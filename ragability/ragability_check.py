#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module to check responses against target facts and assign scores. This creates a result file with the scores which
can then be used to calculate summary statistics in various ways.
"""

import sys
import json
import argparse
import datetime
import hjson
from logging import DEBUG
from ragability.data import read_input_file, read_prompt_file
from llms_wrapper.config import read_config_file, update_llm_config
from ragability.logging import logger, set_logging_level, add_logging_file
from llms_wrapper.llms import LLMS, LLM
from ragability.utils import pp_config
from ragability.checks import CHECKS

DEFAULT_PROMPT = {
    "system": "You are an expert analyzing responses and how they related to desired facts or properties of the responses. You will be given the response following RESPONSE: and before QUERY:, and a query telling you what to analyze after QUERY:",
    "user": "RESPONSE: ${response} QUERY: ${query}",
}

# TODO: allow ${fact0} to ${fact9} as substitution fields.


def get_args():
    """
    Get the command line arguments
    """
    parser = argparse.ArgumentParser(description='Check responses against target facts and assign scores')
    parser.add_argument('--input', '-i', type=str, help='Input file with the responses from ragability_query (or from config), jsonl, json, yaml', required=False)
    parser.add_argument('--output', '-o', type=str, help='Output file with the checking results (default: $DATETIME.out.jsonl), jsonl, json, yaml', required=False)
    parser.add_argument("--config", "-c", type=str, help="Config file with the LLM and other info, json, jsonl, yaml", required=False)
    parser.add_argument('--usellm', '-u', type=str, help='The alias of the configured LLM to use (use first one found)', required=False)
    parser.add_argument("--promptfile", "-pf", type=str, help="File with the prompt to use for the checking queries (or use config), jsonl, json, yaml", required=False)
    parser.add_argument("--all", "-a", action="store_true", help="Run all queries, even if they have a response", required=False)
    parser.add_argument("--logfile", "-f", type=str, help="Log file", required=False)
    parser.add_argument("--dry-run", "-n", action="store_true", help="Dry run, do not actually run the queries", required=False)
    parser.add_argument("--verbose", "-v", action="store_true", help="Be more verbose and inform what is happening", required=False)
    parser.add_argument("--debug", "-d", action="store_true", help="Debug mode", required=False)
    args_tmp = parser.parse_args()
    tmp = {}
    tmp.update(vars(args_tmp))
    args: dict = tmp

    # if a config file is specified, read the config file using our config reading function and update the arguments.
    # The config data may contain:
    # - input: used only if not specified in the command line arguments
    # - output: used only if not specified in the command line arguments
    # - llm: added to the ones specified in the command line arguments
    # - prompt: used to add config info to the llms specified in the command line arguments
    if args["config"]:
        config = read_config_file(args["config"])
        config.update(args)
        args = config
    if not args["input"]:
        print("Error: Missing input file")
        parser.print_help()
        sys.exit(1)
    update_llm_config(args)
    # read the prompt file into memory, add prompts to the "prompts" key in the config, raise an error if the
    # prompt id is already in the config
    if args["promptfile"]:
        prompts = read_prompt_file(args["promptfile"])   # this is a list of dicts with key "pid" containing the id
        if "prompts" not in args:
            args["prompts"] = []
        for prompt in prompts:
            if prompt["pid"] in args["prompts"]:
                raise ValueError(f"Error: Prompt id {prompt['pid']} already in config")
            args["prompts"].append(prompt)
    # create a "prompts_dict" key in the config which is a dict mapping the prompt id to the prompt dict
    if args.get("prompts") is None:
        args["prompts"] = []
    args["prompts_dict"] = {prompt["pid"]: prompt for prompt in args.get("prompts", [])}
    return args


def check_check(check: dict, example: dict, config: dict) -> bool:
    """
    This returns True if the check is correct, False if it can be skipped or raises an exception if the error cannot be
    skipped.
    """
    # make sure the func field is present and that the func field is a string
    # now if the func is not LLM, we can use the function directly, otherwise we need to query the LLM
    if "func" not in check:
        logger.warning(f"Warning: Missing 'func' field in check in example {example['qid']}")
        return False
    if "metrics" not in check:
        logger.warning(f"Warning: Missing 'metrics' field in check in example {example['qid']}")
        return False
    if not isinstance(check["func"], str):
        logger.warning(f"Warning: 'func' field in check must be a string in example {example['qid']}")
        return False
    # make sure the function is in the CHECKS dictionary
    if check["func"] not in CHECKS:
        logger.warning(f"Warning: Check function {check['func']} not in CHECKS in example {example['qid']}")
        return False
    func = CHECKS[check["func"]]
    # check if the number of parameters defined with "parms" matches the number of parameters required by the function
    nargs = func["nargs"]
    args = check.get("args", [])
    if nargs != len(args):
        logger.warning(f"Warning: Wrong number of positional arguments in check for function {func['func']} in example {example['qid']}: {len(args)} instead of {nargs}")
        return False
    if not config['all'] and "result" in check:
        logger.debug(f"Skipping check {check['query']} with result")
        return False
    return True


def run_check(check, llm: LLM, example, config, debug=False):
    llmname = llm["alias"]
    cid = check.get("cid", "NOID")
    # check the check
    if not check_check(check, example, config):
        logger.debug(f"Skipping check in example {example['qid']}")
        return

    # if there is a query in the check, invoke the checker LLM and use the response from the checker
    # as the response to check. If there is no query, use the response from the example as the response to check
    response = None   # this will hold the string to check
    if "query" in check and check["query"] is not None:
        query = check["query"]
        check_for = check.get("check_for")
        # get the prompt id from the check, if there is none, use the default prompt, otherwise use the prompt
        # with that id in the config. If a pid is specified which is not present, this is an error
        if "pid" in check:
            if check["pid"] in config["prompts_dict"]:
                theprompt = config["prompts_dict"][check["pid"]].copy()
            else:
                logger.warning(f"Error: Prompt id {check['pid']} not found for example {example['qid']}")
                logger.debug(f"Have prompt ids {config['prompts_dict'].keys()}")
                check["error"] = f"Prompt id {check['pid']} not found"
                check["result"] = None
                return
        else:
            theprompt = DEFAULT_PROMPT.copy()
        for role, text in theprompt.items():
            text = text.replace("${query}", query)
            text = text.replace("${answer}", example["response"])
            if check_for:
                text = text.replace("${check_for}", check_for)
            theprompt[role] = text
        # check if we have a dry run, if yes, just log what we would do, otherwise query the LLM
        messages = llm.make_messages(prompt=theprompt)
        if config['dry_run']:
            logger.info(f"Would query checker-LLM {llmname} with messages: {messages}")
            response = ""
            error = "NOT RUN: DRY-RUN"
            return
        if config['verbose']:
            logger.info(f"Querying checker-LLM {llmname} for example {example['qid']} and check {cid}")
        ret = llm.query(messages=messages, return_cost=True, debug=config['debug'])
        response = ret.get("answer", "")
        check["cost"] = ret.get("cost", 0)
        check["response"] = response
        error = ret.get("error", "")
        check["llm"] = llmname
        # if we had an error with the checker LLM, log it and return, we cannot check the response
        if error:
            logger.warning(f"Error from checking LLM, cannot check: {error}")
            check["error"] = error
            check["result"] = None
            return
    else:
        response = example["response"]
    func_config = CHECKS[check["func"]]
    func = func_config["func"]
    nargs = func_config["nargs"]
    args = check.get("args", [])
    assert len(args) == nargs, f"Error: Wrong number of positional arguments in check for function {func['func']}: {len(args)} instead of {nargs}"
    kwargs = check.get("kwargs", {})
    try:
        result = func(response, *args, **kwargs)
        error = ""
    except Exception as e:
        logger.error(f"Error in check function {func}: {e}")
        result = None
        error = f"Error in check function {func}: {e}"
    check["result"] = result
    check["error"] = error


def run(config: dict):
    # check the configuration: for checkking, we want exactly one LLM to be configured and we want
    # to have a single prompt or no promot configured. If no prompt is configured, a default prompt will be used.
    if len(config["llms"]) < 1:
        raise ValueError(f"Error: at least one LLM must be configured")
    # if usellm is configured, we want to use the LLM with that alias, otherwise we use the first in the list
    llmname = ""
    if config["usellm"]:
        for llm in config["llm"]:
            if llm["alias"] == config["usellm"]:
                thellmname = llm["alias"]
                break
        if not llmname:
            raise ValueError(f"Error: LLM with alias {config['usellm']} not found")
    else:
        llmname = config["llms"][0]["alias"]
    if len(config["prompts"]) == 0:
        theprompt = DEFAULT_PROMPT
        logger.warning(f"Warning: No prompt configured, using default prompt")
    # read the input file into memory, we do not expect it to be too large and we want to check the format
    # of all json lines
    inputs = read_input_file(config["input"])
    logger.info(f"Loaded {len(inputs)} queries from {config['input']}")
    logger.info(f"LLM to use: {llmname}")
    logger.info(f"Prompts found: {len(config['prompts_dict'])}")

    # initialize the LLMS object with the configuration
    llms = LLMS(config)
    llm: LLM = llms[llmname]

    if not config['output']:
        config['output'] = f"{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.checked.hsjon"
    # write either a jsonl or json file, depending on the file extension
    if not config['output'].endswith(".json") and not config['output'].endswith(".jsonl") and not config[
        'output'].endswith(".hjson"):
        print(f"Error: Output file must end in .json, .jsonl or .hjson, not {config['output']}")
    n_errors = 0
    n_outputs = 0
    total_cost = 0
    with open(config['output'], 'w') as f:
        if config['output'].endswith(".json") or config['output'].endswith(".hjson"):
            f.write("[\n")
        for example in inputs:
            # check if the example has checks at all, give a warning if not
            if not "checks" in example or len(example["checks"]) == 0:
                logger.warning(f"Warning: No checks in example {example['qid']}")
                continue
            # if the example has an error, we cannot check it, so we skip it
            if example.get("error"):
                logger.warning(f"Skipping example {example['qid']} with error: {example['error']}")
                continue
            # now go through each of the checks: if we already have a check result, skip unless the --all option is given
            # if the function is LLM, we need to run the function on the result of querying the LLM, otherwise
            # we directly run the function on the response from the query stage
            for check in example["checks"]:
                run_check(check, llm, example, config, debug=config["debug"])
                cost = check.get("cost", 0)
                total_cost += cost
                if check.get("error"):
                    logger.warning(f"Error in check {check['query']}: {check['error']}")
                    n_errors += 1
            # write the example to the output file
            towrite = example
            n_outputs += 1
            if config['output'].endswith(".json"):
                f.write(json.dumps(towrite, indent=2) + "\n")
            elif config['output'].endswith(".hjson"):
                f.write(hjson.dumps(towrite, indent=2) + "\n")
            else:
                f.write(json.dumps(towrite) + "\n")
        if config['output'].endswith(".json") or config['output'].endswith(".hjson"):
            f.write("]\n")
    logger.info(f"Wrote {n_outputs} examples to {config['output']}, {n_errors} errors")
    logger.info(f"Total cost: {total_cost}")


def main():
    args = get_args()
    if args["logfile"]:
        add_logging_file(args["logfile"])
    if args["debug"]:
        set_logging_level(DEBUG)
        ppargs = pp_config(args)
        logger.debug(f"Effective arguments: {ppargs}")
    run(args)


if __name__ == '__main__':
    main()