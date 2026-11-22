"""Show the fallback admin passcode (used when ADMIN_PASSCODE is not set on the server, e.g. Render).

Run on your laptop:
    .venv/bin/python show_admin_code.py          # uses GOOGLE_API_KEY from .env
    .venv/bin/python show_admin_code.py --ask    # paste the server's key instead (typing is hidden)
The server builds its admin passcode from ITS OWN Gemini key, so if Render uses a different key than
your .env, use --ask and paste the key shown on Render > Environment > GOOGLE_API_KEY.
"""
import getpass
import os
import sys

from dotenv import load_dotenv

from paysetu_agent.auth import derived_admin_passcode

if "--ask" in sys.argv:
    key = getpass.getpass("Paste the GOOGLE_API_KEY from Render (hidden): ")
else:
    load_dotenv()
    key = os.getenv("GOOGLE_API_KEY", "")
code = derived_admin_passcode(key)
print(f"Admin passcode: {code}" if code else "No key given.")
