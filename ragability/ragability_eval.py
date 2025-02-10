#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module for the CLI to create evaluation reports from a ragability_check output file.
"""

import os, sys
from typing import List, Dict, Optional
import json
import argparse
import pandas as pd
from pandas.core.frame import DataFrame
import hjson
import sklearn as sk
from collections import defaultdict, Counter
from logging import DEBUG
from ragability.logging import logger, set_logging_level, add_logging_file
from ragability.data import read_input_file
from ragability.utils import pp_config
from ragability.checks import CHECKS


def make_grouping_func(
    df: pd.DataFrame,
    tags: Optional[List[str]] = None,
    fields: Optional[Dict[str,str]] = None ):
    """
    Create a function which can be used as an argument to the pandas group_by method on the given dataframe.
    This creates a binary grouping where one group consists of all the rows that match the given tags and field values,
    and another group which does not.
    """
    # if both tags and fields are None or empty, raise and Exception
    if tags is None and fields is None:
        raise Exception("No grouping criteria")

    def the_groupby_func(index):
        row = df.loc[index]
        if tags:
            tag_values = [s.strip() for s in row["tags"].split(",")]
            for t in tags:
                if t not in tag_values:
                    logger.debug(f"Tag {t} not in {tag_values} in {row} for groupby {tags}")
                    return False
        if fields:
            for fname, fval in fields.items():
                if row[fname] != fval:
                    return False
        return True
    return the_groupby_func


def get_args():
    """
    Get the command line arguments
    """
    parser = argparse.ArgumentParser(description='Evaluation of a ragability_check output file')
    parser.add_argument('--input', '-i', type=str, help='Input ragability_check output file', required=True)
    parser.add_argument('--save-json', '-o', type=str,
                        help='Output json or hjson', required=False)
    parser.add_argument('--config', '-c', type=str, help='Configuration file', required=False)
    parser.add_argument("--save-longdf", type=str, help="Save the long format dataframe to a csv or tsv file", required=False)
    parser.add_argument("--save-widedf", type=str, help="Save the wide format dataframe to a csv or tsv file", required=False)
    parser.add_argument('--verbose', '-v', action="store_true",
                        help='Be more verbose', required=False)
    parser.add_argument('--by_tags', nargs="+", type=str,
                        help='List of tags or comma-separated taglists to evaluate by', required=False)
    parser.add_argument('--by_qfields', nargs="+", type=str,
                        help='List of query fields to evaluate by', required=False)
    parser.add_argument("--debug", "-d", action="store_true", help="Debug mode", required=False)
    parser.add_argument("--debug-save-checkdfs", action="store_true", help="Save all the per-metric data frames", required=False)
    args_tmp = parser.parse_args()
    args = {}
    args.update(vars(args_tmp))
    return args


Q_STANDARD_FIELDS = ["qid", "tags", "llm", "facts", "query", "pids", "checks", "notes", "error", "response"]
C_STANDARD_FIELDS = ["cid", "query", "func", "metrics", "result", "notes", "error", "response"]


def run(config: dict):
    # read the input file and collect for each check the necessary fields
    indata = read_input_file(config["input"])
    checksdata = defaultdict(lambda: defaultdict(list))
    # counter to count the queries with errors
    n_errors = 0
    n_errors_per_llm = Counter()
    nc_errors = 0
    nc_errors_per_llm = Counter()
    n_rows = 0
    for idx, q in enumerate(indata):
        error = q.get("error")
        llm = q.get("llm")
        if not llm:
            raise ValueError(f"Error: Missing 'llm' field in entry with index {idx}: {q}")
        if error:
            n_errors += 1
            n_errors_per_llm[llm] += 1
            continue
        for check in q["checks"]:
            func = check["func"]
            funcdef = CHECKS.get(func)
            kind = funcdef["kind"]
            if not funcdef:
                logger.error(f"Check function {func} not found in check for qid {q['qid']}")
                nc_errors += 1
                nc_errors_per_llm[llm] += 1
                continue
            metrics = check["metrics"]
            for metric in metrics:
                row = dict(
                    target=funcdef["target"],
                    result=check["result"],
                    qid=q["qid"],
                    tags=q["tags"],
                    llm=llm,
                )
                # add any non=standard fields from the query to the row
                for k, v in q.items():
                    if k not in Q_STANDARD_FIELDS:
                        row[k] = v
                # add any non-standard fields from the check to the row
                for k, v in check.items():
                    if k not in C_STANDARD_FIELDS:
                        row[f"check_{k}"] = v
                checksdata[kind][metric].append(row)
                n_rows += 1
    logger.debug(f"Errors in queries: {n_errors}")
    logger.debug(f"Errors in checks: {nc_errors}")
    logger.debug(f"Errors in queries per llm: {n_errors_per_llm}")
    logger.debug(f"Errors in checks per llm: {nc_errors_per_llm}")
    logger.debug(f"Generated check data rows: {n_rows}")
    # convert the checksdata to a dictionary of dataframes, one for each metric
    checkdfs = {}
    for kind, kinddata in checksdata.items():
        for metric, metricdata in kinddata.items():
            dftmp = pd.DataFrame(metricdata)
            checkdfs[f"{kind}:{metric}"] = dftmp
            logger.debug(f"Generated check data dataframe for {kind}:{metric} with {len(dftmp)} rows and {len(dftmp.columns)} columns")
            # if --debug option is given, write the dataframe to a csv file
            if config.get("debug-save-checkdfs"):
                dftmp.to_csv(f"debug_checkdata_{kind}_{metric}.csv", index=False)
    logger.debug(f"Generated check data dataframes: {len(checkdfs)} for keys {list(checkdfs.keys())}")

    # we have to generate an evaluation report dataframe of the following format:
    # * column "group" contains a description of how the subgroup is defined
    # * columns "llm" contains the llm name
    # * one column per metric and statistic, for binary metrics this is of the form "metricname:accuracy"
    # * one column per metric which contains the number of rows, this is of the form "metricname:n"
    #
    # example:
    # group, llm, metric1:accuracy, metric1:n, metric2:accuracy, metric2:n
    #
    # To prepare the data for this dataframe, collect the rows of the dataframe in list, where each row
    # is a dictionary with all the necessary fields

    dfrows = []
    # first of all, create the entries without any grouping, just by LLMs for all the metrics
    for key, df in checkdfs.items():
        kind, metric = key.split(":")
        for llm, llmgroup in df.groupby("llm"):
            dfrows.append(dict(
                group="all",
                llm=llm,
                metric=f"{metric}:accuracy",
                value=sk.metrics.accuracy_score(llmgroup["target"].values, llmgroup["result"].values)
            ))
            dfrows.append(dict(
                group="all",
                llm=llm,
                metric=f"{metric}:n",
                value=len(llmgroup)
            ))
    logger.debug(f"Generated {len(dfrows)} rows for all LLMs")


    # now if we have grouping criteria, do the following: for each of the by_tags or by_qfields criteria,
    # create a grouping function to split the df into two groups, one that matches the criteria and one that does not.
    # Create the corresponding dataframes with the rows matching the criteria and the other with the rows not
    # matching the criteria. Then group each of these dataframes by LLM and calculate the accuracy and number of rows
    # for each metric.
    if config.get("by_tags") or config.get("by_qfields"):
        for groupbyname in ["by_tags", "by_qfields"]:
            groupbyvalues = config.get(groupbyname)
            logger.debug(f"Grouping by {groupbyname} with values {groupbyvalues}")
            if not groupbyvalues:
                continue
            n_rows4group = 0
            for groupbyvalue in groupbyvalues:
                logger.debug(f"Generating rows for grouping by {groupbyname} with value {groupbyvalue}")
                for key, df in checkdfs.items():
                    if groupbyname == "by_tags":
                        grouping_func = make_grouping_func(df, tags=[groupbyvalue])
                    else:
                        # find all possible values of the field in the df
                        fields = {groupbyvalue: v for v in df[groupbyvalue].unique()}
                        grouping_func = make_grouping_func(df, fields=fields)
                    kind, metric = key.split(":")
                    grouped = df.groupby(grouping_func)
                    for group, groupdf in grouped:
                        logger.debug(f"Grouping {key} by {groupbyname} with value {groupbyvalue} and group {group}")
                        if group:
                            groupname = f"{groupbyvalue}:yes"
                        else:
                            groupname = f"{groupbyvalue}:no"
                        for llm, llmgroup in groupdf.groupby("llm"):
                            dfrows.append(dict(
                                group=groupname,
                                llm=llm,
                                metric=f"{metric}:accuracy",
                                value=sk.metrics.accuracy_score(llmgroup["target"].values, llmgroup["result"].values)
                            ))
                            dfrows.append(dict(
                                group=groupname,
                                llm=llm,
                                metric=f"{metric}:n",
                                value=len(llmgroup)
                            ))
                            n_rows4group += 2
            logger.debug(f"Generated {n_rows4group} rows for grouping by {groupbyname}")
    logger.debug(f"Generated {len(dfrows)} rows in total")
    # create the long format dataframe from the list of rows
    dfout_long = pd.DataFrame(dfrows)
    if config.get("save-longdf"):
        if config["save-longdf"].endswith(".csv"):
            dfout_long.to_csv(config["save-longdf"], index=False)
        elif config["save-longdf"].endswith(".tsv"):
            dfout_long.to_csv(config["save-longdf"], index=False, sep="\t")
        else:
            raise Exception(f"Error: Output file must end in .csv or .tsv, not {config['save-longdf']}")
    # now pivot the long format dataframe to the wide format
    dfout = dfout_long.pivot_table(index=["group", "llm"], columns="metric", values="value")
    dfout.reset_index(inplace=True)
    if config.get("save-widedf"):
        if config["save-widedf"].endswith(".csv"):
            dfout.to_csv(config["save-widedf"], index=False)
        elif config["save-widedf"].endswith(".tsv"):
            dfout.to_csv(config["save-widedf"], index=False, sep="\t")
        else:
            raise Exception(f"Error: Output file must end in .csv or .tsv, not {config['save-widedf']}")
    # if the output file is specified, save the dataframe as csv or tsv depending on the extension or
    # save a dictionary representation of the dataframe as json or hjson
    if config.get("save-json"):
        if config["output"].endswith(".json"):
            dfout.to_json(config["output"], orient="records")
        elif config["output"].endswith(".hjson"):
            with open(config["output"], "wt") as outfp:
                hjson.dump(dfout.to_dict(orient="records"), outfp)
        else:
            raise Exception(f"Error: Output file must end in .csv, .tsv, .json or .hjson, not {config['output']}")
    # if verbose is set, or no output file is specified, write the results to stdout using textual formattign of
    # the dataframe
    if config.get("verbose") or not config.get("output"):
        print(dfout_long.to_string())


def main():
    args = get_args()
    if args["debug"]:
        set_logging_level(DEBUG)
        ppargs = pp_config(args)
        logger.debug(f"Effective arguments: {ppargs}")
    run(args)


if __name__ == '__main__':
    main()