import React, { useState, useEffect, useCallback } from 'react';
import {
  Volume2, Sun, AppWindow, Plus, Trash2, Clock, Bell, FolderSearch,
  Save, Chrome, Code, Music, FileText, Calculator, Terminal, FolderOpen,
  Timer, Clipboard, Loader2,
} from 'lucide-react';

/* ── Types ────────────────────────────────────────────────────────── */
interface AlarmItem {
  id: string;
  label: string;
  time?: string;
  duration_seconds?: number;
  type?: string;
}

interface AlarmsData {
  alarms: AlarmItem[];
  timers: AlarmItem[];
}

interface SystemAndAlarmsProps {
  apiBase: string;
}

/* ── Quick-Launch App Grid ────────────────────────────────────────── */
const QUICK_APPS = [
  { name: 'Chrome', cmd: 'chrome', icon: <Chrome size={20} /> },
  { name: 'VS Code', cmd: 'code', icon: <Code size={20} /> },
  { name: 'Spotify', cmd: 'spotify', icon: <Music size={20} /> },
  { name: 'Notepad', cmd: 'notepad', icon: <FileText size={20} /> },
  { name: 'Calculator', cmd: 'calculator', icon: <Calculator size={20} /> },
  { name: 'Terminal', cmd: 'cmd', icon: <Terminal size={20} /> },
  { name: 'Explorer', cmd: 'explorer', icon: <FolderOpen size={20} /> },
];

/* ── Component ────────────────────────────────────────────────────── */
export const SystemAndAlarms: React.FC<SystemAndAlarmsProps> = ({ apiBase }) => {
  const [volume, setVolume] = useState(50);
  const [brightness, setBrightness] = useState(70);
  const [alarms, setAlarms] = useState<AlarmItem[]>([]);
  const [timers, setTimers] = useState<AlarmItem[]>([]);

  // New alarm form
  const [newAlarmLabel, setNewAlarmLabel] = useState('');
  const [newAlarmTime, setNewAlarmTime] = useState('');

  // New countdown timer form
  const [newTimerLabel, setNewTimerLabel] = useState('');
  const [newTimerMinutes, setNewTimerMinutes] = useState('');

  // Workspace RAG path
  const [workspacePath, setWorkspacePath] = useState('');
  const [pathSaved, setPathSaved] = useState(false);

  // Clipboard Copilot
  const [clipboardResult, setClipboardResult] = useState('');
  const [clipboardLoading, setClipboardLoading] = useState(false);

  const fetchAlarms = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/alarms`);
      const data: AlarmsData = await res.json();
      setAlarms(data.alarms || []);
      setTimers(data.timers || []);
    } catch { /* offline */ }
  }, [apiBase]);

  useEffect(() => { fetchAlarms(); }, [fetchAlarms]);

  // FIX 7: Load saved workspace path from vault on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${apiBase}/api/vault`);
        const data = await res.json();
        if (data.workspace_path) {
          setWorkspacePath(data.workspace_path);
        }
      } catch { /* offline */ }
    })();
  }, [apiBase]);

  /* ── System Controls ────────────────────────────────────────────── */
  const setSystemVolume = async (v: number) => {
    setVolume(v);
    await fetch(`${apiBase}/api/system/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'volume', value: v }),
    });
  };

  const setSystemBrightness = async (b: number) => {
    setBrightness(b);
    await fetch(`${apiBase}/api/system/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'brightness', value: b }),
    });
  };

  const launchApp = async (cmd: string) => {
    await fetch(`${apiBase}/api/system/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'app', value: cmd }),
    });
  };

  /* ── Alarms ─────────────────────────────────────────────────────── */
  const addAlarm = async () => {
    if (!newAlarmLabel.trim()) return;
    await fetch(`${apiBase}/api/alarms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        label: newAlarmLabel,
        time: newAlarmTime || undefined,
        type: 'alarm',
      }),
    });
    setNewAlarmLabel(''); setNewAlarmTime('');
    fetchAlarms();
  };

  /* ── Countdown Timer ────────────────────────────────────────────── */
  const addTimer = async () => {
    const mins = parseInt(newTimerMinutes, 10);
    if (!newTimerLabel.trim() || isNaN(mins) || mins <= 0) return;
    await fetch(`${apiBase}/api/alarms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        label: newTimerLabel,
        duration_seconds: mins * 60,
        type: 'timer',
      }),
    });
    // Also fire a voice command so the backend timer worker actually counts down
    await fetch(`${apiBase}/api/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `set timer for ${mins} minutes`, source: 'text' }),
    });
    setNewTimerLabel(''); setNewTimerMinutes('');
    fetchAlarms();
  };

  const deleteAlarm = async (id: string) => {
    await fetch(`${apiBase}/api/alarms/${id}`, { method: 'DELETE' });
    fetchAlarms();
  };

  /* ── Clipboard Copilot ──────────────────────────────────────────── */
  const clipboardAction = async (commandPrefix: string) => {
    setClipboardLoading(true);
    setClipboardResult('');
    try {
      const res = await fetch(`${apiBase}/api/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: commandPrefix, source: 'text' }),
      });
      const data = await res.json();
      setClipboardResult(data.text || data.response || 'Done.');
    } catch {
      setClipboardResult('Failed to reach JARVIS backend.');
    } finally {
      setClipboardLoading(false);
    }
  };

  /* ── Workspace RAG ──────────────────────────────────────────────── */
  const saveWorkspacePath = async () => {
    if (!workspacePath.trim()) return;
    await fetch(`${apiBase}/api/system/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'workspace_path', value: workspacePath }),
    });
    // Also persist in vault
    await fetch(`${apiBase}/api/vault/roles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_path: workspacePath }),
    });
    setPathSaved(true);
    setTimeout(() => setPathSaved(false), 3000);
  };

  const inputClasses = 'bg-void/60 border border-cyber text-ice text-xs px-3 py-2 rounded focus:border-cyan-arc focus:outline-none w-full font-mono';

  return (
    <div className="flex-1 flex flex-col h-full bg-void/30 p-4 space-y-4 overflow-y-auto">
      {/* ── Volume & Brightness ───────────────────────────────────── */}
      <div className="hud-panel hud-chamfer-sm p-3 space-y-3">
        <div className="flex items-center space-x-2 mb-1">
          <Volume2 size={16} className="text-cyan-arc" />
          <span className="font-hud text-xs font-bold tracking-wider text-ice">SYSTEM CONTROLS</span>
        </div>

        {/* Volume */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-steel flex items-center space-x-1"><Volume2 size={12} /> <span>Volume</span></span>
            <span className="text-[11px] text-cyan-arc font-mono">{volume}%</span>
          </div>
          <input
            type="range" min="0" max="100" value={volume}
            onChange={(e) => setSystemVolume(Number(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
            style={{
              background: `linear-gradient(to right, #00E5FF ${volume}%, #16324A ${volume}%)`,
            }}
          />
        </div>

        {/* Brightness */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-steel flex items-center space-x-1"><Sun size={12} /> <span>Brightness</span></span>
            <span className="text-[11px] text-gold-reactor font-mono">{brightness}%</span>
          </div>
          <input
            type="range" min="0" max="100" value={brightness}
            onChange={(e) => setSystemBrightness(Number(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
            style={{
              background: `linear-gradient(to right, #FFB300 ${brightness}%, #16324A ${brightness}%)`,
            }}
          />
        </div>
      </div>

      {/* ── App Launcher Grid ─────────────────────────────────────── */}
      <div className="hud-panel hud-chamfer-sm p-3 space-y-2">
        <div className="flex items-center space-x-2 mb-1">
          <AppWindow size={16} className="text-gold-reactor" />
          <span className="font-hud text-xs font-bold tracking-wider text-ice">QUICK LAUNCH</span>
        </div>
        <div className="grid grid-cols-4 gap-2">
          {QUICK_APPS.map(({ name, cmd, icon }) => (
            <button
              key={cmd}
              onClick={() => launchApp(cmd)}
              className="flex flex-col items-center space-y-1 p-2.5 rounded border border-cyber/50 bg-void/40 hover:border-cyan-arc hover:bg-cyan-arc/5 transition-all group"
            >
              <span className="text-steel group-hover:text-cyan-arc transition-colors">{icon}</span>
              <span className="text-[10px] text-steel group-hover:text-ice transition-colors">{name}</span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Alarms & Timers ───────────────────────────────────────── */}
      <div className="hud-panel hud-chamfer-sm p-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Bell size={16} className="text-gold-reactor" />
            <span className="font-hud text-xs font-bold tracking-wider text-ice">ALARMS & TIMERS</span>
            <span className="text-[10px] text-steel">({alarms.length + timers.length})</span>
          </div>
        </div>

        {/* Add alarm */}
        <div className="flex items-center space-x-2">
          <input className={inputClasses} placeholder="Alarm label" value={newAlarmLabel} onChange={(e) => setNewAlarmLabel(e.target.value)} />
          <input
            type="time"
            className={`${inputClasses} w-32`}
            value={newAlarmTime}
            onChange={(e) => setNewAlarmTime(e.target.value)}
          />
          <button onClick={addAlarm} className="p-2 rounded bg-cyan-arc/10 border border-cyan-arc/30 text-cyan-arc hover:bg-cyan-arc/20 transition-colors">
            <Plus size={14} />
          </button>
        </div>

        {/* Add countdown timer */}
        <div className="flex items-center space-x-2">
          <input className={inputClasses} placeholder="Timer label" value={newTimerLabel} onChange={(e) => setNewTimerLabel(e.target.value)} />
          <input
            type="number"
            min="1"
            placeholder="Min"
            className={`${inputClasses} w-20`}
            value={newTimerMinutes}
            onChange={(e) => setNewTimerMinutes(e.target.value)}
          />
          <button onClick={addTimer} className="flex items-center space-x-1 whitespace-nowrap px-2.5 py-2 rounded bg-gold-reactor/10 border border-gold-reactor/30 text-gold-reactor text-[11px] hover:bg-gold-reactor/20 transition-colors">
            <Timer size={12} />
            <span>Timer</span>
          </button>
        </div>

        {/* Alarm + timer list */}
        <div className="space-y-1">
          {[...alarms, ...timers].map((item) => (
            <div key={item.id} className="flex items-center justify-between bg-void/40 border border-cyber/50 rounded p-2 group">
              <div className="flex items-center space-x-2">
                <Clock size={12} className="text-gold-reactor" />
                <span className="text-xs text-ice">{item.label}</span>
                {item.time && <span className="text-[10px] text-steel font-mono">{item.time}</span>}
                {item.duration_seconds && <span className="text-[10px] text-gold-reactor font-mono">{Math.round(item.duration_seconds / 60)}m</span>}
              </div>
              <button
                onClick={() => deleteAlarm(item.id)}
                className="text-crimson opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
          {alarms.length + timers.length === 0 && (
            <div className="text-[11px] text-steel text-center py-3">No alarms or timers set.</div>
          )}
        </div>
      </div>

      {/* ── Clipboard Copilot Quick-Actions ────────────────────────── */}
      <div className="hud-panel hud-chamfer-sm p-3 space-y-3">
        <div className="flex items-center space-x-2">
          <Clipboard size={16} className="text-cyan-arc" />
          <span className="font-hud text-xs font-bold tracking-wider text-ice">CLIPBOARD COPILOT</span>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => clipboardAction('summarize clipboard')}
            disabled={clipboardLoading}
            className="flex-1 px-3 py-2 rounded border border-cyan-arc/30 bg-cyan-arc/10 text-xs text-cyan-arc hover:bg-cyan-arc/20 transition-colors disabled:opacity-50"
          >
            Summarize Clipboard
          </button>
          <button
            onClick={() => clipboardAction('fix this code')}
            disabled={clipboardLoading}
            className="flex-1 px-3 py-2 rounded border border-gold-reactor/30 bg-gold-reactor/10 text-xs text-gold-reactor hover:bg-gold-reactor/20 transition-colors disabled:opacity-50"
          >
            Fix Code in Clipboard
          </button>
          <button
            onClick={() => clipboardAction('explain this')}
            disabled={clipboardLoading}
            className="flex-1 px-3 py-2 rounded border border-cyber text-xs text-ice hover:bg-void/60 transition-colors disabled:opacity-50"
          >
            Explain Clipboard
          </button>
        </div>
        {clipboardLoading && (
          <div className="flex items-center space-x-2 text-[11px] text-steel">
            <Loader2 size={12} className="animate-spin" />
            <span>Processing clipboard content...</span>
          </div>
        )}
        {clipboardResult && !clipboardLoading && (
          <div className="bg-void/60 border border-cyber/50 rounded p-2.5 text-[11px] text-ice/90 whitespace-pre-wrap leading-relaxed max-h-40 overflow-y-auto">
            {clipboardResult}
          </div>
        )}
      </div>

      {/* ── Workspace RAG Folder Picker ───────────────────────────── */}
      <div className="hud-panel hud-chamfer-sm p-3 space-y-2">
        <div className="flex items-center space-x-2">
          <FolderSearch size={16} className="text-cyan-arc" />
          <span className="font-hud text-xs font-bold tracking-wider text-ice">WORKSPACE RAG</span>
        </div>
        <div className="flex items-center space-x-2">
          <input
            className={inputClasses}
            placeholder="Workspace folder path (e.g. D:\Projects\MyApp)"
            value={workspacePath}
            onChange={(e) => setWorkspacePath(e.target.value)}
          />
          <button
            onClick={saveWorkspacePath}
            className="flex items-center space-x-1 whitespace-nowrap px-3 py-2 rounded bg-cyan-arc/10 border border-cyan-arc/30 text-xs text-cyan-arc hover:bg-cyan-arc/20 transition-colors"
          >
            <Save size={12} />
            <span>{pathSaved ? 'Saved ✓' : 'Save'}</span>
          </button>
        </div>
        <div className="text-[10px] text-steel">
          Set the folder path for workspace document search (RAG). Files will be indexed for grounded Q&A.
        </div>
      </div>
    </div>
  );
};

export default SystemAndAlarms;
