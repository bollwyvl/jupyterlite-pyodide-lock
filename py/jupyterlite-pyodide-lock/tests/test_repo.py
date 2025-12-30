"""Tests of repo versions, etc."""
# Copyright (c) jupyterlite-pyodide-lock contributors.
# Distributed under the terms of the BSD-3-Clause License.

from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from typing import TYPE_CHECKING

import pytest

from .conftest import PXT, ROOT, UTF8

if TYPE_CHECKING:
    from pathlib import Path

if not PXT.exists():
    pytest.skip("Not in a jupyterlite-pyodide-lock checkout", allow_module_level=True)

PIXI_PATTERNS = {
    ".github/workflows/test.yml": [r"JLPL_PIXI_VERSION: &pixi_version ([^\s]+)"],
    ".github/workflows/pages.yml": [r"JLPL_PIXI_VERSION: &pixi_version ([^\s]+)"],
    "docs/environment.yml": [r"""pixi ==([^\s"']+)"""],
    "CONTRIBUTING.md": [r"""pixi ==([^\s"']+)"""],
}

PY_PATTERNS = {
    "README.md": [
        r"""^\s+jupyterlite-pyodide-lock ==(.*)$""",
        r"""^\s+- jupyterlite-pyodide-lock-recommended ==(.*)$""",
    ],
    "py/*/pyproject.toml": [r"""version = "([^"]+)"""],
    "CHANGELOG.md": [
        r"""^## `([\d\.abcr]+?)`""",
        r"""^### `jupyterlite-pyodide-lock ([\d\.abcr]+?)`""",
        r"""^### `jupyterlite-pyodide-lock-webdriver ([\d\.abcr]+?)`""",
    ],
}


@pytest.mark.parametrize(("glob"), PIXI_PATTERNS.keys())
def test_repo_pixi_version(the_pixi_version: str, glob: str) -> None:
    """Verify consistent ``pixi`` versions."""
    _verify_patterns("pixi version", the_pixi_version, glob, PIXI_PATTERNS)


@pytest.mark.parametrize(("glob"), PY_PATTERNS.keys())
def test_repo_py_version(the_py_version: str, glob: str) -> None:
    """Verify consistent ``jupyterlite-pyodide-lock`` versions."""
    _verify_patterns("python version", the_py_version, glob, PY_PATTERNS)


@pytest.mark.parametrize(
    ("args"), [["jupyter-pyodide-lock"], ["jupyter", "pyodide-lock"]]
)
def test_repo_cli_version(args: list[str], the_py_version: str) -> None:
    """Verify the CLI returns the expected version."""
    cli = subprocess.check_output([*args, "--version"], **UTF8).strip()
    assert cli.endswith(the_py_version)


@pytest.mark.parametrize("pkg", ["jupyterlite-pyodide-kernel", "jupyterlite-core"])
def test_repo_upstream_versions(pkg: str) -> None:
    """Verify mentions of upstream versions are accurate."""
    readme = (ROOT / "README.md").read_text(**UTF8)
    readme_pattern = rf"{pkg} ==([\d\.]+)"
    versions = sorted(set(re.findall(readme_pattern, readme)))
    assert len(versions) == 1
    version = re.escape([*versions][0])

    lock = (PXT.parent / "pixi.lock").read_text(**UTF8)
    lock_pattern = rf"""/{pkg}-{version}-.*?\.conda"""
    packages = sorted(set(re.findall(lock_pattern, lock)))
    assert packages, f"{pkg} {version} not found"


def _verify_patterns(
    what: str, version: str, glob: str, patterns: dict[str, list[str]]
) -> None:
    """Verify some versions against glob patterns."""
    paths = sorted(ROOT.glob(glob))
    assert paths, f"no paths matched {glob}"
    fails: dict[Path, list[str]] = defaultdict(list)

    for path in paths:
        text = path.read_text(**UTF8)
        print(text)
        for pattern in patterns[glob]:
            matches = re.findall(pattern, text, flags=re.MULTILINE)
            if path.name == "CHANGELOG.md":
                matches = matches[:1]
            if {*matches} != {version}:
                fails[path].append(f" - missing {what} {version} [{pattern}]")

    if fails:
        for path, path_fails in fails.items():
            print(path, file=sys.stderr)
            print("\n".join(path_fails), file=sys.stderr)

    assert not fails, "some versions don't match"
