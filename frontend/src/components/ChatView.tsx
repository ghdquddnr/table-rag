"use client";

import React, { useState, useEffect, useRef } from "react";
import { Send, BookOpen, AlertCircle, Layers } from "lucide-react";
import { LLMConfig, DEFAULT_CONFIG } from "./SettingsView";
import MarkdownTable from "./MarkdownTable";

interface Reference {
  chunk_id: number;
  chunk_type: string;
  content: string;
  section_header: string | null;
  score: number;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  references?: Reference[];
  error?: string;
  isStreaming?: boolean;
}

export default function ChatView() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [config, setConfig] = useState<LLMConfig>(DEFAULT_CONFIG);
  const [activeRefId, setActiveRefId] = useState<string | null>(null); // For accordion toggle
  
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load config on mount (asynchronously to avoid synchronous setState in effect)
  useEffect(() => {
    const saved = localStorage.getItem("table_rag_llm_config");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setTimeout(() => {
          setConfig(parsed);
        }, 0);
      } catch (e) {
        console.error("Failed to parse config in ChatView", e);
      }
    }
    
    // Add welcome message
    setTimeout(() => {
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          text: "안녕하세요! 표·숫자에 특화된 한국어 하이브리드 RAG 시스템입니다. 업로드한 PDF 보고서에 들어 있는 재무 정보나 통계 표 데이터에 대해 질문해 보세요. (예: '부채비율 44.3%를 기록한 시점의 자산총계는?')"
        }
      ]);
    }, 0);
  }, []);

  // Auto scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

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

    try {
      const res = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          query: queryText,
          provider: config.provider,
          model: config.model,
          api_key: config.apiKey,
          api_url: config.apiUrl,
          stream: true
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
                // references metadata received
                setMessages(prev => 
                  prev.map(m => m.id === assistantMsgId ? { ...m, references: parsed.references } : m)
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
      const errorMsg = err instanceof Error ? err.message : "답변 생성 실패";
      setMessages(prev => 
        prev.map(m => m.id === assistantMsgId ? { ...m, error: errorMsg, isStreaming: false } : m)
      );
    }
  };

  const handleToggleRef = (msgId: string) => {
    setActiveRefId(prev => (prev === msgId ? null : msgId));
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
        <div>
          <span>RRF Hybrid Search: <strong style={{ color: "var(--accent)" }}>Dense Cosine + pg_trgm word_similarity</strong></span>
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
                  wordBreak: "break-all",
                  boxShadow: isUser ? "0 4px 15px rgba(59,130,246,0.1)" : "var(--card-shadow)"
                }}
              >
                {m.text ? (
                  <div style={{ whiteSpace: "pre-line" }}>{m.text}</div>
                ) : m.isStreaming && !m.error ? (
                  <div style={{ display: "flex", gap: "5px", padding: "4px 0", alignItems: "center" }}>
                    <span style={{ width: "6px", height: "6px", background: "var(--primary)", borderRadius: "50%" }} className="animate-pulse-slow" />
                    <span style={{ width: "6px", height: "6px", background: "var(--primary)", borderRadius: "50%", animationDelay: "0.2s" }} className="animate-pulse-slow" />
                    <span style={{ width: "6px", height: "6px", background: "var(--primary)", borderRadius: "50%", animationDelay: "0.4s" }} className="animate-pulse-slow" />
                  </div>
                ) : null}

                {m.error && (
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#f87171", fontSize: "0.85rem", marginTop: m.text ? "8px" : "0" }}>
                    <AlertCircle size={14} />
                    <span>{m.error}</span>
                  </div>
                )}
              </div>

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
                      {m.references.map((ref, idx) => (
                        <div
                          key={ref.chunk_id}
                          className="glass-panel"
                          style={{
                            padding: "12px",
                            fontSize: "0.8rem",
                            background: "rgba(0, 0, 0, 0.2)"
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
                              <span style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>
                                score {ref.score.toFixed(4)}
                              </span>
                            </div>
                          </div>
                          <MarkdownTable content={ref.content} />
                        </div>
                      ))}
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
        <button type="submit" className="btn btn-primary" style={{ padding: "0 22px" }}>
          <Send size={16} />
          <span>전송</span>
        </button>
      </form>
    </div>
  );
}
