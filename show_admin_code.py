"""Show the fallback admin passcode (used when ADMIN_PASSCODE is not set on the server, e.g. Render).

Run on your laptop:  .venv/bin/python show_admin_code.py
It reads GOOGLE_API_KEY from .env - the same key the server uses - and prints the admin passcode
made from it. Only someone with the key can do this.
"""
import os

from dotenv import load_dotenv

from paysetu_agent.auth import derived_admin_passcode

load_dotenv()
code = derived_admin_passcode(os.getenv("GOOGLE_API_KEY", ""))
print(f"Fallback admin passcode: {code}" if code else "GOOGLE_API_KEY not found in .env")
