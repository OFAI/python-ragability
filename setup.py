#!/usr/bin/env python
# encoding: utf-8
"""Packaging script for the ragability library."""
import sys
import os
import re
from setuptools import setup, find_packages

if sys.version_info < (3, 7):
    sys.exit("ERROR: ragability requires Python 3.9+")

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "README.md")) as f:
    readme = f.read()


def versionfromfile(*filepath):
    infile = os.path.join(here, *filepath)
    with open(infile) as fp:
        version_match = re.search(
            r"^__version__\s*=\s*['\"]([^'\"]*)['\"]", fp.read(), re.M
        )
        if version_match:
            return version_match.group(1)
        raise RuntimeError("Unable to find version string in {}.".format(infile))


version = versionfromfile("ragability/version.py")


setup(
    name="ragability",
    version=version,
    author="Johann Petrak",
    author_email="johann.petrak@gmail.com",
    # url="",
    description="Package for analyzing how LLMs behave in a RAG context",
    long_description=readme,
    long_description_content_type="text/markdown",
    setup_requires=[
    ],
    install_requires=[
    ],
    # extras_require=get_install_extras_require(),
    python_requires=">=3.7",
    tests_require=["pytest", "pytest-cov"],
    platforms="any",
    packages=find_packages(),
    # test_suite="tests",
    entry_points={"console_scripts": [
       "ragability_info=ragability.ragability_info:main",
       "ragability_query=ragability.ragability_query:main",
       "ragability_check=ragability.ragability_check:main",
       "ragability_cc_wc1=ragability.ragability_cc_wc1:main",
       "ragability_eval=ragability.ragability_eval:main",
       "ragability_hjson_cat=ragability.ragability_hjson_cat:main",
       "ragability_hjson_info=ragability.ragability_hjson_info:main",
       "ragability_test_llms=ragability.ragability_test_llms:main",
    ]},
    classifiers=[
        # "Development Status :: 6 - Mature",
        # "Development Status :: 5 - Production/Stable",
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development :: Libraries",
    ],
    project_urls={
       # "Documentation": "",
       #  "Source": "",
    },
)
