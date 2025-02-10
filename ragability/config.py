"""
Module for reading/writing config files and merging in information from the arguments. The config file can be in
one of the following formats: json, hjson, yaml, toml. This module only cares about the top-level fields
"llms" and "providers": all other fields are ignored.

"""
from ragability.logging import logger,  set_logging_level, add_logging_file
import warnings



## Suppress the annoying litellm warning
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from litellm import LITELLM_CHAT_PROVIDERS

# TODO: any additional ragability specific updates or checks related to the config file

