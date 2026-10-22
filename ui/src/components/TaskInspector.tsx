import React from 'react';
import { OctagonAlert, Play, CheckCircle2, AlertTriangle, Eye, Code, Terminal, Layers } from 'lucide-react';

export interface AgentStepItem {
  step: number;
  tier: 'code' | 'mcp' | 'vision_gui' | 'web';
  thought: string;
  action: string;
  status: 'running' | 'done' | 'error' | 'aborted';
  screenshot_b64?: string;
  output?: string;
}

interface TaskInspectorProps {
  steps: AgentStepItem[];
  onAbortAgent: () => void;
}

export const TaskInspector: React.FC<TaskInspectorProps> = ({ steps, onAbortAgent }) => {
  const currentStep = steps.length > 0 ? steps[steps.length - 1] : null;

  return (
    <div className="flex-1 flex flex-col h-full bg-void/30 p-4 space-y-4 overflow-hidden">
      {/* Top Controls Bar */}
      <div className="flex items-center justify-between bg-tactical border border-cyber p-3 rounded hud-panel">
        <div className="flex items-center space-x-2">
          <Layers size={18} className="text-cyan-arc" />
          <span className="font-hud text-sm font-bold tracking-wider text-ice">
            3-TIER OS AUTONOMY INSPECTOR
          </span>
          {currentStep && currentStep.status === 'running' && (
            <span className="flex items-center space-x-1 text-[10px] font-mono bg-cyan-arc/20 text-cyan-arc px-2 py-0.5 rounded border border-cyan-arc/40 animate-pulse">
              <Play size={10} />
              <span>ACTIVE STEP {currentStep.step}</span>
            </span>
          )}
        </div>

        {/* Emergency Abort Button */}
        <button
          onClick={onAbortAgent}
          className="flex items-center space-x-1.5 px-3 py-1.5 bg-crimson/20 hover:bg-crimson/30 text-crimson border border-crimson rounded text-xs font-mono font-bold tracking-wider transition-all shadow-crimson-glow"
          title="Instant Hardware/Software Kill-Switch"
        >
          <OctagonAlert size={15} />
          <span>[ESC] ABORT AGENT</span>
        </button>
      </div>

      {/* Main Grid: Steps Feed & Live Screenshot Viewer */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-4 min-h-0 overflow-hidden">
        {/* Left Column: Observe-Think-Act Step Log */}
        <div className="flex flex-col bg-tactical border border-cyber rounded p-3 overflow-hidden hud-panel">
          <div className="flex items-center justify-between pb-2 border-b border-cyber/50 text-xs font-mono text-steel">
            <span>EXECUTION PIPELINE</span>
            <span>{steps.length} EVENTS RECORDED</span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-3 mt-3 pr-1 font-mono text-xs">
            {steps.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-steel/50 select-none">
                <Terminal size={32} className="mb-2 opacity-50" />
                <span>No active autonomous OS tasks.</span>
                <span className="text-[10px] mt-1 text-steel/40">Tier 1-3 tasks will stream steps live here.</span>
              </div>
            ) : (
              steps.map((s, idx) => (
                <div
                  key={idx}
                  className={`p-2.5 rounded border text-xs space-y-1.5 ${
                    s.status === 'done'
                      ? 'bg-cyan-arc/5 border-cyan-arc/30'
                      : s.status === 'error' || s.status === 'aborted'
                      ? 'bg-crimson/10 border-crimson/40'
                      : 'bg-gold-reactor/5 border-gold-reactor/30'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-ice flex items-center space-x-1.5">
                      <span className="text-gold-reactor">STEP {s.step}</span>
                      <span className="text-steel">[{s.tier.toUpperCase()}]</span>
                    </span>
                    <span
                      className={`text-[9px] uppercase px-1.5 py-0.5 rounded font-bold ${
                        s.status === 'done'
                          ? 'text-cyan-arc bg-cyan-arc/20'
                          : s.status === 'error' || s.status === 'aborted'
                          ? 'text-crimson bg-crimson/20'
                          : 'text-gold-reactor bg-gold-reactor/20 animate-pulse'
                      }`}
                    >
                      {s.status}
                    </span>
                  </div>

                  <p className="text-steel text-[11px] leading-relaxed">{s.thought}</p>

                  {s.output && (
                    <pre className="bg-void/80 p-2 rounded text-[10px] text-ice/90 overflow-x-auto border border-cyber/40 whitespace-pre-wrap">
                      {s.output}
                    </pre>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Column: Set-of-Mark (SoM) Live Vision Preview */}
        <div className="flex flex-col bg-tactical border border-cyber rounded p-3 overflow-hidden hud-panel">
          <div className="flex items-center justify-between pb-2 border-b border-cyber/50 text-xs font-mono text-steel">
            <span className="flex items-center space-x-1">
              <Eye size={13} className="text-cyan-arc" />
              <span>SET-OF-MARK VISION GROUNDING</span>
            </span>
            <span>CYAN BOUNDING BOXES</span>
          </div>

          <div className="flex-1 flex items-center justify-center bg-void/80 rounded mt-3 p-2 overflow-hidden border border-cyber/40 relative">
            {currentStep?.screenshot_b64 ? (
              <img
                src={`data:image/png;base64,${currentStep.screenshot_b64}`}
                alt="Set-of-Mark Vision Grounding"
                className="max-w-full max-h-full object-contain rounded border border-cyan-arc/40 shadow-arc-glow"
              />
            ) : (
              <div className="flex flex-col items-center justify-center text-steel/50 select-none">
                <Eye size={36} className="mb-2 opacity-40 text-cyan-arc" />
                <span className="text-xs font-mono">No active visual snapshot.</span>
                <span className="text-[10px] mt-1 text-steel/40">Tier 3 vision grounding previews appear here.</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
