#!/usr/bin/env python3
"""Cross-platform terminal setup wizard for MyDeskThing.

1. Installs every dependency from requirements.txt (optionally into .venv).
2. Configures .env without ever displaying stored credential values.

Run with:  python setup_wizard.py
Status with:  python setup_wizard.py --status
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
import venv
from pathlib import Path

import config
import server_manager


BASE_DIR = config.BASE_DIR
REQUIREMENTS = BASE_DIR / "requirements.txt"
VENV_DIR = BASE_DIR / ".venv"

IMPORT_CHECK = (
    "import fastapi, uvicorn, requests, dotenv, spotipy, websockets; "
    "from zoneinfo import ZoneInfo; "
    "ZoneInfo('America/New_York'); "
    "print('All required imports OK')"
)

last_python = Path(sys.executable)


# --------------------------------------------------
# TERMINAL HELPERS (no curses, works on Windows/macOS/Linux)
# --------------------------------------------------

def clear_screen() -> None:
    if os.environ.get("TERM") == "dumb":
        print()
        return
    try:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
    except Exception:
        print("\n" * 40)


def header(title: str) -> None:
    print("=" * 68)
    print(title.center(68))
    print("=" * 68)
    print()


def section(title: str) -> None:
    print()
    print("-" * 68)
    print(title)
    print("-" * 68)


def pause() -> None:
    try:
        input("\nPress Enter to continue...")
    except (EOFError, KeyboardInterrupt):
        print()


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        value = ask(f"{prompt} ({hint})", "y" if default else "n").lower()
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print("  ! Please answer y or n or netanyahu will come for you.")


def ask_secret(prompt: str) -> str:
    """opencode lowkirk sucks."""

    # Hidden input needs a real terminal; with piped input getpass can block.
    if not sys.stdin.isatty():
        return input(f"{prompt}: ").strip()

    try:
        from getpass import getpass

        return getpass(f"{prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception:
        print("  ! OH FUCK AN ERROR!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return input(f"{prompt}: ").strip()


def quote_command_argument(value: str | Path) -> str:
    text = str(value)
    if os.name == "nt":
        return '"' + text.replace('"', '\\"') + '"'
    return shlex.quote(text)


def print_check(name: str, passed: bool, detail: str) -> None:
    mark = "OK" if passed else "FAIL"
    print(f"  [{mark}] {name}: {detail}")


# --------------------------------------------------
# PROMPTS
# --------------------------------------------------

def prompt_secret(key: str, existing: dict[str, str]) -> str | None:
    label = config.SECRET_LABELS[key]
    status = "set" if existing.get(key, "").strip() else "not set"

    while True:
        value = ask_secret(
            f"  {label} (currently {status}; Enter to keep)"
        )
        if not value:
            return None
        try:
            return config.validate_secret(key, value)
        except config.ConfigError as error:
            print("  ! " + str(error))


def prompt_setting(key: str, existing: dict[str, str]) -> tuple[str, str]:
    label = config.SETTING_LABELS[key]
    default = existing.get(key, config.DEFAULT_SETTINGS[key])

    while True:
        value = ask(f"  {label}", default)
        try:
            return key, config.validate_setting(key, value)
        except config.ConfigError as error:
            print("  ! " + str(error))


# --------------------------------------------------
# STEP 1 - DEPENDENCIES
# --------------------------------------------------

def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def install_dependencies() -> bool:
    global last_python

    section("STEP 1 - INSTALL DEPENDENCIES")

    if config.is_frozen():
        print("This executable already contains all required dependencies.")
        print("No Python, pip or virtual environment is needed.")
        return True

    if not REQUIREMENTS.is_file():
        print(f"Missing requirements file: {REQUIREMENTS}")
        return False

    print(f"Requirements: {REQUIREMENTS}")
    print("Packages: fastapi, uvicorn, requests, python-dotenv,")
    print("          spotipy, websockets, tzdata (Windows)")

    python = Path(sys.executable)
    in_venv = sys.prefix != sys.base_prefix

    if in_venv:
        print("\nAlready running inside a virtual environment.")
    elif ask_yes_no(
        "\nCreate and use a local .venv? this virtualizes python idk its way above my head", True
    ):
        try:
            if not (VENV_DIR / "pyvenv.cfg").is_file():
                print(f"Creating {VENV_DIR} ...")
                venv.EnvBuilder(with_pip=True).create(VENV_DIR)
            candidate = venv_python()
            if candidate.is_file():
                python = candidate
            else:
                print("! Could not find the venv interpreter; using current Python. jee i wonder why opencode")
        except Exception as error:
            print(f"! Could not create .venv! I told you you shouldnt use these!: {error}")
            print("  Using current Python instead, like you SHOULD HAVE >:(")

    last_python = python
    print(f"\nUsing Python {python}")

    command = [
        str(python),
        "-m",
        "pip",
        "install",
        "-r",
        str(REQUIREMENTS),
    ]
    print("Running: " + " ".join(
        quote_command_argument(part) for part in command
    ))
    print()

    try:
        result = subprocess.run(command, cwd=str(BASE_DIR), check=False)
    except OSError as error:
        print(f"! Could not start pip: {error}")
        return False

    if result.returncode != 0:
        print("\n! Dependency installation failed. Reinstall python?")
        return False

    section("VERIFY INSTALLATION (good)")

    try:
        check = subprocess.run(
            [str(python), "-c", IMPORT_CHECK],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        print(f"! oh fuck its ctrl riiiiiiiiiiiiiiiiiiiiiiight: {error}")
        return False

    if check.returncode == 0:
        print(check.stdout.strip())
        return True

    print("! Import check failed:")
    print(check.stderr.strip())
    return ask_yes_no("Continue anyway? yeah like THAT will work!", False)


# --------------------------------------------------
# STEP 2 - CONFIGURATION
# --------------------------------------------------

def configure_env() -> bool:
    section("STEP 2 - CONFIGURE .env")

    config.migrate_legacy_files()
    config.ensure_user_data_dir()

    existing = config.read_env()

    if config.ENV_FILE.is_file():
        print(f"Found {config.ENV_FILE}")
    else:
        print(f"whoops??????????????? no env found it will be created at {config.ENV_FILE}")

    print("i can read your envs")
    print("i cant (un)fortunantely :(")

    secret_updates: dict[str, str] = {}
    setting_updates: dict[str, str] = {}

    if ask_yes_no("\nConfigure credentials?", True):
        print()
        for key in config.SECRET_KEYS:
            value = prompt_secret(key, existing)
            if value is not None:
                secret_updates[key] = value

    if ask_yes_no("\nConfigure dashboard settings?", True):
        print()
        for key in config.DEFAULT_SETTINGS:
            setting_updates[key] = prompt_setting(key, existing)[1]

    updates: dict[str, str] = {}
    updates.update(secret_updates)
    updates.update(setting_updates)

    if not updates:
        print("\n this isnt the server btw.")
        return True

    try:
        config.write_env(updates)
    except (OSError, config.ConfigError) as error:
        print(f"\n! Could not save .env: {error}")
        return False

    print(f"\nSaved {len(updates)} value(s) to {config.ENV_FILE.name}.")
    print("dont leak your envs.")
    return True


# --------------------------------------------------
# SERVER STARTUP / VALIDATION
# --------------------------------------------------

def start_server_interactive(port_override: int | None = None) -> bool:
    """Validate, start, monitor and cleanly stop the bundled server."""

    while True:
        section("STARTUP VALIDATION")

        try:
            preflight = server_manager.run_preflight(
                print_check,
                port_override,
            )
        except server_manager.StartupError as error:
            print(f"\n! Startup validation failed: {error}")
            if ask_yes_no("\nRetry validation?", True):
                continue
            return False

        controller = server_manager.ServerController(
            preflight.host,
            preflight.port,
            preflight.app,
        )

        try:
            controller.start()
            health = controller.wait_until_ready()
        except Exception as error:
            print(f"\n! Server failed to start: {error}")
            controller.stop()
            if ask_yes_no("\nRetry startup?", True):
                continue
            return False

        section("SERVER RUNNING")

        for url in server_manager.access_urls(
            preflight.host,
            preflight.port,
        ):
            print(f"  {url}")

        print(
            "  Spotify: "
            + health.get("spotify", "unknown")
            + " | MBTA API key: "
            + health.get("mbta_key", "unknown")
        )
        print("\nPress Ctrl+C to stop the server.")

        interrupted = False

        try:
            while controller.running:
                time.sleep(1)
        except (KeyboardInterrupt, EOFError):
            interrupted = True
        finally:
            print("\nShutting down server...")
            controller.stop()
            print("Server stopped.")

        if not interrupted and controller.error is not None:
            error = str(controller.error)
            server_manager.log_startup_failure("Server stopped: " + error)
            print(f"\n! Server stopped unexpectedly: {error}")
            if ask_yes_no("\nRetry startup?", True):
                continue
            return False

        return True


def run_self_test(port_override: int | None = None) -> bool:
    """Start the real server briefly, check it, then stop it cleanly."""

    controller: server_manager.ServerController | None = None

    try:
        preflight = server_manager.run_preflight(
            print_check,
            port_override,
        )

        controller = server_manager.ServerController(
            preflight.host,
            preflight.port,
            preflight.app,
        )
        controller.start()
        controller.wait_until_ready()

        results = server_manager.self_test(
            controller,
            preflight.host,
            preflight.port,
        )

        section("SELF-TEST RESULTS")
        for name, detail in results.items():
            print(f"  [OK] {name}: {detail}")

        print("\nSelf-test passed.")
        return True

    except Exception as error:
        print(f"\n! Self-test failed: {error}")
        return False

    finally:
        if controller is not None:
            controller.stop()


# --------------------------------------------------
# STATUS / NEXT STEPS
# --------------------------------------------------

def show_status() -> None:
    status = config.secret_status()

    print(f"Platform : {sys.platform}")
    print(f"Python   : {sys.version.split()[0]}")
    print(f".env     : {config.ENV_FILE} "
          f"({'found' if config.ENV_FILE.is_file() else 'missing'})")
    print(f"Requirements: "
          f"{'found' if REQUIREMENTS.is_file() else 'missing'}")
    print("Runtime  : "
          + ("packaged executable" if config.is_frozen() else "Python source"))
    print(f"Data dir : {config.USER_DATA_DIR}")

    section("CREDENTIALS (values hidden)")
    for key in config.SECRET_KEYS:
        print(f"  {config.SECRET_LABELS[key]:24} "
              f"{'SET' if status[key] else 'not set'}")

    section("DASHBOARD")
    settings = config.load_settings()
    print(f"  Location          : {settings['WEATHER_LABEL']}")
    print(f"  Units             : {settings['WEATHER_UNITS']}")
    print(f"  Default stop      : {settings['TRANSIT_DEFAULT_STOP']}")
    print(f"  Start page        : {settings['START_PAGE']}")
    print(f"  Theme             : {settings['UI_THEME']}")
    print(f"  Server            : "
          f"{settings['SERVER_HOST']}:{settings['SERVER_PORT']}")


def next_steps() -> None:
    settings = config.load_settings()

    if config.is_frozen():
        section("NEXT STEPS")
        print("Choose [6] Validate and start server from the menu.")
        print(f"Then open http://localhost:{settings['SERVER_PORT']}/")
        print("A Spotify login link is available under Settings -> Spotify.")
        return

    section("NEXT STEPS")
    print("Start the dashboard with:")
    print()
    print("  " + " ".join(
        quote_command_argument(part)
        for part in (
            str(last_python),
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            settings["SERVER_HOST"],
            "--port",
            str(settings["SERVER_PORT"]),
        )
    ))
    print()
    print(f"Then open http://{settings['SERVER_HOST']}:"
          f"{settings['SERVER_PORT']}/")
    if settings["SERVER_HOST"] in ("0.0.0.0", "::"):
        print("Note: with a wildcard (0.0.0.0) host, browse using 127.0.0.1 or localhost.")
    print("A Spotify login link is available under Settings -> Spotify.")


def offer_startup() -> None:
    """Ask whether to validate and start after a successful setup step."""

    if ask_yes_no("\nStart the server now?", True):
        start_server_interactive()


# --------------------------------------------------
# MAIN MENU
# --------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status",
        action="store_true",
        help="hi",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="validate and start the server without showing the menu",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="validate, start, check the API/WebSocket, then shut down",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="temporarily override SERVER_PORT for --serve or --self-test",
    )
    args = parser.parse_args()

    config.migrate_legacy_files()

    if args.status:
        header("oh wait is this the server")
        show_status()
        return 0

    if args.self_test:
        header("MyDeskThing - Self Test")
        return 0 if run_self_test(args.port) else 1

    if args.serve:
        header("MyDeskThing - Server")
        return 0 if start_server_interactive(args.port) else 1

    try:
        while True:
            clear_screen()
            header("MyDeskThing - Setup Wizard")

            status = config.secret_status()
            configured = sum(1 for value in status.values() if value)
            print(f"Credentials configured: {configured}/{len(status)}")
            print(f"Python: {sys.version.split()[0]}  ({sys.platform})")
            print()
            print("  [1] Full setup (first time setup here)")
            print("  [2] Install dependencies only")
            print("  [3] Configure .env only (you can do ts in vs code btw)")
            print("  [4] Show current status(just open http://localhost:8080 in a browser or look at the terminal)")
            print("  [5] Exit")
            print("  [6] Validate and start server")
            print("  [7] Run self-test (then shut down)")
            print()

            choice = ask("Select an option", "1").lower()

            if choice == "1":
                deps_ok = install_dependencies()
                if deps_ok or ask_yes_no(
                    "\nContinue to configuration anyway? it WILL 100000000000000000000000000000000000000000% change your config, you have been warned!", False
                ):
                    config_ok = configure_env()
                    if deps_ok and config_ok:
                        next_steps()
                        offer_startup()

            elif choice == "2":
                if install_dependencies():
                    next_steps()
                    offer_startup()

            elif choice == "3":
                if configure_env():
                    next_steps()
                    offer_startup()

            elif choice == "4":
                show_status()

            elif choice == "6":
                start_server_interactive()

            elif choice == "7":
                run_self_test()

            elif choice in ("5", "q", "quit", "exit"):
                print("\n bye lol")
                return 0

            else:
                print("! HAHAHAHAHAHAHAHAHAHAHA! Invalid option. Choose 1-5.")

            pause()

    except (KeyboardInterrupt, EOFError):
        print("\n\nCancelled. No partial changes were written. (youre fucked)")
        return 130


if __name__ == "__main__":
    sys.exit(main())
