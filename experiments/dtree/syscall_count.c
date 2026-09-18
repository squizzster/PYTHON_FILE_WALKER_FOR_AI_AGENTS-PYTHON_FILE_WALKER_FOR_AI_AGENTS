/* Test/benchmark helper ONLY: Linux x86-64, gcc -O2 -Wall -o syscall_count syscall_count.c
 * Usage: ./syscall_count -- command arguments...
 * Child stdout/stderr pass through. A JSON syscall summary goes to stderr.
 * Counts one process, including startup; no fork/clone following. Not a disk-I/O meter.
 */
#define _GNU_SOURCE
#include <sys/ptrace.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/user.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error This optional syscall-counting helper requires Linux x86-64.
#endif
#define MAX_SYSCALL 1024
static unsigned long long counts[MAX_SYSCALL];
static unsigned long long failed[MAX_SYSCALL];
static const char *scname(long n) {
    switch(n) {
#define SC(x) case SYS_##x: return #x;
        SC(read) SC(write) SC(open) SC(openat) SC(close) SC(stat) SC(lstat)
        SC(fstat) SC(newfstatat) SC(getdents) SC(getdents64) SC(readlink)
        SC(readlinkat) SC(fcntl) SC(dup) SC(dup2) SC(dup3) SC(lseek)
        SC(chdir) SC(fchdir) SC(statx) SC(execve) SC(mmap) SC(munmap)
#undef SC
        default: return NULL;
    }
}
int main(int argc, char **argv) {
    int start = 1, status, entering = 1, rc = 1;
    long number = -1;
    if (argc > 1 && !strcmp(argv[1], "--")) start++;
    if (argc <= start) { fprintf(stderr, "usage: syscall_count -- command args\n"); return 2; }
    pid_t pid = fork();
    if (pid < 0) { perror("fork"); return 2; }
    if (pid == 0) {
        if (ptrace(PTRACE_TRACEME, 0, NULL, NULL) < 0) { perror("ptrace"); _exit(2); }
        raise(SIGSTOP);
        execvp(argv[start], argv + start);
        perror("execvp"); _exit(127);
    }
    if (waitpid(pid, &status, 0) < 0 || !WIFSTOPPED(status)) { fprintf(stderr,"trace startup failed\n"); return 2; }
    if (ptrace(PTRACE_SETOPTIONS, pid, 0, PTRACE_O_TRACESYSGOOD | PTRACE_O_EXITKILL) < 0) {
        perror("PTRACE_SETOPTIONS"); kill(pid, SIGKILL); waitpid(pid, NULL, 0); return 2;
    }
    int deliver = 0;
    for (;;) {
        if (ptrace(PTRACE_SYSCALL, pid, 0, deliver) < 0) { perror("PTRACE_SYSCALL"); break; }
        if (waitpid(pid, &status, 0) < 0) { if (errno == EINTR) continue; perror("waitpid"); break; }
        deliver = 0;
        if (WIFEXITED(status)) { rc = WEXITSTATUS(status); break; }
        if (WIFSIGNALED(status)) { rc = 128 + WTERMSIG(status); break; }
        if (!WIFSTOPPED(status)) continue;
        int sig = WSTOPSIG(status);
        if (sig == (SIGTRAP | 0x80)) {
            struct user_regs_struct regs;
            if (ptrace(PTRACE_GETREGS, pid, 0, &regs) < 0) { perror("PTRACE_GETREGS"); break; }
            if (entering) {
                number = (long)regs.orig_rax;
                if (number >= 0 && number < MAX_SYSCALL) counts[number]++;
            } else if (number >= 0 && number < MAX_SYSCALL && (long)regs.rax < 0 && (long)regs.rax >= -4095) {
                failed[number]++;
            }
            entering = !entering;
        } else if (sig != SIGTRAP && sig != SIGSTOP) {
            deliver = sig;
        }
    }
    fprintf(stderr, "{\"exit_status\":%d,\"syscalls\":{", rc);
    int first = 1;
    unsigned long long total = 0;
    for (long i = 0; i < MAX_SYSCALL; i++) {
        total += counts[i];
        const char *name = scname(i);
        if (counts[i] && name) {
            fprintf(stderr, "%s\"%s\":{\"calls\":%llu,\"errors\":%llu}", first ? "" : ",", name, counts[i], failed[i]);
            first = 0;
        }
    }
    fprintf(stderr, "},\"total_syscalls\":%llu}\n", total);
    return rc;
}
