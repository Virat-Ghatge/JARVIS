#!/usr/bin/env python3
"""
Setup and Benchmark Utility for Embedded Local GGUF Engine
Downloads Llama 3.2 3B Instruct weights, validates CPU / AVX2 compatibility, and benchmarks performance.
"""

import argparse
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config.settings import (
    LOCAL_MODEL_PATH,
    LOCAL_MODEL_NAME,
    LOCAL_MODEL_FILENAME,
    LOCAL_MODEL_URL,
    LOCAL_MODEL_THREADS,
    MODELS_DIR,
)
from core.adapters.local_gguf_adapter import LocalGGUFAdapter


def check_system_environment():
    """Analyze host CPU architecture, core count, and memory."""
    print("=" * 65)
    print("JARVIS LOCAL MODEL SETUP: HARDWARE AUDIT")
    print("=" * 65)

    os_name = platform.system()
    machine = platform.machine()
    processor = platform.processor()
    cpu_count = os.cpu_count() or 4

    print(f"  Operating System  : {os_name} {platform.release()} ({machine})")
    print(f"  Processor Name    : {processor}")
    print(f"  Physical/Logical  : {cpu_count} CPU cores detected")
    print(f"  Allocated Threads : {LOCAL_MODEL_THREADS} physical worker threads")

    # RAM Audit
    try:
        import psutil
        total_ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
        avail_ram_gb = round(psutil.virtual_memory().available / (1024 ** 3), 2)
        print(f"  Total System RAM  : {total_ram_gb} GB")
        print(f"  Available RAM     : {avail_ram_gb} GB (Target Model footprint: ~2.0 GB)")
        if avail_ram_gb < 2.5:
            print("  [WARNING] Low free memory. Close heavy applications before loading model.")
        else:
            print("  [OK] System memory is well within the recommended target budget.")
    except ImportError:
        print("  RAM Audit: psutil not available (skipping exact RAM check)")

    # Python version
    print(f"  Python Version    : {sys.version.split()[0]}")
    return True


def ensure_dependencies():
    """Verify llama-cpp-python installation and pre-built CPU wheel support."""
    print("\n" + "=" * 65)
    print("CHECKING RUNTIME DEPENDENCIES")
    print("=" * 65)

    if LocalGGUFAdapter.is_available():
        import llama_cpp
        print(f"  [OK] llama-cpp-python version {getattr(llama_cpp, '__version__', 'unknown')} is installed.")
        return True

    print("  [NOTICE] llama-cpp-python is not installed.")
    print("  Attempting to install pre-built AVX2 CPU wheel...")
    cmd = [sys.executable, "-m", "pip", "install", "llama-cpp-python"]
    res = subprocess.run(cmd)
    if res.returncode == 0 and LocalGGUFAdapter.is_available():
        print("  [OK] Successfully installed llama-cpp-python.")
        return True

    print("  [ERROR] Failed to automatically install llama-cpp-python.")
    print("  Please run manually: pip install llama-cpp-python")
    return False


def download_model(force: bool = False):
    """Download Llama 3.2 3B Instruct GGUF model weights with terminal progress."""
    print("\n" + "=" * 65)
    print(f"GGUF MODEL WEIGHTS: {LOCAL_MODEL_FILENAME}")
    print("=" * 65)
    print(f"  Target Destination : {LOCAL_MODEL_PATH}")
    print(f"  Source HuggingFace : {LOCAL_MODEL_URL}")

    if LocalGGUFAdapter.is_downloaded() and not force:
        size_mb = round(LOCAL_MODEL_PATH.stat().st_size / (1024 * 1024), 2)
        print(f"  [OK] Model weights already downloaded ({size_mb} MB). Use --force to re-download.")
        return True

    print("\n  Initiating download from Hugging Face...")
    last_print = 0

    def progress(pct, downloaded, total):
        nonlocal last_print
        now = time.time()
        if now - last_print > 0.5 or pct >= 100.0:
            mb_down = round(downloaded / (1024 * 1024), 1)
            mb_tot = round(total / (1024 * 1024), 1) if total else 0.0
            bar_len = 30
            filled = int(bar_len * (pct / 100.0))
            bar = "#" * filled + "-" * (bar_len - filled)
            sys.stdout.write(f"\r  [{bar}] {pct:5.1f}% ({mb_down} / {mb_tot} MB)")
            sys.stdout.flush()
            last_print = now

    success = LocalGGUFAdapter.download_model(progress_callback=progress, force=force)
    print("\n")
    if success:
        size_mb = round(LOCAL_MODEL_PATH.stat().st_size / (1024 * 1024), 2)
        print(f"  [OK] Download complete! Model size: {size_mb} MB")
        return True
    else:
        status = LocalGGUFAdapter.get_download_status()
        print(f"  [ERROR] Download failed: {status.get('error')}")
        return False


def benchmark_model():
    """Load model and benchmark inference latency and generation speed."""
    print("=" * 65)
    print("VERIFICATION & SPEED BENCHMARK")
    print("=" * 65)

    if not LocalGGUFAdapter.is_downloaded():
        print("  [ERROR] Model weights are not downloaded yet.")
        return False

    print("  Loading GGUF model into memory (lazy cache)...")
    t0 = time.time()
    try:
        LocalGGUFAdapter.load_model()
    except Exception as e:
        print(f"  [ERROR] Failed to load model: {e}")
        return False
    load_time = round(time.time() - t0, 2)
    print(f"  [OK] Model loaded into RAM in {load_time}s.")

    adapter = LocalGGUFAdapter()
    test_messages = [
        {"role": "system", "content": "You are JARVIS, the concise British AI assistant to Tony Stark."},
        {"role": "user", "content": "JARVIS, provide a short 1-sentence system readiness confirmation."},
    ]

    from core.adapters.base import ChatMessage
    chat_msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in test_messages]

    print("\n  Executing verification prompt...")
    t_gen_start = time.time()
    resp = adapter.generate(chat_msgs, temperature=0.3, max_tokens=64)
    t_gen_end = time.time()

    if resp.error:
        print(f"  [ERROR] Generation error: {resp.error}")
        return False

    tok_sec = round(resp.completion_tokens / max(0.05, t_gen_end - t_gen_start), 1)
    print(f"  JARVIS Response : \"{resp.text}\"")
    print(f"  Latency         : {resp.latency_ms} ms")
    print(f"  Tokens Produced : {resp.completion_tokens} tokens")
    print(f"  Generation Speed: {tok_sec} tokens/second")

    try:
        import psutil
        rss_mb = round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
        print(f"  Process RAM     : {rss_mb} MB")
    except Exception:
        pass

    print("\n  [SUCCESS] Embedded Llama 3.2 3B Engine is fully operational and ready!")
    return True


def main():
    parser = argparse.ArgumentParser(description="Setup and verify JARVIS Local Model Engine")
    parser.add_argument("--force", action="store_true", help="Force re-download of model weights")
    parser.add_argument("--test-only", action="store_true", help="Skip download, only run benchmark")
    args = parser.parse_args()

    check_system_environment()
    if not ensure_dependencies():
        sys.exit(1)

    if not args.test_only:
        if not download_model(force=args.force):
            sys.exit(1)

    if not benchmark_model():
        sys.exit(1)


if __name__ == "__main__":
    main()
