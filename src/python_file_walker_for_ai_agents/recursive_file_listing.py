#!/usr/bin/env python3
"""Recursively list directories and their files as one streamed JSON tree."""

import errno
import json
import locale
import os
import sys

from .directory_tree import DirectoryTree, fatal
from .file_entries import FileObjectWriter
from .file_listing import (
    HELP_DOCUMENT as FILE_HELP_DOCUMENT,
    UsageError,
    diagnostic,
    parse_args,
)
from .filesystem import MINIMUM_PYTHON


HELP_DOCUMENT = {
    "usage": "list_files_in_a_directory_tree_to_json.py [OPTIONS] DIRECTORY",
    "does": "Emits one recursive JSON tree in one process and one scan per directory; includes hidden directories and files; emits directory symlinks as leaves; stays on the root filesystem; never reads file contents.",
    "envelope": {"tree": "directory node", "complete": "boolean", "errors": "integer"},
    "nodes": {
        "directory": {"type": "directory", "name": "string", "files": "files object", "children": "node[]"},
        "link": {"type": "link", "name": "string", "target": "string"},
    },
    "file_returns": FILE_HELP_DOCUMENT["returns"],
    "options": FILE_HELP_DOCUMENT["options"],
    "aliases": FILE_HELP_DOCUMENT["aliases"],
    "help": FILE_HELP_DOCUMENT["help"],
    "option_terminator": "--",
}


def help_json(error=None):
    document = (HELP_DOCUMENT if error is None else
                {"error": error, "help": HELP_DOCUMENT})
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"))


def main(argv=None):
    try:
        if (not sys.platform.startswith("linux") or
                sys.version_info < MINIMUM_PYTHON or not hasattr(os, "scandir")):
            raise UsageError("Linux and Python 3.5 or newer are required")
        raw_args = sys.argv[1:] if argv is None else argv
        if not raw_args:
            diagnostic(help_json())
            return 2
        args = parse_args(raw_args)
        if args is None:
            diagnostic(help_json())
            return 0
        directory, number, all_entries, base64_names, metadata = args
        try:
            locale.setlocale(locale.LC_COLLATE, "")
        except locale.Error:
            locale.setlocale(locale.LC_COLLATE, "C")

        def file_writer_factory(write):
            return FileObjectWriter(
                write, number, all_entries, base64_names, metadata)

        output = sys.stdout.buffer
        scanner = DirectoryTree(
            output, sys.stderr, file_writer_factory=file_writer_factory)
        status = scanner.run(directory)
        output.flush()
        return status
    except UsageError as exc:
        diagnostic(help_json(str(exc)))
        return 2


def cli():
    try:
        return main()
    except KeyboardInterrupt:
        fatal("file-tree: interrupted; discard incomplete stdout", 130)
    except OSError as exc:
        if exc.errno == errno.EPIPE:
            os._exit(141)
        fatal("file-tree: fatal I/O failure: %s; discard stdout" %
              ascii(str(exc)), 1)
    except MemoryError:
        fatal("file-tree: out of memory; discard incomplete stdout", 1)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(cli())
