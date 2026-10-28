import React, { useState, useRef, useEffect } from "react";
import { Send, Terminal, Trash2, Sparkles, Cpu } from "lucide-react";

interface ChatMessage {
  id?: string;
  role?: string;
  sender?: string;
  content?: string;
  text?: string;
  timestamp?: string;
  meta?: {
    tier?: string;
    provider?: string;
    model?: string;
    latency_ms?: number;
  };
}

interface CommandStreamProps {
  messages?: ChatMessage[];
  onSendCommand?: (cmd: string) => Promise<any> | void;
}

export const CommandStream: React.FC<CommandStreamProps> = ({ messages: externalMessages = [], onSendCommand }) => {
  const [input, setInput] = useState("");
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Merge and deduplicate external WebSocket messages + local fallback messages
  const mergedMessages = React.useMemo(() => {
    const combined = [...externalMessages, ...localMessages];
    const seen = new Set<string>();
    const result: ChatMessage[] = [];
    for (const m of combined) {
      const txt = (m.content || m.text || "").trim();
      const role = m.role || (m.sender === "USER" ? "user" : "assistant");
      const key = m.id || `${role}:${txt}:${m.timestamp || ""}`;
      if (!seen.has(key) && txt) {
        seen.add(key);
        result.push(m);
      }
    }
    return result;
  }, [externalMessages, localMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mergedMessages, loading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cmd = input.trim();
    if (!cmd || loading) return;
    setInput("");
    setLoading(true);

    try {
      if (onSendCommand) {
        await onSendCommand(cmd);
      } else {
        const res = await fetch("/api/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command: cmd, source: "hud" }),
        });
        const data = await res.json();
        if (data?.message && externalMessages.length === 0) {
          setLocalMessages((prev) => [
            ...prev,
            { id: `u_${Date.now()}`, role: "user", content: cmd, timestamp: new Date().toLocaleTimeString() },
            data.message,
          ]);
        }
      }
    } catch (err: any) {
      setLocalMessages((prev) => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          role: "assistant",
          content: `Command execution error: ${err.message}`,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleClearContext = async () => {
    try {
      await fetch("/api/context/clear", { method: "POST" });
      setLocalMessages([]);
    } catch {
      // ignore
    }
  };

  const quickPrompts = [
    "System telemetry status",
    "What time and date is it?",
    "Write a Python quicksort implementation",
    "Weather in Jaipur",
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-180px)] min-h-[480px] bg-[#0B1320]/85 border border-[#00E5FF]/30 rounded overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-[#060A12] border-b border-[#00E5FF]/25">
        <div className="flex items-center gap-2 text-xs font-bold tracking-wider uppercase text-[#00E5FF]">
          <Terminal className="w-4 h-4" /> HOLOGRAPHIC COMMAND STREAM
        </div>
        <button
          onClick={handleClearContext}
          className="flex items-center gap-1 text-[11px] text-gray-400 hover:text-[#00E5FF] px-2 py-1 rounded border border-transparent hover:border-[#00E5FF]/30 transition"
          title="Clear Conversation Memory"
        >
          <Trash2 className="w-3.5 h-3.5" /> Reset Memory
        </button>
      </div>

      {/* Quick Chips */}
      <div className="flex items-center gap-2 px-4 py-2 bg-[#060A12]/60 border-b border-[#00E5FF]/10 overflow-x-auto">
        <Sparkles className="w-3.5 h-3.5 text-[#FFB300] shrink-0" />
        {quickPrompts.map((q) => (
          <button
            key={q}
            onClick={() => setInput(q)}
            className="text-[11px] whitespace-nowrap px-2.5 py-1 rounded bg-[#00E5FF]/10 hover:bg-[#00E5FF]/20 text-[#8AB4F8] border border-[#00E5FF]/25 transition"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {mergedMessages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-gray-400 space-y-2">
            <Cpu className="w-10 h-10 text-[#00E5FF]/50 animate-pulse" />
            <div className="text-sm font-semibold text-[#00E5FF]">JARVIS 2.0 NEURAL CORE READY</div>
            <p className="text-xs max-w-md text-gray-400">
              Enter a conversational query, coding task, OS automation command, or voice instruction below.
            </p>
          </div>
        ) : (
          mergedMessages.map((m, idx) => {
            const isUser = m.role === "user" || m.sender === "USER";
            const text = m.content || m.text || "";
            return (
              <div
                key={m.id || idx}
                className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed border ${
                    isUser
                      ? "bg-[#00E5FF]/15 border-[#00E5FF]/50 text-white"
                      : "bg-[#060A12]/95 border-[#FFB300]/40 text-[#E2F1FF]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-4 mb-1 text-[10px] uppercase tracking-wider opacity-75">
                    <span className={isUser ? "text-[#00E5FF] font-bold" : "text-[#FFB300] font-bold"}>
                      {isUser ? "OPERATOR" : "JARVIS"}
                    </span>
                    <div className="flex items-center gap-2 font-mono">
                      {m.meta?.provider && (
                        <span className="px-1.5 py-0.2 bg-[#00E5FF]/15 text-[#00E5FF] rounded">
                          {m.meta.provider}
                          {m.meta.model ? `:${m.meta.model}` : ""}
                        </span>
                      )}
                      {m.meta?.latency_ms ? <span>{m.meta.latency_ms}ms</span> : null}
                      {m.timestamp && <span>{m.timestamp}</span>}
                    </div>
                  </div>
                  <div>{text}</div>
                </div>
              </div>
            );
          })
        )}

        {loading && (
          <div className="flex items-center gap-2 text-xs text-[#00E5FF] font-mono px-2 animate-pulse">
            <span>[JARVIS] Processing neural response...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input Bar */}
      <form
        onSubmit={handleSubmit}
        className="p-3 bg-[#060A12] border-t border-[#00E5FF]/30 flex items-center gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Transmit command or query to JARVIS..."
          className="flex-1 bg-[#0B1320] border border-[#00E5FF]/40 rounded px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-[#00E5FF]"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-5 py-2.5 bg-[#00E5FF]/20 hover:bg-[#00E5FF]/35 border border-[#00E5FF] text-[#00E5FF] font-bold text-xs uppercase tracking-wider rounded flex items-center gap-2 transition disabled:opacity-50"
        >
          <Send className="w-4 h-4" /> SEND
        </button>
      </form>
    </div>
  );
};

export default CommandStream;
