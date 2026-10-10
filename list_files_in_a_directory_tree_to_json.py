#!/usr/bin/env python3
"""Relocatable shim for the recursive directory-and-file JSON walker."""

import os
import sys


PACKAGE_NAME = "python_file_walker_for_ai_agents"
MODULE_NAME = PACKAGE_NAME + ".recursive_file_listing"


def _prepare_import_path():
    shim_directory = os.path.dirname(os.path.realpath(__file__))
    source_directory = os.path.join(shim_directory, "src")
    package_directory = os.path.join(source_directory, PACKAGE_NAME)
    if os.path.isdir(package_directory):
        sys.path.insert(0, source_directory)
        return
    sys.path[:] = [entry for entry in sys.path
                   if os.path.realpath(entry or os.getcwd()) != shim_directory]


def main():
    _prepare_import_path()
    try:
        from python_file_walker_for_ai_agents.recursive_file_listing import cli
    except ImportError as exc:
        if getattr(exc, "name", None) not in (PACKAGE_NAME, MODULE_NAME):
            raise
        sys.stderr.write(MODULE_NAME + " is not installed\n")
        return 2
    return cli()


if __name__ == "__main__":
    sys.exit(main())
