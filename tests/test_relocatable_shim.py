import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(PROJECT_ROOT, "python_file_walker_for_ai_agents.py")
SOURCE_ROOT = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, SOURCE_ROOT)

from python_file_walker_for_ai_agents import directory_tree


class RelocatableShimTests(unittest.TestCase):
    def test_python35_is_the_runtime_and_package_minimum(self):
        self.assertEqual(directory_tree.MINIMUM_PYTHON, (3, 5))
        with open(os.path.join(PROJECT_ROOT, "pyproject.toml"), "r") as source:
            metadata = source.read()
        self.assertIn('requires-python = ">=3.5"', metadata)

    def assert_help(self, shim, cwd):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        result = subprocess.run([sys.executable, shim, "--help"], cwd=cwd,
                                env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        help_document = json.loads(result.stderr.decode("ascii"))
        self.assertEqual(help_document["usage"],
                         "python_file_walker_for_ai_agents.py LOCATION")

    def test_source_shim_works_from_another_directory(self):
        with tempfile.TemporaryDirectory(prefix="walker-shim-cwd-") as temp:
            self.assert_help(SHIM, temp)

    def test_symlinked_shim_resolves_adjacent_source_package(self):
        with tempfile.TemporaryDirectory(prefix="walker-shim-link-") as temp:
            link = os.path.join(temp, "python_file_walker_for_ai_agents.py")
            os.symlink(SHIM, link)
            self.assert_help(link, temp)

    def test_copied_shim_imports_installed_package_without_self_shadowing(self):
        with tempfile.TemporaryDirectory(prefix="walker-shim-copy-") as temp:
            copied = os.path.join(temp, "python_file_walker_for_ai_agents.py")
            shutil.copy2(SHIM, copied)
            self.assert_help(copied, temp)

    def test_copied_shim_reports_missing_package_without_traceback(self):
        with tempfile.TemporaryDirectory(prefix="walker-shim-missing-") as temp:
            copied = os.path.join(temp, "python_file_walker_for_ai_agents.py")
            shutil.copy2(SHIM, copied)
            result = subprocess.run([sys.executable, "-S", copied, "--help"],
                                    cwd=temp, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(
                result.stderr,
                b"python_file_walker_for_ai_agents package is not installed\n")


if __name__ == "__main__":
    unittest.main()
