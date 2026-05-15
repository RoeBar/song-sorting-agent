import base64
import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from auto_prompter import run_auto_prompter
from parsed_songs import Parsed_song
from playlist_describer import create_playlist_descriptions
from sort_songs import sort_songs as run_song_sort
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
playlist_id_to_name: dict[str, str] = {}

# AI-generated rows: {playlist_id, name, description}; order matches output selection when possible
generated_playlist_descriptions: list[dict[str, Any]] = []
# User-confirmed text after playlist_descriptions.html submit
final_playlist_descriptions: dict[str, str] = {}

songs_to_playlist_mapping: dict[str, list[str]] = {}

# After a successful submit_descriptions sort: playlist_id -> Spotify track URIs to write on confirm
pending_execute_playlists: dict[str, list[str]] | None = None

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
        playlist_id_to_name[playlist_id] = playlist_name
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


def _normalize_playlist_id(entry: Any) -> str | None:
    if isinstance(entry, dict):
        pid = entry.get("id")
        return str(pid).strip() if pid else None
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    return None


def _song_to_llm_dict(s: Parsed_song) -> dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "artists": s.artists or [],
        "album_id": s.album_id,
        "duration_ms": s.duration_ms,
    }


def _collect_deduped_input_songs() -> tuple[list[dict[str, Any]], dict[str, Parsed_song]]:
    by_id: dict[str, Parsed_song] = {}
    for entry in selected_input_playlists:
        playlist_id = _normalize_playlist_id(entry)
        if not playlist_id:
            continue
        tracks = playlist_songs_dict.get(playlist_id, [])
        if not isinstance(tracks, list):
            continue
        for t in tracks:
            if not isinstance(t, Parsed_song):
                continue
            tid = t.id
            if not tid:
                continue
            tid_s = str(tid)
            if tid_s not in by_id:
                by_id[tid_s] = t
    return [_song_to_llm_dict(s) for s in by_id.values()], by_id


def _ordered_playlist_descriptions_from_parsed(
    parsed: list[Any], output_ids: list[str]
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in parsed:
        if not isinstance(row, dict):
            continue
        rid = row.get("playlist_id")
        if not rid:
            continue
        rid_s = str(rid)
        by_id[rid_s] = {
            "playlist_id": rid_s,
            "name": row.get("name")
            or playlist_id_to_name.get(rid_s, "Unknown playlist"),
            "description": (row.get("description") or "").strip(),
        }

    ordered: list[dict[str, Any]] = []
    for pid in output_ids:
        if pid in by_id:
            ordered.append(by_id[pid])
        else:
            ordered.append(
                {
                    "playlist_id": pid,
                    "name": playlist_id_to_name.get(pid, "Unknown playlist"),
                    "description": "",
                }
            )
    return ordered


def post_message_target(state: str | None) -> str:
    if state and state in ALLOWED_CLIENT_ORIGINS:
        return state
    return "http://127.0.0.1:5500"


def _track_uri_for_sort_id(song_lookup: dict[str, Parsed_song], sid: Any) -> str | None:
    sid_s = str(sid) if sid is not None else ""
    if not sid_s:
        return None
    ps = song_lookup.get(sid_s)
    if ps and ps.uri:
        return str(ps.uri)
    return f"spotify:track:{sid_s}"


def _spotify_replace_then_append_tracks(
    access_token: str, playlist_id: str, uris: list[str]
) -> requests.Response | None:
    """Replace playlist contents with uris (batched: first chunk replaces, rest POST)."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if not uris:
        return None
    chunks = [uris[i : i + 100] for i in range(0, len(uris), 100)]
    first = chunks[0]
    r = requests.put(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
        headers=headers,
        json={"uris": first},
        timeout=60,
    )
    if not r.ok:
        return r
    for chunk in chunks[1:]:
        r2 = requests.post(
            f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
            headers=headers,
            json={"uris": chunk},
            timeout=60,
        )
        if not r2.ok:
            return r2
    return r


@app.get("/login")
def login(origin: str | None = Query(default=None)) -> RedirectResponse:
    scope = (
        "user-read-private user-read-email user-library-read "
        "playlist-read-private playlist-read-collaborative "
        "playlist-modify-public playlist-modify-private"
    )
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
    global generated_playlist_descriptions

    prompt_text = body.get("prompt") or body.get("userPrompt")
    if not prompt_text or not str(prompt_text).strip():
        return JSONResponse(
            status_code=400,
            content={"message": "Prompt is required"},
        )

    if not stored_access_token:
        return JSONResponse(
            status_code=401,
            content={"message": "Not authenticated. Complete Spotify login first."},
        )

    if not selected_output_playlists:
        return JSONResponse(
            status_code=400,
            content={
                "message": "No output playlists selected. Complete playlist selection first.",
            },
        )

    stored_prompt = {
        "text": str(prompt_text).strip(),
        "createdAt": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
    }
    prompts.append(stored_prompt)
    print("Received prompt:", stored_prompt["text"])

    output_ids: list[str] = []
    for entry in selected_output_playlists:
        pid = _normalize_playlist_id(entry)
        if pid:
            output_ids.append(pid)

    if not output_ids:
        return JSONResponse(
            status_code=400,
            content={"message": "No valid output playlist IDs."},
        )

    target_for_model: list[dict[str, str]] = []
    for pid in output_ids:
        name = playlist_id_to_name.get(pid, "Unknown playlist")
        target_for_model.append({"playlist_id": pid, "name": name})

    try:
        raw = create_playlist_descriptions(
            stored_prompt["text"], json.dumps(target_for_model)
        )
        parsed = json.loads(raw)
    except RuntimeError as e:
        return JSONResponse(status_code=502, content={"message": str(e)})
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=502,
            content={"message": "Model returned invalid JSON."},
        )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"message": f"Description generation failed: {e}"},
        )

    if not isinstance(parsed, list) or len(parsed) == 0:
        return JSONResponse(
            status_code=502,
            content={"message": "Empty model response."},
        )

    if (
        len(parsed) == 1
        and isinstance(parsed[0], dict)
        and parsed[0].get("error")
    ):
        return JSONResponse(
            status_code=400,
            content={"message": parsed[0].get("error", "Request rejected.")},
        )

    ordered = _ordered_playlist_descriptions_from_parsed(parsed, output_ids)
    generated_playlist_descriptions = ordered
    return {"ok": True, "count": len(ordered)}


@app.post("/magic_sort", response_model=None)
def magic_sort() -> dict[str, Any] | JSONResponse:
    global generated_playlist_descriptions, prompts

    if not stored_access_token:
        return JSONResponse(
            status_code=401,
            content={"message": "Not authenticated. Complete Spotify login first."},
        )

    if not selected_output_playlists:
        return JSONResponse(
            status_code=400,
            content={
                "message": "No output playlists selected. Complete playlist selection first.",
            },
        )

    output_ids: list[str] = []
    for entry in selected_output_playlists:
        pid = _normalize_playlist_id(entry)
        if pid:
            output_ids.append(pid)

    if not output_ids:
        return JSONResponse(
            status_code=400,
            content={"message": "No valid output playlist IDs."},
        )

    songs_list, _ = _collect_deduped_input_songs()
    if not songs_list:
        return JSONResponse(
            status_code=400,
            content={
                "message": "No songs loaded from input playlists. Go back and select input playlists with tracks first.",
            },
        )

    target_for_model: list[dict[str, str]] = []
    for pid in output_ids:
        name = playlist_id_to_name.get(pid, "Unknown playlist")
        target_for_model.append({"playlist_id": pid, "name": name})

    try:
        suggested_prompt, raw = run_auto_prompter(
            json.dumps(songs_list),
            json.dumps(target_for_model),
        )
        parsed = json.loads(raw)
    except RuntimeError as e:
        return JSONResponse(status_code=502, content={"message": str(e)})
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=502,
            content={"message": "Model returned invalid JSON."},
        )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"message": f"Magic sort failed: {e}"},
        )

    if not isinstance(parsed, list) or len(parsed) == 0:
        return JSONResponse(
            status_code=502,
            content={"message": "Empty model response."},
        )

    if (
        len(parsed) == 1
        and isinstance(parsed[0], dict)
        and parsed[0].get("error")
    ):
        return JSONResponse(
            status_code=400,
            content={"message": parsed[0].get("error", "Request rejected.")},
        )

    ordered = _ordered_playlist_descriptions_from_parsed(parsed, output_ids)
    generated_playlist_descriptions = ordered

    stored_prompt = {
        "text": suggested_prompt,
        "createdAt": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
    }
    prompts.append(stored_prompt)
    print("Magic sort suggested prompt:", stored_prompt["text"])

    return {
        "ok": True,
        "count": len(ordered),
        "suggested_prompt": suggested_prompt,
    }


@app.get("/playlist_descriptions")
def playlist_descriptions() -> JSONResponse:
    return JSONResponse(content={"descriptions": generated_playlist_descriptions})


@app.post("/submit_descriptions", response_model=None)
def submit_descriptions(body: dict[str, Any] = Body(...)) -> dict[str, Any] | JSONResponse:
    global final_playlist_descriptions, pending_execute_playlists

    rows = body.get("descriptions")
    if not isinstance(rows, list):
        return JSONResponse(
            status_code=400,
            content={"message": "descriptions must be a list"},
        )

    out: dict[str, str] = {}
    for item in rows:
        if not isinstance(item, dict):
            return JSONResponse(
                status_code=400,
                content={
                    "message": "Each entry must be an object with playlist_id and description",
                },
            )
        pid = item.get("playlist_id")
        desc = item.get("description", "")
        if pid is None or not str(pid).strip():
            return JSONResponse(
                status_code=400,
                content={"message": "Each entry needs a non-empty playlist_id"},
            )
        out[str(pid).strip()] = str(desc) if desc is not None else ""

    final_playlist_descriptions = out

    if not stored_access_token:
        return JSONResponse(
            status_code=401,
            content={"message": "Not authenticated. Complete Spotify login first."},
        )

    songs_list, song_lookup = _collect_deduped_input_songs()
    if not songs_list:
        return JSONResponse(
            status_code=400,
            content={
                "message": "No songs loaded from input playlists. Go back and select input playlists again.",
            },
        )

    output_ids_ordered: list[str] = []
    for entry in selected_output_playlists:
        pid = _normalize_playlist_id(entry)
        if pid and pid in out and pid not in output_ids_ordered:
            output_ids_ordered.append(pid)
    for pid in out:
        if pid not in output_ids_ordered:
            output_ids_ordered.append(pid)

    playlists_json: list[dict[str, str]] = []
    for pid in output_ids_ordered:
        playlists_json.append(
            {
                "playlist_id": pid,
                "name": playlist_id_to_name.get(pid, "Unknown playlist"),
                "description": out[pid],
            }
        )

    pending_execute_playlists = None

    try:
        raw_sort = run_song_sort(
            json.dumps(playlists_json),
            json.dumps(songs_list),
        )
        parsed_sort = json.loads(raw_sort)
    except RuntimeError as e:
        return JSONResponse(status_code=502, content={"message": str(e)})
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=502,
            content={"message": "Sort model returned invalid JSON."},
        )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"message": f"Song sorting failed: {e}"},
        )

    if not isinstance(parsed_sort, dict):
        return JSONResponse(
            status_code=502,
            content={"message": "Sort model returned invalid JSON shape."},
        )

    matched_union: set[str] = set()
    for v in parsed_sort.values():
        if isinstance(v, list):
            for sid in v:
                if sid is not None:
                    matched_union.add(str(sid))

    def _song_payload(ps: Parsed_song) -> dict[str, Any]:
        return {
            "id": ps.id,
            "name": ps.name,
            "artists": ps.artists or [],
            "uri": ps.uri,
        }

    result_playlists: list[dict[str, Any]] = []
    for pid in output_ids_ordered:
        ids = parsed_sort.get(pid)
        if not isinstance(ids, list):
            ids = []
        songs_out: list[dict[str, Any]] = []
        for sid in ids:
            sid_s = str(sid)
            ps = song_lookup.get(sid_s)
            if ps:
                songs_out.append(_song_payload(ps))
            else:
                songs_out.append(
                    {
                        "id": sid_s,
                        "name": None,
                        "artists": [],
                        "uri": f"spotify:track:{sid_s}",
                    }
                )
        result_playlists.append(
            {
                "playlist_id": pid,
                "name": playlist_id_to_name.get(pid, "Unknown playlist"),
                "songs": songs_out,
            }
        )

    pending: dict[str, list[str]] = {}
    for pid in output_ids_ordered:
        ids = parsed_sort.get(pid)
        if not isinstance(ids, list):
            ids = []
        uris: list[str] = []
        for sid in ids:
            u = _track_uri_for_sort_id(song_lookup, sid)
            if u:
                uris.append(u)
        pending[pid] = uris
    pending_execute_playlists = pending

    unmatched: list[dict[str, Any]] = []
    for sid, ps in song_lookup.items():
        if sid not in matched_union:
            unmatched.append(_song_payload(ps))

    return {
        "ok": True,
        "message": "Descriptions saved and songs sorted.",
        "result": {
            "playlists": result_playlists,
            "unmatched": unmatched,
        },
    }


@app.post("/execute_pending_sort", response_model=None)
def execute_pending_sort() -> dict[str, Any] | JSONResponse:
    global pending_execute_playlists, stored_access_token

    if not stored_access_token:
        return JSONResponse(
            status_code=401,
            content={"message": "Not authenticated. Complete Spotify login first."},
        )
    if not pending_execute_playlists:
        return JSONResponse(
            status_code=400,
            content={
                "message": "No pending sort to execute. Submit descriptions and wait for sorted results first.",
            },
        )

    headers = {
        "Authorization": f"Bearer {stored_access_token}",
        "Content-Type": "application/json",
    }
    errors: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []

    for pid, uris in pending_execute_playlists.items():
        name = playlist_id_to_name.get(pid, pid)
        if uris:
            r = _spotify_replace_then_append_tracks(stored_access_token, pid, uris)
            if r is not None and not r.ok:
                errors.append(
                    {
                        "playlist_id": pid,
                        "name": name,
                        "status": r.status_code,
                        "detail": r.text,
                    }
                )
                continue
        else:
            r_clear = requests.put(
                f"https://api.spotify.com/v1/playlists/{pid}/tracks",
                headers=headers,
                json={"uris": []},
                timeout=60,
            )
            if not r_clear.ok:
                errors.append(
                    {
                        "playlist_id": pid,
                        "name": name,
                        "status": r_clear.status_code,
                        "detail": r_clear.text,
                    }
                )
                continue
        updated.append({"playlist_id": pid, "name": name, "track_count": len(uris)})

    if errors:
        return JSONResponse(
            status_code=502,
            content={
                "ok": False,
                "message": "Some playlists could not be updated in Spotify.",
                "updated": updated,
                "errors": errors,
            },
        )

    pending_execute_playlists = None
    return {
        "ok": True,
        "message": "Playlists updated in Spotify.",
        "updated": updated,
    }


@app.post("/reject_pending_sort", response_model=None)
def reject_pending_sort() -> dict[str, Any]:
    global pending_execute_playlists

    pending_execute_playlists = None
    return {"ok": True, "message": "Pending sort discarded."}


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
    global generated_playlist_descriptions, final_playlist_descriptions
    global pending_execute_playlists

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
    generated_playlist_descriptions = []
    final_playlist_descriptions = {}
    pending_execute_playlists = None

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