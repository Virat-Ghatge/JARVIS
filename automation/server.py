import os
import time
import json
import asyncio
import threading
import psutil
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
)
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
from automation.meeting_bot import meeting_bot
import automation.meeting_scheduler as ms_mod
import automation.meeting_handler as mh_mod

tts_engine = getattr(tts_mod, "tts_engine", None) or getattr(tts_mod, "TTSEngine", lambda: None)()
code_executor = getattr(ce_mod, "code_executor", None) or getattr(ce_mod, "CodeExecutor", lambda: None)()
safety_interceptor = getattr(si_mod, "safety_interceptor", None) or getattr(si_mod, "SafetyInterceptor", lambda: None)()
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
                        "online": is_internet_connected(role="chat"),
                        "mic_active": voice_listener.mic_active,
                        "tts_active": getattr(tts_engine, "tts_active", True),
                        "in_meeting": meeting_bot.get_state().get("in_meeting", False),
                        "token_stats": router.get_telemetry(),
                    },
                )
            except Exception:
                pass
            await asyncio.sleep(2.5)

    asyncio.create_task(_telemetry_loop())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        await websocket.send_text(
            json.dumps({
                "type": "AUDIO_STATE",
                "data": {
                    **voice_listener.get_state(),
                    "tts_active": getattr(tts_engine, "tts_active", True),
                },
            })
        )
        await websocket.send_text(
            json.dumps({"type": "MEETING_STATE", "data": meeting_bot.get_state()})
        )
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("type") == "COMMAND" and msg.get("command"):
                    await asyncio.to_thread(engine.process_command, str(msg["command"]), "ws")
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
            **voice_listener.get_state(),
            "tts_active": getattr(tts_engine, "tts_active", True),
        },
        "meeting": meeting_bot.get_state(),
        "telemetry": router.get_telemetry(),
    }


@app.post("/api/command")
async def post_command(request: Request):
    body = await request.json()
    cmd_text = str(body.get("command") or body.get("text") or body.get("prompt") or "").strip()
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
    return {
        **voice_listener.get_state(),
        "tts_active": getattr(tts_engine, "tts_active", True),
    }


@app.post("/api/audio/toggle")
async def toggle_audio(request: Request):
    body = await request.json()
    if "mic_active" in body or body.get("target") == "mic":
        new_mic = body.get("mic_active") if "mic_active" in body else body.get("active")
        if new_mic is None:
            voice_listener.toggle_mic()
        else:
            voice_listener.set_mic_active(bool(new_mic), manual_override=True)

    if "tts_active" in body or body.get("target") == "tts":
        new_tts = body.get("tts_active") if "tts_active" in body else body.get("active")
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
        **voice_listener.get_state(),
        "tts_active": getattr(tts_engine, "tts_active", True),
    }
    await broadcast_ws("AUDIO_STATE", state)
    return state


# ==================== API KEY VAULT ROUTES ====================

def _format_vault_response() -> Dict[str, Any]:
    masked = get_masked_vault()
    return {
        "status": "ok",
        **masked,
        "vault": masked,
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
    prov = body.get("provider")
    model = body.get("model")
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
        "provider": res.get("provider"),
        "model": res.get("model"),
        "latency_ms": res.get("latency_ms", 0),
        "error": res.get("error"),
    }


# ==================== MEETINGS ROUTES ====================

def _list_scheduled_meetings() -> List[Dict[str, Any]]:
    if meeting_scheduler is None:
        return []
    for fn_name in ("list_meetings", "get_meetings", "get_scheduled_meetings"):
        fn = getattr(meeting_scheduler, fn_name, None)
        if callable(fn):
            return fn()
    return []


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


@app.post("/api/meetings")
@app.post("/api/meetings/schedule")
async def schedule_meeting_route(request: Request):
    body = await request.json()
    item = body
    if meeting_scheduler is not None:
        if hasattr(meeting_scheduler, "schedule_from_dict"):
            item = meeting_scheduler.schedule_from_dict(body)
        elif hasattr(meeting_scheduler, "add_meeting"):
            item = meeting_scheduler.add_meeting(
                title=body.get("title", "Scheduled Meeting"),
                url=body.get("url", ""),
                start_time=body.get("start_time") or body.get("time") or body.get("datetime"),
                duration_minutes=int(body.get("duration_minutes", 60)),
                recurrence=body.get("recurrence", "none"),
            )
    return {"status": "ok", "meeting": item, "meetings": _list_scheduled_meetings()}


@app.post("/api/meetings/bulk")
async def bulk_schedule_meetings_route(request: Request):
    body = await request.json()
    text = str(body.get("text") or body.get("schedule_text") or "")
    added = []
    if meeting_scheduler and hasattr(meeting_scheduler, "parse_and_schedule_bulk"):
        added = meeting_scheduler.parse_and_schedule_bulk(text)
    elif meeting_handler and hasattr(meeting_handler, "handle_command"):
        added = [meeting_handler.handle_command(line) for line in text.splitlines() if line.strip()]
    return {"status": "ok", "added": added, "meetings": _list_scheduled_meetings()}


@app.post("/api/meetings/join-url")
@app.post("/api/meetings/join")
async def join_meeting_instant_route(request: Request):
    body = await request.json()
    url = str(body.get("url", "")).strip()
    title = str(body.get("title", "Instant Meeting")).strip()
    if not url:
        raise HTTPException(status_code=400, detail="Meeting URL is required")
    return meeting_bot.join_meeting(url=url, title=title)


@app.post("/api/meetings/{meeting_id}/join")
async def join_scheduled_meeting_route(meeting_id: str):
    meetings = _list_scheduled_meetings()
    target = next((m for m in meetings if str(m.get("id")) == str(meeting_id)), None)
    if not target:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting_bot.join_meeting(url=target.get("url", ""), title=target.get("title", "Scheduled Meeting"), meeting_id=meeting_id)


@app.delete("/api/meetings/{meeting_id}")
@app.post("/api/meetings/{meeting_id}/cancel")
async def cancel_meeting_route(meeting_id: str):
    if meeting_scheduler:
        for fn_name in ("remove_meeting", "cancel_meeting", "delete_meeting"):
            fn = getattr(meeting_scheduler, fn_name, None)
            if callable(fn):
                fn(meeting_id)
                break
    return {"status": "ok", "meetings": _list_scheduled_meetings()}


@app.post("/api/meetings/leave")
async def leave_meeting_route():
    return meeting_bot.leave_meeting()


@app.post("/api/meetings/setup")
async def setup_meeting_browser_route():
    return meeting_bot.open_login_setup()


# ==================== ALARMS, SKILLS, MCP & SAFETY ROUTES ====================

@app.get("/api/alarms")
async def get_alarms_route():
    alarms_list = alarm_handler.list_alarms() if hasattr(alarm_handler, "list_alarms") else (
        alarm_handler.get_alarms() if hasattr(alarm_handler, "get_alarms") else []
    )
    return {"alarms": alarms_list}


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
    return {"status": "ok", "alarm": item, "alarms": alarms_list}


@app.delete("/api/alarms/{alarm_id}")
async def delete_alarm_route(alarm_id: str):
    for fn_name in ("remove_alarm", "delete_alarm", "cancel_alarm"):
        fn = getattr(alarm_handler, fn_name, None)
        if callable(fn):
            fn(alarm_id)
            break
    alarms_list = alarm_handler.list_alarms() if hasattr(alarm_handler, "list_alarms") else []
    return {"status": "ok", "alarms": alarms_list}


@app.get("/api/skills")
async def get_skills_route():
    skills_list = skill_store.list_skills() if (skill_store and hasattr(skill_store, "list_skills")) else (
        skill_store.get_skills() if (skill_store and hasattr(skill_store, "get_skills")) else []
    )
    return {"skills": skills_list, "recording": getattr(skill_store, "recording", False)}


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
    return {"status": "ok", "skills": skills_list}


@app.delete("/api/skills/{skill_name}")
async def delete_skill_route(skill_name: str):
    if skill_store:
        for fn_name in ("remove_skill", "delete_skill"):
            fn = getattr(skill_store, fn_name, None)
            if callable(fn):
                fn(skill_name)
                break
    skills_list = skill_store.list_skills() if (skill_store and hasattr(skill_store, "list_skills")) else []
    return {"status": "ok", "skills": skills_list}


@app.post("/api/skills/teach/start")
async def start_teach_mode_route(request: Request):
    body = await request.json()
    name = str(body.get("name") or body.get("trigger") or "New Routine")
    if skill_store and hasattr(skill_store, "start_recording"):
        skill_store.start_recording(name)
    return {"status": "recording", "name": name}


@app.post("/api/skills/teach/stop")
async def stop_teach_mode_route():
    res = skill_store.stop_recording() if (skill_store and hasattr(skill_store, "stop_recording")) else {}
    skills_list = skill_store.list_skills() if (skill_store and hasattr(skill_store, "list_skills")) else []
    return {"status": "saved", "skill": res, "skills": skills_list}


@app.get("/api/mcp")
async def get_mcp_servers_route():
    servers = mcp_client.list_servers() if (mcp_client and hasattr(mcp_client, "list_servers")) else []
    return {"servers": servers}


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


# Mount built React HUD static files
if UI_DIST_DIR.exists():
    assets_dir = UI_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        candidate = UI_DIST_DIR / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        index_file = UI_DIST_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse({"status": "UI build not found in ui/dist"})
