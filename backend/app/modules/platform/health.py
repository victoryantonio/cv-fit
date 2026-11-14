"""Health status: three booleans the user can look at, nothing more.

No history, no charts. The LLM probe result is cached so polling every two
seconds does not hammer the provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.shared.clock import Clock
from app.shared.secrets import SecretStore, SecretStoreUnavailable

GMAIL_TOKEN_NAME = "gmail_token"  # noqa: S105 - a keychain key, not a secret
_DEFAULT_PROBE_TTL_S = 300.0


class ProbeStatus(StrEnum):
    OK = "ok"
    UNREACHABLE = "unreachable"
    NOT_CONFIGURED = "not_configured"
    AUTH_FAILED = "auth_failed"
    UNKNOWN = "unknown"


class LLMProbe(Protocol):
    async def probe(self) -> ProbeStatus: ...


class NullLLMProbe:
    """Fallback for a wiring mistake. Reports UNKNOWN, never NOT_CONFIGURED.

    Returning NOT_CONFIGURED here made a missing probe indistinguishable from a
    working one with no key, so a stored key still showed "not configured".
    """

    async def probe(self) -> ProbeStatus:
        return ProbeStatus.UNKNOWN


@dataclass(frozen=True)
class HealthReport:
    status: str
    database: str
    gmail: str
    llm: str
    checked_at: datetime

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checked_at"] = self.checked_at.isoformat()
        return payload


class HealthService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        secret_store: SecretStore,
        clock: Clock,
        llm_probe: LLMProbe | None = None,
        probe_ttl_s: float = _DEFAULT_PROBE_TTL_S,
    ) -> None:
        self._session_factory = session_factory
        self._secret_store = secret_store
        self._clock = clock
        self._llm_probe = llm_probe or NullLLMProbe()
        self._probe_ttl_s = probe_ttl_s
        self._cached_llm: ProbeStatus | None = None
        self._cached_at: datetime | None = None

    async def check(self, *, refresh: bool = False) -> HealthReport:
        database = self._database_status()
        return HealthReport(
            status="ok" if database == "ok" else "degraded",
            database=database,
            gmail=self._gmail_status(),
            llm=await self._llm_status(refresh=refresh),
            checked_at=self._clock.now(),
        )

    def _database_status(self) -> str:
        try:
            with self._session_factory() as session:
                session.execute(text("CREATE TEMP TABLE IF NOT EXISTS _health_probe (ok INTEGER)"))
                session.execute(text("INSERT INTO _health_probe VALUES (1)"))
                session.rollback()
        except SQLAlchemyError:
            return "error"
        return "ok"

    def _gmail_status(self) -> str:
        try:
            token = self._secret_store.get(GMAIL_TOKEN_NAME)
        except SecretStoreUnavailable:
            return "keyring_locked"
        return "connected" if token else "not_connected"

    def invalidate(self) -> None:
        """Drop the cached probe so the next check asks the provider again.

        Storing or replacing the API key changes the answer, and the user is not
        going to wait out a five minute TTL to see it.
        """
        self._cached_llm = None
        self._cached_at = None

    async def _llm_status(self, *, refresh: bool) -> ProbeStatus:
        if refresh or self._probe_is_stale():
            try:
                self._cached_llm = await self._llm_probe.probe()
            except Exception:  # noqa: BLE001 - health must never raise
                self._cached_llm = ProbeStatus.UNKNOWN
            self._cached_at = self._clock.now()
        return self._cached_llm or ProbeStatus.UNKNOWN

    def _probe_is_stale(self) -> bool:
        if self._cached_at is None or self._cached_llm is None:
            return True
        age = (self._clock.now() - self._cached_at).total_seconds()
        return age > self._probe_ttl_s
