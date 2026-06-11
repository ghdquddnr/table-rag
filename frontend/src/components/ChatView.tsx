"use client";

import React, { useState, useEffect, useRef } from "react";
import { Send, BookOpen, AlertCircle, Layers, Search, Square } from "lucide-react";
import { LLMConfig, DEFAULT_CONFIG, fetchLLMConfig } from "./SettingsView";
import MarkdownTable from "./MarkdownTable";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Reference {
  chunk_id: number;
  chunk_type: string;
  content: string;
  section_header: string | null;
  page_number: number | null;
  score: number;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  references?: Reference[];
  error?: string;
  isStreaming?: boolean;
  aborted?: boolean; // 사용자가 스트리밍을 중단한 경우
  condensedQuery?: string | null; // 멀티턴 후속 질문이 독립 질의로 재작성된 경우
}

// **bold**, *italic*, [출처N] 패턴을 처리하는 인라인 마크다운 렌더러
function renderInlineMarkdown(
  text: string,
  onCitationClick?: (idx: number) => void
): React.ReactNode {
  const lines = text.split("\n");
  return lines.map((line, lineIdx) => {
    const parts: React.ReactNode[] = [];
    // [출처N] 포함한 인라인 패턴
    const regex = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[출처\d+\])/g;
    let lastIndex = 0;
    let match;
    let key = 0;
    while ((match = regex.exec(line)) !== null) {
      if (match.index > lastIndex) parts.push(<span key={key++}>{line.slice(lastIndex, match.index)}</span>);
      const raw = match[0];
      if (raw.startsWith("**")) {
        parts.push(<strong key={key++}>{raw.slice(2, -2)}</strong>);
      } else if (raw.startsWith("*")) {
        parts.push(<em key={key++}>{raw.slice(1, -1)}</em>);
      } else {
        // [출처N] 마커
        const n = parseInt(raw.match(/\d+/)?.[0] || "0", 10);
        parts.push(
          <button
            key={key++}
            onClick={() => onCitationClick?.(n)}
            title={`출처 ${n} 보기`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              padding: "1px 6px",
              marginLeft: "2px",
              borderRadius: "4px",
              border: "1px solid rgba(59,130,246,0.5)",
              background: "rgba(59,130,246,0.12)",
              color: "var(--primary)",
              fontSize: "0.72rem",
              fontWeight: "600",
              cursor: "pointer",
              verticalAlign: "middle",
              lineHeight: "1.4",
              transition: "background 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "rgba(59,130,246,0.25)")}
            onMouseLeave={e => (e.currentTarget.style.background = "rgba(59,130,246,0.12)")}
          >
            {raw}
          </button>
        );
      }
      lastIndex = match.index + raw.length;
    }
    if (lastIndex < line.length) parts.push(<span key={key++}>{line.slice(lastIndex)}</span>);
    return (
      <React.Fragment key={lineIdx}>
        {parts.length ? parts : line}
        {lineIdx < lines.length - 1 && <br />}
      </React.Fragment>
    );
  });
}

const WELCOME_MESSAGE: Message = {
  id: "welcome",
  role: "assistant",
  text: "안녕하세요! 표·숫자에 특화된 한국어 하이브리드 RAG 시스템입니다. 업로드한 PDF 보고서에 들어 있는 재무 정보나 통계 표 데이터에 대해 질문해 보세요. (예: '부채비율 44.3%를 기록한 시점의 자산총계는?')"
};

export default function ChatView() {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [config, setConfig] = useState<LLMConfig>(DEFAULT_CONFIG);
  const [activeRefId, setActiveRefId] = useState<string | null>(null); // For accordion toggle
  const [highlightedRefKey, setHighlightedRefKey] = useState<string | null>(null);
  const [searchMode, setSearchMode] = useState<"hybrid" | "dense">("hybrid");
  const [rerank, setRerank] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const isStreaming = messages.some(m => m.isStreaming);

  // 마운트 시 DB에 저장된 설정 로드 + SettingsView 저장 시 발행되는 이벤트로 재동기화
  useEffect(() => {
    fetchLLMConfig().then(setConfig);

    const onConfigUpdated = (e: Event) => {
      const detail = (e as CustomEvent<LLMConfig>).detail;
      if (detail) setConfig(detail);
    };
    window.addEventListener("llm-config-updated", onConfigUpdated);
    return () => window.removeEventListener("llm-config-updated", onConfigUpdated);
  }, []);

  // Auto scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 스트리밍 중단 (백로그 #9): fetch + 스트림 리딩을 AbortController로 취소
  const handleAbort = () => {
    abortRef.current?.abort();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    const queryText = input.trim();
    setInput("");

    // Create user message
    const userMsgId = `user-${Date.now()}`;
    const userMessage: Message = {
      id: userMsgId,
      role: "user",
      text: queryText
    };

    // Create placeholder assistant message
    const assistantMsgId = `assistant-${Date.now()}`;
    const assistantMessage: Message = {
      id: assistantMsgId,
      role: "assistant",
      text: "",
      isStreaming: true
    };

    setMessages(prev => [...prev, userMessage, assistantMessage]);

    // welcome 메시지 및 에러가 난 메시지를 제외한 과거 대화 히스토리 조립
    const historyList = messages
      .filter(m => m.id !== "welcome" && m.text && !m.error)
      .map(m => ({
        role: m.role,
        content: m.text
      }));

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          query: queryText,
          history: historyList,
          provider: config.provider,
          model: config.model,
          api_key: config.apiKey,
          api_url: config.apiUrl,
          stream: true,
          search_mode: searchMode,
          rerank: rerank
        })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "대화 중 오류 발생");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("스트림 응답 리더를 생성할 수 없습니다.");

      const decoder = new TextDecoder();
      let buffer = "";
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Save last incomplete chunk to buffer

        for (const line of lines) {
          const cleanLine = line.trim();
          if (!cleanLine) continue;

          if (cleanLine.startsWith("data: ")) {
            const dataStr = cleanLine.slice(6).trim();
            if (dataStr === "[DONE]") {
              setMessages(prev => 
                prev.map(m => m.id === assistantMsgId ? { ...m, isStreaming: false } : m)
              );
              break;
            }

            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.type === "metadata") {
                // references + 재작성된 검색 질의 수신
                setMessages(prev =>
                  prev.map(m => m.id === assistantMsgId ? { ...m, references: parsed.references, condensedQuery: parsed.condensed_query } : m)
                );
              } else if (parsed.type === "content") {
                // content token received
                setMessages(prev => 
                  prev.map(m => m.id === assistantMsgId ? { ...m, text: m.text + parsed.text } : m)
                );
              } else if (parsed.type === "error") {
                // error received
                setMessages(prev => 
                  prev.map(m => m.id === assistantMsgId ? { ...m, error: parsed.text, isStreaming: false } : m)
                );
              }
            } catch (err) {
              console.error("Failed to parse SSE line", err);
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // 사용자 중단: 부분 응답은 유지하고 중단 표시만 남긴다
        setMessages(prev =>
          prev.map(m => m.id === assistantMsgId ? { ...m, isStreaming: false, aborted: true } : m)
        );
      } else {
        const errorMsg = err instanceof Error ? err.message : "답변 생성 실패";
        setMessages(prev =>
          prev.map(m => m.id === assistantMsgId ? { ...m, error: errorMsg, isStreaming: false } : m)
        );
      }
    } finally {
      abortRef.current = null;
    }
  };

  const handleToggleRef = (msgId: string) => {
    setActiveRefId(prev => (prev === msgId ? null : msgId));
  };

  const handleCitationClick = (msgId: string, citationIdx: number) => {
    // 아코디언 열기
    setActiveRefId(msgId);
    const key = `${msgId}-${citationIdx - 1}`;
    setHighlightedRefKey(key);
    // DOM 업데이트 후 스크롤
    setTimeout(() => {
      const el = document.getElementById(`ref-card-${key}`);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      // 하이라이트 잠시 후 해제
      setTimeout(() => setHighlightedRefKey(null), 1800);
    }, 80);
  };

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", height: "100%", position: "relative" }}>
      {/* Top Bar Status Info */}
      <div style={{
        display: "flex", 
        justifyContent: "space-between", 
        alignItems: "center", 
        padding: "10px 20px", 
        background: "rgba(255,255,255,0.01)", 
        borderBottom: "1px solid var(--panel-border)",
        fontSize: "0.8rem",
        color: "var(--text-muted)"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <Layers size={14} style={{ color: "var(--primary)" }} />
          <span>Active LLM Model: <strong style={{ color: "var(--text-main)" }}>{config.provider.toUpperCase()} ({config.model})</strong></span>
        </div>
        {/* Search Mode Toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <button
            onClick={() => setSearchMode("hybrid")}
            style={{
              padding: "4px 12px",
              borderRadius: "6px",
              border: "1px solid",
              borderColor: searchMode === "hybrid" ? "var(--accent)" : "var(--panel-border)",
              background: searchMode === "hybrid" ? "rgba(16,185,129,0.15)" : "transparent",
              color: searchMode === "hybrid" ? "var(--accent)" : "var(--text-muted)",
              fontSize: "0.75rem",
              fontWeight: searchMode === "hybrid" ? "600" : "400",
              cursor: "pointer",
              transition: "all 0.2s"
            }}
          >
            🔀 Hybrid
          </button>
          <button
            onClick={() => setSearchMode("dense")}
            style={{
              padding: "4px 12px",
              borderRadius: "6px",
              border: "1px solid",
              borderColor: searchMode === "dense" ? "var(--primary)" : "var(--panel-border)",
              background: searchMode === "dense" ? "rgba(59,130,246,0.15)" : "transparent",
              color: searchMode === "dense" ? "var(--primary)" : "var(--text-muted)",
              fontSize: "0.75rem",
              fontWeight: searchMode === "dense" ? "600" : "400",
              cursor: "pointer",
              transition: "all 0.2s"
            }}
          >
            📊 Dense only
          </button>
          {/* Re-rank toggle — cross-encoder 2-stage 파이프라인 */}
          <div style={{ width: "1px", background: "var(--panel-border)", height: "18px", margin: "0 2px" }} />
          <button
            onClick={() => setRerank(v => !v)}
            title="BGE cross-encoder re-ranking (느림, 정확도 향상)"
            style={{
              padding: "4px 12px",
              borderRadius: "6px",
              border: "1px solid",
              borderColor: rerank ? "#a855f7" : "var(--panel-border)",
              background: rerank ? "rgba(168,85,247,0.15)" : "transparent",
              color: rerank ? "#a855f7" : "var(--text-muted)",
              fontSize: "0.75rem",
              fontWeight: rerank ? "600" : "400",
              cursor: "pointer",
              transition: "all 0.2s"
            }}
          >
            ✨ Re-rank
          </button>
        </div>
      </div>

      {/* Messages Log area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px", display: "flex", flexDirection: "column", gap: "20px" }}>
        {messages.map((m) => {
          const isUser = m.role === "user";
          return (
            <div key={m.id} style={{
              display: "flex",
              flexDirection: "column",
              alignItems: isUser ? "flex-end" : "flex-start",
              maxWidth: "85%",
              alignSelf: isUser ? "flex-end" : "flex-start"
            }}>
              {/* Message bubble */}
              <div 
                className="glass-panel"
                style={{
                  padding: "14px 18px",
                  borderRadius: isUser ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                  background: isUser ? "linear-gradient(135deg, rgba(59,130,246,0.2), rgba(37,99,235,0.25))" : "rgba(255,255,255,0.02)",
                  borderColor: isUser ? "rgba(59,130,246,0.3)" : "var(--panel-border)",
                  color: "var(--text-main)",
                  fontSize: "0.95rem",
                  lineHeight: "1.6",
                  overflowWrap: "break-word",
                  boxShadow: isUser ? "0 4px 15px rgba(59,130,246,0.1)" : "var(--card-shadow)"
                }}
              >
                {m.text ? (
                  <div>{renderInlineMarkdown(m.text, isUser ? undefined : (idx) => handleCitationClick(m.id, idx))}</div>
                ) : m.isStreaming && !m.error ? (
                  <div style={{ display: "flex", gap: "5px", padding: "4px 0", alignItems: "center" }}>
                    <span style={{ width: "6px", height: "6px", background: "var(--primary)", borderRadius: "50%" }} className="animate-pulse-slow" />
                    <span style={{ width: "6px", height: "6px", background: "var(--primary)", borderRadius: "50%", animationDelay: "0.2s" }} className="animate-pulse-slow" />
                    <span style={{ width: "6px", height: "6px", background: "var(--primary)", borderRadius: "50%", animationDelay: "0.4s" }} className="animate-pulse-slow" />
                  </div>
                ) : null}

                {m.aborted && (
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--text-dim)", fontSize: "0.78rem", marginTop: m.text ? "8px" : "0", fontStyle: "italic" }}>
                    <Square size={11} />
                    <span>응답이 중단되었습니다</span>
                  </div>
                )}

                {m.error && (
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#f87171", fontSize: "0.85rem", marginTop: m.text ? "8px" : "0" }}>
                    <AlertCircle size={14} />
                    <span>{m.error}</span>
                  </div>
                )}
              </div>

              {/* Query Condensing: 후속 질문이 독립 검색 질의로 재작성된 경우 표시 */}
              {!isUser && m.condensedQuery && (
                <div style={{
                  marginTop: "8px",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "0.75rem",
                  color: "var(--text-dim)",
                  padding: "4px 8px",
                  background: "rgba(245,158,11,0.06)",
                  border: "1px solid rgba(245,158,11,0.18)",
                  borderRadius: "6px",
                  maxWidth: "100%"
                }}>
                  <Search size={12} style={{ color: "#f59e0b", flexShrink: 0 }} />
                  <span style={{ overflowWrap: "anywhere" }}>
                    검색 질의 재작성: <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>{m.condensedQuery}</span>
                  </span>
                </div>
              )}

              {/* RAG References Accordion */}
              {!isUser && m.references && m.references.length > 0 && (
                <div style={{ marginTop: "8px", width: "100%" }}>
                  <button
                    onClick={() => handleToggleRef(m.id)}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--primary)",
                      fontSize: "0.8rem",
                      fontWeight: "500",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "4px 8px",
                      borderRadius: "4px",
                      transition: "background 0.2s"
                    }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(59,130,246,0.05)"}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}
                  >
                    <BookOpen size={13} />
                    <span>RAG 참조 출처 ({m.references.length}개)</span>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-dim)" }}>
                      {activeRefId === m.id ? "▼ 닫기" : "▶ 열기"}
                    </span>
                  </button>

                  {activeRefId === m.id && (
                    <div style={{
                      marginTop: "8px",
                      display: "flex",
                      flexDirection: "column",
                      gap: "10px",
                      paddingLeft: "8px",
                      borderLeft: "2px solid rgba(59,130,246,0.3)"
                    }}>
                      {m.references.map((ref, idx) => {
                        const refKey = `${m.id}-${idx}`;
                        const isHighlighted = highlightedRefKey === refKey;
                        return (
                        <div
                          key={ref.chunk_id}
                          id={`ref-card-${refKey}`}
                          className="glass-panel"
                          style={{
                            padding: "12px",
                            fontSize: "0.8rem",
                            background: isHighlighted ? "rgba(59,130,246,0.15)" : "rgba(0, 0, 0, 0.2)",
                            borderColor: isHighlighted ? "rgba(59,130,246,0.5)" : undefined,
                            transition: "background 0.3s, border-color 0.3s",
                          }}
                        >
                          <div style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: "8px",
                            borderBottom: "1px solid rgba(255,255,255,0.04)",
                            paddingBottom: "6px",
                            color: "var(--text-muted)"
                          }}>
                            <span style={{ fontWeight: "600" }}>#{idx + 1} 출처 (Chunk ID: {ref.chunk_id})</span>
                            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                              <span className={`badge badge-${ref.chunk_type}`}>{ref.chunk_type}</span>
                              {ref.section_header && (
                                <span style={{ fontSize: "0.75rem", background: "rgba(255,255,255,0.05)", padding: "1px 6px", borderRadius: "4px" }}>
                                  {ref.section_header}
                                </span>
                              )}
                              {ref.page_number && (
                                <span style={{ fontSize: "0.75rem", background: "rgba(59,130,246,0.1)", color: "var(--primary)", padding: "1px 6px", borderRadius: "4px", fontWeight: "600" }}>
                                  p. {ref.page_number}
                                </span>
                              )}
                              <span style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>
                                score {ref.score.toFixed(4)}
                              </span>
                            </div>
                          </div>
                          <MarkdownTable content={ref.content} />
                        </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        <div ref={chatEndRef} />
      </div>

      {/* Input box form */}
      <form onSubmit={handleSubmit} style={{
        padding: "20px",
        background: "rgba(255,255,255,0.01)",
        borderTop: "1px solid var(--panel-border)",
        display: "flex",
        gap: "10px"
      }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="RAG 검색 및 LLM에게 질문할 내용을 입력하세요... (Enter 송신)"
          className="input-field"
          style={{ flex: 1 }}
        />
        {isStreaming ? (
          <button
            type="button"
            onClick={handleAbort}
            className="btn"
            style={{
              padding: "0 22px",
              background: "rgba(239,68,68,0.12)",
              border: "1px solid rgba(239,68,68,0.45)",
              color: "#f87171",
            }}
          >
            <Square size={14} />
            <span>중단</span>
          </button>
        ) : (
          <button type="submit" className="btn btn-primary" style={{ padding: "0 22px" }}>
            <Send size={16} />
            <span>전송</span>
          </button>
        )}
      </form>
    </div>
  );
}
