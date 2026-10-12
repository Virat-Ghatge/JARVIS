#!/usr/bin/env python3
"""
Schedule Interface Module
Local web dashboard (FastAPI + single-page HTML) at http://localhost:5050

Features:
  - Quick-Add Form: name, URL, start time, duration
  - Today's Timeline: pending/active/completed meetings with Cancel / Join Now buttons
  - Bulk Importer: paste JSON array or text timetable
  - Real-time API for the JARVIS voice layer to query/manage schedules
"""

import os
import threading
import json
from datetime import datetime, timedelta

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("[!] FastAPI/uvicorn not installed. Web dashboard disabled.")

# ─── Configuration ────────────────────────────────────────────────
DASHBOARD_PORT = int(os.getenv("MEETING_DASHBOARD_PORT", "5050"))
DASHBOARD_HOST = os.getenv("MEETING_DASHBOARD_HOST", "127.0.0.1")


# ─── Dashboard HTML (self-contained SPA) ──────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JARVIS — Meeting Schedule</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    :root{
      --bg:#0a0e17;--surface:#111827;--surface2:#1e293b;
      --accent:#6366f1;--accent-glow:rgba(99,102,241,.25);
      --text:#e2e8f0;--text-muted:#94a3b8;--text-dim:#64748b;
      --danger:#ef4444;--success:#22c55e;--warn:#f59e0b;
      --radius:12px;--glass:rgba(255,255,255,.04);
    }
    body{
      font-family:'Inter',system-ui,sans-serif;
      background:var(--bg);color:var(--text);
      min-height:100vh;overflow-x:hidden;
    }

    /* ── Header ─────────────────────────────────── */
    .header{
      position:sticky;top:0;z-index:50;
      background:linear-gradient(180deg,rgba(10,14,23,.98) 60%,rgba(10,14,23,.0));
      backdrop-filter:blur(20px);
      padding:1.5rem 2rem;display:flex;align-items:center;gap:1rem;
    }
    .logo{
      font-size:1.5rem;font-weight:700;
      background:linear-gradient(135deg,#6366f1,#a78bfa);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;
    }
    .logo span{font-weight:300;opacity:.7}
    .header-badge{
      margin-left:auto;font-size:.75rem;padding:.25rem .75rem;
      border-radius:99px;background:var(--accent-glow);color:var(--accent);
      border:1px solid rgba(99,102,241,.3);
    }

    /* ── Container ──────────────────────────────── */
    .container{max-width:960px;margin:0 auto;padding:0 2rem 4rem}

    /* ── Cards ──────────────────────────────────── */
    .card{
      background:var(--surface);border:1px solid rgba(255,255,255,.06);
      border-radius:var(--radius);padding:1.5rem;margin-bottom:1.5rem;
      transition:border-color .2s;
    }
    .card:hover{border-color:rgba(99,102,241,.2)}
    .card-title{font-size:1rem;font-weight:600;margin-bottom:1rem;display:flex;align-items:center;gap:.5rem}
    .card-title .icon{font-size:1.1rem}

    /* ── Form ───────────────────────────────────── */
    .form-grid{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}
    .form-grid .full{grid-column:1/-1}
    label{font-size:.75rem;font-weight:500;color:var(--text-muted);display:block;margin-bottom:.25rem}
    input,select,textarea{
      width:100%;padding:.6rem .85rem;border-radius:8px;
      border:1px solid rgba(255,255,255,.1);background:var(--surface2);
      color:var(--text);font-size:.875rem;font-family:inherit;
      transition:border-color .15s,box-shadow .15s;outline:none;
    }
    input:focus,textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
    textarea{resize:vertical;min-height:80px}

    .btn{
      display:inline-flex;align-items:center;gap:.4rem;
      padding:.6rem 1.25rem;border-radius:8px;border:none;
      font-size:.8rem;font-weight:600;font-family:inherit;cursor:pointer;
      transition:transform .1s,box-shadow .15s;
    }
    .btn:active{transform:scale(.97)}
    .btn-primary{
      background:linear-gradient(135deg,#6366f1,#818cf8);color:#fff;
      box-shadow:0 2px 12px var(--accent-glow);
    }
    .btn-primary:hover{box-shadow:0 4px 20px var(--accent-glow)}
    .btn-danger{background:rgba(239,68,68,.15);color:var(--danger);border:1px solid rgba(239,68,68,.25)}
    .btn-danger:hover{background:rgba(239,68,68,.25)}
    .btn-success{background:rgba(34,197,94,.15);color:var(--success);border:1px solid rgba(34,197,94,.25)}
    .btn-success:hover{background:rgba(34,197,94,.25)}
    .btn-ghost{background:transparent;color:var(--text-muted);border:1px solid rgba(255,255,255,.1)}
    .btn-ghost:hover{background:var(--glass);color:var(--text)}
    .btn-sm{padding:.35rem .7rem;font-size:.72rem}

    /* ── Timeline Table ─────────────────────────── */
    .timeline-empty{text-align:center;padding:2rem;color:var(--text-dim);font-size:.9rem}
    .meeting-row{
      display:grid;grid-template-columns:80px 1fr auto;gap:1rem;
      align-items:center;padding:.85rem 1rem;
      border-radius:8px;margin-bottom:.5rem;
      background:var(--glass);border:1px solid rgba(255,255,255,.04);
      transition:background .15s;
    }
    .meeting-row:hover{background:rgba(255,255,255,.06)}
    .meeting-time{font-size:.8rem;font-weight:600;color:var(--accent);font-variant-numeric:tabular-nums}
    .meeting-info h4{font-size:.875rem;font-weight:500}
    .meeting-info .meta{font-size:.72rem;color:var(--text-dim);margin-top:.15rem}
    .badge{
      display:inline-block;padding:.15rem .5rem;border-radius:99px;
      font-size:.65rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em;
    }
    .badge-pending{background:rgba(245,158,11,.15);color:var(--warn)}
    .badge-active{background:rgba(34,197,94,.15);color:var(--success);animation:pulse-glow 2s infinite}
    .badge-completed{background:rgba(100,116,139,.15);color:var(--text-dim)}
    .badge-cancelled{background:rgba(239,68,68,.1);color:var(--danger)}
    .meeting-actions{display:flex;gap:.4rem;flex-wrap:wrap}

    @keyframes pulse-glow{
      0%,100%{box-shadow:0 0 0 0 rgba(34,197,94,.3)}
      50%{box-shadow:0 0 0 6px rgba(34,197,94,0)}
    }

    /* ── Toast ──────────────────────────────────── */
    .toast{
      position:fixed;bottom:2rem;right:2rem;
      padding:.75rem 1.25rem;border-radius:10px;
      background:var(--surface);border:1px solid rgba(99,102,241,.3);
      color:var(--text);font-size:.85rem;
      box-shadow:0 8px 32px rgba(0,0,0,.4);
      transform:translateY(120%);opacity:0;transition:all .3s ease;
      z-index:999;
    }
    .toast.show{transform:translateY(0);opacity:1}

    /* ── Responsive ─────────────────────────────── */
    @media(max-width:640px){
      .form-grid{grid-template-columns:1fr}
      .meeting-row{grid-template-columns:1fr;gap:.5rem}
      .container{padding:0 1rem 3rem}
    }
  </style>
</head>
<body>

  <!-- Header -->
  <header class="header">
    <div class="logo">JARVIS <span>/ Meetings</span></div>
    <div class="header-badge" id="clock"></div>
  </header>

  <div class="container">

    <!-- Quick-Add Form -->
    <section class="card" id="add-section">
      <div class="card-title"><span class="icon">➕</span> Quick-Add Meeting</div>
      <form id="add-form" class="form-grid" onsubmit="return addMeeting(event)">
        <div>
          <label for="title">Meeting Name</label>
          <input id="title" name="title" placeholder="e.g. Team Standup" required>
        </div>
        <div>
          <label for="url">Meeting URL</label>
          <input id="url" name="meeting_url" placeholder="https://meet.google.com/..." required>
        </div>
        <div>
          <label for="start">Start Time</label>
          <input id="start" name="start_time" type="datetime-local" required>
        </div>
        <div>
          <label for="duration">Duration (minutes)</label>
          <input id="duration" name="duration" type="number" value="60" min="5" max="480">
        </div>
        <div class="full" style="display:flex;gap:.5rem;justify-content:flex-end">
          <button type="submit" class="btn btn-primary">＋ Add Meeting</button>
        </div>
      </form>
    </section>

    <!-- Today's Timeline -->
    <section class="card">
      <div class="card-title"><span class="icon">📅</span> Today's Schedule</div>
      <div id="timeline">
        <div class="timeline-empty">Loading…</div>
      </div>
    </section>

    <!-- Bulk Importer -->
    <section class="card">
      <div class="card-title"><span class="icon">📋</span> Bulk Import</div>
      <p style="font-size:.78rem;color:var(--text-dim);margin-bottom:.75rem">
        Paste a JSON array of meetings. Each object needs <code>title</code>, <code>meeting_url</code>,
        <code>start_time</code> (ISO), and optionally <code>end_time</code>.
      </p>
      <textarea id="bulk-input" placeholder='[{"title":"Standup","meeting_url":"https://meet.google.com/abc","start_time":"2026-10-12T09:00:00"}]'></textarea>
      <div style="margin-top:.5rem;display:flex;gap:.5rem;justify-content:flex-end">
        <button class="btn btn-ghost" onclick="document.getElementById('bulk-input').value=''">Clear</button>
        <button class="btn btn-primary" onclick="bulkImport()">Import</button>
      </div>
    </section>

  </div>

  <!-- Toast -->
  <div class="toast" id="toast"></div>

  <script>
    // ── Clock ────────────────────────────────
    function updateClock(){
      const now=new Date();
      document.getElementById('clock').textContent=now.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
    }
    setInterval(updateClock,1000);updateClock();

    // ── Set default start time to now + 5 min ─
    (function(){
      const d=new Date(Date.now()+5*60000);
      const pad=n=>(''+n).padStart(2,'0');
      document.getElementById('start').value=
        `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    })();

    // ── Toast ────────────────────────────────
    function toast(msg,ms=3000){
      const el=document.getElementById('toast');
      el.textContent=msg;el.classList.add('show');
      setTimeout(()=>el.classList.remove('show'),ms);
    }

    // ── Add Meeting ──────────────────────────
    async function addMeeting(e){
      e.preventDefault();
      const f=new FormData(e.target);
      const start=f.get('start_time');
      const dur=parseInt(f.get('duration'))||60;
      const endDt=new Date(new Date(start).getTime()+dur*60000);
      const body={
        title:f.get('title'),
        meeting_url:f.get('meeting_url'),
        start_time:start+':00',
        end_time:endDt.toISOString().slice(0,19),
      };
      const res=await fetch('/api/meetings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(res.ok){toast('Meeting added!');e.target.reset();loadTimeline();}
      else{const d=await res.json();toast('Error: '+(d.detail||'unknown'));}
      return false;
    }

    // ── Load Timeline ────────────────────────
    async function loadTimeline(){
      const res=await fetch('/api/meetings/today');
      const data=await res.json();
      const el=document.getElementById('timeline');
      if(!data.length){el.innerHTML='<div class="timeline-empty">No meetings today. Add one above!</div>';return;}

      el.innerHTML=data.map(m=>{
        const t=new Date(m.start_time);
        const time=t.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
        const badgeClass={'pending':'badge-pending','active':'badge-active','completed':'badge-completed','cancelled':'badge-cancelled'}[m.status]||'badge-pending';
        const platform=m.platform==='google_meet'?'Google Meet':m.platform==='teams'?'MS Teams':'Unknown';
        let actions='';
        if(m.status==='pending'){
          actions=`<button class="btn btn-success btn-sm" onclick="joinNow('${m.id}')">▶ Join Now</button>
                   <button class="btn btn-danger btn-sm" onclick="cancelMeeting('${m.id}')">✕ Cancel</button>`;
        }else if(m.status==='active'){
          actions=`<button class="btn btn-danger btn-sm" onclick="leaveMeeting()">⏹ Leave</button>`;
        }
        return `<div class="meeting-row">
          <div class="meeting-time">${time}</div>
          <div class="meeting-info">
            <h4>${m.title} <span class="badge ${badgeClass}">${m.status}</span></h4>
            <div class="meta">${platform} · ${m.meeting_url.slice(0,50)}…</div>
          </div>
          <div class="meeting-actions">${actions}</div>
        </div>`;
      }).join('');
    }
    setInterval(loadTimeline,15000);loadTimeline();

    // ── Actions ──────────────────────────────
    async function cancelMeeting(id){
      await fetch(`/api/meetings/${id}`,{method:'DELETE'});
      toast('Meeting cancelled');loadTimeline();
    }
    async function joinNow(id){
      const res=await fetch(`/api/meetings/${id}/join`,{method:'POST'});
      if(res.ok) toast('Joining meeting...');
      else toast('Join failed');
      loadTimeline();
    }
    async function leaveMeeting(){
      await fetch('/api/meetings/leave',{method:'POST'});
      toast('Leaving meeting...');loadTimeline();
    }

    // ── Bulk Import ──────────────────────────
    async function bulkImport(){
      const raw=document.getElementById('bulk-input').value.trim();
      if(!raw){toast('Paste some JSON first');return;}
      try{
        const arr=JSON.parse(raw);
        const res=await fetch('/api/meetings/bulk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(arr)});
        const d=await res.json();
        toast(`Imported ${d.count} meetings`);loadTimeline();
      }catch(e){toast('Invalid JSON: '+e.message);}
    }
  </script>
</body>
</html>"""


class ScheduleInterface:
    """
    Local web dashboard and REST API for managing meeting schedules.
    Runs in a daemon thread so it never blocks the JARVIS main loop.
    """

    def __init__(self, scheduler, meeting_bot=None):
        """
        Args:
            scheduler: MeetingScheduler instance
            meeting_bot: Optional MeetingBot instance (for Join Now / Leave)
        """
        self.scheduler = scheduler
        self.meeting_bot = meeting_bot
        self.app = None
        self._thread = None

        if FASTAPI_AVAILABLE:
            self._build_app()

    def _build_app(self):
        """Create the FastAPI application with all routes."""
        self.app = FastAPI(title="JARVIS Meeting Dashboard")

        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard():
            return DASHBOARD_HTML

        @self.app.get("/api/meetings")
        async def list_meetings():
            return JSONResponse(self.scheduler.get_all())

        @self.app.get("/api/meetings/today")
        async def today_meetings():
            return JSONResponse(self.scheduler.get_today())

        @self.app.get("/api/meetings/pending")
        async def pending_meetings():
            return JSONResponse(self.scheduler.get_pending())

        @self.app.post("/api/meetings")
        async def add_meeting(request: Request):
            data = await request.json()
            try:
                start = datetime.fromisoformat(data["start_time"])
                end = datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None
                meeting = self.scheduler.add_meeting(
                    title=data.get("title", "Untitled Meeting"),
                    meeting_url=data["meeting_url"],
                    start_time=start,
                    end_time=end,
                    auto_leave=data.get("auto_leave", True),
                )
                return JSONResponse(meeting, status_code=201)
            except Exception as e:
                return JSONResponse({"detail": str(e)}, status_code=400)

        @self.app.delete("/api/meetings/{meeting_id}")
        async def cancel_meeting(meeting_id: str):
            ok = self.scheduler.cancel_meeting(meeting_id)
            if ok:
                return JSONResponse({"status": "cancelled"})
            return JSONResponse({"detail": "Meeting not found"}, status_code=404)

        @self.app.post("/api/meetings/{meeting_id}/join")
        async def join_now(meeting_id: str):
            meeting = self.scheduler.get_by_id(meeting_id)
            if not meeting:
                return JSONResponse({"detail": "Not found"}, status_code=404)
            if self.meeting_bot:
                self.scheduler.mark_active(meeting_id)
                end_time = datetime.fromisoformat(meeting["end_time"])
                threading.Thread(
                    target=self.meeting_bot.join_meeting,
                    args=(meeting["meeting_url"],),
                    kwargs={"end_time": end_time, "auto_leave": meeting.get("auto_leave", True)},
                    daemon=True,
                ).start()
                return JSONResponse({"status": "joining"})
            return JSONResponse({"detail": "Meeting bot not available"}, status_code=503)

        @self.app.post("/api/meetings/leave")
        async def leave_meeting():
            if self.meeting_bot:
                self.meeting_bot.leave_meeting()
                # Mark any active meetings as completed
                for m in self.scheduler.get_active():
                    self.scheduler.mark_completed(m["id"])
                return JSONResponse({"status": "left"})
            return JSONResponse({"detail": "No active meeting"}, status_code=404)

        @self.app.post("/api/meetings/bulk")
        async def bulk_import(request: Request):
            data = await request.json()
            count = self.scheduler.bulk_import(data)
            return JSONResponse({"count": count})

    def start(self):
        """Launch the dashboard server in a daemon thread."""
        if not FASTAPI_AVAILABLE or not self.app:
            print("[ScheduleInterface] FastAPI not available — dashboard disabled")
            return

        def _run():
            uvicorn.run(
                self.app,
                host=DASHBOARD_HOST,
                port=DASHBOARD_PORT,
                log_level="warning",
            )

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        print(f"[ScheduleInterface] Dashboard running at http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")

    def stop(self):
        """Stop the server (best-effort; uvicorn in a thread is fire-and-forget)."""
        # Daemon thread will die when the main process exits
        pass
