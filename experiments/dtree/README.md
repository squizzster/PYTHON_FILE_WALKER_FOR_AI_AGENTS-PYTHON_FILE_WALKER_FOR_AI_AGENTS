# Dtree verification assets

Tests and synthetic benchmarks for
`src/python_file_walker_for_ai_agents/directory_tree.py`.

```text
external_walker_dependencies: []
runtime_test_framework: unittest
benchmark_engines: [dtree, listdir-lstat, os-walk]
benchmark_fixtures: [file-heavy, mixed, directory-heavy]
```

From this directory:

```bash
uv run --locked python -m unittest -q test_directory_tree.py
uv run --locked python benchmark_directory_tree.py \
  --scratch-parent /dev/shm --repeats 3 --python-no-site
```

The unittest suite covers hidden directories, sorting, directory-symlink leaves,
filesystem pruning, arbitrary filename bytes, deep trees, descriptor limits,
races, permissions, output failures, and signals.

The benchmark creates and removes more than 150,000 empty fixture entries under
the supplied scratch parent. Use disposable storage. It does not drop caches or
measure physical disk I/O.

Optional Linux x86-64 instrumentation:

```bash
gcc -O2 -Wall -Wextra -shared -fPIC \
  -o force_dtype_unknown.so force_dtype_unknown.c -ldl
LD_PRELOAD="$PWD/force_dtype_unknown.so" \
  uv run --locked python -m unittest -q test_directory_tree.py

gcc -O2 -Wall -Wextra -o syscall_count syscall_count.c
```

`force_dtype_unknown.so` forces libc directory entries through Python's native
metadata path. `syscall_count` uses `ptrace` and counts syscalls, not storage I/O.
