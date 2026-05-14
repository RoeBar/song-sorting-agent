import base64
import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

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
    return result

def fetch_playlist_tracks(access_token: str, playlist_id: str) -> requests.Response:
    return requests.get(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )


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
    return {"message": "Prompt received successfully", "prompt": stored_prompt}


@app.get("/playlist_descriptions")
def playlist_descriptions(
    songLists: str | None = Query(default=None),
) -> dict[str, Any]:
    value: Any = songLists if songLists else 2
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
    
    selected_input_playlists = input_ids
    selected_output_playlists = output_ids
    
    print(f"Received selected playlists - Input: {input_ids}, Output: {output_ids}")
    
    return {
        "message": "Playlists selected successfully",
        "input": input_ids,
        "output": output_ids,
    }


if __name__ == "__main__":
    import uvicorn

    print("Server running on http://localhost:3000")
    uvicorn.run(app, host="127.0.0.1", port=3000)