#!/usr/bin/env python
"""
Command to print system information and package versions.
"""
import importlib
import os, sys
import argparse
from importlib.metadata import version
from ragability.version import __version__ as raga_version

PACKAGES = """
llms_wrapper
pandas
jupyter
notebook
IPython
ipykernel 
jupyterlab
ollama
scikit-learn
"""

def get_args():
    aparser = argparse.ArgumentParser(description="Show various system info")
    aparser.add_argument("-d", "--debug", action="store_true", help="Enable debug output")

    args = aparser.parse_args()
    return args

def main():
    args = get_args()
    print(f"Package ragability: {raga_version}")
    print(f"Python version: {sys.version}")
    if args.debug:
        print(f"Python executable: {sys.executable}")
        print(f"Python path: {sys.path}")
        print(f"Python prefix: {sys.prefix}")
        print(f"Python implementation: {sys.implementation}")
        print(f"Operating system: {os.uname()}")
    print(f"Python platform: {sys.platform}")
    print("Package versions:")
    for p in sorted(PACKAGES.split()):
        try:
            v = version(p)
            print(f"{p}: {v}")
        except Exception as ex:
            print(f"!!! {p}: NOT INSTALLED/CANNOT IMPORT !!! {ex}")


if __name__ == "__main__":
    main()
