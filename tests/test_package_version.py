from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path

from nothing_here import __version__


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "package_version.py"
    spec = importlib.util.spec_from_file_location("package_version", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackageVersionTests(unittest.TestCase):
    def test_local_script_reads_init(self) -> None:
        module = _load()
        old_type = os.environ.pop("GITHUB_REF_TYPE", None)
        old_name = os.environ.pop("GITHUB_REF_NAME", None)
        try:
            self.assertEqual(module.package_version(), __version__)
        finally:
            if old_type is not None:
                os.environ["GITHUB_REF_TYPE"] = old_type
            if old_name is not None:
                os.environ["GITHUB_REF_NAME"] = old_name

    def test_tag_build_uses_the_tag(self) -> None:
        module = _load()
        old_type = os.environ.get("GITHUB_REF_TYPE")
        old_name = os.environ.get("GITHUB_REF_NAME")
        os.environ["GITHUB_REF_TYPE"] = "tag"
        os.environ["GITHUB_REF_NAME"] = "v0.5.4"
        try:
            self.assertEqual(module.package_version(), "0.5.4")
            self.assertEqual(module.version_from_tag("v1.2.0"), "1.2.0")
        finally:
            if old_type is None:
                os.environ.pop("GITHUB_REF_TYPE", None)
            else:
                os.environ["GITHUB_REF_TYPE"] = old_type
            if old_name is None:
                os.environ.pop("GITHUB_REF_NAME", None)
            else:
                os.environ["GITHUB_REF_NAME"] = old_name


if __name__ == "__main__":
    unittest.main()
