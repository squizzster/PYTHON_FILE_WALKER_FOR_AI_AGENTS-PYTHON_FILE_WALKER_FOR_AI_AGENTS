# Test and benchmark report

Recorded in this session on 18 September 2026. These are measured results,
not projected disk performance or exhaustive hardware certification.

## Test outcome

Final normal run: **59 tests run, 58 passed, 1 skipped**, 9.429 seconds.
Final forced-DT_UNKNOWN run: **59 tests run, 58 passed, 1 skipped**, 9.549 seconds.
The forced run used LD_PRELOAD to overwrite the d_type returned by libc
readdir/readdir64 with DT_UNKNOWN, exercising CPython's actual metadata fallback,
not merely replacing DirEntry.is_dir with a mock.

The skipped test in both runs was the direct `tree -d -J` comparison: `tree`
was not installed, and downloading it was unavailable. A GNU find selection
comparison passed. Sixteen seeded randomized filesystem trees, each scanned
with and without hidden entries, matched an independent listdir/stat reference.

Coverage includes normal and hidden directories; symlink directory leaves,
file links, broken links and loops; arbitrary non-UTF-8 bytes and byte-distinct
names with equal display text; Unicode/control characters; missing, regular
file and FIFO roots; sockets/FIFOs; permission errors after dropping root
privileges; directory disappearance; directory-to-symlink replacement; root
rename during traversal; injected partial readdir and metadata errors;
O_NOATIME success and fallback; injected device-boundary and ancestor-identity
cycles; output short writes, zero-progress writes, /dev/full, broken pipes,
SIGINT, injected memory failure, and descriptor leak checks.

A real 1,400-level chain, with descendant paths longer than Linux's usual
single-path argument limit, was produced successfully under a 32-fd soft
limit. The producer did not change its recursion limit. Only the test JSON
decoder's recursion limit was raised to consume that intentionally deep JSON.

The code parses using Python 3.5 grammar, and explicit legacy-backend tests
passed under CPython 3.13.5. Real older interpreter binaries were unavailable.
Device-boundary/ancestor-cycle failures were injected; privileged mount-race
and actual bind-cycle tests were not performed.

All four benchmark producers were additionally compared on all six measured
filesystem/fixture combinations: **24 outputs validated**, equal after sibling
sorting. The fixtures contain no symlinks, so low-I/O selection is equivalent
on these fixtures. See results/benchmark-output-validation.json.

## Environment and method

CPython 3.13.5; Linux x86-64 kernel 6.18.44; glibc-based Debian container.
Filesystems visible to the container: tmpfs at /dev/shm, overlay at /mnt/data.
The overlay's underlying physical device/cache characteristics are unknown.
This environment's normal site initialization adds unusual startup overhead,
so all measured worker processes used Python -S. Interpreter/stdlib startup
is included in the end-to-end tables, but excluded from scan/JSON work tables.

Each engine had one warmup per fixture, then nine serial fresh-process runs
in seeded randomized order. Output went to /dev/null. No caches were dropped,
no disk flush was forced, and no priority/CPU affinity settings were changed.
Fixtures were newly created, so these are **warm-cache** results. No timings
were taken under ptrace. Shared-host noise remains possible; raw runs include
minimums, maximums, and per-run timings.

The baselines are included in benchmark_directory_tree.py. listdir+lstat
performs one lstat per visible entry; os.walk is a contemporary scandir-based
walker, not an intentionally old walk implementation. Both baseline builders
retain a complete nested Python object before JSON serialization. Dtree streams
JSON and adds descriptor-based traversal safeguards. These comparisons therefore
measure useful complete implementations, not isolated enumeration primitives.
All engines import the same benchmark harness before their worker timer starts.

| Fixture | Directories including root | Regular files |
| --- | ---: | ---: |
| file-heavy | 201 | 100,000 |
| mixed | 2,101 | 40,000 |
| directory-heavy | 10,201 | 0 |

## Median scan + JSON time, excluding imports/startup

### Container overlay

| Fixture | Dtree default | Dtree low-I/O | listdir + lstat | os.walk |
| --- | ---: | ---: | ---: | ---: |
| file-heavy | 35.69 ms | 32.02 ms | 293.85 ms | 35.10 ms |
| mixed | 29.24 ms | 28.70 ms | 132.03 ms | 35.20 ms |
| directory-heavy | 86.42 ms | 85.11 ms | 87.43 ms | 110.76 ms |

### tmpfs

| Fixture | Dtree default | Dtree low-I/O | listdir + lstat | os.walk |
| --- | ---: | ---: | ---: | ---: |
| file-heavy | 22.87 ms | 21.67 ms | 184.32 ms | 23.37 ms |
| mixed | 25.50 ms | 21.81 ms | 90.57 ms | 33.02 ms |
| directory-heavy | 59.35 ms | 55.48 ms | 51.42 ms | 76.41 ms |

## Median fresh-process benchmark-worker elapsed time

These include the shared benchmark worker's startup/import overhead. They are
not timings of the standalone script's smaller CLI/import path.

### Container overlay

| Fixture | Dtree default | Dtree low-I/O | listdir + lstat | os.walk |
| --- | ---: | ---: | ---: | ---: |
| file-heavy | 71.28 ms | 67.50 ms | 327.59 ms | 69.70 ms |
| mixed | 64.30 ms | 61.22 ms | 166.38 ms | 69.26 ms |
| directory-heavy | 120.17 ms | 117.48 ms | 128.92 ms | 148.39 ms |

### tmpfs

| Fixture | Dtree default | Dtree low-I/O | listdir + lstat | os.walk |
| --- | ---: | ---: | ---: | ---: |
| file-heavy | 55.67 ms | 59.81 ms | 219.79 ms | 57.09 ms |
| mixed | 64.86 ms | 61.20 ms | 127.27 ms | 70.92 ms |
| directory-heavy | 93.09 ms | 87.83 ms | 84.70 ms | 110.10 ms |

## Interpretation

The largest improvement is over per-file lstat in file-heavy directories.
The modern os.walk baseline is already competitive: on the file-heavy overlay
fixture, its scan/JSON time was slightly below Dtree default. On directory-heavy
tmpfs, listdir+lstat was faster than either Dtree mode. The evidence does not
support a claim that Dtree is universally the fastest possible Python walker.

Default vs low-I/O timing differences on these link-free fixtures are primarily
CPU/sorting effects and noise, not avoided file metadata reads. With links,
low-I/O additionally avoids target probes and readlink. Directory order does
not necessarily equal physical media order.

For 10,201 directories, median process high-water RSS was approximately
10.6 MiB (tmpfs Dtree) / 11.9 MiB (overlay Dtree) versus 14.5 MiB for the two
whole-tree builders. RSS includes interpreter/worker baseline memory and is
not a precise measurement of data-structure allocation.

## Syscall counts: 201 directories, 100,000 regular files

A small Linux x86-64 ptrace helper counted a single process; an identical
no-op worker's startup counts were subtracted. Metadata means the sum of
stat/lstat/fstat/newfstatat/statx, not just pathname lookups. There were no
symlinks in this fixture. Per-directory safety costs are intentionally included.

| Engine | Metadata, normal d_type | Metadata, forced DT_UNKNOWN | getdents64 | openat |
| --- | ---: | ---: | ---: | ---: |
| Dtree default | 402 | 100,602 | 402 | 201 |
| Dtree low-I/O | 402 | 100,602 | 402 | 201 |
| listdir+lstat | 100,401 | 100,401 | 402 | 201 |
| os.walk builder | 601 | 100,801 | 402 | 201 |

The 402 normal Dtree metadata calls are two per directory in this environment
(one explicit identity fstat plus the library's directory check), not stats of
100,000 regular files. Dtree also incurred 603 fcntl calls for descriptor
handling. Avoiding per-file metadata does not mean zero overhead.

DT_UNKNOWN correctly adds one required metadata lookup for every visible
entry, erasing the principal I/O advantage over listdir+lstat. This is why
performance cannot be promised from a filesystem brand name alone. The two
getdents64 calls per directory in this fixture include its end-of-directory
check; larger directories can need many more batches.

**Syscall counts are not physical disk IOPS, bytes read, seek counts, write
amplification, or wear measurements.** Cached metadata calls and on-media
metadata reads are different quantities. No cold-disk, tape, USB-controller,
network-storage, or ext4/XFS/Btrfs/ZFS/F2FS/NTFS hardware benchmark was available.
There is no proof here of a global I/O minimum or universal fastest execution.

## Reproduction and provenance

See README.md for commands and safety notes. Raw results, both final test logs,
and output-validation records are in results/. C helpers are optional test
source code only and are not dependencies of the production Python script.

SHA-256 of the delivered production script:

```text
ea71c5c85e2ec83810814a2e9af98d1c13bc15fa6366ca57f5f2c2fbdf69272c
```

The final CLI failure-reporting cleanup changed only the outer CLI error
handler after the tmpfs timing run; the benchmark uses the unchanged traversal
class directly. All final tests and output validation used the delivered code.
