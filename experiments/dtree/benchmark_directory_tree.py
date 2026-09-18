#!/usr/bin/env python3
"""Opt-in benchmark on synthetic fixtures ONLY; never benchmarks existing data.

python3 benchmark_directory_tree.py --scratch-parent /dev/shm --repeats 9

Creates/removes a unique temporary child of --scratch-parent. Writes many empty
files: don't run on delicate/production storage. Timing is warm-cache, single
process, output to /dev/null. Does not drop caches or modify system settings.
"""
import argparse
import errno
import io
import json
import locale
import os
import platform
import random
import resource
import shutil
import stat
import statistics
import subprocess
import sys
import tempfile
import time

import create_directory_tree_to_json as dt

SCRIPT = os.path.abspath(__file__)
ENGINES = ("dtree", "listdir-lstat", "os-walk")


def node(name):
    return {"type": "directory", "name": name, "children": []}


def listdir_tree(root):
    result = node(root)
    todo = [(root, result)]
    while todo:
        path, parent = todo.pop()
        children = []
        for name in os.listdir(path):
            full = os.path.join(path, name)
            mode = os.lstat(full).st_mode
            if stat.S_ISDIR(mode):
                child = node(name)
                children.append(child)
                todo.append((full, child))
            elif stat.S_ISLNK(mode) and os.path.isdir(full):
                children.append({"type": "link", "name": name, "target": os.readlink(full)})
        children.sort(key=lambda item: item["name"])
        parent["children"] = children
    return {"tree": result, "complete": True, "errors": 0}


def walk_tree(root):
    result = node(root)
    index = {root: result}
    for path, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(dirs)
        parent = index.pop(path)
        for name in dirs:
            full = os.path.join(path, name)
            if os.path.islink(full):
                child = {"type": "link", "name": name, "target": os.readlink(full)}
            else:
                child = node(name)
                index[full] = child
            parent["children"].append(child)
    return {"tree": result, "complete": True, "errors": 0}


def worker(engine, root):
    locale.setlocale(locale.LC_COLLATE, "C")
    start = time.perf_counter()
    status = 0
    if engine == "dtree":
        scanner = dt.DirectoryTree(sys.stdout.buffer, sys.stderr)
        status = scanner.run(root)
    elif engine == "noop":
        pass
    else:
        obj = listdir_tree(root) if engine == "listdir-lstat" else walk_tree(root)
        sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=True,
                                          separators=(",", ":")).encode("ascii") + b"\n")
    sys.stdout.buffer.flush()
    elapsed = time.perf_counter() - start
    usage = resource.getrusage(resource.RUSAGE_SELF)
    report = {"worker_seconds": elapsed, "max_rss_kib": usage.ru_maxrss,
              "user_seconds": usage.ru_utime, "system_seconds": usage.ru_stime}
    sys.stderr.write(json.dumps(report, sort_keys=True) + "\n")
    return status


def build_fixture(root, fixture):
    os.mkdir(root)
    directories, files = 1, 0
    if fixture == "file-heavy":
        top, sub, count = 200, 0, 500
    elif fixture == "mixed":
        top, sub, count = 100, 20, 20
    elif fixture == "directory-heavy":
        top, sub, count = 200, 50, 0
    else:
        raise ValueError("unknown fixture")
    for i in range(top):
        parent = os.path.join(root, "d-%04d" % i)
        os.mkdir(parent)
        directories += 1
        leaves = [parent]
        if sub:
            leaves = []
            for j in range(sub):
                child = os.path.join(parent, "s-%04d" % j)
                os.mkdir(child)
                directories += 1
                leaves.append(child)
        for leaf in leaves:
            for k in range(count):
                fd = os.open(os.path.join(leaf, "f-%04d" % k), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
                files += 1
    return {"directories_including_root": directories, "regular_files": files}


def run_bench(args):
    if args.repeats < 3:
        raise SystemExit("--repeats must be at least 3")
    report = {"python": sys.version, "kernel": platform.release(),
              "platform": platform.platform(), "scratch_parent": args.scratch_parent,
              "method": "one warmup per engine; randomized serial fresh-process runs; no cache drops; stdout=/dev/null",
              "repeats": args.repeats, "python_no_site": args.python_no_site, "fixtures": {}}
    interpreter = [sys.executable] + (["-S"] if args.python_no_site else [])
    base = tempfile.mkdtemp(prefix="dtree-benchmark-", dir=args.scratch_parent)
    try:
        rng = random.Random(209847)
        with open(os.devnull, "wb") as sink:
            for fixture in ("file-heavy", "mixed", "directory-heavy"):
                root = os.path.join(base, fixture)
                print("Building " + fixture + " in " + base, file=sys.stderr)
                details = build_fixture(root, fixture)
                records = {engine: [] for engine in ENGINES}
                for engine in ENGINES:
                    subprocess.check_call(interpreter + [SCRIPT, "--worker", engine, root],
                                          stdout=sink, stderr=sink)
                for unused in range(args.repeats):
                    order = list(ENGINES)
                    rng.shuffle(order)
                    for engine in order:
                        started = time.perf_counter()
                        result = subprocess.run(interpreter + [SCRIPT, "--worker", engine, root],
                                                stdout=sink, stderr=subprocess.PIPE)
                        elapsed = time.perf_counter() - started
                        if result.returncode:
                            raise RuntimeError(result.stderr.decode("utf-8", "replace"))
                        item = json.loads(result.stderr.decode("ascii"))
                        item["end_to_end_seconds"] = elapsed
                        records[engine].append(item)
                details["engines"] = {}
                for engine in ENGINES:
                    runs = records[engine]
                    details["engines"][engine] = {
                        "median_end_to_end_seconds": statistics.median(r["end_to_end_seconds"] for r in runs),
                        "min_end_to_end_seconds": min(r["end_to_end_seconds"] for r in runs),
                        "max_end_to_end_seconds": max(r["end_to_end_seconds"] for r in runs),
                        "median_worker_seconds": statistics.median(r["worker_seconds"] for r in runs),
                        "median_max_rss_kib": statistics.median(r["max_rss_kib"] for r in runs),
                        "runs": runs}
                report["fixtures"][fixture] = details
                if args.keep:
                    details["kept_path"] = root
                else:
                    shutil.rmtree(root)
        if args.keep:
            report["kept_base"] = base
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        if not args.keep:
            shutil.rmtree(base)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--worker":
        return worker(sys.argv[2], sys.argv[3])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scratch-parent", required=True,
                        help="existing disposable scratch filesystem; synthetic fixtures are written here")
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--python-no-site", action="store_true", help="run workers with python -S; omit site hooks")
    parser.add_argument("--keep", action="store_true", help="keep fixtures for a separate syscall trace")
    args = parser.parse_args()
    run_bench(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
