"use client";

import React, { useState, useEffect } from "react";
import { FileText, Settings, Database, Activity, Wifi, WifiOff, MessageSquare } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
import ChatView from "@/components/ChatView";
import DocumentView from "@/components/DocumentView";
import SettingsView from "@/components/SettingsView";

export default function Home() {
  const [activeTab, setActiveTab] = useState<"chat" | "documents" | "settings">("chat");
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [chunkCount, setChunkCount] = useState<number>(0);

  const checkBackendHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (res.ok) {
        const data = await res.json();
        setBackendOnline(true);
        setChunkCount(data.chunk_count || 0);
      } else {
        setBackendOnline(false);
      }
    } catch {
      setBackendOnline(false);
    }
  };

  // Ping backend on load and every 10 seconds
  useEffect(() => {
    checkBackendHealth();
    const interval = setInterval(checkBackendHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{
      width: "100vw",
      height: "100vh",
      display: "flex",
      flexDirection: "column",
      background: "radial-gradient(circle at top, #0c0f24 0%, #06070e 100%)",
      color: "var(--foreground)",
      padding: "16px",
      overflow: "hidden"
    }}>
      {/* Top Header */}
      <header className="glass-panel" style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "14px 24px",
        marginBottom: "16px",
        height: "64px",
        flexShrink: 0
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            background: "linear-gradient(135deg, var(--primary), var(--accent))",
            width: "32px",
            height: "32px",
            borderRadius: "8px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 0 15px rgba(59, 130, 246, 0.4)"
          }}>
            <Database size={18} style={{ color: "#ffffff" }} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.1rem", fontWeight: "700", letterSpacing: "-0.02em" }}>table-rag</h1>
            <p style={{ fontSize: "0.7rem", color: "var(--text-dim)", marginTop: "1px" }}>한국어 표·숫자 특화 RAG 시스템</p>
          </div>
        </div>

        {/* Backend health status indicator */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "0.8rem",
            background: "rgba(255, 255, 255, 0.02)",
            border: "1px solid var(--panel-border)",
            padding: "5px 12px",
            borderRadius: "6px"
          }}>
            {backendOnline === true ? (
              <>
                <Wifi size={14} style={{ color: "var(--accent)" }} />
                <span style={{ color: "var(--text-main)", fontWeight: "500" }}>DB Connected</span>
                <span style={{ color: "var(--text-dim)", marginLeft: "4px" }}>({chunkCount} chunks)</span>
              </>
            ) : backendOnline === false ? (
              <>
                <WifiOff size={14} style={{ color: "var(--danger)" }} />
                <span style={{ color: "#f87171", fontWeight: "500" }}>DB Offline</span>
              </>
            ) : (
              <>
                <Activity size={14} style={{ color: "var(--text-dim)" }} className="animate-pulse-slow" />
                <span style={{ color: "var(--text-dim)" }}>Checking connection...</span>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main content body grid */}
      <div style={{
        flex: 1,
        display: "flex",
        gap: "16px",
        overflow: "hidden"
      }}>
        {/* Left Sidebar Menu */}
        <aside className="glass-panel" style={{
          width: "220px",
          display: "flex",
          flexDirection: "column",
          padding: "16px 12px",
          flexShrink: 0,
          justifyContent: "space-between"
        }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <div style={{ fontSize: "0.75rem", fontWeight: "600", color: "var(--text-dim)", textTransform: "uppercase", paddingLeft: "12px", marginBottom: "8px" }}>
              메뉴 대시보드
            </div>
            
            <button
              onClick={() => setActiveTab("chat")}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                width: "100%",
                padding: "11px 14px",
                borderRadius: "8px",
                border: "none",
                cursor: "pointer",
                textAlign: "left",
                fontSize: "0.9rem",
                fontWeight: activeTab === "chat" ? "600" : "500",
                background: activeTab === "chat" ? "linear-gradient(90deg, rgba(59,130,246,0.15), transparent)" : "transparent",
                color: activeTab === "chat" ? "var(--primary)" : "var(--text-muted)",
                borderLeft: `3px solid ${activeTab === "chat" ? "var(--primary)" : "transparent"}`,
                transition: "all 0.2s"
              }}
            >
              <MessageSquare size={16} />
              <span>RAG 채팅</span>
            </button>

            <button
              onClick={() => setActiveTab("documents")}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                width: "100%",
                padding: "11px 14px",
                borderRadius: "8px",
                border: "none",
                cursor: "pointer",
                textAlign: "left",
                fontSize: "0.9rem",
                fontWeight: activeTab === "documents" ? "600" : "500",
                background: activeTab === "documents" ? "linear-gradient(90deg, rgba(16,185,129,0.1), transparent)" : "transparent",
                color: activeTab === "documents" ? "var(--accent)" : "var(--text-muted)",
                borderLeft: `3px solid ${activeTab === "documents" ? "var(--accent)" : "transparent"}`,
                transition: "all 0.2s"
              }}
            >
              <FileText size={16} />
              <span>문서 관리</span>
            </button>

            <button
              onClick={() => setActiveTab("settings")}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                width: "100%",
                padding: "11px 14px",
                borderRadius: "8px",
                border: "none",
                cursor: "pointer",
                textAlign: "left",
                fontSize: "0.9rem",
                fontWeight: activeTab === "settings" ? "600" : "500",
                background: activeTab === "settings" ? "linear-gradient(90deg, rgba(255,255,255,0.03), transparent)" : "transparent",
                color: activeTab === "settings" ? "var(--text-main)" : "var(--text-muted)",
                borderLeft: `3px solid ${activeTab === "settings" ? "var(--text-main)" : "transparent"}`,
                transition: "all 0.2s"
              }}
            >
              <Settings size={16} />
              <span>연동 설정</span>
            </button>
          </div>

          <div style={{
            padding: "12px",
            borderRadius: "8px",
            background: "rgba(255, 255, 255, 0.01)",
            border: "1px solid var(--panel-border)",
            fontSize: "0.72rem",
            color: "var(--text-dim)"
          }}>
            <div>table-rag version 0.1.0</div>
            <div style={{ marginTop: "2px" }}>BAAI/bge-m3 dense embed</div>
            <div style={{ marginTop: "2px" }}>pg_trgm word_similarity</div>
          </div>
        </aside>

        {/* Right Content Panel — 컴포넌트를 언마운트하지 않고 display로 숨겨 상태(채팅 히스토리 등)를 보존 */}
        <main className="glass-panel" style={{
          flex: 1,
          padding: "24px",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          position: "relative"
        }}>
          <div style={{ display: activeTab === "chat" ? "flex" : "none", flexDirection: "column", height: "100%" }}>
            <ChatView />
          </div>
          <div style={{ display: activeTab === "documents" ? "flex" : "none", flexDirection: "column", height: "100%" }}>
            <DocumentView />
          </div>
          <div style={{ display: activeTab === "settings" ? "flex" : "none", flexDirection: "column", height: "100%" }}>
            <SettingsView />
          </div>
        </main>
      </div>
    </div>
  );
}
