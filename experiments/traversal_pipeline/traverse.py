#!/usr/bin/env python3
"""Time one mother-shim traversal per root, with five-second heartbeats."""

from __future__ import print_function

import json
import os
import subprocess
import sys
import threading
import time


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
MOTHER = os.path.join(
    PROJECT_ROOT, "list_files_in_a_directory_tree_to_json.py")
DEFAULT_DIRECTORIES = (
    "/external_data/data/work_flow_dna/business_genome_classification_system/"
    "EDGAR_SEC_FILING_DOWNLOADER/data/corpus/sec_submissions",
    "/external_data/data/work_flow_dna/business_genome_classification_system/"
    "EDGAR_SEC_FILING_DOWNLOADER/data/corpus/entity_artifacts",
)
HEARTBEAT_SECONDS = 5.0
READ_SIZE = 65536


def compact_json(document):
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"))


def stderr_json(document):
    sys.stderr.write(compact_json(document) + "\n")
    sys.stderr.flush()


class Heartbeat(object):
    def __init__(self):
        self.started = time.monotonic()
        self.state = {
            "root_index": 0,
            "root_total": 0,
            "phase": "starting",
            "root": None,
            "json_bytes_received": 0,
        }
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True

    def start(self):
        self.thread.start()

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def emit(self):
        with self.lock:
            document = dict(self.state)
        document["event"] = "heartbeat"
        document["elapsed_seconds"] = round(
            time.monotonic() - self.started, 3)
        stderr_json(document)

    def _run(self):
        while not self.stopped.wait(HEARTBEAT_SECONDS):
            self.emit()

    def stop(self):
        self.stopped.set()
        self.thread.join()


def count_result(document):
    directories = 0
    links = 0
    files = 0
    stack = [document["tree"]]
    while stack:
        node = stack.pop()
        if node.get("type") == "link":
            links += 1
            continue
        directories += 1
        file_object = node["files"]
        if file_object["mode"] == "count":
            files += file_object["count"]
        else:
            files += len(file_object["entries"])
        stack.extend(node.get("children", ()))
    return directories, links, files


def traverse(root, root_index, root_total, heartbeat):
    heartbeat.update(
        root_index=root_index,
        root_total=root_total,
        phase="mother-traversal",
        root=root,
        json_bytes_received=0,
    )
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, "-B", MOTHER, root],
        stdout=subprocess.PIPE,
    )
    chunks = []
    output_bytes = 0
    while True:
        chunk = process.stdout.read(READ_SIZE)
        if not chunk:
            break
        chunks.append(chunk)
        output_bytes += len(chunk)
        heartbeat.update(json_bytes_received=output_bytes)
    process.stdout.close()
    status = process.wait()
    mother_seconds = time.monotonic() - started
    if status != 0:
        raise RuntimeError("mother exited with status %d for %s" %
                           (status, root))

    heartbeat.update(phase="parse-result")
    parse_started = time.monotonic()
    output = b"".join(chunks)
    del chunks
    document = json.loads(output.decode("ascii"))
    del output
    directories, links, files = count_result(document)
    complete = bool(document.get("complete"))
    errors = int(document.get("errors", 0))
    del document
    parse_seconds = time.monotonic() - parse_started
    result = {
        "root": root,
        "complete": complete and errors == 0,
        "directories": directories,
        "directory_links": links,
        "files": files,
        "json_bytes": output_bytes,
        "mother_seconds": round(mother_seconds, 6),
        "parse_seconds": round(parse_seconds, 6),
        "total_seconds": round(time.monotonic() - started, 6),
        "errors": errors,
    }
    heartbeat.update(phase="root-complete")
    stderr_json(dict({"event": "root-complete"}, **result))
    return result


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    roots = [os.path.abspath(item) for item in (
        arguments if arguments else DEFAULT_DIRECTORIES)]
    heartbeat = Heartbeat()
    heartbeat.start()
    started = time.monotonic()
    results = []
    try:
        for index, root in enumerate(roots, 1):
            results.append(traverse(root, index, len(roots), heartbeat))
    except KeyboardInterrupt:
        stderr_json({"event": "interrupted"})
        return 130
    finally:
        heartbeat.stop()

    report = {
        "experiment": "single-process-recursive-mother",
        "does": "traverses names and entry types only; reads no file contents",
        "roots": results,
        "totals": {
            "roots": len(results),
            "directories": sum(item["directories"] for item in results),
            "directory_links": sum(
                item["directory_links"] for item in results),
            "files": sum(item["files"] for item in results),
            "json_bytes": sum(item["json_bytes"] for item in results),
            "seconds": round(time.monotonic() - started, 6),
        },
        "complete": len(results) == len(roots) and all(
            item["complete"] for item in results),
    }
    sys.stdout.write(compact_json(report) + "\n")
    sys.stdout.flush()
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
