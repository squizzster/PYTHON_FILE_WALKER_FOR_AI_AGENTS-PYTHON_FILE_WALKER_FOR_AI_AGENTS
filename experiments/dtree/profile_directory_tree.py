#!/usr/bin/env python3
"""Count syscalls using the optional local C helper; no timing under tracing.

Uses an ALREADY-CREATED synthetic fixture. It does not create/delete files.
python3 profile_directory_tree.py --helper ./syscall_count \
    --unknown-library ./force_dtype_unknown.so /path/to/synthetic-fixture
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "benchmark_directory_tree.py")
META = ("stat", "lstat", "fstat", "newfstatat", "statx")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--helper", required=True)
    parser.add_argument("--unknown-library", required=True)
    parser.add_argument("fixture")
    args = parser.parse_args()
    report = {"fixture": args.fixture, "method": "ptrace one process; startup subtracted using identical noop worker",
              "normal": {}, "forced_DT_UNKNOWN": {}}
    for group in ("normal", "forced_DT_UNKNOWN"):
        env = dict(os.environ)
        if group != "normal":
            env["LD_PRELOAD"] = os.path.abspath(args.unknown_library)
        else:
            env.pop("LD_PRELOAD", None)
        for engine in ("noop", "dtree-default", "dtree-low-io", "listdir-lstat", "os-walk"):
            command = [os.path.abspath(args.helper), "--", sys.executable, "-S", "-B", WORKER,
                       "--worker", engine, args.fixture]
            result = subprocess.run(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if result.returncode:
                raise RuntimeError(result.stderr.decode("utf-8", "replace"))
            summary = json.loads(result.stderr.decode("ascii").splitlines()[-1])
            report[group][engine] = summary
        baseline = report[group]["noop"]["syscalls"]
        for engine in ("dtree-default", "dtree-low-io", "listdir-lstat", "os-walk"):
            rec = report[group][engine]
            observed = rec["syscalls"]
            delta = {name: observed.get(name, {}).get("calls", 0) - baseline.get(name, {}).get("calls", 0)
                     for name in set(observed) | set(baseline)}
            rec["startup_subtracted_calls"] = delta
            rec["startup_subtracted_metadata_calls"] = sum(delta.get(name, 0) for name in META)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
