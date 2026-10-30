from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from nothing_here import __version__


class PackageVersionTests(unittest.TestCase):
    def test_release_script_reads_the_same_version(self) -> None:
        path = Path(__file__).resolve().parents[1] / "scripts" / "package_version.py"
        spec = importlib.util.spec_from_file_location("package_version", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.package_version(), __version__)


if __name__ == "__main__":
    unittest.main()
