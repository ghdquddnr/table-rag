"""Phase 4 & 5: FastAPI 서비스.

실행: uvicorn src.api.main:app --reload --port 8000
문서: http://localhost:8000/docs
"""
from __future__ import annotations

import os
import shutil
import json
from pathlib import Path
import psycopg
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pgvector.psycopg import register_vector
from pydantic import BaseModel, Field
import ollama
import httpx

from src.config import settings
from src.index.embedder import embed
from src.search.hybrid import SearchResult, _lexical_token
from src.search.hybrid import search as hybrid_search
from src.index.ingest import ingest as run_ingest

app = FastAPI(
    title="table-rag",
    description="표·숫자 특화 한국어 하이브리드 RAG (pgvector + pg_trgm, RRF)",
    version="0.1.0",
)

# CORS Middleware 설정 (Next.js 로컬 서버와의 연동을 위함)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실무에서는 구체적인 Next.js 호스트 주소 기입
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 업로드 임시 디렉토리 보장
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── API 스키마 ──────────────────────────────────────────────────────────────
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


class ChatRequest(BaseModel):
    query: str
    provider: str = Field("ollama", description="'ollama' | 'openai' | 'gemini'")
    model: str = Field("gemma4:12b", description="모델명")
    api_key: str | None = Field(None, description="상용 API Key")
    api_url: str | None = Field(None, description="커스텀 API URL")
    stream: bool = Field(True, description="스트리밍 스트림 여부")


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
    """질문 텍스트를 받아 RRF 하이브리드 검색 결과를 반환한다."""
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


# ── Phase 5 문서 관리 API ───────────────────────────────────────────────────
@app.get("/api/documents", summary="업로드된 문서 목록 조회")
def list_documents():
    """DB에 적재된 모든 문서의 리스트와 각 문서별 chunk 개수를 반환합니다."""
    try:
        with psycopg.connect(settings.db_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT d.id, d.source, d.parser, d.created_at, COUNT(c.id) as chunk_count
                    FROM documents d
                    LEFT JOIN chunks c ON d.id = c.document_id
                    GROUP BY d.id
                    ORDER BY d.created_at DESC
                """)
                rows = cur.fetchall()

        docs = []
        for row in rows:
            source_path = Path(row[1])
            docs.append({
                "id": row[0],
                "filename": source_path.name,
                "source": row[1],
                "parser": row[2],
                "created_at": row[3].isoformat() if row[3] else None,
                "chunk_count": row[4]
            })
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 목록 조회 실패: {str(e)}")


@app.post("/api/documents/upload", summary="PDF 문서 업로드 및 파싱 적재")
async def upload_document(
    file: UploadFile = File(...),
    parser: str = Form("docling")  # 'docling' | 'markitdown'
):
    """PDF 파일을 업로드받아 서버 로컬에 저장 후, 선택된 파서로 인제스트를 구동합니다."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일 포맷만 지원합니다")

    file_path = UPLOAD_DIR / file.filename
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 임시 저장 오류: {str(e)}")

    try:
        # 동기 인제스트 구동 (파싱 -> 청킹 -> 임베딩 -> DB적재)
        chunk_count = run_ingest(file_path, parser=parser)
        if chunk_count == 0:
            raise HTTPException(status_code=500, detail="문서 파싱/청킹 결과가 비어 있거나 처리되지 못했습니다.")
        return {
            "status": "success",
            "filename": file.filename,
            "parser": parser,
            "chunk_count": chunk_count
        }
    except Exception as e:
        # 적재 실패 시 임시 파일 삭제
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"문서 인제스트 처리 실패: {str(e)}")


@app.delete("/api/documents/{id}", summary="문서 삭제 (Cascade)")
def delete_document(id: int):
    """문서를 데이터베이스에서 삭제하고 cascade 연동된 chunk를 일괄 제거합니다."""
    try:
        with psycopg.connect(settings.db_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT source FROM documents WHERE id = %s", (id,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="해당 문서를 찾을 수 없습니다")
                
                source_path = Path(row[0])
                cur.execute("DELETE FROM documents WHERE id = %s", (id,))
                
                # 업로드 디렉토리 안의 원본 파일인 경우 디스크 청소
                if UPLOAD_DIR.resolve() in source_path.resolve().parents and source_path.exists():
                    try:
                        source_path.unlink()
                    except Exception:
                        pass
                        
        return {"status": "ok", "message": f"문서 ID: {id} 및 청크가 성공적으로 제거되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 삭제 처리 실패: {str(e)}")


# ── Phase 5/6 RAG 채팅 API ──────────────────────────────────────────────────
@app.post("/api/chat", summary="RAG 대화형 검색 및 생성")
async def chat(req: ChatRequest):
    """하이브리드 검색 기반 Context를 주입하여 선택한 LLM으로 스트리밍 또는 단일 생성 답변을 전송합니다."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="질문이 비어 있습니다")

    # 1. 하이브리드 검색 수행
    try:
        emb = embed([req.query])[0]
        with psycopg.connect(settings.db_dsn) as conn:
            register_vector(conn)
            results: list[SearchResult] = hybrid_search(emb, req.query, conn, k=5)
            
            # SearchResult에 없는 caption을 DB에서 개별 조회
            chunk_ids = [r.chunk_id for r in results]
            captions = {}
            if chunk_ids:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, caption FROM chunks WHERE id = ANY(%s)",
                        (chunk_ids,)
                    )
                    captions = {row[0]: row[1] for row in cur.fetchall()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"하이브리드 검색 실패: {str(e)}")

    # 2. Context 구성 및 System Prompt 설계
    context_str = ""
    for r in results:
        header = f"[{r.section_header}] " if r.section_header else ""
        caption_val = captions.get(r.chunk_id)
        caption = f"({caption_val}) " if caption_val else ""
        context_str += f"--- Chunk ID: {r.chunk_id} ({r.chunk_type}) {header}{caption}---\n{r.content}\n\n"

    system_prompt = (
        "당신은 제공된 문서를 바탕으로 사용자의 질문에 답변하는 인공지능 어시스턴트입니다.\n"
        "반드시 다음 제공된 [참조 정보]만을 사용하여 답변해 주세요. 문서에 없는 내용은 추측하거나 지어내지 마세요.\n"
        "표(Table) 데이터를 분석할 때는 행과 열의 관계를 정확히 파악하여 답변해 주세요.\n"
        "답변은 한국어로 친절하고 정확하게 작성해 주세요.\n\n"
        "[참조 정보]\n"
        f"{context_str}"
    )

    refs = [
        {
            "chunk_id": r.chunk_id,
            "chunk_type": r.chunk_type,
            "content": r.content,
            "section_header": r.section_header,
            "caption": captions.get(r.chunk_id),
            "score": r.score
        }
        for r in results
    ]

    # 3. LLM API 연동 및 응답 생성
    if req.provider == "ollama":
        host = req.api_url or settings.ollama_base_url
        if req.stream:
            async def generate_ollama():
                # 스트리밍 시 메타데이터를 첫 패킷으로 송신
                yield f"data: {json.dumps({'type': 'metadata', 'references': refs}, ensure_ascii=False)}\n\n"
                try:
                    client = ollama.AsyncClient(host=host)
                    async for chunk in await client.chat(
                        model=req.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": req.query}
                        ],
                        stream=True
                    ):
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield f"data: {json.dumps({'type': 'content', 'text': content}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'text': f'Ollama 에러: {str(e)}'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate_ollama(), media_type="text/event-stream")
        else:
            try:
                client = ollama.Client(host=host)
                resp = client.chat(
                    model=req.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": req.query}
                    ],
                    stream=False
                )
                answer = resp.get("message", {}).get("content", "")
                return {"response": answer, "references": refs}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Ollama 호출 실패: {str(e)}")

    elif req.provider == "openai":
        url = req.api_url or "https://api.openai.com/v1/chat/completions"
        if not req.api_key:
            raise HTTPException(status_code=400, detail="OpenAI API Key가 누락되었습니다")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {req.api_key}"
        }
        payload = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.query}
            ],
            "stream": req.stream
        }

        if req.stream:
            async def generate_openai():
                yield f"data: {json.dumps({'type': 'metadata', 'references': refs}, ensure_ascii=False)}\n\n"
                try:
                    async with httpx.AsyncClient() as client:
                        async with client.stream("POST", url, headers=headers, json=payload, timeout=60.0) as response:
                            if response.status_code != 200:
                                error_text = await response.aread()
                                yield f"data: {json.dumps({'type': 'error', 'text': f'OpenAI 에러 ({response.status_code}): {error_text.decode()}'}, ensure_ascii=False)}\n\n"
                                return
                            async for line in response.iter_lines():
                                if not line:
                                    continue
                                if line.startswith("data: "):
                                    data_str = line[6:].strip()
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        data_json = json.loads(data_str)
                                        content = data_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                        if content:
                                            yield f"data: {json.dumps({'type': 'content', 'text': content}, ensure_ascii=False)}\n\n"
                                    except Exception:
                                        pass
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'text': f'OpenAI 연결 오류: {str(e)}'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate_openai(), media_type="text/event-stream")
        else:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, headers=headers, json=payload, timeout=60.0)
                    if resp.status_code != 200:
                        raise HTTPException(status_code=resp.status_code, detail=resp.text)
                    data = resp.json()
                    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return {"response": answer, "references": refs}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"OpenAI 호출 실패: {str(e)}")

    elif req.provider == "gemini":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="Gemini API Key가 누락되었습니다")
        
        # 스트리밍 방식과 일반 API 호출의 엔드포인트 구분
        if req.stream:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{req.model}:streamGenerateContent?key={req.api_key}"
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{req.model}:generateContent?key={req.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": f"{system_prompt}\n\n사용자 질문: {req.query}"
                        }
                    ]
                }
            ]
        }

        if req.stream:
            async def generate_gemini():
                yield f"data: {json.dumps({'type': 'metadata', 'references': refs}, ensure_ascii=False)}\n\n"
                try:
                    async with httpx.AsyncClient() as client:
                        async with client.stream("POST", url, json=payload, timeout=60.0) as response:
                            if response.status_code != 200:
                                error_text = await response.aread()
                                yield f"data: {json.dumps({'type': 'error', 'text': f'Gemini 에러 ({response.status_code}): {error_text.decode()}'}, ensure_ascii=False)}\n\n"
                                return
                            
                            buffer = ""
                            async for chunk_text in response.iter_text():
                                buffer += chunk_text
                                brace_count = 0
                                in_string = False
                                start_idx = 0
                                idx = 0
                                while idx < len(buffer):
                                    char = buffer[idx]
                                    if char == '"' and (idx == 0 or buffer[idx-1] != '\\'):
                                        in_string = not in_string
                                    if not in_string:
                                        if char == '{':
                                            if brace_count == 0:
                                                start_idx = idx
                                            brace_count += 1
                                        elif char == '}':
                                            brace_count -= 1
                                            if brace_count == 0:
                                                obj_str = buffer[start_idx:idx+1]
                                                try:
                                                    obj = json.loads(obj_str)
                                                    text = obj["candidates"][0]["content"]["parts"][0]["text"]
                                                    yield f"data: {json.dumps({'type': 'content', 'text': text}, ensure_ascii=False)}\n\n"
                                                except Exception:
                                                    pass
                                                buffer = buffer[idx+1:]
                                                idx = -1
                                    idx += 1
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'text': f'Gemini 연결 오류: {str(e)}'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate_gemini(), media_type="text/event-stream")
        else:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=payload, timeout=60.0)
                    if resp.status_code != 200:
                        raise HTTPException(status_code=resp.status_code, detail=resp.text)
                    data = resp.json()
                    answer = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    return {"response": answer, "references": refs}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Gemini 호출 실패: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 LLM 제공자입니다: {req.provider}")


# ── 기존 데모 페이지 ─────────────────────────────────────────────────────────
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
