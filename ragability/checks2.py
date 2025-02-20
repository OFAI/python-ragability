"""
This module defines the checking functions that are implemented for testing the answers we got from LLMs.
The module defines the functions, and registers them in the CHECKS dictionary which contains, for each function
name, the function definition, the kind of check (e.g. binary, multiclass, score), the default target,
and the number of arguments required in addition to the answer text itself.
"""
import re

CHECKS = {}


def register_check(name: str, kind: str, nargs: int, target: str = "", description: str = ""):
    """
    Register a check function in the CHECKS dictionary
    :param name: the name of the check function
    :param kind: the kind of check: binary, multiclass, score
    :param nargs: the number of positional arguments required in addition to the answer text itself
        these positional arguments come from the list valued "args" field.
        keyward parameters are always optional and can be set via the dict valued "kwargs" field.
    :param description: a description of the check function
    """
    def decorator(func):
        CHECKS[name] = {
            "func": func,
            "kind": kind,
            "nargs": nargs,
            "target": target,   # the evaluation target: this is the value that the evaluator should consider correct for this check
            "description": description,
        }
        return func
    return decorator


@register_check("is_eq", "binary", 1,
                target="1",
                description="Check if the answer is exactly the target")
def is_eq(answer, target):
    """
    Check if the answer is exactly the target
    :param answer: the answer text
    :param target: the target text
    :return: 1 if the answer is exactly the target, 0 otherwise
    """
    return "1" if answer == target else "0"


@register_check("is_textual_eq", "binary", 1,
                target="1",
                description="Check if the answer is eq to the target, not considering case and whitespace")
def is_textual_eq(answer, target):
    """
    Check if the answer is equal to the target, ignoring case and whitespace
    :param answer: the answer text
    :param target: the target text
    :return: 1 if the answer is equal to the target, ignoring case and whitespace, 0 otherwise
    """
    return "1" if answer.strip().lower() == target.strip().lower() else "0"


@register_check("contains", "binary", 1,
                target="1",
                description="Check if the answer contains the target")
def contains(answer, target):
    """
    Check if the answer contains the target
    :param answer: the answer text
    :param target: the target text
    :return: 1 if the answer contains the target, 0 otherwise
    """
    return "1" if target in answer else "0"


@register_check("affirmative", "binary", 0,
                target="1",
                description="Check if the answer is affirmative (yes, true, positive)")
def affirmative(answer):
    """
    Check if the answer is affirmative (yes, true, positive)
    :param answer: the answer text
    :return: 1 if the answer is affirmative, 0 otherwise
    """
    if re.match(r'^[\.\s\']{0,10}(yes|true|positive)[\.\s\']{0,10}$', answer.lower()):
    	return "1" 
    else: 
    	return "0"


@register_check("negative", "binary", 0,
                target="1",
                description="Check if the answer is negative (no, false, negative)")
def negative(answer):
    """
    Check if the answer is negative (no, false, negative)
    :param answer: the answer text
    :return: 1 if the answer is negative, 0 otherwise
    """
    if re.match(r'^[\.\s\']{0,10}(no|false|negative)[\.\s\']{0,10}$', answer.lower()):
    	return "1" 
    else: 
    	return "0"


@register_check("unknown", "binary", 0,
                target="1",
                description="Check if the answer equals 'unknown'")
def unknown(answer):
    """
    Check if the answer textually equals one of: unknown, uncertain, i do not know, i don't know
    :param answer: the answer text
    :return: 1 if the answer is unknown, 0 otherwise
    """
    return "1" if answer.strip().lower() in ["unknown", "uncertain", "i do not know", "i don't know"] else "0"


@register_check("is_eq_oneof", "binary", 1,
                description="check if the answer is exactly one of the targets")
def is_eq_oneof(answer, targets):
    """
    Check if the answer is exactly one of the targets
    :param answer: the answer text
    :param targets: a list of target texts
    :return: 1 if the answer is exactly one of the targets, 0 otherwise
    """
    return "1" if answer in targets else "0"


@register_check("is_textual_eq_oneof", "binary", 1,
                description="check if the answer is equal to one of the targets, ignoring case and whitespace")
def is_textual_eq_oneof(answer, targets):
    """
    Check if the answer is equal to one of the targets, ignoring case and whitespace
    :param answer: the answer text
    :param targets: a list of target texts
    :return: 1 if the answer is equal to one of the targets, 0 otherwise
    """
    return "1" if answer.strip().lower() in [t.strip().lower() for t in targets] else "0"


@register_check("contains_oneof", "binary", 1,
                description="check if the answer contains one of the targets")
def contains_oneof(answer, targets):
    """
    Check if the answer contains one of the targets
    :param answer: the answer text
    :param targets: a list of target texts
    :return: 1 if the answer contains one of the targets, 0 otherwise
    """
    return "1" if any(t in answer for t in targets) else "0"


@register_check("contains_all", "binary", 1,
                description="check if the answer contains all of the targets")
def contains_all(answer, targets):
    """
    Check if the answer contains all of the targets
    :param answer: the answer text
    :param targets: a list of target texts
    :return: 1 if the answer contains all of the targets, 0 otherwise
    """
    return "1" if all(t in answer for t in targets) else "0"

@register_check("extract_score", "score", 0,
                description="Extract a score from the answer. Expext exactly one number in the answer,if more raise exception")
def extract_score(answer):
    """
    Extract a score from the answer. Expect exactly one number in the answer, if more raise exception
    :param answer: the answer text
    :return: the score
    """
    numbers = [float(s) for s in re.findall(r'-?\d+\.?\d*', answer)]
    if len(numbers) != 1:
        raise Exception(f"Error: Expected exactly one number in the answer, got {len(numbers)}")
    return numbers[0]
