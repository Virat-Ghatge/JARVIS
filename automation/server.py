#!/usr/bin/env python3
"""
FastAPI REST & WebSocket Server (:5050) for JARVIS 2.0
Serves the Holographic HUD React frontend and provides real-time bi-directional
telemetry and command streaming over WebSockets.
"""

import asyncio
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Internal JARVIS modules
from config.settings import (
    BASE_DIR,
    MEETINGS_FILE,
    ALARMS_FILE,
    SKILLS_FILE,
    MCP_SERVERS_FILE,
    UI_DIST_DIR,
    add_provider_key,
    get_active_key,
    get_masked_vault,
    get_vault,
    is_internet_connected,
    load_vault,
    remove_provider_key,
    save_vault,
)
from core.adapters.openai_compat import fetch_models
from core.engine import engine
from core.llm_router import router
from agent_os.code_executor import code_executor
from agent_os.os_actuator import os_actuator
from agent_os.safety_interceptor import safety_interceptor
from agent_os.state_machine import os_agent
from integrations.mcp_client import mcp_client
from integrations.skill_store import skill_store
from integrations.workspace_rag import workspace_rag
from automation.meeting_bot import MeetingBot

app = FastAPI(title="JARVIS 2.0 Holographic HUD Server", version="2.0.0")

# Enable CORS for local Vite dev and pywebview
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket Connections Pool
connected_clients: List[WebSocket] = []
clients_lock = threading.Lock()
main_event_loop = None


def broadcast_ws_sync(event_type: str, payload: Dict[str, Any]) -> None:
    """Thread-safe synchronous helper to broadcast to WebSocket clients."""
    global main_event_loop
    message = json.dumps({"type": event_type, "payload": payload})
    with clients_lock:
        clients = list(connected_clients)

    if not clients or not main_event_loop or main_event_loop.is_closed():
        return

    for ws in clients:
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(message), main_event_loop)
        except Exception:
            pass


# ── Wire System & Agent Listeners to WebSocket Broadcasts ────────────
router.register_telemetry_listener(lambda data: broadcast_ws_sync("TOKEN_TELEMETRY", data))
engine.register_chat_listener(lambda data: broadcast_ws_sync("CHAT_MESSAGE", data))
code_executor.register_step_listener(lambda data: broadcast_ws_sync("AGENT_STEP", data))
os_agent.register_step_listener(lambda data: broadcast_ws_sync("AGENT_STEP", data))
safety_interceptor.register_approval_listener(lambda data: broadcast_ws_sync("APPROVAL_REQUIRED", data))


# ── WebSocket Endpoint ────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()
    await websocket.accept()

    with clients_lock:
        connected_clients.append(websocket)
    print(f"[WebSocket] HUD client connected (Total: {len(connected_clients)})")

    # Send initial states immediately
    try:
        await websocket.send_text(json.dumps({
            "type": "AUDIO_STATE",
            "payload": {
                "mic_active": engine.get_mic_active(),
                "tts_active": engine.get_tts_active(),
                "status": "idle",
                "meeting_auto_muted": getattr(engine.listener, "meeting_auto_muted", False),
            }
        }))
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                mtype = msg.get("type", "")
                mpayload = msg.get("payload", {})

                if mtype == "USER_COMMAND":
                    q = mpayload.get("query", "")
                    src = mpayload.get("source", "text")
                    threading.Thread(target=engine.process_command, args=(q, src), daemon=True).start()
            except Exception as parse_err:
                print(f"[WebSocket] Inbound parse error: {parse_err}")

    except WebSocketDisconnect:
        with clients_lock:
            if websocket in connected_clients:
                connected_clients.remove(websocket)
        print(f"[WebSocket] HUD client disconnected (Remaining: {len(connected_clients)})")


# ── Background Telemetry Broadcast Loop ───────────────────────────────
async def telemetry_broadcast_worker():
    """Periodically broadcasts SYSTEM_TELEMETRY and AUDIO_STATE every 2 seconds."""
    while True:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            batt = psutil.sensors_battery()
            battery_pct = int(batt.percent) if batt else 100
            charging = batt.power_plugged if batt else True
            online = is_internet_connected()

            broadcast_ws_sync("SYSTEM_TELEMETRY", {
                "cpu": cpu,
                "ram": ram,
                "battery": battery_pct,
                "charging": charging,
                "online": online,
            })

            broadcast_ws_sync("AUDIO_STATE", {
                "mic_active": engine.get_mic_active(),
                "tts_active": engine.get_tts_active(),
                "status": "thinking" if getattr(engine, "is_thinking", False) else ("speaking" if engine.tts.is_speaking() else ("listening" if engine.get_mic_active() else "idle")),
                "meeting_auto_muted": getattr(engine.listener, "meeting_auto_muted", False),
            })

            bot = getattr(engine, "meeting_handler", None) and engine.meeting_handler.bot
            broadcast_ws_sync("MEETING_STATE", {
                "current_meeting": bot.current_meeting if bot else None,
                "captions": bot.get_live_captions() if bot else [],
            })
        except Exception:
            pass

        await asyncio.sleep(2.0)


@app.on_event("startup")
async def startup_event():
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()
    asyncio.create_task(telemetry_broadcast_worker())


# ── Pydantic Request Models ───────────────────────────────────────────
class CommandRequest(BaseModel):
    query: str
    source: str = "text"

class AudioToggleRequest(BaseModel):
    target: str  # "mic" or "tts"
    enabled: bool

class KeyRequest(BaseModel):
    provider: str
    key: Optional[str] = ""
    key_index: Optional[int] = None
    action: str = "add"  # "add" or "remove"

class JoinMeetingRequest(BaseModel):
    url: str
    title: Optional[str] = "Online Meeting"

class TeachStartRequest(BaseModel):
    name: str
    trigger_phrases: List[str] = []

class TeachStopRequest(BaseModel):
    save: bool = True

class CustomEndpointRequest(BaseModel):
    action: str = "add"  # "add" or "delete"
    endpoint: Optional[Dict[str, Any]] = None
    endpoint_id: Optional[str] = None

class FetchModelsRequest(BaseModel):
    base_url: str
    api_key: Optional[str] = ""

class TestConnectionRequest(BaseModel):
    provider: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None

class RolesRequest(BaseModel):
    roles: Optional[Dict[str, Any]] = None
    autonomous_trust_mode: Optional[bool] = None
    workspace_path: Optional[str] = None

class ApprovalRequest(BaseModel):
    approved: bool

class SystemControlRequest(BaseModel):
    action: str  # "volume", "brightness", "app", "workspace_path"
    value: Any


# ── REST API Endpoints ────────────────────────────────────────────────
@app.post("/api/command")
def api_command(req: CommandRequest):
    res = engine.process_command(req.query, source=req.source)
    return res

@app.post("/api/audio/toggle")
def api_audio_toggle(req: AudioToggleRequest):
    if req.target == "mic":
        engine.set_mic_active(req.enabled)
        state = engine.get_mic_active()
    elif req.target == "tts":
        engine.set_tts_active(req.enabled)
        state = engine.get_tts_active()
    else:
        raise HTTPException(status_code=400, detail="Invalid audio target")
    return {"target": req.target, "enabled": state}

@app.get("/api/vault")
def api_get_vault(reveal: bool = False):
    if reveal:
        return load_vault()
    return get_masked_vault()

@app.post("/api/vault/key")
def api_vault_key(req: KeyRequest):
    if req.action == "add":
        success = add_provider_key(req.provider, req.key or "")
    elif req.action == "remove":
        success = remove_provider_key(req.provider, key_or_index=req.key, key_index=req.key_index)
    else:
        raise HTTPException(status_code=400, detail="Action must be 'add' or 'remove'")
    return {"ok": success, "vault": get_masked_vault()}

@app.post("/api/vault/custom-endpoint")
def api_vault_custom_endpoint(req: CustomEndpointRequest):
    vault = load_vault()
    eps = vault.setdefault("providers", {}).setdefault("custom_endpoints", [])
    if req.action == "add" and req.endpoint:
        existing = next((i for i, ep in enumerate(eps) if ep.get("id") == req.endpoint.get("id")), None)
        if existing is not None:
            eps[existing] = req.endpoint
        else:
            eps.append(req.endpoint)
        save_vault(vault)
        return {"ok": True, "vault": get_masked_vault()}
    elif req.action == "delete" and req.endpoint_id:
        vault["providers"]["custom_endpoints"] = [ep for ep in eps if ep.get("id") != req.endpoint_id]
        save_vault(vault)
        return {"ok": True, "vault": get_masked_vault()}
    raise HTTPException(status_code=400, detail="Invalid custom-endpoint request")

@app.post("/api/vault/fetch-models")
def api_fetch_models(req: FetchModelsRequest):
    models = fetch_models(req.base_url, req.api_key or "")
    return {"ok": True, "models": models}

@app.post("/api/vault/test")
def api_test_connection(req: TestConnectionRequest):
    if req.provider == "openweathermap":
        import time
        t0 = time.time()
        old_key = getattr(engine.weather_handler, "_custom_api_key", None)
        if req.api_key:
            engine.weather_handler._custom_api_key = req.api_key
        try:
            ok = engine.weather_handler.test_api_key()
            lat = int((time.time() - t0) * 1000)
            return {"ok": bool(ok), "latency_ms": lat, "error": None if ok else "OpenWeatherMap API key invalid or unreachable"}
        finally:
            engine.weather_handler._custom_api_key = old_key

    adapter = router.get_adapter_for_provider(
        provider=req.provider,
        model=req.model or "",
        api_key=req.api_key,
    )
    if req.base_url and hasattr(adapter, "base_url"):
        adapter.base_url = req.base_url.rstrip("/")
    res = adapter.test_connection()
    return res

@app.post("/api/vault/roles")
def api_update_roles(req: RolesRequest):
    vault = load_vault()
    if req.roles is not None:
        vault["roles"] = req.roles
    if req.autonomous_trust_mode is not None:
        vault["autonomous_trust_mode"] = req.autonomous_trust_mode
    if req.workspace_path is not None:
        vault["workspace_path"] = req.workspace_path
    save_vault(vault)
    return {"ok": True, "vault": get_masked_vault()}

@app.get("/api/meetings")
def api_get_meetings():
    scheduler = getattr(engine, "meeting_handler", None) and engine.meeting_handler.scheduler
    bot = getattr(engine, "meeting_handler", None) and engine.meeting_handler.bot
    meetings_data = scheduler.get_all() if scheduler else []
    summaries = bot.get_summaries() if bot else []
    live_caps = bot.get_live_captions() if bot else []
    curr_mtg = bot.current_meeting if bot else None
    return {
        "meetings": meetings_data,
        "summaries": summaries,
        "live_captions": live_caps,
        "current_meeting": curr_mtg,
    }

@app.post("/api/meetings")
def api_add_meeting(meeting: Dict[str, Any]):
    scheduler = getattr(engine, "meeting_handler", None) and engine.meeting_handler.scheduler
    if not scheduler:
        raise HTTPException(status_code=500, detail="Meeting scheduler not available")
    st = meeting.get("start_time")
    if isinstance(st, str):
        try:
            st_dt = datetime.fromisoformat(st.replace("Z", "+00:00"))
        except Exception:
            st_dt = datetime.now()
    elif isinstance(st, datetime):
        st_dt = st
    else:
        st_dt = datetime.now()

    # FIX 2: Convert timezone-aware datetimes to local naive time
    if st_dt.tzinfo is not None:
        st_dt = st_dt.astimezone().replace(tzinfo=None)

    et = meeting.get("end_time")
    et_dt = None
    if isinstance(et, str):
        try:
            et_dt = datetime.fromisoformat(et.replace("Z", "+00:00"))
        except Exception:
            et_dt = None

    if et_dt is not None and et_dt.tzinfo is not None:
        et_dt = et_dt.astimezone().replace(tzinfo=None)

    new_m = scheduler.add_meeting(
        title=meeting.get("title", "Meeting"),
        meeting_url=meeting.get("meeting_url", ""),
        start_time=st_dt,
        end_time=et_dt,
        auto_leave=meeting.get("auto_leave", True),
    )
    return {"ok": True, "meeting": new_m}

@app.delete("/api/meetings/{meeting_id}")
def api_delete_meeting(meeting_id: str):
    scheduler = getattr(engine, "meeting_handler", None) and engine.meeting_handler.scheduler
    if scheduler:
        scheduler.cancel_meeting(meeting_id)
        with scheduler._lock:
            scheduler._meetings = [m for m in scheduler._meetings if m.get("id") != meeting_id]
            scheduler._save()
        return {"ok": True}
    return {"ok": False}

@app.post("/api/meetings/join-url")
def api_join_meeting_url(req: JoinMeetingRequest):
    bot = getattr(engine, "meeting_handler", None) and engine.meeting_handler.bot
    if bot:
        threading.Thread(target=bot.join_meeting, kwargs={"url": req.url, "title": req.title or "Online Meeting"}, daemon=True).start()
    else:
        import webbrowser
        webbrowser.open(req.url)
    return {"ok": True}

@app.post("/api/meetings/leave")
def api_leave_meeting():
    bot = getattr(engine, "meeting_handler", None) and engine.meeting_handler.bot
    if bot:
        bot.leave_meeting()
    return {"ok": True}

@app.get("/api/alarms")
def api_get_alarms():
    if ALARMS_FILE.exists():
        try:
            return json.loads(ALARMS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"alarms": [], "timers": []}

@app.post("/api/alarms")
def api_add_alarm(payload: Dict[str, Any]):
    data = api_get_alarms()
    target_list = data.setdefault("alarms" if payload.get("type") != "timer" else "timers", [])
    payload["id"] = f"alr-{int(time.time())}"
    target_list.append(payload)
    ALARMS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True, "data": data}

@app.delete("/api/alarms/{alarm_id}")
def api_delete_alarm(alarm_id: str):
    data = api_get_alarms()
    data["alarms"] = [a for a in data.get("alarms", []) if a.get("id") != alarm_id]
    data["timers"] = [t for t in data.get("timers", []) if t.get("id") != alarm_id]
    ALARMS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True}

@app.get("/api/skills")
def api_get_skills():
    return skill_store.get_skills()

@app.post("/api/skills")
def api_add_skill(skill: Dict[str, Any]):
    success = skill_store.add_skill(skill)
    return {"ok": success, "skills": skill_store.get_skills()}

@app.get("/api/skills/teach/status")
def api_teach_status():
    return {"is_teaching": skill_store.is_teaching()}

@app.post("/api/skills/teach/start")
def api_teach_start(req: TeachStartRequest):
    rec = skill_store.start_teach_mode(name=req.name, trigger_phrases=req.trigger_phrases)
    return {"ok": True, "recording": rec}

@app.post("/api/skills/teach/stop")
def api_teach_stop(req: TeachStopRequest):
    saved = skill_store.stop_teach_mode(save=req.save)
    return {"ok": True, "saved": saved, "skills": skill_store.get_skills()}

@app.post("/api/skills/{skill_id}/run")
def api_run_skill(skill_id: str):
    res = skill_store.run_skill(skill_id, engine)
    return res

@app.delete("/api/skills/{skill_id}")
def api_delete_skill(skill_id: str):
    success = skill_store.delete_skill(skill_id)
    return {"ok": success, "skills": skill_store.get_skills()}

@app.get("/api/mcp")
def api_get_mcp():
    return {"servers": mcp_client.get_servers(), "tools": mcp_client.list_tools()}

@app.post("/api/mcp")
def api_add_mcp(payload: Dict[str, Any]):
    name = payload.get("name", "")
    config = payload.get("config", {})
    if not name or not config:
        raise HTTPException(status_code=400, detail="Server name and config required")
    success = mcp_client.add_server(name, config)
    return {"ok": success, "servers": mcp_client.get_servers()}

@app.delete("/api/mcp/{name}")
def api_delete_mcp(name: str):
    success = mcp_client.remove_server(name)
    return {"ok": success, "servers": mcp_client.get_servers()}

@app.post("/api/agent/abort")
def api_agent_abort():
    os_actuator.abort()
    return {"ok": True, "aborted": True}

@app.post("/api/approval/{request_id}")
def api_approval(request_id: str, req: ApprovalRequest):
    if req.approved:
        success = safety_interceptor.approve(request_id)
    else:
        success = safety_interceptor.deny(request_id)
    return {"ok": success, "request_id": request_id, "approved": req.approved}

@app.post("/api/system/control")
def api_system_control(req: SystemControlRequest):
    if req.action == "volume":
        engine.system_controls.set_volume(str(req.value))
    elif req.action == "brightness":
        engine.system_controls.set_brightness(str(req.value))
    elif req.action == "app":
        engine.app_handler.open_application(f"open {req.value}")
    elif req.action == "workspace_path":
        workspace_rag.set_workspace_path(str(req.value))
    return {"ok": True, "action": req.action, "value": req.value}


# ── Mount Frontend Static Bundle ──────────────────────────────────────
if UI_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(UI_DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = UI_DIST_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(UI_DIST_DIR / "index.html")
else:
    @app.get("/")
    def serve_fallback_placeholder():
        return HTMLResponse("<h1>JARVIS 2.0 Backend Online. Building HUD Frontend...</h1>")


if __name__ == "__main__":
    import uvicorn
    print("[JARVIS 2.0] Starting backend on http://127.0.0.1:5050 ...")
    uvicorn.run("automation.server:app", host="127.0.0.1", port=5050, reload=False)

