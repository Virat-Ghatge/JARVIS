import React, { useState, useEffect, useRef } from 'react';
import { Send, Mic, MicOff, Volume2, VolumeX, ShieldAlert, Sparkles, Terminal } from 'lucide-react';

export interface ChatMessageItem {
  id: string;
  sender: 'user' | 'jarvis';
  source: 'voice' | 'text' | 'macro';
  text: string;
  timestamp: string;
  action?: string;
  data?: Record<string, any>;
}

interface CommandStreamProps {
  messages: ChatMessageItem[];
  micActive: boolean;
  ttsActive: boolean;
  meetingAutoMuted: boolean;
  onSendCommand: (query: string) => void;
  onToggleMic: () => void;
  onToggleTts: () => void;
}

export const CommandStream: React.FC<CommandStreamProps> = ({
  messages,
  micActive,
  ttsActive,
  meetingAutoMuted,
  onSendCommand,
  onToggleMic,
  onToggleTts,
}) => {
  const [inputText, setInputText] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim()) return;

    const cmd = inputText.trim();
    setHistory((prev) => [...prev, cmd]);
    setHistoryIndex(-1);
    onSendCommand(cmd);
    setInputText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (history.length === 0) return;
      const nextIdx = historyIndex === -1 ? history.length - 1 : Math.max(0, historyIndex - 1);
      setHistoryIndex(nextIdx);
      setInputText(history[nextIdx]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex === -1) return;
      const nextIdx = historyIndex + 1;
      if (nextIdx >= history.length) {
        setHistoryIndex(-1);
        setInputText('');
      } else {
        setHistoryIndex(nextIdx);
        setInputText(history[nextIdx]);
      }
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-void/40 relative overflow-hidden select-text">
      {/* Messages Feed */}
      <div
        ref={scrollRef}
        className="flex-1 p-4 overflow-y-auto space-y-3 font-mono text-xs scroll-smooth"
      >
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-steel/60 space-y-3 select-none">
            <Sparkles size={36} className="text-cyan-arc/40 animate-pulse" />
            <div className="text-sm font-hud text-ice/70 tracking-widest">SYSTEM READY FOR INPUT</div>
            <div className="text-[11px] max-w-sm text-center text-steel/80 leading-relaxed">
              Speak via voice commands or type queries below. Say <span className="text-cyan-arc">"What time is it"</span>, <span className="text-cyan-arc">"Check system status"</span>, or describe desktop tasks.
            </div>
          </div>
        ) : (
          messages.map((msg) => {
            const isUser = msg.sender === 'user';
            return (
              <div
                key={msg.id}
                className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
              >
                {/* Meta header */}
                <div className="flex items-center space-x-1.5 text-[9px] text-steel mb-1">
                  <span className={isUser ? 'text-cyan-arc font-bold' : 'text-gold-reactor font-bold'}>
                    {isUser ? 'OPERATOR' : 'J.A.R.V.I.S.'}
                  </span>
                  <span>•</span>
                  <span>{new Date(msg.timestamp).toLocaleTimeString()}</span>
                  <span>•</span>
                  <span className="uppercase text-[8px] bg-cyber/40 px-1 rounded">{msg.source}</span>
                  {msg.action && msg.action !== 'none' && (
                    <span className="text-cyan-arc/80 font-bold">[{msg.action}]</span>
                  )}
                </div>

                {/* Card Bubble */}
                <div
                  className={`max-w-[82%] px-3.5 py-2.5 rounded-lg border text-xs leading-relaxed transition-all ${
                    isUser
                      ? 'bg-tactical border-cyan-arc/30 text-ice shadow-arc-glow'
                      : 'bg-[#0b1526]/90 border-cyber text-ice/95'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.text}</p>

                  {/* Render Structured Card Data if present */}
                  {msg.data && Object.keys(msg.data).length > 0 && msg.data.summary && (
                    <div className="mt-2 pt-2 border-t border-cyber/50 text-[10px] text-steel font-mono">
                      <span className="text-cyan-arc font-bold">TELEMETRY: </span>
                      {msg.data.summary}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Persistent Bottom Hybrid Command Dock */}
      <div className="p-3 bg-tactical border-t border-cyber/70 hud-panel relative z-30">
        <form onSubmit={handleSubmit} className="flex items-center space-x-2">
          {/* Mic Toggle Button */}
          <button
            type="button"
            onClick={onToggleMic}
            className={`flex items-center space-x-1.5 px-3 py-2 rounded font-mono text-[11px] font-bold tracking-wider transition-all border ${
              micActive
                ? 'bg-cyan-arc/15 text-cyan-arc border-cyan-arc shadow-arc-glow'
                : meetingAutoMuted
                ? 'bg-crimson/20 text-crimson border-crimson/60 animate-pulse'
                : 'bg-cyber/40 text-steel border-cyber hover:border-steel'
            }`}
            title={
              meetingAutoMuted
                ? 'Microphone auto-muted by active meeting (Click to manually unmute)'
                : micActive
                ? 'Microphone active (Click to mute)'
                : 'Microphone muted (Click to listen)'
            }
          >
            {micActive ? <Mic size={14} className="animate-pulse" /> : <MicOff size={14} />}
            <span className="hidden sm:inline">
              {meetingAutoMuted ? 'AUTO-MUTED' : micActive ? 'MIC ACTIVE' : 'MIC MUTED'}
            </span>
          </button>

          {/* JARVIS Voice (TTS) Toggle Button */}
          <button
            type="button"
            onClick={onToggleTts}
            className={`flex items-center space-x-1.5 px-3 py-2 rounded font-mono text-[11px] font-bold tracking-wider transition-all border ${
              ttsActive
                ? 'bg-cyan-arc/15 text-cyan-arc border-cyan-arc/70 shadow-arc-glow'
                : 'bg-gold-reactor/15 text-gold-reactor border-gold-reactor/60'
            }`}
            title={ttsActive ? 'Spoken Voice Output ON' : 'Silent Text-Only Mode ON'}
          >
            {ttsActive ? <Volume2 size={14} /> : <VolumeX size={14} />}
            <span className="hidden sm:inline">{ttsActive ? 'VOICE ON' : 'SILENT'}</span>
          </button>

          {/* Persistent Text Input Bar */}
          <div className="flex-1 relative flex items-center">
            <Terminal size={14} className="absolute left-3 text-steel pointer-events-none" />
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type an OS instruction, question, or query... (Enter to send, ↑/↓ for history)"
              className="w-full bg-void/80 border border-cyber focus:border-cyan-arc text-ice text-xs font-mono rounded pl-8 pr-10 py-2 focus:outline-none transition-colors"
            />
            <button
              type="submit"
              disabled={!inputText.trim()}
              className="absolute right-1.5 p-1 text-cyan-arc disabled:text-steel/40 hover:bg-cyan-arc/10 rounded transition-colors"
            >
              <Send size={15} />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
