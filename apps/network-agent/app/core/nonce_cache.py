"""Replay protection for signed requests: remembers every nonce seen
within its TTL and rejects a repeat.

In-process only — correct because this agent runs as a single process on
one VPS (not horizontally scaled the way apps/api is on Railway). If that
ever changes, this needs to move to a shared store (Redis) so every
process sees the same nonces.
"""

import asyncio
import time


class NonceCache:
    def __init__(self, *, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def seen_before(self, nonce: str) -> bool:
        """Atomically checks-and-records: returns True if `nonce` was
        already recorded (a replay), False if this is the first time (and
        records it). The check and the record must be one atomic operation
        under the lock — otherwise two concurrent requests carrying the
        same nonce could both pass the check before either records it."""
        now = time.monotonic()
        async with self._lock:
            self._purge_expired(now)
            if nonce in self._seen:
                return True
            self._seen[nonce] = now + self._ttl_seconds
            return False

    def _purge_expired(self, now: float) -> None:
        expired = [key for key, expires_at in self._seen.items() if expires_at <= now]
        for key in expired:
            del self._seen[key]
