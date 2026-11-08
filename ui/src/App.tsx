import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  Bell,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Hexagon,
  KeyRound,
  Layers,
  MessageSquare,
  Settings,
  Zap,
} from 'lucide-react';

import { TopTelemetryBar } from './components/TopTelemetryBar';
import { CommandStream, ChatMessageItem } from './components/CommandStream';
import { TaskInspector, AgentStepItem } from './components/TaskInspector';
import { MeetingHub } from './components/MeetingHub';
import { ApiKeyVault } from './components/ApiKeyVault';
import { SkillsAndMcp } from './components/SkillsAndMcp';
import { SystemAndAlarms } from './components/SystemAndAlarms';
import { ApprovalModal, ApprovalRequest } from './components/ApprovalModal';

const API_BASE = window.location.origin;
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;

const TABS = [
  { id: 'command', label: 'Command', detail: 'Chat & control', icon: <MessageSquare size={17} /> },
  { id: 'agent', label: 'Agent OS', detail: 'Observe / think / act', icon: <Layers size={17} /> },
  { id: 'meetings', label: 'Meetings', detail: 'Schedule & captions', icon: <Calendar size={17} /> },
  { id: 'vault', label: 'Connections', detail: 'Local & cloud routes', icon: <KeyRound size={17} /> },
  { id: 'skills', label: 'Skills', detail: 'Macros & MCP tools', icon: <Zap size={17} /> },
  { id: 'system', label: 'System', detail: 'Controls & alarms', icon: <Settings size={17} /> },
] as const;

type TabId = typeof TABS[number]['id'];

interface TelemetryData {
  cpu: number;
  ram: number;
  memory?: number;
  battery: number;
  charging?: boolean;
  plugged?: boolean;
  online: boolean;
}

interface AudioData {
  mic_active: boolean;
  tts_active: boolean;
  status: 'idle' | 'listening' | 'thinking' | 'speaking';
  meeting_auto_muted: boolean;
}

interface TokenData {
  provider: string;
  model: string;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_session_tokens: number;
}

interface ConnectionData {
  local_first?: boolean;
  local?: {
    available?: boolean;
    downloaded?: boolean;
    ready?: boolean;
    loaded?: boolean;
    model?: string;
  };
  configured_target?: { provider?: string; model?: string };
  fallback_chain?: Array<{ provider?: string; model?: string }>;
}

interface AlarmNotification {
  id?: string;
  label: string;
  time?: string;
}

const DEFAULT_TELEMETRY: TelemetryData = { cpu: 0, ram: 0, battery: 100, charging: true, online: true };
const DEFAULT_AUDIO: AudioData = { mic_active: false, tts_active: true, status: 'idle', meeting_auto_muted: false };
const DEFAULT_TOKENS: TokenData = { provider: 'standby', model: '-', latency_ms: 0, prompt_tokens: 0, completion_tokens: 0, total_session_tokens: 0 };

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('command');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMiniMode, setIsMiniMode] = useState(false);
  const [miniInput, setMiniInput] = useState('');

  const [telemetry, setTelemetry] = useState<TelemetryData>(DEFAULT_TELEMETRY);
  const [audioState, setAudioState] = useState<AudioData>(DEFAULT_AUDIO);
  const [tokenData, setTokenData] = useState<TokenData>(DEFAULT_TOKENS);
  const [connection, setConnection] = useState<ConnectionData>({});
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [agentSteps, setAgentSteps] = useState<AgentStepItem[]>([]);
  const [approvalRequest, setApprovalRequest] = useState<ApprovalRequest | null>(null);

  // Cloud API Off-Switch & Subsystems State
  const [cloudApiEnabled, setCloudApiEnabled] = useState<boolean>(true);
  const [activeAlarmNotification, setActiveAlarmNotification] = useState<AlarmNotification | null>(null);
  const [musicState, setMusicState] = useState<any>(null);

  const [meetings, setMeetings] = useState<any[]>([]);
  const [summaries, setSummaries] = useState<any[]>([]);
  const [captions, setCaptions] = useState<any[]>([]);
  const [currentMeeting, setCurrentMeeting] = useState<any>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttempts = useRef(0);
  const isMountedRef = useRef(true);

  // Dual-tone Web Audio Chime (D5 587.33Hz -> A5 880Hz)
  const playAlarmChime = useCallback((): void => {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      if (ctx.state === 'suspended') {
        ctx.resume();
      }
      const now = ctx.currentTime;

      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(587.33, now);
      gain1.gain.setValueAtTime(0.28, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.35);

      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(880, now + 0.18);
      gain2.gain.setValueAtTime(0.32, now + 0.18);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.65);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.18);
      osc2.stop(now + 0.65);
    } catch (err) {
      console.warn('[JARVIS] Web Audio chime error:', err);
    }
  }, []);

  const refreshCloudApiState = useCallback(async (): Promise<void> => {
    try {
      const res = await fetch(`${API_BASE}/api/cloud-api-toggle`, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        if (typeof data.cloud_api_enabled === 'boolean') {
          setCloudApiEnabled(data.cloud_api_enabled);
        }
      }
    } catch {
      // Retain state during offline periods
    }
  }, []);

  const toggleCloudApi = useCallback(async (): Promise<void> => {
    const target = !cloudApiEnabled;
    setCloudApiEnabled(target);
    try {
      const res = await fetch(`${API_BASE}/api/cloud-api-toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: target, cloud_api_enabled: target }),
      });
      if (res.ok) {
        const data = await res.json();
        if (typeof data.cloud_api_enabled === 'boolean') {
          setCloudApiEnabled(data.cloud_api_enabled);
        }
      }
    } catch (err) {
      console.warn('[JARVIS] Failed to toggle cloud API:', err);
    }
  }, [cloudApiEnabled]);

  const refreshConnection = useCallback(async (): Promise<void> => {
    try {
      const res = await fetch(`${API_BASE}/api/status`, { cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();
      if (data.connection) setConnection(data.connection);
      if (data.telemetry) setTokenData((prev) => ({ ...prev, ...data.telemetry }));
      if (data.audio) setAudioState((prev) => ({ ...prev, ...data.audio }));
    } catch {
      // The WebSocket state remains the source of truth while the server is offline.
    }
  }, []);

  const toggleMiniMode = useCallback((enabled: boolean): void => {
    setIsMiniMode(enabled);
    try {
      (window as any).pywebview?.api?.set_mini_mode?.(enabled);
    } catch {
      // Browser mode has no native bridge.
    }
  }, []);

  const connectWs = useCallback((): void => {
    if (!isMountedRef.current) return;
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = undefined;
    }

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttempts.current = 0;
        setTelemetry((prev) => ({ ...prev, online: true }));
        refreshConnection();
        refreshCloudApiState();
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return;
        try {
          const parsed = JSON.parse(event.data);
          const type = parsed?.type || parsed?.event;
          const payload = parsed?.payload !== undefined ? parsed.payload : parsed?.data;
          if (payload === undefined && type !== 'APPROVAL_REQUIRED') return;

          switch (type) {
            case 'SYSTEM_TELEMETRY':
              if (payload && typeof payload === 'object') {
                setTelemetry((prev) => ({ ...prev, ...payload, online: true, charging: payload.charging ?? payload.plugged ?? prev.charging }));
                if (payload.token_stats && typeof payload.token_stats === 'object') {
                  setTokenData((prev) => ({ ...prev, ...payload.token_stats }));
                }
              }
              break;
            case 'AUDIO_STATE':
              if (payload && typeof payload === 'object') {
                setAudioState((prev) => ({ ...prev, ...payload, meeting_auto_muted: payload.meeting_auto_muted ?? payload.in_meeting_auto_muted ?? prev.meeting_auto_muted }));
              }
              break;
            case 'TOKEN_TELEMETRY':
              if (payload && typeof payload === 'object') setTokenData((prev) => ({ ...prev, ...payload }));
              break;
            case 'CHAT_MESSAGE':
              if (payload) setMessages((prev) => (prev.some((item) => item.id === payload.id) ? prev : [...prev.slice(-200), payload]));
              break;
            case 'AGENT_STEP':
              if (payload) setAgentSteps((prev) => [...prev.slice(-50), payload]);
              break;
            case 'APPROVAL_REQUIRED':
              setApprovalRequest(payload || null);
              break;
            case 'MEETING_STATE':
              if (payload && typeof payload === 'object') {
                if (payload.captions) setCaptions(payload.captions);
                if (payload.current_meeting !== undefined) setCurrentMeeting(payload.current_meeting);
              }
              break;
            case 'ALARM_TRIGGERED':
              playAlarmChime();
              if (payload) {
                setActiveAlarmNotification({
                  id: payload.alarm_id || payload.id,
                  label: payload.label || 'Alarm',
                  time: payload.time || new Date().toLocaleTimeString(),
                });
              }
              break;
            case 'MUSIC_STATE_CHANGED':
              if (payload) {
                setMusicState(payload);
              }
              break;
            case 'CLOUD_API_TOGGLED':
              if (payload && typeof payload.cloud_api_enabled === 'boolean') {
                setCloudApiEnabled(payload.cloud_api_enabled);
              }
              break;
            default:
              break;
          }
        } catch (error) {
          console.warn('[JARVIS] WebSocket message ignored:', error);
        }
      };

      ws.onclose = () => {
        if (!isMountedRef.current) return;
        setTelemetry((prev) => ({ ...prev, online: false }));
        const attempt = reconnectAttempts.current++;
        const delay = Math.min(1000 * 2 ** attempt, 8000) + Math.floor(Math.random() * 400);
        reconnectTimer.current = setTimeout(connectWs, delay);
      };

      ws.onerror = () => {
        try { ws.close(); } catch { /* connection is already closing */ }
      };
    } catch {
      setTelemetry((prev) => ({ ...prev, online: false }));
      reconnectTimer.current = setTimeout(connectWs, Math.min(1000 * 2 ** reconnectAttempts.current++, 8000));
    }
  }, [refreshConnection, refreshCloudApiState, playAlarmChime]);

  useEffect(() => {
    isMountedRef.current = true;
    refreshConnection();
    refreshCloudApiState();
    connectWs();
    return () => {
      isMountedRef.current = false;
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
      }
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connectWs, refreshConnection, refreshCloudApiState]);

  useEffect(() => {
    if (activeTab !== 'meetings') return;
    fetch(`${API_BASE}/api/meetings`, { cache: 'no-store' })
      .then((res) => res.json())
      .then((data) => {
        setMeetings(data.meetings || []);
        setSummaries(data.summaries || []);
        if (data.live_captions) setCaptions(data.live_captions);
        if (data.current_meeting) setCurrentMeeting(data.current_meeting);
      })
      .catch(() => undefined);
  }, [activeTab]);

  const sendCommand = useCallback((query: string): void => {
    const cleanQuery = query.trim();
    if (!cleanQuery) return;

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'USER_COMMAND', payload: { query: cleanQuery, source: 'text' } }));
      return;
    }

    const userMessage: ChatMessageItem = {
      id: `user-${Date.now()}`,
      role: 'user',
      sender: 'user',
      content: cleanQuery,
      text: cleanQuery,
      source: 'text',
      timestamp: new Date().toLocaleTimeString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    fetch(`${API_BASE}/api/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cleanQuery, source: 'text' }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.connection) setConnection(data.connection);
        const assistantMessage: ChatMessageItem = data.message || {
          id: `jarvis-${Date.now()}`,
          role: 'assistant',
          sender: 'jarvis',
          content: data.text || data.reply || data.response || 'No response received.',
          text: data.text || data.reply || data.response || 'No response received.',
          source: 'text',
          timestamp: new Date().toLocaleTimeString(),
          action: data.action,
          tier: data.tier,
          provider: data.provider,
          latency_ms: data.latency_ms,
          data: data.data,
          meta: {
            action: data.action,
            tier: data.tier,
            provider: data.provider,
            model: data.model,
            latency_ms: data.latency_ms,
            data: data.data,
          },
        };
        setMessages((prev) => [...prev, assistantMessage]);
      })
      .catch(() => setMessages((prev) => [...prev, {
        id: `error-${Date.now()}`,
        role: 'assistant',
        sender: 'jarvis',
        content: 'Connection to the JARVIS core was interrupted. Reconnecting now.',
        text: 'Connection to the JARVIS core was interrupted. Reconnecting now.',
        source: 'system',
        timestamp: new Date().toLocaleTimeString(),
      }]));
  }, []);

  const toggleMic = useCallback(async (): Promise<void> => {
    const enabled = !audioState.mic_active;
    try {
      const res = await fetch(`${API_BASE}/api/audio/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: 'mic', enabled }),
      });
      if (res.ok) {
        const data = await res.json();
        setAudioState((prev) => ({ ...prev, ...data }));
      }
    } catch {
      setAudioState((prev) => ({ ...prev, mic_active: enabled }));
    }
  }, [audioState.mic_active]);

  const toggleTts = useCallback(async (): Promise<void> => {
    const enabled = !audioState.tts_active;
    try {
      const res = await fetch(`${API_BASE}/api/audio/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: 'tts', enabled }),
      });
      if (res.ok) {
        const data = await res.json();
        setAudioState((prev) => ({ ...prev, ...data }));
      }
    } catch {
      setAudioState((prev) => ({ ...prev, tts_active: enabled }));
    }
  }, [audioState.tts_active]);

  const abortAgent = useCallback(async (): Promise<void> => {
    try { await fetch(`${API_BASE}/api/agent/abort`, { method: 'POST' }); } catch { /* offline */ }
  }, []);

  const addMeeting = useCallback(async (meeting: any): Promise<void> => {
    try {
      await fetch(`${API_BASE}/api/meetings`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(meeting) });
      const data = await (await fetch(`${API_BASE}/api/meetings`)).json();
      setMeetings(data.meetings || []);
    } catch { /* offline */ }
  }, []);

  const deleteMeeting = useCallback(async (id: string): Promise<void> => {
    try { await fetch(`${API_BASE}/api/meetings/${id}`, { method: 'DELETE' }); setMeetings((prev) => prev.filter((item) => item.id !== id)); } catch { /* offline */ }
  }, []);

  const joinMeeting = useCallback(async (url: string, title?: string, id?: string): Promise<void> => {
    try {
      if (id) await fetch(`${API_BASE}/api/meetings/${id}/join`, { method: 'POST' });
      else await fetch(`${API_BASE}/api/meetings/join-url`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, title: title || 'Online Meeting' }) });
      const data = await (await fetch(`${API_BASE}/api/meetings`)).json();
      setMeetings(data.meetings || []);
    } catch { /* offline */ }
  }, []);

  const leaveMeeting = useCallback(async (): Promise<void> => {
    try { await fetch(`${API_BASE}/api/meetings/leave`, { method: 'POST' }); setCurrentMeeting(null); } catch { /* offline */ }
  }, []);

  const renderActivePanel = (): React.ReactNode => {
    switch (activeTab) {
      case 'command':
        return (
          <CommandStream
            messages={messages}
            connection={connection}
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
        return <MeetingHub meetings={meetings} summaries={summaries} liveCaptions={captions} currentMeeting={currentMeeting} onAddMeeting={addMeeting} onDeleteMeeting={deleteMeeting} onJoinMeeting={joinMeeting} onLeaveMeeting={leaveMeeting} apiBase={API_BASE} />;
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

  if (isMiniMode) {
    const latestJarvisMsg = [...messages].reverse().find((item) => item.sender === 'jarvis');
    return (
      <div className="h-screen w-screen overflow-hidden bg-void p-2 text-ice hud-scanlines">
        <TopTelemetryBar
          telemetry={telemetry}
          audioState={audioState}
          tokenData={tokenData}
          isMiniMode
          onToggleMiniMode={() => toggleMiniMode(false)}
          cloudApiEnabled={cloudApiEnabled}
          onToggleCloudApi={toggleCloudApi}
        />
        <div className="flex h-[calc(100%-88px)] flex-col justify-end gap-2">
          {latestJarvisMsg && (
            <div className="rounded-xl border border-cyan-arc/30 bg-[#09192D]/90 px-3 py-2 text-xs text-cyan-arc">
              {latestJarvisMsg.text || latestJarvisMsg.content}
            </div>
          )}
          <div className="flex gap-2">
            <input
              className="jarvis-input min-w-0 flex-1 px-3 py-2 text-xs"
              placeholder="Ask JARVIS…"
              value={miniInput}
              onChange={(event) => setMiniInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && miniInput.trim()) {
                  sendCommand(miniInput);
                  setMiniInput('');
                }
              }}
            />
            <button
              className="jarvis-button jarvis-button-orange px-3 text-xs"
              onClick={() => {
                if (miniInput.trim()) {
                  sendCommand(miniInput);
                  setMiniInput('');
                }
              }}
            >
              Send
            </button>
          </div>
        </div>
      </div>
    );
  }

  const localReady = Boolean(connection.local?.ready);

  return (
    <div className="jarvis-shell relative flex h-screen w-screen flex-col overflow-hidden bg-void text-ice">
      {/* Top Telemetry Header with Prominent Cloud API Toggle */}
      <TopTelemetryBar
        telemetry={telemetry}
        audioState={audioState}
        tokenData={tokenData}
        isMiniMode={false}
        onToggleMiniMode={() => toggleMiniMode(true)}
        cloudApiEnabled={cloudApiEnabled}
        onToggleCloudApi={toggleCloudApi}
      />

      {/* In-App Alarm Notification Banner with Dismiss Button */}
      {activeAlarmNotification && (
        <div className="fixed top-4 left-1/2 z-50 -translate-x-1/2 flex items-center gap-3.5 rounded-2xl border border-[#FF8A1F] bg-[#120B04]/95 px-5 py-3 shadow-[0_0_35px_rgba(255,138,31,0.45)] backdrop-blur-xl animate-bounce">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#FF8A1F]/20 text-[#FF8A1F] stitch-pulse-amber">
            <Bell size={20} />
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-widest text-[#FF8A1F]">Alarm Triggered</div>
            <div className="text-sm font-bold text-white">
              {activeAlarmNotification.label}
              {activeAlarmNotification.time ? ` (${activeAlarmNotification.time})` : ''}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setActiveAlarmNotification(null)}
            className="ml-3 rounded-xl border border-[#FF8A1F]/60 bg-[#FF8A1F]/20 px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-[#FF8A1F] transition hover:bg-[#FF8A1F]/30"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <aside className={`flex h-full shrink-0 flex-col border-r border-cyber/80 bg-[#09192D]/92 transition-all duration-200 ${sidebarOpen ? 'w-[232px]' : 'w-[62px]'}`}>
          <div className="flex items-center justify-between border-b border-cyber/70 px-3 py-3">
            {sidebarOpen && (
              <div className="flex items-center gap-2">
                <Hexagon size={18} className="text-cyan-arc" />
                <span className="font-hud text-[11px] font-bold tracking-[0.2em] text-ice">JARVIS OS</span>
              </div>
            )}
            <button
              className="ml-auto rounded-lg p-1.5 text-steel transition hover:bg-cyber/40 hover:text-cyan-arc"
              onClick={() => setSidebarOpen((open) => !open)}
              title={sidebarOpen ? 'Collapse navigation' : 'Expand navigation'}
            >
              {sidebarOpen ? <ChevronLeft size={15} /> : <ChevronRight size={15} />}
            </button>
          </div>

          <nav className="flex-1 space-y-1 px-2 py-3">
            {TABS.map((tab) => {
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`group flex w-full items-center gap-3 rounded-xl border px-2.5 py-2.5 text-left transition ${
                    active
                      ? 'border-cyan-arc/40 bg-cyan-arc/10 text-ice shadow-[inset_3px_0_0_#4DA3FF]'
                      : 'border-transparent text-steel hover:border-cyber hover:bg-cyber/25 hover:text-ice'
                  }`}
                  title={tab.detail}
                >
                  <span className={active ? 'text-cyan-arc' : 'text-steel group-hover:text-cyan-arc'}>{tab.icon}</span>
                  {sidebarOpen && (
                    <span className="min-w-0">
                      <span className="block text-[11px] font-bold uppercase tracking-[0.12em]">{tab.label}</span>
                      <span className="mt-0.5 block truncate text-[10px] text-steel">{tab.detail}</span>
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          <div className={`border-t border-cyber/70 p-3 ${sidebarOpen ? '' : 'flex justify-center'}`}>
            {sidebarOpen ? (
              <div className="rounded-xl border border-cyber/70 bg-void/50 p-3">
                <div className="mb-2 flex items-center justify-between text-[9px] font-bold uppercase tracking-[0.16em] text-steel">
                  <span className="flex items-center gap-1.5"><Activity size={11} className="text-gold-reactor" /> Route health</span>
                  <span className={localReady ? 'text-emerald-300' : 'text-gold-reactor'}>{localReady ? 'ready' : 'check'}</span>
                </div>
                <div className="text-[10px] leading-relaxed text-steel">
                  {connection.local?.model || 'Local engine'}<br />
                  <span className="text-cyan-arc">{cloudApiEnabled ? (connection.local_first ? 'Local-first routing' : 'Cloud-first routing') : 'Pure Offline (0.05ms NN)'}</span>
                </div>
              </div>
            ) : (
              <Cpu size={16} className={localReady ? 'text-emerald-300' : 'text-gold-reactor'} />
            )}
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-hidden">{renderActivePanel()}</main>
      </div>

      <ApprovalModal request={approvalRequest} apiBase={API_BASE} onDismiss={() => setApprovalRequest(null)} />
    </div>
  );
};

export default App;

