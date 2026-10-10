import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(
    PROJECT_ROOT, "list_files_in_a_directory_tree_to_json.py")
PACKAGE_FILES = (
    os.path.join(PROJECT_ROOT, "src", "python_file_walker_for_ai_agents",
                 "filesystem.py"),
    os.path.join(PROJECT_ROOT, "src", "python_file_walker_for_ai_agents",
                 "file_entries.py"),
    os.path.join(PROJECT_ROOT, "src", "python_file_walker_for_ai_agents",
                 "recursive_file_listing.py"),
)


class RelocatableRecursiveFileListingShimTests(unittest.TestCase):
    def assert_help(self, shim, cwd, flag="--help"):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, shim, flag], cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        document = json.loads(result.stderr.decode("ascii"))
        self.assertEqual(
            document["usage"],
            "list_files_in_a_directory_tree_to_json.py [OPTIONS] DIRECTORY",
        )
        self.assertEqual(set(document["options"]), {
            "--all-entries", "--base64", "--inode", "--permissions",
            "--stats", "--number",
        })

    def test_source_and_symlinked_shims_work_from_elsewhere(self):
        with tempfile.TemporaryDirectory(prefix="mother-shim-cwd-") as temp:
            for flag in ("-h", "--help", "-help"):
                self.assert_help(SHIM, temp, flag)
            linked = os.path.join(
                temp, "list_files_in_a_directory_tree_to_json.py")
            os.symlink(SHIM, linked)
            self.assert_help(linked, temp)

    def test_no_directory_emits_compact_json_help(self):
        with tempfile.TemporaryDirectory(prefix="mother-shim-noarg-") as temp:
            result = subprocess.run(
                [sys.executable, SHIM], cwd=temp,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            document = json.loads(result.stderr.decode("ascii"))
            self.assertEqual(
                document["usage"],
                "list_files_in_a_directory_tree_to_json.py [OPTIONS] DIRECTORY",
            )

    def test_incompatible_sister_options_return_mother_help(self):
        with tempfile.TemporaryDirectory(prefix="mother-shim-options-") as temp:
            result = subprocess.run(
                [sys.executable, SHIM, "--number", "--stats", temp],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            document = json.loads(result.stderr.decode("ascii"))
            self.assertIn("cannot be combined", document["error"])
            self.assertEqual(
                document["help"]["usage"],
                "list_files_in_a_directory_tree_to_json.py [OPTIONS] DIRECTORY",
            )

    def test_copied_shim_imports_installed_package(self):
        with tempfile.TemporaryDirectory(prefix="mother-shim-copy-") as temp:
            copied = os.path.join(
                temp, "list_files_in_a_directory_tree_to_json.py")
            shutil.copy2(SHIM, copied)
            self.assert_help(copied, temp)

    def test_copied_shim_reports_missing_package_without_traceback(self):
        with tempfile.TemporaryDirectory(prefix="mother-shim-missing-") as temp:
            copied = os.path.join(
                temp, "list_files_in_a_directory_tree_to_json.py")
            shutil.copy2(SHIM, copied)
            result = subprocess.run(
                [sys.executable, "-S", copied, "--help"], cwd=temp,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(
                result.stderr,
                b"python_file_walker_for_ai_agents.recursive_file_listing is not installed\n",
            )

    def test_new_runtime_files_use_python35_grammar(self):
        for path in (SHIM,) + PACKAGE_FILES:
            with open(path, "r") as source:
                text = source.read()
            if sys.version_info >= (3, 8):
                ast.parse(text, filename=path, feature_version=(3, 5))
            else:
                ast.parse(text, filename=path)


if __name__ == "__main__":
    unittest.main()
