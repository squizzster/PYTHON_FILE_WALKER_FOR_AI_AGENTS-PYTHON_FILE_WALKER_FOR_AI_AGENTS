import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(PROJECT_ROOT, "list_files_in_a_directory_to_json.py")


class FileListingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="file-listing-test-")
        with open(os.path.join(self.temp, "visible"), "wb") as stream:
            stream.write(b"content")
        with open(os.path.join(self.temp, ".hidden"), "wb"):
            pass
        os.mkdir(os.path.join(self.temp, "directory"))
        os.symlink("visible", os.path.join(self.temp, "symlink"))
        os.mkfifo(os.path.join(self.temp, "fifo"))

    def tearDown(self):
        shutil.rmtree(self.temp)

    def invoke(self, *options):
        return subprocess.run([sys.executable, SHIM] + list(options) + [self.temp],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def document(self, *options):
        result = self.invoke(*options)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        document = json.loads(result.stdout.decode("ascii"))
        self.assertEqual(document["complete"], True)
        self.assertEqual(document["errors"], 0)
        return document["files"]

    def test_default_lists_regular_files_including_hidden(self):
        files = self.document()
        self.assertEqual(files["mode"], "names")
        self.assertEqual(files["scope"], "regular-files")
        self.assertEqual(set(files["entries"]), {"visible", ".hidden"})

    def test_metadata_modes(self):
        inode_records = self.document("--inode")["entries"]
        self.assertTrue(all(set(record) == {"name", "inode"}
                            for record in inode_records))

        permission_records = self.document("--permissions")["entries"]
        visible = next(record for record in permission_records
                       if record["name"] == "visible")
        self.assertEqual(set(visible),
                         {"name", "mode", "permissions", "uid", "gid"})
        self.assertTrue(stat.S_ISREG(visible["mode"]))

        stats_records = self.document("--stats")["entries"]
        self.assertTrue(all(record["type"] == "file" for record in stats_records))
        self.assertTrue(all("inode" in record and "mtime_ns" in record
                            for record in stats_records))

    def test_all_entry_metadata_does_not_follow_symlinks(self):
        records = self.document("--all-entries", "--stats")["entries"]
        types = {record["name"]: record["type"] for record in records}
        self.assertEqual(types["directory"], "directory")
        self.assertEqual(types["symlink"], "symlink")
        self.assertEqual(types["fifo"], "fifo")

    def test_base64_preserves_arbitrary_filename_bytes(self):
        raw_name = b"raw-\xff"
        with open(os.fsencode(self.temp) + b"/" + raw_name, "wb"):
            pass
        records = self.document("--base64", "--inode")["entries"]
        self.assertIn(base64.b64encode(raw_name).decode("ascii"),
                      {record["name"] for record in records})

    def test_count_and_metadata_are_incompatible(self):
        count = self.document("--number")
        self.assertEqual(count["mode"], "count")
        self.assertEqual(count["count"], 2)
        result = self.invoke("--number", "--stats")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"cannot be combined", result.stderr)


if __name__ == "__main__":
    unittest.main()
