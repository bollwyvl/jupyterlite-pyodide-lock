"""Tests of the ``jupyter-lite`` CLI with ``jupyterlite-pyodide-lock``."""
# Copyright (c) jupyterlite-pyodide-lock contributors.
# Distributed under the terms of the BSD-3-Clause License.

from __future__ import annotations

import json
import re
import subprocess
from typing import TYPE_CHECKING, Any

import pyodide_lock
import pytest
from jupyterlite_core.constants import UTF8
from jupyterlite_pyodide_kernel.constants import PYODIDE_LOCK

from jupyterlite_pyodide_lock.constants import ENV_VAR_LOCK_DATE_EPOCH

from .conftest import (
    CUSTOM_EXPECT_RUNNABLE,
    EXPECT_WIDGETS_RUN,
    WIDGETS_WHEEL,
    expect_no_diff,
    patch_config,
)

if TYPE_CHECKING:
    from pathlib import Path

    from .conftest import LiteRunner

MESSAGES = {
    "not-a-locker": (
        "The 'locker' trait of a PyodideLockAddon instance expected any of"
    ),
    "cant-find-wheel": "Can't find a pure python wheel",
}


@pytest.mark.parametrize("args", [[], ["--json"], ["--check"], ["--check", "--json"]])
def test_cli_self_browsers(args: list[str]) -> None:
    """Verify the browser check CLI works."""
    out = subprocess.check_output(["jupyter-pyodide-lock", "browsers", *args], **UTF8)
    if "--json" in args:
        out_json = json.loads(out)
        expected = {"status", "ok", "search_path", "browsers"}
        assert set(out_json.keys()) == expected


@pytest.mark.parametrize("args", [[]])
def test_cli_status(lite_cli: LiteRunner, args: list[str]) -> None:
    """Verify various status invocations work."""
    from jupyterlite_pyodide_lock import __version__

    lite_cli(*["status", *args], expect_text=__version__)


@pytest.mark.parametrize(
    ("bad_config", "message"),
    [({"locker": "not-a-locker"}, "not-a-locker")],
)
def test_cli_bad_config(
    lite_cli: LiteRunner,
    a_lite_config: Path,
    bad_config: dict[str, Any],
    message: str,
) -> None:
    """Verify bad configs are caught."""
    patch_config(a_lite_config, PyodideLockAddon=bad_config)
    lite_cli("status", expect_rc=2, expect_text=MESSAGES[message])


def test_cli_good_build(
    lite_cli: LiteRunner,
    a_widget_approach: str,
    a_lite_config_with_widgets: Path,
) -> None:
    """Verify a build works, twice."""
    from jupyterlite_pyodide_lock.constants import (
        PYODIDE_LOCK_OFFLINE,
        PYODIDE_LOCK_STEM,
    )

    a_lite_dir = a_lite_config_with_widgets.parent
    out = a_lite_dir / "_output"
    lock_dir = out / "static" / PYODIDE_LOCK_STEM
    lock = lock_dir / PYODIDE_LOCK
    lock_offline = lock_dir / PYODIDE_LOCK_OFFLINE

    lite_cli("build", "--debug")
    lock_text = lock.read_text(**UTF8)

    matches = re.findall(re.escape(WIDGETS_WHEEL), lock_text)
    assert matches, f"{WIDGETS_WHEEL} does not appear in lock text"

    # this would fail pydantic
    pyodide_lock.PyodideLockSpec.from_json(lock)

    lite_cli("build", "--debug")
    relock_text = lock.read_text(**UTF8)

    expect_no_diff(lock_text, relock_text, "build", "rebuild")

    patch_config(
        a_lite_config_with_widgets,
        PyodideLockOfflineAddon={"enabled": True, "extra_includes": ["ipywidgets"]},
    )
    lite_cli("build", "--debug")
    pyodide_lock.PyodideLockSpec.from_json(lock_offline)
    offline_text = lock_offline.read_text(**UTF8)
    assert "https://" in offline_text

    patch_config(
        a_lite_config_with_widgets,
        PyodideLockOfflineAddon={"prune": True},
    )
    # only test pruned, offline in browser, as we'll have everything locally
    expect_runnable = CUSTOM_EXPECT_RUNNABLE.get(a_widget_approach, EXPECT_WIDGETS_RUN)
    lite_cli("build", "--debug", expect_runnable=expect_runnable)
    pyodide_lock.PyodideLockSpec.from_json(lock_offline)
    pruned_text = lock_offline.read_text(**UTF8)
    assert "https://" not in pruned_text


def test_cli_bad_build(lite_cli: LiteRunner, a_lite_config: Path) -> None:
    """Verify an impossible package solve fails."""
    patch_config(a_lite_config, PyodideLockAddon={"enabled": True, "specs": ["torch"]})
    lite_cli("build", "--debug", expect_rc=1)


def test_cli_lock_date_epoch(
    lite_cli: LiteRunner,
    a_widget_approach: str,
    a_lite_config_with_widgets: Path,
    a_bad_widget_lock_date_epoch: int,
    a_good_widget_lock_date_epoch: int,
) -> None:
    """Verify a lock clamped by good environment variable, failed by bad config."""
    if a_widget_approach != "specs_pep508":
        pytest.skip(f"{ENV_VAR_LOCK_DATE_EPOCH} does not affect {a_widget_approach}")

    good_env = {ENV_VAR_LOCK_DATE_EPOCH: str(a_good_widget_lock_date_epoch)}
    lite_cli("build", "--debug", env=good_env)

    patch_config(
        a_lite_config_with_widgets,
        PyodideLockAddon=dict(lock_date_epoch=a_bad_widget_lock_date_epoch),
    )
    lite_cli("build", "--debug", expect_rc=1)


def test_cli_patches(lite_cli: LiteRunner, a_lite_config: Path) -> None:
    """Verify patch behavior."""
    from jupyterlite_pyodide_lock.constants import PYODIDE_LOCK_STEM

    wnbe = "widgetsnbextension"
    ipyw = "ipywidgets"

    patch_config(
        a_lite_config,
        PyodideLockAddon={
            "specs": [f"{ipyw} <8.1"],
            "patch_lock_fragment": {"packages": {wnbe: None}},
            "package_depends_remove": {ipyw: [wnbe]},
        },
    )
    out = a_lite_config.parent / "_output"
    lite_cli("build", "--debug")
    lock_dir = out / "static" / PYODIDE_LOCK_STEM
    lock = lock_dir / PYODIDE_LOCK
    lock_text = lock.read_text(**UTF8)
    lock_json = json.loads(lock_text)
    packages = lock_json["packages"]
    assert wnbe not in packages
    assert wnbe not in packages[ipyw]["depends"]
