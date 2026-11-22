"""Passcode checks, lockout after repeated wrong attempts, and admin identity.

Pure Python (no Streamlit), so it is fully unit-tested. The web app keeps one LoginGuard
per browser session for the customer passcode and one for the admin passcode.
This is demo-grade protection for a practice app, not production banking security.
"""
import hmac
import re
import time
from dataclasses import dataclass, field

MAX_ATTEMPTS = 5          # wrong tries allowed...
LOCK_SECONDS = 300        # ...then locked for 5 minutes


def passcode_matches(entered: str, expected: str) -> bool:
    """Constant-time comparison; an empty expected passcode never matches."""
    if not expected:
        return False
    return hmac.compare_digest((entered or "").strip().encode(), expected.strip().encode())


@dataclass
class LoginGuard:
    failures: int = 0
    locked_until: float = 0.0
    now: callable = field(default=time.time, repr=False)  # replaceable in tests

    def is_locked(self) -> bool:
        return self.now() < self.locked_until

    def seconds_left(self) -> int:
        return max(0, int(self.locked_until - self.now() + 0.999))

    def tries_left(self) -> int:
        return max(0, MAX_ATTEMPTS - self.failures)

    def attempt(self, entered: str, expected: str) -> str:
        """Returns "ok", "wrong" or "locked". Locked sessions are refused without checking."""
        if self.is_locked():
            return "locked"
        if passcode_matches(entered, expected):
            self.failures = 0
            return "ok"
        self.failures += 1
        if self.failures >= MAX_ATTEMPTS:
            self.failures = 0
            self.locked_until = self.now() + LOCK_SECONDS
            return "locked"
        return "wrong"


_NAME = re.compile(r"[^A-Za-z0-9 ._-]")


def clean_admin_name(name: str) -> str:
    """Admin display name for the audit log: letters, digits, space . _ - only, max 30 chars."""
    return _NAME.sub("", (name or "").strip())[:30].strip()


def admin_actor(state: dict) -> str:
    """Name of the signed-in admin, or raise PermissionError. Every admin action calls this first."""
    if not state.get("admin_ok") or not state.get("admin_name"):
        raise PermissionError("Admin sign-in required.")
    return f"{state['admin_name']} (admin)"


# ---------- finding passcodes on different hosts ----------
# Accepted spellings, so a small typo on the host does not lock the admin pages.
ALIASES = {
    "ADMIN_PASSCODE": ["ADMIN_PASSCODE", "ADMIN_PASSWORD", "ADMIN_PASS", "ADMIN_PASSKEY", "ADMIN_CODE"],
    "APP_PASSCODE": ["APP_PASSCODE", "APP_PASSWORD", "APP_PASS"],
}
SECRET_DIRS = ["/etc/secrets"]  # Render "Secret Files" land here


def _norm(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())


def _clean_value(value) -> str:
    v = str(value or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":  # someone typed the quotes too
        v = v[1:-1].strip()
    return v


def _from_files(names: set[str], dirs: list[str]) -> str:
    """Look in Render Secret Files: a file named like the setting, or a .env / secrets.toml file."""
    import tomllib
    from pathlib import Path

    for d in dirs:
        folder = Path(d)
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            try:
                if not f.is_file():
                    continue
                text = f.read_text(encoding="utf-8")
                if _norm(f.name) in names:
                    return _clean_value(text)
                if f.suffix == ".toml":
                    data = tomllib.loads(text)
                    for k, v in data.items():
                        if _norm(k) in names and _clean_value(v):
                            return _clean_value(v)
                elif f.name in (".env", "env", "secrets.env"):
                    for line in text.splitlines():
                        if "=" in line and _norm(line.split("=", 1)[0]) in names:
                            v = _clean_value(line.split("=", 1)[1])
                            if v:
                                return v
            except Exception:
                continue
    return ""


def find_setting(name: str, environ: dict, streamlit_secrets: dict | None = None,
                 secret_dirs: list[str] | None = None) -> str:
    """Find a passcode in Streamlit secrets, environment variables (any accepted spelling) or
    Render Secret Files. Returns "" if nowhere."""
    names = {_norm(n) for n in ALIASES.get(name, [name])}
    for source in (streamlit_secrets or {}, environ):
        for key, value in source.items():
            if _norm(key) in names and _clean_value(value):
                return _clean_value(value)
    return _from_files(names, SECRET_DIRS if secret_dirs is None else secret_dirs)


def similar_setting_names(environ: dict) -> list[str]:
    """Names (never values) of environment variables that look like passcodes - for error messages."""
    return sorted(k for k in environ if re.search(r"ADMIN|PASS|CODE", k.upper()))


def derived_admin_passcode(api_key: str) -> str:
    """Fallback admin passcode when ADMIN_PASSCODE is not configured on the host.

    Made one-way from the server's secret Gemini key, so only someone who has that key (the owner)
    can work it out; customers cannot, and the key cannot be recovered from it. Returns "" without a key.
    """
    import hashlib

    key = (api_key or "").strip()
    if not key:
        return ""
    return "admin-" + hashlib.sha256(("paysetu-admin:" + key).encode()).hexdigest()[:10]
