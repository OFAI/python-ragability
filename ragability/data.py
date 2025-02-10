"""
Module for functions related to reading or writing files and checking file contents.
"""
import sys
import json
import yaml
import hjson
from ragability.logging import logger


def read_file(input_file):
    """
    Read the input file into memory. Depending on the file extension, the input file is either a jsonl file
    with one json dict per line, a json file which contains the json/hjson representation of an array of dicts, or
    a YAML file containing an array of dicts. Return the list of dicts.

    We only check for json and yaml that the data read is an array, and we check for each entry in the array
    that it is a dict.

    :param input_file: file to read
    :return: array of dicts
    """
    data = []
    if input_file.endswith(".jsonl"):
        with open(input_file, 'r') as f:
            linenr = 0
            for line in f:
                linenr += 1
                # ignore empty lines
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    raise Exception(f"Error: Could not decode JSON line in file {input_file}, line {linenr}: {line}\nError: {e}")
                if not isinstance(entry, dict):
                    raise Exception(f"Error: Entry in line {linenr} is not a dict")
                data.append(entry)
    elif input_file.endswith(".json"):
        with open(input_file, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise Exception(f"Error: Could not decode JSON file {input_file}: {e}")
            if not isinstance(data, list):
                raise Exception(f"Error: JSON file {input_file} does not contain an array")
            for idx, entry in enumerate(data):
                if not isinstance(entry, dict):
                    raise Exception(f"Error: Entry {idx+1} in JSON file {input_file} is not a dict: {entry}")
    elif input_file.endswith(".hjson"):
        with open(input_file, 'r') as f:
            try:
                data = hjson.load(f)
            except json.JSONDecodeError as e:
                raise Exception(f"Error: Could not decode HJSON file {input_file}: {e}")
            if not isinstance(data, list):
                raise Exception(f"Error: HJSON file {input_file} does not contain an array")
            for idx, entry in enumerate(data):
                if not isinstance(entry, dict):
                    raise Exception(f"Error: Entry {idx+1} in HJSON file {input_file} is not a dict: {entry}")
    elif input_file.endswith(".yaml"):
        with open(input_file, 'r') as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise Exception(f"Error: Could not decode YAML file {input_file}: {e}")
            if not isinstance(data, list):
                raise Exception(f"Error: JSON file {input_file} does not contain an array")
            for idx, entry in enumerate(data):
                if not isinstance(entry, dict):
                    raise Exception(f"Error: Entry {idx+1} in ZAML file {input_file} is not a dict: {entry}")
    else:
        raise Exception(f"Error: Unknown file extension for input file {input_file}")
    return data

def read_input_file(input_file):
    """
    Read the input file into memory. Depending on the file extension, the input file is either a jsonl file
    with one json dict per line, a json/hjson file which contains the json representation of an array of dicts, or
    a YAML file containing an array of dicts. Each of the dicts has the following fields:
    - qid: the query id, a unique identifier for the query, a string
    - facts: the fact to query: this can be a string or a list of strings. Currently, list of strings are
         concatenated with newlines
    - query: the query to run: this must be a string. The string may contain arbitrary whitespace, but
         newlines are must be escaped with a backslash
    - checks: a list of checks that can be run on the response, where each check is a dictionary with
            the following fields:
            - query: the query to use for analyzing the response
            - function: the function to use for analyzing the response to the checking query. The function should
                return a score between 0 and 1
            - OTHERFIELDS: all other fields are passed as arguments to the function
    We first read in the whole file, depending on file format, then check all the entries we got for the
    required fields and their types.
    """
    # check the file extension and read the file accordingly

    # Now check the fields and their types:
    nentry = 0
    data = read_file(input_file)
    for entry in data:
        nentry += 1
        # check the fields
        if 'qid' not in entry:
            raise ValueError(f"Error: Missing 'qid' field in entry: {nentry}")
        if 'facts' not in entry:
            logger.debug(f"Missing 'facts' field in entry: {nentry}")
        facts = entry.get('facts')
        if 'query' not in entry:
            raise ValueError(f"Error: Missing 'query' field in entry: {nentry}")
        if 'checks' not in entry:
            logger.warning(f"Missing 'checks' field in entry: {nentry}")
        # check the type of the fields
        if facts is not None and not isinstance(facts, (str, list)):
            raise ValueError(f"Error: 'facts' field must be a string or a list of strings in entry: {nentry}")
        if not isinstance(entry['query'], str):
            raise ValueError(f"Error: 'query' field must be a string in entry: {nentry}")
        if "checks" in entry:
            if not isinstance(entry['checks'], list):
                raise ValueError(f"Error: 'checks' field must be a list in entry: {nentry}")
            for check in entry['checks']:
                if not isinstance(check, dict):
                    raise ValueError(f"Error: Check in entry {nentry} is not a dict")
                if not 'query' in check:
                    logger.debug(f"Missing 'query' field in check in entry: {nentry}")
                elif not isinstance(check['query'], str):
                    raise ValueError(f"Error: 'query' field in check must be a string in entry: {nentry}")
                if not 'func' in check:
                    # raise ValueError(f"Error: Missing 'func' field in check in entry: {nentry}")
                    logger.warning(f"Missing 'func' field in check in entry: {nentry}")
                elif not isinstance(check['func'], (str, dict)):
                    raise ValueError(f"Error: 'func' field in check must be a string or dictionary in entry: {nentry}")
                elif isinstance(check['func'], dict):
                    if not 'name' in check['function']:
                        raise ValueError(f"Error: Missing 'name' field in func in entry: {nentry}")
                    if not isinstance(check['func']['name'], str):
                        raise ValueError(f"Error: 'name' field in func must be a string in entry: {nentry}")
    return data


def read_prompt_file(prompt_file):
    """
    Read the prompt file into memory: depending on the extension this is either a jason line file (".jsonl") with
    a dict in each line, a json file containing an array of dicts or a yaml file containing an array of dicts. each line is a prompt to use for the queries. The prompt file must contain
    We first read the complete file into an array of dicts, then check the format of all the entries.
    Each dictionary should have the following fields:
    - system: the system prompt to use for the queries, a string or null/missing to not use a system prompt
    - user: the user prompt to use for the queries, a string or null/missing to not use a user prompt
    - assistant: the assistant prompt to use for the queries, a string or null/missing to not use an assistant prompt
    - pid: the prompt id, a unique identifier for the prompt, a string
    At least one of the system, user or assistant fields must be non-null.
    """
    data = read_file(prompt_file)

    seen_ids = set()
    for idx, entry in enumerate(data):
        # check the fields
        if not 'system' in entry and not 'user' in entry and not 'assistant' in entry:
            raise ValueError(f"Error: Missing 'system', 'user' or 'assistant' field in line: {entry}")
        # if all of the system, user and assistant fields are only whitespace, show an error message
        if 'system' in entry and not entry['system'].strip() and 'user' in entry and not entry['user'].strip() and 'assistant' in entry and not entry['assistant'].strip():
            raise ValueError(f"Error: All of 'system', 'user' and 'assistant' fields are only whitespace in line: {entry}")
        # set all missing fields of system, user and assistant to the empty string, then check that all fields
        # are strings
        if not 'system' in entry:
            entry['system'] = ""
        if not 'user' in entry:
            entry['user'] = ""
        if not 'assistant' in entry:
            entry['assistant'] = ""
        if not isinstance(entry['system'], str):
            raise ValueError(f"Error: 'system' field must be a string in line: {entry}")
        if not isinstance(entry['user'], str):
            raise ValueError(f"Error: 'user' field must be a string in line: {entry}")
        if not isinstance(entry['assistant'], str):
            raise ValueError(f"Error: 'assistant' field must be a string in line: {entry}")
        if not 'pid' in entry:
            raise ValueError(f"Error: Missing 'pid' field in line: {entry}")
        if not isinstance(entry['pid'], str):
            raise ValueError(f"Error: 'pid' field must be a string in line: {entry}")
        pid = entry['pid']
        if pid in seen_ids:
            raise ValueError(f"Error: Duplicate 'pid' field in line: {entry}")
    return data

