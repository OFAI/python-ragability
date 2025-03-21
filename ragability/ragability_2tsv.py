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
    parser.add_argument('--output', '-o', type=str, help='Output tsv file (same as input but with tsv extension)', required=False)
    args_tmp = parser.parse_args()
    args = {}
    args.update(vars(args_tmp))
    return args



def run(config: dict):
    indata = read_input_file(config["input"])
    logger.info(f"Read {len(indata)} records from {config['input']}")
    # indata is a list of nested dictionaries where each of the values in the dictionaries could
    # be a scalar value, a nested dictionary, a scalar value or a list of scalar values or
    # nested dictionaries. We need to flatten this structure into a list of flat dictionaries where
    # each dictionary contains only scalar values. We will use a recursive function to do this.
    # The names use dots to separate nested fields and underscores to separate array indices.
    # Example:
    # indata = [ { "a": 1, "b": [2, 3], "c": { "d": 4, "e": 5 }, "e": [{ "f": 6 },{ "f": 7 }] } ]
    # outdata = [ { "a": 1, "b_0": 2, "b_1": 3, "c.d": 4, "c.e": 5, "e_0.f": 6, "e_1.f": 7 } ]
    # First we analyse all the nested dictionaries in the list to find all the field names
    # and the maximum number of elements in any array.
    # We also need to make sure that none of the text fields contain any new lines or tabs before
    # we write the tsv file.
    def analyse(indata):
        fieldnames = set()
        maxarraysize = 0
        for item in indata:
            for k, v in item.items():
                fieldnames.add(k)
                if isinstance(v, list):
                    maxarraysize = max(maxarraysize, len(v))
        return fieldnames, maxarraysize
    # now we actually convert the list of nested dictionaries into a list of flat dictionaries
    def flatten(indata):
        fieldnames, maxarraysize = analyse(indata)
        flatdata = []
        for item in indata:
            flatitem = {}
            for k in fieldnames:
                v = item.get(k)
                if isinstance(v, list):
                    for i, vi in enumerate(v):
                        flatitem[f"{k}_{i}"] = vi
                elif isinstance(v, dict):
                    for k1, v1 in v.items():
                        flatitem[f"{k}.{k1}"] = v1
                else:
                    flatitem[k] = v
            flatdata.append(flatitem)
        return flatdata
    flatdata = flatten(indata)
    # make sure there are no new lines or tabs in the text fields
    for item in flatdata:
        for k, v in item.items():
            if isinstance(v, str):
                item[k] = v.replace("\n", " ").replace("\t", " ")
    df = pd.DataFrame(flatdata)
    logger.info(f"Converted to dataframe with {df.shape[0]} rows and {df.shape[1]} columns")
    # Now we have the dataframe, we can write it to the output file
    outputfile = config["output"]
    if not outputfile:
        outputfile = os.path.splitext(config["input"])[0] + ".tsv"
    df.to_csv(outputfile, sep="\t", index=False)
    logger.info(f"Output written to {outputfile}")


def main():
    args = get_args()
    run(args)


if __name__ == '__main__':
    main()