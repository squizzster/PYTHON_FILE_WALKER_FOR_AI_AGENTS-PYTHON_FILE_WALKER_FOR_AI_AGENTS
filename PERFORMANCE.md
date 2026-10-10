# Traversal performance

These point-in-time observations show how Linux filesystem caching affects the
walkers and compare directory-only output with recursive all-entry counts. They
are operational measurements, not controlled storage benchmarks.

```text
date_utc: 2026-10-10
commit: 228af50
python: 3.11.15
kernel: Linux 5.14.0-687.42.1.el9_8.x86_64
filesystem_reported_type: ext2/ext3
locale: C
timing_tool: /usr/bin/time -v
```

Each command streamed stdout to a local file. The generated JSON was parsed to
verify `complete: true`, zero errors, and the reported counts, then removed.
No run opened or read regular-file contents.

## Measurements

| Target | Mode | Cache observation | Directories | Entries | Wall time | CPU time | CPU | Filesystem inputs | Peak RSS | JSON bytes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Downloader | directory-only | first observed | 87,857 | — | 246.79 s | 2.95 s | 1% | 714,632 | 15,616 KiB | 6,016,434 |
| Downloader | all-entry count | warm | 87,857 | 259,579 | 1.71 s | 1.70 s | 99% | 0 | 15,104 KiB | 11,029,955 |
| Downloader | all-entry count | warm, after larger-tree scan | 87,857 | 259,579 | 1.98 s | 1.68 s | 85% | 0 | 15,104 KiB | 11,029,955 |
| Classifier V2 | all-entry count | first observed | 292,957 | 1,262,957 | 934.34 s | 13.32 s | 1% | 2,282,000 | 16,256 KiB | 35,548,696 |
| Classifier V2 | all-entry count | warm | 292,957 | 1,262,957 | 6.27 s | 5.95 s | 94% | 0 | 16,256 KiB | 35,548,696 |
| Classifier V2 | directory-only | warm | 292,957 | — | 4.46 s | 4.12 s | 92% | 0 | 16,256 KiB | 18,831,665 |

`Downloader` identifies the `EDGAR_SEC_FILING_DOWNLOADER` root, and
`Classifier V2` identifies `EDGAR_SEC_FILING_BUSINESS_GENOME_CLASSIFIER_V2`.
The all-entry counts found 10,693 empty directories in Downloader and 13,715
in Classifier V2. An empty directory had `count: 0`, including hidden and
special entries in that decision.

`Filesystem inputs` is the counter reported by GNU `time`; it is not a byte
count. The target labels are short names for the measured directory roots.

## Cache warm-up

The operating system caches directory data, dentries, inodes, and file-backed
pages. A first traversal may therefore spend nearly all its elapsed time waiting
for storage, while a later traversal can reuse cached metadata.

No cache was deliberately cleared. “First observed” means only the first run
made in this measurement session; it is not a guaranteed cold-cache state.
“Warm” means a preceding traversal had read the same tree. Zero reported
filesystem inputs and high CPU utilization provide evidence that those runs
were served from cache.

The cache remained useful across targets. After the 292,957-directory tree was
scanned, Downloader still completed in 1.98 seconds with zero filesystem
inputs, compared with its earlier 1.71-second warm run.

## Directory-only versus all-entry count

The directly comparable warm runs on Classifier V2 took 4.46 seconds for
directory-only output and 6.27 seconds for `--number --all-entries`:

- Directory-only saved 1.81 seconds, or 28.9% of the all-entry-count time.
- Directory-only emitted 47.0% fewer JSON bytes.
- Peak memory was unchanged at 16,256 KiB.

Both modes must enumerate every directory entry to identify child directories.
The count mode additionally increments the all-entry count and emits a `files`
object for each real directory. It does not emit individual filenames or request
per-entry metadata.

There was no controlled cold-cache A/B run. If the measured 1.81-second warm
processing difference were applied to the 934.34-second first-observed run, the
implied saving would be about 0.2%. That is an inference, not a measurement, and
ordinary storage variation could exceed it. The evidence therefore supports:

- On storage-bound initial traversals, directory enumeration dominates and
  directory-only output is unlikely to save much wall time.
- On warm traversals, directory-only output materially reduces CPU and JSON
  generation work.
- Filename, permission, or full-stat modes are outside this comparison and may
  cost more than `--number --all-entries`.

## Reproduce the commands

```bash
LC_ALL=C /usr/bin/time -v -o timing.txt \
  ./python_file_walker_for_ai_agents.py DIRECTORY > tree.json

LC_ALL=C /usr/bin/time -v -o timing.txt \
  ./list_files_in_a_directory_tree_to_json.py \
  --number --all-entries DIRECTORY > tree.json
```

Results describe a live filesystem rather than an atomic snapshot. Cache state,
storage, directory layout, concurrent activity, and output destination can all
change the timings.
