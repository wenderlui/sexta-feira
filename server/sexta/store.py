"""Ajustes salvos no PC (data/ajustes.json), nunca no iPad.

- Preferências (voz, velocidade) e conexões (Home Assistant, Govee) ficam num único arquivo.
- Senhas e chaves são guardadas só aqui e nunca voltam para o navegador: a API devolve
  apenas "configurado" e os 4 últimos caracteres.
- Gravação atômica (arquivo temporário + replace) para não corromper se o PC desligar no meio.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

SECRET_KEYS = {"token", "api_key", "password", "senha"}


def mask(value: str) -> str:
    value = str(value or "")
    return ("••••" + value[-4:]) if len(value) > 4 else ("••••" if value else "")


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "ajustes.json"
        self._lock = threading.Lock()
        self._data = self._read()

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("prefs", {})
                data.setdefault("connections", {})
                return data
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # Arquivo estragado: guarda uma cópia para análise e começa do zero.
            try:
                self.path.replace(self.path.with_suffix(".corrompido.json"))
            except OSError:
                pass
        return {"prefs": {}, "connections": {}}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)  # só o dono lê (no Windows vale a pasta do usuário)
        except OSError:
            pass
        tmp.replace(self.path)

    # ---- preferências ----
    @property
    def prefs(self) -> dict[str, Any]:
        return dict(self._data["prefs"])

    def set_prefs(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._data["prefs"].update(values)
            self._write()
            return dict(self._data["prefs"])

    # ---- conexões ----
    def connection(self, cid: str) -> dict[str, Any]:
        return dict(self._data["connections"].get(cid) or {})

    def set_connection(self, cid: str, values: dict[str, Any]) -> None:
        with self._lock:
            current = self._data["connections"].get(cid) or {}
            for k, v in values.items():
                # Campo secreto vazio = manter o que já estava salvo.
                if k in SECRET_KEYS and not v:
                    continue
                current[k] = v
            self._data["connections"][cid] = current
            self._write()

    def remove_connection(self, cid: str) -> None:
        with self._lock:
            self._data["connections"].pop(cid, None)
            self._write()

    def public_connection(self, cid: str) -> dict[str, Any]:
        """O que pode ir para o iPad: segredos mascarados."""
        out = {}
        for k, v in self.connection(cid).items():
            out[k] = mask(v) if k in SECRET_KEYS else v
        return out
