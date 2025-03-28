#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module for the CLI to convert data files from json/hjson to tsv formt.

This will create a tsv file where for each array in the json/hjson file, the tsv row contains
as many columns as the maximum number of elements in any of the arrays. The columns are named
with the array index as a suffix, starting at 0. If the array has fewer elements than the maximum, the
missing columns are filled with empty strings. The first row of the tsv file contains the column names.
Nested fields in the json/hjson file are represented by a column name that is the concatenation of the
field names separated by a dot.
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



def get_args():
    """
    Get the command line arguments
    """
    parser = argparse.ArgumentParser(description='Convert json/hjson to tsv')
    parser.add_argument('--input', '-i', type=str, help='Input json/hjson file', required=True)
    parser.add_argument('--all', '-a', action="store_true",
                        help='Also include fields which are always empty or have the same value in all records', required=False)
    parser.add_argument('--output', '-o', type=str, help='Output tsv file (same as input but with tsv extension)', required=False)
    args_tmp = parser.parse_args()
    args = {}
    args.update(vars(args_tmp))
    return args


def max_elements(data: List[Dict], keys: List[str|int]):
    """
    Get the maximum number of elements in the array identified by the given list of keys that lead to the
    nested array.
    """
    maxn = 0
    for record in data:
        # access the nested list or ignore the record if it does not exist
        val = record
        for k in keys:
            if isinstance(val, list):
                val = val[k]
            else:
                val = val.get(k)
            if val is None:
                break
        if val is not None:
            if isinstance(val, list):
                maxn = max(maxn, len(val))
            else:
                maxn = max(maxn, 1)
    return maxn

def run(config: dict):
    indata = read_input_file(config["input"])
    logger.info(f"Read {len(indata)} records from {config['input']}")

    # For now we only support instances with a single element in the "checks"  field and the pid field
    maxn_checks = max_elements(indata, ["checks"])
    if maxn_checks > 1:
        logger.error(f"Only one element in the 'checks' field is supported for now, but found {maxn_checks}")
        sys.exit(1)
    maxn_pids = max_elements(indata, ["checks", 0, "pids"])
    if maxn_pids > 1:
        logger.error(f"Only one element in the 'pids' field is supported for now, but found {maxn_pids}")
        sys.exit(1)
    TOPFIELDS_SCALAR = ["qid", "tags", "query", "WikiContradict_ID", "reasoning_required_c1c2", "response", "error", "pid", "llm"]
    CHECKFIELDS = ["cid", "query", "func", "metrics", "pid", "response", "llm", "result", "error", "check_for"]
    flatdata = []
    # find the maximum number for "facts"
    maxn_facts = max_elements(indata, ["facts"])
    unknownfields = Counter()
    for record in indata:
        flatrecord = {}
        for field in TOPFIELDS_SCALAR:
            flatrecord[field] = record.get(field, "")
        # add the facts fields, not all records have the same number of facts
        facts = record.get("facts")
        if facts is None:
            facts = []
        elif isinstance(facts, str):
            facts = [facts]
        for i in range(maxn_facts):
            if i < len(facts):
                flatrecord[f"facts_{i}"] = facts[i]
            else:
                flatrecord[f"facts_{i}"] = ""
        check = record.get("checks", [{}])[0]
        for field in CHECKFIELDS:
            val = check.get(field, "")
            if isinstance(val, list):
                val = ", ".join(val)
            flatrecord[f"check.{field}"] = val
        # check if the check dict has any fields not mentioned in CHECKFIELDS, if so, count them using the
        # name check.{unknownfieldname}
        for k in check:
            if k not in CHECKFIELDS:
                if k not in ["cost"]:
                    unknownfields[f"check.{k}"] += 1
        # also check if the top level record has any fields not mentioned in TOPFIELDS_SCALAR
        for k in record:
            if k not in TOPFIELDS_SCALAR:
                if k not in ["checks", "c1xq", "c2xq", "cost", "pids", "facts"]:
                    unknownfields[k] += 1
        flatdata.append(flatrecord)
    # convert to a data frame
    df = pd.DataFrame(flatdata)
    # Now find all the fields in flatdata which all have exactly the same value: for each of these fields
    # log the name and value and remove the field from the dataframe
    for col in df.columns:
        if len(df[col].unique()) == 1:
            logger.info(f"Field {col} has the same value in all records: >>{df[col].iloc[0]}<<")
            if not config["all"]:
                df.drop(columns=[col], inplace=True)
    logger.info(f"Converted to dataframe with {df.shape[0]} rows and {df.shape[1]} columns")
    # Now we have the dataframe, we can write it to the output file
    outputfile = config["output"]
    if not outputfile:
        outputfile = os.path.splitext(config["input"])[0] + ".tsv"
    df.to_csv(outputfile, sep="\t", index=False)
    logger.info(f"Output written to {outputfile}")
    # print out the unknown fields, if there are any
    if unknownfields:
        logger.info("Unknown fields:")
        for k, v in unknownfields.items():
            logger.info(f"{k}: {v}")


def main():
    args = get_args()
    run(args)


if __name__ == '__main__':
    main()