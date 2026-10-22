import React, { useState, useEffect, useRef } from 'react';
import { ShieldAlert, CheckCircle2, XCircle, Clock, AlertTriangle } from 'lucide-react';

/* ── Types ────────────────────────────────────────────────────────── */
export interface ApprovalRequest {
  request_id: string;
  action_type: string;
  description: string;
  preview?: string;
  timeout_seconds?: number;
  timeout_sec?: number;
}

interface ApprovalModalProps {
  request: ApprovalRequest | null;
  apiBase: string;
  onDismiss: () => void;
}

/* ── Component ────────────────────────────────────────────────────── */
export const ApprovalModal: React.FC<ApprovalModalProps> = ({ request, apiBase, onDismiss }) => {
  const [countdown, setCountdown] = useState(0);
  const [responding, setResponding] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  const totalTimeout = request ? (request.timeout_sec || request.timeout_seconds || 15) : 15;

  useEffect(() => {
    if (!request) return;
    const timeout = request.timeout_sec || request.timeout_seconds || 15;
    setCountdown(timeout);
    setResponding(false);

    timerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [request]);

  const respond = async (approved: boolean) => {
    if (!request || responding) return;
    setResponding(true);
    try {
      await fetch(`${apiBase}/api/approval/${request.request_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
      });
    } catch { /* network error handled gracefully */ }
    onDismiss();
  };

  if (!request) return null;

  const progressPct = totalTimeout > 0 ? (countdown / totalTimeout) * 100 : 100;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-void/80 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative w-full max-w-md mx-4 hud-panel hud-chamfer p-0 border-crimson/50 shadow-crimson-glow animate-pulse-glow">
        {/* Countdown bar */}
        <div className="h-1 bg-void/60 rounded-t overflow-hidden">
          <div
            className="h-full transition-all duration-1000 ease-linear"
            style={{
              width: `${progressPct}%`,
              background: countdown > 10
                ? 'linear-gradient(90deg, #00E5FF, #00E5FF)'
                : countdown > 5
                ? 'linear-gradient(90deg, #FFB300, #FFB300)'
                : 'linear-gradient(90deg, #FF3B5C, #FF3B5C)',
            }}
          />
        </div>

        <div className="p-5 space-y-4">
          {/* Header */}
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-full bg-crimson/10 border border-crimson/30">
              <ShieldAlert size={22} className="text-crimson" />
            </div>
            <div>
              <h3 className="font-hud text-sm font-bold tracking-wider text-crimson glow-crimson">
                SAFETY APPROVAL REQUIRED
              </h3>
              <div className="flex items-center space-x-2 mt-0.5">
                <AlertTriangle size={12} className="text-gold-reactor" />
                <span className="text-[11px] text-gold-reactor font-mono">{request.action_type.toUpperCase()}</span>
              </div>
            </div>
          </div>

          {/* Description */}
          <div className="bg-void/60 border border-cyber rounded p-3">
            <p className="text-xs text-ice leading-relaxed">{request.description}</p>
          </div>

          {/* Code/Command Preview */}
          {request.preview && (
            <div className="bg-void/80 border border-cyber/50 rounded p-3 max-h-32 overflow-y-auto">
              <pre className="text-[11px] font-mono text-steel whitespace-pre-wrap break-all">{request.preview}</pre>
            </div>
          )}

          {/* Countdown */}
          <div className="flex items-center justify-center space-x-2">
            <Clock size={14} className={countdown <= 5 ? 'text-crimson' : 'text-steel'} />
            <span className={`text-sm font-mono ${countdown <= 5 ? 'text-crimson glow-crimson' : 'text-steel'}`}>
              {countdown}s remaining
            </span>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center space-x-3">
            <button
              onClick={() => respond(false)}
              disabled={responding}
              className="flex-1 flex items-center justify-center space-x-2 py-2.5 rounded border border-crimson/50 bg-crimson/5 text-crimson text-sm font-hud tracking-wider hover:bg-crimson/15 transition-colors disabled:opacity-50"
            >
              <XCircle size={16} />
              <span>DENY</span>
            </button>
            <button
              onClick={() => respond(true)}
              disabled={responding}
              className="flex-1 flex items-center justify-center space-x-2 py-2.5 rounded border border-cyan-arc/50 bg-cyan-arc/5 text-cyan-arc text-sm font-hud tracking-wider hover:bg-cyan-arc/15 transition-colors disabled:opacity-50"
            >
              <CheckCircle2 size={16} />
              <span>APPROVE</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ApprovalModal;
