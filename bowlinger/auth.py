"""A single shared password for the admin and training pages.

The password comes from BOWLINGER_ADMIN_PASSWORD. It is not stored in the
database. A matching login sets an HttpOnly cookie that is an HMAC of that
password, so the check does not keep a server-side session.
"""

from __future__ import annotations

import hashlib
import hmac

from bowlinger.config import Settings

COOKIE_NAME = "bowlinger_admin"
_PURPOSE = b"bowlinger-admin-v1"


def admin_configured(settings: Settings) -> bool:
    return bool(settings.admin_password)


def password_matches(settings: Settings, presented: str) -> bool:
    if not settings.admin_password or presented is None:
        return False
    return hmac.compare_digest(presented.encode(), settings.admin_password.encode())


def cookie_token(settings: Settings) -> str:
    return hmac.new(settings.admin_password.encode(), _PURPOSE, hashlib.sha256).hexdigest()


def cookie_matches(settings: Settings, presented: str | None) -> bool:
    if not settings.admin_password or not presented:
        return False
    return hmac.compare_digest(presented, cookie_token(settings))
