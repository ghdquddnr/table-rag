"use client";

import React, { useState, useEffect, useRef } from "react";
import { Upload, FileText, Trash2, CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";

interface DocumentItem {
  id: number;
  filename: string;
  source: string;
  parser: string;
  created_at: string;
  chunk_count: number;
}

export default function DocumentView() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [parser, setParser] = useState<"docling" | "markitdown">("docling");
  const [uploadStatus, setUploadStatus] = useState<{ type: "success" | "error"; msg: string } | null>(null);
  const [dragActive, setDragActive] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    setIsFetching(true);
    try {
      const res = await fetch("http://localhost:8000/api/documents");
      if (!res.ok) throw new Error("Failed to fetch documents");
      const data = await res.json();
      setDocuments(data);
    } catch (e) {
      console.error("Error fetching documents:", e);
    } finally {
      setIsFetching(false);
    }
  };

  useEffect(() => {
    setTimeout(() => {
      fetchDocuments();
    }, 0);
  }, []);

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
      const res = await fetch("http://localhost:8000/api/documents/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "인제스트 처리 중 오류가 발생했습니다.");
      }

      setUploadStatus({
        type: "success",
        msg: `성공! 파일: ${data.filename} (${data.chunk_count}개 청크 적재됨)`,
      });
      fetchDocuments();
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
      const res = await fetch(`http://localhost:8000/api/documents/${id}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "문서 삭제 실패");
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
    <div className="animate-fade-in" style={{ display: "grid", gridTemplateColumns: "1fr 1.5fr", gap: "24px", height: "100%" }}>
      {/* Left: Upload area */}
      <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
        <div className="glass-panel" style={{ padding: "24px" }}>
          <h3 style={{ fontSize: "1.05rem", fontWeight: "600", marginBottom: "16px" }}>신규 문서 업로드</h3>
          
          {/* Parser select */}
          <div style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "6px" }}>
              문서 분석 파서 선택
            </label>
            <div style={{ display: "flex", gap: "10px" }}>
              <button
                onClick={() => setParser("docling")}
                className={`btn ${parser === "docling" ? "btn-primary" : "btn-secondary"}`}
                style={{ flex: 1, padding: "8px", fontSize: "0.85rem" }}
              >
                Docling (표 정밀)
              </button>
              <button
                onClick={() => setParser("markitdown")}
                className={`btn ${parser === "markitdown" ? "btn-primary" : "btn-secondary"}`}
                style={{ flex: 1, padding: "8px", fontSize: "0.85rem" }}
              >
                MarkItDown (경량)
              </button>
            </div>
            <span style={{ display: "block", fontSize: "0.72rem", color: "var(--text-dim)", marginTop: "6px" }}>
              {parser === "docling" 
                ? "* AI 기반 TableFormer 모델을 구동하여 표 구조를 온전히 해독합니다." 
                : "* 가볍고 빠른 추출용 텍스트 변환 파서입니다."}
            </span>
          </div>

          {/* Drag & Drop Zone */}
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${dragActive ? "var(--primary)" : "var(--panel-border)"}`,
              borderRadius: "8px",
              padding: "36px 20px",
              textAlign: "center",
              background: dragActive ? "rgba(59, 130, 246, 0.05)" : "rgba(255, 255, 255, 0.01)",
              cursor: "pointer",
              transition: "all 0.2s",
              position: "relative",
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
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
                <RefreshCw size={36} className="animate-pulse-slow" style={{ color: "var(--primary)" }} />
                <div>
                  <div style={{ fontSize: "0.9rem", fontWeight: "600" }}>문서 분석 및 DB 적재 중...</div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "4px" }}>
                    Docling 분석은 수십 초 가량 소요될 수 있습니다.
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px" }}>
                <Upload size={36} style={{ color: dragActive ? "var(--primary)" : "var(--text-dim)" }} />
                <div>
                  <span style={{ color: "var(--primary)", fontWeight: "500" }}>PDF 파일 업로드</span> 또는 드래그
                </div>
                <span style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>
                  PDF만 지원 (최대 30MB)
                </span>
              </div>
            )}
          </div>

          {/* Status Message */}
          {uploadStatus && (
            <div
              style={{
                marginTop: "16px",
                padding: "12px",
                borderRadius: "8px",
                fontSize: "0.8rem",
                display: "flex",
                gap: "8px",
                alignItems: "center",
                background: uploadStatus.type === "success" ? "rgba(16, 185, 129, 0.08)" : "rgba(239, 68, 68, 0.08)",
                border: `1px solid ${uploadStatus.type === "success" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)"}`,
                color: uploadStatus.type === "success" ? "#34d399" : "#f87171",
              }}
            >
              {uploadStatus.type === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
              <span style={{ wordBreak: "break-all" }}>{uploadStatus.msg}</span>
            </div>
          )}
        </div>
      </div>

      {/* Right: Documents List */}
      <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h3 style={{ fontSize: "1.05rem", fontWeight: "600" }}>인제스트 문서 라이브러리</h3>
          <button 
            onClick={fetchDocuments} 
            disabled={isFetching}
            className="btn btn-secondary" 
            style={{ padding: "6px 10px", fontSize: "0.75rem" }}
          >
            <RefreshCw size={12} className={isFetching ? "animate-pulse-slow" : ""} />
            새로고침
          </button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", border: "1px solid var(--panel-border)", borderRadius: "8px", background: "rgba(0,0,0,0.1)" }}>
          {documents.length === 0 ? (
            <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--text-dim)" }}>
              <FileText size={40} style={{ opacity: 0.3, marginBottom: "10px" }} />
              <div style={{ fontSize: "0.85rem" }}>적재된 문서가 없습니다. PDF를 업로드해 주세요.</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {documents.map((doc, index) => (
                <div
                  key={doc.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "14px 16px",
                    borderBottom: index === documents.length - 1 ? "none" : "1px solid var(--panel-border)",
                    transition: "background 0.2s",
                  }}
                  onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.01)"}
                  onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}
                >
                  <div style={{ display: "flex", gap: "12px", alignItems: "center", flex: 1, minWidth: 0 }}>
                    <FileText size={20} style={{ color: "var(--primary)", flexShrink: 0 }} />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: "0.85rem", fontWeight: "500", color: "var(--text-main)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {doc.filename}
                      </div>
                      <div style={{ display: "flex", gap: "10px", fontSize: "0.75rem", color: "var(--text-dim)", marginTop: "4px" }}>
                        <span>파서: <strong style={{ color: "var(--text-muted)" }}>{doc.parser}</strong></span>
                        <span>•</span>
                        <span>청크: <strong style={{ color: "var(--primary)" }}>{doc.chunk_count}개</strong></span>
                        <span>•</span>
                        <span>업로드: {new Date(doc.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="btn btn-danger"
                    style={{ padding: "8px", borderRadius: "6px", flexShrink: 0, marginLeft: "12px" }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
