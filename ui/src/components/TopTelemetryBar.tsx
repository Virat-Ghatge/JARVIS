import React from 'react';
import {
  Battery,
  BatteryCharging,
  Cpu,
  HardDrive,
  Minimize2,
  Maximize2,
  Network,
  Wifi,
  WifiOff,
  Cloud,
  CloudOff,
  Zap,
} from 'lucide-react';

export interface TelemetryData {
  cpu: number;
  ram: number;
  battery: number;
  charging?: boolean;
  plugged?: boolean;
  online: boolean;
}

export interface AudioData {
  mic_active: boolean;
  tts_active: boolean;
  status: 'idle' | 'listening' | 'thinking' | 'speaking';
  meeting_auto_muted: boolean;
}

export interface TokenData {
  provider: string;
  model: string;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_session_tokens: number;
}

export interface TopTelemetryBarProps {
  telemetry: TelemetryData;
  audioState: AudioData;
  tokenData: TokenData;
  isMiniMode: boolean;
  onToggleMiniMode: () => void;
  cloudApiEnabled?: boolean;
  onToggleCloudApi?: () => void;
}

const safeNumber = (value: number | undefined, fallback = 0): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback;

const Metric: React.FC<{
  label: string;
  value: number;
  icon: React.ReactNode;
  tone: 'blue' | 'orange';
  detail?: string;
}> = ({ label, value, icon, tone, detail }) => {
  const bounded = Math.max(0, Math.min(100, safeNumber(value)));
  const color = tone === 'orange' ? '#FF8A1F' : '#4DA3FF';
  const tooltip = detail || `${label} Utilization: ${Math.round(bounded)}%`;

  return (
    <div
      title={tooltip}
      className="group relative min-w-[114px] cursor-help rounded-xl border border-white/10 bg-[#07111F]/70 px-3 py-1.5 backdrop-blur-md transition-all hover:border-[#4DA3FF]/40 hover:bg-[#07111F]/90"
    >
      <div className="mb-1 flex items-center justify-between text-[9px] font-semibold uppercase tracking-[0.16em] text-steel group-hover:text-ice">
        <span className="flex items-center gap-1.5">{icon}{label}</span>
        <span className="font-mono text-ice">{Math.round(bounded)}%</span>
      </div>
      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-[#0E1F38]">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{
            width: `${bounded}%`,
            background: `linear-gradient(90deg, ${color}99, ${color})`,
            boxShadow: `0 0 8px ${color}88`,
          }}
        />
      </div>
    </div>
  );
};

export const TopTelemetryBar: React.FC<TopTelemetryBarProps> = ({
  telemetry,
  audioState,
  tokenData,
  isMiniMode,
  onToggleMiniMode,
  cloudApiEnabled = true,
  onToggleCloudApi,
}) => {
  const currentAudio = audioState || { mic_active: false, tts_active: true, status: 'idle', meeting_auto_muted: false };
  const currentTelemetry = telemetry || { cpu: 0, ram: 0, battery: 100, charging: true, online: true };
  const currentToken = tokenData || { provider: '-', model: '-', latency_ms: 0, prompt_tokens: 0, completion_tokens: 0, total_session_tokens: 0 };
  const status = currentAudio.status || 'idle';
  const isThinking = status === 'thinking';
  const isLive = status === 'listening' || status === 'speaking';
  const coreColor = isThinking ? '#FF8A1F' : isLive ? '#4DA3FF' : '#7D9AB8';
  const online = currentTelemetry.online !== false;
  const charging = currentTelemetry.charging ?? currentTelemetry.plugged ?? true;

  return (
    <header className="relative z-40 flex min-h-[76px] items-center justify-between gap-3 border-b border-cyber/80 bg-[#09192D]/95 px-4 py-3 shadow-[0_12px_35px_rgba(0,0,0,0.22)] backdrop-blur-xl sm:px-6">
      {/* Brand & Status */}
      <div className="flex min-w-0 items-center gap-3">
        <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-cyan-arc/60 bg-cyan-arc/10" aria-label="JARVIS core">
          <div className="absolute inset-1 rounded-xl border border-gold-reactor/50" />
          <div className="h-3.5 w-3.5 rounded-full transition-all duration-300" style={{ background: coreColor, boxShadow: `0 0 20px ${coreColor}` }} />
          <div className="absolute inset-0 rounded-2xl border border-cyan-arc/25 animate-ping" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate font-hud text-sm font-black tracking-[0.22em] text-ice">JARVIS</span>
            <span className="rounded-full border border-gold-reactor/40 bg-gold-reactor/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.16em] text-gold-reactor">command center</span>
          </div>
          <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-steel">
            <span className={online ? 'text-emerald-300' : 'text-crimson'}>{online ? 'Core online' : 'Offline fallback'}</span>
            <span className="text-cyber">/</span>
            <span>{status}</span>
            {currentAudio.meeting_auto_muted && <span className="text-gold-reactor">/ meeting muted</span>}
          </div>
        </div>
      </div>

      {/* Cloud API Off-Switch & Micro-Gauges */}
      <div className="flex items-center gap-2.5">
        {/* Prominent Cloud API Off-Switch Toggle Button */}
        <button
          type="button"
          onClick={onToggleCloudApi}
          title={cloudApiEnabled ? "Cloud APIs active (Groq, Gemini). Click to switch to Pure Offline Mode (0.05ms local NN)." : "Pure Offline Mode active (Air-Gapped, Zero Latency). Click to enable Cloud AI."}
          className={`group relative flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-bold transition-all duration-200 select-none ${
            cloudApiEnabled
              ? 'border-[#4DA3FF]/50 bg-[#4DA3FF]/15 text-[#9DCEFF] hover:border-[#4DA3FF] hover:bg-[#4DA3FF]/25 stitch-glow-cyan'
              : 'border-[#FF8A1F]/60 bg-[#FF8A1F]/15 text-[#FFB66F] hover:border-[#FF8A1F] hover:bg-[#FF8A1F]/25 stitch-glow-amber'
          }`}
        >
          <span
            className="flex h-2 w-2 rounded-full transition-all duration-300"
            style={{
              background: cloudApiEnabled ? '#4DA3FF' : '#FF8A1F',
              boxShadow: `0 0 8px ${cloudApiEnabled ? '#4DA3FF' : '#FF8A1F'}`,
            }}
          />
          <span className="hidden sm:inline">
            {cloudApiEnabled ? '☁️ Cloud AI: Active' : '⚡ Pure Offline (0.05ms NN)'}
          </span>
          <span className="sm:hidden">
            {cloudApiEnabled ? '☁️ Cloud' : '⚡ Offline'}
          </span>
        </button>

        {/* Telemetry Micro-Gauges */}
        <div className="hidden items-center gap-2 xl:flex">
          <Metric label="CPU" value={currentTelemetry.cpu} icon={<Cpu size={11} />} tone="blue" detail={`CPU Load: ${currentTelemetry.cpu}%`} />
          <Metric label="Memory" value={currentTelemetry.ram} icon={<HardDrive size={11} />} tone="blue" detail={`RAM Usage: ${currentTelemetry.ram}%`} />
          <Metric
            label={charging ? 'Power' : 'Battery'}
            value={currentTelemetry.battery}
            icon={charging ? <BatteryCharging size={11} /> : <Battery size={11} />}
            tone="orange"
            detail={`Battery: ${currentTelemetry.battery}% (${charging ? 'Charging/Plugged' : 'Discharging'})`}
          />
        </div>
      </div>

      {/* Connection & Mini Mode Toggle */}
      <div className="flex shrink-0 items-center gap-2">
        <div className="hidden rounded-xl border border-white/8 bg-[#07111F]/60 px-3 py-2 text-right lg:block" title={`Active Provider: ${currentToken.provider} | Model: ${currentToken.model}`}>
          <div className="flex items-center justify-end gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-ice">
            <Network size={11} className="text-gold-reactor" />
            <span className="max-w-[150px] truncate text-cyan-arc">{currentToken.provider || 'standby'}</span>
          </div>
          <div className="mt-1 flex items-center justify-end gap-2 text-[9px] font-mono text-steel">
            <span>{currentToken.latency_ms || 0}ms</span>
            <span>•</span>
            <span>{(currentToken.total_session_tokens || 0).toLocaleString()} tok</span>
          </div>
        </div>
        <div className={`flex h-9 items-center gap-1.5 rounded-xl border px-2.5 text-[10px] font-bold uppercase tracking-wider ${online ? 'border-cyan-arc/40 bg-cyan-arc/10 text-cyan-arc' : 'border-crimson/40 bg-crimson/10 text-crimson'}`}>
          {online ? <Wifi size={13} /> : <WifiOff size={13} />}
          <span className="hidden sm:inline">{online ? 'connected' : 'offline'}</span>
        </div>
        <button
          onClick={onToggleMiniMode}
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyber bg-cyber/30 text-steel transition hover:border-cyan-arc/60 hover:text-cyan-arc"
          title={isMiniMode ? 'Restore full command center' : 'Open mini command mode'}
        >
          {isMiniMode ? <Maximize2 size={15} /> : <Minimize2 size={15} />}
        </button>
      </div>
    </header>
  );
};

