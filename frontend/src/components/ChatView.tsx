"use client";

import React, { useState, useEffect, useRef } from "react";
import { Send, BookOpen, AlertCircle, Search, Square, MessageSquare, Sparkles } from "lucide-react";
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

// 빈 채팅 상태에서 보여줄 예시 질문 (골든셋 기반)
const SUGGESTED_QUESTIONS = [
  "부채비율 44.3%를 기록한 시점의 자산총계는?",
  "영업이익이 37억원인 분기의 IT 부문 매출은?",
  "수주잔고가 0.70조원인 분기 다음 분기 수주잔고는?",
];

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
            className="citation-chip"
            onClick={() => onCitationClick?.(n)}
            title={`출처 ${n} 보기`}
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

export default function ChatView() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [config, setConfig] = useState<LLMConfig>(DEFAULT_CONFIG);
  const [activeRefId, setActiveRefId] = useState<string | null>(null); // For accordion toggle
  const [highlightedRefKey, setHighlightedRefKey] = useState<string | null>(null);
  const [searchMode, setSearchMode] = useState<"hybrid" | "dense">("hybrid");
  const [rerank, setRerank] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const msgSeqRef = useRef(0); // 메시지 ID 시퀀스 (render-pure 유지를 위해 Date.now 대신 사용)
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

  const sendQuery = async (queryText: string) => {
    if (!queryText.trim() || isStreaming) return;

    // Create user message
    const seq = ++msgSeqRef.current;
    const userMsgId = `user-${seq}`;
    const userMessage: Message = {
      id: userMsgId,
      role: "user",
      text: queryText
    };

    // Create placeholder assistant message
    const assistantMsgId = `assistant-${seq}`;
    const assistantMessage: Message = {
      id: assistantMsgId,
      role: "assistant",
      text: "",
      isStreaming: true
    };

    setMessages(prev => [...prev, userMessage, assistantMessage]);

    // 에러가 난 메시지를 제외한 과거 대화 히스토리 조립
    const historyList = messages
      .filter(m => m.text && !m.error)
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const queryText = input.trim();
    if (!queryText) return;
    setInput("");
    sendQuery(queryText);
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
    <div className="view animate-fade-in">
      {/* Header */}
      <div className="view-header" style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", paddingBottom: "16px", borderBottom: "1px solid var(--border)" }}>
        <div>
          <h2>RAG 채팅</h2>
          <p className="desc">
            {config.provider} · {config.model}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div className="seg" role="group" aria-label="검색 모드">
            <button className={searchMode === "hybrid" ? "on" : ""} onClick={() => setSearchMode("hybrid")}>
              Hybrid
            </button>
            <button className={searchMode === "dense" ? "on" : ""} onClick={() => setSearchMode("dense")}>
              Dense
            </button>
          </div>
          <button
            className={`toggle-chip ${rerank ? "on" : ""}`}
            onClick={() => setRerank(v => !v)}
            title="BGE cross-encoder re-ranking (느림, 정확도 향상)"
          >
            <Sparkles size={12} />
            Re-rank
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 32px", display: "flex", flexDirection: "column", gap: "18px", minHeight: 0 }}>
        {messages.length === 0 ? (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "8px" }}>
            <div style={{
              width: "44px", height: "44px", borderRadius: "12px", background: "var(--surface-2)",
              border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center",
              color: "var(--text-2)", marginBottom: "6px",
            }}>
              <MessageSquare size={20} />
            </div>
            <div style={{ fontSize: "1.02rem", fontWeight: 600 }}>문서 속 표·숫자에 대해 물어보세요</div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-2)", maxWidth: "380px", textAlign: "center" }}>
              업로드한 PDF에서 하이브리드 검색으로 근거를 찾아 출처와 함께 답변합니다.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", justifyContent: "center", marginTop: "14px", maxWidth: "560px" }}>
              {SUGGESTED_QUESTIONS.map(q => (
                <button key={q} className="suggest-chip" onClick={() => sendQuery(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => {
            const isUser = m.role === "user";
            return (
              <div key={m.id} style={{
                display: "flex",
                flexDirection: "column",
                alignItems: isUser ? "flex-end" : "flex-start",
                maxWidth: "78%",
                alignSelf: isUser ? "flex-end" : "flex-start"
              }}>
                {/* Message bubble */}
                <div className={`bubble ${isUser ? "bubble-user" : "bubble-assistant"}`}>
                  {m.text ? (
                    <div>{renderInlineMarkdown(m.text, isUser ? undefined : (idx) => handleCitationClick(m.id, idx))}</div>
                  ) : m.isStreaming && !m.error ? (
                    <div style={{ display: "flex", gap: "5px", padding: "4px 0", alignItems: "center" }}>
                      <span style={{ width: "5px", height: "5px", background: "var(--text-2)", borderRadius: "50%" }} className="animate-pulse-slow" />
                      <span style={{ width: "5px", height: "5px", background: "var(--text-2)", borderRadius: "50%", animationDelay: "0.2s" }} className="animate-pulse-slow" />
                      <span style={{ width: "5px", height: "5px", background: "var(--text-2)", borderRadius: "50%", animationDelay: "0.4s" }} className="animate-pulse-slow" />
                    </div>
                  ) : null}

                  {m.aborted && (
                    <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--text-3)", fontSize: "0.76rem", marginTop: m.text ? "8px" : "0", fontStyle: "italic" }}>
                      <Square size={10} />
                      <span>응답이 중단되었습니다</span>
                    </div>
                  )}

                  {m.error && (
                    <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--red)", fontSize: "0.82rem", marginTop: m.text ? "8px" : "0" }}>
                      <AlertCircle size={13} />
                      <span>{m.error}</span>
                    </div>
                  )}
                </div>

                {/* Query Condensing: 후속 질문이 독립 검색 질의로 재작성된 경우 표시 */}
                {!isUser && m.condensedQuery && (
                  <div style={{
                    marginTop: "6px",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "0.74rem",
                    color: "var(--text-3)",
                    padding: "4px 9px",
                    background: "var(--amber-soft)",
                    border: "1px solid rgba(232, 163, 61, 0.2)",
                    borderRadius: "6px",
                    maxWidth: "100%"
                  }}>
                    <Search size={11} style={{ color: "var(--amber)", flexShrink: 0 }} />
                    <span style={{ overflowWrap: "anywhere" }}>
                      검색 질의 재작성: <span style={{ color: "var(--text-2)", fontStyle: "italic" }}>{m.condensedQuery}</span>
                    </span>
                  </div>
                )}

                {/* RAG References Accordion */}
                {!isUser && m.references && m.references.length > 0 && (
                  <div style={{ marginTop: "6px", width: "100%" }}>
                    <button
                      onClick={() => handleToggleRef(m.id)}
                      style={{
                        background: "none",
                        border: "none",
                        color: "var(--text-2)",
                        fontSize: "0.78rem",
                        fontWeight: 500,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        padding: "4px 6px",
                        borderRadius: "5px",
                      }}
                    >
                      <BookOpen size={12} />
                      <span>참조 출처 {m.references.length}개</span>
                      <span style={{ fontSize: "0.68rem", color: "var(--text-3)" }}>
                        {activeRefId === m.id ? "접기" : "펼치기"}
                      </span>
                    </button>

                    {activeRefId === m.id && (
                      <div style={{
                        marginTop: "8px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "8px",
                        paddingLeft: "10px",
                        borderLeft: "2px solid var(--border-strong)"
                      }}>
                        {m.references.map((ref, idx) => {
                          const refKey = `${m.id}-${idx}`;
                          const isHighlighted = highlightedRefKey === refKey;
                          return (
                          <div
                            key={ref.chunk_id}
                            id={`ref-card-${refKey}`}
                            className="card"
                            style={{
                              padding: "12px 14px",
                              fontSize: "0.8rem",
                              background: isHighlighted ? "var(--accent-soft)" : "var(--surface)",
                              borderColor: isHighlighted ? "rgba(91,124,250,0.45)" : undefined,
                              transition: "background 0.3s, border-color 0.3s",
                            }}
                          >
                            <div style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              marginBottom: "8px",
                              borderBottom: "1px solid var(--border)",
                              paddingBottom: "7px",
                              color: "var(--text-2)"
                            }}>
                              <span style={{ fontWeight: 600 }}>출처 {idx + 1} · 청크 {ref.chunk_id}</span>
                              <div style={{ display: "flex", gap: "7px", alignItems: "center" }}>
                                <span className={`badge badge-${ref.chunk_type}`}>{ref.chunk_type === "table" ? "표" : "본문"}</span>
                                {ref.section_header && (
                                  <span style={{ fontSize: "0.72rem", background: "var(--surface-3)", padding: "1px 7px", borderRadius: "4px" }}>
                                    {ref.section_header}
                                  </span>
                                )}
                                {ref.page_number && (
                                  <span style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>p.{ref.page_number}</span>
                                )}
                                <span style={{ fontSize: "0.72rem", color: "var(--text-3)", fontVariantNumeric: "tabular-nums" }}>
                                  {ref.score.toFixed(4)}
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
          })
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={{
        padding: "16px 32px 22px",
        borderTop: "1px solid var(--border)",
        display: "flex",
        gap: "10px",
        flexShrink: 0,
      }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="문서에 대해 질문을 입력하세요"
          className="input-field"
          style={{ flex: 1 }}
        />
        {isStreaming ? (
          <button type="button" onClick={handleAbort} className="btn btn-stop" style={{ minWidth: "92px" }}>
            <Square size={13} />
            <span>중단</span>
          </button>
        ) : (
          <button type="submit" className="btn btn-primary" style={{ minWidth: "92px" }}>
            <Send size={14} />
            <span>전송</span>
          </button>
        )}
      </form>
    </div>
  );
}
