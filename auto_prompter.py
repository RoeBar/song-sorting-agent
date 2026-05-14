import argparse
import json
import sys

from dotenv import load_dotenv

from openrouter_llm import chat_json
from playlist_describer import create_playlist_descriptions

load_dotenv()

_MUSIC_ANALYST_SYSTEM_INSTRUCTION = """
You are a strict Music Analyst.
Your ONLY task is to read the provided list of songs and the provided target playlists (by name and count), then decide the single best natural-language sorting rule that maps those songs into those specific playlists.

You MUST:
- Ground the rule in the actual playlist names and the exact number of target playlists given in the input. Name the playlists when it clarifies the mapping.
- Prefer criteria that clearly follow from those playlist names (themes, moods, genres implied by names, etc.).
- Avoid generic sorting rules (for example "by decade" or "by BPM") unless they are clearly justified by the given playlist names.

You MUST NOT output anything other than the required JSON object shape specified in the user message.
"""


def _parse_and_canonicalize_json_array(label: str, raw: str) -> tuple[list, str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON for {label}: {e}") from e
    if not isinstance(parsed, list):
        raise ValueError(f"{label} must be a JSON array, got {type(parsed).__name__}")
    canonical = json.dumps(parsed, ensure_ascii=False)
    return parsed, canonical


def generate_suggested_prompt(
    songs_json_canonical: str,
    songs_count: int,
    playlists_json_canonical: str,
    playlists_count: int,
) -> str:
    user_message = f"""
Output EXACTLY one JSON object and nothing else. The object must have exactly this shape:
{{"suggested_prompt": "The single best sorting instruction here"}}

The suggested_prompt must be one clear natural-language instruction a downstream agent can use to sort the given songs into the given playlists.

Facts you must respect:
- Number of songs provided: {songs_count}
- Number of target playlists: {playlists_count}

Songs (JSON):
{songs_json_canonical}

Target playlists (JSON):
{playlists_json_canonical}
"""

    text = chat_json(_MUSIC_ANALYST_SYSTEM_INSTRUCTION, user_message)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Music Analyst returned invalid JSON: {e}\nRaw: {text!r}") from e

    if not isinstance(payload, dict):
        raise RuntimeError(f"Music Analyst JSON must be an object, got {type(payload).__name__}. Raw: {text!r}")

    suggested = payload.get("suggested_prompt")
    if not isinstance(suggested, str) or not suggested.strip():
        raise RuntimeError(f"Missing or invalid 'suggested_prompt' in response. Raw: {text!r}")

    return suggested.strip()


def run_auto_prompter(songs_json: str, playlists_json: str) -> tuple[str, str]:
    songs_parsed, songs_canonical = _parse_and_canonicalize_json_array("songs", songs_json)
    playlists_parsed, playlists_canonical = _parse_and_canonicalize_json_array(
        "playlists", playlists_json
    )

    songs_count = len(songs_parsed)
    playlists_count = len(playlists_parsed)

    suggested_prompt = generate_suggested_prompt(
        songs_json_canonical=songs_canonical,
        songs_count=songs_count,
        playlists_json_canonical=playlists_canonical,
        playlists_count=playlists_count,
    )

    updated_playlists_json = create_playlist_descriptions(
        suggested_prompt,
        playlists_canonical,
    )
    return suggested_prompt, updated_playlists_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-generate a sorting prompt from songs + target playlists, then run playlist_describer.",
    )
    parser.add_argument(
        "--songs",
        required=True,
        help="Raw JSON string: array of songs (e.g. song_id, song_name, artist).",
    )
    parser.add_argument(
        "--playlists",
        required=True,
        help="Raw JSON string: array of target playlists (e.g. playlist_id, name).",
    )
    args = parser.parse_args()

    try:
        suggested_prompt, updated_playlists_json = run_auto_prompter(
            args.songs,
            args.playlists,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print("--- Generated sorting prompt (Music Analyst) ---")
    print(suggested_prompt)
    print()
    print("--- Playlist descriptions JSON (Playlist Architect) ---")
    print(updated_playlists_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
