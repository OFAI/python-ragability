#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module for the CLI to concatenate several json or hjson files into one.
"""

import argparse
from collections import Counter
from logging import DEBUG
from ragability.logging import logger, set_logging_level
from ragability.data import read_input_file
from ragability.utils import pp_config


def get_args():
    """
    Get the command line arguments
    """
    parser = argparse.ArgumentParser(description='Show information about the contents of a hjsonm json or jsonl file')
    parser.add_argument('--input', '-i', type=str, help='One or more json, hjson, jsonl files', required=True)
    parser.add_argument('--debug', '-d', action='store_true', help='Debug mode')
    args_tmp = parser.parse_args()
    args = {}
    args.update(vars(args_tmp))
    return args


def run(config: dict):
    # read each of the input files in turn and write all the entries of each file to the output file
    data = read_input_file(config["input"])
    # show the following information: number of entries, and all the keys that are present in the entries
    # and how many times each key is present. Also if there are nested keys, e.g. "a.b.c.d" show these as well.
    # Dictionaries can be nested arbitrarily.
    # If there are nested keys within lists, show as a.b[].c where a.b is a list of dicts.
    n_total = 0
    keys = Counter()
    total_cost = 0
    total_cost_per_llm = Counter()
    query_cost = 0
    checking_cost = 0
    have_cost = False
    def count_keys(entry, prefix=""):
        for k, v in entry.items():
            keys[prefix + k] += 1
            if isinstance(v, dict):
                count_keys(v, prefix + k + ".")
            elif isinstance(v, list):
                for idx, item in enumerate(v):
                    if isinstance(item, dict):
                        count_keys(item, prefix + k + f"[{idx}].")

    for entry in data:
        count_keys(entry)
        n_total += 1
        # if there is a toplevel "cost" key and a toplevel "llm" key, add to total cost and total cost per llm
        if "cost" in entry and "llm" in entry:
            have_cost = True
            total_cost += entry["cost"]
            total_cost_per_llm[entry["llm"]] += entry["cost"]
            query_cost += entry["cost"]
        # if we have a "checks" key which has a non-empty list value, process each of the elements and
        # extract the cost and llm and update total cost and total cost per llm as well as checking cost
        if "checks" in entry and entry["checks"]:
            for check in entry["checks"]:
                if "cost" in check and "llm" in check:
                    have_cost = True
                    total_cost += check["cost"]
                    total_cost_per_llm[check["llm"]] += check["cost"]
                    checking_cost += check["cost"]

    logger.info(f"Read {n_total} entries from {config['input']}")
    logger.info(f"Keys found in the entries:")
    for k, v in keys.items():
        logger.info(f"{k}: {v}")
    if have_cost:
        logger.info(f"Total cost: {total_cost}")
        logger.info(f"Total cost per LLM:")
        for llm, cost in total_cost_per_llm.items():
            logger.info(f"  {llm}: {cost}")
        logger.info(f"Query cost: {query_cost}")
        logger.info(f"Checking cost: {checking_cost}")
    else:
        logger.info("No cost information found")



def main():
    args = get_args()
    if args["debug"]:
        set_logging_level(DEBUG)
        ppargs = pp_config(args)
        logger.debug(f"Effective arguments: {ppargs}")
    run(args)


if __name__ == '__main__':
    main()