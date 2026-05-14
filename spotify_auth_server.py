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

prompts: list[dict[str, Any]] = []
playlists: list[Any] = []

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def fetch_user_playlists(access_token: str) -> requests.Response:
    return requests.get(
        "https://api.spotify.com/v1/me/playlists",
        headers={"Authorization": "Bearer " + access_token},
        timeout=30,
    )


def fetch_playlist_tracks(access_token: str, playlist_id: str) -> requests.Response:
    return requests.get(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
        headers={"Authorization": "Bearer " + access_token},
        timeout=30,
    )


@app.get("/login")
def login() -> RedirectResponse:
    scope = "user-read-private user-read-email user-library-read"
    auth_url = (
        "https://accounts.spotify.com/authorize"
        f"?response_type=code&client_id={CLIENT_ID}"
        f"&scope={quote(scope, safe='')}"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
    )
    return RedirectResponse(url=auth_url, status_code=302)


@app.get("/callback", response_model=None)
def callback(code: str | None = Query(default=None)) -> HTMLResponse | PlainTextResponse:
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
        token_js = json.dumps(access_token)
        html = f"""
            <script>
                try {{
                    window.opener.postMessage({{
                        type: 'SPOTIFY_AUTH_SUCCESS',
                        accessToken: {token_js}
                    }}, 'http://127.0.0.1:5500');
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


if __name__ == "__main__":
    import uvicorn

    print("Server running on http://localhost:3000")
    uvicorn.run(app, host="127.0.0.1", port=3000)
