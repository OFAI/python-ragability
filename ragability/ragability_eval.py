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
    fields: Optional[List[str]] = None):
    """
    Create a function which can be used as an argument to the pandas group_by method on the given dataframe.
    This creates a binary grouping where one group consists of all the rows that match the given tags and field values,
    and another group which does not.
    """
    # NOTE: for now this must be used for either tags or fields, not both
    assert not (tags and fields)

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
            return True
        elif fields:
            keys = []
            for fname in fields:
                keys.append(row[fname])
            groupname = ",".join(keys)
            return groupname
        else:
            raise Exception("No grouping criteria")
    return the_groupby_func


def get_args():
    """
    Get the command line arguments
    """
    parser = argparse.ArgumentParser(description='Evaluation of a ragability_check output file')
    parser.add_argument('--input', '-i', type=str, help='Input ragability_check output file', required=True)
    parser.add_argument('--save_json', '-o', type=str,
                        help='Output json or hjson', required=False)
    parser.add_argument('--config', '-c', type=str, help='Configuration file', required=False)
    parser.add_argument("--save_longdf", type=str, help="Save the long format dataframe to a csv or tsv file", required=False)
    parser.add_argument("--save_widedf", type=str, help="Save the wide format dataframe to a csv or tsv file", required=False)
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
            error = check.get("error")
            if error:
                nc_errors += 1
                nc_errors_per_llm[llm] += 1
                continue
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
                    func=func,
                    kind=kind,
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
            try:
                score_value = sk.metrics.accuracy_score(llmgroup["target"].values, llmgroup["result"].values)
            except Exception as e:
                logger.error(f"Error: {e} in calculating metric {metric} for {llm} in {key}")
                # print the rows from the df where the result value is None or NaN and make sure all
                # columns are printed properly! For this, we need to convert each row to a dictionary
                # of column name / value pairs and print each dictionary in a separate line.
                for idx, row in llmgroup.iterrows():
                    # only print the rows where the result is None or NaN
                    if row["result"] is None or row["result"] != row["result"]:
                        logger.error(f"Row {idx}: {dict(row)}")
                # set it to NaN if there is an error
                score_value = float("nan")
            dfrows.append(dict(
                group="all",
                llm=llm,
                metric=f"{metric}:accuracy",
                value=score_value
            ))
            dfrows.append(dict(
                group="all",
                llm=llm,
                metric=f"{metric}:n",
                value=len(llmgroup)
            ))
    logger.debug(f"Generated {len(dfrows)} rows for all LLMs")

    # for eachof the tag names mentioned in the config "by_tags" parameter, create a group for all rows
    # which do have the tag, labeling with the group name "tagname:yes" and for all rows which do not have the tag
    # labeling with the group name "tagname:no". For each of these groups, create the same metrics as for the "all"
    # group.
    if config.get("by_tags"):
        for tagname in config.get("by_tags"):
            logger.debug(f"Generating rows for grouping by tag {tagname}")
            for key, df in checkdfs.items():
                grouping_func = make_grouping_func(df, tags=[tagname])
                kind, metric = key.split(":")
                grouped = df.groupby(grouping_func)
                for group, groupdf in grouped:
                    logger.debug(f"Grouping {key} by tag {tagname} and group {group}")
                    if group:
                        groupname = f"{tagname}:yes"
                    else:
                        groupname = f"{tagname}:no"
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

    # for each of the field names mentioned in the config "by_qfields" parameter, find all the different
    # values of the field in the dataframe and create a group for each of these values, labeling with the group name
    # "fieldname:value" for all rows which have the value.
    # For each of these groups, create the same metrics as for the "all" group.
    if config.get("by_qfields"):
        for fieldname in config.get("by_qfields"):
            logger.debug(f"Generating rows for grouping by field {fieldname}")
            for key, df in checkdfs.items():
                grouping_func = make_grouping_func(df, fields=[fieldname])
                kind, metric = key.split(":")
                grouped = df.groupby(grouping_func)
                for group, groupdf in grouped:
                    logger.debug(f"Grouping {key} by field {fieldname} and group {group}")
                    if group:
                        groupname = f"{fieldname}:{group}"
                    else:
                        groupname = f"{fieldname}:no"
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

    logger.debug(f"Generated {len(dfrows)} rows in total")
    # re-order the rows and sort by group, llm, metric
    dfrows = sorted(dfrows, key=lambda x: (x["group"], x["llm"], x["metric"]))

    # create the long format dataframe from the list of rows
    dfout_long = pd.DataFrame(dfrows)
    logger.debug(f"Generated long format dataframe with {len(dfout_long)} rows and {len(dfout_long.columns)} columns")
    if config.get("save_longdf"):
        if config["save_longdf"].endswith(".csv"):
            dfout_long.to_csv(config["save_longdf"], index=False)
        elif config["save_longdf"].endswith(".tsv"):
            dfout_long.to_csv(config["save_longdf"], index=False, sep="\t")
        else:
            raise Exception(f"Error: Output file must end in .csv or .tsv, not {config['save-longdf']}")
    # now pivot the long format dataframe to the wide format
    dfout = dfout_long.pivot_table(index=["group", "llm"], columns="metric", values="value")
    dfout.reset_index(inplace=True)
    if config.get("save_widedf"):
        if config["save_widedf"].endswith(".csv"):
            dfout.to_csv(config["save_widedf"], index=False)
        elif config["save_widedf"].endswith(".tsv"):
            dfout.to_csv(config["save_widedf"], index=False, sep="\t")
        else:
            raise Exception(f"Error: Output file must end in .csv or .tsv, not {config['save_widedf']}")
    # if the output file is specified, save the dataframe as csv or tsv depending on the extension or
    # save a dictionary representation of the dataframe as json or hjson
    if config.get("save_json"):
        if config["save_json"].endswith(".json"):
            dfout.to_json(config["save_json"], orient="records")
        elif config["save_json"].endswith(".hjson"):
            with open(config["save_json"], "wt") as outfp:
                hjson.dump(dfout.to_dict(orient="records"), outfp)
        else:
            raise Exception(f"Error: Output file must end in .csv, .tsv, .json or .hjson, not {config['output']}")
    # if verbose is set, or no output file is specified, write the results to stdout using textual formattign of
    # the dataframe
    if config.get("verbose") or not config.get("save-json"):
        # createa copy of the dataframe with all the rows where the column "metric" has a value
        # which ends with :n removed
        dfout_long_metrics = dfout_long[~dfout_long["metric"].str.endswith(":n")]
        print(dfout_long_metrics.to_string())

    # report the total number and number per LLM of query time errors and checking time errors
    # which we encountered and which were ignored. For the errors per LLM output one line per LLM
    logger.info(f"Errors in queries (ignored for eval): {n_errors}")
    logger.info(f"Errors in queries per llm:")
    if n_errors > 0:
        for llm, n in n_errors_per_llm.items():
            logger.info(f"  {llm}: {n}")
    logger.info(f"Errors in checks (ignored for eval): {nc_errors}")
    logger.info(f"Errors in checks per llm:")
    if nc_errors:
        for llm, n in nc_errors_per_llm.items():
            logger.info(f"  {llm}: {n}")

def main():
    args = get_args()
    if args["debug"]:
        set_logging_level(DEBUG)
        ppargs = pp_config(args)
        logger.debug(f"Effective arguments: {ppargs}")
    run(args)


if __name__ == '__main__':
    main()