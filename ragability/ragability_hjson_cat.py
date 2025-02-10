#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module for the CLI to concatenate several json or hjson files into one.
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
    parser = argparse.ArgumentParser(description='Concatenate json, hjson, jsonl into one file')
    parser.add_argument('--input', '-i', nargs="=", type=str, help='One or more json, hjson, jsonl files', required=True)
    parser.add_argument('--output', '-o', type=str,
                        help='Output file, hjson, json or jsonl', required=True)
    parser.add_argument('--debug', '-d', action='store_true', help='Debug mode')
    args_tmp = parser.parse_args()
    args = {}
    args.update(vars(args_tmp))
    return args


def run(config: dict):
    # read each of the input files in turn and write all the entries of each file to the output file
    n_total = 0
    with open(config['output'], 'w') as f:
        if config['output'].endswith(".json") or config['output'].endswith(".hjson"):
            f.write("[\n")
        for idx, input_file in enumerate(config['input']):
            data = read_input_file(config["input"])
            n_total += len(data)
            logger.debug(f"Read {len(data)} entries from {input_file}")
            if idx > 0:
                f.write(",\n")
            if config['output'].endswith(".json") or config['output'].endswith(".hjson"):
                f.write(json.dumps(data, indent=4))
            else:
                for entry in data:
                    f.write(json.dumps(entry) + "\n")
        if config['output'].endswith(".json") or config['output'].endswith(".hjson"):
            f.write("\n]\n")
    logger.info(f"Written {n_total} entries to {config['output']}")


def main():
    args = get_args()
    if args["debug"]:
        set_logging_level(DEBUG)
        ppargs = pp_config(args)
        logger.debug(f"Effective arguments: {ppargs}")
    run(args)


if __name__ == '__main__':
    main()