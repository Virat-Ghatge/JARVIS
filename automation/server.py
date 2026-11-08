import os
import time
import json
import asyncio
import threading
import psutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from config.settings import (
    UI_DIST_DIR,
    init_config_files,
    load_vault,
    save_vault,
    get_masked_vault,
    add_provider_key,
    remove_provider_key,
    set_active_key_index,
    add_custom_endpoint,
    remove_custom_endpoint,
    set_role_target,
    update_role_mappings,
    is_internet_connected,
    get_local_model_status,
    is_local_first_mode,
    set_local_first_mode,
    get_role_target,
    is_cloud_api_enabled,
    set_cloud_api_enabled,
)
from core.adapters.local_gguf_adapter import LocalGGUFAdapter
from core.llm_router import router
from core.engine import engine
from core.context_manager import context_manager
from audio.voice_listener import voice_listener
import audio.tts_engine as tts_mod
import agent_os.code_executor as ce_mod
from agent_os.state_machine import os_agent
import agent_os.safety_interceptor as si_mod
import integrations.skill_store as ss_mod
import integrations.mcp_client as mcp_mod
from integrations.handlers import alarm as alarm_handler
from integrations.handlers import music as music_handler_mod
from integrations.handlers import web_search as web_search_mod
from automation.meeting_bot import meeting_bot
import automation.meeting_scheduler as ms_mod
import automation.meeting_handler as mh_mod

tts_engine = getattr(tts_mod, "tts_engine", None) or getattr(tts_mod, "TTSEngine", lambda: None)()
code_executor = getattr(ce_mod, "code_executor", None) or getattr(ce_mod, "CodeExecutor", lambda: None)()
safety_interceptor = getattr(si_mod, "safety_interceptor", None) or getattr(si_mod, "SafetyInterceptor", lambda: None)()
if hasattr(ss_mod, "is_teaching"):
    skill_store = ss_mod
else:
    skill_store = getattr(ss_mod, "skill_store", None) or getattr(ss_mod, "SkillStore", lambda: None)()
mcp_client = getattr(mcp_mod, "mcp_client", None) or getattr(mcp_mod, "MCPClient", lambda: None)()
meeting_scheduler = getattr(ms_mod, "meeting_scheduler", None) or getattr(ms_mod, "MeetingScheduler", lambda: None)()
meeting_handler = getattr(mh_mod, "meeting_handler", None) or getattr(mh_mod, "MeetingHandler", lambda: None)()

init_config_files()

app = FastAPI(title="JARVIS 2.0 Holographic HUD Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_static_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


# WebSocket Connection Manager
_ws_clients: Set[WebSocket] = set()
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def _audio_state() -> Dict[str, Any]:
    state = dict(voice_listener.get_state())
    state["meeting_auto_muted"] = bool(
        getattr(voice_listener, "meeting_auto_muted", state.get("in_meeting_auto_muted", False))
    )
    state["tts_active"] = getattr(tts_engine, "tts_active", True)
    return state


async def broadcast_ws(event_type: str, payload: Any) -> None:
    if not _ws_clients:
        return
    message = json.dumps({"type": event_type, "event": event_type, "data": payload, "payload": payload})
    dead: List[WebSocket] = []
    for ws in list(_ws_clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


def broadcast_ws_sync(event_type: str, payload: Any) -> None:
    global _main_loop
    if _main_loop and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(broadcast_ws(event_type, payload), _main_loop)


# Wire Subsystem Event Listeners to WebSocket Broadcast
router.register_telemetry_listener(lambda d: broadcast_ws_sync("TOKEN_TELEMETRY", d))
engine.register_chat_listener(lambda d: broadcast_ws_sync("CHAT_MESSAGE", d))
if code_executor and hasattr(code_executor, "register_step_listener"):
    code_executor.register_step_listener(lambda d: broadcast_ws_sync("AGENT_STEP", d))
os_agent.register_step_listener(lambda d: broadcast_ws_sync("AGENT_STEP", d))
if safety_interceptor and hasattr(safety_interceptor, "register_approval_listener"):
    safety_interceptor.register_approval_listener(lambda d: broadcast_ws_sync("APPROVAL_REQUIRED", d))
meeting_bot.register_state_listener(lambda d: broadcast_ws_sync("MEETING_STATE", d))
voice_listener.register_state_listener(
    lambda d: broadcast_ws_sync(
        "AUDIO_STATE",
        {
            **d,
            "meeting_auto_muted": bool(d.get("in_meeting_auto_muted", False)),
            "tts_active": getattr(tts_engine, "tts_active", True),
        },
    )
)


@app.on_event("startup")
async def on_startup():
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    voice_listener.set_callback(lambda text: engine.process_command(text, source="voice"))

    async def _telemetry_loop():
        while True:
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                batt = psutil.sensors_battery()
                await broadcast_ws(
                    "SYSTEM_TELEMETRY",
                    {
                        "cpu": cpu,
                        "ram": mem,
                        "memory": mem,
                        "battery": batt.percent if batt else 100,
                        "plugged": batt.power_plugged if batt else True,
                        "charging": batt.power_plugged if batt else True,
                        "online": is_internet_connected(role="chat"),
                        "mic_active": voice_listener.mic_active,
                        "tts_active": getattr(tts_engine, "tts_active", True),
                        "meeting_auto_muted": bool(getattr(voice_listener, "meeting_auto_muted", False)),
                        "in_meeting": meeting_bot.get_state().get("in_meeting", False),
                        "token_stats": router.get_telemetry(),
                    },
                )
            except Exception:
                pass
            await asyncio.sleep(2.5)

    asyncio.create_task(_telemetry_loop())


@app.on_event("shutdown")
async def on_shutdown():
    try:
        voice_listener.shutdown()
    except Exception:
        pass
    try:
        if hasattr(tts_engine, "shutdown"):
            tts_engine.shutdown()
    except Exception:
        pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        audio_state = {
            **_audio_state(),
        }
        await websocket.send_text(
            json.dumps({
                "type": "AUDIO_STATE",
                "event": "AUDIO_STATE",
                "data": audio_state,
                "payload": audio_state,
            })
        )
        meeting_state = meeting_bot.get_state()
        await websocket.send_text(
            json.dumps({
                "type": "MEETING_STATE",
                "event": "MEETING_STATE",
                "data": meeting_state,
                "payload": meeting_state,
            })
        )
        batt = psutil.sensors_battery()
        initial_telemetry = {
            "cpu": psutil.cpu_percent(interval=None),
            "ram": psutil.virtual_memory().percent,
            "memory": psutil.virtual_memory().percent,
            "battery": batt.percent if batt else 100,
            "plugged": batt.power_plugged if batt else True,
            "charging": batt.power_plugged if batt else True,
            "online": is_internet_connected(role="chat"),
            "mic_active": voice_listener.mic_active,
            "tts_active": getattr(tts_engine, "tts_active", True),
            "meeting_auto_muted": bool(getattr(voice_listener, "meeting_auto_muted", False)),
            "in_meeting": meeting_bot.get_state().get("in_meeting", False),
            "token_stats": router.get_telemetry(),
        }
        await websocket.send_text(
            json.dumps({
                "type": "SYSTEM_TELEMETRY",
                "event": "SYSTEM_TELEMETRY",
                "data": initial_telemetry,
                "payload": initial_telemetry,
            })
        )
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                mtype = msg.get("type") or msg.get("event")
                payload_val = msg.get("payload")
                query_val = None
                if isinstance(payload_val, dict):
                    query_val = payload_val.get("query") or payload_val.get("command")
                cmd_text = msg.get("command") or query_val or msg.get("query")
                if mtype in ("COMMAND", "USER_COMMAND") and cmd_text:
                    await asyncio.to_thread(engine.process_command, str(cmd_text), "ws")
            except Exception:
                pass
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
    except Exception:
        _ws_clients.discard(websocket)


# ==================== REST API ROUTES ====================

@app.get("/api/health")
@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "online": is_internet_connected(role="chat"),
        "audio": {
            **_audio_state(),
        },
        "meeting": meeting_bot.get_state(),
        "telemetry": router.get_telemetry(),
        "connection": _connection_status(),
    }


@app.post("/api/command")
async def post_command(request: Request):
    body = await request.json()
    cmd_text = str(body.get("command") or body.get("query") or body.get("text") or body.get("prompt") or "").strip()
    if not cmd_text:
        raise HTTPException(status_code=400, detail="Command text is required")
    res = await asyncio.to_thread(engine.process_command, cmd_text, body.get("source", "hud"))
    return dict(res)


@app.post("/api/context/clear")
async def clear_chat_context():
    context_manager.clear()
    return {"status": "ok", "message": "Conversation context cleared."}


@app.get("/api/audio/state")
async def get_audio_state():
    return _audio_state()


@app.post("/api/audio/toggle")
async def toggle_audio(request: Request):
    body = await request.json()
    if "mic_active" in body or body.get("target") == "mic":
        new_mic = body.get("mic_active") if "mic_active" in body else body.get("active", body.get("enabled"))
        if new_mic is None:
            voice_listener.toggle_mic()
        else:
            voice_listener.set_mic_active(bool(new_mic), manual_override=True)

    if "tts_active" in body or body.get("target") == "tts":
        new_tts = body.get("tts_active") if "tts_active" in body else body.get("active", body.get("enabled"))
        if new_tts is None:
            curr = getattr(tts_engine, "tts_active", True)
            if hasattr(tts_engine, "set_tts_active"):
                tts_engine.set_tts_active(not curr)
            elif tts_engine is not None:
                tts_engine.tts_active = not curr
        else:
            if hasattr(tts_engine, "set_tts_active"):
                tts_engine.set_tts_active(bool(new_tts))
            elif tts_engine is not None:
                tts_engine.tts_active = bool(new_tts)

    state = {
        **_audio_state(),
    }
    await broadcast_ws("AUDIO_STATE", state)
    return state


# ==================== API KEY VAULT ROUTES ====================

def _format_vault_response() -> Dict[str, Any]:
    masked = get_masked_vault()
    return {
        "ok": True,
        "status": "ok",
        "autonomous_trust_mode": masked.get("safety", {}).get("auto_approve_safe", True),
        **masked,
        "vault": masked,
    }


def _connection_status() -> Dict[str, Any]:
    """Return a safe, UI-ready view of the active route and its fallbacks."""
    local = get_local_model_status()
    try:
        chain = router._build_candidate_chain("chat")
        fallback_chain = [
            {"provider": item.get("provider"), "model": item.get("model")}
            for item in chain
        ]
    except Exception:
        fallback_chain = []
    target = get_role_target("chat")
    return {
        "local_first": is_local_first_mode(),
        "local": {
            "available": bool(local.get("runtime_available")),
            "downloaded": bool(local.get("downloaded")),
            "ready": bool(local.get("ready")),
            "loaded": bool(local.get("loaded")),
            "model": local.get("model_name"),
        },
        "configured_target": {
            "provider": target.get("provider"),
            "model": target.get("model"),
        },
        "fallback_chain": fallback_chain,
    }


@app.get("/api/vault")
@app.get("/api/vault/keys")
async def get_vault_endpoint():
    return _format_vault_response()


@app.post("/api/vault/key")
@app.post("/api/vault/keys")
async def add_vault_key_endpoint(request: Request):
    body = await request.json()
    provider = str(body.get("provider", "gemini")).strip().lower()
    key = str(body.get("key") or body.get("api_key") or body.get("value") or "").strip()
    label = str(body.get("label") or "").strip()
    action = str(body.get("action", "add")).lower()
    if action in ("delete", "remove"):
        remove_provider_key(provider, key)
        return _format_vault_response()
    if not key:
        raise HTTPException(status_code=400, detail="API key value cannot be empty.")
    add_provider_key(provider=provider, key=key, label=label)
    return _format_vault_response()


@app.delete("/api/vault/key")
@app.delete("/api/vault/keys")
@app.post("/api/vault/key/remove")
async def delete_vault_key_endpoint(
    request: Request,
    provider: Optional[str] = None,
    index: Optional[int] = None,
    key_id: Optional[str] = None,
):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    prov = provider or body.get("provider")
    target = index if index is not None else (key_id or body.get("index") if body.get("index") is not None else (body.get("id") or body.get("key")))
    if not prov or target is None:
        raise HTTPException(status_code=400, detail="Provider and key index/id are required.")
    remove_provider_key(str(prov), target)
    return _format_vault_response()


@app.delete("/api/vault/key/{provider}/{key_or_index}")
@app.delete("/api/vault/keys/{provider}/{key_or_index}")
async def delete_vault_key_path_endpoint(provider: str, key_or_index: str):
    remove_provider_key(provider, key_or_index)
    return _format_vault_response()


@app.post("/api/vault/key/activate")
@app.post("/api/vault/active")
async def set_active_vault_key_endpoint(request: Request):
    body = await request.json()
    provider = str(body.get("provider", "gemini")).strip().lower()
    index = int(body.get("index", 0))
    set_active_key_index(provider, index)
    return _format_vault_response()


@app.post("/api/vault/endpoint")
@app.post("/api/vault/endpoints")
@app.post("/api/vault/custom")
async def add_custom_endpoint_route(request: Request):
    body = await request.json()
    add_custom_endpoint(body)
    return _format_vault_response()


@app.delete("/api/vault/endpoint/{ep_id}")
@app.delete("/api/vault/endpoints/{ep_id}")
@app.delete("/api/vault/custom/{ep_id}")
async def remove_custom_endpoint_route(ep_id: str):
    remove_custom_endpoint(ep_id)
    return _format_vault_response()


@app.post("/api/vault/role")
@app.post("/api/vault/roles")
async def update_vault_roles_route(request: Request):
    body = await request.json()
    if "role" in body and "provider" in body:
        set_role_target(str(body["role"]), body["provider"], model=body.get("model"))
    elif "role_mappings" in body and isinstance(body["role_mappings"], dict):
        update_role_mappings(body["role_mappings"])
    elif isinstance(body, dict):
        update_role_mappings(body)
    return _format_vault_response()


@app.post("/api/vault/test")
async def test_vault_llm_route(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    requested_provider = body.get("provider")
    prov = str(requested_provider).strip() if requested_provider else None
    model = body.get("model")
    if not prov:
        chain = router._build_candidate_chain("chat")
        first = chain[0] if chain else {"provider": "local", "model": None}
        prov = str(first.get("provider") or "local")
        model = model or first.get("model")
    if not model or model == "default":
        model = router._resolve_model(prov, None)
    res = await asyncio.to_thread(
        router.chat,
        [{"role": "user", "content": "Respond with: JARVIS_ONLINE"}],
        "chat",
        "You are JARVIS. Reply with a short confirmation.",
        prov,
        model,
    )
    return {
        "status": "ok" if res.get("success") else "error",
        "success": bool(res.get("success")),
        "reply": res.get("content"),
        "provider": res.get("provider") or prov,
        "model": res.get("model") or model,
        "latency_ms": res.get("latency_ms", 0),
        "error": res.get("error"),
        "connection": _connection_status(),
    }


@app.get("/api/vault/local-model")
async def get_local_model_endpoint():
    status = get_local_model_status()
    status["local_first_mode"] = is_local_first_mode()
    return {"ok": True, **status}


@app.post("/api/vault/local-model/download")
async def download_local_model_endpoint():
    def _run_download():
        LocalGGUFAdapter.download_model()
    t = threading.Thread(target=_run_download, daemon=True)
    t.start()
    return {"ok": True, "message": "Download initiated in background", **get_local_model_status()}


@app.post("/api/vault/local-model/unload")
async def unload_local_model_endpoint():
    LocalGGUFAdapter.unload_model()
    return {"ok": True, "message": "Local model unloaded from memory", **get_local_model_status()}


@app.post("/api/vault/local-model/toggle-local-first")
async def toggle_local_first_endpoint(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    current = is_local_first_mode()
    target = bool(body.get("enabled", not current))
    set_local_first_mode(target)
    return {"ok": True, "local_first_mode": target}


@app.post("/api/vault/local-model/test")
async def test_local_model_endpoint():
    adapter = LocalGGUFAdapter()
    res = await asyncio.to_thread(adapter.test_connection)
    return res


# ==================== MEETINGS ROUTES ====================

def _list_scheduled_meetings() -> List[Dict[str, Any]]:
    sched = getattr(getattr(engine, "meeting_handler", None), "scheduler", None) or getattr(meeting_handler, "scheduler", None) or meeting_scheduler
    if sched is None:
        return []
    for fn_name in ("list_meetings", "get_meetings", "get_scheduled_meetings", "get_all"):
        fn = getattr(sched, fn_name, None)
        if callable(fn):
            return fn()
    return getattr(sched, "_meetings", [])


@app.get("/api/meetings")
async def list_meetings():
    return {
        "meetings": _list_scheduled_meetings(),
        "summaries": meeting_bot.get_summaries(),
        "bot_state": meeting_bot.get_state(),
    }


@app.get("/api/meetings/summaries")
async def get_meeting_summaries():
    return {"summaries": meeting_bot.get_summaries()}


def _clean_naive_datetime_str(val: Any) -> Any:
    if isinstance(val, str):
        s = val.strip()
        if s.endswith("Z"):
            s = s[:-1]
        if "+" in s:
            s = s.split("+")[0]
        try:
            dt = datetime.fromisoformat(s)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            return s
    elif isinstance(val, datetime):
        if val.tzinfo is not None:
            val = val.replace(tzinfo=None)
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    return val


@app.post("/api/meetings")
@app.post("/api/meetings/schedule")
async def schedule_meeting_route(request: Request):
    body = await request.json()
    item = dict(body)
    raw_st = body.get("start_time") or body.get("time") or body.get("datetime")
    clean_st = _clean_naive_datetime_str(raw_st)
    meeting_url = body.get("meeting_url") or body.get("url", "")
    title = body.get("title", "Scheduled Meeting")

    # Use scheduler
    sched = getattr(getattr(engine, "meeting_handler", None), "scheduler", None) or getattr(meeting_handler, "scheduler", None) or meeting_scheduler
    if sched is not None:
        if hasattr(sched, "add_meeting"):
            try:
                dt_obj = datetime.fromisoformat(clean_st) if isinstance(clean_st, str) else clean_st
            except Exception:
                dt_obj = datetime.now()
            item = sched.add_meeting(
                title=title,
                meeting_url=meeting_url,
                start_time=dt_obj,
                auto_leave=body.get("auto_leave", True),
            )
        elif hasattr(sched, "schedule_from_dict"):
            body_copy = dict(body)
            body_copy["start_time"] = clean_st
            body_copy["meeting_url"] = meeting_url
            item = sched.schedule_from_dict(body_copy)
    if isinstance(item, dict):
        item["start_time"] = _clean_naive_datetime_str(item.get("start_time"))
    return {"ok": True, "status": "ok", "meeting": item, "meetings": _list_scheduled_meetings()}


@app.post("/api/meetings/bulk")
async def bulk_schedule_meetings_route(request: Request):
    body = await request.json()
    added = []
    sched = getattr(getattr(engine, "meeting_handler", None), "scheduler", None) or getattr(meeting_handler, "scheduler", None) or meeting_scheduler
    if isinstance(body, list):
        for entry in body:
            title = entry.get("title", "Bulk Meeting")
            url = entry.get("meeting_url") or entry.get("url", "")
            raw_st = entry.get("start_time") or entry.get("time")
            clean_st = _clean_naive_datetime_str(raw_st)
            try:
                dt_obj = datetime.fromisoformat(clean_st) if isinstance(clean_st, str) else clean_st
            except Exception:
                dt_obj = datetime.now()
            if sched and hasattr(sched, "add_meeting"):
                m = sched.add_meeting(title=title, meeting_url=url, start_time=dt_obj)
                added.append(m)
    elif isinstance(body, dict):
        text = str(body.get("text") or body.get("schedule_text") or "")
        if sched and hasattr(sched, "parse_and_schedule_bulk"):
            added = sched.parse_and_schedule_bulk(text)
    return {"ok": True, "status": "ok", "count": len(added), "added": added, "meetings": _list_scheduled_meetings()}


@app.post("/api/meetings/join-url")
@app.post("/api/meetings/join")
async def join_meeting_instant_route(request: Request):
    body = await request.json()
    url = str(body.get("url") or body.get("meeting_url") or "").strip()
    title = str(body.get("title", "Instant Meeting")).strip()
    if not url:
        raise HTTPException(status_code=400, detail="Meeting URL is required")
    res = meeting_bot.join_meeting(url=url, title=title)
    return {"ok": True, **res}


@app.post("/api/meetings/{meeting_id}/join")
async def join_scheduled_meeting_route(meeting_id: str):
    sched = getattr(getattr(engine, "meeting_handler", None), "scheduler", None) or getattr(meeting_handler, "scheduler", None) or meeting_scheduler
    if sched:
        if hasattr(sched, "mark_active"):
            sched.mark_active(meeting_id)
        target = sched.get_by_id(meeting_id) if hasattr(sched, "get_by_id") else None
        if target:
            target["status"] = "active"
            if hasattr(sched, "_save"):
                sched._save()
            elif hasattr(sched, "_save_meetings"):
                sched._save_meetings()
            bot = getattr(getattr(engine, "meeting_handler", None), "bot", None) or getattr(meeting_handler, "bot", None) or meeting_bot
            if bot and hasattr(bot, "join_meeting"):
                bot.join_meeting(url=target.get("meeting_url") or target.get("url", ""), title=target.get("title", "Scheduled Meeting"), meeting_id=meeting_id)
            return {"ok": True, "status": "active", "meeting": target}
    return {"ok": True, "status": "active"}


@app.delete("/api/meetings/{meeting_id}")
@app.post("/api/meetings/{meeting_id}/cancel")
async def cancel_meeting_route(meeting_id: str):
    sched = getattr(getattr(engine, "meeting_handler", None), "scheduler", None) or getattr(meeting_handler, "scheduler", None) or meeting_scheduler
    if sched:
        for fn_name in ("remove_meeting", "cancel_meeting", "delete_meeting"):
            fn = getattr(sched, fn_name, None)
            if callable(fn):
                fn(meeting_id)
                break
    return {"ok": True, "status": "ok", "meetings": _list_scheduled_meetings()}


@app.post("/api/meetings/leave")
async def leave_meeting_route():
    res = meeting_bot.leave_meeting()
    return {"ok": True, **res}


@app.post("/api/meetings/setup")
async def setup_meeting_browser_route():
    return meeting_bot.open_login_setup()


# ==================== ALARMS, SKILLS, MCP & SAFETY ROUTES ====================

@app.get("/api/alarms")
async def get_alarms_route():
    alarms_list = alarm_handler.list_alarms() if hasattr(alarm_handler, "list_alarms") else (
        alarm_handler.get_alarms() if hasattr(alarm_handler, "get_alarms") else []
    )
    return {"alarms": alarms_list, "timers": []}


@app.post("/api/alarms")
async def add_alarm_route(request: Request):
    body = await request.json()
    time_str = str(body.get("time") or body.get("alarm_time") or "")
    label = str(body.get("label") or "Alarm")
    if hasattr(alarm_handler, "add_alarm"):
        item = alarm_handler.add_alarm(time_str, label=label)
    elif hasattr(alarm_handler, "set_alarm"):
        item = alarm_handler.set_alarm(time_str, label=label)
    else:
        item = {"time": time_str, "label": label}
    alarms_list = alarm_handler.list_alarms() if hasattr(alarm_handler, "list_alarms") else []
    return {"ok": True, "status": "ok", "alarm": item, "alarms": alarms_list, "timers": []}


@app.delete("/api/alarms/{alarm_id}")
async def delete_alarm_route(alarm_id: str):
    for fn_name in ("remove_alarm", "delete_alarm", "cancel_alarm"):
        fn = getattr(alarm_handler, fn_name, None)
        if callable(fn):
            fn(alarm_id)
            break
    alarms_list = alarm_handler.list_alarms() if hasattr(alarm_handler, "list_alarms") else []
    return {"ok": True, "status": "ok", "alarms": alarms_list, "timers": []}


@app.get("/api/skills")
async def get_skills_route():
    skills_list = skill_store.list_skills() if (skill_store and hasattr(skill_store, "list_skills")) else (
        skill_store.get_skills() if (skill_store and hasattr(skill_store, "get_skills")) else []
    )
    return skills_list


@app.post("/api/skills")
async def add_skill_route(request: Request):
    body = await request.json()
    if skill_store and hasattr(skill_store, "add_skill"):
        skill_store.add_skill(
            name=body.get("name", "Custom Skill"),
            trigger=body.get("trigger", body.get("name", "")),
            steps=body.get("steps", []),
        )
    skills_list = skill_store.list_skills() if (skill_store and hasattr(skill_store, "list_skills")) else []
    return {"ok": True, "status": "ok", "skills": skills_list}


@app.delete("/api/skills/{skill_name}")
async def delete_skill_route(skill_name: str):
    if skill_store:
        for fn_name in ("delete_skill", "remove_skill"):
            fn = getattr(skill_store, fn_name, None)
            if callable(fn):
                fn(skill_name)
                break
    skills_list = skill_store.list_skills() if (skill_store and hasattr(skill_store, "list_skills")) else []
    return {"ok": True, "status": "ok", "skills": skills_list}


@app.post("/api/skills/teach/start")
async def start_teach_mode_route(request: Request):
    body = await request.json()
    name = str(body.get("name") or body.get("trigger") or "New Routine")
    triggers = body.get("trigger_phrases") or [name]
    if skill_store:
        if hasattr(skill_store, "start_teach_mode"):
            skill_store.start_teach_mode(name=name, trigger_phrases=triggers)
        elif hasattr(skill_store, "start_recording"):
            skill_store.start_recording(name)
    return {"ok": True, "status": "recording", "is_teaching": True, "name": name}


@app.get("/api/skills/teach/status")
async def teach_mode_status_route():
    is_t = False
    if skill_store:
        if callable(getattr(skill_store, "is_teaching", None)):
            is_t = skill_store.is_teaching()
        else:
            is_t = getattr(skill_store, "is_teaching", None) or getattr(skill_store, "recording", False)
    return {"ok": True, "is_teaching": bool(is_t)}


@app.post("/api/skills/teach/stop")
async def stop_teach_mode_route(request: Request = None):
    save = True
    if request:
        try:
            body = await request.json()
            if isinstance(body, dict) and "save" in body:
                save = bool(body["save"])
        except Exception:
            pass
    saved_skill = None
    if skill_store:
        if hasattr(skill_store, "stop_teach_mode"):
            saved_skill = skill_store.stop_teach_mode(save=save)
        elif hasattr(skill_store, "stop_recording"):
            saved_skill = skill_store.stop_recording(save=save)
    skills_list = skill_store.list_skills() if (skill_store and hasattr(skill_store, "list_skills")) else []
    return {"ok": True, "status": "saved", "saved": saved_skill, "skill": saved_skill, "skills": skills_list}


@app.get("/api/mcp")
async def get_mcp_servers_route():
    servers = mcp_client.list_servers() if (mcp_client and hasattr(mcp_client, "list_servers")) else []
    tools = mcp_client.list_tools() if (mcp_client and hasattr(mcp_client, "list_tools")) else []
    return {"servers": servers, "tools": tools}


@app.post("/api/mcp")
async def add_mcp_server_route(request: Request):
    body = await request.json()
    if mcp_client and hasattr(mcp_client, "add_server"):
        mcp_client.add_server(body)
    servers = mcp_client.list_servers() if (mcp_client and hasattr(mcp_client, "list_servers")) else []
    return {"status": "ok", "servers": servers}


@app.delete("/api/mcp/{server_id}")
async def delete_mcp_server_route(server_id: str):
    if mcp_client and hasattr(mcp_client, "remove_server"):
        mcp_client.remove_server(server_id)
    servers = mcp_client.list_servers() if (mcp_client and hasattr(mcp_client, "list_servers")) else []
    return {"status": "ok", "servers": servers}


@app.post("/api/agent/abort")
async def abort_os_agent_route():
    aborted = os_agent.abort_current_task()
    return {"status": "aborted", "aborted": aborted}


@app.post("/api/approval/{req_id}")
async def resolve_safety_approval_route(req_id: str, request: Request):
    body = await request.json()
    approved = bool(body.get("approved", False))
    if safety_interceptor and hasattr(safety_interceptor, "resolve_approval"):
        safety_interceptor.resolve_approval(req_id, approved)
    return {"status": "ok", "id": req_id, "approved": approved}


# ==================== CLOUD API & SUBSYSTEM HARDENING ROUTES ====================

@app.get("/api/cloud-api-toggle")
async def get_cloud_api_toggle_route():
    enabled = is_cloud_api_enabled()
    return {"cloud_api_enabled": enabled}


@app.post("/api/cloud-api-toggle")
async def post_cloud_api_toggle_route(request: Request):
    body = await request.json()
    enabled_val = body.get("enabled") if "enabled" in body else body.get("cloud_api_enabled", True)
    target_enabled = bool(enabled_val)
    set_cloud_api_enabled(target_enabled)
    await broadcast_ws("CLOUD_API_TOGGLED", {"cloud_api_enabled": target_enabled})
    return {"cloud_api_enabled": target_enabled, "status": "ok"}


@app.get("/api/subsystems/alarms")
async def get_subsystems_alarms_route():
    handler = getattr(engine, "alarm_handler", None) or alarm_handler.get_alarm_handler()
    active_alarms = handler.get_active_alarms() if hasattr(handler, "get_active_alarms") else getattr(handler, "alarms", [])
    active_timers = getattr(handler, "timers", [])
    return {"alarms": active_alarms, "timers": active_timers}


@app.post("/api/subsystems/alarms")
async def post_subsystems_alarms_route(request: Request):
    body = await request.json()
    handler = getattr(engine, "alarm_handler", None) or alarm_handler.get_alarm_handler()
    cmd = str(body.get("command") or body.get("time") or "").strip()
    if not cmd:
        raise HTTPException(status_code=400, detail="Alarm command or time is required.")
    if "set alarm" not in cmd.lower() and "alarm" not in cmd.lower():
        cmd = f"set alarm for {cmd}"
    msg = handler.set_alarm(cmd)
    active_alarms = handler.get_active_alarms() if hasattr(handler, "get_active_alarms") else getattr(handler, "alarms", [])
    return {"status": "ok", "message": msg, "alarms": active_alarms}


@app.delete("/api/subsystems/alarms/{alarm_id}")
async def delete_subsystems_alarm_route(alarm_id: str):
    handler = getattr(engine, "alarm_handler", None) or alarm_handler.get_alarm_handler()
    success = False
    if hasattr(handler, "cancel_alarm_by_id"):
        success = handler.cancel_alarm_by_id(alarm_id)
    elif hasattr(handler, "cancel_alarm"):
        res = handler.cancel_alarm(alarm_id)
        success = "cancelled" in res.lower()
    if not success:
        raise HTTPException(status_code=404, detail=f"Alarm '{alarm_id}' not found.")
    return {"status": "ok", "message": f"Alarm '{alarm_id}' cancelled.", "alarm_id": alarm_id}


@app.get("/api/subsystems/music")
async def get_subsystems_music_route():
    handler = getattr(engine, "music_handler", None) or music_handler_mod.music_handler
    state = handler.get_playback_state() if hasattr(handler, "get_playback_state") else getattr(handler, "current_state", {"song": "", "platform": "default", "state": "stopped"})
    return dict(state)


@app.post("/api/subsystems/music/control")
async def post_subsystems_music_control_route(request: Request):
    body = await request.json()
    action = str(body.get("action") or body.get("command") or "play_pause").strip()
    handler = getattr(engine, "music_handler", None) or music_handler_mod.music_handler
    res = handler.control_playback(action)
    state = handler.get_playback_state() if hasattr(handler, "get_playback_state") else getattr(handler, "current_state", {})
    await broadcast_ws("MUSIC_STATE_CHANGED", state)
    return {"status": "ok", "action": action, "playback": state, "result": res}


# Mount built React HUD static files
(UI_DIST_DIR / "assets").mkdir(parents=True, exist_ok=True)
if not any(getattr(route, "path", None) == "/assets" for route in getattr(app, "routes", [])):
    app.mount("/assets", StaticFiles(directory=str(UI_DIST_DIR / "assets")), name="assets")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
    if full_path.startswith("assets/"):
        candidate = UI_DIST_DIR / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        raise HTTPException(status_code=404, detail="Static asset not found")
    candidate = UI_DIST_DIR / full_path
    if full_path and candidate.exists() and candidate.is_file():
        return FileResponse(str(candidate))
    index_file = UI_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"status": "UI build not found in ui/dist"}, status_code=503)
