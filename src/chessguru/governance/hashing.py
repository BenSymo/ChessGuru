"""Hash other people's usernames before they reach the gold layer.

Opponents are third parties, so the dashboard only ever sees a keyed hash
(HMAC-SHA256) of their username. The same opponent always gets the same
hash, so "games against this person" still works, but the name can't be
recovered without the key.

The key comes from CHESSGURU_HASH_KEY. If that isn't set, a random key is
created once and kept in the data folder (which is never committed).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable

from chessguru.config import Settings

KEY_FILE = ".hash_key"


def load_key(settings: Settings) -> bytes:
    if settings.hash_key:
        return settings.hash_key.get_secret_value().encode()
    path = settings.data_dir / KEY_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip().encode()


def make_hasher(key: bytes) -> Callable[[str], str]:
    def hash_name(name: str) -> str:
        digest = hmac.new(key, name.strip().lower().encode(), hashlib.sha256)
        return digest.hexdigest()[:16]

    return hash_name
