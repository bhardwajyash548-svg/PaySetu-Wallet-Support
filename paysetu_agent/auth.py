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
