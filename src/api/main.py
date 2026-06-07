"""Phase 4 & 5: FastAPI 서비스.

실행: uvicorn src.api.main:app --reload --port 8000
문서: http://localhost:8000/docs
"""
from __future__ import annotations

import json
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import ollama
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from src.api.condense import CONDENSE_SYSTEM, build_condense_user, clean_condensed
from src.config import settings
from src.index.embedder import embed
from src.index.ingest import ingest as run_ingest
from src.search.hybrid import SearchResult, _lexical_token
from src.search.hybrid import search as hybrid_search


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ConnectionPool 생성 및 즉시 커넥션 활성화
    # pgvector 타입 등록 함수인 register_vector를 configure 인자로 전달하여 모든 커넥션에서 자동 등록
    app.state.pool = ConnectionPool(
        settings.db_dsn,
        min_size=2,
        max_size=10,
        configure=register_vector,
        open=True
    )
    yield
    app.state.pool.close()


app = FastAPI(
    title="table-rag",
    description="표·숫자 특화 한국어 하이브리드 RAG (pgvector + pg_trgm, RRF)",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware 설정 (Next.js 로컬 서버와의 연동을 위함)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실무에서는 구체적인 Next.js 호스트 주소 기입
    allow_credentials=False,
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
    search_mode: str = Field("hybrid", description="'hybrid' | 'dense'")


class SearchHit(BaseModel):
    chunk_id: int
    chunk_type: str
    content: str
    section_header: str | None
    page_number: int | None = None
    score: float


class SearchResponse(BaseModel):
    query: str
    lexical_token: str | None
    hits: list[SearchHit]


class ChatRequest(BaseModel):
    query: str
    history: list[dict] = Field([], description="대화 히스토리 (멀티턴)")
    provider: str = Field("ollama", description="'ollama' | 'openai' | 'gemini'")
    model: str = Field("gemma4:12b", description="모델명")
    api_key: str | None = Field(None, description="상용 API Key")
    api_url: str | None = Field(None, description="커스텀 API URL")
    stream: bool = Field(True, description="스트리밍 스트림 여부")
    search_mode: str = Field("hybrid", description="'hybrid' | 'dense'")
    condense: bool = Field(True, description="멀티턴 후속 질문을 독립 검색 질의로 재작성할지 여부")


# ── 엔드포인트 ───────────────────────────────────────────────────────────────
@app.get("/health", summary="DB 연결 상태 확인")
def health() -> dict:
    try:
        with app.state.pool.connection() as conn:
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
    with app.state.pool.connection() as conn:
        results: list[SearchResult] = hybrid_search(emb, req.query, conn, k=req.k, mode=req.search_mode)

    return SearchResponse(
        query=req.query,
        lexical_token=None if req.search_mode == "dense" else _lexical_token(req.query),
        hits=[
            SearchHit(
                chunk_id=r.chunk_id,
                chunk_type=r.chunk_type,
                content=r.content,
                section_header=r.section_header,
                page_number=r.page_number,
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
        with app.state.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT d.id, d.source, d.parser, d.created_at, d.status, COUNT(c.id) as chunk_count
                    FROM documents d
                    LEFT JOIN chunks c ON d.id = c.document_id
                    GROUP BY d.id, d.status
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
                "status": row[4],
                "chunk_count": row[5]
            })
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 목록 조회 실패: {str(e)}")


def _run_ingest_background(doc_id: int, file_path: Path, parser: str):
    try:
        with app.state.pool.connection() as conn:
            run_ingest(file_path, parser=parser, conn=conn, doc_id=doc_id)
    except Exception as e:
        print(f"[background-ingest] doc_id={doc_id} 실패: {str(e)}")
        # 실패 시 디스크 상의 업로드 임시 파일 정리 시도
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass


@app.post("/api/documents/upload", summary="PDF 문서 업로드 및 파싱 적재")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    parser: str = Form("docling")  # 'docling' | 'markitdown'
):
    """PDF 파일을 업로드받아 서버 로컬에 저장 후, 선택된 파서로 백그라운드 인제스트를 구동합니다."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일 포맷만 지원합니다")

    safe_name = Path(file.filename).name
    file_path = UPLOAD_DIR / safe_name
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 임시 저장 오류: {str(e)}")

    try:
        # DB 레코드를 'processing' 상태로 우선 생성
        with app.state.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO documents (source, parser, status) VALUES (%s, %s, 'processing') RETURNING id",
                    (str(file_path), parser),
                )
                doc_id = cur.fetchone()[0]
            conn.commit()
    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"문서 데이터베이스 레코드 생성 실패: {str(e)}")

    # BackgroundTasks를 이용해 비동기로 인제스트 파이프라인 구동
    background_tasks.add_task(_run_ingest_background, doc_id, file_path, parser)

    return {
        "status": "processing",
        "doc_id": doc_id,
        "filename": safe_name,
        "parser": parser
    }


@app.delete("/api/documents/{id}", summary="문서 삭제 (Cascade)")
def delete_document(id: int):
    """문서를 데이터베이스에서 삭제하고 cascade 연동된 chunk를 일괄 제거합니다."""
    try:
        with app.state.pool.connection() as conn:
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
def _retrieve_and_search(query: str, k: int = 5, mode: str = "hybrid") -> tuple[list[SearchResult], dict[int, str]]:
    emb = embed([query])[0]
    with app.state.pool.connection() as conn:
        results: list[SearchResult] = hybrid_search(emb, query, conn, k=k, mode=mode)
        
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
    return results, captions


async def _condense_query(req: ChatRequest) -> str:
    """멀티턴 후속 질문을 독립 검색 질의로 재작성한다.

    히스토리가 없거나 LLM 호출이 실패하면 원본 질의를 그대로 반환한다.
    검색에만 쓰이는 보조 호출이므로 실패가 대화를 막지 않도록 방어적으로 처리한다.
    """
    if not req.history:
        return req.query

    user_content = build_condense_user(req.history, req.query)
    messages = [
        {"role": "system", "content": CONDENSE_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    try:
        if req.provider == "ollama":
            host = req.api_url or settings.ollama_base_url
            client = ollama.AsyncClient(host=host)
            resp = await client.chat(model=req.model, messages=messages, stream=False)
            raw = resp.message.content or ""

        elif req.provider == "openai":
            if not req.api_key:
                return req.query
            url = req.api_url or "https://api.openai.com/v1/chat/completions"
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {req.api_key}"},
                    json={"model": req.model, "messages": messages, "stream": False},
                    timeout=30.0,
                )
                if resp.status_code != 200:
                    return req.query
                raw = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")

        elif req.provider == "gemini":
            if not req.api_key:
                return req.query
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{req.model}:generateContent?key={req.api_key}"
            )
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json={
                        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
                        "systemInstruction": {"parts": [{"text": CONDENSE_SYSTEM}]},
                    },
                    timeout=30.0,
                )
                if resp.status_code != 200:
                    return req.query
                raw = (
                    resp.json()
                    .get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
        else:
            return req.query
    except Exception:
        # 재작성 실패는 치명적이지 않음 → 원본 질의로 폴백
        return req.query

    return clean_condensed(raw, fallback=req.query)


@app.post("/api/chat", summary="RAG 대화형 검색 및 생성")
async def chat(req: ChatRequest):
    """하이브리드 검색 기반 Context를 주입하여 선택한 LLM으로 스트리밍 또는 단일 생성 답변을 전송합니다."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="질문이 비어 있습니다")

    # 0. 멀티턴 후속 질문을 독립 검색 질의로 재작성 (Query Condensing)
    search_query = await _condense_query(req) if req.condense else req.query
    # 원본과 달라졌을 때만 UI에 노출 (재작성 효과 시연용)
    condensed_for_meta = search_query if search_query != req.query else None

    # 1. 하이브리드 검색 수행 (재작성된 질의로 검색, 스레드풀 위임)
    try:
        results, captions = await run_in_threadpool(_retrieve_and_search, search_query, 5, req.search_mode)
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
            "page_number": r.page_number,
            "score": r.score
        }
        for r in results
    ]

    # 스트리밍 첫 패킷으로 보낼 메타데이터 (references + 재작성된 검색 질의)
    meta_json = json.dumps(
        {"type": "metadata", "references": refs, "condensed_query": condensed_for_meta},
        ensure_ascii=False,
    )

    # 3. LLM API 연동 및 응답 생성
    if req.provider == "ollama":
        host = req.api_url or settings.ollama_base_url
        if req.stream:
            async def generate_ollama():
                # 스트리밍 시 메타데이터를 첫 패킷으로 송신
                yield f"data: {meta_json}\n\n"
                try:
                    client = ollama.AsyncClient(host=host)
                    async for chunk in await client.chat(
                        model=req.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            *req.history,
                            {"role": "user", "content": req.query}
                        ],
                        stream=True
                    ):
                        content = chunk.message.content or ""
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
                        *req.history,
                        {"role": "user", "content": req.query}
                    ],
                    stream=False
                )
                answer = resp.message.content or ""
                return {"response": answer, "references": refs, "condensed_query": condensed_for_meta}
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
                *req.history,
                {"role": "user", "content": req.query}
            ],
            "stream": req.stream
        }

        if req.stream:
            async def generate_openai():
                yield f"data: {meta_json}\n\n"
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
                    return {"response": answer, "references": refs, "condensed_query": condensed_for_meta}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"OpenAI 호출 실패: {str(e)}")

    elif req.provider == "gemini":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="Gemini API Key가 누락되었습니다")
        
        # 스트리밍 방식과 일반 API 호출의 엔드포인트 구분 (스트리밍 시 alt=sse 필수)
        if req.stream:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{req.model}:streamGenerateContent?alt=sse&key={req.api_key}"
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{req.model}:generateContent?key={req.api_key}"

        # Gemini의 컨텐츠 히스토리 구조 변환
        gemini_contents = []
        for h in req.history:
            role = "model" if h.get("role") == "assistant" else "user"
            gemini_contents.append({
                "role": role,
                "parts": [{"text": h.get("content", "")}]
            })
        gemini_contents.append({
            "role": "user",
            "parts": [{"text": req.query}]
        })

        payload = {
            "contents": gemini_contents,
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            }
        }

        if req.stream:
            async def generate_gemini():
                yield f"data: {meta_json}\n\n"
                try:
                    async with httpx.AsyncClient() as client:
                        async with client.stream("POST", url, json=payload, timeout=60.0) as response:
                            if response.status_code != 200:
                                error_text = await response.aread()
                                yield f"data: {json.dumps({'type': 'error', 'text': f'Gemini 에러 ({response.status_code}): {error_text.decode()}'}, ensure_ascii=False)}\n\n"
                                return
                            
                            async for line in response.iter_lines():
                                if not line:
                                    continue
                                if line.startswith("data: "):
                                    data_str = line[6:].strip()
                                    try:
                                        data_json = json.loads(data_str)
                                        content = data_json.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                                        if content:
                                            yield f"data: {json.dumps({'type': 'content', 'text': content}, ensure_ascii=False)}\n\n"
                                    except Exception:
                                        pass
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
                    return {"response": answer, "references": refs, "condensed_query": condensed_for_meta}
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
