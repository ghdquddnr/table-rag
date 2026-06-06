"""Phase 4: FastAPI 서비스.

실행: uvicorn src.api.main:app --reload
문서: http://localhost:8000/docs
데모: http://localhost:8000/
"""
from __future__ import annotations

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pgvector.psycopg import register_vector
from pydantic import BaseModel

from src.config import settings
from src.index.embedder import embed
from src.search.hybrid import SearchResult, _lexical_token
from src.search.hybrid import search as hybrid_search

app = FastAPI(
    title="table-rag",
    description="표·숫자 특화 한국어 하이브리드 RAG (pgvector + pg_trgm, RRF)",
    version="0.1.0",
)


# ── 스키마 ──────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str
    k: int = 5


class SearchHit(BaseModel):
    chunk_id: int
    chunk_type: str
    content: str
    section_header: str | None
    score: float


class SearchResponse(BaseModel):
    query: str
    lexical_token: str | None
    hits: list[SearchHit]


# ── 엔드포인트 ───────────────────────────────────────────────────────────────
@app.get("/health", summary="DB 연결 상태 확인")
def health() -> dict:
    try:
        with psycopg.connect(settings.db_dsn) as conn:
            row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        return {"status": "ok", "chunk_count": row[0] if row else 0}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/search", response_model=SearchResponse, summary="하이브리드 검색")
def search(req: SearchRequest) -> SearchResponse:
    """질문 텍스트를 받아 RRF 하이브리드 검색 결과를 반환한다.

    - dense: bge-m3 1024차원 코사인 유사도
    - lexical: 질문의 숫자 토큰 → pg_trgm word_similarity
    - 융합: RRF k=60
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query가 비어 있습니다")
    if not 1 <= req.k <= 20:
        raise HTTPException(status_code=400, detail="k는 1~20 사이여야 합니다")

    emb = embed([req.query])[0]
    with psycopg.connect(settings.db_dsn) as conn:
        register_vector(conn)
        results: list[SearchResult] = hybrid_search(emb, req.query, conn, k=req.k)

    return SearchResponse(
        query=req.query,
        lexical_token=_lexical_token(req.query),
        hits=[
            SearchHit(
                chunk_id=r.chunk_id,
                chunk_type=r.chunk_type,
                content=r.content,
                section_header=r.section_header,
                score=round(r.score, 6),
            )
            for r in results
        ],
    )


# ── 최소 데모 페이지 ─────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def demo() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>table-rag demo</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 860px; margin: 40px auto; padding: 0 16px; color: #1a1a1a; }
  h1   { font-size: 1.4rem; margin-bottom: 4px; }
  .sub { color: #666; font-size: .85rem; margin-bottom: 20px; }
  .row { display: flex; gap: 8px; margin-bottom: 24px; }
  input  { flex: 1; padding: 9px 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }
  button { padding: 9px 20px; background: #2563eb; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 1rem; }
  button:hover { background: #1d4ed8; }
  .token { font-size: .8rem; color: #888; margin-bottom: 12px; }
  .token b { color: #2563eb; }
  .card  { border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px; }
  .card-head { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; font-size: .85rem; color: #555; }
  .badge { padding: 2px 8px; border-radius: 12px; font-size: .75rem; font-weight: 600; }
  .table { background: #eff6ff; color: #1e40af; }
  .text  { background: #f0fdf4; color: #166534; }
  .score { margin-left: auto; color: #888; }
  pre  { margin: 0; white-space: pre-wrap; font-size: .82rem; color: #111; font-family: 'Menlo', 'Consolas', monospace; }
  .err { color: #dc2626; padding: 12px; background: #fef2f2; border-radius: 6px; }
  .none{ color: #888; text-align: center; padding: 24px; }
</style>
</head>
<body>
<h1>table-rag</h1>
<p class="sub">표·숫자 특화 한국어 하이브리드 RAG &nbsp;·&nbsp; dense (bge-m3) + pg_trgm RRF</p>

<div class="row">
  <input id="q" placeholder="예: 부채비율 44.3%를 기록한 시점의 자산총계는?" value="부채비율 44.3%를 기록한 시점의 자산총계는?">
  <button onclick="run()">검색</button>
</div>
<div id="token" class="token"></div>
<div id="results"></div>

<script>
async function run() {
  const query = document.getElementById('q').value.trim();
  if (!query) return;
  document.getElementById('results').innerHTML = '<p class="none">검색 중…</p>';
  document.getElementById('token').innerHTML = '';
  try {
    const res = await fetch('/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query, k: 5})
    });
    const data = await res.json();
    if (!res.ok) {
      document.getElementById('results').innerHTML = `<div class="err">${data.detail}</div>`;
      return;
    }
    if (data.lexical_token) {
      document.getElementById('token').innerHTML =
        `lexical token: <b>${data.lexical_token}</b> &nbsp;(pg_trgm word_similarity)`;
    }
    if (!data.hits.length) {
      document.getElementById('results').innerHTML = '<p class="none">결과 없음</p>';
      return;
    }
    document.getElementById('results').innerHTML = data.hits.map((h, i) => `
      <div class="card">
        <div class="card-head">
          <span>#${i+1}</span>
          <span class="badge ${h.chunk_type}">${h.chunk_type}</span>
          ${h.section_header ? `<span>${h.section_header}</span>` : ''}
          <span class="score">score ${h.score.toFixed(4)} &nbsp; id=${h.chunk_id}</span>
        </div>
        <pre>${h.content.slice(0, 600)}${h.content.length > 600 ? '…' : ''}</pre>
      </div>`).join('');
  } catch(e) {
    document.getElementById('results').innerHTML = `<div class="err">${e.message}</div>`;
  }
}
document.getElementById('q').addEventListener('keydown', e => { if (e.key === 'Enter') run(); });
</script>
</body>
</html>"""
