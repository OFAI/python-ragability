#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module to run a bunch of ragability queries and get the responses.
"""

import json
import argparse
import re
import datetime
import hjson
from collections import Counter
from logging import DEBUG
from ragability.logging import logger, set_logging_level, add_logging_file
from ragability.data import read_input_file, read_prompt_file
from llms_wrapper.config import read_config_file, update_llm_config
from llms_wrapper.llms import LLMS, ROLES
from ragability.utils import pp_config


def get_args():
    """
    Get the command line arguments
    """
    parser = argparse.ArgumentParser(description='Run a bunch of ragability queries and get the responses')
    parser.add_argument('--input', '-i', type=str, help='Input file with the facts and queries (or from config), jsonl, json, yaml', required=False)
    parser.add_argument('--output', '-o', type=str, help='Output file with the responses (default: $DATETIME.out.jsonl), jsonl, json, yaml', required=False)
    parser.add_argument("--config", "-c", type=str, help="Config file with the LLM and other info for an experiment, json, jsonl, yaml", required=False)
    parser.add_argument('--llms', '-l', nargs="*", type=str, default=[], help='LLMs to use for the queries (or use config)', required=False)
    parser.add_argument("--promptfile", "-pf", type=str, help="File with the prompt to use for the queries (or use config), jsonl, json, yaml", required=False)
    parser.add_argument("--dry-run", "-n", action="store_true", help="Dry run, do not actually run the queries", required=False)
    parser.add_argument("--all", "-a", action="store_true", help="Run all queries, even if they have a response", required=False)
    parser.add_argument("--logfile", "-f", type=str, help="Log file", required=False)
    parser.add_argument("--debug", "-d", action="store_true", help="Debug mode", required=False)
    parser.add_argument("--verbose", "-v", action="store_true", help="Be more verbose and inform what is happening", required=False)
    args_tmp = parser.parse_args()
    for llm in args_tmp.llms:
        if not re.match(r"^[a-zA-Z0-9_\-./]+/.+$", llm):
            raise Exception(f"Error: 'llm' field must be in the format 'provider/model' in line: {llm}")
    # convert the argparse object to a dictionary
    tmp = {}
    tmp.update(vars(args_tmp))
    args: dict = tmp

    # if a config file is specified, read the config file using our config reading function and update the arguments.
    # The config data may contain:
    # - input: used only if not specified in the command line arguments
    # - output: used only if not specified in the command line arguments
    # - llms: added to the ones specified in the command line arguments
    # - prompt: used to add config info to the llms specified in the command line arguments
    if args["config"]:
        config = read_config_file(args["config"], update=False)
        # merge the args into the config, giving precedence to the args, except for the LLM list, which is merged
        # by adding the args to the config
        oldllms = config.get("llms", [])
        config.update(args)
        # add the llms from the args to the llms from the config, but only if the llms is not already in the config
        mentionedllm = [llm if isinstance(llm, str) else llm["llm"] for llm in config["llms"]]
        for llm in args["llms"]:
            if llm not in mentionedllm:
                oldllms.append(llm)
        config["llms"] = oldllms
        args = config
    # make sure we got the input file, prompt and llm arguments, if not, show an error message, then the
    # argparse help message and exit
    # also, we need the prompt file. If we have both, an error message is shown.
    # If we have a prompt, put it into a list as the only element, otherwise use the read_prompt_file function
    # to read the prompt file into a list
    if not args["input"]:
        parser.print_help()
        raise Exception("Error: Missing input file")
    if not args["llms"]:
        parser.print_help()
        raise Exception("Error: Missing llms argument")
    if not args["promptfile"]:
        parser.print_help()
        raise Exception("Error: Must specify promptfile")
    args["prompt"] = read_prompt_file(args["promptfile"])
    # update the llm configuration in the args dict
    update_llm_config(args)
    return args


def run(config: dict):
    # read the input file into memory, we do not expect it to be too large and we want to check the format
    # of all json lines
    inputs = read_input_file(config["input"])
    llms = LLMS(config)
    llmnames = llms.list_aliases()
    logger.info(f"LLMs to use: {llmnames}")
    logger.info(f"Loaded {len(inputs)} queries from {config['input']}")
    logger.info(f"Got {len(config['prompt'])} prompts")

    # for each LLM, for each prompt, for each query, query the LLM and write the response to the output file
    # if the output file is not specified, use the current date and time to create a default output file
    # if the output file exists, overwrite it

    if not config['output']:
        config['output'] = f"{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.out.jsonl"
    # write either a jsonl or json file, depending on the file extension
    if not config['output'].endswith(".json") and not config['output'].endswith(".jsonl") and not config['output'].endswith(".hjson"):
        raise Exception(f"Error: Output file must end in .json, .jsonl or .hjson, not {config['output']}")
    prompt_idx = {p["pid"]: idx for idx, p in enumerate(config["prompt"])}
    n_llm_errors = 0
    n_outputs = 0
    total_cost = 0
    cost_per_llm = Counter()
    with open(config['output'], 'w') as f:
        if config['output'].endswith(".json") or config['output'].endswith(".hjson"):
            f.write("[\n")
        for llmname in llmnames:
            for query in inputs:
                # if we have the field "pid" in the query, we use just that prompt, otherwise,
                # if we have the field "pids" in the query, we iterate over those prompts, otherwise we use all prompts
                # defined in the config
                # NOTE: the field "pid" is put into the output of a processed query, which makes it possible to
                # reprocess the output file with the same prompt
                if "pid" in query:
                    pids = [query["pid"]]
                elif "pids" in query:
                    pids = query["pids"]
                else:
                    pids = prompt_idx.keys()
                for pid in pids:
                    prompt_tmpl = config["prompt"][prompt_idx[pid]]
                    logger.debug(f"Processing prompt {pid}")
                    # if the response is already in the query and there is no or an empty error,
                    # skip unless the option --all is give
                    if not config['all'] and query.get("response") is not None and not query.get("error"):
                        logger.debug(f"Skipping query {query['qid']} with response")
                        continue
                    prompt = prompt_tmpl.copy()
                    logger.debug(f"Processing query {query['qid']}")
                    if query.get("response"):     # we already have a response, skip
                        logger.debug(f"Skipping query {query['qid']} with response")
                        continue
                    # replace facts and query variables in the prompt
                    facts = query.get("facts")
                    if facts is None:
                        pass
                    elif facts == []:
                        facts = None
                    elif isinstance(facts, str):
                        facts = [facts]
                    logger.debug(f"Got facts list {facts}")
                    for role, content in prompt.items():
                        if role in ROLES:
                            if facts is not None:
                                facttmpl = prompt.get("fact")
                                if facttmpl:
                                    factsfmt = []
                                    for idx, fact in enumerate(facts):
                                        factsfmt.append(facttmpl.replace("${fact}", fact).replace("${n}", str(idx+1)))
                                    factsfmt = "".join(factsfmt)
                                else:
                                    factsfmt = "\n".join(facts)
                                prompt[role] = content.replace("${facts}", factsfmt)
                            prompt[role] = prompt[role].replace("${query}", query["query"])
                    messages = llms.make_messages(prompt=prompt)
                    if config['dry_run']:
                        logger.info(f"Would query LLM {llmname} with prompt {prompt['pid']} for query {query['qid']}")
                        logger.debug(f"Messages: {messages}")
                        response = ""
                        error = "NOT RUN: DRY-RUN"
                    else:
                        if config['verbose']:
                            logger.info(f"Querying LLM {llmname} with prompt {prompt['pid']} for query {query['qid']}")
                        else:
                            logger.debug(f"Querying LLM {llmname} with prompt {prompt['pid']} for query {query['qid']}")
                        logger.debug(f"Messages: {messages}")
                        ret = llms.query(llmname, messages=messages, return_cost=True, debug=config['debug'])
                        response = ret.get("answer", "")
                        error = ret.get("error", "")
                        cost = ret.get("cost", 0)
                        total_cost += cost
                        cost_per_llm[llmname] += cost
                        if error:
                            logger.warning(f"Error querying LLM {llmname} with prompt {prompt['pid']} for query {query['qid']}: {error}")
                            n_llm_errors += 1

                    towrite = query.copy()
                    towrite["response"] = response
                    towrite["error"] = error
                    towrite["pid"] = pid
                    towrite["llm"] = llmname
                    towrite["cost"] = cost
                    n_outputs += 1
                    if config['output'].endswith(".json"):
                        f.write(json.dumps(towrite, indent=2) + "\n")
                    elif config['output'].endswith(".hjson"):
                        f.write(hjson.dumps(towrite, indent=2) + "\n")
                    else:
                        f.write(json.dumps(towrite) + "\n")
        if config['output'].endswith(".json") or config['output'].endswith(".hjson"):
            f.write("]\n")

    logger.info(f"Wrote {n_outputs} entries to {config['output']}, {n_llm_errors} LLM errors")
    logger.info(f"Total cost: {total_cost}")
    logger.info(f"Cost per LLM:")
    for llmname, cost in cost_per_llm.items():
        logger.info(f"{llmname}: {cost}")


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