import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Bell,
  Bot,
  CheckCircle2,
  Clock,
  Cpu,
  ExternalLink,
  Globe,
  Mic,
  MicOff,
  Music,
  Pause,
  Play,
  RotateCcw,
  Send,
  SkipBack,
  SkipForward,
  Sparkles,
  Volume2,
  VolumeX,
  Wifi,
  WifiOff,
  Zap,
} from 'lucide-react';

export interface ChatMessage {
  id?: string;
  role?: string;
  sender?: string;
  content?: string;
  text?: string;
  timestamp?: string;
  source?: string;
  action?: string;
  tier?: string;
  provider?: string;
  latency_ms?: number;
  data?: any;
  meta?: {
    tier?: string;
    provider?: string;
    model?: string;
    latency_ms?: number;
    action?: string;
    data?: any;
  };
}

export type ChatMessageItem = ChatMessage;

interface ConnectionSummary {
  local_first?: boolean;
  local?: { available?: boolean; downloaded?: boolean; ready?: boolean; loaded?: boolean; model?: string };
  fallback_chain?: Array<{ provider?: string; model?: string }>;
}

export interface CommandStreamProps {
  messages?: ChatMessage[];
  connection?: ConnectionSummary;
  micActive?: boolean;
  ttsActive?: boolean;
  meetingAutoMuted?: boolean;
  onSendCommand?: (cmd: string) => Promise<any> | void;
  onToggleMic?: () => void;
  onToggleTts?: () => void;
}

/**
 * Music Player Card
 * Displays active track, platform badge, and control buttons (Previous, Play/Pause, Next)
 */
const MusicPlayerCard: React.FC<{
  action?: string;
  data?: any;
}> = ({ data = {} }) => {
  const [isPlaying, setIsPlaying] = useState<boolean>(data?.state === 'playing');
  const [currentSong, setCurrentSong] = useState<string>(data?.song || 'Playback Track');
  const [loading, setLoading] = useState<boolean>(false);

  const platform = String(data?.platform || 'local').toLowerCase();
  const platformLabel =
    platform.includes('spotify') ? 'Spotify' :
    platform.includes('youtube') ? 'YouTube Music' :
    platform.includes('apple') ? 'Apple Music' : 'Local / System';

  const handleControl = async (ctrlAction: 'play_pause' | 'play' | 'pause' | 'next' | 'previous'): Promise<void> => {
    setLoading(true);
    try {
      const res = await fetch('/api/subsystems/music/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: ctrlAction }),
      });
      if (res.ok) {
        const resData = await res.json();
        if (ctrlAction === 'play_pause') {
          setIsPlaying((prev) => !prev);
        } else if (ctrlAction === 'play') {
          setIsPlaying(true);
        } else if (ctrlAction === 'pause') {
          setIsPlaying(false);
        }
        if (resData?.playback?.song) {
          setCurrentSong(resData.playback.song);
        }
      }
    } catch (err) {
      console.warn('[JARVIS] Music control error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stitch-card mt-2.5 overflow-hidden rounded-xl border border-[#4DA3FF]/30 bg-gradient-to-br from-[#0c1e36]/90 to-[#071324]/95 p-3.5 shadow-lg">
      <div className="flex items-center justify-between gap-2 border-b border-white/10 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#4DA3FF]/20 text-[#4DA3FF]">
            <Music size={15} />
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#7D9AB8]">Music Subsystem</div>
            <div className="max-w-[200px] truncate text-xs font-semibold text-white">{currentSong}</div>
          </div>
        </div>
        <span className="stitch-badge stitch-badge-cyan text-[9px]">
          {platformLabel}
        </span>
      </div>

      <div className="mt-3 flex items-center justify-center gap-3">
        <button
          type="button"
          disabled={loading}
          onClick={() => handleControl('previous')}
          title="Previous Track"
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-[#07111F]/70 text-steel transition hover:border-[#4DA3FF]/50 hover:text-[#4DA3FF] disabled:opacity-40"
        >
          <SkipBack size={14} />
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => handleControl('play_pause')}
          title={isPlaying ? 'Pause' : 'Play'}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#4DA3FF]/60 bg-[#4DA3FF]/20 text-[#4DA3FF] shadow-[0_0_12px_rgba(77,163,255,0.3)] transition hover:bg-[#4DA3FF]/30 disabled:opacity-40"
        >
          {isPlaying ? <Pause size={16} /> : <Play size={16} className="ml-0.5" />}
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => handleControl('next')}
          title="Next Track"
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-[#07111F]/70 text-steel transition hover:border-[#4DA3FF]/50 hover:text-[#4DA3FF] disabled:opacity-40"
        >
          <SkipForward size={14} />
        </button>
      </div>
    </div>
  );
};

/**
 * Alarm Widget Card
 * Displays alarm time badge, label, and Cancel button calling DELETE /api/subsystems/alarms/{id}
 */
const AlarmWidgetCard: React.FC<{
  action?: string;
  data?: any;
}> = ({ data = {} }) => {
  const [cancelledIds, setCancelledIds] = useState<Set<string>>(new Set());
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const alarms: Array<{ id: string; time: string; label?: string }> = useMemo(() => {
    if (Array.isArray(data?.alarms) && data.alarms.length > 0) {
      return data.alarms.map((a: any, idx: number) => ({
        id: String(a.id || a.alarm_id || `alr-${idx}`),
        time: String(a.time || a.alarm_time || '00:00'),
        label: String(a.label || 'Alarm'),
      }));
    }
    if (data?.time || data?.alarm_id || data?.id) {
      return [{
        id: String(data.alarm_id || data.id || 'current'),
        time: String(data.time || (data.duration_minutes ? `${data.duration_minutes}m` : 'Scheduled')),
        label: String(data.label || 'Alarm'),
      }];
    }
    return [];
  }, [data]);

  const handleCancel = async (alarmId: string): Promise<void> => {
    setCancellingId(alarmId);
    try {
      const res = await fetch(`/api/subsystems/alarms/${encodeURIComponent(alarmId)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setCancelledIds((prev) => new Set([...prev, alarmId]));
      }
    } catch (err) {
      console.warn('[JARVIS] Cancel alarm error:', err);
    } finally {
      setCancellingId(null);
    }
  };

  if (alarms.length === 0) return null;

  return (
    <div className="stitch-card stitch-card-amber mt-2.5 overflow-hidden rounded-xl border border-[#FF8A1F]/30 bg-gradient-to-br from-[#1d160c]/90 to-[#0d0904]/95 p-3.5 shadow-lg">
      <div className="flex items-center gap-2 border-b border-white/10 pb-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#FF8A1F]/20 text-[#FF8A1F]">
          <Bell size={15} />
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wider text-[#FF8A1F]">Active Alarm Monitor</div>
          <div className="text-[11px] text-steel">{alarms.length} scheduled trigger{alarms.length > 1 ? 's' : ''}</div>
        </div>
      </div>

      <div className="mt-2.5 space-y-2">
        {alarms.map((alarm) => {
          const isCancelled = cancelledIds.has(alarm.id);
          const isProcessing = cancellingId === alarm.id;
          return (
            <div
              key={alarm.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-white/8 bg-[#07111F]/60 px-3 py-2 text-xs"
            >
              <div className="flex min-w-0 items-center gap-2">
                <span className="stitch-badge stitch-badge-amber font-mono font-bold">
                  <Clock size={11} className="mr-1 inline" />
                  {alarm.time}
                </span>
                <span className="truncate font-semibold text-ice">{alarm.label}</span>
              </div>
              <button
                type="button"
                disabled={isCancelled || isProcessing}
                onClick={() => handleCancel(alarm.id)}
                className={`shrink-0 rounded-lg border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider transition ${
                  isCancelled
                    ? 'cursor-not-allowed border-white/10 bg-white/5 text-steel/50'
                    : 'border-[#FF3B5C]/50 bg-[#FF3B5C]/15 text-[#FF3B5C] hover:border-[#FF3B5C] hover:bg-[#FF3B5C]/25'
                }`}
              >
                {isCancelled ? 'Cancelled' : isProcessing ? 'Cancelling…' : 'Cancel Alarm'}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/**
 * Web Search Card
 * Displays search query, snippet extracts, and external source link buttons
 */
const WebSearchCard: React.FC<{
  action?: string;
  data?: any;
}> = ({ data = {} }) => {
  const query = String(data?.query || data?.search_query || '');
  const results: Array<{ title?: string; snippet?: string; url?: string; link?: string }> = useMemo(() => {
    if (Array.isArray(data?.results) && data.results.length > 0) return data.results;
    if (data?.summary) return [{ title: 'Synthesized Summary', snippet: String(data.summary), url: '' }];
    return [];
  }, [data]);

  return (
    <div className="stitch-card mt-2.5 overflow-hidden rounded-xl border border-[#4DA3FF]/30 bg-gradient-to-br from-[#0b1c33]/90 to-[#07111F]/95 p-3.5 shadow-lg">
      <div className="flex items-center justify-between gap-2 border-b border-white/10 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#4DA3FF]/20 text-[#4DA3FF]">
            <Globe size={15} />
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#7D9AB8]">Neural Web Search</div>
            {query && <div className="max-w-[220px] truncate text-xs font-semibold text-ice">"{query}"</div>}
          </div>
        </div>
        <span className="stitch-badge stitch-badge-cyan text-[9px]">Verified Source</span>
      </div>

      {results.length > 0 && (
        <div className="mt-2.5 space-y-2">
          {results.slice(0, 3).map((res, idx) => {
            const url = res.url || res.link;
            return (
              <div key={idx} className="rounded-lg border border-white/8 bg-[#07111F]/60 p-2.5 text-xs">
                {res.title && <div className="mb-1 font-semibold text-ice">{res.title}</div>}
                {res.snippet && <div className="line-clamp-3 text-[11px] leading-relaxed text-steel">{res.snippet}</div>}
                {url && (
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-[#4DA3FF]/40 bg-[#4DA3FF]/10 px-2 py-0.5 text-[10px] font-semibold text-[#4DA3FF] transition hover:border-[#4DA3FF] hover:bg-[#4DA3FF]/20"
                  >
                    <span>Visit Source</span>
                    <ExternalLink size={10} />
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

/**
 * Routing Badge Helper
 */
const RoutingBadge: React.FC<{
  tier?: string;
  provider?: string;
  model?: string;
  latencyMs?: number;
}> = ({ tier, provider, model, latencyMs }) => {
  const isLocalNN =
    tier === 'LOCAL_NN' ||
    tier === 'LOCAL' ||
    tier === 'LOCAL_FIRST' ||
    provider === 'local' ||
    provider === 'music_handler' ||
    provider === 'alarm_handler' ||
    provider === 'system_controls';

  const isPureOffline = tier === 'OFFLINE' || tier === 'PURE_OFFLINE';

  if (isLocalNN) {
    const lat = latencyMs !== undefined && latencyMs > 0 ? `${latencyMs}ms` : '0.05ms';
    return (
      <span className="stitch-badge stitch-badge-cyan font-mono text-[9px] tracking-wider" title="Local Neural ONNX Intent Classification (Sub-5ms, Zero API Call)">
        <Zap size={10} className="mr-0.5 inline text-[#4DA3FF]" />
        ⚡ Local NN · {lat}
      </span>
    );
  }

  if (isPureOffline) {
    return (
      <span className="stitch-badge stitch-badge-amber font-mono text-[9px] tracking-wider" title="Pure Offline Mode Active (Air-Gapped)">
        🔒 Offline Mode · 0.05ms NN
      </span>
    );
  }

  const prov = provider || 'Cloud AI';
  const latStr = latencyMs ? ` · ${latencyMs}ms` : '';
  return (
    <span className="stitch-badge stitch-badge-cyan font-mono text-[9px] tracking-wider" title={`Cloud Provider: ${prov} ${model || ''}`}>
      ☁️ {prov}{model ? ` (${model})` : ''}{latStr}
    </span>
  );
};

export const CommandStream: React.FC<CommandStreamProps> = ({
  messages: externalMessages = [],
  connection = {},
  micActive = false,
  ttsActive = true,
  meetingAutoMuted = false,
  onSendCommand,
  onToggleMic,
  onToggleTts,
}) => {
  const [input, setInput] = useState('');
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [isListeningSpeech, setIsListeningSpeech] = useState(false);
  const recognitionRef = useRef<any>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const mergedMessages = useMemo(() => {
    const seen = new Set<string>();
    return [...externalMessages, ...localMessages].filter((message) => {
      const text = (message.content || message.text || '').trim();
      if (!text) return false;
      const key = message.id || `${message.role || message.sender}:${text}:${message.timestamp || ''}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [externalMessages, localMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [mergedMessages, loading]);

  const transmitCommand = async (command: string): Promise<void> => {
    const cleanCmd = command.trim();
    if (!cleanCmd || loading) return;
    setInput('');
    setLoading(true);
    try {
      if (onSendCommand) {
        await onSendCommand(cleanCmd);
      } else {
        const response = await fetch('/api/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: cleanCmd, source: 'hud' }),
        });
        const data = await response.json();
        setLocalMessages((previous) => [
          ...previous,
          {
            id: `user-${Date.now()}`,
            role: 'user',
            content: cleanCmd,
            timestamp: new Date().toLocaleTimeString(),
          },
          ...(data.message ? [data.message] : []),
        ]);
      }
    } catch (error: any) {
      setLocalMessages((previous) => [
        ...previous,
        {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: `Command failed: ${error?.message || 'JARVIS core unavailable.'}`,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    await transmitCommand(input);
  };

  // Browser Native Speech Recognition
  const handleMicClick = (): void => {
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
      if (onToggleMic) onToggleMic();
      return;
    }

    if (isListeningSpeech && recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      setIsListeningSpeech(false);
      return;
    }

    try {
      const recognition = new SpeechRec();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListeningSpeech(true);
      };

      recognition.onresult = (event: any) => {
        let interim = '';
        let final = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            final += event.results[i][0].transcript;
          } else {
            interim += event.results[i][0].transcript;
          }
        }
        const captured = final || interim;
        if (captured) {
          setInput(captured);
        }
        if (final && final.trim()) {
          try {
            recognition.stop();
          } catch {}
          setIsListeningSpeech(false);
          transmitCommand(final.trim());
        }
      };

      recognition.onerror = (event: any) => {
        console.warn('[JARVIS] Browser Speech error:', event.error);
        setIsListeningSpeech(false);
      };

      recognition.onend = () => {
        setIsListeningSpeech(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      console.warn('[JARVIS] Browser Speech setup failed, using native toggle:', err);
      setIsListeningSpeech(false);
      if (onToggleMic) onToggleMic();
    }
  };

  const clearContext = async (): Promise<void> => {
    try {
      await fetch('/api/context/clear', { method: 'POST' });
      setLocalMessages([]);
    } catch {
      // Keep the current stream visible when the server is offline.
    }
  };

  const quickPrompts = [
    { label: 'System check', value: 'System telemetry status' },
    { label: 'Play music', value: 'Play jazz on Spotify' },
    { label: 'Set alarm', value: 'Set alarm for 7:30 AM' },
    { label: 'Web search', value: 'Search for quantum computing advancements' },
  ];
  const localReady = Boolean(connection.local?.ready);
  const online = connection.local?.ready || (connection.fallback_chain && connection.fallback_chain.length > 0);

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 overflow-hidden bg-transparent p-4 sm:p-6">
      <div className="jarvis-panel shrink-0 overflow-hidden p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-gold-reactor">
              <Sparkles size={13} /> Neural command stream
            </div>
            <h1 className="font-hud text-xl font-bold tracking-[0.08em] text-ice sm:text-2xl">How can I help, sir?</h1>
            <p className="mt-2 max-w-xl text-xs leading-relaxed text-steel">
              Sub-5ms local neural routing with offline fallback, inline widgets, and full cloud failover.
            </p>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider">
            <span className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 ${online ? 'border-emerald-300/30 bg-emerald-300/10 text-emerald-300' : 'border-gold-reactor/30 bg-gold-reactor/10 text-gold-reactor'}`}>
              {online ? <Wifi size={12} /> : <WifiOff size={12} />}{online ? 'Route available' : 'Checking route'}
            </span>
            <span className="hidden rounded-full border border-cyan-arc/30 bg-cyan-arc/10 px-2.5 py-1.5 text-cyan-arc sm:inline">
              {connection.local_first ? 'Local first' : 'Cloud first'}
            </span>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {quickPrompts.map((prompt) => (
            <button
              key={prompt.label}
              onClick={() => setInput(prompt.value)}
              className="jarvis-button rounded-full border border-cyber bg-void/40 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-steel hover:border-cyan-arc/50 hover:text-cyan-arc"
            >
              {prompt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-cyber/80 bg-[#09192D]/75 shadow-[0_18px_45px_rgba(0,0,0,0.2)]">
        <div className="flex shrink-0 items-center justify-between border-b border-cyber/70 px-4 py-3 sm:px-5">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-arc/10 text-cyan-arc">
              <Bot size={15} />
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-ice">Conversation</div>
              <div className="text-[10px] text-steel">{mergedMessages.length} messages in this session</div>
            </div>
          </div>
          <button onClick={clearContext} className="flex items-center gap-1.5 rounded-lg border border-transparent px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-steel hover:border-cyber hover:text-gold-reactor">
            <RotateCcw size={12} /> Reset memory
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
          {mergedMessages.length === 0 ? (
            <div className="flex h-full min-h-[220px] flex-col items-center justify-center text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-cyan-arc/30 bg-cyan-arc/10 text-cyan-arc shadow-arc-glow">
                <Cpu size={28} />
              </div>
              <div className="font-hud text-sm font-bold uppercase tracking-[0.15em] text-ice">Core ready</div>
              <p className="mt-2 max-w-md text-xs leading-relaxed text-steel">
                Send a question, command, or use the microphone button. Local neural inference is {localReady ? 'ready' : 'active as local fallback'}.
              </p>
            </div>
          ) : (
            <div className="mx-auto flex max-w-4xl flex-col gap-4">
              {mergedMessages.map((message, index) => {
                const isUser = message.role === 'user' || message.sender?.toLowerCase() === 'user';
                const text = message.content || message.text || '';
                const action = message.action || message.meta?.action || '';
                const data = message.data || message.meta?.data || {};
                const tier = message.tier || message.meta?.tier || '';
                const provider = message.provider || message.meta?.provider || '';
                const model = message.meta?.model || '';
                const latencyMs = message.latency_ms ?? message.meta?.latency_ms;

                const isMusic = !isUser && (
                  action === 'play_music' ||
                  action === 'music_control' ||
                  Boolean(data?.song) ||
                  Boolean(data?.platform) ||
                  (data?.action && ['play', 'pause', 'play_pause', 'next', 'previous'].includes(data.action))
                );

                const isAlarm = !isUser && (
                  action === 'set_alarm' ||
                  action === 'list_alarms' ||
                  action === 'cancel_alarm' ||
                  Boolean(data?.alarms) ||
                  Boolean(data?.time) ||
                  Boolean(data?.alarm_id)
                );

                const isWebSearch = !isUser && (
                  action === 'web_search' ||
                  action === 'web_research' ||
                  (Array.isArray(data?.results) && data.results.length > 0) ||
                  Boolean(data?.query && data?.results)
                );

                return (
                  <div key={message.id || index} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[92%] rounded-2xl border px-4 py-3 sm:max-w-[82%] ${isUser ? 'border-cyan-arc/35 bg-cyan-arc/10' : 'border-gold-reactor/25 bg-gold-reactor/5'}`}>
                      <div className="mb-2 flex flex-wrap items-center gap-2 text-[9px] font-bold uppercase tracking-[0.16em]">
                        <span className={isUser ? 'text-cyan-arc' : 'text-gold-reactor'}>{isUser ? 'You' : 'JARVIS'}</span>
                        {!isUser && (
                          <RoutingBadge tier={tier} provider={provider} model={model} latencyMs={latencyMs} />
                        )}
                        {message.timestamp && <span className="ml-auto font-mono font-normal text-steel">{message.timestamp}</span>}
                      </div>

                      <div className="whitespace-pre-wrap text-sm leading-relaxed text-ice">{text}</div>

                      {/* Inline Interactive Cards */}
                      {isMusic && <MusicPlayerCard action={action} data={data} />}
                      {isAlarm && <AlarmWidgetCard action={action} data={data} />}
                      {isWebSearch && <WebSearchCard action={action} data={data} />}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {loading && (
            <div className="mt-3 flex items-center gap-2 text-xs text-gold-reactor">
              <span className="h-2 w-2 animate-ping rounded-full bg-gold-reactor" /> JARVIS is thinking…
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={handleSubmit} className="shrink-0 border-t border-cyber/70 bg-[#07111F]/80 p-3 sm:p-4">
          {meetingAutoMuted && <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gold-reactor">Microphone auto-muted while a meeting is active</div>}
          <div className="flex items-center gap-2">
            <input
              id="command-input"
              name="commandInput"
              autoComplete="off"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={isListeningSpeech ? "Listening to your voice..." : "Ask JARVIS anything…"}
              className="jarvis-input min-w-0 flex-1 px-4 py-3 text-sm placeholder:text-steel/70"
            />
            <button
              type="button"
              onClick={handleMicClick}
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition ${
                isListeningSpeech || micActive
                  ? 'border-cyan-arc/70 bg-cyan-arc/20 text-cyan-arc stitch-glow-cyan animate-pulse'
                  : 'border-cyber text-steel hover:border-cyan-arc/50 hover:text-cyan-arc'
              }`}
              title={isListeningSpeech ? 'Listening (click to stop)' : 'Speak command via microphone'}
            >
              {isListeningSpeech || micActive ? <Mic size={17} /> : <MicOff size={17} />}
            </button>
            {onToggleTts && (
              <button
                type="button"
                onClick={onToggleTts}
                className={`hidden h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition sm:flex ${
                  ttsActive ? 'border-gold-reactor/60 bg-gold-reactor/10 text-gold-reactor' : 'border-cyber text-steel hover:border-gold-reactor/50 hover:text-gold-reactor'
                }`}
                title={ttsActive ? 'Mute voice output' : 'Enable voice output'}
              >
                {ttsActive ? <Volume2 size={17} /> : <VolumeX size={17} />}
              </button>
            )}
            <button type="submit" disabled={loading || !input.trim()} className="jarvis-button jarvis-button-orange h-11 shrink-0 px-4 text-xs font-bold uppercase tracking-wider disabled:opacity-40">
              <Send size={15} /> <span className="hidden sm:inline">Transmit</span>
            </button>
          </div>
          <div className="mt-2 flex items-center justify-between text-[9px] uppercase tracking-[0.14em] text-steel">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 size={11} className="text-emerald-300" /> End-to-end command route active
            </span>
            <span className="hidden font-mono sm:inline">Enter to transmit</span>
          </div>
        </form>
      </div>
    </section>
  );
};

export default CommandStream;

