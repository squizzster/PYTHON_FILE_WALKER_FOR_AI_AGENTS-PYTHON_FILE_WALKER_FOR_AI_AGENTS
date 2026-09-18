import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SOURCE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SOURCE_ROOT)

from python_file_walker_for_ai_agents import directory_tree
from python_file_walker_for_ai_agents.file_entries import FileObjectWriter


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOTHER = os.path.join(
    PROJECT_ROOT, "list_files_in_a_directory_tree_to_json.py")
SISTER = os.path.join(PROJECT_ROOT, "list_files_in_a_directory_to_json.py")


def child(node, name):
    return next(item for item in node["children"] if item["name"] == name)


class RecursiveFileListingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="recursive-file-listing-test-")
        os.mkdir(os.path.join(self.temp, "a"))
        os.mkdir(os.path.join(self.temp, "z"))
        with open(os.path.join(self.temp, "visible"), "wb") as stream:
            stream.write(b"CONTENT MUST NOT BE READ")
        with open(os.path.join(self.temp, ".hidden"), "wb"):
            pass
        with open(os.path.join(self.temp, "a", "nested"), "wb"):
            pass
        os.symlink("a", os.path.join(self.temp, ".directory-link"))
        os.symlink("visible", os.path.join(self.temp, "file-link"))
        os.mkfifo(os.path.join(self.temp, "fifo"))

    def tearDown(self):
        shutil.rmtree(self.temp)

    def invoke(self, shim, *options):
        result = subprocess.run(
            [sys.executable, shim] + list(options) + [self.temp],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        return json.loads(result.stdout.decode("ascii"))

    def mother(self, *options):
        document = self.invoke(MOTHER, *options)
        self.assertTrue(document["complete"])
        self.assertEqual(document["errors"], 0)
        return document["tree"]

    def sister(self, *options):
        return self.invoke(SISTER, *options)["files"]

    def test_recursive_default_combines_brother_tree_and_sister_files(self):
        tree = self.mother()
        self.assertEqual(
            [item["name"] for item in tree["children"]],
            [".directory-link", "a", "z"],
        )
        self.assertEqual(child(tree, ".directory-link")["type"], "link")
        self.assertNotIn("files", child(tree, ".directory-link"))
        self.assertEqual(set(tree["files"]["entries"]), {".hidden", "visible"})
        self.assertEqual(child(tree, "a")["files"]["entries"], ["nested"])
        self.assertEqual(child(tree, "z")["files"]["entries"], [])

    def test_every_file_mode_is_the_sister_schema(self):
        for options in (
                (), ("--number",), ("-n",), ("--inode",), ("--permissions",),
                ("--stats",), ("--all-entries",),
                ("--file-permissions-stats",),
                ("--file_permissions_stats",),
                ("--all-entries", "--stats"), ("--base64", "--inode")):
            self.assertEqual(self.mother(*options)["files"],
                             self.sister(*options))

    def test_stats_never_follow_symlinks(self):
        records = self.mother("--all-entries", "--stats")["files"]["entries"]
        types = {record["name"]: record["type"] for record in records}
        self.assertEqual(types[".directory-link"], "symlink")
        self.assertEqual(types["file-link"], "symlink")
        self.assertEqual(types["a"], "directory")
        visible = next(record for record in records
                       if record["name"] == "visible")
        self.assertTrue(stat.S_ISREG(visible["mode"]))

    def test_mother_core_scans_each_real_directory_once_and_opens_no_files(self):
        output = io.BytesIO()
        errors = io.StringIO()
        real_scandir = directory_tree.os.scandir
        real_open = directory_tree.os.open
        scans = []
        opened_flags = []

        def counted_scandir(target):
            scans.append(target)
            return real_scandir(target)

        def checked_open(path, flags, *args, **kwargs):
            opened_flags.append(flags)
            self.assertTrue(flags & os.O_DIRECTORY)
            return real_open(path, flags, *args, **kwargs)

        def writer_factory(write):
            return FileObjectWriter(write)

        with mock.patch.object(directory_tree.os, "scandir",
                               side_effect=counted_scandir), \
                mock.patch.object(directory_tree.os, "open",
                                  side_effect=checked_open):
            scanner = directory_tree.DirectoryTree(
                output, errors, file_writer_factory=writer_factory)
            status = scanner.run(self.temp)

        document = json.loads(output.getvalue().decode("ascii"))
        self.assertEqual(status, 0)
        self.assertTrue(document["complete"])
        self.assertEqual(len(scans), 3)
        self.assertEqual(len(opened_flags), 3)

    def test_missing_root_is_valid_incomplete_family_json(self):
        missing = os.path.join(self.temp, "missing")
        result = subprocess.run(
            [sys.executable, MOTHER, missing],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 1)
        document = json.loads(result.stdout.decode("ascii"))
        self.assertFalse(document["complete"])
        self.assertEqual(document["errors"], 1)
        self.assertEqual(document["tree"]["files"]["entries"], [])
        self.assertIn("error", document["tree"])


if __name__ == "__main__":
    unittest.main()
