import React, { useState } from 'react';
import {
  Calendar,
  Clock,
  Video,
  PhoneOff,
  Plus,
  FileText,
  ChevronDown,
  ChevronRight,
  MessageSquareQuote,
  Globe,
  Upload,
  Copy,
  CheckCircle2,
  AlertCircle,
  Play,
} from 'lucide-react';

export interface MeetingItem {
  id: string;
  title: string;
  platform?: string;
  meeting_url: string;
  start_time: string;
  end_time?: string;
  auto_leave?: boolean;
  status?: string;
}

export interface SummaryItem {
  id: string;
  title: string;
  date: string;
  captions_count: number;
  summary: string;
}

export interface CaptionItem {
  text: string;
  timestamp: string;
  platform: string;
}

interface MeetingHubProps {
  meetings: MeetingItem[];
  summaries: SummaryItem[];
  liveCaptions: CaptionItem[];
  currentMeeting: Record<string, any> | null;
  onAddMeeting: (meeting: Partial<MeetingItem>) => void;
  onDeleteMeeting: (id: string) => void;
  onJoinMeeting: (url: string, title?: string, id?: string) => void;
  onLeaveMeeting: () => void;
  apiBase?: string;
}

export const MeetingHub: React.FC<MeetingHubProps> = ({
  meetings,
  summaries,
  liveCaptions,
  currentMeeting,
  onAddMeeting,
  onDeleteMeeting,
  onJoinMeeting,
  onLeaveMeeting,
  apiBase,
}) => {
  const getDefaultTime = () => {
    const d = new Date(Date.now() + 5 * 60 * 1000);
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const [newTitle, setNewTitle] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [newTime, setNewTime] = useState(getDefaultTime());
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [instantUrl, setInstantUrl] = useState('');
  const [expandedSummary, setExpandedSummary] = useState<string | null>(null);

  // Setup button state
  const [setupLoading, setSetupLoading] = useState(false);
  const [setupMessage, setSetupMessage] = useState<string | null>(null);

  // Bulk import/export state
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkJson, setBulkJson] = useState('');
  const [bulkStatus, setBulkStatus] = useState<string | null>(null);

  const baseUrl = apiBase || window.location.origin;

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle || !newUrl) return;

    const startDate = new Date(newTime || Date.now());
    const endDate = new Date(startDate.getTime() + (durationMinutes || 60) * 60 * 1000);

    onAddMeeting({
      title: newTitle,
      meeting_url: newUrl,
      start_time: startDate.toISOString(),
      end_time: endDate.toISOString(),
      platform: newUrl.includes('google.com') ? 'google_meet' : 'teams',
      auto_leave: true,
      status: 'pending',
    });

    setNewTitle('');
    setNewUrl('');
    setNewTime(getDefaultTime());
    setDurationMinutes(60);
  };

  const handleInstantJoin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!instantUrl.trim()) return;
    onJoinMeeting(instantUrl.trim(), 'Ad-hoc Call');
    setInstantUrl('');
  };

  const handleAccountSetup = async () => {
    setSetupLoading(true);
    setSetupMessage(null);
    try {
      const res = await fetch(`${baseUrl}/api/meetings/setup`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        setSetupMessage('Chrome profile launched! Sign in to Google & Teams, then close the window.');
      } else {
        setSetupMessage('Failed to launch browser setup.');
      }
    } catch {
      setSetupMessage('Error contacting server for account setup.');
    } finally {
      setSetupLoading(false);
      setTimeout(() => setSetupMessage(null), 7000);
    }
  };

  const handleBulkImport = async () => {
    if (!bulkJson.trim()) return;
    try {
      const parsed = JSON.parse(bulkJson);
      const res = await fetch(`${baseUrl}/api/meetings/bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      });
      const data = await res.json();
      if (data.ok) {
        setBulkStatus(`Successfully imported ${data.count} meeting(s)!`);
        setBulkJson('');
        // Refresh by triggering a state fetch or refetch via parent
        const refreshRes = await fetch(`${baseUrl}/api/meetings`);
        const refreshData = await refreshRes.json();
        if (refreshData.meetings) {
          // Parent will update on polling or tab switch
        }
      } else {
        setBulkStatus('Bulk import rejected by server.');
      }
    } catch (err: any) {
      setBulkStatus(`JSON parse error: ${err.message || 'Invalid format'}`);
    }
    setTimeout(() => setBulkStatus(null), 5000);
  };

  const handleExportJson = () => {
    const jsonStr = JSON.stringify(meetings, null, 2);
    navigator.clipboard.writeText(jsonStr);
    setBulkStatus('Schedule copied to clipboard!');
    setTimeout(() => setBulkStatus(null), 4000);
  };

  const renderStatusBadge = (status?: string) => {
    const s = (status || 'pending').toLowerCase();
    if (s === 'active') {
      return (
        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-cyan-arc/20 text-cyan-arc border border-cyan-arc animate-pulse uppercase tracking-wider">
          ACTIVE
        </span>
      );
    }
    if (s === 'completed') {
      return (
        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-steel/20 text-steel border border-steel/30 uppercase tracking-wider">
          COMPLETED
        </span>
      );
    }
    if (s === 'cancelled') {
      return (
        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-crimson/20 text-crimson border border-crimson/30 uppercase tracking-wider">
          CANCELLED
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-amber-500/20 text-amber-400 border border-amber-500/30 uppercase tracking-wider">
        PENDING
      </span>
    );
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-void/30 p-4 space-y-4 overflow-y-auto font-mono text-xs">
      {/* Top Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyber/50 pb-3">
        <div className="flex items-center space-x-2">
          <Calendar className="text-cyan-arc" size={18} />
          <div>
            <div className="font-hud text-sm font-bold text-ice tracking-wider">MEETING ASSISTANT HUB</div>
            <div className="text-[10px] text-steel">Playwright Autonomous Telemetry & Closed Caption Engine</div>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={handleAccountSetup}
            disabled={setupLoading}
            title="Open Chrome profile to save Google Meet & MS Teams login sessions"
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-tactical hover:bg-tactical/80 text-ice border border-cyber hover:border-cyan-arc/60 rounded font-bold tracking-wider transition-all text-[11px]"
          >
            <Globe size={13} className="text-cyan-arc" />
            <span>{setupLoading ? 'OPENING...' : 'BROWSER ACCOUNT SETUP'}</span>
          </button>
        </div>
      </div>

      {setupMessage && (
        <div className="p-2.5 rounded bg-cyan-arc/10 border border-cyan-arc text-ice text-[11px] flex items-center space-x-2">
          <CheckCircle2 size={14} className="text-cyan-arc flex-shrink-0" />
          <span>{setupMessage}</span>
        </div>
      )}

      {/* Live Active Meeting Banner */}
      {currentMeeting ? (
        <div className="bg-cyan-arc/10 border border-cyan-arc p-3.5 rounded flex items-center justify-between hud-panel shadow-arc-glow">
          <div className="flex items-center space-x-3">
            <div className="w-3 h-3 rounded-full bg-cyan-arc animate-ping" />
            <div>
              <div className="font-hud text-sm font-bold text-ice tracking-wider">
                ACTIVE MEETING: {currentMeeting.title?.toUpperCase() || 'ONLINE CALL'}
              </div>
              <div className="text-[10px] text-steel">
                Connected via Playwright Attendant • Microphone Auto-Muted
              </div>
            </div>
          </div>
          <button
            onClick={onLeaveMeeting}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-crimson/20 hover:bg-crimson/30 text-crimson border border-crimson rounded font-bold tracking-wider transition-all"
          >
            <PhoneOff size={14} />
            <span>LEAVE CALL</span>
          </button>
        </div>
      ) : null}

      {/* Ad-Hoc Direct Instant Join Bar */}
      <div className="bg-tactical/80 border border-cyber p-2.5 rounded hud-panel">
        <form onSubmit={handleInstantJoin} className="flex items-center gap-2">
          <div className="flex items-center space-x-2 text-cyan-arc flex-shrink-0 pl-1">
            <Play size={13} fill="currentColor" />
            <span className="font-bold text-[11px] text-ice">INSTANT CALL:</span>
          </div>
          <input
            type="text"
            placeholder="Paste Google Meet or Teams link for immediate direct join..."
            value={instantUrl}
            onChange={(e) => setInstantUrl(e.target.value)}
            className="flex-1 bg-void/80 border border-cyber focus:border-cyan-arc text-ice px-3 py-1.5 rounded focus:outline-none text-[11px]"
          />
          <button
            type="submit"
            className="px-3.5 py-1.5 bg-cyan-arc/20 hover:bg-cyan-arc/30 text-cyan-arc border border-cyan-arc rounded font-bold tracking-wider transition-colors flex-shrink-0 text-[11px]"
          >
            INSTANT JOIN
          </button>
        </form>
      </div>

      {/* Main Grid: Schedule & Summaries */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left Column: Schedule & Quick-Add */}
        <div className="space-y-4">
          {/* Quick-Add Form */}
          <div className="bg-tactical border border-cyber p-3.5 rounded hud-panel space-y-3">
            <div className="flex items-center space-x-2 text-ice font-hud font-bold text-xs tracking-wider">
              <Plus size={14} className="text-cyan-arc" />
              <span>SCHEDULE NEW MEETING</span>
            </div>
            <form onSubmit={handleCreate} className="space-y-2">
              <input
                type="text"
                placeholder="Meeting Title (e.g. Sprint Planning)"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                className="w-full bg-void/80 border border-cyber focus:border-cyan-arc text-ice p-2 rounded focus:outline-none"
              />
              <input
                type="text"
                placeholder="Meeting URL (Google Meet or Teams link)"
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                className="w-full bg-void/80 border border-cyber focus:border-cyan-arc text-ice p-2 rounded focus:outline-none"
              />
              <div className="flex flex-wrap sm:flex-nowrap gap-2">
                <input
                  type="datetime-local"
                  value={newTime}
                  onChange={(e) => setNewTime(e.target.value)}
                  className="flex-1 bg-void/80 border border-cyber focus:border-cyan-arc text-ice p-2 rounded focus:outline-none text-[11px]"
                />
                <div className="flex items-center space-x-1.5 bg-void/80 border border-cyber px-2.5 py-1.5 rounded flex-shrink-0">
                  <Clock size={12} className="text-steel" />
                  <input
                    type="number"
                    min={5}
                    max={480}
                    step={5}
                    value={durationMinutes}
                    onChange={(e) => setDurationMinutes(Number(e.target.value) || 60)}
                    className="w-10 bg-transparent text-ice text-center focus:outline-none text-xs"
                    title="Duration in minutes"
                  />
                  <span className="text-[10px] text-steel">min</span>
                </div>
                <button
                  type="submit"
                  className="px-4 py-2 bg-cyan-arc/20 hover:bg-cyan-arc/30 text-cyan-arc border border-cyan-arc rounded font-bold tracking-wider transition-colors flex-shrink-0"
                >
                  SCHEDULE
                </button>
              </div>
            </form>
          </div>

          {/* Scheduled Meetings List */}
          <div className="bg-tactical border border-cyber p-3.5 rounded hud-panel space-y-3">
            <div className="flex items-center justify-between text-steel text-xs border-b border-cyber/50 pb-2">
              <span className="flex items-center space-x-1.5 font-hud font-bold text-ice">
                <Calendar size={13} className="text-cyan-arc" />
                <span>UPCOMING SCHEDULES</span>
              </span>
              <span>{meetings.length} REGISTERED</span>
            </div>

            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {meetings.length === 0 ? (
                <div className="text-center py-6 text-steel/60">No scheduled meetings.</div>
              ) : (
                meetings.map((m) => (
                  <div
                    key={m.id}
                    className="p-2.5 bg-void/70 border border-cyber rounded flex items-center justify-between hover:border-cyan-arc/50 transition-colors"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="text-ice font-bold">{m.title}</span>
                        {renderStatusBadge(m.status)}
                      </div>
                      <div className="text-[10px] text-steel flex items-center space-x-2">
                        <Clock size={10} />
                        <span>{new Date(m.start_time).toLocaleString()}</span>
                        <span>•</span>
                        <span className="uppercase text-cyan-arc">{m.platform || 'MEETING'}</span>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => onJoinMeeting(m.meeting_url, m.title, m.id)}
                        className="px-2.5 py-1 bg-cyan-arc/20 hover:bg-cyan-arc/30 text-cyan-arc border border-cyan-arc/50 rounded font-bold transition-colors"
                      >
                        JOIN
                      </button>
                      <button
                        onClick={() => onDeleteMeeting(m.id)}
                        className="px-2 py-1 text-steel hover:text-crimson transition-colors"
                        title="Delete meeting"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Live Captions & AI Post-Call Summaries */}
        <div className="space-y-4">
          {/* Live Captions Feed */}
          <div className="bg-tactical border border-cyber p-3.5 rounded hud-panel space-y-2">
            <div className="flex items-center justify-between text-steel text-xs border-b border-cyber/50 pb-2">
              <span className="flex items-center space-x-1.5 font-hud font-bold text-ice">
                <MessageSquareQuote size={13} className="text-cyan-arc" />
                <span>REAL-TIME DOM CAPTIONS</span>
              </span>
              <span>{liveCaptions.length} CAPTURED</span>
            </div>

            <div className="h-44 overflow-y-auto space-y-1.5 bg-void/80 p-2.5 rounded border border-cyber/40 text-[11px]">
              {liveCaptions.length === 0 ? (
                <div className="h-full flex items-center justify-center text-steel/40 text-center">
                  Captions stream live during Google Meet / Teams calls.
                </div>
              ) : (
                liveCaptions.map((c, i) => (
                  <div key={i} className="text-ice/90 leading-relaxed">
                    <span className="text-steel text-[9px] mr-1.5">[{c.timestamp}]</span>
                    <span>{c.text}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* AI Post-Call Summaries */}
          <div className="bg-tactical border border-cyber p-3.5 rounded hud-panel space-y-3">
            <div className="flex items-center justify-between text-steel text-xs border-b border-cyber/50 pb-2">
              <span className="flex items-center space-x-1.5 font-hud font-bold text-ice">
                <FileText size={13} className="text-gold-reactor" />
                <span>AI POST-CALL SUMMARIES & ACTION ITEMS</span>
              </span>
              <span>{summaries.length} SAVED</span>
            </div>

            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {summaries.length === 0 ? (
                <div className="text-center py-6 text-steel/60">No post-call summaries yet.</div>
              ) : (
                summaries.map((s) => {
                  const isExp = expandedSummary === s.id;
                  return (
                    <div
                      key={s.id}
                      className="p-2.5 bg-void/70 border border-cyber rounded space-y-1.5 transition-colors"
                    >
                      <div
                        onClick={() => setExpandedSummary(isExp ? null : s.id)}
                        className="flex items-center justify-between cursor-pointer hover:text-cyan-arc transition-colors"
                      >
                        <div className="flex items-center space-x-1.5">
                          {isExp ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <span className="font-bold text-ice">{s.title}</span>
                        </div>
                        <span className="text-[10px] text-steel">{s.date}</span>
                      </div>

                      {isExp && (
                        <div className="mt-2 pt-2 border-t border-cyber/50 text-[11px] text-ice/90 whitespace-pre-wrap leading-relaxed">
                          {s.summary}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Collapsible Bulk JSON Import / Export Section */}
      <div className="bg-tactical border border-cyber rounded hud-panel">
        <button
          onClick={() => setBulkOpen(!bulkOpen)}
          className="w-full p-3 flex items-center justify-between text-ice hover:text-cyan-arc transition-colors font-bold tracking-wider"
        >
          <div className="flex items-center space-x-2">
            <Upload size={14} className="text-cyan-arc" />
            <span>BULK JSON IMPORT / EXPORT TIMETABLE</span>
          </div>
          {bulkOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        {bulkOpen && (
          <div className="p-3.5 border-t border-cyber/50 space-y-3">
            <div className="text-[11px] text-steel">
              Paste a JSON array of meetings to bulk-schedule, or export your current schedule JSON:
            </div>
            <textarea
              value={bulkJson}
              onChange={(e) => setBulkJson(e.target.value)}
              placeholder={`[\n  {\n    "title": "Team Standup",\n    "meeting_url": "https://meet.google.com/abc-defg-hij",\n    "start_time": "2026-10-22T14:00:00",\n    "end_time": "2026-10-22T15:00:00"\n  }\n]`}
              className="w-full h-28 bg-void/80 border border-cyber focus:border-cyan-arc text-ice p-2.5 rounded focus:outline-none font-mono text-[11px]"
            />
            {bulkStatus && (
              <div className="text-[11px] text-cyan-arc flex items-center space-x-1.5">
                <CheckCircle2 size={13} />
                <span>{bulkStatus}</span>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleBulkImport}
                className="flex items-center space-x-1.5 px-3 py-1.5 bg-cyan-arc/20 hover:bg-cyan-arc/30 text-cyan-arc border border-cyan-arc rounded font-bold tracking-wider transition-colors"
              >
                <Upload size={13} />
                <span>IMPORT JSON</span>
              </button>
              <button
                onClick={handleExportJson}
                className="flex items-center space-x-1.5 px-3 py-1.5 bg-tactical hover:bg-tactical/80 text-ice border border-cyber rounded font-bold tracking-wider transition-colors"
              >
                <Copy size={13} />
                <span>EXPORT CURRENT SCHEDULE (COPY JSON)</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
