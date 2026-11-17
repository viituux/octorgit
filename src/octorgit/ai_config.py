"""AI settings: persist non-secrets, retain credentials only in server memory."""

import ipaddress
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit

from .ai_engine import AIError

PRESETS = {
    "openai-compatible": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini"},
    "google": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "model": "gemini-3.8-flash"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "model": "claude-sonnet-4-5"},
}


def is_local(url):
    hostname = urlsplit(url).hostname or ""
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def validate_config(data):
    provider = data.get("provider")
    if not isinstance(provider, str) or provider not in PRESETS:
        raise AIError("Selecione um tipo de API disponível.")
    model, base = data.get("model", ""), data.get("base_url", "")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,150}", model):
        raise AIError("Informe o identificador do modelo, sem espaços ou caracteres especiais.")
    if not isinstance(base, str) or len(base) > 500 or any(ord(c) < 33 for c in base):
        raise AIError("Endereço da API inválido.")
    try:
        url = urlsplit(base)
        if not url.hostname or url.username or url.password or url.query or url.fragment or url.port == 0:
            raise ValueError()
        if url.scheme != "https" and not (url.scheme == "http" and is_local(base)):
            raise ValueError()
    except ValueError:
        raise AIError("Use um endereço HTTPS sem chave, usuário ou parâmetros na URL. HTTP só é aceito em localhost.") from None
    key = data.get("api_key", "")
    if not isinstance(key, str) or len(key) > 1024 or not key.isascii() or any(c.isspace() for c in key):
        raise AIError("A chave deve ser um texto sem espaços. Ela não será exibida nem salva em disco.")
    if key and key in base:
        raise AIError("A chave deve ficar somente no campo Chave de API, nunca no endereço.")
    if provider == "google" and not re.fullmatch(r"gemini-[a-z0-9.-]{1,80}", model):
        raise AIError("Para a API Google, informe um identificador de modelo Gemini de texto.")
    return {"provider": provider, "model": model, "base_url": base.rstrip("/"), "api_key": key}


def environment_config():
    provider = os.environ.get("AI_PROVIDER") or ("google" if os.environ.get("GEMINI_API_KEY") else "openai-compatible")
    preset = PRESETS.get(provider, PRESETS["openai-compatible"])
    return {"provider": provider, "base_url": os.environ.get("AI_BASE_URL") or preset["base_url"],
            "model": os.environ.get("AI_MODEL") or (os.environ.get("GEMINI_MODEL") if provider == "google" else None) or preset["model"],
            "api_key": os.environ.get("AI_API_KEY") or (os.environ.get("GEMINI_API_KEY", "") if provider == "google" else "")}


class AIConfiguration:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.lock = threading.RLock()
        self._state = None
        self.persistence_error = None
        if self.path and self.path.exists():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                candidate = validate_config({**stored, "api_key": ""})
                env = environment_config()
                if all(candidate[k] == env[k] for k in ("provider", "base_url")):
                    candidate["api_key"] = env["api_key"]
                self._state = candidate
            except (OSError, ValueError, TypeError, AIError):
                self.persistence_error = "Configuração anterior inválida. Aplique novamente as opções de IA."

    def snapshot(self):
        with self.lock:
            return validate_config(dict(self._state or environment_config()))

    def public(self):
        try:
            data = self.snapshot()
            configured = bool(data["api_key"]) or is_local(data["base_url"])
        except AIError:
            data = {"provider": "openai-compatible", **PRESETS["openai-compatible"]}
            configured = False
        return {"provider": data["provider"], "model": data["model"], "base_url": data["base_url"],
                "configured": configured, "key_present": bool(data.get("api_key")), "key_storage": "session_memory_only",
                "persistence_error": self.persistence_error, "presets": PRESETS}

    def apply(self, payload):
        if not isinstance(payload, dict) or set(payload) - {"provider", "model", "base_url", "api_key", "clear_key"}:
            raise AIError("Configuração de IA inválida.")
        if not isinstance(payload.get("clear_key", False), bool):
            raise AIError("Opção de remover chave inválida.")
        with self.lock:
            try:
                current = self.snapshot()
            except AIError:
                current = {"provider": "openai-compatible", **PRESETS["openai-compatible"], "api_key": ""}
            proposed = {key: payload.get(key, current[key]) for key in ("provider", "model", "base_url")}
            same_destination = all(proposed[k] == current[k] for k in ("provider", "base_url"))
            if current["api_key"] and isinstance(proposed["base_url"], str) and current["api_key"] in proposed["base_url"]:
                raise AIError("O endereço da API não pode conter a chave da sessão.")
            key = payload.get("api_key", "")
            if key == "" and same_destination and not payload.get("clear_key"):
                key = current["api_key"]
            proposed["api_key"] = "" if payload.get("clear_key") else key
            self._state = validate_config(proposed)
            self.persistence_error = None
            if self.path:
                try:
                    self.path.write_text(json.dumps({k: v for k, v in self._state.items() if k != "api_key"}, indent=2), encoding="utf-8")
                except OSError:
                    self.persistence_error = "Preferências aplicadas só nesta sessão: não foi possível salvar os campos não secretos."
        return self.public()


def create_provider(config):
    from .ai_engine import GeminiProvider, OpenAICompatibleProvider, AnthropicProvider
    validated = validate_config(config)
    if not validated["api_key"] and not is_local(validated["base_url"]):
        raise AIError("Configure a chave na tela Configurações de IA antes de gerar explicações.")
    return {"google": GeminiProvider, "openai-compatible": OpenAICompatibleProvider, "anthropic": AnthropicProvider}[validated["provider"]](validated)
