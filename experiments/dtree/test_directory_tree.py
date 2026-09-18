#!/usr/bin/env python3
"""Run: python3 -m unittest -v test_directory_tree

Only temporary test fixtures are changed. Linux and Python 3.12+.
Optional LD_PRELOAD helper is built separately for the DT_UNKNOWN tests.
"""
import base64
import errno
import io
import json
import locale
import os
import random
import resource
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SOURCE_ROOT = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, SOURCE_ROOT)

from python_file_walker_for_ai_agents import directory_tree as dt

SCRIPT = os.path.join(PROJECT_ROOT, "python_file_walker_for_ai_agents.py")


def names(node):
    return [child["name"] for child in node["children"]]


def decode_name(node, key="name"):
    if key + "_bytes_b64" in node:
        return base64.b64decode(node[key + "_bytes_b64"])
    return node[key].encode("utf-8")


def flatten(node):
    found = []
    stack = [(node, ())]
    while stack:
        item, parent = stack.pop()
        path = parent + (decode_name(item),)
        found.append((path, item["type"]))
        stack.extend((child, path) for child in reversed(item.get("children", [])))
    return found


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="dtree-test-")
        self.old_locale = locale.setlocale(locale.LC_COLLATE)
        locale.setlocale(locale.LC_COLLATE, "C")

    def tearDown(self):
        locale.setlocale(locale.LC_COLLATE, self.old_locale)
        shutil.rmtree(self.temp)

    def mkdir(self, name):
        path = os.path.join(self.temp, name)
        os.makedirs(path)
        return path

    def file(self, name):
        path = os.path.join(self.temp, name)
        with open(path, "wb") as handle:
            handle.write(b"DO NOT READ FILE CONTENTS\n")
        return path

    def run_scan(self, location=None, **kwargs):
        output, errors = io.BytesIO(), io.StringIO()
        scanner = dt.DirectoryTree(output, errors, **kwargs)
        status = scanner.run(self.temp if location is None else location)
        return status, json.loads(output.getvalue().decode("ascii")), errors.getvalue()

    def cli(self, *args, **kwargs):
        return subprocess.run([sys.executable, SCRIPT] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)

    def test_empty(self):
        code, doc, err = self.run_scan()
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(doc["complete"])
        self.assertEqual(doc["errors"], 0)
        self.assertEqual(doc["tree"]["children"], [])

    def test_directories_only_sorted(self):
        self.mkdir("z/child")
        self.mkdir("a")
        self.file("file")
        self.mkdir(".hidden/subdir")
        code, doc, err = self.run_scan()
        self.assertEqual(names(doc["tree"]), [".hidden", "a", "z"])
        self.assertEqual(names(doc["tree"]["children"][0]), ["subdir"])
        self.assertEqual(names(doc["tree"]["children"][2]), ["child"])
        self.assertEqual((code, err), (0, ""))

    def test_hidden_directories_are_included(self):
        self.mkdir(".hidden/child")
        self.mkdir("normal")
        os.symlink("normal", os.path.join(self.temp, ".alias"))
        code, doc, err = self.run_scan()
        self.assertEqual(doc["tree"]["children"][0]["type"], "link")
        self.assertEqual(names(doc["tree"]), [".alias", ".hidden", "normal"])

    def test_hidden_root_is_still_traversed(self):
        path = self.mkdir(".hidden/child")
        code, doc, err = self.run_scan(os.path.dirname(path))
        self.assertEqual(names(doc["tree"]), ["child"])

    def test_directory_links_are_leaves(self):
        self.mkdir("real/child")
        os.symlink("real", os.path.join(self.temp, "alias"))
        code, doc, err = self.run_scan()
        alias = doc["tree"]["children"][0]
        self.assertEqual(alias, {"name": "alias", "type": "link", "target": "real"})
        self.assertEqual((code, err), (0, ""))

    def test_file_broken_and_cyclic_links_omitted(self):
        self.file("file")
        for name, target in [("filelink", "file"), ("broken", "missing"),
                             ("cycle1", "cycle2"), ("cycle2", "cycle1")]:
            os.symlink(target, os.path.join(self.temp, name))
        code, doc, err = self.run_scan()
        self.assertEqual(doc["tree"]["children"], [])
        self.assertEqual((code, err), (0, ""))

    def test_symlink_to_parent_does_not_recurse(self):
        self.mkdir("a")
        os.symlink("..", os.path.join(self.temp, "a", "up"))
        code, doc, err = self.run_scan()
        self.assertEqual(doc["tree"]["children"][0]["children"][0]["type"], "link")
        self.assertEqual(code, 0)

    def test_explicit_root_symlink_is_followed(self):
        self.mkdir("real/child")
        link = os.path.join(self.temp, "alias")
        os.symlink("real", link)
        code, doc, err = self.run_scan(link)
        self.assertEqual(names(doc["tree"]), ["child"])

    def test_missing_root(self):
        code, doc, err = self.run_scan(os.path.join(self.temp, "missing"))
        self.assertEqual(code, 1)
        self.assertFalse(doc["complete"])
        self.assertEqual(doc["tree"]["error"]["errno"], errno.ENOENT)
        self.assertIn("open directory", err)

    def test_regular_file_root(self):
        code, doc, err = self.run_scan(self.file("file"))
        self.assertEqual(code, 1)
        self.assertEqual(doc["tree"]["error"]["errno"], errno.ENOTDIR)

    def test_fifo_root_cannot_block(self):
        fifo = os.path.join(self.temp, "fifo")
        os.mkfifo(fifo)
        result = self.cli(fifo, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["tree"]["error"]["errno"], errno.ENOTDIR)

    def test_fifo_and_socket_entries_omitted(self):
        os.mkfifo(os.path.join(self.temp, "fifo"))
        sock = socket.socket(socket.AF_UNIX)
        try:
            sock.bind(os.path.join(self.temp, "socket"))
            code, doc, err = self.run_scan()
            self.assertEqual(doc["tree"]["children"], [])
            self.assertEqual(code, 0)
        finally:
            sock.close()

    def test_json_escaping_and_unicode(self):
        testnames = ['quote"', "back\\slash", "new\nline", "tab\tname", "\x01control", "-dash", "snow-\u96ea", "\U0001f333"]
        for name in testnames:
            self.mkdir(name)
        code, doc, err = self.run_scan()
        self.assertEqual(set(names(doc["tree"])), set(testnames))
        self.assertEqual(code, 0)

    def test_invalid_utf8_roundtrips_without_surrogates(self):
        raw = os.fsencode(self.temp) + b"/bad-\xff\xfe"
        os.mkdir(raw)
        os.symlink(b"bad-\xff\xfe", os.fsencode(self.temp) + b"/alias")
        code, doc, err = self.run_scan()
        children = doc["tree"]["children"]
        self.assertEqual(decode_name(children[0], "target"), b"bad-\xff\xfe")
        self.assertEqual(decode_name(children[1]), b"bad-\xff\xfe")
        json.dumps(doc, ensure_ascii=False).encode("utf-8", "strict")
        self.assertEqual(code, 0)

    def test_invalid_utf8_root(self):
        raw = os.fsencode(self.temp) + b"/\xff"
        os.mkdir(raw)
        code, doc, err = self.run_scan(raw)
        self.assertEqual(decode_name(doc["tree"]), raw)
        self.assertEqual(code, 0)

    def test_ascii_stdout_locale(self):
        self.mkdir("\u96ea")
        env = dict(os.environ, LC_ALL="C", PYTHONIOENCODING="ascii:strict")
        result = self.cli(self.temp, env=env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(names(json.loads(result.stdout)["tree"]), ["\u96ea"])

    def test_invalid_environment_locale_falls_back(self):
        self.mkdir("a")
        env = dict(os.environ, LC_COLLATE="not_a_real_locale")
        env.pop("LC_ALL", None)
        result = self.cli(self.temp, env=env)
        self.assertEqual(result.returncode, 0)

    def test_relative_location_and_cwd_unchanged(self):
        cwd = os.getcwd()
        relative = os.path.relpath(self.temp)
        code, doc, err = self.run_scan(relative)
        self.assertEqual(doc["tree"]["name"], relative)
        self.assertEqual(os.getcwd(), cwd)

    def test_trailing_slash(self):
        self.mkdir("a")
        code, doc, err = self.run_scan(self.temp + "/")
        self.assertEqual(names(doc["tree"]), ["a"])

    def test_no_location_and_extra_location(self):
        for args in [(), (self.temp, self.temp), ("",)]:
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            help_doc = json.loads(result.stderr)
            self.assertEqual(help_doc["usage"], "python_file_walker_for_ai_agents.py LOCATION")

    def test_help(self):
        for flag in ("-h", "--help", "-help"):
            result = self.cli(flag)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
            help_doc = json.loads(result.stderr)
            self.assertEqual(help_doc["usage"], "python_file_walker_for_ai_agents.py LOCATION")
            self.assertEqual(set(help_doc["nodes"]), {"directory", "link"})

    def test_dash_location_needs_no_option_delimiter(self):
        self.mkdir("-name/child")
        result = self.cli("-name", cwd=self.temp)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(names(json.loads(result.stdout)["tree"]), ["child"])

    def test_legacy_backend_same_output_restores_cwd(self):
        self.mkdir("a/b")
        self.mkdir("z")
        os.symlink("a", os.path.join(self.temp, "alias"))
        cwd = os.getcwd()
        native = self.run_scan()
        legacy = self.run_scan(native_scandir=False)
        self.assertEqual(native, legacy)
        self.assertEqual(cwd, os.getcwd())

    def test_legacy_backend_restores_cwd_on_failure(self):
        self.mkdir("a")
        class FailingSink(object):
            def write(self, data):
                raise OSError(errno.ENOSPC, "no space")
        cwd = os.getcwd()
        scanner = dt.DirectoryTree(FailingSink(), io.StringIO(), native_scandir=False)
        with self.assertRaises(OSError):
            scanner.run(self.temp)
        self.assertEqual(cwd, os.getcwd())

    def test_noatime_permission_fallback(self):
        real_open = dt.os.open
        attempts = []
        def wrapped(path, flags, **kwargs):
            attempts.append(flags)
            if flags & getattr(os, "O_NOATIME", 0):
                raise OSError(errno.EPERM, "no noatime permission")
            return real_open(path, flags, **kwargs)
        with mock.patch.object(dt.os, "open", side_effect=wrapped):
            code, doc, err = self.run_scan()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(attempts), 2)

    def test_noatime_unsupported_fallback(self):
        real_open = dt.os.open
        def wrapped(path, flags, **kwargs):
            if flags & getattr(os, "O_NOATIME", 0):
                raise OSError(errno.EOPNOTSUPP, "unsupported")
            return real_open(path, flags, **kwargs)
        with mock.patch.object(dt.os, "open", side_effect=wrapped):
            code, doc, err = self.run_scan()
        self.assertEqual(code, 0)

    def test_no_retry_on_media_error(self):
        with mock.patch.object(dt.os, "open", side_effect=OSError(errno.EIO, "media error")) as op:
            code, doc, err = self.run_scan()
        self.assertEqual(code, 1)
        self.assertEqual(op.call_count, 1)

    def test_native_noatime_preserves_directory_atime(self):
        if not getattr(os, "O_NOATIME", 0):
            self.skipTest("O_NOATIME unavailable")
        self.mkdir("a")
        past = 946684800
        for path in (self.temp, os.path.join(self.temp, "a")):
            os.utime(path, (past, past))
        code, doc, err = self.run_scan()
        self.assertEqual(code, 0)
        for path in (self.temp, os.path.join(self.temp, "a")):
            self.assertEqual(os.stat(path).st_atime, past)

    def test_directory_swap_to_symlink_not_followed(self):
        self.mkdir("victim")
        outside = tempfile.mkdtemp(prefix="dtree-outside-")
        os.mkdir(os.path.join(outside, "must-not-appear"))
        real_scan = dt.DirectoryTree.scan
        def wrapped(scanner, fd, name):
            result = real_scan(scanner, fd, name)
            if name == self.temp:
                os.rmdir(os.path.join(self.temp, "victim"))
                os.symlink(outside, os.path.join(self.temp, "victim"))
            return result
        try:
            with mock.patch.object(dt.DirectoryTree, "scan", new=wrapped):
                code, doc, err = self.run_scan()
            self.assertEqual(code, 1)
            self.assertNotIn("must-not-appear", json.dumps(doc))
        finally:
            shutil.rmtree(outside)

    def test_disappearing_directory_partial_json(self):
        self.mkdir("gone")
        self.mkdir("survivor")
        real_scan = dt.DirectoryTree.scan
        def wrapped(scanner, fd, name):
            result = real_scan(scanner, fd, name)
            if name == self.temp:
                os.rmdir(os.path.join(self.temp, "gone"))
            return result
        with mock.patch.object(dt.DirectoryTree, "scan", new=wrapped):
            code, doc, err = self.run_scan()
        self.assertEqual(code, 1)
        self.assertFalse(doc["complete"])
        self.assertEqual(names(doc["tree"]), ["gone", "survivor"])
        self.assertIn("error", doc["tree"]["children"][0])

    def test_root_rename_during_scan_remains_anchored(self):
        self.mkdir("a/child")
        new_name = self.temp + "-renamed"
        real_scan = dt.DirectoryTree.scan
        def wrapped(scanner, fd, name):
            result = real_scan(scanner, fd, name)
            if name == self.temp:
                os.rename(self.temp, new_name)
            return result
        old = self.temp
        try:
            with mock.patch.object(dt.DirectoryTree, "scan", new=wrapped):
                code, doc, err = self.run_scan()
        finally:
            self.temp = new_name
        self.assertEqual(code, 0)
        self.assertEqual(names(doc["tree"]["children"][0]), ["child"])
        self.assertEqual(doc["tree"]["name"], old)

    def test_partial_readdir_error_retains_known_entries(self):
        self.mkdir("known")
        real_scandir = dt.os.scandir
        class InterruptedIterator(object):
            def __init__(self, fd):
                self.it = real_scandir(fd)
                self.once = False
            def __iter__(self):
                return self
            def __next__(self):
                if self.once:
                    raise OSError(errno.EIO, "injected readdir error")
                self.once = True
                return next(self.it)
            def close(self):
                self.it.close()
        used = [False]
        def wrapped(fd):
            if not used[0]:
                used[0] = True
                return InterruptedIterator(fd)
            return real_scandir(fd)
        with mock.patch.object(dt.os, "scandir", side_effect=wrapped):
            code, doc, err = self.run_scan()
        self.assertEqual(code, 1)
        self.assertEqual(names(doc["tree"]), ["known"])
        self.assertEqual(doc["tree"]["errors"], 1)

    def test_entry_type_error_reported(self):
        class BadEntry(object):
            name = "unknown"
            def is_dir(self, **kwargs):
                raise OSError(errno.EACCES, "type inaccessible")
        with mock.patch.object(dt.os, "scandir", return_value=iter([BadEntry()])):
            code, doc, err = self.run_scan()
        self.assertEqual(code, 1)
        self.assertEqual(doc["tree"]["errors"], 1)
        self.assertIn("entry type", err)

    def test_symlink_target_permission_error(self):
        class BadLink(object):
            name = "badlink"
            def is_dir(self, follow_symlinks=True):
                if follow_symlinks:
                    raise OSError(errno.EACCES, "target inaccessible")
                return False
            def is_symlink(self):
                return True
        with mock.patch.object(dt.os, "scandir", return_value=iter([BadLink()])):
            code, doc, err = self.run_scan()
        self.assertEqual(code, 1)
        self.assertIn("symlink metadata", err)

    def test_ancestor_identity_cycle_is_stopped(self):
        self.mkdir("loop")
        real_fstat = dt.os.fstat
        identity = [None]
        def wrapped(fd):
            info = real_fstat(fd)
            if identity[0] is None:
                identity[0] = info
            return identity[0]
        with mock.patch.object(dt.os, "fstat", side_effect=wrapped):
            code, doc, err = self.run_scan()
        self.assertEqual(code, 1)
        self.assertEqual(doc["tree"]["children"][0]["error"]["errno"], errno.ELOOP)

    def test_different_filesystem_is_always_pruned(self):
        self.mkdir("foreign/hidden_child")
        real_fstat = dt.os.fstat
        calls = [0]
        def wrapped(fd):
            info = real_fstat(fd)
            calls[0] += 1
            if calls[0] == 2:
                values = list(info)
                values[2] = info.st_dev + 1000000
                return os.stat_result(values)
            return info
        with mock.patch.object(dt.os, "fstat", side_effect=wrapped):
            code, doc, err = self.run_scan()
        self.assertEqual(code, 0)
        self.assertEqual(doc["tree"]["children"][0]["pruned"], "different-filesystem")
        self.assertNotIn("hidden_child", json.dumps(doc))

    def test_descriptor_exhaustion_is_incomplete_not_crash(self):
        self.mkdir("a")
        real_open = dt.os.open
        def wrapped(path, flags, **kwargs):
            if path == "a":
                raise OSError(errno.EMFILE, "too many open files")
            return real_open(path, flags, **kwargs)
        with mock.patch.object(dt.os, "open", side_effect=wrapped):
            code, doc, err = self.run_scan()
        self.assertEqual(code, 1)
        self.assertEqual(doc["tree"]["children"][0]["error"]["errno"], errno.EMFILE)

    def test_no_fd_leak_repeated_scans(self):
        self.mkdir("a/b")
        self.mkdir("z")
        before = len(os.listdir("/proc/self/fd"))
        for unused in range(30):
            self.run_scan()
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_no_fd_leak_output_failure(self):
        self.mkdir("a/b")
        self.mkdir("z")
        class Fail(object):
            def write(self, data):
                raise OSError(errno.ENOSPC, "full")
        before = len(os.listdir("/proc/self/fd"))
        scanner = dt.DirectoryTree(Fail(), io.StringIO())
        scanner.out.limit = 1
        with self.assertRaises(OSError):
            scanner.run(self.temp)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_full_output_device(self):
        if not os.path.exists("/dev/full"):
            self.skipTest("/dev/full unavailable")
        with open("/dev/full", "wb") as sink:
            result = subprocess.run([sys.executable, SCRIPT, self.temp], stdout=sink,
                                    stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_broken_pipe(self):
        for i in range(1800):
            self.mkdir("directory-%04d" % i)
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        try:
            result = subprocess.run([sys.executable, SCRIPT, self.temp], stdout=write_fd,
                                    stderr=subprocess.PIPE, timeout=10)
        finally:
            os.close(write_fd)
        self.assertEqual(result.returncode, 141)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_short_writes(self):
        class ShortSink(object):
            def __init__(self):
                self.data = bytearray()
            def write(self, data):
                amount = min(7, len(data))
                self.data.extend(data[:amount])
                return amount
        sink = ShortSink()
        scanner = dt.DirectoryTree(sink, io.StringIO())
        self.assertEqual(scanner.run(self.temp), 0)
        self.assertTrue(json.loads(sink.data.decode("ascii"))["complete"])

    def test_zero_or_none_write_is_failure(self):
        for result in (0, None):
            sink = mock.Mock()
            sink.write.return_value = result
            writer = dt.BufferedJSON(sink)
            writer.write("{}")
            with self.assertRaises(OSError):
                writer.flush()

    def test_many_files_do_not_enter_output(self):
        for i in range(3000):
            self.file("f-%04d" % i)
        self.mkdir("only-directory")
        code, doc, err = self.run_scan()
        self.assertEqual(names(doc["tree"]), ["only-directory"])
        self.assertLess(len(json.dumps(doc)), 400)

    def test_randomized_against_independent_listdir_stat_reference(self):
        rng = random.Random(492075)
        for trial in range(16):
            base = self.mkdir("case-%02d" % trial)
            dirs = [base]
            for j in range(45):
                parent = rng.choice(dirs)
                name = ("." if rng.random() < 0.15 else "") + "n-%03d" % j
                path = os.path.join(parent, name)
                choice = rng.randrange(4)
                if choice < 2:
                    os.mkdir(path)
                    dirs.append(path)
                elif choice == 2:
                    with open(path, "wb"):
                        pass
                else:
                    os.symlink(rng.choice(dirs), path)
            expected = []
            stack = [(base, ())]
            while stack:
                path, parent = stack.pop()
                for name in sorted(os.listdir(path), reverse=True):
                    child = os.path.join(path, name)
                    if os.path.isdir(child):
                        rel = parent + (name.encode("utf-8"),)
                        if os.path.islink(child):
                            expected.append((rel, "link"))
                        else:
                            expected.append((rel, "directory"))
                            stack.append((child, rel))
            code, doc, err = self.run_scan(base)
            got = [(path[1:], typ) for path, typ in flatten(doc["tree"])[1:]]
            self.assertEqual(sorted(got), sorted(expected))
            self.assertEqual(code, 0)

    def test_deep_chain_over_pathmax_and_low_fd_limit(self):
        depth = 1400
        fd = os.open(self.temp, os.O_RDONLY | os.O_DIRECTORY)
        component = "deep"
        try:
            for unused in range(depth):
                os.mkdir(component, dir_fd=fd)
                child_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = child_fd
        finally:
            os.close(fd)
        def limit_fds():
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(32, hard), hard))
        try:
            result = self.cli(self.temp, preexec_fn=limit_fds, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            # The PRODUCER has no recursion. Raise only the test decoder's limit.
            old = sys.getrecursionlimit()
            try:
                sys.setrecursionlimit(10000)
                doc = json.loads(result.stdout)
            finally:
                sys.setrecursionlimit(old)
            count, node = 0, doc["tree"]
            while node["children"]:
                count += 1
                node = node["children"][0]
            self.assertEqual(count, depth)
            del node, doc
        finally:
            # Iterative fd-relative cleanup, including paths longer than PATH_MAX.
            fd = os.open(self.temp, os.O_RDONLY | os.O_DIRECTORY)
            for unused in range(depth):
                child_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = child_fd
            for unused in range(depth):
                parent_fd = os.open("..", os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)
                os.close(fd)
                os.rmdir(component, dir_fd=parent_fd)
                fd = parent_fd
            os.close(fd)

    def test_real_permissions_as_unprivileged_user(self):
        if os.geteuid() != 0:
            blocked = self.mkdir("blocked/inside")
            os.chmod(os.path.dirname(blocked), 0)
            try:
                code, doc, err = self.run_scan()
                self.assertEqual(code, 1)
            finally:
                os.chmod(os.path.dirname(blocked), 0o700)
            return
        import pwd
        try:
            user = pwd.getpwnam("nobody")
        except KeyError:
            self.skipTest("nobody account unavailable")
        os.chmod(self.temp, 0o755)
        self.mkdir("blocked/inside")
        os.chmod(os.path.join(self.temp, "blocked"), 0)
        self.mkdir("readable")
        def drop_privileges():
            os.setgroups([])
            os.setgid(user.pw_gid)
            os.setuid(user.pw_uid)
        try:
            result = self.cli(self.temp, preexec_fn=drop_privileges)
            self.assertEqual(result.returncode, 1, result.stderr)
            doc = json.loads(result.stdout)
            self.assertFalse(doc["complete"])
            self.assertEqual(names(doc["tree"]), ["blocked", "readable"])
        finally:
            os.chmod(os.path.join(self.temp, "blocked"), 0o700)

    def test_sigint_exit_code(self):
        # Force SIGINT during scan, not during Python's import machinery.
        program = ('import os,signal,sys; sys.path.insert(0,%r); '
                   'from python_file_walker_for_ai_agents import directory_tree as d; '
                   'd.DirectoryTree.scan=lambda *a: os.kill(os.getpid(), signal.SIGINT); '
                   'sys.argv=[%r,%r]; sys.exit(d.cli())') % (SOURCE_ROOT, SCRIPT, self.temp)
        result = subprocess.run([sys.executable, "-c", program], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 130)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_each_directory_enumerated_once(self):
        self.mkdir("a/b")
        self.mkdir("z")
        self.file("file")
        real_scan = dt.os.scandir
        seen = []
        def wrapped(fd):
            info = os.fstat(fd)
            seen.append((info.st_dev, info.st_ino))
            return real_scan(fd)
        with mock.patch.object(dt.os, "scandir", side_effect=wrapped):
            code, doc, err = self.run_scan()
        self.assertEqual(code, 0)
        self.assertEqual(len(seen), 4)
        self.assertEqual(len(set(seen)), 4)

    def test_only_directories_are_opened(self):
        self.mkdir("a")
        self.file("file")
        os.symlink("a", os.path.join(self.temp, "alias"))
        real_open = dt.os.open
        opened = []
        def wrapped(path, flags, **kwargs):
            self.assertTrue(flags & os.O_DIRECTORY)
            opened.append(path)
            return real_open(path, flags, **kwargs)
        with mock.patch.object(dt.os, "open", side_effect=wrapped):
            code, doc, err = self.run_scan()
        self.assertEqual(opened, [self.temp, "a"])
        self.assertEqual(code, 0)

    def test_invalid_names_with_same_display_do_not_collide(self):
        for raw in (b"\xff", b"\xfe", b"\xef\xbf\xbd"):
            os.mkdir(os.fsencode(self.temp) + b"/" + raw)
        code, doc, err = self.run_scan()
        actual = [decode_name(child) for child in doc["tree"]["children"]]
        self.assertEqual(set(actual), {b"\xff", b"\xfe", b"\xef\xbf\xbd"})
        self.assertEqual(len(actual), 3)

    def test_memory_error_exit_code(self):
        program = ('import sys; sys.path.insert(0,%r); '
                   'from python_file_walker_for_ai_agents import directory_tree as d; '
                   'from unittest import mock; '
                   'sys.argv=[%r,%r]; '
                   'p=mock.patch.object(d.DirectoryTree,"scan",side_effect=MemoryError); '
                   'p.start(); sys.exit(d.cli())') % (SOURCE_ROOT, SCRIPT, self.temp)
        result = subprocess.run([sys.executable, "-S", "-c", program], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"out of memory", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)

if __name__ == "__main__":
    unittest.main(verbosity=2)
