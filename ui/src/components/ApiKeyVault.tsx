import React, { useState, useEffect, useCallback } from 'react';
import {
  Key, Plus, Trash2, Eye, EyeOff, RefreshCw, Zap, ChevronDown, ChevronRight,
  Server, Shield, ShieldCheck, Globe, Cpu, Link2, CheckCircle2, XCircle,
} from 'lucide-react';

/* ── Types ────────────────────────────────────────────────────────── */
interface VaultProvider {
  keys: string[];
}

interface CustomEndpoint {
  id: string;
  name: string;
  base_url: string;
  api_key: string;
  model: string;
}

interface Roles {
  intent_router: { provider: string; model: string };
  qa_chat: { provider: string; model: string };
  vision_agent: { provider: string; model: string };
  offline_fallback: { provider: string; model: string };
}

interface VaultData {
  providers: Record<string, VaultProvider | CustomEndpoint[]>;
  roles: Roles;
  autonomous_trust_mode: boolean;
  workspace_path: string;
}

interface ApiKeyVaultProps {
  apiBase: string;
}

/* ── Provider metadata ────────────────────────────────────────────── */
const PROVIDERS = [
  { id: 'gemini', label: 'Gemini', icon: <Cpu size={16} /> },
  { id: 'groq', label: 'Groq', icon: <Zap size={16} /> },
  { id: 'anthropic', label: 'Anthropic', icon: <Shield size={16} /> },
  { id: 'openrouter', label: 'OpenRouter', icon: <Globe size={16} /> },
  { id: 'ollama', label: 'Ollama', icon: <Server size={16} /> },
  { id: 'openweathermap', label: 'OpenWeatherMap', icon: <Globe size={16} /> },
];

const ROLE_IDS = ['intent_router', 'qa_chat', 'vision_agent', 'offline_fallback'] as const;

/* ── Component ────────────────────────────────────────────────────── */
export const ApiKeyVault: React.FC<ApiKeyVaultProps> = ({ apiBase }) => {
  const [vault, setVault] = useState<VaultData | null>(null);
  const [reveal, setReveal] = useState(false);
  const [newKeys, setNewKeys] = useState<Record<string, string>>({});
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; msg: string }>>({});

  // Custom endpoint builder state
  const [ceExpanded, setCeExpanded] = useState(false);
  const [ceName, setCeName] = useState('');
  const [ceUrl, setCeUrl] = useState('');
  const [ceApiKey, setCeApiKey] = useState('');
  const [ceModel, setCeModel] = useState('');
  const [ceFetchedModels, setCeFetchedModels] = useState<string[]>([]);
  const [ceTestResult, setCeTestResult] = useState<string | null>(null);

  // Roles
  const [roles, setRoles] = useState<Roles | null>(null);
  const [trustMode, setTrustMode] = useState(false);

  const fetchVault = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/vault?reveal=${reveal}`);
      const data = await res.json();
      setVault(data);
      if (data.roles) setRoles(data.roles);
      if (typeof data.autonomous_trust_mode === 'boolean') setTrustMode(data.autonomous_trust_mode);
    } catch { /* offline */ }
  }, [apiBase, reveal]);

  useEffect(() => { fetchVault(); }, [fetchVault]);

  /* ── Key Management ─────────────────────────────────────────────── */
  const addKey = async (provider: string) => {
    const key = newKeys[provider]?.trim();
    if (!key) return;
    await fetch(`${apiBase}/api/vault/key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, key, action: 'add' }),
    });
    setNewKeys((prev) => ({ ...prev, [provider]: '' }));
    fetchVault();
  };

  const removeKey = async (provider: string, keyVal: string, keyIdx?: number) => {
    await fetch(`${apiBase}/api/vault/key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, key: keyVal, key_index: keyIdx, action: 'remove' }),
    });
    fetchVault();
  };

  const testConnection = async (provider: string) => {
    try {
      const res = await fetch(`${apiBase}/api/vault/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider }),
      });
      const data = await res.json();
      setTestResults((prev) => ({
        ...prev,
        [provider]: { ok: data.ok !== false, msg: data.error || 'Connected' },
      }));
    } catch {
      setTestResults((prev) => ({ ...prev, [provider]: { ok: false, msg: 'Network error' } }));
    }
  };

  /* ── Custom Endpoint ────────────────────────────────────────────── */
  const fetchModels = async () => {
    if (!ceUrl.trim()) return;
    try {
      const res = await fetch(`${apiBase}/api/vault/fetch-models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: ceUrl, api_key: ceApiKey }),
      });
      const data = await res.json();
      setCeFetchedModels(data.models || []);
    } catch {
      setCeFetchedModels([]);
    }
  };

  const testCustomEndpoint = async () => {
    try {
      const res = await fetch(`${apiBase}/api/vault/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: 'custom', base_url: ceUrl, api_key: ceApiKey, model: ceModel }),
      });
      const data = await res.json();
      setCeTestResult(data.ok !== false ? '✓ Connection successful' : `✗ ${data.error || 'Failed'}`);
    } catch {
      setCeTestResult('✗ Network error');
    }
  };

  const saveCustomEndpoint = async () => {
    const ep: CustomEndpoint = {
      id: `custom-${Date.now()}`,
      name: ceName || 'Custom Endpoint',
      base_url: ceUrl,
      api_key: ceApiKey,
      model: ceModel,
    };
    await fetch(`${apiBase}/api/vault/custom-endpoint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'add', endpoint: ep }),
    });
    setCeName(''); setCeUrl(''); setCeApiKey(''); setCeModel('');
    setCeFetchedModels([]); setCeTestResult(null);
    fetchVault();
  };

  const deleteCustomEndpoint = async (id: string) => {
    await fetch(`${apiBase}/api/vault/custom-endpoint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'delete', endpoint_id: id }),
    });
    fetchVault();
  };

  /* ── Roles ──────────────────────────────────────────────────────── */
  const updateRole = async (roleId: string, field: 'provider' | 'model', value: string) => {
    if (!roles) return;
    const updated = { ...roles, [roleId]: { ...roles[roleId as keyof Roles], [field]: value } };
    setRoles(updated);
    await fetch(`${apiBase}/api/vault/roles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roles: updated }),
    });
  };

  const handleProviderChange = async (roleId: string, newProvider: string) => {
    if (!roles) return;
    // Find default model for the new provider
    let defaultModel = '';
    const builtinModels = DEFAULT_MODELS_BY_PROVIDER[newProvider];
    if (builtinModels && builtinModels.length > 0) {
      defaultModel = builtinModels[0];
    } else {
      // Check if newProvider is a saved custom endpoint
      const eps = customEndpoints();
      const ep = eps.find((e) => e.name === newProvider || e.id === newProvider);
      if (ep && ep.model) {
        defaultModel = ep.model;
      }
    }
    const updated = { ...roles, [roleId]: { provider: newProvider, model: defaultModel } };
    setRoles(updated);
    await fetch(`${apiBase}/api/vault/roles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roles: updated }),
    });
  };

  const toggleTrustMode = async () => {
    const next = !trustMode;
    setTrustMode(next);
    await fetch(`${apiBase}/api/vault/roles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ autonomous_trust_mode: next }),
    });
  };

  /* ── Helpers ────────────────────────────────────────────────────── */
  interface KeyItem {
    display: string;
    raw: string;
    index: number;
  }

  const DEFAULT_MODELS_BY_PROVIDER: Record<string, string[]> = {
    gemini: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash'],
    groq: ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768', 'deepseek-r1-distill-llama-70b'],
    anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
    openrouter: ['google/gemini-2.0-flash-exp:free', 'meta-llama/llama-3.3-70b-instruct', 'anthropic/claude-3.5-sonnet'],
    ollama: ['llama3', 'mistral', 'qwen2.5-coder', 'deepseek-r1'],
  };

  const providerKeys = (provider: string): KeyItem[] => {
    if (!vault || !vault.providers) return [];
    const p: any = vault.providers[provider];
    if (!p || Array.isArray(p)) return [];
    const rawList: string[] = p.keys || [];
    const maskedList: string[] = p.keys_masked || rawList.map((k) => k.length > 8 ? `${k.slice(0, 4)}...${k.slice(-4)}` : '••••••••');
    const displayList = reveal ? rawList : (maskedList.length > 0 ? maskedList : rawList);
    return displayList.map((disp, idx) => ({
      display: disp,
      raw: rawList[idx] || disp,
      index: idx,
    }));
  };

  const customEndpoints = (): CustomEndpoint[] => {
    if (!vault || !vault.providers) return [];
    const ce = vault.providers.custom_endpoints;
    if (Array.isArray(ce)) return ce as CustomEndpoint[];
    return [];
  };

  const inputClasses = 'bg-void/60 border border-cyber text-ice text-xs px-3 py-2 rounded focus:border-cyan-arc focus:outline-none w-full font-mono';

  return (
    <div className="flex-1 flex flex-col h-full bg-void/30 p-4 space-y-4 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Key size={18} className="text-gold-reactor" />
          <span className="font-hud text-sm font-bold tracking-wider text-ice">API KEY VAULT</span>
        </div>
        <button
          onClick={() => { setReveal(!reveal); }}
          className="flex items-center space-x-1 text-xs text-steel hover:text-cyan-arc transition-colors"
        >
          {reveal ? <EyeOff size={14} /> : <Eye size={14} />}
          <span>{reveal ? 'Mask Keys' : 'Reveal Keys'}</span>
        </button>
      </div>

      {/* Provider Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {PROVIDERS.map(({ id, label, icon }) => {
          const keys = providerKeys(id);
          const test = testResults[id];
          return (
            <div key={id} className="hud-panel hud-chamfer-sm p-3 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  {icon}
                  <span className="font-hud text-xs font-bold tracking-wider text-cyan-arc">{label.toUpperCase()}</span>
                  <span className="text-[10px] text-steel">({keys.length} key{keys.length !== 1 ? 's' : ''})</span>
                </div>
                <button
                  onClick={() => testConnection(id)}
                  className="text-[10px] px-2 py-0.5 rounded border border-cyber text-steel hover:text-cyan-arc hover:border-cyan-arc transition-colors"
                >
                  Test
                </button>
              </div>

              {test && (
                <div className={`flex items-center space-x-1 text-[10px] ${test.ok ? 'text-green-400' : 'text-crimson'}`}>
                  {test.ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                  <span>{test.msg}</span>
                </div>
              )}

              {keys.map((k) => (
                <div key={k.index} className="flex items-center space-x-2">
                  <span className="flex-1 font-mono text-[11px] text-steel truncate">{k.display}</span>
                  <button onClick={() => removeKey(id, k.display, k.index)} className="text-crimson hover:text-red-300">
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}

              <div className="flex items-center space-x-2">
                <input
                  className={inputClasses}
                  placeholder={`Add ${label} key...`}
                  value={newKeys[id] || ''}
                  onChange={(e) => setNewKeys((prev) => ({ ...prev, [id]: e.target.value }))}
                  onKeyDown={(e) => e.key === 'Enter' && addKey(id)}
                />
                <button
                  onClick={() => addKey(id)}
                  className="p-1.5 rounded bg-cyber hover:bg-cyan-arc/20 text-cyan-arc transition-colors"
                >
                  <Plus size={14} />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Custom OpenAI-Compatible Endpoint Builder */}
      <div className="hud-panel hud-chamfer-sm p-3 space-y-3">
        <button
          onClick={() => setCeExpanded(!ceExpanded)}
          className="flex items-center space-x-2 w-full text-left"
        >
          {ceExpanded ? <ChevronDown size={14} className="text-cyan-arc" /> : <ChevronRight size={14} className="text-steel" />}
          <Link2 size={16} className="text-gold-reactor" />
          <span className="font-hud text-xs font-bold tracking-wider text-gold-reactor">CUSTOM OPENAI-COMPATIBLE ENDPOINT</span>
        </button>

        {ceExpanded && (
          <div className="space-y-2 pl-6">
            <input className={inputClasses} placeholder="Endpoint Name" value={ceName} onChange={(e) => setCeName(e.target.value)} />
            <input className={inputClasses} placeholder="Base URL (e.g. https://api.openai.com/v1)" value={ceUrl} onChange={(e) => setCeUrl(e.target.value)} />
            <input className={inputClasses} placeholder="API Key (optional for Ollama)" value={ceApiKey} onChange={(e) => setCeApiKey(e.target.value)} />

            <div className="flex items-center space-x-2">
              {ceFetchedModels.length > 0 ? (
                <select
                  className={`${inputClasses} cursor-pointer`}
                  value={ceModel}
                  onChange={(e) => setCeModel(e.target.value)}
                >
                  <option value="">Select model…</option>
                  {ceFetchedModels.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              ) : (
                <input className={inputClasses} placeholder="Model ID" value={ceModel} onChange={(e) => setCeModel(e.target.value)} />
              )}
              <button
                onClick={fetchModels}
                className="flex items-center space-x-1 whitespace-nowrap px-3 py-2 rounded border border-cyber text-xs text-steel hover:text-cyan-arc hover:border-cyan-arc transition-colors"
              >
                <RefreshCw size={12} /> <span>Fetch Models</span>
              </button>
            </div>

            {ceTestResult && (
              <div className={`text-[11px] ${ceTestResult.startsWith('✓') ? 'text-green-400' : 'text-crimson'}`}>{ceTestResult}</div>
            )}

            <div className="flex items-center space-x-2">
              <button onClick={testCustomEndpoint} className="px-3 py-1.5 rounded border border-cyber text-xs text-steel hover:text-cyan-arc hover:border-cyan-arc transition-colors">
                Test Endpoint
              </button>
              <button onClick={saveCustomEndpoint} className="px-3 py-1.5 rounded bg-cyan-arc/10 border border-cyan-arc/30 text-xs text-cyan-arc hover:bg-cyan-arc/20 transition-colors">
                Save Endpoint
              </button>
            </div>

            {/* Saved Custom Endpoints */}
            {customEndpoints().map((ep) => {
              const epTestKey = `ep-${ep.id}`;
              const epTest = testResults[epTestKey];
              return (
                <div key={ep.id} className="bg-void/40 border border-cyber/50 rounded p-2 text-[11px] text-steel space-y-1">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-ice font-bold">{ep.name}</span> — <span className="font-mono">{ep.base_url}</span>
                      {ep.model && <span className="ml-2 text-gold-reactor">[{ep.model}]</span>}
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={async () => {
                          try {
                            const res = await fetch(`${apiBase}/api/vault/test`, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ provider: ep.id, base_url: ep.base_url, api_key: ep.api_key, model: ep.model }),
                            });
                            const data = await res.json();
                            setTestResults((prev) => ({
                              ...prev,
                              [epTestKey]: { ok: data.ok !== false, msg: data.error || 'Connected' },
                            }));
                          } catch {
                            setTestResults((prev) => ({ ...prev, [epTestKey]: { ok: false, msg: 'Network error' } }));
                          }
                        }}
                        className="text-[10px] px-2 py-0.5 rounded border border-cyber text-steel hover:text-cyan-arc hover:border-cyan-arc transition-colors"
                      >
                        Test
                      </button>
                      <button onClick={() => deleteCustomEndpoint(ep.id)} className="text-crimson hover:text-red-300"><Trash2 size={12} /></button>
                    </div>
                  </div>
                  {epTest && (
                    <div className={`flex items-center space-x-1 text-[10px] ${epTest.ok ? 'text-green-400' : 'text-crimson'}`}>
                      {epTest.ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                      <span>{epTest.msg}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Role Router Matrix */}
      <div className="hud-panel hud-chamfer-sm p-3 space-y-3">
        <div className="flex items-center space-x-2">
          <Cpu size={16} className="text-cyan-arc" />
          <span className="font-hud text-xs font-bold tracking-wider text-ice">ROLE ROUTER MATRIX</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {ROLE_IDS.map((roleId) => {
            const role = roles?.[roleId] || { provider: 'gemini', model: 'gemini-2.5-flash' };
            const endpoints = customEndpoints();
            const providerOptions = [
              'gemini',
              'groq',
              'anthropic',
              'openrouter',
              'ollama',
              ...endpoints.map((ep) => ep.name || ep.id),
            ];
            const currentProvider = role.provider || 'gemini';
            const modelSuggestions = DEFAULT_MODELS_BY_PROVIDER[currentProvider] || [];
            const datalistId = `models-${roleId}`;

            return (
              <div key={roleId} className="bg-void/40 border border-cyber/50 rounded p-2.5 space-y-1.5">
                <span className="text-[10px] font-hud tracking-wider text-gold-reactor">
                  {roleId.toUpperCase().replace(/_/g, ' ')}
                </span>
                <div className="space-y-1">
                  <select
                    className={`${inputClasses} text-[11px] cursor-pointer`}
                    value={role.provider}
                    onChange={(e) => handleProviderChange(roleId, e.target.value)}
                  >
                    {providerOptions.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                  <input
                    list={datalistId}
                    className={`${inputClasses} text-[11px]`}
                    placeholder="Model ID (select or type)..."
                    value={role.model}
                    onChange={(e) => updateRole(roleId, 'model', e.target.value)}
                  />
                  <datalist id={datalistId}>
                    {modelSuggestions.map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                </div>
              </div>
            );
          })}
        </div>

        {/* Autonomous Trust Mode */}
        <div className="flex items-center justify-between bg-void/40 border border-cyber/50 rounded p-2">
          <div className="flex items-center space-x-2">
            {trustMode ? <ShieldCheck size={16} className="text-gold-reactor" /> : <Shield size={16} className="text-steel" />}
            <span className="text-xs text-ice">Autonomous Trust Mode</span>
            <span className="text-[10px] text-steel">(skip safety approval)</span>
          </div>
          <button
            onClick={toggleTrustMode}
            className={`relative w-10 h-5 rounded-full transition-colors ${trustMode ? 'bg-gold-reactor/40' : 'bg-cyber'}`}
          >
            <span className={`absolute top-0.5 w-4 h-4 rounded-full transition-all ${trustMode ? 'left-5 bg-gold-reactor' : 'left-0.5 bg-steel'}`} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ApiKeyVault;
