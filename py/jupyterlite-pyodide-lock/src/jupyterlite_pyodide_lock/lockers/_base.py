import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Union as _Union

from jupyterlite_pyodide_kernel.constants import PYODIDE_VERSION
from traitlets import Dict, Instance, Int, List, Unicode
from traitlets.config import LoggingConfigurable

from ..constants import FILES_PYTHON_HOSTED

if TYPE_CHECKING:
    from ..addons.lock import PyodideLockAddon


class BaseLocker(LoggingConfigurable):
    """Common traits and methods for `pyodide-lock.json` resolving strategies."""

    # configurables
    extra_micropip_args = Dict(help="options for `micropip.install`").tag(config=True)
    pyodide_cdn_url = Unicode(
        f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full",
        help="remote URL for the version of a full pyodide distribution",
    ).tag(config=True)
    pypi_api_url = Unicode(
        "https://pypi.org/pypi", help="remote URL for a Warehouse-compatible JSON API"
    ).tag(config=True)
    pythonhosted_cdn_url = Unicode(
        FILES_PYTHON_HOSTED,
        help="remote URL for python packages (third-party not supported)",
    )

    timeout = Int(30, help="seconds to wait for a solve").tag(config=True)

    # from parent
    specs = List(Unicode())
    packages = List(Instance(Path))
    lockfile = Instance(Path)

    # runtime
    parent: "PyodideLockAddon" = Instance(
        "jupyterlite_pyodide_lock.addons.lock.PyodideLockAddon"
    )
    micropip_args = Dict()

    # API methods
    def resolve_sync(self) -> _Union[bool, None]:
        """A synchronous facade for doing async solves, called by `PyodideLockAddon`.

        If a locker is entirely synchronous, it can overload this.
        """
        loop = asyncio.get_event_loop()
        future = self.resolve_async()
        return loop.run_until_complete(future)

    async def resolve_async(self) -> _Union[bool, None]:
        """Asynchronous solve that handles timeout.

        An async locker should _not_ overload this unless it has some other means
        of timing out.
        """
        try:
            async with asyncio.timeout(self.timeout):
                return await self.resolve()
        except TimeoutError:
            self.log.error("Failed to lock within %s seconds", self.timeout)

    async def resolve(self) -> _Union[bool, None]:
        """Asynchronous solve.

        An async locker should overload this.
        """
        msg = f"{self} cannot solve a `pyodide-lock.json`."
        raise NotImplementedError(msg)