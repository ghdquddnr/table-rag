"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { Upload, FileText, Trash2, CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface DocumentItem {
  id: number;
  filename: string;
  source: string;
  parser: string;
  created_at: string;
  status: string;
  chunk_count: number;
}

export default function DocumentView() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isFetching, setIsFetching] = useState(true); // 마운트 직후 목록을 불러오므로 true로 시작
  const [parser, setParser] = useState<"docling" | "markitdown">("docling");
  const [uploadStatus, setUploadStatus] = useState<{ type: "success" | "error"; msg: string } | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // setState는 모두 promise 콜백 안에서만 호출 → effect 본문에서 직접 불러도 안전
  // (react-hooks/set-state-in-effect: 동기 setState만 금지, 비동기 콜백은 허용)
  const fetchDocuments = useCallback(
    () =>
      fetch(`${API_BASE}/api/documents`)
        .then(res => {
          if (!res.ok) throw new Error("Failed to fetch documents");
          return res.json();
        })
        .then((data: DocumentItem[]) => setDocuments(data))
        .catch(e => console.error("Error fetching documents:", e))
        .finally(() => setIsFetching(false)),
    []
  );

  // 사용자 액션(새로고침 버튼, 업로드 후)용: 스피너를 켜고 다시 불러온다
  const refreshDocuments = useCallback(() => {
    setIsFetching(true);
    return fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // 분석 중인 문서가 있을 경우 3초마다 상태를 자동 새로고침(폴링)
  useEffect(() => {
    const hasProcessing = documents.some(doc => doc.status === "processing");
    if (!hasProcessing) return;

    const interval = setInterval(refreshDocuments, 3000);
    return () => clearInterval(interval);
  }, [documents, refreshDocuments]);

  const handleUpload = async (file: File) => {
    if (!file.name.endsWith(".pdf")) {
      setUploadStatus({ type: "error", msg: "PDF 파일만 업로드 가능합니다." });
      return;
    }

    setIsUploading(true);
    setUploadStatus(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("parser", parser);

    try {
      const res = await fetch(`${API_BASE}/api/documents/upload`, {
        method: "POST",
        body: formData,
      });

      let errorMsg = "인제스트 처리 중 오류가 발생했습니다.";
      if (!res.ok) {
        try {
          const data = await res.json();
          errorMsg = data.detail || errorMsg;
        } catch {
          errorMsg = (await res.text()) || errorMsg;
        }
        throw new Error(errorMsg);
      }

      const data = await res.json();
      setUploadStatus({
        type: "success",
        msg: `'${data.filename}' 분석이 백그라운드에서 진행 중입니다.`,
      });
      refreshDocuments();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : "업로드 실패";
      setUploadStatus({ type: "error", msg: errorMsg });
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("문서 및 모든 추출된 청크가 데이터베이스에서 삭제됩니다. 진행하시겠습니까?")) {
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/documents/${id}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        let errorMsg = "문서 삭제 실패";
        try {
          const data = await res.json();
          errorMsg = data.detail || errorMsg;
        } catch {
          errorMsg = (await res.text()) || errorMsg;
        }
        throw new Error(errorMsg);
      }

      setDocuments(prev => prev.filter(doc => doc.id !== id));
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : "삭제 중 오류가 발생했습니다.";
      alert(errorMsg);
    }
  };

  // Drag and Drop handlers
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleUpload(e.dataTransfer.files[0]);
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleUpload(e.target.files[0]);
    }
  };

  return (
    <div className="view animate-fade-in">
      <div className="view-header">
        <h2>문서 관리</h2>
        <p className="desc">PDF를 업로드하면 파싱 → 표 인지 청킹 → 임베딩 → 적재까지 자동으로 처리됩니다.</p>
      </div>

      <div className="view-body" style={{ display: "grid", gridTemplateColumns: "minmax(300px, 380px) 1fr", gap: "14px", alignItems: "start" }}>
        {/* Upload card */}
        <div className="card card-pad">
          <div className="card-title">신규 문서 업로드</div>

          {/* Parser select */}
          <div style={{ marginBottom: "14px" }}>
            <label className="field-label">파서 선택</label>
            <div className="seg" style={{ display: "flex" }}>
              <button
                className={parser === "docling" ? "on" : ""}
                onClick={() => setParser("docling")}
                style={{ flex: 1 }}
              >
                Docling
              </button>
              <button
                className={parser === "markitdown" ? "on" : ""}
                onClick={() => setParser("markitdown")}
                style={{ flex: 1 }}
              >
                MarkItDown
              </button>
            </div>
            <p style={{ fontSize: "0.74rem", color: "var(--text-3)", marginTop: "6px" }}>
              {parser === "docling"
                ? "TableFormer 모델로 표 구조를 보존합니다. 수십 초가 소요됩니다."
                : "가볍고 빠른 텍스트 추출용 대조군 파서입니다."}
            </p>
          </div>

          {/* Drag & Drop Zone */}
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `1.5px dashed ${dragActive ? "var(--accent)" : "var(--border-strong)"}`,
              borderRadius: "var(--radius-sm)",
              padding: "32px 20px",
              textAlign: "center",
              background: dragActive ? "var(--accent-soft)" : "transparent",
              cursor: "pointer",
              transition: "border-color 0.15s, background 0.15s",
            }}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={onFileChange}
              style={{ display: "none" }}
              accept=".pdf"
            />
            {isUploading ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px" }}>
                <RefreshCw size={26} className="animate-spin" style={{ color: "var(--accent-text)" }} />
                <div>
                  <div style={{ fontSize: "0.86rem", fontWeight: 600 }}>문서 분석 및 적재 중</div>
                  <div style={{ fontSize: "0.74rem", color: "var(--text-3)", marginTop: "3px" }}>
                    Docling 분석은 수십 초 가량 소요될 수 있습니다.
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
                <Upload size={26} style={{ color: dragActive ? "var(--accent-text)" : "var(--text-3)" }} />
                <div style={{ fontSize: "0.86rem" }}>
                  <span style={{ color: "var(--accent-text)", fontWeight: 600 }}>클릭해서 선택</span>
                  <span style={{ color: "var(--text-2)" }}>하거나 끌어다 놓기</span>
                </div>
                <span style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>PDF · 최대 30MB</span>
              </div>
            )}
          </div>

          {/* Status Message */}
          {uploadStatus && (
            <div
              style={{
                marginTop: "12px",
                padding: "10px 12px",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.78rem",
                display: "flex",
                gap: "8px",
                alignItems: "flex-start",
                background: uploadStatus.type === "success" ? "var(--green-soft)" : "var(--red-soft)",
                border: `1px solid ${uploadStatus.type === "success" ? "rgba(61,214,140,0.25)" : "rgba(242,85,90,0.25)"}`,
                color: uploadStatus.type === "success" ? "var(--green)" : "var(--red)",
              }}
            >
              {uploadStatus.type === "success" ? <CheckCircle2 size={14} style={{ flexShrink: 0, marginTop: "1px" }} /> : <AlertCircle size={14} style={{ flexShrink: 0, marginTop: "1px" }} />}
              <span style={{ wordBreak: "break-all" }}>{uploadStatus.msg}</span>
            </div>
          )}
        </div>

        {/* Documents List */}
        <div className="card">
          <div className="card-title" style={{ padding: "16px 20px 0", marginBottom: "10px" }}>
            문서 라이브러리
            <button
              onClick={refreshDocuments}
              disabled={isFetching}
              className="btn btn-ghost"
              style={{ marginLeft: "auto", padding: "4px 10px", fontSize: "0.74rem" }}
            >
              <RefreshCw size={11} className={isFetching ? "animate-spin" : ""} />
              새로고침
            </button>
          </div>

          {documents.length === 0 ? (
            <div style={{ textAlign: "center", padding: "44px 20px", color: "var(--text-3)" }}>
              <FileText size={32} style={{ opacity: 0.4, marginBottom: "10px" }} />
              <div style={{ fontSize: "0.84rem" }}>적재된 문서가 없습니다. PDF를 업로드해 주세요.</div>
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
                  <th style={{ width: "44px" }}></th>
                </tr>
              </thead>
              <tbody>
                {documents.map(doc => (
                  <tr key={doc.id}>
                    <td style={{ maxWidth: "280px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
                        <FileText size={14} style={{ color: "var(--text-3)", flexShrink: 0 }} />
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {doc.filename}
                        </span>
                      </div>
                    </td>
                    <td style={{ color: "var(--text-2)" }}>{doc.parser}</td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {doc.status === "completed" ? doc.chunk_count.toLocaleString() : "–"}
                    </td>
                    <td>
                      {doc.status === "completed" ? (
                        <span className="badge badge-text">완료</span>
                      ) : doc.status === "processing" ? (
                        <span className="badge" style={{ background: "var(--amber-soft)", color: "var(--amber)", display: "inline-flex", gap: "5px" }}>
                          <RefreshCw size={9} className="animate-spin" /> 분석 중
                        </span>
                      ) : doc.status === "failed" ? (
                        <span className="badge" style={{ background: "var(--red-soft)", color: "var(--red)" }}>실패</span>
                      ) : (
                        <span className="badge" style={{ background: "var(--surface-3)", color: "var(--text-2)" }}>대기</span>
                      )}
                    </td>
                    <td style={{ color: "var(--text-2)" }}>{new Date(doc.created_at).toLocaleDateString("ko-KR")}</td>
                    <td>
                      <button onClick={() => handleDelete(doc.id)} className="btn btn-danger" style={{ padding: "5px 7px" }} title="문서 삭제">
                        <Trash2 size={13} />
                      </button>
                    </td>
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
