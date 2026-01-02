"""Tests of the ``jupyter-lite`` CLI with ``jupyterlite-pyodide-lock-webdriver``."""
# Copyright (c) jupyterlite-pyodide-lock contributors.
# Distributed under the terms of the BSD-3-Clause License.

from __future__ import annotations

from typing import TYPE_CHECKING

import pyodide_lock
from jupyterlite_core.constants import UTF8
from jupyterlite_pyodide_kernel.constants import PYODIDE_LOCK

from .conftest import expect_no_diff

if TYPE_CHECKING:
    from pathlib import Path

    from .conftest import LiteRunner


def test_cli_good_build(lite_cli: LiteRunner, a_lite_config_with_widgets: Path) -> None:
    """Verify a build works, twice."""
    from jupyterlite_pyodide_lock.constants import PYODIDE_LOCK_STEM

    a_lite_dir = a_lite_config_with_widgets.parent
    out = a_lite_dir / "_output"
    lock_dir = out / "static" / PYODIDE_LOCK_STEM
    lock = lock_dir / PYODIDE_LOCK

    lite_cli("build", "--debug")
    lock_text = lock.read_text(**UTF8)

    # this would fail pydantic
    pyodide_lock.PyodideLockSpec.from_json(lock)

    lite_cli("build", "--debug")
    relock_text = lock.read_text(**UTF8)

    return expect_no_diff(lock_text, relock_text, "build", "rebuild")
