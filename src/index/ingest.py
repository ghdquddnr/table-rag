"""파싱 → 청킹 → 임베딩 → DB 적재 파이프라인.

CLI: python -m src.index.ingest <pdf_or_dir> [--parser docling|markitdown]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from src.config import settings
from src.index import chunker, embedder
from src.parse import docling_parser, markitdown_parser


def ingest(pdf_path: Path, parser: str = "docling") -> int:
    """PDF 1건을 파싱·청킹·임베딩 후 DB에 적재. 적재된 청크 수 반환."""
    print(f"[ingest] {pdf_path.name} (parser={parser})")

    if parser == "docling":
        result = docling_parser.parse(pdf_path)
    else:
        result = markitdown_parser.parse(pdf_path)

    if result.error:
        print(f"  ❌ parse error: {result.error}", file=sys.stderr)
        return 0

    chunks = chunker.chunk(result)
    print(f"  chunks: {len(chunks)} (table={sum(c.chunk_type=='table' for c in chunks)})")

    if not chunks:
        return 0

    texts = [c.content for c in chunks]
    embeddings = embedder.embed(texts)

    with psycopg.connect(settings.db_dsn) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (source, parser) VALUES (%s, %s) RETURNING id",
                (str(pdf_path), parser),
            )
            doc_id = cur.fetchone()[0]

            cur.executemany(
                """
                INSERT INTO chunks
                    (document_id, chunk_type, content, section_header, caption, embedding)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (doc_id, c.chunk_type, c.content, c.section_header, c.caption, emb)
                    for c, emb in zip(chunks, embeddings, strict=True)
                ],
            )
        conn.commit()

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
