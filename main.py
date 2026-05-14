import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("API_KEY is not set. Add it to your .env file.")

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

system_instruction = """
You are an advanced automated song sorting agent. 
Your task is to receive a JSON array of songs and a list of target playlists with their descriptions. You must sort the songs into the appropriate playlists based on their attributes and the playlist descriptions.

Rules for sorting:
1. A song can be added to multiple playlists if it matches the criteria for more than one playlist.
2. If a song does not match the criteria of ANY playlist, completely exclude it from the output.
3. Your output must be strictly in JSON format. The JSON object should contain the playlist names as keys, and the values should be arrays of the matched songs.
4. Do not include any conversational text or explanations; output only the valid JSON object.
"""

model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    system_instruction=system_instruction
)
print(model.generate_content("hello world"))