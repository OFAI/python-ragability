# python-ragability

A library and corpus for checking/benchmarking LLMs with regard to properties relevant to their use in RAG 
systems.

### Conda

* create a conda environment, e.g. by sourcing `conda-create.sourceme`
  * e.g. with bash: `. conda-create.sourceme`
* if necessary (re-)install the requirements `pip install -r requirements.txt` (the conda creation code already does this too)
* if necessary install/update the ragability package `pip install -e .` (the conda creation code already does this too)
* NOTE: as long as the package gets developed/changed, the re-installation steps make sure that changed CLI programs
  are being made available. 

## Usage

* Activate conda environment: `conda activate ragability` 
* After installation, the following commands are available:
* `ragability_info` : show the versions of all relevant Python packages installed
* `ragability_cc_wc1` : convert the wiki-contradict based corpus to ragability format
* `ragability_query` : given an input file with facts and queries, a list of candidate LLMs and a prompt template, produce and output file that contains 
  LLM answers to the queries 
* `ragability_check` : given a query result file and a judge LLM, evaluate the answers received against the pre-defined answers and create an output file that contains the evaluation scores and meta-information for each example
* `ragability_eval` : given the data created with `ragability_check`, calculate detailled performance statistics
* `ragability_hjson_info` : provides an overview of the major information present in a hjson, json, or jsonl file
* `ragability_hjson_cat` : concatenate several hjson, json or jsonl files into one hjson or json file
* `llms_wrapper_test`: for the configured/specified LLMs, test if they are working and returning an answer. This is useful to check a config file and
   test if all the API keys are correctly set and working
* All commands take the `--help` option to get usage information

LLMs currently supported: support is based on the [LiteLLM](https://github.com/BerriAI/litellm) backend via the [llms_wrapper](https://github.com/OFAI/python-llms-wrapper/) package. The supported LLMs are listed [here](https://docs.litellm.ai/docs/providers/)

### Example usage

with the converted wiki-contradict dataset:

* (optional conversion step, the current converted dataset is already part of the repo): convert the dataset tsv file to ragability format
  * `ragability_cc_wc1 --input corpus/wikicontradict1/Dataset_v0.2_short.tsv --output corpus/wikicontradict1/v0d2.hjson`
* create or copy and modify one of the conf*.hjson files to contain the LLMs and LLM configs wanted for the experiment
* Run the base LLMs on the corpus. The following will create also a log file:
  * `ragability_query -i corpus/wikicontradict1/v0d2.hjson -o experiments-wc1/v0d2.out1.hjson --config experiments-wc1/conf-all.hjson --promptfile experiments-wc1/prompt.hjson  --logfile experiments-wc1/v0d2.log1.txt  --verbose`
* Run the checker LLM on the output of the previous step
  * `ragability_check -i experiments-wc1/v0d2.out1.hjson -o experiments-wc1/v0d2.out2.hjson --config experiments-wc1/conf-ollama.hjson --promptfile experiments-wc1/prompt.hjson --logfile experiments-wc1/v0d2.log2.txt --verbose`
* run the evaluation program:
  * `ragability_eval -i experiments-wc1/v0d2_small.out2.hjson -o experiments-wc1/v0d2_small.eval.tsv --verbose`
  * the generated tsv file can be loaded into a pandas dataframe or some spreadsheet app

### Files/File formats

NOTE: tools to convert between jsonl, json, yaml:

* https://github.com/spatialcurrent/go-simple-serializer
* `hjson` command (already available from the package installation can be used to convert between json and hjson

Query file:

* Either a json or hjson file that contains an array of dicts, or a jsonl file that contains one json dict per line or a yaml file that 
  contains an array of dicts
* Each dict must contain the following fields (fields marked as '(output)' are written to the output file):
  * `qid`: the id of the query should be a short reminder, e.g. `kwoks-are-vertebrates01`
  * `facts`: a string or an array of strings giving the knowledge snippets we want to query, these simulate the RAG document snippets included in a RAG query
  * `query`: the query to ask about the facts
  * `pids` : the prompt ids from the configured prompts to use, if not given all configured prompts are used
  * `tags`: a comma-separated list of tags which identify the kind, purpose, etc. of the corresponding instance. The presence or absence of a tag
        can be used in the eval program for breakign down the LLM-performances. 
  * `response` (output) : the response as received from the base LLM if there was no error
  * `error` (output) : the error if there was an error 
  * `llm` (output) : the llm alias / name used 
  * `checks`: (optional, but required if checking and evaluation should get performed later) a list of checks where each check is a dict which contains:
    * `query`: if present, a query to ask the checker LLM about the response from the base-LLM. If missing, the checking process will directly analyse
       the base-LLM response (e.g. when the base LLM query was a yes/no question)
    * `pid`: the prompt id of the configured prompt to use for the checking LLM. If this is missing a default prompt is used.
    * `func`: the name of a checking function, which will be called with the response of the checking or base LLM and the additional parameters specified with "args". Each function definition internally knows about the kind of evaluation (binary, multiclass, score). See the `checks.py` module
    * `args` : optional additional positional parameters for the checking function, e.g. some value or values to compare against. The meaning of the parameters depends on the concrete checking function. Some checking functions do not need any `args` in which case this field can be omitted. 
    * `check_for` : optional value to insert into the checker query and all prompt strings using variable name "${check_for}" 
    * `kwargs` : optional additional keyword-arguments to provide to the checker function
    * `response` (output) : the response as received from the checking LLM (if no error)
    * `error` (output) : the error if an error during checking occurred
    * `result` (output) : the result of the checking function, either a response label that will get compared to a target label for evaluation, or a score
          
Prompt file:

* Either a json file that contains an array of dicts, or a jsonl file that contains one json dict per line or a yaml file that
  contains an array of dicts
* Each dict must contain the following fields:
  * `pid`:  the id of the prompt, should be a short reminder of what it does
  * at least one of `system`, `assistant`, `user`: a string to use for creating the actual final prompt for the LLM. The string can contain
    the placeholders `${query}` and `${facts}` in order to insert the current query and facts (if facts is an array of strings, these will get 
    concatenated with newlines)
  * `fact`: how to format a single fact if there are several. This supports the variables `${fact}` and `${n}` (1-based fact index)
* The placeholder `${check_for}` can be used for prompts to be used by the checking LLM to insert some value to check for in the response to check
* The placeholder `${answer}` can be used for prompts to be used by the checking LLM to insert the response from the base-LLM to check

Query Output file / Checker Input file:

* Either a json, hjson or a jsonl file
* each dictionary contains the same fields as the input, plus the fields added (marked with '(output)' above)
* NOTE: if there were transient errors during processing, the output file can be re-used as an input file and by default, 
  only those entries which do not already have a response will get re-processed
  
Checker Output file / Eval Input file:

* Either a json, hjson or a jsonl file 
* each dictionary contains the same fields as the input, plus the fields added (marked with '(output)' above)
* NOTE: if there were transient errors during processing, the output file can be re-used as an input file and by default, 
  only those entries which do not already have a response will get re-processed

Config file:

* IMPORTANT: the config file is used by the backend library `llms_wrapper` to configure LLMs and providers, see the documentation
  of that library for the most recent description of what is supported in the config file for LLMs and providers: 
  https://github.com/OFAI/python-llms-wrapper/wiki
* a json or hjson or yaml file containing a dictionary with the following keys
* `llms`: a list of strings or dictionaries describing the LLMs to use. A dictionary can contain the following keys:
  * `llm`: the name/id of the LLM. This should be in the form provider:llmmodel where "provider" must be a known provider or something defined in the 
     `providers` part of the config. The "llmmodel" is the provider-specific way to specify a model.
  * `api_key`: the API key to use for the model
  * `api_key_env`: the name of an environment variable containing the API key
  * `api_url`: the URL to use. In this URL the placeholders `${model}`, `${user}`, `${password}` and `${api_key}` can be used to get replaced 
     with the actual values
  * `user`: the user name to use for basic authentication 
  * `password`: the password to use for basic authentication
  * Any specification of the above fields that is present in the corresponding provider config is overridden with the value provided in the llm config
  * `cost_per_prompt_token`: configure or override the cost per prompt token
  * `cost_per_output_token`: configure or override the cost per output token
  * `max_input_tokens`: configure or override the maximum number of input/prompt tokens
  * `max_output_tokens`: configure or override the maximum number of output tokens
* `providers`: a dict with provider names as the key and a dict of provider settings as the values where each dict can contain the followign keys:
  * `api_key`: the API key to use for the model
  * `api_key_env`: the name of an environment variable containing the API key
  * `api_url`: the URL to use. In this URL the placeholders `${model}`, `${user}`, `${password}` and `${api_key}` can be used to get replaced 
     with the actual values
  * `user`: the user name to use for basic authentication 
  * `password`: the password to use for basic authentication
* `prompts` : a list of prompts in the same way as in a separate prompts file


