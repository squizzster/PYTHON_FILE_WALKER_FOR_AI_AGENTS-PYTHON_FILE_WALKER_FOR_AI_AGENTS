import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(PROJECT_ROOT, "list_files_in_a_directory_to_json.py")
COMPANION_SHIM = os.path.join(PROJECT_ROOT, "python_file_walker_for_ai_agents.py")
PACKAGE_MODULE = os.path.join(
    PROJECT_ROOT, "src", "python_file_walker_for_ai_agents", "file_listing.py")


class RelocatableFileListingShimTests(unittest.TestCase):
    def assert_help(self, shim, cwd, flag="--help"):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        result = subprocess.run([sys.executable, shim, flag], cwd=cwd,
                                env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        document = json.loads(result.stderr.decode("ascii"))
        self.assertEqual(document["usage"],
                         "list_files_in_a_directory_to_json.py [OPTIONS] DIRECTORY")
        self.assertEqual(document["envelope"],
                         {"files": "object", "complete": "boolean", "errors": "integer"})
        self.assertIn("--stats", document["returns"])

    def test_source_shim_works_from_another_directory(self):
        with tempfile.TemporaryDirectory(prefix="file-shim-cwd-") as temp:
            for flag in ("-h", "--help", "-help"):
                self.assert_help(SHIM, temp, flag)

    def test_no_directory_emits_json_help_with_usage_exit(self):
        with tempfile.TemporaryDirectory(prefix="file-shim-noarg-") as temp:
            result = subprocess.run([sys.executable, SHIM], cwd=temp,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            document = json.loads(result.stderr.decode("ascii"))
            self.assertEqual(document["usage"],
                             "list_files_in_a_directory_to_json.py [OPTIONS] DIRECTORY")

    def test_symlinked_shim_resolves_adjacent_source_package(self):
        with tempfile.TemporaryDirectory(prefix="file-shim-link-") as temp:
            link = os.path.join(temp, "list_files_in_a_directory_to_json.py")
            os.symlink(SHIM, link)
            self.assert_help(link, temp)

    def test_copied_shim_ignores_companion_shim_and_imports_installed_package(self):
        with tempfile.TemporaryDirectory(prefix="file-shim-copy-") as temp:
            copied = os.path.join(temp, "list_files_in_a_directory_to_json.py")
            shutil.copy2(SHIM, copied)
            shutil.copy2(COMPANION_SHIM, temp)
            self.assert_help(copied, temp)

    def test_copied_shim_reports_missing_package_without_traceback(self):
        with tempfile.TemporaryDirectory(prefix="file-shim-missing-") as temp:
            copied = os.path.join(temp, "list_files_in_a_directory_to_json.py")
            shutil.copy2(SHIM, copied)
            result = subprocess.run([sys.executable, "-S", copied, "--help"],
                                    cwd=temp, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(
                result.stderr,
                b"python_file_walker_for_ai_agents.file_listing is not installed\n")

    def test_runtime_files_use_python35_grammar(self):
        for path in (SHIM, PACKAGE_MODULE):
            with open(path, "r") as source:
                text = source.read()
            if sys.version_info >= (3, 8):
                ast.parse(text, filename=path, feature_version=(3, 5))
            else:
                ast.parse(text, filename=path)


if __name__ == "__main__":
    unittest.main()
