import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  MessageSquare, Layers, Calendar, Key, Zap, Settings,
  Hexagon, ChevronLeft, ChevronRight, Mic, MicOff, Volume2, VolumeX,
} from 'lucide-react';

import { TopTelemetryBar } from './components/TopTelemetryBar';
import { CommandStream, ChatMessageItem } from './components/CommandStream';
import { TaskInspector, AgentStepItem } from './components/TaskInspector';
import { MeetingHub } from './components/MeetingHub';
import { ApiKeyVault } from './components/ApiKeyVault';
import { SkillsAndMcp } from './components/SkillsAndMcp';
import { SystemAndAlarms } from './components/SystemAndAlarms';
import { ApprovalModal, ApprovalRequest } from './components/ApprovalModal';

/* ── Constants ────────────────────────────────────────────────────── */
const API_BASE = window.location.origin;
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;

const TABS = [
  { id: 'command', label: 'COMMAND', icon: <MessageSquare size={18} /> },
  { id: 'agent', label: 'AGENT OS', icon: <Layers size={18} /> },
  { id: 'meetings', label: 'MEETINGS', icon: <Calendar size={18} /> },
  { id: 'vault', label: 'API VAULT', icon: <Key size={18} /> },
  { id: 'skills', label: 'SKILLS', icon: <Zap size={18} /> },
  { id: 'system', label: 'SYSTEM', icon: <Settings size={18} /> },
] as const;

type TabId = typeof TABS[number]['id'];

/* ── WebSocket State Types ────────────────────────────────────────── */
interface TelemetryData {
  cpu: number; ram: number; battery: number; charging: boolean; online: boolean;
}
interface AudioData {
  mic_active: boolean; tts_active: boolean;
  status: 'idle' | 'listening' | 'thinking' | 'speaking';
  meeting_auto_muted: boolean;
}
interface TokenData {
  provider: string; model: string; latency_ms: number;
  prompt_tokens: number; completion_tokens: number; total_session_tokens: number;
}

/* ── App Component ────────────────────────────────────────────────── */
const App: React.FC = () => {
  /* ─ Navigation State ─ */
  const [activeTab, setActiveTab] = useState<TabId>('command');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMiniMode, setIsMiniMode] = useState(false);
  const [miniInput, setMiniInput] = useState('');

  /* ─ WebSocket Data Stores ─ */
  const [telemetry, setTelemetry] = useState<TelemetryData>({ cpu: 0, ram: 0, battery: 100, charging: true, online: true });
  const [audioState, setAudioState] = useState<AudioData>({ mic_active: false, tts_active: true, status: 'idle', meeting_auto_muted: false });
  const [tokenData, setTokenData] = useState<TokenData>({ provider: '-', model: '-', latency_ms: 0, prompt_tokens: 0, completion_tokens: 0, total_session_tokens: 0 });
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [agentSteps, setAgentSteps] = useState<AgentStepItem[]>([]);
  const [approvalRequest, setApprovalRequest] = useState<ApprovalRequest | null>(null);

  /* ─ Meeting data ─ */
  const [meetings, setMeetings] = useState<any[]>([]);
  const [summaries, setSummaries] = useState<any[]>([]);
  const [captions, setCaptions] = useState<any[]>([]);
  const [currentMeeting, setCurrentMeeting] = useState<any>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  /* ─ PyWebView Mini-Mode Bridge ─ */
  const toggleMiniMode = useCallback((enabled: boolean) => {
    setIsMiniMode(enabled);
    try {
      (window as any).pywebview?.api?.set_mini_mode?.(enabled);
    } catch { /* offline / not in pywebview */ }
  }, []);

  /* ─ WebSocket Connection ─ */
  const connectWs = useCallback(() => {
    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[HUD] WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const { type, payload } = JSON.parse(event.data);
          switch (type) {
            case 'SYSTEM_TELEMETRY':
              setTelemetry(payload);
              break;
            case 'AUDIO_STATE':
              setAudioState(payload);
              break;
            case 'TOKEN_TELEMETRY':
              setTokenData((prev) => ({
                ...prev,
                ...payload,
                total_session_tokens: payload.total_session_tokens ?? ((prev.total_session_tokens || 0) + (payload.prompt_tokens || 0) + (payload.completion_tokens || 0)),
              }));
              break;
            case 'CHAT_MESSAGE':
              setMessages((prev) => (prev.some((m) => m.id === payload.id) ? prev : [...prev.slice(-200), payload]));
              break;
            case 'AGENT_STEP':
              setAgentSteps((prev) => [...prev.slice(-50), payload]);
              break;
            case 'APPROVAL_REQUIRED':
              setApprovalRequest(payload);
              break;
            case 'MEETING_STATE':
              if (payload.captions) setCaptions(payload.captions);
              if (payload.current_meeting !== undefined) setCurrentMeeting(payload.current_meeting);
              break;
            default:
              break;
          }
        } catch { /* parse error */ }
      };

      ws.onclose = () => {
        console.log('[HUD] WebSocket disconnected, reconnecting in 3s...');
        reconnectTimer.current = setTimeout(connectWs, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      reconnectTimer.current = setTimeout(connectWs, 3000);
    }
  }, []);

  useEffect(() => {
    connectWs();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connectWs]);

  /* ─ Fetch meetings on tab switch ─ */
  useEffect(() => {
    if (activeTab === 'meetings') {
      fetch(`${API_BASE}/api/meetings`)
        .then((r) => r.json())
        .then((data) => {
          setMeetings(data.meetings || []);
          setSummaries(data.summaries || []);
          if (data.live_captions) setCaptions(data.live_captions);
          if (data.current_meeting) setCurrentMeeting(data.current_meeting);
        })
        .catch(() => {});
    }
  }, [activeTab]);

  /* ─ Command / Audio Handlers ─ */
  const sendCommand = useCallback((query: string) => {
    // Send over WebSocket if connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'USER_COMMAND', payload: { query, source: 'text' } }));
    } else {
      // Fallback to REST and manually append user message only when WS is offline
      const userMsg: ChatMessageItem = {
        id: `user-${Date.now()}`,
        sender: 'user',
        source: 'text',
        text: query,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      fetch(`${API_BASE}/api/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, source: 'text' }),
      })
        .then((r) => r.json())
        .then((data) => {
          setMessages((prev) => [...prev, { ...data, sender: 'jarvis', source: 'text', text: data.text || data.response }]);
        })
        .catch(() => {});
    }
  }, []);

  const toggleMic = useCallback(async () => {
    const next = !audioState.mic_active;
    try {
      await fetch(`${API_BASE}/api/audio/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: 'mic', enabled: next }),
      });
      setAudioState((prev) => ({ ...prev, mic_active: next }));
    } catch { /* offline */ }
  }, [audioState.mic_active]);

  const toggleTts = useCallback(async () => {
    const next = !audioState.tts_active;
    try {
      await fetch(`${API_BASE}/api/audio/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: 'tts', enabled: next }),
      });
      setAudioState((prev) => ({ ...prev, tts_active: next }));
    } catch { /* offline */ }
  }, [audioState.tts_active]);

  const abortAgent = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/agent/abort`, { method: 'POST' });
    } catch { /* offline */ }
  }, []);

  /* ─ Meeting Handlers ─ */
  const addMeeting = useCallback(async (meeting: any) => {
    try {
      await fetch(`${API_BASE}/api/meetings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(meeting),
      });
      const res = await fetch(`${API_BASE}/api/meetings`);
      const data = await res.json();
      setMeetings(data.meetings || []);
    } catch { /* offline */ }
  }, []);

  const deleteMeeting = useCallback(async (id: string) => {
    try {
      await fetch(`${API_BASE}/api/meetings/${id}`, { method: 'DELETE' });
      setMeetings((prev) => prev.filter((m) => m.id !== id));
    } catch { /* offline */ }
  }, []);

  const joinMeeting = useCallback(async (url: string, title?: string) => {
    try {
      await fetch(`${API_BASE}/api/meetings/join-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, title: title || 'Online Meeting' }),
      });
    } catch { /* offline */ }
  }, []);

  const leaveMeeting = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/meetings/leave`, { method: 'POST' });
      setCurrentMeeting(null);
    } catch { /* offline */ }
  }, []);

  /* ── Ghost Mini-HUD Mode ────────────────────────────────────────── */
  if (isMiniMode) {
    const latestJarvisMsg = [...messages].reverse().find((m) => m.sender === 'jarvis');
    return (
      <div className="h-screen w-screen bg-void hud-scanlines flex flex-col justify-between p-2 select-none overflow-hidden">
        <TopTelemetryBar
          telemetry={telemetry}
          audioState={audioState}
          tokenData={tokenData}
          isMiniMode={true}
          onToggleMiniMode={() => toggleMiniMode(false)}
        />
        {latestJarvisMsg && (
          <div className="px-3 py-1 text-[11px] font-mono text-cyan-arc truncate bg-void/60 border border-cyber/40 rounded my-1">
            <span className="text-steel font-bold mr-1">JARVIS:</span>
            {latestJarvisMsg.text}
          </div>
        )}
        <div className="flex items-center space-x-2 pt-1 border-t border-cyber/40">
          <input
            type="text"
            placeholder="Ask JARVIS (Enter to send)..."
            value={miniInput}
            onChange={(e) => setMiniInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && miniInput.trim()) {
                sendCommand(miniInput.trim());
                setMiniInput('');
              }
            }}
            className="flex-1 bg-void/80 border border-cyber text-ice text-xs px-2.5 py-1.5 rounded focus:border-cyan-arc focus:outline-none font-mono"
          />
          <button
            onClick={toggleMic}
            className={`p-1.5 rounded border transition-colors ${
              audioState.mic_active
                ? 'border-cyan-arc bg-cyan-arc/20 text-cyan-arc animate-pulse-glow'
                : 'border-cyber text-steel hover:text-ice'
            }`}
            title="Toggle Mic"
          >
            {audioState.mic_active ? <Mic size={14} /> : <MicOff size={14} />}
          </button>
          <button
            onClick={toggleTts}
            className={`p-1.5 rounded border transition-colors ${
              audioState.tts_active
                ? 'border-cyan-arc bg-cyan-arc/10 text-cyan-arc'
                : 'border-cyber text-steel hover:text-ice'
            }`}
            title="Toggle TTS"
          >
            {audioState.tts_active ? <Volume2 size={14} /> : <VolumeX size={14} />}
          </button>
        </div>
      </div>
    );
  }

  /* ── Full HUD Layout ────────────────────────────────────────────── */
  const renderActivePanel = () => {
    switch (activeTab) {
      case 'command':
        return (
          <CommandStream
            messages={messages}
            micActive={audioState.mic_active}
            ttsActive={audioState.tts_active}
            meetingAutoMuted={audioState.meeting_auto_muted}
            onSendCommand={sendCommand}
            onToggleMic={toggleMic}
            onToggleTts={toggleTts}
          />
        );
      case 'agent':
        return <TaskInspector steps={agentSteps} onAbortAgent={abortAgent} />;
      case 'meetings':
        return (
          <MeetingHub
            meetings={meetings}
            summaries={summaries}
            liveCaptions={captions}
            currentMeeting={currentMeeting}
            onAddMeeting={addMeeting}
            onDeleteMeeting={deleteMeeting}
            onJoinMeeting={joinMeeting}
            onLeaveMeeting={leaveMeeting}
          />
        );
      case 'vault':
        return <ApiKeyVault apiBase={API_BASE} />;
      case 'skills':
        return <SkillsAndMcp apiBase={API_BASE} />;
      case 'system':
        return <SystemAndAlarms apiBase={API_BASE} />;
      default:
        return null;
    }
  };

  return (
    <div className="h-screen w-screen bg-void hud-scanlines flex flex-col overflow-hidden">
      {/* Top Telemetry Bar */}
      <TopTelemetryBar
        telemetry={telemetry}
        audioState={audioState}
        tokenData={tokenData}
        isMiniMode={false}
        onToggleMiniMode={() => toggleMiniMode(true)}
      />

      {/* Main Body: Sidebar + Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Holographic Sidebar ─────────────────────────────────── */}
        <div
          className={`flex flex-col h-full bg-tactical border-r border-cyber transition-all duration-300 ${
            sidebarOpen ? 'w-48' : 'w-12'
          }`}
        >
          {/* Sidebar Toggle */}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="flex items-center justify-center h-8 text-steel hover:text-cyan-arc transition-colors border-b border-cyber/50"
          >
            {sidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
          </button>

          {/* JARVIS Logo */}
          <div className="flex items-center justify-center py-3 border-b border-cyber/30">
            <Hexagon
              size={sidebarOpen ? 28 : 20}
              className="text-cyan-arc animate-pulse-glow"
              strokeWidth={1.5}
            />
            {sidebarOpen && (
              <span className="ml-2 font-hud text-xs font-bold tracking-[0.25em] text-cyan-arc glow-cyan">
                J.A.R.V.I.S.
              </span>
            )}
          </div>

          {/* Navigation Tabs */}
          <nav className="flex-1 flex flex-col py-2 space-y-0.5">
            {TABS.map(({ id, label, icon }) => {
              const isActive = activeTab === id;
              return (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  className={`flex items-center px-3 py-2.5 transition-all ${
                    isActive
                      ? 'bg-cyan-arc/10 border-l-2 border-cyan-arc text-cyan-arc'
                      : 'border-l-2 border-transparent text-steel hover:text-ice hover:bg-void/30'
                  }`}
                >
                  <span className={isActive ? 'text-cyan-arc' : ''}>{icon}</span>
                  {sidebarOpen && (
                    <span className={`ml-3 text-[11px] font-hud tracking-wider ${isActive ? 'font-bold' : ''}`}>
                      {label}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Footer */}
          {sidebarOpen && (
            <div className="px-3 py-2 border-t border-cyber/30">
              <div className="text-[9px] text-steel text-center font-mono">JARVIS 2.0 HUD</div>
              <div className="text-[9px] text-steel/50 text-center font-mono">TACTICAL INTERFACE</div>
            </div>
          )}
        </div>

        {/* ── Main Content Panel ──────────────────────────────────── */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {renderActivePanel()}
        </div>
      </div>

      {/* Approval Modal Overlay */}
      <ApprovalModal
        request={approvalRequest}
        apiBase={API_BASE}
        onDismiss={() => setApprovalRequest(null)}
      />
    </div>
  );
};

export default App;
