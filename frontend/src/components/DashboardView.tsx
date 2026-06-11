"use client";

import React, { useState, useEffect } from "react";
import {
  FileText,
  Layers,
  Table2,
  Cpu,
  ArrowRight,
  Upload,
  MessageSquare,
  Activity,
} from "lucide-react";
import type { Tab } from "@/app/page";
import { LLMConfig, DEFAULT_CONFIG, fetchLLMConfig } from "./SettingsView";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Stats {
  documents_completed: number;
  documents_failed: number;
  chunks_total: number;
  chunks_table: number;
}

interface DocumentItem {
  id: number;
  filename: string;
  parser: string;
  created_at: string;
  status: string;
  chunk_count: number;
}

// README 벤치마크 수치 — eval CI(고정 fixture)가 PR마다 재측정하는 값과 동일
const BENCHMARK = [
  { metric: "Recall@1", vector: 0.5, hybrid: 1.0 },
  { metric: "MRR@10", vector: 0.72, hybrid: 1.0 },
  { metric: "숫자정답률@5", vector: 1.0, hybrid: 1.0 },
];

function BenchRow({ metric, vector, hybrid }: { metric: string; vector: number; hybrid: number }) {
  return (
    <div className="bench-row">
      <div className="bench-label">
        <span>{metric}</span>
        <span>
          vector {vector.toFixed(2)} · <strong style={{ color: "var(--accent-text)" }}>hybrid {hybrid.toFixed(2)}</strong>
        </span>
      </div>
      <div className="bench-track" style={{ marginBottom: "4px" }}>
        <div className="bench-fill" style={{ width: `${vector * 100}%`, background: "var(--text-3)" }} />
      </div>
      <div className="bench-track">
        <div className="bench-fill" style={{ width: `${hybrid * 100}%`, background: "var(--accent)" }} />
      </div>
    </div>
  );
}

export default function DashboardView({
  active,
  onNavigate,
}: {
  active: boolean;
  onNavigate: (tab: Tab) => void;
}) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [llmConfig, setLlmConfig] = useState<LLMConfig>(DEFAULT_CONFIG);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  // 탭이 활성화될 때마다 최신 데이터로 갱신
  useEffect(() => {
    if (!active) return;

    fetch(`${API_BASE}/api/stats`)
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        setStats(data);
        setApiOnline(data !== null);
      })
      .catch(() => setApiOnline(false));

    fetch(`${API_BASE}/api/documents`)
      .then(res => (res.ok ? res.json() : []))
      .then((data: DocumentItem[]) => setDocuments(data))
      .catch(() => {});

    fetchLLMConfig().then(setLlmConfig);
  }, [active]);

  const tableRatio =
    stats && stats.chunks_total > 0
      ? Math.round((stats.chunks_table / stats.chunks_total) * 100)
      : 0;
  const recentDocs = documents.slice(0, 5);

  return (
    <div className="view animate-fade-in">
      <div className="view-header" style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <h2>대시보드</h2>
          <p className="desc">코퍼스 현황과 하이브리드 검색 품질을 한눈에 확인합니다.</p>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button className="btn btn-ghost" onClick={() => onNavigate("documents")}>
            <Upload size={14} />
            문서 업로드
          </button>
          <button className="btn btn-primary" onClick={() => onNavigate("chat")}>
            <MessageSquare size={14} />
            채팅 시작
          </button>
        </div>
      </div>

      <div className="view-body">
        {/* KPI */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "14px" }}>
          <div className="card kpi">
            <div className="label"><FileText size={13} /> 적재 문서</div>
            <div className="value">{stats ? stats.documents_completed : "–"}</div>
            <div className="sub">
              {stats && stats.documents_failed > 0 ? `실패 ${stats.documents_failed}건 포함 안 됨` : "분석 완료 기준"}
            </div>
          </div>
          <div className="card kpi">
            <div className="label"><Layers size={13} /> 전체 청크</div>
            <div className="value">{stats ? stats.chunks_total.toLocaleString() : "–"}</div>
            <div className="sub">bge-m3 dense 1024차원 임베딩</div>
          </div>
          <div className="card kpi">
            <div className="label"><Table2 size={13} /> 표 청크</div>
            <div className="value">
              {stats ? stats.chunks_table.toLocaleString() : "–"}
              {stats && <span style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--text-3)", marginLeft: "6px" }}>{tableRatio}%</span>}
            </div>
            <div className="sub">표 구조 보존 · 1표 1청크</div>
          </div>
          <div className="card kpi">
            <div className="label"><Cpu size={13} /> 활성 LLM</div>
            <div className="value" style={{ fontSize: "1.1rem", lineHeight: "1.4", paddingTop: "4px" }}>{llmConfig.model}</div>
            <div className="sub" style={{ textTransform: "capitalize" }}>{llmConfig.provider}</div>
          </div>
        </div>

        {/* 벤치마크 + 시스템 */}
        <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: "14px", marginTop: "14px" }}>
          <div className="card card-pad">
            <div className="card-title">
              검색 벤치마크
              <span style={{ fontSize: "0.72rem", fontWeight: 400, color: "var(--text-3)", marginLeft: "auto" }}>
                골든셋 10문항 · PR마다 CI 재측정
              </span>
            </div>
            {BENCHMARK.map(b => (
              <BenchRow key={b.metric} {...b} />
            ))}
            <p style={{ fontSize: "0.76rem", color: "var(--text-3)", marginTop: "14px" }}>
              표 안 수치 질문에서 vector 검색 단독은 절반을 놓치지만, 숫자 토큰 매칭을 더한
              하이브리드(RRF)는 전 문항 rank 1을 달성합니다.
            </p>
          </div>

          <div className="card card-pad">
            <div className="card-title"><Activity size={14} /> 검색 파이프라인</div>
            <div className="status-row">
              <span className="name">
                <span className={`dot ${apiOnline === true ? "ok" : apiOnline === false ? "bad" : "idle"}`} />
                API 서버
              </span>
              <span className="value">{apiOnline === true ? "정상" : apiOnline === false ? "오프라인" : "확인 중"}</span>
            </div>
            <div className="status-row">
              <span className="name">벡터 저장소</span>
              <span className="value">pgvector · HNSW cosine</span>
            </div>
            <div className="status-row">
              <span className="name">어휘 검색</span>
              <span className="value">pg_trgm word_similarity</span>
            </div>
            <div className="status-row">
              <span className="name">순위 융합</span>
              <span className="value">RRF (k=60)</span>
            </div>
            <div className="status-row">
              <span className="name">파서</span>
              <span className="value">Docling TableFormer</span>
            </div>
          </div>
        </div>

        {/* 최근 문서 */}
        <div className="card" style={{ marginTop: "14px" }}>
          <div className="card-title" style={{ padding: "16px 20px 0", marginBottom: "10px" }}>
            최근 문서
            <button
              onClick={() => onNavigate("documents")}
              style={{
                marginLeft: "auto", background: "none", border: "none", cursor: "pointer",
                color: "var(--accent-text)", fontSize: "0.78rem", fontWeight: 500,
                display: "inline-flex", alignItems: "center", gap: "4px",
              }}
            >
              전체 보기 <ArrowRight size={12} />
            </button>
          </div>
          {recentDocs.length === 0 ? (
            <div style={{ padding: "28px 20px", textAlign: "center", color: "var(--text-3)", fontSize: "0.84rem" }}>
              아직 적재된 문서가 없습니다.{" "}
              <button
                onClick={() => onNavigate("documents")}
                style={{ background: "none", border: "none", color: "var(--accent-text)", cursor: "pointer", fontSize: "inherit", fontWeight: 600 }}
              >
                첫 PDF를 업로드
              </button>
              해 보세요.
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>파일명</th>
                  <th>파서</th>
                  <th style={{ textAlign: "right" }}>청크</th>
                  <th>상태</th>
                  <th>업로드일</th>
                </tr>
              </thead>
              <tbody>
                {recentDocs.map(doc => (
                  <tr key={doc.id}>
                    <td style={{ maxWidth: "320px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {doc.filename}
                    </td>
                    <td style={{ color: "var(--text-2)" }}>{doc.parser}</td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {doc.status === "completed" ? doc.chunk_count.toLocaleString() : "–"}
                    </td>
                    <td>
                      {doc.status === "completed" ? (
                        <span className="badge badge-text">완료</span>
                      ) : doc.status === "processing" ? (
                        <span className="badge" style={{ background: "var(--amber-soft)", color: "var(--amber)" }}>분석 중</span>
                      ) : (
                        <span className="badge" style={{ background: "var(--red-soft)", color: "var(--red)" }}>실패</span>
                      )}
                    </td>
                    <td style={{ color: "var(--text-2)" }}>{new Date(doc.created_at).toLocaleDateString("ko-KR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
