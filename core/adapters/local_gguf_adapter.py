#!/usr/bin/env python3
"""
Local GGUF In-Process Adapter using llama-cpp-python.
Runs lightweight local LLMs (e.g., Llama 3.2 3B Instruct) entirely offline with zero cloud tokens.
Optimized for 12th Gen Intel Core i5 with AVX2 instruction set and <16 GB RAM envelope.
"""

import gc
import json
import os
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base import BaseLLMAdapter, ChatMessage, LLMResponse, extract_json_from_text
from config.settings import (
    LOCAL_MODEL_PATH,
    LOCAL_MODEL_NAME,
    LOCAL_MODEL_THREADS,
    LOCAL_MODEL_URL,
    LOCAL_MODEL_FILENAME,
    MODELS_DIR,
)

try:
    import llama_cpp
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    llama_cpp = None
    LLAMA_CPP_AVAILABLE = False


class LocalGGUFAdapter(BaseLLMAdapter):
    """
    In-process GGUF inference adapter for JARVIS.
    Thread-safe, lazy-loading, memory-efficient.
    """

    _model_instance: Optional[Any] = None
    _lock = threading.RLock()
    _download_lock = threading.Lock()
    _download_status: Dict[str, Any] = {
        "downloading": False,
        "progress": 0.0,
        "downloaded_bytes": 0,
        "total_bytes": 0,
        "speed_mb_s": 0.0,
        "error": None,
    }

    def __init__(self, api_key: str = "local-in-process", model: str = LOCAL_MODEL_NAME):
        super().__init__(api_key=api_key, model=model or LOCAL_MODEL_NAME)
        self.provider = "local"

    @classmethod
    def is_available(cls) -> bool:
        """Check if llama-cpp-python package is installed."""
        return LLAMA_CPP_AVAILABLE

    @classmethod
    def is_downloaded(cls) -> bool:
        """Check if the GGUF model weights file exists and is valid (>100MB)."""
        return LOCAL_MODEL_PATH.exists() and LOCAL_MODEL_PATH.stat().st_size > 100 * 1024 * 1024

    @classmethod
    def is_loaded(cls) -> bool:
        """Check if the model is currently resident in RAM."""
        return cls._model_instance is not None

    @classmethod
    def get_download_status(cls) -> Dict[str, Any]:
        """Return real-time download status dictionary."""
        with cls._download_lock:
            return dict(cls._download_status)

    @classmethod
    def load_model(cls) -> Any:
        """
        Thread-safe lazy loader for the GGUF model.
        Loads into RAM only on first call or when explicitly pre-warmed.
        """
        with cls._lock:
            if cls._model_instance is not None:
                return cls._model_instance

            if not LLAMA_CPP_AVAILABLE:
                raise RuntimeError(
                    "llama-cpp-python is not installed. Please install it via: pip install llama-cpp-python"
                )

            if not cls.is_downloaded():
                raise FileNotFoundError(
                    f"Local model GGUF file not found at {LOCAL_MODEL_PATH}. "
                    f"Run scripts/setup_local_model.py or download via the HUD API Vault."
                )

            # Initialize Llama instance optimized for AVX2 Intel CPU
            cls._model_instance = llama_cpp.Llama(
                model_path=str(LOCAL_MODEL_PATH),
                n_ctx=2048,
                n_threads=LOCAL_MODEL_THREADS,
                n_batch=512,
                verbose=False,
            )
            return cls._model_instance

    @classmethod
    def unload_model(cls) -> None:
        """Frees model weights from system RAM."""
        with cls._lock:
            if cls._model_instance is not None:
                try:
                    if hasattr(cls._model_instance, "close"):
                        cls._model_instance.close()
                except Exception:
                    pass
                del cls._model_instance
                cls._model_instance = None
                gc.collect()

    @classmethod
    def download_model(
        cls,
        progress_callback: Optional[Callable[[float, int, int], None]] = None,
        force: bool = False,
    ) -> bool:
        """
        Stream download the GGUF model weights from Hugging Face with progress tracking.
        Writes to a temporary file first, then atomically replaces target on completion.
        """
        if cls.is_downloaded() and not force:
            with cls._download_lock:
                cls._download_status["progress"] = 100.0
                cls._download_status["downloading"] = False
                cls._download_status["error"] = None
            return True

        with cls._download_lock:
            if cls._download_status["downloading"]:
                return True  # Already in progress
            cls._download_status["downloading"] = True
            cls._download_status["progress"] = 0.0
            cls._download_status["downloaded_bytes"] = 0
            cls._download_status["total_bytes"] = 0
            cls._download_status["error"] = None

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = LOCAL_MODEL_PATH.with_suffix(".tmp")

        try:
            req = urllib.request.Request(
                LOCAL_MODEL_URL,
                headers={"User-Agent": "JARVIS-Local-Model-Downloader/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                with cls._download_lock:
                    cls._download_status["total_bytes"] = total_size

                chunk_size = 1024 * 1024  # 1MB chunks
                downloaded = 0
                start_time = time.time()

                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        elapsed = max(0.1, now - start_time)
                        speed = (downloaded / (1024 * 1024)) / elapsed
                        pct = round((downloaded / total_size * 100.0) if total_size else 0.0, 1)

                        with cls._download_lock:
                            cls._download_status["downloaded_bytes"] = downloaded
                            cls._download_status["progress"] = pct
                            cls._download_status["speed_mb_s"] = round(speed, 2)

                        if progress_callback:
                            try:
                                progress_callback(pct, downloaded, total_size)
                            except Exception:
                                pass

            # Atomic replace (safely unload in-memory model first to free file handles on Windows)
            cls.unload_model()
            if LOCAL_MODEL_PATH.exists():
                try:
                    LOCAL_MODEL_PATH.unlink()
                except Exception:
                    pass
            tmp_path.replace(LOCAL_MODEL_PATH)

            with cls._download_lock:
                cls._download_status["downloading"] = False
                cls._download_status["progress"] = 100.0
                cls._download_status["error"] = None
            return True

        except Exception as e:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            with cls._download_lock:
                cls._download_status["downloading"] = False
                cls._download_status["error"] = str(e)
            return False

    def generate(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Generate chat completion using in-process GGUF model.
        """
        t0 = time.time()

        if not LLAMA_CPP_AVAILABLE:
            return LLMResponse(
                text="",
                provider=self.provider,
                model=self.model,
                latency_ms=0,
                error="llama-cpp-python is not installed. Run: pip install llama-cpp-python",
            )

        if not self.is_downloaded():
            return LLMResponse(
                text="",
                provider=self.provider,
                model=self.model,
                latency_ms=0,
                error=f"Local model {LOCAL_MODEL_FILENAME} not downloaded at {LOCAL_MODEL_PATH}. Download it via scripts/setup_local_model.py or HUD.",
            )

        try:
            llm = self.load_model()
        except Exception as exc:
            return LLMResponse(
                text="",
                provider=self.provider,
                model=self.model,
                latency_ms=int((time.time() - t0) * 1000),
                error=f"Failed to load local model into memory: {exc}",
            )

        formatted: List[Dict[str, str]] = []
        for m in messages:
            if isinstance(m, dict):
                role = m.get("role", "user")
                content = str(m.get("content", ""))
            else:
                role = getattr(m, "role", "user")
                content = str(getattr(m, "content", "") or "")
            if role not in ("system", "user", "assistant"):
                role = "user"
            formatted.append({"role": role, "content": content})

        if not formatted:
            formatted = [{"role": "user", "content": "Hello"}]

        try:
            completion_kwargs: Dict[str, Any] = {
                "messages": formatted,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            # Older llama-cpp-python builds reject response_format=None, so
            # only send the structured-output option when it is requested.
            if json_mode:
                completion_kwargs["response_format"] = {"type": "json_object"}
            with self._lock:
                output = llm.create_chat_completion(**completion_kwargs)

            latency_ms = int((time.time() - t0) * 1000)
            choices = output.get("choices", [])
            if not choices:
                return LLMResponse(
                    text="",
                    provider=self.provider,
                    model=self.model,
                    latency_ms=latency_ms,
                    error="Local model returned no response choices.",
                )

            text = choices[0].get("message", {}).get("content", "").strip()
            usage = output.get("usage", {})
            prompt_tokens = int(usage.get("prompt_tokens", max(1, len(str(formatted)) // 4)))
            completion_tokens = int(usage.get("completion_tokens", max(1, len(text) // 4)))
            total_tokens = prompt_tokens + completion_tokens

            raw_json = extract_json_from_text(text) if json_mode else None

            return LLMResponse(
                text=text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                provider=self.provider,
                model=self.model,
                raw_json=raw_json,
            )

        except Exception as exc:
            latency_ms = int((time.time() - t0) * 1000)
            return LLMResponse(
                text="",
                provider=self.provider,
                model=self.model,
                latency_ms=latency_ms,
                error=f"Local model generation failed: {exc}",
            )

    def test_connection(self) -> Dict[str, Any]:
        """Verify model weights availability and execute lightweight test inference."""
        t0 = time.time()
        if not self.is_downloaded():
            return {
                "ok": False,
                "latency_ms": 0,
                "error": f"Model weights not downloaded ({LOCAL_MODEL_FILENAME})",
            }

        res = self.generate(
            [ChatMessage(role="user", content="Ping. Respond with exactly: JARVIS_ONLINE")],
            max_tokens=10,
        )
        latency = int((time.time() - t0) * 1000)

        if res.error:
            return {"ok": False, "latency_ms": latency, "error": res.error}

        return {
            "ok": True,
            "latency_ms": latency,
            "reply": res.text.strip(),
            "error": None,
        }
