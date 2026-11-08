"""Casa conectada: Home Assistant (hub para quase tudo) e Govee direto.

O Home Assistant roda no PC e já tem integração pronta para TVs Samsung (SmartThings),
TCL (Google TV / Android TV), câmeras Blink, ar-condicionado, Wake-on-LAN do PC etc.
A Sexta-feira só conversa com ele pela API REST, com um token de acesso de longa duração.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any

import httpx

from .store import Store

# ---------------------------------------------------------------- catálogo
CATALOG: list[dict[str, Any]] = [
    {"id": "homeassistant", "name": "Home Assistant", "icon": "🏠", "kind": "native",
     "desc": "Central da casa. Por ele entram TVs, câmeras, ar-condicionado, luzes e o PC.",
     "fields": [
         {"key": "url", "label": "Endereço", "type": "url", "placeholder": "http://127.0.0.1:8123"},
         {"key": "token", "label": "Token de acesso", "type": "password",
          "help": "No Home Assistant: seu perfil > Segurança > Tokens de acesso de longa duração."},
     ]},
    {"id": "govee", "name": "Govee (LEDs)", "icon": "💡", "kind": "native",
     "desc": "Fitas e lâmpadas Govee direto pela nuvem da Govee.",
     "fields": [
         {"key": "api_key", "label": "Chave da API", "type": "password",
          "help": "No app Govee Home: Perfil > Configurações > Solicitar chave da API (chega por e-mail)."},
     ]},
    {"id": "samsung_tv", "name": "TV Samsung", "icon": "📺", "kind": "via_ha",
     "desc": "Ligar, desligar, volume e apps, pela integração SmartThings ou Samsung Smart TV."},
    {"id": "tcl_tv", "name": "TV TCL", "icon": "📺", "kind": "via_ha",
     "desc": "Google TV/Android TV (integração Android TV Remote) ou Roku TV (integração Roku)."},
    {"id": "blink", "name": "Câmeras Blink", "icon": "📷", "kind": "via_ha",
     "desc": "Ver as câmeras e armar/desarmar, pela integração Blink."},
    {"id": "ar", "name": "Ar-condicionado", "icon": "❄️", "kind": "via_ha",
     "desc": "Pela integração da marca do aparelho, ou um controle IR (Broadlink, SwitchBot)."},
    {"id": "pc", "name": "Computador", "icon": "🖥️", "kind": "via_ha",
     "desc": "Ligar pela rede (Wake-on-LAN) e desligar/bloquear com o HASS.Agent."},
    {"id": "iptv", "name": "IPTV", "icon": "📡", "kind": "soon",
     "desc": "Abrir canais na TV por um player (Kodi/VLC) controlado pelo Home Assistant."},
    {"id": "gmail", "name": "Gmail", "icon": "✉️", "kind": "soon",
     "desc": "Ler e-mails de contas a vencer (só leitura). Próxima etapa."},
    {"id": "social", "name": "Redes sociais", "icon": "💬", "kind": "soon",
     "desc": "Resumo de notificações e mensagens (só leitura)."},
    {"id": "banco", "name": "Banco", "icon": "🏦", "kind": "soon",
     "desc": "Saldo e gastos via Open Finance, só leitura. Ela nunca paga nada sozinha."},
]
CATALOG_BY_ID = {c["id"]: c for c in CATALOG}

HA_DOMAINS = {
    "light": "luz", "switch": "tomada", "input_boolean": "interruptor", "fan": "ventilador",
    "media_player": "tv", "remote": "controle", "climate": "ar", "camera": "câmera",
}
ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
GOVEE_URL = "https://openapi.api.govee.com/router/api/v1"


class HomeError(Exception):
    pass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def best_match(devices: list[dict], query: str) -> dict | None:
    """Acha o aparelho pelo nome falado ("luz da sala", "tv do quarto")."""
    words = {w for w in re.findall(r"[a-z0-9]+", normalize(query)) if len(w) > 1
             and w not in {"da", "do", "de", "na", "no", "a", "o", "as", "os"}}
    if not words:
        return None
    synonyms = {"luz": {"lampada", "led", "luz", "light"}, "tv": {"tv", "televisao", "televisor"},
                "ar": {"ar", "condicionado", "climate"}}
    best, best_score = None, 0.0
    for d in devices:
        hay = set(re.findall(r"[a-z0-9]+", normalize(f"{d['name']} {d['id']} {d['kind']}")))
        score = 0.0
        for w in words:
            if w in hay:
                score += 1
            elif any(w in syn and hay & syn for syn in synonyms.values()):
                score += 0.6
        if score > best_score:
            best, best_score = d, score
    return best


class HomeAssistant:
    def __init__(self, client: httpx.AsyncClient, url: str, token: str):
        self.client, self.url, self.token = client, url.rstrip("/"), token

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def check(self) -> str:
        r = await self.client.get(f"{self.url}/api/", headers=self._h(), timeout=6)
        if r.status_code == 401:
            raise HomeError("token recusado pelo Home Assistant")
        r.raise_for_status()
        return r.json().get("message", "ok")

    async def devices(self) -> list[dict]:
        r = await self.client.get(f"{self.url}/api/states", headers=self._h(), timeout=8)
        r.raise_for_status()
        out = []
        for s in r.json():
            eid = s.get("entity_id", "")
            domain = eid.split(".", 1)[0]
            if domain not in HA_DOMAINS or s.get("state") == "unavailable":
                continue
            attrs = s.get("attributes") or {}
            out.append({
                "id": f"ha:{eid}", "name": attrs.get("friendly_name") or eid, "kind": HA_DOMAINS[domain],
                "on": s.get("state") not in ("off", "idle", "standby", "unavailable", "unknown"),
                "state": s.get("state"), "source": "Home Assistant",
            })
        return out

    async def act(self, entity_id: str, action: str, value: float | None = None) -> None:
        if not ENTITY_RE.match(entity_id):
            raise HomeError("aparelho inválido")
        domain = entity_id.split(".", 1)[0]
        if domain not in HA_DOMAINS or domain == "camera":
            raise HomeError("esse aparelho não aceita comando")
        body: dict[str, Any] = {"entity_id": entity_id}
        if action == "temperatura":
            if domain != "climate" or value is None:
                raise HomeError("temperatura só para ar-condicionado")
            svc_domain, service = "climate", "set_temperature"
            body["temperature"] = max(16, min(30, float(value)))
        elif action == "brilho":
            if domain != "light" or value is None:
                raise HomeError("brilho só para luz")
            svc_domain, service = "light", "turn_on"
            body["brightness_pct"] = int(max(1, min(100, value)))
        else:
            service = {"ligar": "turn_on", "desligar": "turn_off", "alternar": "toggle"}.get(action)
            if not service:
                raise HomeError("ação desconhecida")
            svc_domain = "homeassistant" if domain in ("input_boolean",) else domain
        r = await self.client.post(f"{self.url}/api/services/{svc_domain}/{service}",
                                   headers=self._h(), json=body, timeout=8)
        r.raise_for_status()


class Govee:
    def __init__(self, client: httpx.AsyncClient, api_key: str):
        self.client, self.key = client, api_key

    def _h(self) -> dict:
        return {"Govee-API-Key": self.key, "Content-Type": "application/json"}

    async def devices(self) -> list[dict]:
        r = await self.client.get(f"{GOVEE_URL}/user/devices", headers=self._h(), timeout=8)
        if r.status_code in (401, 403):
            raise HomeError("chave da Govee recusada")
        r.raise_for_status()
        return [{
            "id": f"govee:{d['sku']}:{d['device']}", "name": d.get("deviceName") or d["sku"],
            "kind": "luz", "on": None, "state": None, "source": "Govee",
        } for d in r.json().get("data", [])]

    async def check(self) -> str:
        return f"{len(await self.devices())} aparelho(s)"

    async def act(self, sku: str, device: str, action: str, value: float | None = None) -> None:
        if action == "brilho" and value is not None:
            cap = {"type": "devices.capabilities.range", "instance": "brightness",
                   "value": int(max(1, min(100, value)))}
        elif action in ("ligar", "desligar"):
            cap = {"type": "devices.capabilities.on_off", "instance": "powerSwitch",
                   "value": 1 if action == "ligar" else 0}
        else:
            raise HomeError("a Govee aceita ligar, desligar e brilho")
        r = await self.client.post(f"{GOVEE_URL}/device/control", headers=self._h(), timeout=8, json={
            "requestId": str(uuid.uuid4()), "payload": {"sku": sku, "device": device, "capability": cap}})
        r.raise_for_status()


class Home:
    """Junta tudo o que está conectado e responde ao painel e à IA."""

    def __init__(self, client: httpx.AsyncClient, store: Store):
        self.client, self.store = client, store

    def _ha(self) -> HomeAssistant | None:
        c = self.store.connection("homeassistant")
        return HomeAssistant(self.client, c["url"], c["token"]) if c.get("url") and c.get("token") else None

    def _govee(self) -> Govee | None:
        c = self.store.connection("govee")
        return Govee(self.client, c["api_key"]) if c.get("api_key") else None

    @property
    def configured(self) -> bool:
        return bool(self._ha() or self._govee())

    async def check(self, cid: str) -> str:
        target = {"homeassistant": self._ha, "govee": self._govee}.get(cid, lambda: None)()
        if not target:
            raise HomeError("falta preencher os dados")
        try:
            return await target.check()
        except httpx.HTTPError as exc:
            raise HomeError(f"não consegui conectar: {exc.__class__.__name__}") from exc

    async def devices(self) -> tuple[list[dict], list[str]]:
        out, errors = [], []
        for name, target in (("Home Assistant", self._ha()), ("Govee", self._govee())):
            if not target:
                continue
            try:
                out.extend(await target.devices())
            except (httpx.HTTPError, HomeError, ValueError, KeyError) as exc:
                errors.append(f"{name}: {exc}")
        return out, errors

    async def act(self, device_id: str, action: str, value: float | None = None) -> None:
        kind, _, rest = device_id.partition(":")
        try:
            if kind == "ha" and (ha := self._ha()):
                return await ha.act(rest, action, value)
            if kind == "govee" and (gv := self._govee()):
                sku, _, dev = rest.partition(":")
                return await gv.act(sku, dev, action, value)
        except httpx.HTTPError as exc:
            raise HomeError(f"o aparelho não respondeu ({exc.__class__.__name__})") from exc
        raise HomeError("aparelho não encontrado")

    async def command(self, dispositivo: str, acao: str, valor: float | None = None) -> str:
        """Usado pela IA: acha o aparelho pelo nome e executa."""
        devices, errors = await self.devices()
        if not devices:
            return "Nenhum aparelho conectado." + (f" Erros: {'; '.join(errors)}" if errors else "")
        if acao == "listar":
            return "Aparelhos: " + "; ".join(f"{d['name']} ({d['kind']})" for d in devices[:30])
        d = best_match(devices, dispositivo)
        if not d:
            return f"Não achei '{dispositivo}'. Tenho: " + ", ".join(x["name"] for x in devices[:15])
        try:
            await self.act(d["id"], acao, valor)
        except HomeError as exc:
            return f"Não consegui com {d['name']}: {exc}"
        return f"Feito: {acao} {d['name']}" + (f" ({valor})" if valor is not None else "") + "."
