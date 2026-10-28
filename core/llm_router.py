import time
import json
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Callable

from config.settings import (
    load_vault,
    get_active_key,
    rotate_key,
    mark_key_status,
    get_role_target,
    get_custom_endpoint,
    is_internet_connected,
    DEFAULT_PROVIDERS,
)
from core.adapters.base import extract_json_from_text


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

    def _emit_telemetry(self, event_data: Dict[str, Any]) -> None:
        payload = {**self.stats, **event_data, "timestamp": time.time()}
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

        # 1. Explicit override or configured role target
        if preferred_provider:
            ep = get_custom_endpoint(preferred_provider, vault_path=self.vault_path)
            if ep:
                candidates.append({
                    "provider": f"custom:{ep['id']}",
                    "model": preferred_model or ep.get("default_model", "default"),
                    "base_url": ep.get("base_url"),
                    "api_key": ep.get("api_key", "sk-local"),
                    "is_custom": True,
                })
            else:
                k = get_active_key(preferred_provider, vault_path=self.vault_path)
                if k:
                    prov_cfg = vault.get("providers", {}).get(preferred_provider.lower(), {})
                    candidates.append({
                        "provider": preferred_provider.lower(),
                        "model": preferred_model or prov_cfg.get("default_model", "gemini-2.5-flash"),
                        "base_url": None,
                        "api_key": k,
                        "is_custom": False,
                    })

        primary = get_role_target(role, vault_path=self.vault_path)
        if primary.get("api_key") or primary.get("is_custom"):
            if not any(c["provider"] == primary["provider"] for c in candidates):
                candidates.append(dict(primary))

        # 2. Add all other providers that have keys configured as automatic fallbacks
        for prov_name, prov_cfg in vault.get("providers", {}).items():
            k = get_active_key(prov_name, vault_path=self.vault_path)
            if k and not any(c["provider"] == prov_name for c in candidates):
                candidates.append({
                    "provider": prov_name,
                    "model": prov_cfg.get("default_model", DEFAULT_PROVIDERS.get(prov_name, {}).get("default_model", "default")),
                    "base_url": None,
                    "api_key": k,
                    "is_custom": False,
                })

        # 3. Add enabled custom endpoints as fallback
        for ep in vault.get("custom_endpoints", []):
            if ep.get("enabled", True):
                cid = f"custom:{ep['id']}"
                if not any(c["provider"] == cid or c["provider"] == ep["id"] for c in candidates):
                    candidates.append({
                        "provider": cid,
                        "model": ep.get("default_model") or ep.get("model") or "default",
                        "base_url": ep.get("base_url"),
                        "api_key": ep.get("api_key", "sk-local"),
                        "is_custom": True,
                    })

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

        candidates = self._build_candidate_chain(role=role, preferred_provider=provider, preferred_model=model)
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
                    if not is_custom:
                        mark_key_status(prov_name, curr_key, "active", vault_path=self.vault_path)

                    p_tok = int(res.get("prompt_tokens", 0))
                    c_tok = int(res.get("completion_tokens", 0))
                    with self._lock:
                        self.stats["total_calls"] += 1
                        self.stats["prompt_tokens"] += p_tok
                        self.stats["completion_tokens"] += c_tok
                        self.stats["total_tokens"] += p_tok + c_tok
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
                    if not is_custom:
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

    def generate(
        self,
        prompt: str,
        role: str = "chat",
        system_prompt: Optional[str] = None,
        image_b64: Optional[str] = None,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> str:
        res = self.chat(
            messages=[{"role": "user", "content": prompt}],
            role=role,
            system_prompt=system_prompt,
            image_b64=image_b64,
            json_mode=json_mode,
            **kwargs,
        )
        return str(res.get("content", ""))

    def route_and_respond(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        return self.chat(messages=[{"role": "user", "content": prompt}], role="chat", system_prompt=system_prompt)


router = LLMRouter()
llm_router = router
