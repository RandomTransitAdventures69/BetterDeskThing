import asyncio
import importlib.metadata
import sys
from contextlib import asynccontextmanager, suppress

import requests
import spotipy
from spotipy.oauth2 import CacheFileHandler, SpotifyOAuth

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse, RedirectResponse

import config


config.migrate_legacy_files()
config.ensure_user_data_dir()
config.load_env_into_process()

clients = set()
current_song = None


# --------------------------------------------------
# SPOTIFY
# --------------------------------------------------

SPOTIFY_SCOPE = (
    "user-read-currently-playing "
    "user-read-playback-state "
    "user-modify-playback-state"
)


def build_spotify():
    """Build the Spotify client from the current .env values.

    Returns None when credentials are missing so the rest of the dashboard
    still works before setup has been run.
    """

    values = config.read_env()

    client_id = values.get("SPOTIPY_CLIENT_ID", "").strip()
    client_secret = values.get("SPOTIPY_CLIENT_SECRET", "").strip()
    redirect_uri = values.get("SPOTIPY_REDIRECT_URI", "").strip()

    if not client_id or not client_secret or not redirect_uri:
        return None

    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SPOTIFY_SCOPE,
            open_browser=True,
            cache_handler=CacheFileHandler(
                cache_path=str(config.CACHE_FILE)
            ),
        )
    )


spotify = build_spotify()


def spotify_ready():
    if spotify is None:
        raise HTTPException(
            503,
            "Spotify is not configured. Run the setup wizard or add "
            "credentials in Settings.",
        )
    return spotify


def rebuild_spotify():
    global spotify
    spotify = build_spotify()
    return spotify is not None


# --------------------------------------------------
# APP
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(spotify_loop())

    yield

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(lifespan=lifespan)


# --------------------------------------------------
# MAIN PAGE
# --------------------------------------------------

@app.get("/")
async def index():
    page = config.resource_path("index.html")

    if not page.is_file():
        raise HTTPException(
            500,
            "Bundled index.html is missing from the application resources.",
        )

    return FileResponse(str(page))


# --------------------------------------------------
# SPOTIFY LOGIN
# --------------------------------------------------

@app.get("/login")
async def login():
    client = spotify_ready()
    return RedirectResponse(client.auth_manager.get_authorize_url())


@app.get("/callback")
async def callback(code: str):
    client = spotify_ready()

    try:
        # Exchange the code for a token and store it in the local cache.
        client.auth_manager.get_access_token(code, check_cache=False)
    except Exception as error:
        print("Spotify login error:", error)
        raise HTTPException(400, "Spotify login failed.") from None

    return RedirectResponse("/")


# --------------------------------------------------
# SPOTIFY CONTROLS
# --------------------------------------------------

@app.post("/api/play-pause")
async def play_pause():
    try:
        playback = spotify_ready().current_playback()

        if playback and playback.get("is_playing"):
            spotify.pause_playback()
        else:
            spotify.start_playback()

        return {"success": True}

    except HTTPException:
        raise

    except Exception as e:
        print("Play/pause error:", e)

        return {
            "success": False,
            "error": str(e),
        }


@app.post("/api/next")
async def next_track():
    try:
        spotify_ready().next_track()

        return {"success": True}

    except HTTPException:
        raise

    except Exception as e:
        print("Next track error:", e)

        return {
            "success": False,
            "error": str(e),
        }


@app.post("/api/previous")
async def previous_track():
    try:
        spotify_ready().previous_track()

        return {"success": True}

    except HTTPException:
        raise

    except Exception as e:
        print("Previous track error:", e)

        return {
            "success": False,
            "error": str(e),
        }


# --------------------------------------------------
# WEATHER
# --------------------------------------------------

@app.get("/api/weather")
async def weather():
    settings = config.load_settings()

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": settings["WEATHER_LAT"],
        "longitude": settings["WEATHER_LON"],

        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "wind_speed_10m,"
            "wind_direction_10m,"
            "surface_pressure,"
            "visibility,"
            "uv_index,"
            "weather_code"
        ),

        "daily": (
            "weather_code,"
            "temperature_2m_max,"
            "temperature_2m_min"
        ),

        "temperature_unit": settings["WEATHER_UNITS"],
        "wind_speed_unit": (
            "mph" if settings["WEATHER_UNITS"] == "fahrenheit" else "kmh"
        ),
        "timezone": settings["WEATHER_TIMEZONE"],
        "forecast_days": settings["FORECAST_DAYS"],
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()
        data["settings"] = {
            "label": settings["WEATHER_LABEL"],
            "units": settings["WEATHER_UNITS"],
            "forecast_days": settings["FORECAST_DAYS"],
        }

        return data

    except Exception as e:

        print("Weather error:", e)

        return {
            "error": str(e)
        }


# --------------------------------------------------
# MBTA TRANSIT
# --------------------------------------------------

MBTA_BASE_URL = "https://api-v3.mbta.com"

STATION_NAMES = {
    "place-WML-0081": "Newtonville",
    "place-WML-0040": "Boston Landing",
    "place-WML-0038": "Lansdowne",
    "place-WML-0050": "Back Bay",
    "place-WML-0078": "West Newton",
    "place-WML-0075": "Auburndale",
}


@app.get("/api/transit")
async def transit(stop_id: str | None = None):
    settings = config.load_settings()

    stop = (stop_id or settings["TRANSIT_DEFAULT_STOP"]).strip()

    if not config.STOP_ID.fullmatch(stop):
        raise HTTPException(400, "Invalid stop ID.")

    url = f"{MBTA_BASE_URL}/predictions"

    params = {
        "filter[stop]": stop,
        "include": "route,trip",
        "sort": "departure_time",
        "page[limit]": settings["TRANSIT_DEPARTURE_LIMIT"],
    }

    headers = {}
    api_key = config.read_env().get("MBTA_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    try:

        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        included = {
            item["id"]: item
            for item in data.get("included", [])
        }

        departures = []

        for prediction in data.get("data", []):

            attributes = prediction.get(
                "attributes",
                {}
            )

            relationships = prediction.get(
                "relationships",
                {}
            )

            route_data = relationships.get(
                "route",
                {}
            ).get("data")

            trip_data = relationships.get(
                "trip",
                {}
            ).get("data")

            route = (
                included.get(
                    route_data["id"]
                )
                if route_data
                else None
            )

            trip = (
                included.get(
                    trip_data["id"]
                )
                if trip_data
                else None
            )

            route_attributes = (
                route.get(
                    "attributes",
                    {}
                )
                if route
                else {}
            )

            trip_attributes = (
                trip.get(
                    "attributes",
                    {}
                )
                if trip
                else {}
            )

            departures.append({

                "departure_time":
                    attributes.get(
                        "departure_time"
                    ),

                "arrival_time":
                    attributes.get(
                        "arrival_time"
                    ),

                "route_id":
                    route.get("id")
                    if route
                    else None,

                "route_name":
                    route_attributes.get(
                        "long_name"
                    ),

                "route_short_name":
                    route_attributes.get(
                        "short_name"
                    ),

                "trip_headsign":
                    trip_attributes.get(
                        "headsign"
                    ),

                "status":
                    attributes.get(
                        "status"
                    ),

                "schedule_relationship":
                    attributes.get(
                        "schedule_relationship"
                    ),
            })

        return {
            "stop": STATION_NAMES.get(stop, stop),
            "stop_id": stop,
            "departures": departures,
        }

    except Exception as e:

        print(
            "MBTA error:",
            e
        )

        raise HTTPException(
            502,
            "Unable to retrieve transit data: " + str(e),
        ) from None


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

def settings_payload() -> dict:
    """Everything the settings page needs, with no secret values."""

    return {
        "settings": config.public_settings(),
        "secrets": config.secret_status(),
        "stations": [
            {"id": stop, "name": name}
            for stop, name in STATION_NAMES.items()
        ],
        "env_file": str(config.ENV_FILE),
    }


@app.get("/api/settings")
async def get_settings():
    return settings_payload()


@app.post("/api/settings")
async def save_settings(payload: dict):
    try:
        updates = config.validate_settings_patch(payload)
    except config.ConfigError as error:
        raise HTTPException(400, str(error)) from None

    config.write_env(updates)

    restart_required = any(
        key in ("SERVER_HOST", "SERVER_PORT")
        for key in updates
    )

    response = settings_payload()
    response["success"] = True
    response["restart_required"] = restart_required
    return response


@app.post("/api/settings/secrets")
async def save_secrets(payload: dict):
    try:
        updates = config.validate_secret_patch(payload)
    except config.ConfigError as error:
        raise HTTPException(400, str(error)) from None

    if updates:
        config.write_env(updates)

    reconnected = False
    if any(key.startswith("SPOTIPY_") for key in updates):
        reconnected = rebuild_spotify()

    return {
        "success": True,
        "secrets": config.secret_status(),
        "reconnected": reconnected,
        "restart_required": False,
    }


@app.post("/api/settings/reset")
async def reset_settings():
    config.write_env(config.DEFAULT_SETTINGS)

    response = settings_payload()
    response["success"] = True
    response["restart_required"] = False
    return response


@app.get("/api/health")
async def health():
    versions = {}
    for package in (
        "fastapi",
        "uvicorn",
        "requests",
        "python-dotenv",
        "spotipy",
        "websockets",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "missing"

    settings = config.load_settings()

    return {
        "status": "ok",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "versions": versions,
        "spotify": "configured" if spotify is not None else "not configured",
        "mbta_key": (
            "configured"
            if config.secret_status()["MBTA_API_KEY"]
            else "not configured"
        ),
        "weather_location": settings["WEATHER_LABEL"],
        "default_stop": settings["TRANSIT_DEFAULT_STOP"],
        "runtime": config.runtime_info(),
    }


@app.get("/api/server-info")
async def server_info():
    """Runtime layout information, with no credential values."""

    info = config.runtime_info()
    info["server"] = {
        "host": config.load_settings()["SERVER_HOST"],
        "port": config.load_settings()["SERVER_PORT"],
    }
    return info


# --------------------------------------------------
# WEBSOCKET
# --------------------------------------------------

@app.websocket("/ws")
async def websocket(ws: WebSocket):

    await ws.accept()

    clients.add(ws)

    if current_song is not None:

        await ws.send_json(
            current_song
        )

    try:

        while True:

            await ws.receive_text()

    except Exception:

        clients.discard(ws)


# --------------------------------------------------
# BROADCAST
# --------------------------------------------------

async def broadcast(data):

    dead = []

    for client in clients:

        try:

            await client.send_json(
                data
            )

        except Exception:

            dead.append(client)

    for client in dead:

        clients.discard(client)


# --------------------------------------------------
# SPOTIFY POLLING
# --------------------------------------------------

async def spotify_loop():

    global current_song

    last_track_id = None

    while True:

        try:

            client = spotify

            if client is None:
                await asyncio.sleep(1)
                continue

            current = (
                client.current_playback()
            )

            if (
                current
                and current.get("item")
            ):

                track = current["item"]

                track_id = track["id"]

                current_song = {

                    "type":
                        "now_playing",

                    "playing":
                        current["is_playing"],

                    "title":
                        track["name"],

                    "artist":
                        ", ".join(
                            artist["name"]
                            for artist
                            in track["artists"]
                        ),

                    "album":
                        track["album"]["name"],

                    "album_art":
                        (
                            track["album"]["images"][0]["url"]
                            if track["album"]["images"]
                            else None
                        ),

                    "progress_ms":
                        current["progress_ms"] or 0,

                    "duration_ms":
                        track["duration_ms"] or 0,
                }

                if (
                    track_id
                    != last_track_id
                ):

                    print(
                        "Playing: "
                        f"{current_song['title']} "
                        "by "
                        f"{current_song['artist']}"
                    )

                    last_track_id = (
                        track_id
                    )

                await broadcast(
                    current_song
                )

        except Exception as e:

            print(
                "Spotify error:",
                e
            )

        await asyncio.sleep(
            config.load_settings()["SPOTIFY_POLL_SECONDS"]
        )
