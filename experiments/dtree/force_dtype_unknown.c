/* Test helper ONLY. Force CPython's real DT_UNKNOWN fallback path.
 * Build: gcc -O2 -Wall -shared -fPIC -o force_dtype_unknown.so force_dtype_unknown.c -ldl
 * Use only on test fixtures: LD_PRELOAD=$PWD/force_dtype_unknown.so python3 ...
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>

struct dirent *readdir(DIR *dirp) {
    static struct dirent *(*real_fn)(DIR *);
    if (!real_fn) real_fn = dlsym(RTLD_NEXT, "readdir");
    if (!real_fn) { fputs("cannot resolve readdir\n", stderr); abort(); }
    struct dirent *entry = real_fn(dirp);
    if (entry) entry->d_type = DT_UNKNOWN;
    return entry;
}
struct dirent64 *readdir64(DIR *dirp) {
    static struct dirent64 *(*real_fn)(DIR *);
    if (!real_fn) real_fn = dlsym(RTLD_NEXT, "readdir64");
    if (!real_fn) { fputs("cannot resolve readdir64\n", stderr); abort(); }
    struct dirent64 *entry = real_fn(dirp);
    if (entry) entry->d_type = DT_UNKNOWN;
    return entry;
}
