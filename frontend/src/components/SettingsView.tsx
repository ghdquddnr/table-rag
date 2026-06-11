"use client";

import React, { useState, useEffect } from "react";
import { Settings, Server, Cpu, Key, CheckCircle, AlertTriangle } from "lucide-react";

export interface LLMConfig {
  provider: "ollama" | "openai" | "gemini";
  model: string;
  apiUrl: string;
  apiKey: string;
}

export const DEFAULT_CONFIG: LLMConfig = {
  provider: "ollama",
  model: "gemma4:12b",
  apiUrl: "http://localhost:11434",
  apiKey: "",
};

interface OllamaTag {
  name: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// 백엔드에 저장된 LLM 설정 조회 (snake_case API ↔ camelCase 프런트 매핑).
// 저장된 적이 없거나 백엔드가 꺼져 있으면 기본값을 반환한다.
export async function fetchLLMConfig(): Promise<LLMConfig> {
  try {
    const res = await fetch(`${API_BASE}/api/settings/llm`);
    if (!res.ok) return DEFAULT_CONFIG;
    const data = await res.json();
    if (!data) return DEFAULT_CONFIG;
    return {
      ...DEFAULT_CONFIG,
      provider: data.provider,
      model: data.model,
      apiUrl: data.api_url,
      apiKey: data.api_key,
    };
  } catch {
    return DEFAULT_CONFIG;
  }
}

export default function SettingsView() {
  const [config, setConfig] = useState<LLMConfig>(DEFAULT_CONFIG);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [connError, setConnError] = useState<string | null>(null);

  // 마운트 시 DB에 저장된 설정 로드
  useEffect(() => {
    fetchLLMConfig().then(setConfig);
  }, []);

  // Fetch Ollama models when provider or apiUrl changes
  useEffect(() => {
    const fetchOllamaModels = async (url: string) => {
      setIsLoadingModels(true);
      setConnError(null);
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000); // 3s timeout
        
        const res = await fetch(`${url}/api/tags`, { signal: controller.signal });
        clearTimeout(timeoutId);
        
        if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
        const data = await res.json();
        const models = (data.models || []).map((m: OllamaTag) => m.name);
        setOllamaModels(models);
        
        // If currently selected model is not in list, pick appropriate one
        if (models.length > 0 && !models.includes(config.model)) {
          const defaultModel = models.find((m: string) => m.startsWith("gemma4")) || models[0];
          setConfig(prev => ({ ...prev, model: defaultModel }));
        }
      } catch (e) {
        console.warn("Ollama connection failed, falling back to manual model input", e);
        setConnError("Ollama 서버에 연결할 수 없습니다. URL 및 실행 상태를 확인해 주세요.");
        setOllamaModels([]);
      } finally {
        setIsLoadingModels(false);
      }
    };

    if (config.provider === "ollama") {
      fetchOllamaModels(config.apiUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.provider, config.apiUrl]);

  const handleSave = async () => {
    setSaveError(null);
    try {
      const res = await fetch(`${API_BASE}/api/settings/llm`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: config.provider,
          model: config.model,
          api_url: config.apiUrl,
          api_key: config.apiKey,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || `저장 실패 (HTTP ${res.status})`);
      }
      // 같은 탭의 ChatView에 변경을 즉시 반영하기 위한 커스텀 이벤트
      window.dispatchEvent(new CustomEvent<LLMConfig>("llm-config-updated", { detail: config }));
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "설정 저장에 실패했습니다.");
    }
  };

  const updateField = (field: keyof LLMConfig, value: string) => {
    setConfig(prev => {
      const next = { ...prev, [field]: value };
      // Apply default models if provider changed
      if (field === "provider") {
        if (value === "ollama") {
          next.model = ollamaModels.includes("gemma4:12b") ? "gemma4:12b" : (ollamaModels[0] || "gemma4:12b");
          next.apiUrl = "http://localhost:11434";
        } else if (value === "openai") {
          next.model = "gpt-4o";
          next.apiUrl = "https://api.openai.com/v1/chat/completions";
        } else if (value === "gemini") {
          next.model = "gemini-1.5-flash";
          next.apiUrl = "";
        }
      }
      return next;
    });
  };

  return (
    <div className="glass-panel animate-fade-in" style={{ padding: "30px", maxWidth: "600px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "24px" }}>
        <Settings size={22} style={{ color: "var(--primary)" }} />
        <h2 style={{ fontSize: "1.25rem", fontWeight: "600" }}>LLM 연동 및 환경 설정</h2>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
        {/* Provider Select */}
        <div>
          <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "8px" }}>
            LLM 제공자 (Provider)
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px" }}>
            {(["ollama", "openai", "gemini"] as const).map(p => (
              <button
                key={p}
                onClick={() => updateField("provider", p)}
                style={{
                  padding: "12px",
                  borderRadius: "8px",
                  background: config.provider === p ? "var(--primary)" : "rgba(255, 255, 255, 0.03)",
                  color: config.provider === p ? "#ffffff" : "var(--text-main)",
                  border: `1px solid ${config.provider === p ? "var(--primary)" : "var(--panel-border)"}`,
                  cursor: "pointer",
                  fontWeight: config.provider === p ? "600" : "500",
                  textTransform: "capitalize",
                  transition: "all 0.2s",
                }}
              >
                {p === "ollama" ? "Ollama (로컬)" : p === "openai" ? "OpenAI" : "Gemini"}
              </button>
            ))}
          </div>
        </div>

        {/* API URL (Ollama or Custom OpenAI) */}
        {config.provider !== "gemini" && (
          <div>
            <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "8px" }}>
              <Server size={14} />
              API 엔드포인트 주소
            </label>
            <input
              type="text"
              className="input-field"
              value={config.apiUrl}
              onChange={e => updateField("apiUrl", e.target.value)}
              placeholder={config.provider === "ollama" ? "http://localhost:11434" : "https://api.openai.com/v1/chat/completions"}
            />
            {config.provider === "ollama" && connError && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#f87171", fontSize: "0.75rem", marginTop: "6px" }}>
                <AlertTriangle size={12} />
                <span>{connError}</span>
              </div>
            )}
          </div>
        )}

        {/* API Key */}
        {config.provider !== "ollama" && (
          <div>
            <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "8px" }}>
              <Key size={14} />
              API Key 인증키
            </label>
            <input
              type="password"
              className="input-field"
              value={config.apiKey}
              onChange={e => updateField("apiKey", e.target.value)}
              placeholder={`${config.provider.toUpperCase()} API 키 입력`}
            />
          </div>
        )}

        {/* Model Selection */}
        <div>
          <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "8px" }}>
            <Cpu size={14} />
            모델 선택 (Model)
          </label>
          
          {config.provider === "ollama" && ollamaModels.length > 0 ? (
            <select
              className="input-field"
              value={config.model}
              onChange={e => updateField("model", e.target.value)}
              style={{ background: "#0d1023", cursor: "pointer" }}
            >
              {ollamaModels.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              className="input-field"
              value={config.model}
              onChange={e => updateField("model", e.target.value)}
              placeholder={isLoadingModels ? "모델 조회 중..." : "사용할 모델명을 입력하세요"}
              disabled={isLoadingModels}
            />
          )}
          {config.provider === "ollama" && ollamaModels.length === 0 && !isLoadingModels && (
            <span style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginTop: "4px" }}>
              * 로컬 Ollama 실행 상태를 감지하여 자동 드롭다운이 활성화됩니다.
            </span>
          )}
        </div>

        <div style={{ marginTop: "10px", display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "12px" }}>
          {saveError && (
            <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#f87171", fontSize: "0.8rem" }}>
              <AlertTriangle size={13} />
              <span>{saveError}</span>
            </div>
          )}
          <button onClick={handleSave} className="btn btn-primary" style={{ minWidth: "140px" }}>
            {saveSuccess ? (
              <>
                <CheckCircle size={16} />
                저장 완료!
              </>
            ) : (
              "설정 저장"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
