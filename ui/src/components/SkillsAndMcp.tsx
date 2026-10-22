import React, { useState, useEffect, useCallback } from 'react';
import {
  Zap, Plus, Trash2, Play, BookOpen,
  Server, Settings, ChevronDown, ChevronRight, Wrench,
} from 'lucide-react';

/* ── Types ────────────────────────────────────────────────────────── */
interface Skill {
  id: string;
  name: string;
  trigger_phrases?: string[];
  trigger?: string;
  steps: (string | { command: string })[];
}

interface McpServer {
  name: string;
  command?: string;
  url?: string;
  transport?: string;
  tools?: string[];
}

interface McpTool {
  server: string;
  name: string;
  description?: string;
}

interface SkillsAndMcpProps {
  apiBase: string;
}

/* ── Component ────────────────────────────────────────────────────── */
export const SkillsAndMcp: React.FC<SkillsAndMcpProps> = ({ apiBase }) => {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [mcpTools, setMcpTools] = useState<McpTool[]>([]);
  const [runResult, setRunResult] = useState<Record<string, string>>({});

  // Teach Mode state
  const [isTeaching, setIsTeaching] = useState(false);
  const [teachName, setTeachName] = useState('');
  const [teachTrigger, setTeachTrigger] = useState('');

  // New skill form
  const [showNewSkill, setShowNewSkill] = useState(false);
  const [newSkillName, setNewSkillName] = useState('');
  const [newSkillTrigger, setNewSkillTrigger] = useState('');
  const [newSkillSteps, setNewSkillSteps] = useState('');

  // New MCP server form
  const [showNewMcp, setShowNewMcp] = useState(false);
  const [newMcpName, setNewMcpName] = useState('');
  const [newMcpCommand, setNewMcpCommand] = useState('');
  const [newMcpUrl, setNewMcpUrl] = useState('');

  // MCP expanded
  const [mcpExpanded, setMcpExpanded] = useState(false);

  const fetchSkills = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/skills`);
      const data = await res.json();
      setSkills(Array.isArray(data) ? data : data.skills || []);
    } catch { /* offline */ }
  }, [apiBase]);

  const fetchMcp = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/mcp`);
      const data = await res.json();
      const rawServers = data.servers || {};
      const serversList = Array.isArray(rawServers)
        ? rawServers
        : Object.entries(rawServers).map(([name, conf]: [string, any]) => ({ name, ...conf }));
      setMcpServers(serversList);
      setMcpTools(data.tools || []);
    } catch { /* offline */ }
  }, [apiBase]);

  const fetchTeachStatus = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/skills/teach/status`);
      const data = await res.json();
      setIsTeaching(Boolean(data.is_teaching));
    } catch { /* offline */ }
  }, [apiBase]);

  useEffect(() => {
    fetchSkills();
    fetchMcp();
    fetchTeachStatus();
    const interval = setInterval(fetchTeachStatus, 3000);
    return () => clearInterval(interval);
  }, [fetchSkills, fetchMcp, fetchTeachStatus]);

  /* ── Teach Mode Actions ─────────────────────────────────────────── */
  const startTeachMode = async () => {
    if (!teachName.trim()) return;
    const triggers = teachTrigger
      ? teachTrigger.split(',').map((t) => t.trim().toLowerCase()).filter(Boolean)
      : [teachName.trim().toLowerCase()];
    await fetch(`${apiBase}/api/skills/teach/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: teachName.trim(), trigger_phrases: triggers }),
    });
    setIsTeaching(true);
  };

  const stopTeachMode = async (save: boolean = true) => {
    await fetch(`${apiBase}/api/skills/teach/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ save }),
    });
    setIsTeaching(false);
    setTeachName('');
    setTeachTrigger('');
    fetchSkills();
  };

  /* ── Skills CRUD ────────────────────────────────────────────────── */
  const addSkill = async () => {
    const steps: string[] = newSkillSteps
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    if (!newSkillName.trim() || steps.length === 0) return;
    const triggers = newSkillTrigger
      ? newSkillTrigger.split(',').map((t) => t.trim().toLowerCase()).filter(Boolean)
      : [newSkillName.trim().toLowerCase()];
    await fetch(`${apiBase}/api/skills`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newSkillName.trim(),
        trigger_phrases: triggers,
        steps,
      }),
    });
    setNewSkillName(''); setNewSkillTrigger(''); setNewSkillSteps('');
    setShowNewSkill(false);
    fetchSkills();
  };

  const runSkill = async (id: string) => {
    try {
      const res = await fetch(`${apiBase}/api/skills/${id}/run`, { method: 'POST' });
      const data = await res.json();
      setRunResult((prev) => ({ ...prev, [id]: data.ok !== false ? 'Executed ✓' : 'Error' }));
      setTimeout(() => setRunResult((prev) => ({ ...prev, [id]: '' })), 3000);
    } catch {
      setRunResult((prev) => ({ ...prev, [id]: 'Network error' }));
    }
  };

  const deleteSkill = async (id: string) => {
    await fetch(`${apiBase}/api/skills/${id}`, { method: 'DELETE' });
    fetchSkills();
  };

  /* ── MCP CRUD ───────────────────────────────────────────────────── */
  const addMcpServer = async () => {
    if (!newMcpName.trim()) return;
    const config: Record<string, string> = {};
    if (newMcpCommand.trim()) config.command = newMcpCommand;
    if (newMcpUrl.trim()) config.url = newMcpUrl;
    await fetch(`${apiBase}/api/mcp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newMcpName, config }),
    });
    setNewMcpName(''); setNewMcpCommand(''); setNewMcpUrl('');
    setShowNewMcp(false);
    fetchMcp();
  };

  const deleteMcpServer = async (name: string) => {
    await fetch(`${apiBase}/api/mcp/${name}`, { method: 'DELETE' });
    fetchMcp();
  };

  const inputClasses = 'bg-void/60 border border-cyber text-ice text-xs px-3 py-2 rounded focus:border-cyan-arc focus:outline-none w-full font-mono';

  return (
    <div className="flex-1 flex flex-col h-full bg-void/30 p-4 space-y-4 overflow-y-auto">
      {/* ── Teach Mode Recorder Card / Banner ──────────────────────── */}
      {isTeaching ? (
        <div className="bg-gold-reactor/10 border-2 border-gold-reactor rounded p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-pulse-glow shadow-gold-glow">
          <div className="flex items-center space-x-3">
            <div className="w-3 h-3 rounded-full bg-gold-reactor animate-ping" />
            <div>
              <div className="font-hud text-xs font-bold tracking-wider text-gold-reactor">
                TEACH MODE ACTIVE — Any command you say or type is being recorded
              </div>
              <div className="text-[11px] text-steel font-mono mt-0.5">
                Recording routine: <span className="text-ice font-bold">{teachName || 'Custom Routine'}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => stopTeachMode(false)}
              className="px-3 py-1.5 rounded border border-crimson/50 text-crimson text-xs hover:bg-crimson/10 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => stopTeachMode(true)}
              className="px-4 py-1.5 rounded bg-gold-reactor text-void font-bold text-xs hover:bg-yellow-400 transition-colors"
            >
              Stop & Save Routine
            </button>
          </div>
        </div>
      ) : (
        <div className="hud-panel hud-chamfer-sm p-3 space-y-2 border-cyber/50">
          <div className="flex items-center space-x-2">
            <Zap size={16} className="text-gold-reactor" />
            <span className="font-hud text-xs font-bold tracking-wider text-ice">TEACH MODE RECORDER</span>
            <span className="text-[10px] text-steel">(Record multi-step routines live by talking or typing)</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              className={inputClasses}
              placeholder="New Routine Name (e.g. Morning Briefing)"
              value={teachName}
              onChange={(e) => setTeachName(e.target.value)}
            />
            <input
              className={inputClasses}
              placeholder="Voice trigger phrase (e.g. start morning briefing)"
              value={teachTrigger}
              onChange={(e) => setTeachTrigger(e.target.value)}
            />
          </div>
          <div className="flex justify-end pt-1">
            <button
              onClick={startTeachMode}
              disabled={!teachName.trim()}
              className="px-3 py-1.5 rounded bg-gold-reactor/15 border border-gold-reactor/40 text-xs font-hud font-bold tracking-wider text-gold-reactor hover:bg-gold-reactor/25 transition-colors disabled:opacity-40"
            >
              Start Recording (Teach Mode)
            </button>
          </div>
        </div>
      )}

      {/* ── Skills Section ────────────────────────────────────────── */}
      <div className="hud-panel hud-chamfer-sm p-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Zap size={16} className="text-gold-reactor" />
            <span className="font-hud text-xs font-bold tracking-wider text-ice">VOICE MACRO SKILLS</span>
            <span className="text-[10px] text-steel">({skills.length})</span>
          </div>
          <button
            onClick={() => setShowNewSkill(!showNewSkill)}
            className="flex items-center space-x-1 text-xs px-2 py-1 rounded border border-cyber text-steel hover:text-cyan-arc hover:border-cyan-arc transition-colors"
          >
            <Plus size={12} /> <span>New Skill</span>
          </button>
        </div>

        {/* New skill form */}
        {showNewSkill && (
          <div className="bg-void/40 border border-cyber/50 rounded p-3 space-y-2">
            <input className={inputClasses} placeholder="Skill Name (e.g. Morning Routine)" value={newSkillName} onChange={(e) => setNewSkillName(e.target.value)} />
            <input className={inputClasses} placeholder="Voice trigger phrase (optional, comma-separated)" value={newSkillTrigger} onChange={(e) => setNewSkillTrigger(e.target.value)} />
            <textarea
              className={`${inputClasses} h-20 resize-none`}
              placeholder="Commands (one per line):&#10;open spotify&#10;set volume to 30&#10;what is the weather"
              value={newSkillSteps}
              onChange={(e) => setNewSkillSteps(e.target.value)}
            />
            <div className="flex items-center space-x-2">
              <button onClick={addSkill} className="px-3 py-1.5 rounded bg-cyan-arc/10 border border-cyan-arc/30 text-xs text-cyan-arc hover:bg-cyan-arc/20 transition-colors">
                Save Skill
              </button>
              <button onClick={() => setShowNewSkill(false)} className="px-3 py-1.5 text-xs text-steel hover:text-ice transition-colors">
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Skill cards */}
        <div className="space-y-2">
          {skills.map((skill) => {
            const triggerText = (skill.trigger_phrases && skill.trigger_phrases.length > 0)
              ? skill.trigger_phrases.join(', ')
              : (skill.trigger || '');
            const stepsList = Array.isArray(skill.steps) ? skill.steps : [];

            return (
              <div key={skill.id} className="flex items-center justify-between bg-void/40 border border-cyber/50 rounded p-2 group">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center space-x-2">
                    <BookOpen size={12} className="text-cyan-arc flex-shrink-0" />
                    <span className="text-xs text-ice font-bold truncate">{skill.name}</span>
                    {triggerText && (
                      <span className="text-[10px] text-steel bg-void/60 px-1.5 py-0.5 rounded truncate max-w-xs">"{triggerText}"</span>
                    )}
                  </div>
                  <div className="text-[10px] text-steel mt-0.5 pl-5">
                    {stepsList.length} step{stepsList.length !== 1 ? 's' : ''}
                    {stepsList.slice(0, 2).map((s, i) => {
                      const cmdText = typeof s === 'string' ? s : (s && (s as any).command ? (s as any).command : String(s));
                      return <span key={i} className="ml-2 font-mono">→ {cmdText}</span>;
                    })}
                    {stepsList.length > 2 && <span className="ml-1">…</span>}
                  </div>
                </div>
                <div className="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {runResult[skill.id] && (
                    <span className="text-[10px] text-green-400 mr-1">{runResult[skill.id]}</span>
                  )}
                  <button onClick={() => runSkill(skill.id)} className="p-1 text-cyan-arc hover:text-ice" title="Run routine"><Play size={14} /></button>
                  <button onClick={() => deleteSkill(skill.id)} className="p-1 text-crimson hover:text-red-300" title="Delete routine"><Trash2 size={14} /></button>
                </div>
              </div>
            );
          })}
          {skills.length === 0 && (
            <div className="text-[11px] text-steel text-center py-4">No skills configured. Create one above or use Teach Mode via voice or button above.</div>
          )}
        </div>
      </div>

      {/* ── MCP Section ───────────────────────────────────────────── */}
      <div className="hud-panel hud-chamfer-sm p-3 space-y-3">
        <div className="flex items-center justify-between">
          <button onClick={() => setMcpExpanded(!mcpExpanded)} className="flex items-center space-x-2">
            {mcpExpanded ? <ChevronDown size={14} className="text-cyan-arc" /> : <ChevronRight size={14} className="text-steel" />}
            <Server size={16} className="text-cyan-arc" />
            <span className="font-hud text-xs font-bold tracking-wider text-ice">MCP SERVER MANAGER</span>
            <span className="text-[10px] text-steel">({mcpServers.length} server{mcpServers.length !== 1 ? 's' : ''}, {mcpTools.length} tool{mcpTools.length !== 1 ? 's' : ''})</span>
          </button>
          <button
            onClick={() => setShowNewMcp(!showNewMcp)}
            className="flex items-center space-x-1 text-xs px-2 py-1 rounded border border-cyber text-steel hover:text-cyan-arc hover:border-cyan-arc transition-colors"
          >
            <Plus size={12} /> <span>Add Server</span>
          </button>
        </div>

        {showNewMcp && (
          <div className="bg-void/40 border border-cyber/50 rounded p-3 space-y-2">
            <input className={inputClasses} placeholder="Server Name" value={newMcpName} onChange={(e) => setNewMcpName(e.target.value)} />
            <input className={inputClasses} placeholder="Command (e.g. npx -y @mcp/server)" value={newMcpCommand} onChange={(e) => setNewMcpCommand(e.target.value)} />
            <input className={inputClasses} placeholder="URL (for HTTP transport)" value={newMcpUrl} onChange={(e) => setNewMcpUrl(e.target.value)} />
            <div className="flex items-center space-x-2">
              <button onClick={addMcpServer} className="px-3 py-1.5 rounded bg-cyan-arc/10 border border-cyan-arc/30 text-xs text-cyan-arc hover:bg-cyan-arc/20 transition-colors">
                Add Server
              </button>
              <button onClick={() => setShowNewMcp(false)} className="px-3 py-1.5 text-xs text-steel hover:text-ice transition-colors">Cancel</button>
            </div>
          </div>
        )}

        {mcpExpanded && (
          <div className="space-y-2">
            {mcpServers.map((srv) => (
              <div key={srv.name} className="bg-void/40 border border-cyber/50 rounded p-2 space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Settings size={12} className="text-gold-reactor" />
                    <span className="text-xs text-ice font-bold">{srv.name}</span>
                    <span className="text-[10px] text-steel font-mono">{srv.transport || 'stdio'}</span>
                  </div>
                  <button onClick={() => deleteMcpServer(srv.name)} className="text-crimson hover:text-red-300"><Trash2 size={12} /></button>
                </div>
                {srv.command && <div className="text-[10px] text-steel font-mono pl-5">{srv.command}</div>}
                {srv.url && <div className="text-[10px] text-steel font-mono pl-5">{srv.url}</div>}
                {srv.tools && srv.tools.length > 0 && (
                  <div className="text-[10px] text-steel pl-5">
                    Tools: {srv.tools.slice(0, 5).join(', ')}{srv.tools.length > 5 ? ` +${srv.tools.length - 5} more` : ''}
                  </div>
                )}
              </div>
            ))}
            {mcpServers.length === 0 && (
              <div className="text-[11px] text-steel text-center py-3">No MCP servers configured.</div>
            )}

            {mcpTools.length > 0 && (
              <div className="mt-2">
                <div className="flex items-center space-x-1 mb-1">
                  <Wrench size={12} className="text-gold-reactor" />
                  <span className="text-[10px] font-hud tracking-wider text-steel">DISCOVERED TOOLS</span>
                </div>
                <div className="grid grid-cols-2 gap-1">
                  {mcpTools.slice(0, 12).map((tool, i) => (
                    <div key={i} className="text-[10px] text-steel bg-void/40 px-2 py-1 rounded font-mono truncate">
                      <span className="text-cyan-arc">{tool.server}</span>:{tool.name}
                    </div>
                  ))}
                </div>
                {mcpTools.length > 12 && <div className="text-[10px] text-steel text-center mt-1">+{mcpTools.length - 12} more tools</div>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default SkillsAndMcp;
