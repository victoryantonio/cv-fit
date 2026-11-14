"""Secret storage port. The only implementation is the OS keychain."""

from __future__ import annotations

from typing import Protocol

import keyring
from keyring.errors import KeyringError


class SecretStoreUnavailable(Exception):
    """The keychain exists but cannot be read right now (locked, denied)."""


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class KeyringSecretStore:
    def __init__(self, service: str = "cv-fit") -> None:
        self._service = service

    def get(self, name: str) -> str | None:
        try:
            return keyring.get_password(self._service, name)
        except KeyringError as exc:
            raise SecretStoreUnavailable(str(exc)) from exc

    def set(self, name: str, value: str) -> None:
        try:
            keyring.set_password(self._service, name, value)
        except KeyringError as exc:
            raise SecretStoreUnavailable(str(exc)) from exc

    def delete(self, name: str) -> None:
        try:
            keyring.delete_password(self._service, name)
        except KeyringError as exc:
            raise SecretStoreUnavailable(str(exc)) from exc
