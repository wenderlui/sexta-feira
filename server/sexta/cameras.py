"""Vigia das câmeras: quando uma câmera detecta movimento, a Sexta-feira olha a foto com a IA de
visão (no próprio PC) e, se houver pessoa ou carro na madrugada, cria um alerta no painel.

Fluxo com as Blink: a Blink detecta movimento -> o Home Assistant chama POST /api/cameras/event
(com o token do webhook) -> a Sexta-feira pega a foto da câmera no Home Assistant -> o modelo de
visão diz se há pessoa ou carro -> alerta com foto, descrição e voz no iPad.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import threading
import time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .store import DATA_DIR

DEFAULT_RULE = {"start": "00:00", "end": "05:00", "objects": ["pessoa", "carro"], "enabled": True}
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
OBJECTS = ("pessoa", "carro", "animal")

VISION_PROMPT = (
    "Você é o vigia de segurança de uma casa. Olhe esta foto de uma câmera e responda SÓ com JSON: "
    '{"pessoa": true/false, "carro": true/false, "animal": true/false, '
    '"descricao": "uma frase curta em português sobre o que aparece"}. '
    "Marque true só se tiver certeza de que aparece na imagem."
)


def in_window(now: dtime, start: str, end: str) -> bool:
    """Janela de horário; aceita virar a meia-noite (ex.: 22:00 às 05:00)."""
    s, e = dtime.fromisoformat(start), dtime.fromisoformat(end)
    return s <= now < e if s < e else (now >= s or now < e)


def parse_vision(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:
        data = {}
    out = {k: bool(data.get(k)) for k in OBJECTS}
    out["descricao"] = str(data.get("descricao") or "").strip()[:200]
    return out


class Alerts:
    """Guarda os alertas (data/alertas.jsonl) e as fotos (data/alertas/)."""

    def __init__(self, folder: Path | None = None, keep: int = 200):
        self.dir = folder or DATA_DIR / "alertas"
        self.log = self.dir.parent / "alertas.jsonl"
        self.keep = keep
        self._lock = threading.Lock()
        self.items: list[dict] = self._load()

    def _load(self) -> list[dict]:
        try:
            lines = self.log.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        items = []
        for line in lines[-self.keep:]:
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
        return items

    def add(self, alert: dict, jpeg: bytes | None) -> dict:
        with self._lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            if jpeg:
                (self.dir / f"{alert['id']}.jpg").write_bytes(jpeg)
                alert["foto"] = True
            self.items.append(alert)
            self.items = self.items[-self.keep:]
            with open(self.log, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert, ensure_ascii=False) + "\n")
            return alert

    def ack(self, alert_id: str) -> bool:
        with self._lock:
            for a in self.items:
                if a["id"] == alert_id:
                    a["visto"] = True
                    self._rewrite()
                    return True
        return False

    def _rewrite(self) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.log.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in self.items), encoding="utf-8")
        tmp.replace(self.log)

    def photo(self, alert_id: str) -> Path | None:
        if not re.fullmatch(r"[0-9a-f]{16}", alert_id):
            return None
        p = self.dir / f"{alert_id}.jpg"
        return p if p.exists() else None


class Watchman:
    def __init__(self, settings, store, home, alerts: Alerts, vision):
        """vision(image_b64, prompt) -> texto; normalmente o modelo de visão do Ollama."""
        self.s, self.store, self.home, self.alerts, self.vision = settings, store, home, alerts, vision

    # ---- regra e token ----
    def rule(self) -> dict:
        return {**DEFAULT_RULE, **(self.store.prefs.get("camera_rule") or {})}

    def set_rule(self, rule: dict) -> dict:
        for k in ("start", "end"):
            if k in rule and not TIME_RE.match(str(rule[k])):
                raise ValueError("horário no formato HH:MM")
        if "objects" in rule:
            if not isinstance(rule["objects"], list) or any(o not in OBJECTS for o in rule["objects"]):
                raise ValueError("objetos: pessoa, carro ou animal")
        merged = {**self.rule(), **{k: v for k, v in rule.items() if k in DEFAULT_RULE}}
        self.store.set_prefs({"camera_rule": merged})
        return merged

    def webhook_token(self) -> str:
        token = self.store.prefs.get("webhook_token")
        if not token:
            token = secrets.token_urlsafe(24)
            self.store.set_prefs({"webhook_token": token})
        return token

    def check_token(self, token: str | None) -> bool:
        return bool(token) and secrets.compare_digest(token, self.webhook_token())

    # ---- evento ----
    async def event(self, camera: str, image_b64: str | None = None, now: datetime | None = None) -> dict:
        rule = self.rule()
        now = now or datetime.now(ZoneInfo(self.s.timezone))
        if not rule["enabled"]:
            return {"alerta": False, "motivo": "vigia desligado"}
        if not in_window(now.time(), rule["start"], rule["end"]):
            return {"alerta": False, "motivo": f"fora do horário ({rule['start']}–{rule['end']})"}
        jpeg = base64.b64decode(image_b64) if image_b64 else await self.home.snapshot(camera)
        if not jpeg:
            return {"alerta": False, "motivo": "sem foto da câmera"}
        seen = parse_vision(await self.vision(base64.b64encode(jpeg).decode(), VISION_PROMPT))
        found = [o for o in rule["objects"] if seen.get(o)]
        if not found:
            return {"alerta": False, "motivo": "nada de risco na foto", "visao": seen}
        alert = {
            "id": secrets.token_hex(8), "quando": now.isoformat(timespec="seconds"),
            "camera": camera, "objetos": found, "descricao": seen["descricao"], "visto": False,
            "ts": time.time(),
        }
        return {"alerta": True, **self.alerts.add(alert, jpeg)}
