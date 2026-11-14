"""User-editable settings. Non-secret values in the database, the API key in the keychain.

Environment variables stay the source of defaults; this service only stores
overrides the user makes through the UI/API (FR-24).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import session_scope
from app.modules.platform.queries import get_setting, put_setting
from app.shared.llm_config import LlmRuntime
from app.shared.secrets import SecretStore, SecretStoreUnavailable

SETTINGS_KEY = "settings"
LLM_API_KEY_NAME = "llm_api_key"


def _validate_entry_list(
    values: list[str], *, max_items: int, max_len: int, min_len: int = 1
) -> list[str]:
    if len(values) > max_items:
        raise ValueError(f"At most {max_items} entries are allowed.")
    cleaned = [value.strip() for value in values]
    for value in cleaned:
        if not min_len <= len(value) <= max_len:
            raise ValueError(f"Each entry must be {min_len}-{max_len} characters.")
    return cleaned


class SalaryFloor(BaseModel):
    amount: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class Criteria(BaseModel):
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)

    @field_validator("include_keywords", "exclude_keywords", "locations", "seniority", mode="after")
    @classmethod
    def _limits(cls, values: list[str]) -> list[str]:
        return _validate_entry_list(values, max_items=50, max_len=60)


class NonNegotiables(BaseModel):
    languages: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_modes: list[Literal["remote", "hybrid", "onsite"]] = Field(default_factory=list)
    salary_floor: SalaryFloor | None = None
    work_authorization: str | None = Field(default=None, max_length=60)

    @field_validator("languages", mode="after")
    @classmethod
    def _language_limit(cls, values: list[str]) -> list[str]:
        return _validate_entry_list(values, max_items=10, max_len=60)

    @field_validator("locations", mode="after")
    @classmethod
    def _location_limit(cls, values: list[str]) -> list[str]:
        return _validate_entry_list(values, max_items=20, max_len=60)


class LlmSettings(BaseModel):
    base_url: str = "http://127.0.0.1:8000/v1"
    model: str = Field(default="deepseek-v4-flash", min_length=1, max_length=120)
    runs: int = Field(default=3, ge=1, le=5)
    temperature: float = Field(default=0.2, ge=0.0, le=0.2)
    api_key: str | None = Field(default=None, exclude=True, repr=False)

    @field_validator("base_url")
    @classmethod
    def _https_or_localhost(cls, value: str) -> str:
        lowered = value.lower()
        if lowered.startswith("https://"):
            return value
        if lowered.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
            return value
        raise ValueError("The LLM base URL must use HTTPS, or HTTP on localhost.")


class BudgetSettings(BaseModel):
    monthly_tokens: int | None = Field(default=None, ge=0)


class RedactionSettings(BaseModel):
    terms: list[str] = Field(default_factory=list)

    @field_validator("terms", mode="after")
    @classmethod
    def _term_limits(cls, values: list[str]) -> list[str]:
        return _validate_entry_list(values, max_items=100, max_len=100, min_len=2)


class AppSettings(BaseModel):
    criteria: Criteria = Field(default_factory=Criteria)
    non_negotiables: NonNegotiables = Field(default_factory=NonNegotiables)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    budget: BudgetSettings = Field(default_factory=BudgetSettings)
    redaction: RedactionSettings = Field(default_factory=RedactionSettings)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class SettingsService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        secret_store: SecretStore,
        defaults: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._secret_store = secret_store
        self._defaults = defaults

    def read(self) -> dict[str, Any]:
        payload = self._merged().model_dump()
        payload["llm"]["api_key_set"] = self._api_key_is_set()
        return payload

    def update(self, payload: AppSettings) -> dict[str, Any]:
        stored = payload.model_dump(exclude={"llm": {"api_key"}})
        with session_scope(self._session_factory) as session:
            put_setting(session, SETTINGS_KEY, stored)
        if payload.llm.api_key:
            self._secret_store.set(LLM_API_KEY_NAME, payload.llm.api_key)
        return self.read()

    def _defaults_model(self) -> AppSettings:
        return AppSettings(
            llm=LlmSettings(
                base_url=self._defaults.llm_base_url,
                model=self._defaults.llm_model,
                runs=self._defaults.match_runs,
            ),
            budget=BudgetSettings(
                monthly_tokens=self._defaults.token_budget_monthly or None,
            ),
        )

    def _merged(self) -> AppSettings:
        with self._session_factory() as session:
            stored = get_setting(session, SETTINGS_KEY) or {}
        data = _merge(self._defaults_model().model_dump(), stored)
        llm_section = data.get("llm")
        if isinstance(llm_section, dict):
            llm_section.pop("api_key", None)
        return AppSettings.model_validate(data)

    def _api_key_is_set(self) -> bool:
        try:
            return bool(self._secret_store.get(LLM_API_KEY_NAME))
        except SecretStoreUnavailable:
            return False

    def runtime(self) -> LlmRuntime:
        """What the LLM client needs, merged from defaults, overrides and the keychain."""
        merged = self._merged()
        try:
            api_key = self._secret_store.get(LLM_API_KEY_NAME)
        except SecretStoreUnavailable:
            api_key = None
        return LlmRuntime(
            base_url=merged.llm.base_url,
            model=merged.llm.model,
            api_key=api_key or None,
            temperature=merged.llm.temperature,
            runs=merged.llm.runs,
        )
