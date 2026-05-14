import os
import argparse
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("API_KEY is not set. Add it to your .env file.")
def sort_songs(playlists_json_str, songs_json_str):
    # Securely load the API key from environment variables
    genai.configure(api_key=api_key)

    # Assign the model its precise role and rules using System Instructions
    system_instruction = """
    You are an automated song sorting agent.
    Your task is to receive a list of songs and sort them into target playlists based on their descriptions.

    Sorting Rules:
    1. Multiple Matches: A single song can be added to multiple playlists if it fits the criteria for more than one list.
    2. Exclusion: If a song does not fit the criteria for any of the provided playlists, it is completely excluded and not added to any list.

    Expected Output:
    Return a strict, raw JSON object. The keys of this JSON object must be the `playlist_id`s, and the values must be arrays containing the `song_id`s of the songs that were matched to that specific playlist.
    """

    # Initialize the specific model with the system instructions
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_instruction
    )

    # Prepare the prompt with the raw JSON string inputs
    prompt = f"""
    Target Playlists:
    {playlists_json_str}

    Songs:
    {songs_json_str}
    """

    # Configure the API request to return a clean JSON format
    generation_config = genai.GenerationConfig(
        response_mime_type="application/json"
    )

    # Generate the structured output
    response = model.generate_content(
        prompt,
        generation_config=generation_config
    )

    # Return the raw JSON object
    return response.text


if __name__ == "__main__":
    # Accept the two arguments directly as raw JSON strings
    parser = argparse.ArgumentParser(description="Automated Song Sorting Agent")
    parser.add_argument("playlists", type=str, help="Raw JSON string of target playlists")
    parser.add_argument("songs", type=str, help="Raw JSON string of songs to be sorted")

    args = parser.parse_args()

    try:
        # Pass the parsed raw strings directly to the function
        sorted_json_result = sort_songs(args.playlists, args.songs)
        print(sorted_json_result)
    except Exception as e:
        print(f"An error occurred: {e}")