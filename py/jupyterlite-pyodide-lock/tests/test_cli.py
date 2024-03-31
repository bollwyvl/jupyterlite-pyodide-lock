"""Tests of the `jupyter-lite` CLI with `jupyterlite-pyodide-lock`."""

import difflib
import json
import pprint
from pathlib import Path

import pyodide_lock
import pytest
from jupyterlite_core.constants import JSON_FMT, UTF8
from jupyterlite_pyodide_kernel.constants import PYODIDE_LOCK

MESSAGES = {
    "not-a-locker": (
        "The 'locker' trait of a PyodideLockAddon instance expected any of"
        " ['browser'], not the str 'not-a-locker'."
    ),
}


@pytest.mark.parametrize(["args"], [(["--pyodide-lock"],), ([],)])
def test_cli_status(lite_cli, args):
    """Verify various status invocations work."""
    from jupyterlite_pyodide_lock import __version__

    status = lite_cli("status", *args)
    assert status.success
    ours = status.stdout.split("status:pyodide-lock:lock")[1]
    assert __version__ in ours


@pytest.mark.parametrize(
    ["bad_config", "message"],
    [({"locker": "not-a-locker"}, "not-a-locker")],
)
def test_cli_bad_config(
    lite_cli, a_lite_config: Path, bad_config, message: str
) -> None:
    config = json.load(a_lite_config.open())
    config["PyodideLockAddon"].update(bad_config)
    pprint.pprint(config)
    json.dump(config, a_lite_config.open("w"))
    status = lite_cli("status")
    assert MESSAGES[message] in status.stderr


def test_cli_good_build(
    lite_cli, a_lite_dir: Path, a_lite_config_with_widgets: Path
) -> None:
    """Verify a build works, twice."""
    from jupyterlite_pyodide_lock.constants import PYODIDE_LOCK_STEM

    build = lite_cli("build", "--debug")
    assert build.success
    out = a_lite_dir / "_output"
    assert out.exists()
    lock_dir = out / "static" / PYODIDE_LOCK_STEM
    assert lock_dir.exists()
    lock = lock_dir / PYODIDE_LOCK
    lock_text = lock.read_text(**UTF8)
    pyodide_lock.PyodideLockSpec.from_json(lock)

    rebuild = lite_cli("build", "--debug")
    assert rebuild.success
    relock_text = lock.read_text(**UTF8)
    diff = [
        *difflib.unified_diff(
            lock_text.splitlines(), relock_text.splitlines(), "build", "rebuild"
        )
    ]
    print("\n".join(diff))
    assert not diff, "didn't see same lockfile on rebuild"


def test_cli_bad_build(lite_cli, a_lite_config: Path):
    """Verify an impossible solve fails."""
    a_lite_config.write_text(
        json.dumps(
            {"PyodideLockAddon": {"enabled": True, "specs": ["pytorch"]}}, **JSON_FMT
        ),
        **UTF8,
    )
    build = lite_cli("build", "--debug")
    assert not build.success
