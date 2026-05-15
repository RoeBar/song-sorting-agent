# Song Sorting Agent

An AI-powered tool that sorts tracks from your Spotify input playlists into target playlists using natural-language rules. You describe how songs should be grouped (or use **Magic sort** to infer rules from playlist names and track metadata), review AI-generated playlist descriptions, preview the sort, then apply changes to Spotify when you are ready.

## How it works

1. **Connect** — Log in with Spotify via OAuth (popup flow).
2. **Select playlists** — Choose source playlists (tracks to sort) and destination playlists (where sorted tracks go).
3. **Define criteria** — Enter a sorting prompt (e.g. “high energy for workouts, mellow for focus”) or click **Magic sort** to let the model suggest a prompt from your songs and target playlist names.
4. **Review descriptions** — The Playlist Architect agent writes a short rule per target playlist; you can edit them before continuing.
5. **Preview & apply** — The sorting agent assigns each song to zero or more playlists. Review the result, then confirm to update playlists in Spotify (or discard).

Songs that match no playlist are listed as **unmatched** and are not added anywhere.

## Tech stack

| Layer | Stack |
|--------|--------|
| Backend | Python, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/) |
| AI | [OpenRouter](https://openrouter.ai/) (OpenAI-compatible API; default model: `google/gemini-2.5-flash`) |
| Music | [Spotify Web API](https://developer.spotify.com/documentation/web-api) |
| Frontend | Static HTML/CSS/JS (serve with Live Server or any static file server) |

## Prerequisites

- Python 3.10+
- A [Spotify Developer](https://developer.spotify.com/dashboard) application
- An [OpenRouter](https://openrouter.ai/) API key

## Setup

### 1. Clone and install Python dependencies

```bash
cd song-sorting-agent
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file in the project root:

```env
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
OPENROUTER_API_KEY=your_openrouter_api_key

# Optional
OPENROUTER_MODEL=google/gemini-2.5-flash
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=
OPENROUTER_APP_TITLE=song-sorting-agent
```

### 3. Spotify app settings

In the Spotify Developer Dashboard for your app:

1. Add **Redirect URI**: `http://127.0.0.1:3000/callback`
2. Enable scopes used by the app (requested at login):
   - `user-read-private`, `user-read-email`, `user-library-read`
   - `playlist-read-private`, `playlist-read-collaborative`
   - `playlist-modify-public`, `playlist-modify-private`

The backend allows CORS from `http://127.0.0.1:5500` and `http://localhost:5500` (typical [Live Server](https://marketplace.visualstudio.com/items?itemName=ritwickdey.LiveServer) origins).

## Running the app

### Backend (required)

```bash
python spotify_auth_server.py
```

API runs at **http://127.0.0.1:3000** (also printed as `http://localhost:3000`).

### Frontend

Open the HTML pages with a local static server on port **5500** (recommended), for example:

- VS Code **Live Server** on the project folder, or  
- `npx serve . -p 5500`

Suggested flow:

1. `auth_page.html` — Spotify login  
2. `playlist_select.html` — pick input/output playlists  
3. `prompt_page.html` — enter criteria or Magic sort  
4. `playlist_descriptions.html` — edit descriptions, preview sort, apply to Spotify  

## CLI tools

These modules can be run standalone for testing or scripting:

**Generate playlist descriptions from a prompt**

```bash
python playlist_describer.py "Sort by energy level" '[{"playlist_id":"abc","name":"Chill"}]'
```

**Sort songs into playlists (JSON in → JSON out)**

```bash
python sort_songs.py '[{"playlist_id":"abc","name":"Chill","description":"..."}]' '[{"id":"track1","name":"Song","artists":["Artist"]}]'
```

**Magic sort: infer prompt + descriptions**

```bash
python auto_prompter.py --songs '[...]' --playlists '[{"playlist_id":"abc","name":"Chill"}]'
```

## Project structure

```
song-sorting-agent/
├── spotify_auth_server.py   # FastAPI app: OAuth, playlists, AI pipeline, Spotify writes
├── openrouter_llm.py        # OpenRouter chat client (JSON responses)
├── playlist_describer.py    # Playlist Architect: prompt → per-playlist descriptions
├── sort_songs.py            # Sorting agent: descriptions + songs → playlist_id → song_ids
├── auto_prompter.py         # Music Analyst + Playlist Architect (“magic sort”)
├── parsed_songs.py          # Track model used by the server
├── auth_page.html           # Login UI
├── playlist_select.html     # Playlist selection UI
├── prompt_page.html         # Criteria / magic sort UI
├── playlist_descriptions.html
├── *_script.js              # Frontend API calls
├── style.css
└── requirements.txt
```

## API overview

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/login` | Start Spotify OAuth (`?origin=` for postMessage target) |
| GET | `/callback` | OAuth redirect; returns token to opener window |
| GET | `/playlists` | List user playlists |
| POST | `/selected_playlists` | Store input/output selection; fetch tracks |
| POST | `/prompt` | Generate descriptions from user prompt |
| POST | `/magic_sort` | Auto-generate prompt and descriptions |
| GET | `/playlist_descriptions` | Fetch generated description rows |
| POST | `/submit_descriptions` | Save edits, run sort, return preview |
| POST | `/execute_pending_sort` | Write sorted tracks to Spotify |
| POST | `/reject_pending_sort` | Discard pending Spotify update |

## Notes

- **Confirm before apply** — Sorting only updates Spotify after you call execute on the descriptions page; until then changes are preview-only.
- **Replacing playlist contents** — Execute replaces each target playlist’s tracks with the sorted set (empty playlists are cleared).
- **Prompt injection** — `playlist_describer` includes guardrails to reject unrelated or injection-style prompts.
- **Secrets** — Never commit `.env`; it is listed in `.gitignore`.

## License

ISC (see `package.json` if present; Python components are project-local).
