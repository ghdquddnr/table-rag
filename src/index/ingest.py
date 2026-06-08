"""파싱 → 청킹 → 임베딩 → DB 적재 파이프라인.

CLI: python -m src.index.ingest <pdf_or_dir> [--parser docling|markitdown]
"""
from __future__ import annotations

import argparse
import json as _json
import sys
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from src.config import settings
from src.index import chunker, embedder
from src.parse import docling_parser, markitdown_parser


def ingest(pdf_path: Path, parser: str = "docling", conn: psycopg.Connection | None = None, doc_id: int | None = None) -> int:
    """PDF 1건을 파싱·청킹·임베딩 후 DB에 적재. 적재된 청크 수 반환."""
    print(f"[ingest] {pdf_path.name} (parser={parser})")

    if parser == "docling":
        result = docling_parser.parse(pdf_path)
    else:
        result = markitdown_parser.parse(pdf_path)

    if result.error:
        print(f"  ❌ parse error: {result.error}", file=sys.stderr)
        if doc_id is not None and conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE documents SET status = 'failed' WHERE id = %s",
                        (doc_id,)
                    )
                conn.commit()
            except Exception:
                pass
        return 0

    chunks = chunker.chunk(result)
    print(f"  chunks: {len(chunks)} (table={sum(c.chunk_type=='table' for c in chunks)})")

    if not chunks:
        if doc_id is not None and conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE documents SET status = 'failed' WHERE id = %s",
                        (doc_id,)
                    )
                conn.commit()
            except Exception:
                pass
        return 0

    texts = [c.content for c in chunks]
    dense_vecs, sparse_vecs = embedder.embed_full(texts)

    # 커넥션 풀을 사용하는 경우 전달받은 conn을 이용하고, CLI 구동 등으로 없으면 새로 생성
    if conn is None:
        _conn_ctx = psycopg.connect(settings.db_dsn)
        conn = _conn_ctx.__enter__()
        register_vector(conn)
        close_conn = True
    else:
        close_conn = False

    try:
        with conn.cursor() as cur:
            if doc_id is None:
                # CLI 구동 시에는 status를 바로 completed로 인서트
                cur.execute(
                    "INSERT INTO documents (source, parser, status) VALUES (%s, %s, 'completed') RETURNING id",
                    (str(pdf_path), parser),
                )
                doc_id = cur.fetchone()[0]

            cur.executemany(
                """
                INSERT INTO chunks
                    (document_id, chunk_type, content, section_header, caption, page_number, embedding, sparse_embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        doc_id, c.chunk_type, c.content, c.section_header, c.caption,
                        c.page_number, dense,
                        _json.dumps(sparse, ensure_ascii=False) if sparse else None,
                    )
                    for c, dense, sparse in zip(chunks, dense_vecs, sparse_vecs, strict=True)
                ],
            )
            
            # 인제스트 성공 시 status를 completed로 업데이트
            cur.execute(
                "UPDATE documents SET status = 'completed' WHERE id = %s",
                (doc_id,)
            )
        conn.commit()
    except Exception as e:
        if doc_id is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE documents SET status = 'failed' WHERE id = %s",
                        (doc_id,)
                    )
                conn.commit()
            except Exception:
                pass
        raise e
    finally:
        if close_conn:
            _conn_ctx.__exit__(None, None, None)

    print(f"  OK: {len(chunks)} chunks -> DB (doc_id={doc_id})")
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDF(s) into table-rag DB")
    parser.add_argument("path", help="PDF file or directory")
    parser.add_argument("--parser", choices=["docling", "markitdown"], default="docling")
    args = parser.parse_args()

    target = Path(args.path)
    if target.is_dir():
        pdfs = list(target.glob("**/*.pdf"))
        if not pdfs:
            print(f"No PDF found under {target}", file=sys.stderr)
            sys.exit(1)
        total = sum(ingest(p, args.parser) for p in pdfs)
        print(f"\nTotal: {total} chunks ingested from {len(pdfs)} files")
    elif target.is_file():
        ingest(target, args.parser)
    else:
        print(f"Path not found: {target}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
