# i used assGPT because i cant code shit on my own

# MyDeskThing Installation Instructions

This guide will get MyDeskThing running on your computer.

## Requirements

Before starting, make sure you have:

* A computer
* Python 3.10 or newer
* A Spotify account
* A Spotify Developer App
* An MBTA API key
* Internet access

---

# 1. Download MyDeskThing

Download or clone the MyDeskThing repository.

If you are using Git:

```bash
git clone <repository-url>
cd MyDeskThing
```

Or just download the project as a ZIP and extract it.

---

# 2. Install Python

Make sure Python is installed.

Run:

```bash
python --version
```

If that doesn't work, try:

```bash
python3 --version
```

You should see something similar to:

```text
Python 3.x.x
```

If Python isn't installed, install it from the official Python website.

---

# 3. Install the Required Python Packages

Open a terminal inside the MyDeskThing folder.

Run:

```bash
pip install -r requirements.txt
```

If your computer uses `pip3` instead:

```bash
pip3 install -r requirements.txt
```

---

# 4. Create Your Spotify App

MyDeskThing uses Spotify's API to control Spotify and display the currently playing song.

Go to the Spotify Developer Dashboard and create an application.

You will need:

* Client ID
* Client Secret

Set the redirect URI to:

```text
http://127.0.0.1:8080/callback
```

Make sure the redirect URI in Spotify exactly matches the one above.

---

# 5. Get an MBTA API Key

MyDeskThing uses the MBTA API for transit information.

Get an MBTA API key and keep it somewhere safe.

You will need it for the `.env` file.

---

# 6. Create the `.env` File

Inside the MyDeskThing folder, create a file named:

```text
.env
```

Put your API credentials inside it:

```env
SPOTIPY_CLIENT_ID=YOUR_SPOTIFY_CLIENT_ID
SPOTIPY_CLIENT_SECRET=YOUR_SPOTIFY_CLIENT_SECRET
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8080/callback

MBTA_API_KEY=YOUR_MBTA_API_KEY
```

Replace the placeholder values with your actual credentials.

Do **not** share this file publicly.

Do **not** upload it to GitHub.

---

# 7. Start MyDeskThing

From the MyDeskThing folder, run:

```bash
uvicorn server:app --host 0.0.0.0 --port 8080
```

You should see something similar to:

```text
Uvicorn running on http://0.0.0.0:8080
```

---

# 8. Open MyDeskThing

Open your web browser and go to:

```text
http://localhost:8080
```

MyDeskThing should appear.

---

# 9. Spotify Login

The first time you use Spotify, MyDeskThing may open a browser window asking you to authorize the application.

Log into Spotify and approve the requested permissions.

After authorization, return to MyDeskThing.

Your currently playing Spotify track should appear automatically.

---

# 10. Using MyDeskThing

The top bar contains the available apps.

Currently available:

* Weather
* Spotify
* Transit

### Weather

Displays current weather conditions and a five-day forecast.

### Spotify

Displays:

* Song title
* Artist
* Album
* Album artwork
* Playback position
* Playback controls

### Transit

Displays upcoming MBTA departures.

You can select different stations from the station selector.

---

# Troubleshooting

## `python` is not recognized

Try:

```bash
python3 --version
```

If that also fails, Python is probably not installed or isn't in your PATH.

---

## `pip` is not recognized

Try:

```bash
python -m pip install -r requirements.txt
```

---

## Spotify authentication isn't working

Check that your Spotify redirect URI is exactly:

```text
http://127.0.0.1:8080/callback
```

Also check that your `.env` contains the correct Client ID and Client Secret.

---

## Transit isn't working

Check that:

1. Your MBTA API key is correct.
2. `MBTA_API_KEY` exists in `.env`.
3. Your computer has internet access.
4. MyDeskThing's backend is running.

You can test the transit API directly by opening:

```text
http://localhost:8080/api/transit
```

If it works, you should receive JSON containing the stop and upcoming departures.

---

## The page won't load

Make sure the server is running.

You should have a terminal window showing Uvicorn running on port `8080`.

Then open:

```text
http://localhost:8080
```

---

# Stopping MyDeskThing

To stop the server, go back to the terminal running MyDeskThing and press:

```text
Ctrl+C
```

That's it.

---

# Important

Keep your `.env` file private.

It contains credentials that should not be shared with other people.

For Git users, add `.env` to `.gitignore`:

```text
.env
```

```i aint gon lie i used ai
