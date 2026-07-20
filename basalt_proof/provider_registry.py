from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .beta_models import ProviderProfile


class ProviderError(RuntimeError):
    pass


_DEFAULTS = [
    ProviderProfile(
        provider_id="local-deterministic",
        kind="local",
        display_name="Basalt Deterministic Runtime",
        model="basalt-deterministic-planner",
        base_url="local://deterministic",
        api_key_env="",
        enabled=True,
        configured=True,
        privacy_modes=("local", "private", "standard"),
        capabilities=("reasoning", "planning", "review"),
    ),
    ProviderProfile(
        provider_id="local-codegen",
        kind="local",
        display_name="Basalt Template Codegen",
        model="basalt-template-codegen",
        base_url="local://template-codegen",
        api_key_env="",
        enabled=True,
        configured=True,
        privacy_modes=("local", "private", "standard"),
        capabilities=("code", "tests", "scaffolding"),
    ),
]


class ProviderRegistry:
    """Secret-safe provider inventory and minimal OpenAI-compatible adapter.

    API keys are referenced by environment-variable name and are never written to disk or returned by snapshots.
    """

    def __init__(self, config_path: Path | None = None, environ: dict[str, str] | None = None) -> None:
        self.config_path = config_path.resolve() if config_path else None
        self.environ = environ if environ is not None else os.environ
        self._profiles = {item.provider_id: item for item in _DEFAULTS}
        self._load_config()
        self._load_environment_profile()

    def _load_config(self) -> None:
        if self.config_path is None or not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Provider config is invalid: {self.config_path}") from exc
        entries = data.get("providers", data if isinstance(data, list) else [])
        if not isinstance(entries, list):
            raise ProviderError("Provider config must contain a providers list.")
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            provider_id = str(raw.get("provider_id", "")).strip()
            kind = str(raw.get("kind", "openai-compatible")).strip()
            model = str(raw.get("model", "")).strip()
            base_url = str(raw.get("base_url", "")).strip()
            api_key_env = str(raw.get("api_key_env", "")).strip()
            if not provider_id or not model or not base_url:
                continue
            configured = kind == "local" or bool(api_key_env and self.environ.get(api_key_env))
            profile = ProviderProfile(
                provider_id=provider_id,
                kind=kind,
                display_name=str(raw.get("display_name", provider_id)),
                model=model,
                base_url=base_url.rstrip("/"),
                api_key_env=api_key_env,
                enabled=bool(raw.get("enabled", True)),
                configured=configured,
                privacy_modes=tuple(raw.get("privacy_modes", ["standard"])),
                capabilities=tuple(raw.get("capabilities", ["reasoning", "code"])),
            )
            self._profiles[provider_id] = profile

    def _load_environment_profile(self) -> None:
        base_url = self.environ.get("BASALT_OPENAI_BASE_URL", "").strip()
        model = self.environ.get("BASALT_OPENAI_MODEL", "").strip()
        if not base_url or not model:
            return
        key_env = "BASALT_OPENAI_API_KEY"
        self._profiles["openai-compatible"] = ProviderProfile(
            provider_id="openai-compatible",
            kind="openai-compatible",
            display_name="OpenAI-Compatible Provider",
            model=model,
            base_url=base_url.rstrip("/"),
            api_key_env=key_env,
            enabled=True,
            configured=bool(self.environ.get(key_env)),
            privacy_modes=("standard",),
            capabilities=("reasoning", "code", "review"),
        )

    def inventory(self) -> list[dict[str, Any]]:
        result = []
        for profile in sorted(self._profiles.values(), key=lambda item: item.provider_id):
            item = profile.to_dict()
            item["credential_reference"] = profile.api_key_env or None
            item["credential_configured"] = bool(profile.api_key_env and self.environ.get(profile.api_key_env))
            item.pop("api_key_env", None)
            result.append(item)
        return result

    def get(self, provider_id: str) -> ProviderProfile:
        try:
            return self._profiles[provider_id]
        except KeyError as exc:
            raise ProviderError(f"Provider not found: {provider_id}") from exc

    def choose(self, capability: str, privacy_mode: str = "local") -> ProviderProfile:
        candidates = [
            item
            for item in self._profiles.values()
            if item.enabled
            and item.configured
            and capability in item.capabilities
            and privacy_mode in item.privacy_modes
        ]
        if not candidates:
            raise ProviderError(f"No configured provider supports {capability!r} in {privacy_mode!r} mode.")
        candidates.sort(key=lambda item: (item.kind != "local", item.provider_id))
        return candidates[0]

    @staticmethod
    def _chat_url(base_url: str) -> str:
        if base_url.rstrip("/").endswith("/chat/completions"):
            return base_url.rstrip("/")
        if base_url.rstrip("/").endswith("/v1"):
            return base_url.rstrip("/") + "/chat/completions"
        return base_url.rstrip("/") + "/v1/chat/completions"

    def complete(
        self,
        provider_id: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        timeout: int = 30,
    ) -> dict[str, Any]:
        profile = self.get(provider_id)
        if not profile.enabled or not profile.configured:
            raise ProviderError(f"Provider is not configured: {provider_id}")
        if profile.kind == "local":
            text = "\n".join(item.get("content", "") for item in messages if item.get("role") == "user")
            return {
                "provider": profile.provider_id,
                "model": profile.model,
                "content": f"Deterministic local response prepared for: {text[:500]}",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        if profile.kind != "openai-compatible":
            raise ProviderError(f"Unsupported provider kind: {profile.kind}")
        api_key = self.environ.get(profile.api_key_env, "")
        if not api_key:
            raise ProviderError(f"Credential environment variable is missing: {profile.api_key_env}")
        payload = json.dumps(
            {
                "model": profile.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._chat_url(profile.base_url),
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Basalt-Private-Beta/2.5",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=max(1, timeout)) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ProviderError(f"Provider returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Provider request failed: {exc}") from exc
        choices = body.get("choices") or []
        if not choices:
            raise ProviderError("Provider response did not contain choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderError("Provider response did not contain text content.")
        return {
            "provider": profile.provider_id,
            "model": body.get("model", profile.model),
            "content": content,
            "usage": dict(body.get("usage") or {}),
        }

    def snapshot(self) -> dict[str, Any]:
        inventory = self.inventory()
        return {
            "total": len(inventory),
            "configured": sum(1 for item in inventory if item["configured"]),
            "remote_configured": sum(1 for item in inventory if item["kind"] != "local" and item["configured"]),
            "providers": inventory,
        }
