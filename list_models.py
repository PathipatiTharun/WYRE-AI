"""Shows which Gemini models your API key can use:  python list_models.py"""
import os
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
for m in client.models.list():
    if "generateContent" in (getattr(m, "supported_actions", None) or []):
        print(m.name.replace("models/", ""))
