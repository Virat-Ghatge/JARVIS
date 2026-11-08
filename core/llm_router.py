import time
import json
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Callable

from config.settings import (
    load_vault,
    get_vault,
    get_active_key,
    rotate_key,
    rotate_provider_key,
    mark_key_status,
    get_role_target,
    get_custom_endpoint,
    is_internet_connected,
    DEFAULT_PROVIDERS,
    LOCAL_MODEL_NAME,
    is_cloud_api_enabled,
    is_local_endpoint_url,
)
from core.adapters.base import ChatMessage, LLMResponse, BaseLLMAdapter, extract_json_from_text
from core.adapters.gemini_adapter import GeminiAdapter
from core.adapters.groq_adapter import GroqAdapter
from core.adapters.anthropic_adapter import AnthropicAdapter
from core.adapters.openai_compat import OpenAICompatAdapter
from core.adapters.local_gguf_adapter import LocalGGUFAdapter


class LLMRouter:
    """
    Multi-Provider, Multi-Key LLM Router with automatic key rotation on 429/401/quota errors,
    automatic cross-provider failover when a provider has no keys configured,
    FREELLMAPI 65ms rate-limit pacing, and real-time WebSocket token telemetry.
    """

    def __init__(self, vault_path: Optional[Any] = None):
        self.vault_path = vault_path
        self._telemetry_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._lock = threading.RLock()
        self._last_call_ts: float = 0.0
        self.stats: Dict[str, Any] = {
            "total_calls": 0,
            "total_tokens": 0,
            "total_session_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "active_provider": "standby",
            "active_model": "none",
            "last_latency_ms": 0,
            "key_rotations": 0,
        }

    def register_telemetry_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback not in self._telemetry_listeners:
            self._telemetry_listeners.append(callback)

    def _emit_telemetry(self, event_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        payload = dict(self.stats)
        if event_data:
            payload.update(event_data)
        if kwargs:
            payload.update(kwargs)
        payload.setdefault("timestamp", time.time())
        if "total_session_tokens" not in payload:
            p = int(payload.get("prompt_tokens", 0) or 0)
            c = int(payload.get("completion_tokens", 0) or 0)
            payload["total_session_tokens"] = p + c
        for cb in list(self._telemetry_listeners):
            try:
                cb(payload)
            except Exception:
                pass

    def get_telemetry(self) -> Dict[str, Any]:
        return dict(self.stats)

    def _pace_requests(self, min_interval_ms: int = 65) -> None:
        with self._lock:
            now = time.time()
            elapsed_ms = (now - self._last_call_ts) * 1000.0
            if elapsed_ms < min_interval_ms:
                time.sleep((min_interval_ms - elapsed_ms) / 1000.0)
            self._last_call_ts = time.time()

    def _build_candidate_chain(self, role: str, preferred_provider: Optional[str] = None, preferred_model: Optional[str] = None) -> List[Dict[str, Any]]:
        vault = load_vault(vault_path=self.vault_path)
        candidates: List[Dict[str, Any]] = []
        local_first = bool(vault.get("local_first_mode", True))
        cloud_enabled = is_cloud_api_enabled(vault_path=self.vault_path)

        compat_defaults = {
            "openrouter": "https://openrouter.ai/api/v1",
            "ollama": "http://127.0.0.1:11434/v1",
            "lmstudio": "http://127.0.0.1:1234/v1",
            "lm_studio": "http://127.0.0.1:1234/v1",
            "deepseek": "https://api.deepseek.com/v1",
        }

        local_cfg = vault.get("providers", {}).get("local", {})
        local_cand = {
            "provider": "local",
            "model": (local_cfg.get("default_model") if isinstance(local_cfg, dict) else None) or LOCAL_MODEL_NAME,
            "base_url": None,
            "api_key": "local-in-process",
            "is_custom": False,
        }

        def is_cloud_cand(candidate: Dict[str, Any]) -> bool:
            p_name = str(candidate.get("provider", "")).strip().lower()
            if p_name == "local":
                return False
            if p_name.startswith("custom:") or candidate.get("is_custom"):
                b_url = str(candidate.get("base_url") or "")
                return not is_local_endpoint_url(b_url)
            return True

        def append_candidate(candidate: Optional[Dict[str, Any]]) -> None:
            if not candidate:
                return
            if not cloud_enabled and is_cloud_cand(candidate):
                return
            provider_name = str(candidate.get("provider", "")).strip().lower()
            if not provider_name:
                return
            if not any(str(item.get("provider", "")).lower() == provider_name for item in candidates):
                candidates.append(candidate)

        def provider_candidate(provider_name: str, model_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
            clean_provider = str(provider_name or "").strip().lower()
            if clean_provider == "local":
                candidate = dict(local_cand)
                if model_name:
                    candidate["model"] = model_name
                return candidate

            endpoint = get_custom_endpoint(clean_provider, vault_path=self.vault_path)
            if endpoint and endpoint.get("enabled", True):
                return {
                    "provider": f"custom:{endpoint['id']}",
                    "model": model_name or endpoint.get("default_model") or endpoint.get("model") or "default",
                    "base_url": endpoint.get("base_url"),
                    "api_key": endpoint.get("api_key", "sk-local"),
                    "is_custom": True,
                }

            prov_cfg = vault.get("providers", {}).get(clean_provider, {})
            if not isinstance(prov_cfg, dict):
                prov_cfg = {}
            active_key = get_active_key(clean_provider, vault_path=self.vault_path)
            if not active_key:
                return None
            return {
                "provider": clean_provider,
                "model": model_name or prov_cfg.get("default_model") or DEFAULT_PROVIDERS.get(clean_provider, {}).get("default_model", "default"),
                "base_url": prov_cfg.get("base_url") or compat_defaults.get(clean_provider),
                "api_key": active_key,
                "is_custom": False,
            }

        # An explicit provider is an operator override and must be tried first.
        if preferred_provider:
            append_candidate(provider_candidate(str(preferred_provider), preferred_model))

        # Local-first mode applies to conversational roles only. The local
        # candidate is still inserted immediately after an explicit/role
        # target in cloud-first mode so a broken cloud connection fails over
        # to the embedded model before trying unrelated providers.
        conversational_role = role in ("chat", "qa_chat")
        if local_first and not preferred_provider and conversational_role:
            append_candidate(dict(local_cand))

        primary = get_role_target(role, vault_path=self.vault_path)
        if primary.get("provider") == "local":
            append_candidate(provider_candidate("local", primary.get("model")))
        elif primary.get("api_key") or primary.get("is_custom"):
            append_candidate({
                "provider": primary.get("provider"),
                "model": primary.get("model") or "default",
                "base_url": primary.get("base_url"),
                "api_key": primary.get("api_key"),
                "is_custom": bool(primary.get("is_custom")),
            })

        if not local_first and conversational_role:
            append_candidate(dict(local_cand))

        # Add all other configured providers as fallbacks. Their configured
        # base_url is preserved for OpenAI-compatible providers such as
        # Ollama, LM Studio, OpenRouter, and DeepSeek.
        for prov_name in vault.get("providers", {}).keys():
            if str(prov_name).lower() in ("custom_endpoints", "local"):
                continue
            append_candidate(provider_candidate(str(prov_name)))

        # Finally add enabled custom endpoints that are not already bound.
        for endpoint in vault.get("custom_endpoints", []):
            if endpoint.get("enabled", True):
                append_candidate({
                    "provider": f"custom:{endpoint['id']}",
                    "model": endpoint.get("default_model") or endpoint.get("model") or "default",
                    "base_url": endpoint.get("base_url"),
                    "api_key": endpoint.get("api_key", "sk-local"),
                    "is_custom": True,
                })

        # The embedded model is always the final safety net, including for
        # non-conversational roles whose cloud provider is unavailable.
        append_candidate(dict(local_cand))

        return candidates

    def _call_gemini(
        self,
        api_key: str,
        model: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        image_b64: Optional[str] = None,
        temperature: float = 0.4,
    ) -> Dict[str, Any]:
        model_id = model or "gemini-2.5-flash"
        if model_id.startswith("models/"):
            model_id = model_id.split("/", 1)[1]

        contents = []
        sys_parts = []
        if system_prompt:
            sys_parts.append({"text": system_prompt})

        for msg in messages:
            m_role = msg.get("role", "user")
            m_text = str(msg.get("content", ""))
            if m_role == "system":
                sys_parts.append({"text": m_text})
                continue
            gemini_role = "model" if m_role == "assistant" else "user"
            parts: List[Dict[str, Any]] = [{"text": m_text}]
            contents.append({"role": gemini_role, "parts": parts})

        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Hello"}]}]

        if image_b64:
            clean_b64 = image_b64.split(",", 1)[1] if "," in image_b64 else image_b64
            contents[-1]["parts"].append({
                "inline_data": {"mime_type": "image/png", "data": clean_b64}
            })

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 2048},
        }
        if sys_parts:
            payload["systemInstruction"] = {"parts": sys_parts}

        # Try requested model, then fallback to gemini-2.0-flash / gemini-1.5-flash if 404
        models_to_try = [model_id]
        for fallback_m in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
            if fallback_m not in models_to_try:
                models_to_try.append(fallback_m)

        last_err = None
        for m_try in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_try}:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                cands = body.get("candidates", [])
                if not cands:
                    raise RuntimeError(f"Gemini returned empty candidates: {body}")
                parts = cands[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                usage = body.get("usageMetadata", {})
                return {
                    "content": text,
                    "model": m_try,
                    "prompt_tokens": int(usage.get("promptTokenCount", max(1, len( str(messages) ) // 4))),
                    "completion_tokens": int(usage.get("candidatesTokenCount", max(1, len(text) // 4))),
                }
            except urllib.error.HTTPError as he:
                err_body = he.read().decode("utf-8", errors="ignore")
                if he.code == 404 and m_try != models_to_try[-1]:
                    last_err = f"HTTP 404 for {m_try}: {err_body}"
                    continue
                raise RuntimeError(f"HTTP {he.code}: {err_body}") from he

        raise RuntimeError(last_err or "Gemini call failed")

    def _call_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.4,
    ) -> Dict[str, Any]:
        clean_base = base_url.rstrip("/")
        if not clean_base.endswith("/chat/completions"):
            if not clean_base.endswith("/v1"):
                # Allow endpoints that already include /v1 or custom paths
                pass
            url = f"{clean_base}/chat/completions"
        else:
            url = clean_base

        full_messages: List[Dict[str, str]] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        for m in messages:
            full_messages.append({
                "role": m.get("role", "user"),
                "content": str(m.get("content", "")),
            })

        payload = {
            "model": model or "default",
            "messages": full_messages,
            "temperature": temperature,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key or 'sk-local'}",
            "User-Agent": "JARVIS-2.0-HUD",
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices", [])
            if not choices:
                raise RuntimeError(f"Empty choices from {url}: {body}")
            msg = choices[0].get("message", {})
            text = str(msg.get("content", "")).strip()
            usage = body.get("usage", {})
            return {
                "content": text,
                "model": body.get("model", model),
                "prompt_tokens": int(usage.get("prompt_tokens", max(1, len(str(full_messages)) // 4))),
                "completion_tokens": int(usage.get("completion_tokens", max(1, len(text) // 4))),
            }
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {he.code}: {err_body}") from he

    def _call_anthropic(
        self,
        api_key: str,
        model: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.4,
    ) -> Dict[str, Any]:
        url = "https://api.anthropic.com/v1/messages"
        filtered_msgs = []
        sys_text = system_prompt or ""
        for m in messages:
            if m.get("role") == "system":
                sys_text = (sys_text + "\n" + str(m.get("content", ""))).strip()
            else:
                filtered_msgs.append({
                    "role": "assistant" if m.get("role") == "assistant" else "user",
                    "content": str(m.get("content", "")),
                })
        if not filtered_msgs:
            filtered_msgs = [{"role": "user", "content": "Hello"}]

        payload: Dict[str, Any] = {
            "model": model or "claude-3-5-sonnet-latest",
            "max_tokens": 2048,
            "temperature": temperature,
            "messages": filtered_msgs,
        }
        if sys_text:
            payload["system"] = sys_text

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            blocks = body.get("content", [])
            text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict)).strip()
            usage = body.get("usage", {})
            return {
                "content": text,
                "model": body.get("model", model),
                "prompt_tokens": int(usage.get("input_tokens", 50)),
                "completion_tokens": int(usage.get("output_tokens", max(1, len(text) // 4))),
            }
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {he.code}: {err_body}") from he

    def _resolve_model(self, provider: str, model: Optional[str]) -> str:
        if model and model != "default" and str(model).strip():
            return str(model).strip()
        endpoint = get_custom_endpoint(provider, vault_path=self.vault_path)
        if endpoint:
            return str(endpoint.get("default_model") or endpoint.get("model") or "default")
        provider_config = load_vault(vault_path=self.vault_path).get("providers", {}).get(str(provider).lower(), {})
        if isinstance(provider_config, dict) and provider_config.get("default_model"):
            return str(provider_config["default_model"])
        defaults = {
            "local": LOCAL_MODEL_NAME,
            "gemini": "gemini-2.5-flash",
            "groq": "llama-3.3-70b-versatile",
            "anthropic": "claude-3-5-sonnet-latest",
            "openai": "gpt-4o-mini",
        }
        return defaults.get(str(provider).lower(), "gemini-2.5-flash")

    def get_adapter_for_provider(
        self,
        provider: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> BaseLLMAdapter:
        clean_prov = str(provider).strip().lower()
        prov_key = api_key if api_key is not None else get_active_key(clean_prov, vault_path=self.vault_path)
        resolved_model = self._resolve_model(clean_prov, model)

        if clean_prov == "local":
            return LocalGGUFAdapter(model=resolved_model)
        elif clean_prov == "gemini":
            return GeminiAdapter(api_key=prov_key or "", model=resolved_model)
        elif clean_prov == "groq":
            return GroqAdapter(api_key=prov_key or "", model=resolved_model)
        elif clean_prov == "anthropic":
            return AnthropicAdapter(api_key=prov_key or "", model=resolved_model)

        ep = get_custom_endpoint(provider, vault_path=self.vault_path)
        if ep:
            ep_model = resolved_model if (model and model != "default") else (ep.get("model") or "gpt-4o-mini")
            return OpenAICompatAdapter(
                base_url=base_url or ep.get("base_url", "https://api.openai.com/v1"),
                api_key=prov_key or ep.get("api_key", ""),
                model=ep_model,
                provider_name=ep.get("name", "custom"),
            )

        provider_cfg = load_vault(vault_path=self.vault_path).get("providers", {}).get(clean_prov, {})
        configured_base_url = provider_cfg.get("base_url") if isinstance(provider_cfg, dict) else None
        compat_defaults = {
            "openrouter": "https://openrouter.ai/api/v1",
            "ollama": "http://127.0.0.1:11434/v1",
            "lmstudio": "http://127.0.0.1:1234/v1",
            "lm_studio": "http://127.0.0.1:1234/v1",
            "deepseek": "https://api.deepseek.com/v1",
        }
        return OpenAICompatAdapter(
            base_url=base_url or configured_base_url or compat_defaults.get(clean_prov, "https://api.openai.com/v1"),
            api_key=prov_key or "",
            model=resolved_model,
            provider_name=clean_prov,
        )

    def is_retryable_error(self, error_str: Optional[str]) -> bool:
        if not error_str:
            return False
        err_lower = error_str.lower()
        retry_signatures = [
            "429",
            "rate limit",
            "quota",
            "resource_exhausted",
            "too many requests",
            "unauthorized",
            "invalid api key",
            "authentication",
            "401",
        ]
        return any(sig in err_lower for sig in retry_signatures)

    def generate_with_failover(
        self,
        provider: str,
        model: str,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        vault = load_vault(vault_path=self.vault_path)
        prov_data = vault.get("providers", {}).get(provider, {})
        keys = prov_data.get("keys", [])
        max_attempts = max(1, len(keys))
        last_response = None

        for attempt in range(max_attempts):
            adapter = self.get_adapter_for_provider(provider, model)
            response = adapter.generate(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            last_response = response

            if not response.error:
                tok_total = response.total_tokens or (response.prompt_tokens + response.completion_tokens)
                with self._lock:
                    self.stats["total_session_tokens"] = int(self.stats.get("total_session_tokens", 0)) + tok_total
                self._emit_telemetry({
                    "provider": provider,
                    "model": model,
                    "latency_ms": response.latency_ms,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "total_session_tokens": tok_total,
                })
                return response

            if self.is_retryable_error(response.error) and len(keys) > 1 and attempt < max_attempts - 1:
                new_key = rotate_key(provider, reason=response.error, vault_path=self.vault_path)
                with self._lock:
                    self.stats["key_rotations"] = int(self.stats.get("key_rotations", 0)) + 1
                continue
            else:
                break

        if last_response:
            tok_total = last_response.total_tokens or (last_response.prompt_tokens + last_response.completion_tokens)
            self._emit_telemetry({
                "provider": provider,
                "model": model,
                "latency_ms": last_response.latency_ms,
                "prompt_tokens": last_response.prompt_tokens,
                "completion_tokens": last_response.completion_tokens,
                "total_session_tokens": tok_total,
            })
            return last_response

        return LLMResponse(text="", error="Unknown generation failure", provider=provider, model=model)

    def chat(
        self,
        messages: Any,
        role: str = "chat",
        system_prompt: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        image_b64: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.4,
    ) -> Dict[str, Any]:
        if isinstance(messages, str):
            norm_messages = [{"role": "user", "content": messages}]
        elif isinstance(messages, list):
            norm_messages = messages
        else:
            norm_messages = [{"role": "user", "content": str(messages)}]

        cloud_enabled = is_cloud_api_enabled(vault_path=self.vault_path)
        candidates = self._build_candidate_chain(role=role, preferred_provider=provider, preferred_model=model)
        if not cloud_enabled:
            has_local = any(
                str(c.get("provider", "")).lower() == "local" or
                (bool(c.get("is_custom")) and is_local_endpoint_url(str(c.get("base_url", ""))))
                for c in candidates
            )
            if not has_local or not candidates:
                clean_offline_msg = "Cloud AI API is disabled (Offline Mode). All local OS controls, music, alarms, and search remain active, sir."
                return {
                    "content": clean_offline_msg,
                    "text": clean_offline_msg,
                    "provider": "offline",
                    "model": "none",
                    "status": "offline",
                    "success": False,
                }
        if not candidates:
            msg = (
                "No LLM API keys or custom endpoints are configured in the API Vault yet. "
                "Open the **API Key Vault** tab in the HUD, paste a Gemini, Groq, OpenAI, Anthropic, "
                "or Custom Endpoint key, and click **Add Key**."
            )
            return {
                "content": msg,
                "text": msg,
                "provider": "offline_fallback",
                "model": "none",
                "success": False,
                "error": "no_keys_configured",
            }

        errors_log: List[str] = []
        vault = load_vault(vault_path=self.vault_path)

        for cand in candidates:
            prov_name = cand["provider"]
            model_name = cand["model"]
            is_custom = cand.get("is_custom", False)
            base_url = cand.get("base_url")

            # Determine how many keys we can try for this provider
            max_attempts = 1
            if not is_custom:
                prov_keys = vault.get("providers", {}).get(prov_name, {}).get("keys", [])
                max_attempts = max(1, len(prov_keys))

            for attempt in range(max_attempts):
                curr_key = cand.get("api_key") if is_custom else (get_active_key(prov_name, vault_path=self.vault_path) or cand.get("api_key"))
                if not curr_key and not is_custom:
                    break

                self._pace_requests(65)
                t0 = time.time()
                try:
                    if is_custom:
                        res = self._call_openai_compatible(
                            base_url=base_url or "http://127.0.0.1:8000/v1",
                            api_key=curr_key or "sk-local",
                            model=model_name,
                            messages=norm_messages,
                            system_prompt=system_prompt,
                            temperature=temperature,
                        )
                    elif prov_name == "local":
                        local_adapter = self.get_adapter_for_provider("local", model=model_name)
                        chat_msgs = []
                        if system_prompt:
                            chat_msgs.append(ChatMessage(role="system", content=system_prompt))
                        for m in norm_messages:
                            chat_msgs.append(ChatMessage(role=m.get("role", "user"), content=str(m.get("content", ""))))
                        res_obj = local_adapter.generate(
                            messages=chat_msgs,
                            temperature=temperature,
                            max_tokens=1024,
                            json_mode=json_mode,
                        )
                        if res_obj.error:
                            raise RuntimeError(res_obj.error)
                        res = {
                            "content": res_obj.text,
                            "model": res_obj.model or model_name,
                            "prompt_tokens": res_obj.prompt_tokens,
                            "completion_tokens": res_obj.completion_tokens,
                        }
                    elif prov_name == "gemini":
                        res = self._call_gemini(
                            api_key=curr_key,
                            model=model_name,
                            messages=norm_messages,
                            system_prompt=system_prompt,
                            image_b64=image_b64,
                            temperature=temperature,
                        )
                    elif prov_name == "groq":
                        res = self._call_openai_compatible(
                            base_url="https://api.groq.com/openai/v1",
                            api_key=curr_key,
                            model=model_name or "llama-3.3-70b-versatile",
                            messages=norm_messages,
                            system_prompt=system_prompt,
                            temperature=temperature,
                        )
                    elif prov_name == "openai":
                        res = self._call_openai_compatible(
                            base_url="https://api.openai.com/v1",
                            api_key=curr_key,
                            model=model_name or "gpt-4o-mini",
                            messages=norm_messages,
                            system_prompt=system_prompt,
                            temperature=temperature,
                        )
                    elif prov_name == "anthropic":
                        res = self._call_anthropic(
                            api_key=curr_key,
                            model=model_name or "claude-3-5-sonnet-latest",
                            messages=norm_messages,
                            system_prompt=system_prompt,
                            temperature=temperature,
                        )
                    else:
                        res = self._call_openai_compatible(
                            base_url=base_url or "http://127.0.0.1:8000/v1",
                            api_key=curr_key or "sk-local",
                            model=model_name,
                            messages=norm_messages,
                            system_prompt=system_prompt,
                            temperature=temperature,
                        )

                    latency_ms = int((time.time() - t0) * 1000)
                    if not is_custom and prov_name != "local":
                        mark_key_status(prov_name, curr_key, "active", vault_path=self.vault_path)

                    p_tok = int(res.get("prompt_tokens", 0))
                    c_tok = int(res.get("completion_tokens", 0))
                    with self._lock:
                        self.stats["total_calls"] += 1
                        self.stats["prompt_tokens"] += p_tok
                        self.stats["completion_tokens"] += c_tok
                        self.stats["total_tokens"] += p_tok + c_tok
                        self.stats["total_session_tokens"] += p_tok + c_tok
                        self.stats["active_provider"] = prov_name
                        self.stats["active_model"] = res.get("model", model_name)
                        self.stats["last_latency_ms"] = latency_ms

                    self._emit_telemetry({
                        "provider": prov_name,
                        "model": res.get("model", model_name),
                        "role": role,
                        "prompt_tokens": p_tok,
                        "completion_tokens": c_tok,
                        "latency_ms": latency_ms,
                        "status": "ok",
                    })

                    content_str = res.get("content", "")
                    out: Dict[str, Any] = {
                        "content": content_str,
                        "text": content_str,
                        "provider": prov_name,
                        "model": res.get("model", model_name),
                        "latency_ms": latency_ms,
                        "prompt_tokens": p_tok,
                        "completion_tokens": c_tok,
                        "success": True,
                    }
                    if json_mode:
                        out["json"] = extract_json_from_text(content_str)
                    return out

                except Exception as exc:
                    err_str = str(exc)
                    errors_log.append(f"{prov_name} ({model_name}): {err_str}")
                    if not is_custom and prov_name != "local" and self.is_retryable_error(err_str):
                        rotate_key(prov_name, reason=err_str, vault_path=self.vault_path)
                        with self._lock:
                            self.stats["key_rotations"] += 1
                    self._emit_telemetry({
                        "provider": prov_name,
                        "model": model_name,
                        "role": role,
                        "status": "error",
                        "error": err_str[:200],
                    })

        if not cloud_enabled:
            clean_offline_msg = "Cloud AI API is disabled (Offline Mode). All local OS controls, music, alarms, and search remain active, sir."
            return {
                "content": clean_offline_msg,
                "text": clean_offline_msg,
                "provider": "offline",
                "model": "none",
                "status": "offline",
                "success": False,
                "error": "cloud_api_disabled",
            }

        err_summary = " | ".join(errors_log[-3:]) if errors_log else "Unknown LLM error"
        fail_msg = f"All configured LLM providers failed to respond. Details: {err_summary}"
        return {
            "content": fail_msg,
            "text": fail_msg,
            "provider": "error",
            "model": "none",
            "success": False,
            "error": err_summary,
        }

    def query_text(
        self,
        arg1: str = "",
        arg2: Optional[str] = None,
        role: str = "chat",
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if arg2 is not None:
            resolved_role = arg1 or role
            resolved_prompt = arg2
        else:
            resolved_prompt = arg1
            resolved_role = role or "chat"

        if not resolved_prompt and "prompt" in kwargs:
            resolved_prompt = kwargs.pop("prompt")
        if "role" in kwargs:
            resolved_role = kwargs.pop("role")

        res = self.chat(
            messages=[{"role": "user", "content": resolved_prompt}],
            role=resolved_role,
            system_prompt=system_prompt,
            **kwargs,
        )
        return str(res.get("content", res.get("text", "")))

    def generate(
        self,
        prompt: str = "",
        role: str = "chat",
        system_prompt: Optional[str] = None,
        image_b64: Optional[str] = None,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> str:
        return self.query_text(
            arg1=prompt,
            role=role,
            system_prompt=system_prompt,
            image_b64=image_b64,
            json_mode=json_mode,
            **kwargs,
        )

    def route_and_respond(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        return self.chat(messages=[{"role": "user", "content": prompt}], role="chat", system_prompt=system_prompt)


router = LLMRouter()
llm_router = router
