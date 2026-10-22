import React from 'react';
import { Cpu, HardDrive, Battery, BatteryCharging, Wifi, WifiOff, Minimize2, Maximize2 } from 'lucide-react';

interface TelemetryData {
  cpu: number;
  ram: number;
  battery: number;
  charging: boolean;
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

interface TopTelemetryBarProps {
  telemetry: TelemetryData;
  audioState: AudioData;
  tokenData: TokenData;
  isMiniMode: boolean;
  onToggleMiniMode: () => void;
}

export const TopTelemetryBar: React.FC<TopTelemetryBarProps> = ({
  telemetry,
  audioState,
  tokenData,
  isMiniMode,
  onToggleMiniMode,
}) => {
  // Determine Core Visualizer State
  const isAgentWorking = audioState.status === 'thinking';
  const isAudioActive = audioState.status === 'listening' || audioState.status === 'speaking';

  const coreColor = isAudioActive
    ? '#00E5FF'
    : isAgentWorking
    ? '#FFB300'
    : '#6488A4';

  const coreGlow = isAudioActive
    ? 'rgba(0, 229, 255, 0.4)'
    : isAgentWorking
    ? 'rgba(255, 179, 0, 0.4)'
    : 'rgba(100, 136, 164, 0.15)';

  // Arc Gauge renderer
  const renderRadialGauge = (value: number, label: string, icon: React.ReactNode, color: string) => {
    const radius = 22;
    const stroke = 3;
    const normalizedRadius = radius - stroke * 2;
    const circumference = normalizedRadius * 2 * Math.PI;
    const strokeDashoffset = circumference - (value / 100) * circumference;

    return (
      <div className="flex items-center space-x-2 bg-void/60 border border-cyber/50 px-2.5 py-1 rounded">
        <div className="relative w-11 h-11 flex items-center justify-center">
          <svg height={radius * 2} width={radius * 2} className="transform -rotate-90">
            <circle
              stroke="#16324A"
              fill="transparent"
              strokeWidth={stroke}
              r={normalizedRadius}
              cx={radius}
              cy={radius}
            />
            <circle
              stroke={color}
              fill="transparent"
              strokeWidth={stroke}
              strokeDasharray={`${circumference} ${circumference}`}
              style={{ strokeDashoffset, transition: 'stroke-dashoffset 0.5s ease-in-out' }}
              strokeLinecap="round"
              r={normalizedRadius}
              cx={radius}
              cy={radius}
            />
          </svg>
          <div className="absolute text-[10px] font-mono text-ice font-bold">{Math.round(value)}%</div>
        </div>
        <div className="flex flex-col">
          <div className="flex items-center space-x-1 text-steel text-[10px] font-mono">
            {icon}
            <span>{label}</span>
          </div>
          <span className="text-xs font-mono font-bold text-ice">{value.toFixed(1)}%</span>
        </div>
      </div>
    );
  };

  return (
    <header className="w-full bg-tactical border-b border-cyber px-4 py-2 flex items-center justify-between hud-panel relative z-40 select-none">
      {/* Left: Branding & Core Visualizer */}
      <div className="flex items-center space-x-4">
        {/* Dynamic Geometric Core Visualizer (NO MARVEL LOGOS) */}
        <div className="relative w-12 h-12 flex items-center justify-center">
          {/* Outer Segmented Tech Ring */}
          <svg className="absolute inset-0 w-full h-full animate-spin-slow" viewBox="0 0 100 100">
            <circle
              cx="50"
              cy="50"
              r="44"
              fill="none"
              stroke={coreColor}
              strokeWidth="2"
              strokeDasharray="18 10 35 12"
              opacity="0.85"
            />
          </svg>
          {/* Inner Counter-Rotating Ring */}
          <svg className="absolute inset-0 w-full h-full animate-spin-reverse" viewBox="0 0 100 100">
            <circle
              cx="50"
              cy="50"
              r="34"
              fill="none"
              stroke={coreColor}
              strokeWidth="1.5"
              strokeDasharray="10 8 20 6"
              opacity="0.65"
            />
          </svg>
          {/* Concentric Geometric Hexagon Center */}
          <div
            className="w-5 h-5 rounded-full flex items-center justify-center transition-all duration-300"
            style={{
              backgroundColor: coreColor,
              boxShadow: `0 0 16px ${coreGlow}`,
            }}
          >
            <div className="w-2 h-2 rounded-full bg-void animate-ping" />
          </div>
        </div>

        {/* Brand & Status Text */}
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-sm font-hud font-black tracking-widest text-ice glow-cyan">
              J.A.R.V.I.S. <span className="text-cyan-arc font-mono font-normal text-xs">2.0</span>
            </span>
            <span
              className={`text-[9px] font-mono px-1.5 py-0.5 rounded uppercase font-bold tracking-wider ${
                audioState.status === 'listening'
                  ? 'bg-cyan-arc/20 text-cyan-arc border border-cyan-arc/40'
                  : audioState.status === 'speaking'
                  ? 'bg-cyan-arc/20 text-cyan-arc border border-cyan-arc/40'
                  : audioState.status === 'thinking'
                  ? 'bg-gold-reactor/20 text-gold-reactor border border-gold-reactor/40'
                  : 'bg-cyber/40 text-steel border border-cyber'
              }`}
            >
              {audioState.status}
            </span>
          </div>
          <div className="text-[10px] font-mono text-steel flex items-center space-x-2">
            <span>SYS::ONLINE</span>
            <span>•</span>
            <span className="text-ice/70">{new Date().toLocaleTimeString()}</span>
          </div>
        </div>
      </div>

      {/* Center: Live Radial Gauges */}
      <div className="hidden md:flex items-center space-x-3">
        {renderRadialGauge(telemetry.cpu, 'CPU LOAD', <Cpu size={11} />, '#00E5FF')}
        {renderRadialGauge(telemetry.ram, 'MEM USAGE', <HardDrive size={11} />, '#00E5FF')}
        {renderRadialGauge(
          telemetry.battery,
          telemetry.charging ? 'CHARGING' : 'BATTERY',
          telemetry.charging ? <BatteryCharging size={11} /> : <Battery size={11} />,
          telemetry.battery < 20 ? '#FF3B5C' : '#00E5FF'
        )}
      </div>

      {/* Right: Live Token & Latency Telemetry + Mini-HUD Toggle */}
      <div className="flex items-center space-x-3">
        {/* Token Telemetry HUD */}
        <div className="hidden lg:flex flex-col text-right font-mono text-[10px] bg-void/60 border border-cyber/50 px-2.5 py-1 rounded">
          <div className="flex items-center justify-end space-x-1.5 text-ice font-bold">
            <span className="text-gold-reactor">{tokenData.provider.toUpperCase()}</span>
            <span className="text-steel">/</span>
            <span className="text-cyan-arc">{tokenData.model}</span>
          </div>
          <div className="flex items-center justify-end space-x-2 text-steel text-[9px]">
            <span>{tokenData.latency_ms}ms</span>
            <span>•</span>
            <span>{tokenData.prompt_tokens + tokenData.completion_tokens} tok</span>
            <span>•</span>
            <span className="text-ice/90">Total: {tokenData.total_session_tokens}</span>
          </div>
        </div>

        {/* Online Network Badge */}
        <div
          className={`flex items-center space-x-1 px-2 py-1 rounded text-[10px] font-mono border ${
            telemetry.online
              ? 'border-cyan-arc/30 bg-cyan-arc/10 text-cyan-arc'
              : 'border-crimson/30 bg-crimson/10 text-crimson'
          }`}
          title={telemetry.online ? 'Global Network Connected' : 'Offline Mode (Local Fallback Active)'}
        >
          {telemetry.online ? <Wifi size={12} /> : <WifiOff size={12} />}
          <span className="hidden sm:inline font-bold">{telemetry.online ? 'ONLINE' : 'OFFLINE'}</span>
        </div>

        {/* Mini-HUD Mode Toggle */}
        <button
          onClick={onToggleMiniMode}
          className="p-1.5 bg-cyber/40 hover:bg-cyan-arc/20 border border-cyber hover:border-cyan-arc text-steel hover:text-cyan-arc rounded transition-colors"
          title={isMiniMode ? 'Restore Full Tactical HUD' : 'Collapse to Ghost Mini-HUD'}
        >
          {isMiniMode ? <Maximize2 size={15} /> : <Minimize2 size={15} />}
        </button>
      </div>
    </header>
  );
};
