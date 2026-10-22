import React, { useState } from 'react';
import { Calendar, Clock, Video, PhoneOff, Plus, FileText, ChevronDown, ChevronRight, MessageSquareQuote } from 'lucide-react';

interface MeetingItem {
  id: string;
  title: string;
  platform?: string;
  meeting_url: string;
  start_time: string;
  end_time?: string;
  auto_leave?: boolean;
  status?: string;
}

interface SummaryItem {
  id: string;
  title: string;
  date: string;
  captions_count: number;
  summary: string;
}

interface CaptionItem {
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
  onJoinMeeting: (url: string, title: string) => void;
  onLeaveMeeting: () => void;
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
}) => {
  // Default newTime to 5 minutes from now in local YYYY-MM-DDTHH:mm format
  const getDefaultTime = () => {
    const d = new Date(Date.now() + 5 * 60 * 1000);
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const [newTitle, setNewTitle] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [newTime, setNewTime] = useState(getDefaultTime());
  const [expandedSummary, setExpandedSummary] = useState<string | null>(null);

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle || !newUrl) return;

    onAddMeeting({
      title: newTitle,
      meeting_url: newUrl,
      start_time: newTime || new Date().toISOString(),
      platform: newUrl.includes('google.com') ? 'google_meet' : 'teams',
      auto_leave: true,
      status: 'scheduled',
    });

    setNewTitle('');
    setNewUrl('');
    setNewTime('');
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-void/30 p-4 space-y-4 overflow-y-auto font-mono text-xs">
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
              <div className="flex space-x-2">
                <input
                  type="datetime-local"
                  value={newTime}
                  onChange={(e) => setNewTime(e.target.value)}
                  className="flex-1 bg-void/80 border border-cyber focus:border-cyan-arc text-ice p-2 rounded focus:outline-none text-[11px]"
                />
                <button
                  type="submit"
                  className="px-4 py-2 bg-cyan-arc/20 hover:bg-cyan-arc/30 text-cyan-arc border border-cyan-arc rounded font-bold tracking-wider transition-colors"
                >
                  ADD
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

            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {meetings.length === 0 ? (
                <div className="text-center py-6 text-steel/60">No scheduled meetings.</div>
              ) : (
                meetings.map((m) => (
                  <div
                    key={m.id}
                    className="p-2.5 bg-void/70 border border-cyber rounded flex items-center justify-between hover:border-cyan-arc/50 transition-colors"
                  >
                    <div>
                      <div className="text-ice font-bold">{m.title}</div>
                      <div className="text-[10px] text-steel flex items-center space-x-2 mt-0.5">
                        <Clock size={10} />
                        <span>{new Date(m.start_time).toLocaleString()}</span>
                        <span>•</span>
                        <span className="uppercase text-cyan-arc">{m.platform || 'MEETING'}</span>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => onJoinMeeting(m.meeting_url, m.title)}
                        className="px-2.5 py-1 bg-cyan-arc/20 hover:bg-cyan-arc/30 text-cyan-arc border border-cyan-arc/50 rounded font-bold transition-colors"
                      >
                        JOIN
                      </button>
                      <button
                        onClick={() => onDeleteMeeting(m.id)}
                        className="px-2 py-1 text-steel hover:text-crimson transition-colors"
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

            <div className="h-40 overflow-y-auto space-y-1.5 bg-void/80 p-2.5 rounded border border-cyber/40 text-[11px]">
              {liveCaptions.length === 0 ? (
                <div className="h-full flex items-center justify-center text-steel/40">
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
    </div>
  );
};
