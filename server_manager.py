"""Startup validation and lifecycle management for the MyDeskThing server.

The wizard uses this module so validation, startup, health checks and shutdown
all happen in-process.  No extra Python or Uvicorn process is spawned, which
keeps packaged builds from leaving orphaned processes behind.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import config


REQUIRED_MODULES = (
    "fastapi",
    "uvicorn",
    "requests",
    "dotenv",
    "spotipy",
    "websockets",
)

ReportCallback = Callable[[str, bool, str], None]


class StartupError(RuntimeError):
    """A preflight check or startup health check failed. Is anything installed?"""


@dataclass
class PreflightResult:
    host: str
    port: int
    app: Any
    steps: list[tuple[str, bool, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(passed for _, passed, _ in self.steps)


def log_startup_failure(message: str) -> None:
    """Append a non-secret diagnostic line to the user data directory. idk what on gods green FUCKING earth opencode makes"""

    try:
        path = config.ensure_user_data_dir() / "startup.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                time.strftime("%Y-%m-%d %H:%M:%S")
                + "  "
                + message.replace("\n", " ")
                + "\n"
            )
    except OSError:
        # The failure is always displayed to the user as well.
        pass


def _report(callback: ReportCallback | None, name: str,
            passed: bool, detail: str) -> None:
    if not passed:
        log_startup_failure(f"{name}: {detail}")
    if callback is not None:
        callback(name, passed, detail)


def _check_data_directory() -> str:
    directory = config.ensure_user_data_dir()

    with tempfile.NamedTemporaryFile(
        prefix=".writecheck-",
        dir=str(directory),
        delete=True,
    ):
        pass

    return str(directory)


def _check_modules() -> str:
    versions: list[str] = []

    for name in REQUIRED_MODULES:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "unknown")
        versions.append(f"{name} {version}")

    from zoneinfo import ZoneInfo

    ZoneInfo("America/New_York")

    return ", ".join(versions)


def _check_app() -> Any:
    module = importlib.import_module("server")
    app = getattr(module, "app", None)

    if app is None or not hasattr(app, "routes"):
        raise StartupError("server.py did not expose a FastAPI app. Install fastapi?")

    return app


def _port_socket(host: str, port: int) -> socket.socket:
    if host == "::":
        return socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def check_port_available(host: str, port: int) -> None:
    """Fail if another process is already listening on the bind address. Hint: change one (1) number in the port"""

    bind_host = "" if host in ("0.0.0.0", "::") else host
    probe = _port_socket(host, port)

    try:
        probe.bind((bind_host, port))
    except OSError as error:
        raise StartupError(
            f"Port {port} is not available: {error}. "
            "Close the other program or change SERVER_PORT in Settings. wait do the thing above"
        ) from None
    finally:
        probe.close()


def run_preflight(
    callback: ReportCallback | None = None,
    port_override: int | None = None,
) -> PreflightResult:
    """do not run all checks required before starting the production server."""

    steps: list[tuple[str, bool, str]] = []

    try:
        host, port = config.validate_server_config()

        if port_override is not None:
            if not 1 <= port_override <= 65535:
                raise config.ConfigError("Override port must be 1-65535. ????????????????????")
            port = port_override

    except config.ConfigError as error:
        _report(callback, "Configuration", False, str(error))
        raise StartupError(str(error)) from None

    _report(
        callback,
        "Configuration",
        True,
        f"bind address {host}:{port}",
    )
    steps.append(("Configuration", True, f"{host}:{port}"))

    try:
        detail = _check_data_directory()
    except OSError as error:
        message = f"User data directory is not writable: {error}"
        _report(callback, "User data directory", False, message)
        raise StartupError(message) from None

    _report(callback, "User data directory", True, detail)
    steps.append(("User data directory", True, detail))

    try:
        detail = _check_modules()
    except Exception as error:
        message = f"Required module import failed: {error}"
        _report(callback, "Required modules", False, message)
        raise StartupError(message) from None

    _report(callback, "Required modules", True, detail)
    steps.append(("Required modules", True, detail))

    try:
        app = _check_app()
    except Exception as error:
        message = f"FastAPI application failed to load: {error}"
        _report(callback, "FastAPI application", False, message)
        raise StartupError(message) from None

    _report(callback, "FastAPI application", True, "server:app loaded")
    steps.append(("FastAPI application", True, "server:app loaded"))

    try:
        check_port_available(host, port)
    except StartupError as error:
        _report(callback, "Port availability", False, str(error))
        raise

    _report(callback, "Port availability", True, f"{port} is free")
    steps.append(("Port availability", True, f"{port} is free"))

    return PreflightResult(
        host=host,
        port=port,
        app=app,
        steps=steps,
    )


def health_host(host: str) -> str:
    """Return an address that can reach the server for local health checks."""

    if host in ("0.0.0.0", "::", ""):
        return "127.0.0.1"
    return host


def _open_url(url: str, timeout: float = 3.0):
    # Bypass system proxies so a global proxy cannot break localhost checks.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({})
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MyDeskThing-startup-check"},
    )
    return opener.open(request, timeout=timeout)


def fetch_health(host: str, port: int, timeout: float = 3.0) -> dict:
    address = health_host(host)
    url = f"http://{address}:{port}/api/health"

    with _open_url(url, timeout) as response:
        payload = json.loads(
            response.read().decode("utf-8", errors="replace")
        )

    if payload.get("status") != "ok":
        raise StartupError(f"Health endpoint returned: {payload}")

    return payload


def lan_address() -> str | None:
    """Best-effort LAN IPv4 address; no packets are sent. haha no internet for you"""

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def access_urls(host: str, port: int) -> list[str]:
    urls = [f"http://localhost:{port}"]

    if host in ("0.0.0.0", "::", ""):
        address = lan_address()
        if address:
            urls.append(f"http://{address}:{port}")
    elif host not in ("127.0.0.1", "localhost"):
        urls.append(f"http://{host}:{port}")

    return urls


_active_server: "ServerController | None" = None
_server_lock = threading.Lock()


class ServerController:
    """Run Uvicorn in a daemon thread owned by the wizard process. hehe nerd talk"""

    def __init__(self, host: str, port: int, app: Any,
                 log_level: str = "warning") -> None:
        self.host = host
        self.port = port
        self.app = app
        self.log_level = log_level
        self._server: Any = None
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    @property
    def running(self) -> bool:
        return bool(
            self._server is not None
            and self._thread is not None
            and self._thread.is_alive()
            and not self._server.should_exit
        )

    @property
    def error(self) -> BaseException | None:
        return self._error

    def start(self) -> None:
        global _active_server

        with _server_lock:
            if _active_server is not None and _active_server.running:
                raise StartupError(
                    "A MyDeskThing server is already running in this process."
                )

            import uvicorn

            configuration = uvicorn.Config(
                self.app,
                host=self.host,
                port=self.port,
                log_level=self.log_level,
                lifespan="on",
                access_log=False,
            )
            self._server = uvicorn.Server(configuration)

            self._thread = threading.Thread(
                target=self._run,
                name="MyDeskThingServer",
                daemon=True,
            )
            _active_server = self
            self._thread.start()

    def _run(self) -> None:
        try:
            self._server.run()
        except BaseException as error:  # reported by wait_until_ready
            self._error = error

    def wait_until_ready(self, timeout: float = 20.0) -> dict:
        deadline = time.monotonic() + timeout
        last_error = "server did not respond"

        while time.monotonic() < deadline:
            if self._thread is not None and not self._thread.is_alive():
                last_error = str(self._error or "server thread stopped early")
                break

            try:
                return fetch_health(self.host, self.port)
            except (urllib.error.URLError, OSError, ValueError,
                    StartupError) as error:
                last_error = str(error)

            time.sleep(0.25)

        message = (
            f"Server health check failed after {timeout:g}s: {last_error}"
        )
        log_startup_failure(message)
        raise StartupError(message)

    def stop(self, timeout: float = 10.0) -> None:
        global _active_server

        if self._server is not None:
            self._server.should_exit = True

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        if self._thread is not None and self._thread.is_alive():
            print(
                "Warning: the server thread did not stop within "
                f"{timeout:g}s."
            )

        with _server_lock:
            if _active_server is self:
                _active_server = None


async def _websocket_check(url: str) -> None:
    import websockets

    async with websockets.connect(url, open_timeout=3):
        pass


def self_test(controller: ServerController, host: str, port: int) -> dict:
    """Check the running server without starting a second instance. try running it as admin lol"""

    results: dict[str, str] = {}

    address = health_host(host)
    base = f"http://{address}:{port}"

    with _open_url(base + "/") as response:
        body = response.read().decode("utf-8", errors="replace")
        if response.status != 200 or "settingsApp" not in body:
            raise StartupError("Frontend did not load from /")
    results["frontend"] = "index.html served. oh fuck it worked"

    with _open_url(base + "/api/settings") as response:
        payload = json.loads(response.read().decode("utf-8"))
        if "settings" not in payload or "secrets" not in payload:
            raise StartupError("Settings API returned an unexpected payload. haha")
    results["settings_api"] = "ok"

    with _open_url(base + "/api/health") as response:
        payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") != "ok":
            raise StartupError("Health API did not report ok. haha sucks for you >:)")
    results["health_api"] = "ok"

    ws_url = f"ws://{address}:{port}/ws"
    asyncio.run(_websocket_check(ws_url))
    results["websocket"] = "connected"

    return results
print("idk opencode is this like a tui settings app?")