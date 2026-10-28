import React, { useState, useEffect } from "react";
import { Key, Plus, Trash2, CheckCircle2, RefreshCw, Server, Shield, Zap, AlertCircle } from "lucide-react";

interface KeyEntry {
  id?: string;
  index: number;
  label?: string;
  key?: string;
  masked?: string;
  masked_key?: string;
  status?: string;
  is_active?: boolean;
  calls?: number;
  errors?: number;
  last_error?: string | null;
}

interface ProviderConfig {
  keys: KeyEntry[];
  active_index: number;
  default_model: string;
  models?: string[];
}

interface CustomEndpoint {
  id: string;
  name: string;
  base_url: string;
  api_key?: string;
  masked_key?: string;
  default_model: string;
  enabled: boolean;
}

export const ApiKeyVault: React.FC = () => {
  const [providers, setProviders] = useState<Record<string, ProviderConfig>>({});
  const [customEndpoints, setCustomEndpoints] = useState<CustomEndpoint[]>([]);
  const [roleMappings, setRoleMappings] = useState<Record<string, any>>({});
  const [selectedProvider, setSelectedProvider] = useState<string>("gemini");
  const [newKey, setNewKey] = useState<string>("");
  const [newLabel, setNewLabel] = useState<string>("");

  const [epName, setEpName] = useState<string>("");
  const [epUrl, setEpUrl] = useState<string>("http://127.0.0.1:8000/v1");
  const [epKey, setEpKey] = useState<string>("sk-local");
  const [epModel, setEpModel] = useState<string>("default");

  const [statusMsg, setStatusMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [testing, setTesting] = useState<boolean>(false);

  const applyVaultData = (data: any) => {
    const v = data?.vault || data || {};
    if (v.providers) setProviders(v.providers);
    if (Array.isArray(v.custom_endpoints)) setCustomEndpoints(v.custom_endpoints);
    if (v.role_mappings) setRoleMappings(v.role_mappings);
  };

  const fetchVault = async () => {
    try {
      const res = await fetch("/api/vault");
      const data = await res.json();
      applyVaultData(data);
    } catch (e) {
      setStatusMsg({ type: "err", text: `Failed to load Vault: ${e}` });
    }
  };

  useEffect(() => {
    fetchVault();
  }, []);

  const handleAddKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKey.trim()) {
      setStatusMsg({ type: "err", text: "Please paste a valid API key first." });
      return;
    }
    try {
      const res = await fetch("/api/vault/key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: selectedProvider,
          key: newKey.trim(),
          label: newLabel.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Failed to add key");
      applyVaultData(data);
      setNewKey("");
      setNewLabel("");
      setStatusMsg({
        type: "ok",
        text: `Added ${selectedProvider.toUpperCase()} API key to pool and bound unconfigured AI roles.`,
      });
    } catch (err: any) {
      setStatusMsg({ type: "err", text: err.message || "Error adding API key" });
    }
  };

  const handleRemoveKey = async (provider: string, index: number) => {
    try {
      const res = await fetch(`/api/vault/key/${provider}/${index}`, { method: "DELETE" });
      const data = await res.json();
      applyVaultData(data);
      setStatusMsg({ type: "ok", text: `Removed key #${index + 1} from ${provider.toUpperCase()}.` });
    } catch (err: any) {
      setStatusMsg({ type: "err", text: err.message || "Failed to remove key" });
    }
  };

  const handleSetActiveKey = async (provider: string, index: number) => {
    try {
      const res = await fetch("/api/vault/key/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, index }),
      });
      const data = await res.json();
      applyVaultData(data);
      setStatusMsg({ type: "ok", text: `Activated key #${index + 1} for ${provider.toUpperCase()}.` });
    } catch (err: any) {
      setStatusMsg({ type: "err", text: err.message || "Failed to activate key" });
    }
  };

  const handleAddEndpoint = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!epName.trim() || !epUrl.trim()) return;
    try {
      const res = await fetch("/api/vault/endpoint", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: epName.trim(),
          base_url: epUrl.trim(),
          api_key: epKey.trim() || "sk-local",
          default_model: epModel.trim() || "default",
          enabled: true,
        }),
      });
      const data = await res.json();
      applyVaultData(data);
      setEpName("");
      setStatusMsg({ type: "ok", text: `Custom endpoint '${epName}' saved.` });
    } catch (err: any) {
      setStatusMsg({ type: "err", text: err.message || "Failed to add endpoint" });
    }
  };

  const handleRemoveEndpoint = async (id: string) => {
    try {
      const res = await fetch(`/api/vault/endpoint/${encodeURIComponent(id)}`, { method: "DELETE" });
      const data = await res.json();
      applyVaultData(data);
    } catch (err: any) {
      setStatusMsg({ type: "err", text: err.message || "Failed to remove endpoint" });
    }
  };

  const handleRoleChange = async (role: string, provider: string, model?: string) => {
    try {
      const res = await fetch("/api/vault/role", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, provider, model }),
      });
      const data = await res.json();
      applyVaultData(data);
      setStatusMsg({ type: "ok", text: `Updated role '${role}' -> ${provider}` });
    } catch (err: any) {
      setStatusMsg({ type: "err", text: err.message || "Failed to update role" });
    }
  };

  const handleTestAIConnection = async () => {
    setTesting(true);
    setStatusMsg(null);
    try {
      const res = await fetch("/api/vault/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (data.success) {
        setStatusMsg({
          type: "ok",
          text: `AI Connection Verified [${data.provider} / ${data.model}] (${data.latency_ms}ms): "${data.reply}"`,
        });
      } else {
        setStatusMsg({
          type: "err",
          text: `AI Test Failed: ${data.error || data.reply || "No active key responded"}`,
        });
      }
      fetchVault();
    } catch (err: any) {
      setStatusMsg({ type: "err", text: `Connection test error: ${err.message}` });
    } finally {
      setTesting(false);
    }
  };

  const providerList = ["gemini", "groq", "openai", "anthropic"];
  const rolesList = [
    { id: "chat", label: "Primary Chat & Reasoning" },
    { id: "coding", label: "Tier 1 OS Code Synthesizer" },
    { id: "vision", label: "Tier 3 Set-of-Mark Vision" },
    { id: "summarizer", label: "Meeting Transcript Summarizer" },
  ];

  const allProviderOptions = [
    ...providerList.map((p) => ({ value: p, label: p.toUpperCase() })),
    ...customEndpoints.map((ep) => ({ value: `custom:${ep.id}`, label: `CUSTOM: ${ep.name}` })),
  ];

  return (
    <div className="space-y-6 text-[#E2F1FF]">
      {/* Status Banner & Live Connection Test */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-[#0B1320]/90 border border-[#00E5FF]/30 p-4 rounded">
        <div>
          <h2 className="text-lg font-bold tracking-wider text-[#00E5FF] flex items-center gap-2">
            <Shield className="w-5 h-5" /> MULTI-KEY API VAULT & FAILOVER ROUTER
          </h2>
          <p className="text-xs text-[#8AB4F8] mt-1">
            Add multiple keys per provider for automatic 429 rate-limit rotation and cross-provider failover.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleTestAIConnection}
            disabled={testing}
            className="flex items-center gap-2 px-4 py-2 bg-[#FFB300]/20 hover:bg-[#FFB300]/30 border border-[#FFB300] text-[#FFB300] text-xs font-bold tracking-wider rounded transition"
          >
            <Zap className="w-4 h-4" />
            {testing ? "TESTING AI..." : "TEST ACTIVE AI"}
          </button>
          <button
            onClick={fetchVault}
            className="p-2 bg-[#00E5FF]/10 hover:bg-[#00E5FF]/20 border border-[#00E5FF]/40 text-[#00E5FF] rounded"
            title="Refresh Vault"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {statusMsg && (
        <div
          className={`p-3 rounded border text-xs flex items-center gap-2 ${
            statusMsg.type === "ok"
              ? "bg-[#00E676]/10 border-[#00E676] text-[#00E676]"
              : "bg-[#FF1744]/15 border-[#FF1744] text-[#FF8A80]"
          }`}
        >
          {statusMsg.type === "ok" ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
          <span>{statusMsg.text}</span>
        </div>
      )}

      {/* Add API Key Form */}
      <form
        onSubmit={handleAddKey}
        className="bg-[#0B1320]/80 border border-[#00E5FF]/25 p-4 rounded space-y-3"
      >
        <div className="text-xs font-bold uppercase tracking-wider text-[#00E5FF] flex items-center gap-2">
          <Plus className="w-4 h-4" /> Add API Key to Provider Pool
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <select
            value={selectedProvider}
            onChange={(e) => setSelectedProvider(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/40 rounded px-3 py-2 text-sm text-[#00E5FF] focus:outline-none"
          >
            {providerList.map((p) => (
              <option key={p} value={p}>
                {p.toUpperCase()}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Label (optional, e.g. Personal Key 1)"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-2 text-sm text-white focus:border-[#00E5FF] focus:outline-none"
          />
          <input
            type="password"
            placeholder="Paste API Key (AIza..., gsk_..., sk-...)"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-2 text-sm text-white focus:border-[#00E5FF] focus:outline-none"
          />
          <button
            type="submit"
            className="bg-[#00E5FF]/20 hover:bg-[#00E5FF]/35 border border-[#00E5FF] text-[#00E5FF] font-bold text-xs uppercase tracking-wider rounded px-4 py-2 transition"
          >
            + Add Key
          </button>
        </div>
      </form>

      {/* Provider Key Pools Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {providerList.map((prov) => {
          const cfg = providers[prov] || { keys: [], active_index: 0, default_model: "" };
          const keys = Array.isArray(cfg.keys) ? cfg.keys : [];
          return (
            <div
              key={prov}
              className="bg-[#0B1320]/80 border border-[#00E5FF]/25 rounded p-4 flex flex-col justify-between space-y-3"
            >
              <div className="flex items-center justify-between border-b border-[#00E5FF]/20 pb-2">
                <div className="flex items-center gap-2">
                  <Key className="w-4 h-4 text-[#00E5FF]" />
                  <span className="font-bold text-sm tracking-wider uppercase text-[#00E5FF]">
                    {prov}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-[#00E5FF]/15 text-[#00E5FF]">
                    {keys.length} {keys.length === 1 ? "Key" : "Keys"}
                  </span>
                </div>
                <span className="text-xs text-[#8AB4F8] font-mono">{cfg.default_model}</span>
              </div>

              {keys.length === 0 ? (
                <div className="text-xs text-gray-400 italic py-4 text-center border border-dashed border-gray-700 rounded">
                  No keys in {prov.toUpperCase()} pool. Add a key above.
                </div>
              ) : (
                <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                  {keys.map((k, idx) => {
                    const isActive = idx === (cfg.active_index ?? 0) || k.is_active;
                    const maskedStr = k.masked || k.masked_key || k.key || "****";
                    const status = isActive ? "active" : k.status || "standby";
                    const badgeColor =
                      status === "active"
                        ? "bg-[#00E676]/20 text-[#00E676] border-[#00E676]"
                        : status === "cooldown"
                        ? "bg-[#FFB300]/20 text-[#FFB300] border-[#FFB300]"
                        : status === "exhausted"
                        ? "bg-[#FF1744]/20 text-[#FF1744] border-[#FF1744]"
                        : "bg-[#00E5FF]/10 text-[#8AB4F8] border-[#00E5FF]/30";

                    return (
                      <div
                        key={k.id || idx}
                        className={`flex items-center justify-between p-2.5 rounded border text-xs ${
                          isActive
                            ? "bg-[#00E5FF]/10 border-[#00E5FF]"
                            : "bg-[#060A12]/80 border-gray-800"
                        }`}
                      >
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-white">
                              {k.label || `${prov.toUpperCase()} Key #${idx + 1}`}
                            </span>
                            <span className={`px-1.5 py-0.2 text-[10px] uppercase border rounded ${badgeColor}`}>
                              {status}
                            </span>
                          </div>
                          <div className="font-mono text-[#00E5FF] text-xs">{maskedStr}</div>
                          <div className="text-[10px] text-gray-400">
                            Calls: {k.calls ?? 0} | Errors: {k.errors ?? 0}
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5">
                          {!isActive && (
                            <button
                              onClick={() => handleSetActiveKey(prov, idx)}
                              className="px-2 py-1 text-[10px] bg-[#00E5FF]/15 hover:bg-[#00E5FF]/30 text-[#00E5FF] border border-[#00E5FF]/40 rounded"
                            >
                              Use
                            </button>
                          )}
                          <button
                            onClick={() => handleRemoveKey(prov, idx)}
                            className="p-1.5 text-red-400 hover:bg-red-500/20 rounded"
                            title="Remove Key"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Role Mappings */}
      <div className="bg-[#0B1320]/80 border border-[#00E5FF]/25 rounded p-4 space-y-3">
        <div className="text-xs font-bold uppercase tracking-wider text-[#00E5FF]">
          Subsystem Role Dispatch Mapping
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {rolesList.map((r) => {
            const curr = roleMappings[r.id];
            const currProv = typeof curr === "object" ? curr?.provider || "gemini" : curr || "gemini";
            const currModel = typeof curr === "object" ? curr?.model || "" : "";
            return (
              <div
                key={r.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-[#060A12] border border-[#00E5FF]/20 p-3 rounded"
              >
                <span className="text-xs font-semibold text-white">{r.label}</span>
                <div className="flex items-center gap-2">
                  <select
                    value={currProv}
                    onChange={(e) => handleRoleChange(r.id, e.target.value)}
                    className="bg-[#0B1320] border border-[#00E5FF]/40 rounded px-2 py-1 text-xs text-[#00E5FF]"
                  >
                    {allProviderOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={currModel}
                    onChange={(e) => handleRoleChange(r.id, currProv, e.target.value)}
                    placeholder="Default model"
                    className="bg-[#0B1320] border border-[#00E5FF]/25 rounded px-2 py-1 text-xs text-gray-200 w-36 font-mono"
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Custom OpenAI-Compatible Endpoints (FREELLMAPI / Ollama / OpenRouter) */}
      <div className="bg-[#0B1320]/80 border border-[#00E5FF]/25 rounded p-4 space-y-4">
        <div className="text-xs font-bold uppercase tracking-wider text-[#FFB300] flex items-center gap-2">
          <Server className="w-4 h-4" /> Custom OpenAI-Compatible Endpoints (Ollama / FREELLMAPI / LM Studio)
        </div>
        <form onSubmit={handleAddEndpoint} className="grid grid-cols-1 md:grid-cols-5 gap-2">
          <input
            type="text"
            placeholder="Name (e.g. Local Ollama)"
            value={epName}
            onChange={(e) => setEpName(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-1.5 text-xs text-white"
          />
          <input
            type="text"
            placeholder="Base URL (http://127.0.0.1:11434/v1)"
            value={epUrl}
            onChange={(e) => setEpUrl(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-1.5 text-xs text-white font-mono"
          />
          <input
            type="password"
            placeholder="API Key (sk-local)"
            value={epKey}
            onChange={(e) => setEpKey(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-1.5 text-xs text-white"
          />
          <input
            type="text"
            placeholder="Model (e.g. qwen3.5:9b)"
            value={epModel}
            onChange={(e) => setEpModel(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-1.5 text-xs text-white font-mono"
          />
          <button
            type="submit"
            className="bg-[#FFB300]/20 hover:bg-[#FFB300]/30 border border-[#FFB300] text-[#FFB300] font-bold text-xs uppercase rounded px-3 py-1.5"
          >
            + Save Endpoint
          </button>
        </form>

        {customEndpoints.length > 0 && (
          <div className="space-y-2">
            {customEndpoints.map((ep) => (
              <div
                key={ep.id}
                className="flex items-center justify-between bg-[#060A12] border border-[#FFB300]/30 px-3 py-2 rounded text-xs"
              >
                <div>
                  <span className="font-bold text-[#FFB300]">{ep.name}</span>
                  <span className="ml-2 font-mono text-gray-400">{ep.base_url}</span>
                  <span className="ml-2 px-1.5 py-0.5 bg-[#00E5FF]/10 text-[#00E5FF] rounded font-mono">
                    model: {ep.default_model}
                  </span>
                </div>
                <button
                  onClick={() => handleRemoveEndpoint(ep.id)}
                  className="text-red-400 hover:bg-red-500/20 p-1 rounded"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ApiKeyVault;
