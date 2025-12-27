"""Locker implementation ``jupyterlite-pyodide-lock-uv``."""
# Copyright (c) jupyterlite-pyodide-lock contributors.
# Distributed under the terms of the BSD-3-Clause License.

from __future__ import annotations

import json
import re
import subprocess  # noqa: S404
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyodide_lock import PyodideLockSpec
from pyodide_lock.utils import add_wheels_to_spec

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import pkginfo
from jupyterlite_core.constants import JSON_FMT, UTF8
from jupyterlite_core.trait_types import TypedTuple
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from psutil import Popen
from traitlets import Unicode, default

from jupyterlite_pyodide_lock.constants import (
    PYODIDE_LOCK,
    PYODIDE_LOCK_STEM,
    RE_REMOTE_URL,
)
from jupyterlite_pyodide_lock.lockers._base import BaseLocker  # noqa: PLC2701
from jupyterlite_pyodide_lock.utils import find_binary

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pyodide_lock import PackageSpec


class UvLocker(BaseLocker):
    """A locker that uses ``uv pip compile``."""

    uv_bin: str = Unicode(help="a custom executable for ``uv``").tag(config=True)
    uv_platform: str = Unicode(
        "wasm32-pyodide2024", help="the ``uv`` python platform"
    ).tag(config=True)
    uv_pip_compile_args: tuple[str] = TypedTuple(
        Unicode(),
        default_value=["--format=pylock.toml", "--no-build"],
        help="arguments to ``uv pip compile``",
    ).tag(config=True)
    uv_python_version: str = Unicode(
        allow_none=True, help="the ``uv`` python version"
    ).tag(config=True)
    extra_uv_pip_compile_args: tuple[str] = TypedTuple(
        Unicode(),
        help=("extra arguments to ``uv pip compile``, such as ``--default-index``"),
    ).tag(config=True)

    # trait defaults
    @default("uv_bin")
    def _default_uv_bin(self) -> str:
        return f"""{find_binary(["uv"])[0]}"""

    @default("uv_python_version")
    def _default_uv_python_version(self) -> str | None:
        lockfile = self.parent.pyodide_addon.output_pyodide / PYODIDE_LOCK
        if lockfile.exists():
            lock = json.loads(lockfile.read_text(**UTF8))
            return f"""{lock["info"]["python"]}"""
        return None

    # locker API
    async def resolve(self) -> bool:
        """Get the lock."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        reqs = self.build_requirements_txt()
        self.build_constraints_txt(reqs)
        self.run_pip_compile()
        self.build_pyodide_lock()
        return True

    def build_requirements_txt(self) -> dict[str, str]:
        """Combine all requirements."""
        lines: dict[str, str] = {}

        for spec in sorted(self.specs):
            req = Requirement(spec)
            lines[canonicalize_name(req.name)] = spec

        for wheel in sorted(self.packages):
            lines.update(self.build_one_package_requirement(wheel))

        self.requirements_in.write_text("\n".join(sorted(lines.values())), **UTF8)
        return lines

    def build_constraints_txt(self, requirements: dict[str, str]) -> None:
        """Combine all constraints."""
        out_dir = self.parent.pyodide_addon.output_pyodide
        bootstrap_lock = PyodideLockSpec.from_json(out_dir / PYODIDE_LOCK)

        package_specs: dict[str, str] = {}

        for pkg in bootstrap_lock.packages.values():
            package_specs.update(
                self.build_one_constraint_from_pyodide_lock(pkg, requirements)
            )

        for constraint in self.constraints:
            req = Requirement(constraint)
            name = canonicalize_name(req.name)
            package_specs[name] = constraint

        self.constraints_txt.write_text(
            "\n".join(sorted(package_specs.values())), **UTF8
        )

    def build_one_constraint_from_pyodide_lock(
        self, pkg: PackageSpec, requirements: dict[str, str]
    ) -> dict[str, str]:
        """Build a PEP-508 ``@`` constraint from a ``pyodide-lock.json`` package."""
        if pkg.package_type != "package":
            return {}
        out_dir = self.parent.pyodide_addon.output_pyodide
        cdn = self.parent.pyodide_cdn_url
        name, file_name = canonicalize_name(pkg.name), pkg.file_name
        wheel = out_dir / file_name
        if wheel.exists():
            url = wheel.as_uri()
        elif re.match(RE_REMOTE_URL, file_name):
            url = file_name
        else:
            url = f"""{cdn}/{file_name}"""
        spec = f"{name} @ {url}"
        required = requirements.get(name)
        if required:
            self.log.debug(
                "[uv] [constraints] [%s] skipping required %s", name, required
            )
            spec = "\n".join([
                f"# {name} already required by: {required}",
                f"# {spec}",
            ])
        return {name: spec}

    def run_pip_compile(self) -> None:
        """Run a constrained ``uv pip compile``."""
        args = [*self.all_uv_pip_compile_args]
        self.log.debug("[uv] [compile] %s", "\t".join(args))
        proc = Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = proc.communicate()
        if proc.returncode != 0:
            self.log.error("[uv] [compile] error %s: %s", proc.returncode, out)

    def build_pyodide_lock(self) -> None:
        """Update ``{out_dir}/pyodide-lock/pyodide-lock.json`` from wheels."""
        lockfile = self.parent.lockfile
        lock_dir = lockfile.parent

        pylock = tomllib.loads(self.pylock.read_text(**UTF8))
        wheels: list[Path] = []

        for pkg in pylock["packages"]:
            wheels += [*self.collect_pylock_wheel(pkg)]

        self.log.debug("[uv] [lock] collected wheels: %s", [w.name for w in wheels])

        lock_json = self.build_tmp_pyodide_lock(
            self.parent.pyodide_addon.output_pyodide / PYODIDE_LOCK, wheels
        )

        lock_dir.mkdir(parents=True, exist_ok=True)
        root_path = self.parent.manager.output_dir.as_posix()

        found = {wheel.name: wheel for wheel in wheels}
        for package in lock_json["packages"].values():
            self.fix_one_tmp_pyodide_lock_package(root_path, lock_dir, package, found)

        lockfile.write_text(json.dumps(lock_json, **JSON_FMT), **UTF8)

    def build_tmp_pyodide_lock(
        self, old_lockfile: Path, wheels: list[Path]
    ) -> dict[str, Any]:
        """Use local wheels to make a patched ``pyodide-lock.json``."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            tmp_lock = tdp / PYODIDE_LOCK
            self.parent.copy_one(old_lockfile, tdp / PYODIDE_LOCK)
            [
                self.parent.copy_one(path, tdp / path.name)
                for path in sorted(set(wheels))
            ]
            spec = PyodideLockSpec.from_json(tdp / PYODIDE_LOCK)
            spec = add_wheels_to_spec(spec, [*tdp.glob("*.whl")])
            spec.to_json(tmp_lock)
            return {**json.loads(tmp_lock.read_text(**UTF8))}

    def fix_one_tmp_pyodide_lock_package(
        self,
        root_posix: str,
        lock_dir: Path,
        package: dict[str, Any],
        found_wheels: dict[str, Path],
    ) -> None:
        """Update a ``pyodide-lock`` URL for deployment."""
        file_name = package["file_name"]
        just_file_name = file_name.rsplit("/")[-1]
        new_file_name = file_name
        found_path = found_wheels.get(just_file_name)

        if found_path:
            path_posix = found_path.as_posix()
            if path_posix.startswith(root_posix):
                # build relative path to existing file
                new_file_name = found_path.as_posix().replace(root_posix, "../..")
            else:
                # copy to be sibling of lockfile, leaving name unchanged
                dest = lock_dir / file_name
                self.parent.copy_one(found_path, dest)
                new_file_name = f"../../static/{PYODIDE_LOCK_STEM}/{file_name}"
        else:
            new_file_name = f"{self.parent.pyodide_cdn_url}/{just_file_name}"

        package["file_name"] = new_file_name

    def collect_pylock_wheel(self, pkg: dict[str, Any]) -> Iterator[Path]:
        """Ensure a local wheel from a PEP-751 package."""
        archive: dict[str, Any] | None = pkg.get("archive")
        wheels: list[dict[str, Any]] | None = pkg.get("wheels")
        raw_url: str | None = None
        dest: Path | None = None

        if archive:
            raw_url = archive.get("url")
            raw_path = archive.get("path")
            if raw_url and raw_url.startswith(self.parent.pyodide_cdn_url):
                return

            if raw_path:
                rel = (self.pylock.parent / raw_path).resolve()
                if rel.exists():
                    self.log.debug("[uv] [%s] is local", pkg["name"])
                    dest = rel
        elif wheels:
            wheel = wheels[0]
            raw_url = f"""{wheel["url"]}"""

        if not dest and raw_url:
            url = urllib.parse.urlparse(raw_url)
            wheel_name = f"""{url.path.split("/")[-1]}"""
            dest = self.parent.package_cache / wheel_name

            if dest.exists():
                self.log.debug("[uv] [%s] already cached: %s", pkg["name"], dest)
            else:
                self.log.debug("[uv] [%s] downloading: %s", pkg["name"], dest)
                self.parent.fetch_one(raw_url, dest)

        if dest and dest.exists():
            self.log.debug("[uv] [%s] will be locked: %s", pkg["name"], dest.name)
            yield dest

    def build_one_package_requirement(self, wheel: Path) -> dict[str, str]:
        """Build a ``package @ file://url`` spec for an on-disk wheel."""
        info = pkginfo.get_metadata(f"{wheel}")
        name = info and info.name
        if not name:  # pragma: no cover
            self.log.error("[uv] failed to parse wheel metadata for %s", wheel)
            return {}
        name = canonicalize_name(name)
        return {name: f"{name} @ {wheel.absolute().as_uri()}"}

    # derived properties
    @property
    def cache_dir(self) -> Path:
        """The location of cached files discovered during the solve."""
        return Path(self.parent.manager.cache_dir / "uv-locker")

    @property
    def requirements_in(self) -> Path:
        """The a temporary ``requirements.in`` to solve."""
        return Path(self.cache_dir / "requirements.in")

    @property
    def pylock(self) -> Path:
        """A temporary ``pylock.toml``."""
        return Path(self.cache_dir / "pylock.toml")

    @property
    def constraints_txt(self) -> Path:
        """A temporary ``constraints.txt``."""
        return Path(self.cache_dir / "constraints.txt")

    @property
    def lockfile_cache(self) -> Path:
        """The location of the updated lockfile."""
        return Path(self.cache_dir / PYODIDE_LOCK)

    @property
    def all_uv_pip_compile_args(self) -> list[str]:
        """All args for ``uv pip compile``."""
        py_ver = self.uv_python_version
        args = [
            self.uv_bin,
            "pip",
            "compile",
            f"--python-platform={self.uv_platform}",
            f"--output-file={self.pylock}",
            f"--constraints={self.constraints_txt}",
            *([] if not py_ver else [f"--python-version={py_ver}"]),
            *self.uv_pip_compile_args,
            *self.extra_uv_pip_compile_args,
        ]

        if self.parent.lock_date_epoch:
            rfc339 = datetime.fromtimestamp(
                self.parent.lock_date_epoch, timezone.utc
            ).isoformat()
            args += [f"--exclude-newer={rfc339}"]

        return [
            *args,
            f"{self.requirements_in}",
        ]
