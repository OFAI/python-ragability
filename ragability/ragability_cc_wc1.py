#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module for the CLI to convert the wiki-contradiction corpus to ragability input format
"""

import json
import argparse
import pandas as pd
import hjson
from logging import DEBUG
from ragability.logging import logger, set_logging_level
from ragability.utils import pp_config

PROMPTS = [
    dict(
        pid="q_no_context",
        user="${query}",
    ),
    dict(
        pid="q_one_context",
        system="Read the following facts between '====START' and '====END' and then answer the question which comes after these facts, only providing the facts and not mentioning that you extracted them from the text: \n====START\n${facts}\n====END",
        fact="Fact ${n}: ${fact}\n",
        user="${query}",
    ),
    dict(
        pid="q_two_contexts",
        system="Read the following facts between '====START' and '====END' and then answer the question which comes after these facts, only providing the facts and not mentioning that you extracted them from the text: \n====START\n${facts}\n====END",
        fact="Fact ${n}: ${fact}\n",
        user="${query}",
    ),
    dict(
        pid="ci_one_context",
        user="Read the following facts between '====START' and '====END' and decide if there is any contradiction present. Answer 'yes' if there is a contraction, answer 'no' if there is no contracdition, do not add anything else to your answer: \n====START\n${facts}\n====END",
        fact="Fact ${n}: ${fact}\n",
    ),
    dict(
        pid="ci_two_contexts",
        user="Read the following facts between '====START' and '====END' and decide if there is any contradiction present. Answer 'yes' if there is a contraction, answer 'no' if there is no contracdition, do not add anything else to your answer: \n====START\n${facts}\n====END",
        fact="Fact ${n}: ${fact}\n",
    ),
    dict(
        pid="check_response_answerable",
        system="You are to analyse the response after 'RESPONSE:' and answer 'yes' if the response refuses to give a concrete answer and instead points out that an answer is not possible. You are to answer no if the response includes, even just as a possibility, a concrete answer. Answer only with 'yes' or 'no', do not include additional explanations or information.",
        user="RESPONSE: ${answer}",
    ),
    dict(
        pid="check_correct_answer",
        system="You are to analyse the response after 'RESPONSE:' and compare it to the target after 'TARGET:'. Answer 'yes' if the response and target are semantically equivalent and the response does not add or omit any information in the target, otherwise answer 'no'. Answer only with 'yes' or 'no', do not include additional explanations or information.",
        user="RESPONSE: ${answer}, TARGET: ${check_for}",
    ),

]

VAR = "-var01"


def row2raga_nc(row):
    out = dict(
        qid=row["contradiction_ID"] + "-" + "nc" + VAR,
        tags="kind_no_context, kind_no_context_q, not_answerable",
        query=row["query_text"],
        pids=["q_no_context"],
        checks=[
            dict(
                cid="no_ctx_not_answerable",
                query="",
                func="affirmative",
                metrics=["correct_answer_all", "refusal_not_answerable"],
                pid="check_response_answerable",
            ),
        ],
    )
    return out


def row2raga_ctx1(row):
    out = dict(
        qid=row["contradiction_ID"] + "-" + "ctx1" + VAR,
        tags="kind_1context, kind_1context_q, kind_context1, kind_context1_q, answerable",
        facts=row["context_1"],
        query=row["query_text"],
        pids=["q_one_context"],
        checks=[
            dict(
                cid="answer_correct",
                query="",
                func="affirmative",
                metrics=["correct_answer_all", "correct_answer_answerable"],
                pid="check_correct_answer",
                check_for=row["answer_context1"]
            ),
        ],
    )
    return out


def row2raga_ctx2(row):
    out = dict(
        qid=row["contradiction_ID"] + "-" + "ctx2" + VAR,
        tags="kind_1context, kind_1context_q, kind_context2, kind_context2_q, answerable",
        facts=row["context_2"],
        query=row["query_text"],
        pids=["q_one_context"],
        checks=[
            dict(
                cid="answer_correct",
                query="",
                func="affirmative",
                metrics=["correct_answer_all", "correct_answer_answerable"],
                pid="check_correct_answer",
                check_for=row["answer_context2"]
            ),
        ],
    )
    return out


def row2raga_ctx12q(row):
    out = dict(
        qid=row["contradiction_ID"] + "-" + "ctx12q" + VAR,
        tags="kind_2contexts, kind_2contexts_q, kind_context1+2, kind_context1+2_q, not_answerable",
        facts=[row["context_1"], row["context_2"]],
        query=row["query_text"],
        pids=["q_two_contexts"],
        checks=[
            dict(
                cid="2ctx_not_answerable",
                query="",
                func="affirmative",
                metrics=["correct_answer_all", "refusal_not_answerable"],
                pid="check_response_answerable",
            ),
        ],
    )
    return out

def row2raga_ctx21q(row):
    out = dict(
        qid=row["contradiction_ID"] + "-" + "ctx21q" + VAR,
        tags="kind_2contexts, kind_2contexts_q, kind_context2+1, kind_context2+1_q, not_answerable",
        facts=[row["context_1"], row["context_2"]],
        query=row["query_text"],
        pids=["q_two_contexts"],
        checks=[
            dict(
                cid="2ctx_not_answerable",
                query="",
                func="affirmative",
                metrics=["correct_answer_all", "refusal_not_answerable"],
                pid="check_response_answerable",
            ),
        ],
    )
    return out


def row2raga_ctx1ic(row):
    out = dict(
        qid=row["contradiction_ID"] + "-" + "ctx1ic" + VAR,
        tags="kind_1context, kind_1context_ic, kind_context1, kind_context1_ic, answerable",
        facts=row["context_1"],
        query="",
        pids=["ci_one_context"],
        checks=[
            dict(
                cid="answer_correct",
                func="negative",
                metrics=["correct_answer_all", "contradiction_identification"],
            ),
        ],
    )
    return out


def row2raga_ctx2ic(row):
    out = dict(
        qid=row["contradiction_ID"] + "-" + "ctx2ic" + VAR,
        tags="kind_1context, kind_1context_ic, kind_context2, kind_context2_ic, answerable",
        facts=row["context_2"],
        query="",
        pids=["ci_two_contexts"],
        checks=[
            dict(
                cid="answer_correct",
                func="negative",
                metrics=["correct_answer_all", "contradiction_identification"],
            ),
        ],
    )
    return out


def row2raga_ctx12ic(row):
    out = dict(
        qid=row["contradiction_ID"] + "-" + "ctx12ic" + VAR,
        tags="kind_2contexts, kind_2contexts_ic, kind_context1+2, kind_context1+2_ic, answerable",
        facts=[row["context_1"],row["context_2"]],
        query="",
        pids=["ci_two_contexts"],
        checks=[
            dict(
                cid="answer_correct",
                func="affirmative",
                metrics=["correct_answer_all", "contradiction_identification"],
            ),
        ],
    )
    return out


def row2raga_ctx21ic(row):
    out = dict(
        qid=row["contradiction_ID"] + "-" + "ctx21ic" + VAR,
        tags="kind_2contexts, kind_2contexts_ic, kind_context2+1, kind_context2+1_ic, answerable",
        facts=[row["context_2"],row["context_1"]],
        query="",
        pids=["ci_two_contexts"],
        checks=[
            dict(
                cid="answer_correct",
                func="affirmative",
                metrics=["correct_answer_all", "contradiction_identification"],
            ),
        ],
    )
    return out


CONVS = [
    row2raga_nc,
    row2raga_ctx1, row2raga_ctx2,
    row2raga_ctx12q, row2raga_ctx21q,
    row2raga_ctx1ic, row2raga_ctx2ic,
    row2raga_ctx12ic, row2raga_ctx21ic]


def get_args():
    """
    Get the command line arguments
    """
    parser = argparse.ArgumentParser(description='Convert the WikiContradict-based datast to ragability input format')
    parser.add_argument('--input', '-i', type=str, help='Input TSV file', required=False)
    parser.add_argument('--output', '-o', type=str, help='Output hjson,json file', required=False)
    parser.add_argument('--maxn', '-n', type=int, help='Maximum number of input rows to process', required=False)
    parser.add_argument('--promptfile', '-p', type=str, help='Promptfile to write with the default prompts (do not write)', required=False)
    parser.add_argument("--debug", "-d", action="store_true", help="Debug mode", required=False)
    args_tmp = parser.parse_args()
    args = {}
    args.update(vars(args_tmp))
    return args


def run(config: dict):
    pfile = config.get("promptfile")
    if pfile:
        with open(pfile, "wt") as outfp:
            hjson.dump(PROMPTS, outfp)
        logger.info(f"Prompts written to {pfile}")
    if not config.get("input"):
        logger.info("No input file given, exiting")
        return
    if not config.get("output"):
        logger.error("Output file must be given if input file is specified")
        return
    df = pd.read_csv(config["input"], sep="\t", dtype="string", na_filter=False)
    logger.info(f"Read {len(df)} rows with {df.shape[1]} columns from {config['input']}")

    # write either a jsonl or json file, depending on the file extension
    if not config['output'].endswith(".json") and not config['output'].endswith(".jsonl") and not config['output'].endswith(".hjson"):
        raise Exception(f"Error: Output file must end in .json, .jsonl or .hjson, not {config['output']}")
    with open(config['output'], 'wt') as f:
        if config['output'].endswith(".json") or config['output'].endswith(".hjson"):
            f.write("[\n")

        colnames = ["index"] + list(df.columns)
        n_rows = 0
        n_inputs = 0
        for row in df.itertuples(name=None):
            n_inputs += 1
            rowdict = {cn: cv for cn, cv in zip(colnames, row)}
            for conv in CONVS:
                crow = conv(rowdict)
                # copy over the meta data fields
                for field in ["reasoning_required", "notes", "WikiContradict_ID", "contradictory_level"]:
                    if field in rowdict:
                        crow[field] = rowdict[field]
                n_rows += 1
                if config['output'].endswith(".json"):
                    f.write(json.dumps(crow, indent=2) + "\n")
                elif config['output'].endswith(".hjson"):
                    f.write(hjson.dumps(crow, indent=2) + "\n")
                else:
                    f.write(json.dumps(crow) + "\n")
            if config.get("maxn") and n_inputs >= config["maxn"]:
                logger.info(f"Processed {n_inputs} rows, stopping")
                break

        if config['output'].endswith(".json") or config['output'].endswith(".hjson"):
            f.write("]\n")
        logger.info(f"Written {n_rows} entries to {config['output']}")


def main():
    args = get_args()
    if args["debug"]:
        set_logging_level(DEBUG)
        ppargs = pp_config(args)
        logger.debug(f"Effective arguments: {ppargs}")
    run(args)


if __name__ == '__main__':
    main()
