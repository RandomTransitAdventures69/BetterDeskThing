"""Shared configuration for MyDeskThing.

User settings live in a persistent user data directory.  In development that
is the project directory; in a PyInstaller build it is %APPDATA%/MyDeskThing
on Windows (or the platform equivalent).  Secret values are only read here
and are never returned by the settings API or printed by the setup wizard.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv


BASE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""

    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Directory that contains bundled assets (index.html, templates)."""

    if is_frozen():
        return Path(
            getattr(
                sys,
                "_MEIPASS",
                str(Path(sys.executable).resolve().parent),
            )
        )
    return BASE_DIR


def user_data_dir() -> Path:
    """Writable, persistent directory for .env and the Spotify cache."""

    override = os.environ.get("MYDESKTHING_HOME")
    if override:
        return Path(override).expanduser().resolve()

    if is_frozen():
        if os.name == "nt":
            base = Path(
                os.environ.get(
                    "APPDATA",
                    str(Path.home() / "AppData" / "Roaming"),
                )
            )
            return base / "MyDeskThing"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "MyDeskThing"
        return (
            Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
            / "MyDeskThing"
        )

    return BASE_DIR


USER_DATA_DIR = user_data_dir()

# The override is useful for tests and for running from another directory.
ENV_FILE = Path(
    os.environ.get(
        "MYDESKTHING_ENV_FILE",
        str(USER_DATA_DIR / ".env"),
    )
).expanduser().resolve()

CACHE_FILE = USER_DATA_DIR / ".cache"

SECRET_KEYS = (
    "SPOTIPY_CLIENT_ID",
    "SPOTIPY_CLIENT_SECRET",
    "SPOTIPY_REDIRECT_URI",
    "MBTA_API_KEY",
)

DEFAULT_SETTINGS: dict[str, str] = {
    "WEATHER_LABEL": "Keystone, FL",
    "WEATHER_LAT": "28.6314",
    "WEATHER_LON": "-82.2995",
    "WEATHER_UNITS": "fahrenheit",
    "WEATHER_TIMEZONE": "America/New_York",
    "FORECAST_DAYS": "5",
    "WEATHER_REFRESH_MINUTES": "15",
    "TRANSIT_DEFAULT_STOP": "place-WML-0081",
    "TRANSIT_REFRESH_SECONDS": "30",
    "TRANSIT_DEPARTURE_LIMIT": "10",
    "SPOTIFY_POLL_SECONDS": "2",
    "SERVER_HOST": "0.0.0.0",
    "SERVER_PORT": "8080",
    "START_PAGE": "weather",
    "UI_THEME": "classic",
    "SHOW_STATUSBAR": "true",
}

SECRET_LABELS = {
    "SPOTIPY_CLIENT_ID": "Spotify Client ID",
    "SPOTIPY_CLIENT_SECRET": "Spotify Client Secret",
    "SPOTIPY_REDIRECT_URI": "Spotify Redirect URI",
    "MBTA_API_KEY": "MBTA API key",
}

SETTING_LABELS = {
    "WEATHER_LABEL": "Weather location label",
    "WEATHER_LAT": "Latitude (-90 to 90)",
    "WEATHER_LON": "Longitude (-180 to 180)",
    "WEATHER_UNITS": "Temperature units (fahrenheit/celsius)",
    "WEATHER_TIMEZONE": "Timezone (IANA name)",
    "FORECAST_DAYS": "Forecast days (3-7)",
    "WEATHER_REFRESH_MINUTES": "Weather refresh (minutes)",
    "TRANSIT_DEFAULT_STOP": "Default MBTA stop ID",
    "TRANSIT_REFRESH_SECONDS": "Transit refresh (seconds)",
    "TRANSIT_DEPARTURE_LIMIT": "Departures to show (1-25)",
    "SPOTIFY_POLL_SECONDS": "Spotify poll interval (seconds)",
    "SERVER_HOST": "Server host",
    "SERVER_PORT": "Server port",
    "START_PAGE": "Start page (weather/spotify/transit/settings)",
    "UI_THEME": "Theme (classic/dark)",
    "SHOW_STATUSBAR": "Show status bar",
}

ENV_LINE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*="
)

SAFE_VALUE = re.compile(r"^[A-Za-z0-9_./:@?=&%+\-,]*$")

STOP_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ConfigError(ValueError):
    """Raised when a configuration value is invalid."""


# --------------------------------------------------
# PACKAGED / USER DATA PATHS
# --------------------------------------------------

def resource_path(name: str) -> Path:
    """Return the path of a bundled read-only resource."""

    return resource_dir() / name


def ensure_user_data_dir() -> Path:
    """Create the persistent user data directory when needed."""

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return USER_DATA_DIR


def migrate_legacy_files() -> None:
    """Copy an old project-local .env / Spotify cache into user data.

    Only runs in a frozen build and only when the destination does not
    already exist.  Existing user settings are never overwritten.
    """

    if not is_frozen() or os.environ.get("MYDESKTHING_NO_MIGRATE") == "1":
        return

    ensure_user_data_dir()

    source_dir = Path(sys.executable).resolve().parent

    for name in (".env", ".cache"):
        source = source_dir / name
        destination = USER_DATA_DIR / name

        if source.is_file() and not destination.exists():
            try:
                shutil.copy2(source, destination)
            except OSError:
                # Startup validation will report an unwritable data dir.
                pass


def validate_server_config(
    path: Path | str | None = None,
) -> tuple[str, int]:
    """Return the validated bind host and port."""

    settings = load_settings(path)

    host = str(settings["SERVER_HOST"]).strip()
    port = int(settings["SERVER_PORT"])

    if not host or any(character.isspace() for character in host):
        raise ConfigError("Server host cannot be empty or contain spaces.")

    if port < 1 or port > 65535:
        raise ConfigError("Server port must be between 1 and 65535.")

    ensure_user_data_dir()

    return host, port


def runtime_info() -> dict[str, Any]:
    """Non-secret information about the current runtime layout."""

    return {
        "frozen": is_frozen(),
        "resource_dir": str(resource_dir()),
        "user_data_dir": str(USER_DATA_DIR),
        "env_file": str(ENV_FILE),
        "cache_file": str(CACHE_FILE),
    }


# --------------------------------------------------
# VALIDATION
# --------------------------------------------------

def _clean_text(value: Any, label: str, maximum: int = 256) -> str:
    text = str(value).strip()
    if not text:
        raise ConfigError(f"{label} cannot be empty.")
    if "\n" in text or "\r" in text:
        raise ConfigError(f"{label} cannot contain a new line.")
    if len(text) > maximum:
        raise ConfigError(f"{label} must be {maximum} characters or fewer.")
    return text


def _number(value: Any, label: str, low: float, high: float,
            integer: bool = False) -> str:
    text = _clean_text(value, label, 40)
    try:
        number = int(text) if integer else float(text)
    except ValueError:
        raise ConfigError(f"{label} must be a number.") from None
    if number < low or number > high:
        kind = "whole number" if integer else "number"
        raise ConfigError(
            f"{label} must be a {kind} between {low:g} and {high:g}."
        )
    return str(number)


def _choice(value: Any, label: str, choices: tuple[str, ...]) -> str:
    text = _clean_text(value, label, 80).lower()
    if text not in choices:
        raise ConfigError(
            f"{label} must be one of: {', '.join(choices)}."
        )
    return text


def _timezone(value: Any) -> str:
    text = _clean_text(value, "Timezone", 80)
    if not re.fullmatch(r"[A-Za-z0-9_+\-/:]+", text):
        raise ConfigError("Timezone must be an IANA name, e.g. America/New_York.")
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(text)
    except Exception:
        # Python on Windows needs the ``tzdata`` package for ZoneInfo.  If it
        # is not installed yet (first wizard run), keep the typed name.
        pass
    return text


def validate_setting(key: str, value: Any) -> str:
    """Return the normalised string form of one non-secret setting."""

    if key not in DEFAULT_SETTINGS:
        raise ConfigError(f"Unknown setting: {key}")

    label = SETTING_LABELS.get(key, key)

    if key == "WEATHER_LABEL":
        return _clean_text(value, label, 80)

    if key == "WEATHER_LAT":
        return _number(value, label, -90, 90)

    if key == "WEATHER_LON":
        return _number(value, label, -180, 180)

    if key == "WEATHER_UNITS":
        return _choice(value, label, ("fahrenheit", "celsius"))

    if key == "WEATHER_TIMEZONE":
        return _timezone(value)

    if key == "FORECAST_DAYS":
        return _number(value, label, 3, 7, integer=True)

    if key == "WEATHER_REFRESH_MINUTES":
        return _number(value, label, 1, 1440, integer=True)

    if key == "TRANSIT_DEFAULT_STOP":
        text = _clean_text(value, label, 64)
        if not STOP_ID.fullmatch(text):
            raise ConfigError("Stop ID may only contain letters, numbers, - and _.")
        return text

    if key == "TRANSIT_REFRESH_SECONDS":
        return _number(value, label, 10, 3600, integer=True)

    if key == "TRANSIT_DEPARTURE_LIMIT":
        return _number(value, label, 1, 25, integer=True)

    if key == "SPOTIFY_POLL_SECONDS":
        return _number(value, label, 1, 60, integer=True)

    if key == "SERVER_HOST":
        return _clean_text(value, label, 253)

    if key == "SERVER_PORT":
        return _number(value, label, 1, 65535, integer=True)

    if key == "START_PAGE":
        return _choice(
            value,
            label,
            ("weather", "spotify", "transit", "settings"),
        )

    if key == "UI_THEME":
        return _choice(value, label, ("classic", "dark"))

    if key == "SHOW_STATUSBAR":
        if isinstance(value, bool):
            return "true" if value else "false"
        text = _clean_text(value, label, 8).lower()
        if text in ("true", "1", "yes", "on"):
            return "true"
        if text in ("false", "0", "no", "off"):
            return "false"
        raise ConfigError(f"{label} must be yes or no.")

    raise ConfigError(f"Unknown setting: {key}")


def validate_secret(key: str, value: Any) -> str:
    """Return the normalised string form of one secret."""

    if key not in SECRET_KEYS:
        raise ConfigError(f"Unknown credential: {key}")

    label = SECRET_LABELS[key]
    text = _clean_text(value, label, 512)

    if key == "SPOTIPY_REDIRECT_URI":
        from urllib.parse import urlparse

        parsed = urlparse(text)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ConfigError(
                "Spotify Redirect URI must be a full http:// or https:// URL."
            )
    else:
        if any(character.isspace() for character in text):
            raise ConfigError(f"{label} cannot contain spaces.")

    return text


def validate_settings_patch(payload: Any) -> dict[str, str]:
    """Validate a partial settings update. Secrets are rejected here."""

    if not isinstance(payload, dict):
        raise ConfigError("Settings must be a JSON object.")

    updates: dict[str, str] = {}
    for key, value in payload.items():
        if key in SECRET_KEYS:
            raise ConfigError(
                f"{key} is a credential; use the Credentials section."
            )
        updates[key] = validate_setting(key, value)
    return updates


def validate_secret_patch(payload: Any) -> dict[str, str]:
    """Validate a partial credential update. Blank values are ignored."""

    if not isinstance(payload, dict):
        raise ConfigError("Credentials must be a JSON object.")

    updates: dict[str, str] = {}
    for key, value in payload.items():
        text = "" if value is None else str(value).strip()
        if not text:
            # Blank means "keep the current value".
            continue
        updates[key] = validate_secret(key, text)
    return updates


# --------------------------------------------------
# READ / WRITE
# --------------------------------------------------

def read_env(path: Path | str | None = None) -> dict[str, str]:
    """Read .env without printing or interpolating any values."""

    target = Path(path) if path is not None else ENV_FILE
    if not target.is_file():
        return {}
    raw = dotenv_values(target, interpolate=False)
    return {
        str(key): ("" if value is None else str(value))
        for key, value in raw.items()
    }


def _format_value(value: Any) -> str:
    text = str(value)
    if SAFE_VALUE.fullmatch(text):
        return text
    # python-dotenv keeps single-quoted values literal (no ${} expansion).
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    return "'" + escaped + "'"


def write_env(updates: dict[str, Any], path: Path | str | None = None) -> None:
    """Atomically update .env, preserving unrelated keys and comments."""

    target = Path(path) if path is not None else ENV_FILE
    target.parent.mkdir(parents=True, exist_ok=True)

    clean = {str(key): str(value) for key, value in updates.items()}
    for key, value in clean.items():
        if "\n" in value or "\r" in value:
            raise ConfigError(f"{key} cannot contain a new line.")

    lines: list[str] = []
    if target.is_file():
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()

    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        match = ENV_LINE.match(line)
        if match and match.group(1) in clean:
            key = match.group(1)
            output.append(f"{key}={_format_value(clean[key])}")
            seen.add(key)
        else:
            output.append(line)

    for key, value in clean.items():
        if key not in seen:
            output.append(f"{key}={_format_value(value)}")

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write("\n".join(output) + "\n")
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    if os.name != "nt":
        try:
            target.chmod(0o600)
        except OSError:
            pass


def load_env_into_process() -> None:
    """Make the .env values available to libraries such as spotipy."""

    if ENV_FILE.is_file():
        load_dotenv(dotenv_path=ENV_FILE, override=True)


# --------------------------------------------------
# PUBLIC VIEWS
# --------------------------------------------------

def load_settings(path: Path | str | None = None) -> dict[str, Any]:
    """Return settings with proper Python types and safe fallbacks."""

    values = read_env(path)
    normalised: dict[str, str] = {}
    for key, default in DEFAULT_SETTINGS.items():
        raw = values.get(key, default)
        try:
            normalised[key] = validate_setting(key, raw)
        except ConfigError:
            normalised[key] = default

    return {
        "WEATHER_LABEL": normalised["WEATHER_LABEL"],
        "WEATHER_LAT": float(normalised["WEATHER_LAT"]),
        "WEATHER_LON": float(normalised["WEATHER_LON"]),
        "WEATHER_UNITS": normalised["WEATHER_UNITS"],
        "WEATHER_TIMEZONE": normalised["WEATHER_TIMEZONE"],
        "FORECAST_DAYS": int(normalised["FORECAST_DAYS"]),
        "WEATHER_REFRESH_MINUTES": int(normalised["WEATHER_REFRESH_MINUTES"]),
        "TRANSIT_DEFAULT_STOP": normalised["TRANSIT_DEFAULT_STOP"],
        "TRANSIT_REFRESH_SECONDS": int(normalised["TRANSIT_REFRESH_SECONDS"]),
        "TRANSIT_DEPARTURE_LIMIT": int(normalised["TRANSIT_DEPARTURE_LIMIT"]),
        "SPOTIFY_POLL_SECONDS": int(normalised["SPOTIFY_POLL_SECONDS"]),
        "SERVER_HOST": normalised["SERVER_HOST"],
        "SERVER_PORT": int(normalised["SERVER_PORT"]),
        "START_PAGE": normalised["START_PAGE"],
        "UI_THEME": normalised["UI_THEME"],
        "SHOW_STATUSBAR": normalised["SHOW_STATUSBAR"] == "true",
    }


def public_settings(path: Path | str | None = None) -> dict[str, Any]:
    """A JSON-safe copy of settings (contains no credentials)."""

    return dict(load_settings(path))


def secret_status(path: Path | str | None = None) -> dict[str, bool]:
    """Report only whether each credential is present, never its value."""

    values = read_env(path)
    return {key: bool(values.get(key, "").strip()) for key in SECRET_KEYS}
