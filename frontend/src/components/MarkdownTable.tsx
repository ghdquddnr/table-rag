"use client";

import React from "react";

interface MarkdownTableProps {
  content: string;
}

export default function MarkdownTable({ content }: MarkdownTableProps) {
  // 테이블 구분자(|)가 없는 일반 본문 텍스트는 pre로 렌더링
  if (!content.includes("|")) {
    return (
      <pre style={{ 
        margin: 0, 
        whiteSpace: "pre-wrap", 
        fontFamily: "var(--font-mono)", 
        fontSize: "0.82rem",
        lineHeight: "1.5",
        color: "#d1d5db"
      }}>
        {content}
      </pre>
    );
  }

  const lines = content.split("\n").map(l => l.trim()).filter(l => l.length > 0);
  const tableLines = lines.filter(l => l.startsWith("|") && l.endsWith("|"));

  if (tableLines.length < 2) {
    return (
      <pre style={{ 
        margin: 0, 
        whiteSpace: "pre-wrap", 
        fontFamily: "var(--font-mono)", 
        fontSize: "0.82rem",
        lineHeight: "1.5",
        color: "#d1d5db"
      }}>
        {content}
      </pre>
    );
  }

  let parsedTable: { headers: string[]; rows: string[][] } | null = null;
  let isParseFailed = false;

  try {
    // 헤더 행 파싱 (앞뒤의 |를 제외하고 split)
    const headers = tableLines[0]
      .split("|")
      .slice(1, -1)
      .map(cell => cell.trim());

    // 두 번째 행이 구분자 행인지 검증 (예: |---|---|)
    const hasSeparator = tableLines[1].replace(/[\s\-\:\|]/g, "").length === 0;
    const dataStartIdx = hasSeparator ? 2 : 1;

    // 데이터 행 파싱
    const rows = tableLines.slice(dataStartIdx).map(line => {
      return line
        .split("|")
        .slice(1, -1)
        .map(cell => cell.trim());
    });

    parsedTable = { headers, rows };
  } catch {
    isParseFailed = true;
  }

  // try/catch 블록 외부에서 JSX 구성
  if (isParseFailed || !parsedTable) {
    return (
      <pre style={{ 
        margin: 0, 
        whiteSpace: "pre-wrap", 
        fontFamily: "var(--font-mono)", 
        fontSize: "0.82rem",
        color: "#f87171"
      }}>
        {content}
      </pre>
    );
  }

  return (
    <div style={{ overflowX: "auto", margin: "6px 0" }}>
      <table className="premium-table">
        <thead>
          <tr>
            {parsedTable.headers.map((h, i) => (
              <th key={i}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {parsedTable.rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td key={ci}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
