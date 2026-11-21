"""Quick setup check: is the API key present, and which Gemini models can it use?

Run:  .venv/bin/python check_setup.py
It never prints the key itself.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

key = os.getenv("GOOGLE_API_KEY", "").strip()
if not key or key == "your-key-here":
    sys.exit("GOOGLE_API_KEY is missing. Copy .env.example to .env and add your key.")
print(f"GOOGLE_API_KEY found ({len(key)} characters).")

try:
    from google import genai

    client = genai.Client(api_key=key)
    names = [m.name for m in client.models.list()]
except Exception as exc:  # bad key, no network, etc.
    sys.exit(f"Could not reach Gemini: {exc}")

flash_lite = [n for n in names if "flash-lite" in n]
embed = [n for n in names if "embedding" in n]
print("Flash-Lite models:", ", ".join(flash_lite) or "none found")
print("Embedding models:", ", ".join(embed) or "none found")
