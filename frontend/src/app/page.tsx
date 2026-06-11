"use client";

import React, { useState, useEffect } from "react";
import { FileText, Settings, Database, MessageSquare, LayoutDashboard } from "lucide-react";

import DashboardView from "@/components/DashboardView";
import ChatView from "@/components/ChatView";
import DocumentView from "@/components/DocumentView";
import SettingsView from "@/components/SettingsView";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type Tab = "dashboard" | "chat" | "documents" | "settings";

const NAV_ITEMS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "dashboard", label: "대시보드", icon: <LayoutDashboard size={16} /> },
  { id: "chat", label: "RAG 채팅", icon: <MessageSquare size={16} /> },
  { id: "documents", label: "문서 관리", icon: <FileText size={16} /> },
  { id: "settings", label: "연동 설정", icon: <Settings size={16} /> },
];

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [chunkCount, setChunkCount] = useState<number>(0);

  // Ping backend on load and every 10 seconds
  useEffect(() => {
    let cancelled = false;

    const checkBackendHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        if (res.ok) {
          const data = await res.json();
          if (cancelled) return;
          setBackendOnline(true);
          setChunkCount(data.chunk_count || 0);
        } else if (!cancelled) {
          setBackendOnline(false);
        }
      } catch {
        if (!cancelled) setBackendOnline(false);
      }
    };

    checkBackendHealth();
    const interval = setInterval(checkBackendHealth, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="logo">
            <Database size={16} />
          </div>
          <div>
            <h1>table-rag</h1>
            <p>표·숫자 특화 한국어 RAG</p>
          </div>
        </div>

        <nav style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
          <div className="nav-section">메뉴</div>
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              className={`nav-item ${activeTab === item.id ? "active" : ""}`}
              onClick={() => setActiveTab(item.id)}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span className={`dot ${backendOnline === true ? "ok" : backendOnline === false ? "bad" : "idle"}`} />
            <span>
              {backendOnline === true
                ? `검색 엔진 연결됨 · 청크 ${chunkCount.toLocaleString()}개`
                : backendOnline === false
                ? "검색 엔진 오프라인"
                : "연결 확인 중..."}
            </span>
          </div>
          <div style={{ color: "var(--text-3)" }}>v0.1.0 · bge-m3 + pg_trgm</div>
        </div>
      </aside>

      {/* Content — 탭 전환 시 컴포넌트를 언마운트하지 않고 숨겨 상태(채팅 히스토리 등)를 보존 */}
      <main className="main-area">
        <div style={{ display: activeTab === "dashboard" ? "flex" : "none", flexDirection: "column", height: "100%" }}>
          <DashboardView active={activeTab === "dashboard"} onNavigate={setActiveTab} />
        </div>
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
  );
}
