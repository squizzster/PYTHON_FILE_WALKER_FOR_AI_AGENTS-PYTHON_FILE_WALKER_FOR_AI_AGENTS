# Current verification report

```text
date_utc: 2026-09-18
python: 3.12.13
kernel: 5.14.0-687.42.1.el9_8.x86_64
libc: glibc 2.34
benchmark_storage: tmpfs (/dev/shm)
benchmark_repeats: 3
cache_state: warm
python_site_initialization: disabled
```

## Correctness

| Check | Result |
| --- | ---: |
| Native unittest suite, Python 3.12 | 53 passed |
| Path-backend unittest suite, Python 3.5 | 53 run, 1 skipped |
| Forced `DT_UNKNOWN` suite | 52 passed |
| Relocatable shim suite, Python 3.12 | 5 passed |
| Installed-wheel shim suite, Python 3.5 | 5 passed |
| Architecture validation | 0 errors, 0 advisories |

Both optional C helpers compile with `gcc -O2 -Wall -Wextra`. The test suite
invokes no external filesystem walker.

## Benchmark

Median worker time measures scan plus JSON generation and excludes interpreter
startup. Fixtures are created immediately before measurement.

| Fixture | Directories | Files | Dtree | listdir+lstat | os.walk |
| --- | ---: | ---: | ---: | ---: | ---: |
| file-heavy | 201 | 100,000 | 40.87 ms | 340.73 ms | 48.95 ms |
| mixed | 2,101 | 40,000 | 37.94 ms | 165.78 ms | 49.29 ms |
| directory-heavy | 10,201 | 0 | 110.53 ms | 108.44 ms | 148.97 ms |

| Fixture | Dtree median RSS |
| --- | ---: |
| file-heavy | 15,488 KiB |
| mixed | 15,744 KiB |
| directory-heavy | 15,744 KiB |

These are warm-cache tmpfs measurements with three repeats. They are not cold
storage, physical-I/O, seek, wear, or cross-filesystem measurements.
