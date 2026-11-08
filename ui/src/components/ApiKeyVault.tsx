import React, { useState, useEffect } from "react";
import {
  Key,
  Plus,
  Trash2,
  CheckCircle2,
  RefreshCw,
  Server,
  Shield,
  Zap,
  AlertCircle,
  Cpu,
  HardDrive,
  Download,
  Power,
} from "lucide-react";

export interface LocalModelStatus {
  downloaded: boolean;
  runtime_available?: boolean;
  ready?: boolean;
  loaded: boolean;
  model_name: string;
  filename: string;
  size_mb: number;
  ram_usage_mb: number;
  threads: number;
  local_first_mode?: boolean;
  download_state?: {
    downloading: boolean;
    progress: number;
    downloaded_bytes: number;
    total_bytes: number;
    speed_mb_s: number;
    error?: string | null;
  };
}

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

export interface ApiKeyVaultProps {
  apiBase?: string;
}

export const ApiKeyVault: React.FC<ApiKeyVaultProps> = ({ apiBase = "" }) => {
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

  const [localModel, setLocalModel] = useState<LocalModelStatus | null>(null);
  const [localFirstMode, setLocalFirstMode] = useState<boolean>(true);
  const [downloadingLocal, setDownloadingLocal] = useState<boolean>(false);

  const applyVaultData = (data: any) => {
    const v = data?.vault || data || {};
    if (v.providers) setProviders(v.providers);
    if (Array.isArray(v.custom_endpoints)) setCustomEndpoints(v.custom_endpoints);
    if (v.role_mappings) setRoleMappings(v.role_mappings);
  };

  const fetchVault = async () => {
    try {
      const res = await fetch(`${apiBase}/api/vault`);
      const data = await res.json();
      applyVaultData(data);
      if (data?.local_first_mode !== undefined) {
        setLocalFirstMode(Boolean(data.local_first_mode));
      }
      if (data?.local_model) {
        setLocalModel(data.local_model);
      }
    } catch (e) {
      setStatusMsg({ type: "err", text: `Failed to load Vault: ${e}` });
    }
  };

  const fetchLocalModelStatus = async () => {
    try {
      const res = await fetch(`${apiBase}/api/vault/local-model`);
      if (res.ok) {
        const data = await res.json();
        setLocalModel(data);
        if (data.local_first_mode !== undefined) {
          setLocalFirstMode(Boolean(data.local_first_mode));
        }
        if (data.download_state?.downloading) {
          setDownloadingLocal(true);
        } else {
          setDownloadingLocal(false);
        }
      }
    } catch (e) {}
  };

  useEffect(() => {
    fetchVault();
    fetchLocalModelStatus();
  }, []);

  useEffect(() => {
    if (!downloadingLocal) return;
    const interval = setInterval(() => {
      fetchLocalModelStatus();
    }, 1500);
    return () => clearInterval(interval);
  }, [downloadingLocal]);

  const handleAddKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKey.trim()) {
      setStatusMsg({ type: "err", text: "Please paste a valid API key first." });
      return;
    }
    try {
      const res = await fetch(`${apiBase}/api/vault/key`, {
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
      const res = await fetch(`${apiBase}/api/vault/key/${provider}/${index}`, { method: "DELETE" });
      const data = await res.json();
      applyVaultData(data);
      setStatusMsg({ type: "ok", text: `Removed key #${index + 1} from ${provider.toUpperCase()}.` });
    } catch (err: any) {
      setStatusMsg({ type: "err", text: err.message || "Failed to remove key" });
    }
  };

  const handleSetActiveKey = async (provider: string, index: number) => {
    try {
      const res = await fetch(`${apiBase}/api/vault/key/activate`, {
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
      const res = await fetch(`${apiBase}/api/vault/endpoint`, {
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
      const res = await fetch(`${apiBase}/api/vault/endpoint/${encodeURIComponent(id)}`, { method: "DELETE" });
      const data = await res.json();
      applyVaultData(data);
    } catch (err: any) {
      setStatusMsg({ type: "err", text: err.message || "Failed to remove endpoint" });
    }
  };

  const handleRoleChange = async (role: string, provider: string, model?: string) => {
    try {
      const res = await fetch(`${apiBase}/api/vault/role`, {
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
      const res = await fetch(`${apiBase}/api/vault/test`, {
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

  const handleToggleLocalFirst = async () => {
    try {
      const target = !localFirstMode;
      const res = await fetch(`${apiBase}/api/vault/local-model/toggle-local-first`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: target }),
      });
      const data = await res.json();
      setLocalFirstMode(Boolean(data.local_first_mode));
      setStatusMsg({
        type: "ok",
        text: target
          ? "Local-First Routing ON: General chat & Q&A run locally at zero token cost."
          : "Cloud-First Routing ON: Cloud providers preferred with local model as safety net.",
      });
      fetchVault();
      fetchLocalModelStatus();
    } catch (err: any) {
      setStatusMsg({ type: "err", text: `Failed to toggle local-first: ${err.message}` });
    }
  };

  const handleDownloadLocalModel = async () => {
    setDownloadingLocal(true);
    setStatusMsg({
      type: "ok",
      text: "Background download initiated for Llama 3.2 3B Instruct weights (~2.0 GB).",
    });
    try {
      await fetch(`${apiBase}/api/vault/local-model/download`, { method: "POST" });
    } catch (err: any) {
      setStatusMsg({ type: "err", text: `Download trigger error: ${err.message}` });
    }
  };

  const handleUnloadLocalModel = async () => {
    try {
      const res = await fetch(`${apiBase}/api/vault/local-model/unload`, { method: "POST" });
      const data = await res.json();
      setLocalModel(data);
      setStatusMsg({ type: "ok", text: "Local model unloaded from system RAM." });
      fetchLocalModelStatus();
    } catch (err: any) {
      setStatusMsg({ type: "err", text: `Failed to unload model: ${err.message}` });
    }
  };

  const handleTestLocalModel = async () => {
    setTesting(true);
    setStatusMsg(null);
    try {
      const res = await fetch(`${apiBase}/api/vault/local-model/test`, { method: "POST" });
      const data = await res.json();
      if (data.ok) {
        setStatusMsg({
          type: "ok",
          text: `Local Llama 3.2 Inference Verified (${data.latency_ms}ms): "${data.reply}"`,
        });
      } else {
        setStatusMsg({
          type: "err",
          text: `Local Model Test Failed: ${data.error || "Generation error"}`,
        });
      }
      fetchLocalModelStatus();
    } catch (err: any) {
      setStatusMsg({ type: "err", text: `Local test error: ${err.message}` });
    } finally {
      setTesting(false);
    }
  };

  const providerList = ["local", "gemini", "groq", "openai", "anthropic"];
  const addKeyProviderList = ["gemini", "groq", "openai", "anthropic"];
  const rolesList = [
    { id: "chat", label: "Primary Chat & Reasoning" },
    { id: "qa_chat", label: "Spoken Q&A & Trivia" },
    { id: "coding", label: "Tier 1 OS Code Synthesizer" },
    { id: "vision", label: "Tier 3 Set-of-Mark Vision" },
    { id: "summarizer", label: "Meeting Transcript Summarizer" },
  ];

  const allProviderOptions = [
    ...providerList.map((p) => ({
      value: p,
      label: p === "local" ? "LOCAL (In-Process GGUF)" : p.toUpperCase(),
    })),
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

      {/* Embedded In-Process Local Engine Card */}
      <div className="bg-[#0B1320]/90 border border-[#00E5FF]/40 p-4 rounded space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#00E5FF]/20 pb-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-[#00E5FF]/10 border border-[#00E5FF]/30 rounded">
              <Cpu className="w-6 h-6 text-[#00E5FF]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm tracking-wider uppercase text-white">
                  Local In-Process Engine (Llama 3.2 3B Instruct)
                </span>
                {localModel?.loaded ? (
                  <span className="px-2 py-0.5 text-[10px] font-bold uppercase bg-[#00E676]/20 text-[#00E676] border border-[#00E676] rounded">
                    Active in RAM (~{localModel.ram_usage_mb || 2100} MB)
                  </span>
                ) : localModel?.downloaded && !localModel?.runtime_available ? (
                  <span className="px-2 py-0.5 text-[10px] font-bold uppercase bg-[#FF3B5C]/15 text-[#FF8A80] border border-[#FF3B5C]/60 rounded">
                    Runtime missing
                  </span>
                ) : localModel?.downloaded ? (
                  <span className="px-2 py-0.5 text-[10px] font-bold uppercase bg-[#00E5FF]/20 text-[#00E5FF] border border-[#00E5FF] rounded">
                    Ready on Disk ({localModel.size_mb || 2023} MB)
                  </span>
                ) : (
                  <span className="px-2 py-0.5 text-[10px] font-bold uppercase bg-[#FFB300]/20 text-[#FFB300] border border-[#FFB300] rounded">
                    Weights Not Downloaded
                  </span>
                )}
              </div>
              <p className="text-xs text-[#8AB4F8] mt-1">
                 AVX2-optimized CPU inference ({localModel?.threads || 4} threads, 2048 ctx). Runs offline at zero cost with no cloud API limits.
                 {!localModel?.runtime_available && <span className="block mt-1 text-[#FF8A80]">Install the local runtime with <span className="font-mono">pip install llama-cpp-python</span>, then test inference again.</span>}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleToggleLocalFirst}
              className={`flex items-center gap-2 px-3 py-1.5 text-xs font-bold rounded border transition ${
                localFirstMode
                  ? "bg-[#00E676]/20 text-[#00E676] border-[#00E676]"
                  : "bg-gray-800/60 text-gray-400 border-gray-700"
              }`}
              title="Toggle whether general chat/Q&A runs locally first"
            >
              <Power className="w-3.5 h-3.5" />
              {localFirstMode ? "LOCAL-FIRST: ACTIVE" : "LOCAL-FIRST: OFF"}
            </button>

            {localModel?.downloaded ? (
              <>
                <button
                  type="button"
                  onClick={handleTestLocalModel}
                  disabled={testing}
                  className="px-3 py-1.5 text-xs font-bold bg-[#00E5FF]/15 hover:bg-[#00E5FF]/25 border border-[#00E5FF] text-[#00E5FF] rounded transition flex items-center gap-1.5"
                >
                  <Zap className="w-3.5 h-3.5" />
                  {testing ? "RUNNING..." : "TEST INFERENCE"}
                </button>
                {localModel.loaded && (
                  <button
                    type="button"
                    onClick={handleUnloadLocalModel}
                    className="px-3 py-1.5 text-xs font-bold bg-[#FF1744]/15 hover:bg-[#FF1744]/25 border border-[#FF1744] text-[#FF8A80] rounded transition"
                  >
                    UNLOAD RAM
                  </button>
                )}
              </>
            ) : (
              <button
                type="button"
                onClick={handleDownloadLocalModel}
                disabled={downloadingLocal}
                className="px-4 py-1.5 text-xs font-bold bg-[#00E5FF]/20 hover:bg-[#00E5FF]/30 border border-[#00E5FF] text-[#00E5FF] rounded transition flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                {downloadingLocal ? "DOWNLOADING..." : "DOWNLOAD MODEL (~2.0 GB)"}
              </button>
            )}
          </div>
        </div>

        {/* Download Progress Bar */}
        {downloadingLocal && (
          <div className="bg-[#060A12] border border-[#00E5FF]/30 p-3 rounded space-y-2">
            <div className="flex justify-between text-xs text-[#8AB4F8]">
              <span>Downloading Llama 3.2 3B Instruct Q4_K_M weights from Hugging Face...</span>
              <span className="font-mono text-[#00E5FF]">
                {localModel?.download_state?.progress || 0}% ({localModel?.download_state?.speed_mb_s || 0} MB/s)
              </span>
            </div>
            <div className="w-full bg-gray-800 h-2 rounded overflow-hidden">
              <div
                className="bg-[#00E5FF] h-full transition-all duration-300"
                style={{ width: `${localModel?.download_state?.progress || 0}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Add API Key Form */}
      <form
        onSubmit={handleAddKey}
        className="bg-[#0B1320]/80 border border-[#00E5FF]/25 p-4 rounded space-y-3"
      >
        <div className="text-xs font-bold uppercase tracking-wider text-[#00E5FF] flex items-center gap-2">
          <Plus className="w-4 h-4" /> Add Cloud API Key to Provider Pool
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <select
            id="vault-provider-select"
            name="vaultProviderSelect"
            value={selectedProvider}
            onChange={(e) => setSelectedProvider(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/40 rounded px-3 py-2 text-sm text-[#00E5FF] focus:outline-none"
          >
            {addKeyProviderList.map((p) => (
              <option key={p} value={p}>
                {p.toUpperCase()}
              </option>
            ))}
          </select>
          <input
            id="vault-new-label"
            name="newApiLabel"
            type="text"
            autoComplete="off"
            placeholder="Label (optional, e.g. Personal Key 1)"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-2 text-sm text-white focus:border-[#00E5FF] focus:outline-none"
          />
          <input
            id="vault-new-key"
            name="newApiKey"
            type="password"
            autoComplete="off"
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
          const isLocalProv = prov === "local";

          return (
            <div
              key={prov}
              className="bg-[#0B1320]/80 border border-[#00E5FF]/25 rounded p-4 flex flex-col justify-between space-y-3"
            >
              <div className="flex items-center justify-between border-b border-[#00E5FF]/20 pb-2">
                <div className="flex items-center gap-2">
                  {isLocalProv ? (
                    <Cpu className="w-4 h-4 text-[#00E5FF]" />
                  ) : (
                    <Key className="w-4 h-4 text-[#00E5FF]" />
                  )}
                  <span className="font-bold text-sm tracking-wider uppercase text-[#00E5FF]">
                    {isLocalProv ? "LOCAL ENGINE" : prov}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-[#00E5FF]/15 text-[#00E5FF]">
                    {isLocalProv ? "In-Process GGUF" : `${keys.length} ${keys.length === 1 ? "Key" : "Keys"}`}
                  </span>
                </div>
                <span className="text-xs text-[#8AB4F8] font-mono">{cfg.default_model}</span>
              </div>

              {keys.length === 0 && !isLocalProv ? (
                <div className="text-xs text-gray-400 italic py-4 text-center border border-dashed border-gray-700 rounded">
                  No keys in {prov.toUpperCase()} pool. Add a key above.
                </div>
              ) : (
                <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                  {(isLocalProv && keys.length === 0 ? [{ id: "local_1", key: "local-in-process", label: "Embedded In-Process Engine", status: "active", is_active: true }] : keys).map((rawK: any, idx: number) => {
                    const isObj = rawK && typeof rawK === "object";
                    const keyStr = isObj ? (rawK.key || rawK.masked || rawK.masked_key || "") : String(rawK || "");
                    const isActive = isLocalProv ? true : (idx === (cfg.active_index ?? 0) || (isObj && rawK.is_active));
                    const maskedStr = isLocalProv
                      ? "local-in-process (AVX2 CPU)"
                      : (isObj ? (rawK.masked || rawK.masked_key || rawK.preview || rawK.key) : null) || (keyStr.length > 8 ? `${keyStr.slice(0, 4)}••••••••${keyStr.slice(-4)}` : keyStr || "****");
                    const status = isLocalProv ? "active" : (isActive ? "active" : ((isObj ? rawK.status : null) || "standby"));
                    const badgeColor =
                      status === "active"
                        ? "bg-[#00E676]/20 text-[#00E676] border-[#00E676]"
                        : status === "cooldown"
                        ? "bg-[#FFB300]/20 text-[#FFB300] border-[#FFB300]"
                        : status === "exhausted"
                        ? "bg-[#FF1744]/20 text-[#FF1744] border-[#FF1744]"
                        : "bg-[#00E5FF]/10 text-[#8AB4F8] border-[#00E5FF]/30";
                    const keyId = (isObj && rawK.id) ? rawK.id : `${prov}_${idx + 1}`;
                    const label = isLocalProv
                      ? "Embedded CPU Llama 3.2"
                      : (isObj && rawK.label) ? rawK.label : `${prov.toUpperCase()} Key #${idx + 1}`;
                    const calls = isObj ? (rawK.calls ?? 0) : 0;
                    const errors = isObj ? (rawK.errors ?? 0) : 0;

                    return (
                      <div
                        key={keyId}
                        className={`flex items-center justify-between p-2.5 rounded border text-xs ${
                          isActive
                            ? "bg-[#00E5FF]/10 border-[#00E5FF]"
                            : "bg-[#060A12]/80 border-gray-800"
                        }`}
                      >
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-white">
                              {label}
                            </span>
                            <span className={`px-1.5 py-0.2 text-[10px] uppercase border rounded ${badgeColor}`}>
                              {status}
                            </span>
                          </div>
                          <div className="font-mono text-[#00E5FF] text-xs">{maskedStr}</div>
                          <div className="text-[10px] text-gray-400">
                            {isLocalProv ? "Zero cloud cost / offline fallback" : `Calls: ${calls} | Errors: ${errors}`}
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5">
                          {!isLocalProv && !isActive && (
                            <button
                              type="button"
                              onClick={() => handleSetActiveKey(prov, idx)}
                              className="px-2 py-1 text-[10px] bg-[#00E5FF]/15 hover:bg-[#00E5FF]/30 text-[#00E5FF] border border-[#00E5FF]/40 rounded"
                            >
                              Use
                            </button>
                          )}
                          {!isLocalProv && (
                            <button
                              type="button"
                              onClick={() => handleRemoveKey(prov, idx)}
                              className="p-1.5 text-red-400 hover:bg-red-500/20 rounded"
                              title="Remove Key"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
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
                    id={`role-provider-${r.id}`}
                    name={`roleProvider_${r.id}`}
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
                    id={`role-model-${r.id}`}
                    name={`roleModel_${r.id}`}
                    type="text"
                    autoComplete="off"
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
            id="ep-name-input"
            name="epNameInput"
            type="text"
            autoComplete="off"
            placeholder="Name (e.g. Local Ollama)"
            value={epName}
            onChange={(e) => setEpName(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-1.5 text-xs text-white"
          />
          <input
            id="ep-url-input"
            name="epUrlInput"
            type="text"
            autoComplete="off"
            placeholder="Base URL (http://127.0.0.1:11434/v1)"
            value={epUrl}
            onChange={(e) => setEpUrl(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-1.5 text-xs text-white font-mono"
          />
          <input
            id="custom-ep-key"
            name="customEndpointKey"
            type="password"
            autoComplete="off"
            placeholder="API Key (sk-local)"
            value={epKey}
            onChange={(e) => setEpKey(e.target.value)}
            className="bg-[#060A12] border border-[#00E5FF]/30 rounded px-3 py-1.5 text-xs text-white"
          />
          <input
            id="ep-model-input"
            name="epModelInput"
            type="text"
            autoComplete="off"
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
