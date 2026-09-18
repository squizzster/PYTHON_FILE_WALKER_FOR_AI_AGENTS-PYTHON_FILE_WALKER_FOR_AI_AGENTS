#!/usr/bin/env python3
"""Relocatable executable shim for the installed or adjacent source package."""
import os
import sys


PACKAGE_NAME = "python_file_walker_for_ai_agents"


def _prepare_import_path():
    shim_directory = os.path.dirname(os.path.realpath(__file__))
    source_directory = os.path.join(shim_directory, "src")
    package_directory = os.path.join(source_directory, PACKAGE_NAME)
    if os.path.isdir(package_directory):
        sys.path.insert(0, source_directory)
        return

    # A copied shim has the same filename as the package. Remove its directory
    # from import lookup so it cannot shadow an installed package and recurse.
    sys.path[:] = [entry for entry in sys.path
                   if os.path.realpath(entry or os.getcwd()) != shim_directory]


def main():
    _prepare_import_path()
    try:
        from python_file_walker_for_ai_agents.directory_tree import cli
    except ImportError as exc:
        if getattr(exc, "name", None) != PACKAGE_NAME:
            raise
        sys.stderr.write("python_file_walker_for_ai_agents package is not installed\n")
        return 2
    return cli()


if __name__ == "__main__":
    sys.exit(main())
