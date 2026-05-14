import base64
import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from parsed_songs import Parsed_song
import requests
from dotenv import load_dotenv
from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

load_dotenv()

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = "http://127.0.0.1:3000/callback"

ALLOWED_CLIENT_ORIGINS = frozenset(
    {"http://127.0.0.1:5500", "http://localhost:5500"}
)

prompts: list[dict[str, Any]] = []
playlists: list[Any] = []
stored_access_token: str | None = None
selected_input_playlists: list[str] = []
selected_output_playlists: list[str] = []
# store the playlist song dicttionary here after fetching, so the agent can access without needing to wait for the client to resend
playlist_songs_dict: dict[str, Any] = {}

playlist_items_urls: dict[str, str] = {}

songs_to_playlist_mapping: dict[str, list[str]] = {}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_CLIENT_ORIGINS),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def fetch_user_playlists(access_token: str) -> requests.Response:
    url = "https://api.spotify.com/v1/me/playlists" 
    
    result = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )
    
    print(result.text)
    # also store the playlists name and items in a dict 
    for playlist in result.json().get("items", []):
        playlist_id = playlist["id"]
        playlist_name = playlist["name"]
        playlist_items_urls[playlist_id] = playlist["href"]
    return result

def fetch_playlist_tracks(access_token: str, playlist_id: str) -> requests.Response:
    response = requests.get(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )
    # also build the song to playlist mapping
    for item in response.json().get("items", []):
        song_id = item["track"]["id"]
        if song_id not in songs_to_playlist_mapping:
            songs_to_playlist_mapping[song_id] = []
        songs_to_playlist_mapping[song_id].append(playlist_id)
    return response


def post_message_target(state: str | None) -> str:
    if state and state in ALLOWED_CLIENT_ORIGINS:
        return state
    return "http://127.0.0.1:5500"


@app.get("/login")
def login(origin: str | None = Query(default=None)) -> RedirectResponse:
    scope = "user-read-private user-read-email user-library-read playlist-read-private playlist-read-collaborative"
    oauth_state = post_message_target(origin)
    auth_url = (
        "https://accounts.spotify.com/authorize"
        f"?response_type=code&client_id={CLIENT_ID}"
        f"&scope={quote(scope, safe='')}"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
        f"&state={quote(oauth_state, safe='')}"
    )
    return RedirectResponse(url=auth_url, status_code=302)


@app.get("/callback", response_model=None)
def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> HTMLResponse | PlainTextResponse:
    if not code:
        return PlainTextResponse("Authentication Error: missing code", status_code=400)
    target_origin = post_message_target(state)
    global stored_access_token
    try:
        basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        token_resp = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic " + basic,
            },
            timeout=30,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]
        stored_access_token = access_token
        token_js = json.dumps(access_token)
        target_js = json.dumps(target_origin)
        html = f"""
            <script>
                try {{
                    window.opener.postMessage({{
                        type: 'SPOTIFY_AUTH_SUCCESS',
                        accessToken: {token_js}
                    }}, {target_js});
                    window.close();
                }} catch (e) {{
                    console.error("Message failed:", e);
                    window.close();
                }}
            </script>
        """
        return HTMLResponse(content=html)
    except Exception:
        return PlainTextResponse("Authentication Error", status_code=200)


@app.post("/prompt", response_model=None)
def prompt(body: dict[str, Any] = Body(...)) -> dict[str, Any] | JSONResponse:
    prompt_text = body.get("prompt") or body.get("userPrompt")
    if not prompt_text or not str(prompt_text).strip():
        return JSONResponse(
            status_code=400,
            content={"message": "Prompt is required"},
        )

    stored_prompt = {
        "text": str(prompt_text).strip(),
        "createdAt": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
    }
    prompts.append(stored_prompt)
    print("Received prompt:", stored_prompt["text"])
    # WIP: Wait for the agent to fetch the descriptions, then send to the client
    return {"message": "Prompt received successfully", "prompt": stored_prompt}


@app.get("/playlist_descriptions")
def playlist_descriptions(
    songLists: str | None = Query(default=None),
) -> dict[str, Any]:
    value: Any = songLists if songLists else len(selected_output_playlists)
    return {"songLists": value}


@app.get("/playlists", response_model=None)
def get_playlists() -> dict[str, Any] | JSONResponse:
    if not stored_access_token:
        return JSONResponse(
            status_code=401,
            content={"message": "Not authenticated. Complete Spotify login first."},
        )
    spotify_resp = fetch_user_playlists(stored_access_token)
    try:
        body = spotify_resp.json()
    except Exception:
        body = {"message": spotify_resp.text}
    if not spotify_resp.ok:
        return JSONResponse(status_code=spotify_resp.status_code, content=body)
    return body


@app.get("/select_playlist_tracks", )
def select_playlist_tracks() -> dict[str, Any]:
    return {}


@app.post("/selected_playlists", response_model=None)
def submit_selected_playlists(body: dict[str, Any] = Body(...)) -> dict[str, Any] | JSONResponse:
    global selected_input_playlists, selected_output_playlists
    
    input_ids = body.get("input", [])
    output_ids = body.get("output", [])
    
    if not isinstance(input_ids, list) or not isinstance(output_ids, list):
        return JSONResponse(
            status_code=400,
            content={"message": "input and output must be lists of playlist IDs"},
        )
    
    # store the raw selections as received (could be list[str] or list[dict])
    selected_input_playlists = input_ids
    selected_output_playlists = output_ids

    if not stored_access_token:
        return JSONResponse(
            status_code=401,
            content={"message": "Not authenticated. Complete Spotify login first."},
        )

    # now fetch the tracks for each input playlist and store in the dict
    for entry in input_ids:
        # accept either a plain id string or an object like {id:..., name:...}
        playlist_id = entry.get("id") if isinstance(entry, dict) else entry
        if not playlist_id:
            print("Skipping invalid playlist entry:", entry)
            continue

        tracks_resp = fetch_playlist_tracks(stored_access_token, playlist_id)
        try:
            raw_items = tracks_resp.json().get("items", [])
        except Exception:
            raw_items = []

        # Normalize items into a list of simple track dicts for easier use by the agent
        parsed_tracks: list[Parsed_song] = []
        for itm in raw_items:
            track = None
            if isinstance(itm, dict):
                # Spotify sometimes returns the track under 'track', sometimes under 'item'
                track = itm.get("track") or itm.get("item") or None
            if not track or not isinstance(track, dict):
                continue
            track_id = track.get("id")
            if not track_id:
                continue

            artists = [a.get("name") for a in track.get("artists", []) if isinstance(a, dict)]
            album = track.get("album") or {}
            album_id = album.get("id") if isinstance(album, dict) else None

            parsed = Parsed_song(
                id=track_id,
                name=track.get("name"),
                artists=artists,
                album_id=album_id,
                duration_ms=track.get("duration_ms"),
                external_urls=track.get("external_urls"),
                uri=track.get("uri"),
            )
            parsed_tracks.append(parsed)

            # update songs_to_playlist_mapping (avoid duplicates)
            if track_id not in songs_to_playlist_mapping:
                songs_to_playlist_mapping[track_id] = []
            if playlist_id not in songs_to_playlist_mapping[track_id]:
                songs_to_playlist_mapping[track_id].append(playlist_id)

        print(f"Fetched {len(parsed_tracks)} tracks for playlist {playlist_id}:")
        print(parsed_tracks)
        playlist_songs_dict[playlist_id] = parsed_tracks
    
    
    print(f"Received selected playlists - Input: {input_ids}, Output: {output_ids}")

    # now create a list of songs to sort from the input playlists (flatten all tracks from all input playlists into one list)
    songs_to_sort = []
    for pid in input_ids:
        # accept either a plain id string or an object like {id:..., name:...}
        playlist_id = pid.get("id") if isinstance(pid, dict) else pid
        if not playlist_id:
            continue
        songs = playlist_songs_dict.get(playlist_id, [])
        songs_to_sort.extend(songs)
    
    return {
        "message": "Playlists selected successfully",
        "input": input_ids,
        "output": output_ids,
        "songs_to_sort": songs_to_sort,
    }


if __name__ == "__main__":
    import uvicorn

    print("Server running on http://localhost:3000")
    uvicorn.run(app, host="127.0.0.1", port=3000)