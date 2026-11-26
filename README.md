# MyDeskThing

Oh hey there!

DeskThing was maxing out my CPU, so I made a **VERY lightweight version**.

MyDeskThing is a simple, fast dashboard for Spotify, weather, and transit that runs locally with a Python backend and a plain HTML/CSS/JavaScript frontend.

## Requirements

* A computer
* Python
* A Spotify App
* An MBTA API key
* Internet access

That's pretty much it.

## Why?

idk why but deskthing is laggy as hell 😭

The goal is simple:

**Make it fast. Make it lightweight. Make it work.**


# i aint gonna lie i asked assgpt to write this because the guide would miss A LOT of things

## Packaged Windows executable (EXE)

This release also includes a standalone Windows build. The EXE bundles Python
and every required package, so it does not need Python, pip, Node.js, or a
development environment.

```powershell
.\dist\MyDeskThing.exe
```

The wizard creates/validates configuration, then asks whether to start the
server. To start without the menu:

```powershell
.\dist\MyDeskThing.exe --serve
```

To check status without starting anything:

```powershell
.\dist\MyDeskThing.exe --status
```

To run the full startup check, start the real server briefly, verify the
frontend/API/WebSocket, and shut it down again:

```powershell
.\dist\MyDeskThing.exe --self-test
```

Use `--port 8181` with `--serve` or `--self-test` for a temporary port override.

Open the dashboard at <http://localhost:8080>. When `SERVER_HOST` is
`0.0.0.0`, the wizard also prints a best-effort LAN address.

## User data

The executable never writes persistent settings into its temporary extraction
directory.

| Environment | User data directory |
| --- | --- |
| Packaged Windows build | `%APPDATA%\MyDeskThing` |
| Packaged macOS build | `~/Library/Application Support/MyDeskThing` |
| Packaged Linux build | `$XDG_CONFIG_HOME/MyDeskThing` or `~/.config/MyDeskThing` |
| Python source | project directory |

`.env` and the Spotify token cache live in that directory. Existing settings
are never overwritten when rebuilding or upgrading. If a project-local `.env`
or `.cache` exists next to the EXE, it is copied once, only when no user copy
exists yet. Set `MYDESKTHING_NO_MIGRATE=1` to skip that copy.

Credential values are never displayed by the wizard, returned by the settings
API, or written to `startup.log`. The API only reports `configured` /
`not configured`.

## Build from source

Install runtime dependencies first:

```powershell
python -m pip install -r requirements.txt
```

Then build both the onedir test build and the onefile release EXE:

```powershell
.\build_exe.ps1
```

Outputs:

- `dist\MyDeskThing\MyDeskThing.exe` — onedir test build
- `dist\MyDeskThing.exe` — standalone onefile release build

Build files:

- `MyDeskThing_onedir.spec` — onedir configuration
- `MyDeskThing.spec` — onefile configuration
- `build-requirements.txt` — PyInstaller dependencies

The build script installs build dependencies, cleans only MyDeskThing build
artifacts, reports failures, and verifies both EXEs exist.

## Python source mode

```powershell
python -m pip install -r requirements.txt
python setup_wizard.py
python setup_wizard.py --self-test --port 8181
python setup_wizard.py --serve
```

`python -m uvicorn server:app --host 0.0.0.0 --port 8080` still works too.

## Startup validation

The wizard validates before starting anything:

1. required configuration
2. writable user data directory
3. bundled/importable modules
4. `server:app`
5. server host/port
6. port availability
7. health endpoint

Failures are shown and appended to `%APPDATA%\MyDeskThing\startup.log` without
secret values. Retry or exit are offered instead of silently failing. Uvicorn
runs in-process as a daemon thread owned by the wizard, so normal shutdown
does not leave orphaned Python/Uvicorn processes behind.

## Troubleshooting

- **Port already in use:** close the other program or change `SERVER_PORT` in
  Settings / `.env`. Startup validation stops before launching a second server.
- **Startup validation fails:** the failing check is printed and appended to
  `%APPDATA%\MyDeskThing\startup.log`. No secret values are logged.
- **Spotify shows `not configured`:** add credentials in Settings → Spotify,
  then use the login button.
- **Weather or MBTA fails:** the API returns a clear error; the rest of the
  dashboard stays available.
- **Browser shows an old value after saving:** reload the page. Host/port
  changes require a server restart.
- **EXE opens and closes immediately:** run it from PowerShell so the console
  output stays visible, then use `--status` or `--self-test`.
