"""Tests of the ``jupyter-lite`` CLI with ``jupyterlite-pyodide-lock-uv``."""
# Copyright (c) jupyterlite-pyodide-lock contributors.
# Distributed under the terms of the BSD-3-Clause License.

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pyodide_lock
from jupyterlite_core.constants import UTF8
from jupyterlite_pyodide_kernel.constants import PYODIDE_LOCK

from .conftest import expect_no_diff, patch_config

if TYPE_CHECKING:
    from pathlib import Path

    from .conftest import LiteRunner


def test_cli_good_build(lite_cli: LiteRunner, a_lite_config_with_widgets: Path) -> None:
    """Verify a build works, twice."""
    from jupyterlite_pyodide_lock.constants import PYODIDE_LOCK_STEM

    wnbe = "widgetsnbextension"
    ipyw = "ipywidgets"

    patch_config(
        a_lite_config_with_widgets,
        PyodideLockAddon={
            "patch_lock_fragment": {"packages": {wnbe: None}},
            "package_depends_remove": {ipyw: [wnbe]},
        },
        UvLocker={"exclude_specs": ["nbclient"]},
    )

    a_lite_dir = a_lite_config_with_widgets.parent
    out = a_lite_dir / "_output"
    lock_dir = out / "static" / PYODIDE_LOCK_STEM
    lock = lock_dir / PYODIDE_LOCK

    lite_cli("build", "--debug")
    lock_text = lock.read_text(**UTF8)
    lock_json = json.loads(lock_text)
    packages = lock_json["packages"]
    assert wnbe not in packages
    assert wnbe not in packages[ipyw]["depends"]

    # this would fail pydantic
    pyodide_lock.PyodideLockSpec.from_json(lock)

    lite_cli("build", "--debug")
    relock_text = lock.read_text(**UTF8)

    return expect_no_diff(lock_text, relock_text, "build", "rebuild")
