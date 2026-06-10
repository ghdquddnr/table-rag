"""eval CI용 고정 fixture 생성 (백로그 #8).

지정한 문서의 청크를 dense 임베딩 포함 SQL 덤프로 내보낸다.
chunk ID는 1부터 순서대로 리매핑 — golden_set.jsonl 의 source_chunk_id 와 일치시키기 위함.
(골든셋은 최초 인제스트 시점의 chunk ID 1~N 을 참조하므로, 재인제스트로 ID가 밀려도
이 fixture 를 다시 만들면 동일한 ID 체계로 복원된다.)

실행: python -m eval.make_fixture --doc-id 6
출력: eval/fixtures/eval_chunks.sql
"""
from __future__ import annotations

import argparse
from pathlib import Path

import psycopg

from src.config import settings

OUT_PATH = Path(__file__).parent / "fixtures" / "eval_chunks.sql"


def _q(text: str | None) -> str:
    """SQL 문자열 리터럴 (작은따옴표 이스케이프). None 은 NULL."""
    if text is None:
        return "NULL"
    return "'" + text.replace("'", "''") + "'"


def make_fixture(doc_id: int) -> None:
    with psycopg.connect(settings.db_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source, parser FROM documents WHERE id = %s", (doc_id,))
            doc = cur.fetchone()
            if doc is None:
                raise SystemExit(f"document id={doc_id} 없음")
            source, parser = doc

            cur.execute(
                """
                SELECT chunk_type, content, section_header, caption, page_number,
                       embedding::text
                FROM chunks WHERE document_id = %s ORDER BY id
                """,
                (doc_id,),
            )
            chunks = cur.fetchall()

    if not chunks:
        raise SystemExit(f"document id={doc_id} 에 청크 없음")

    lines = [
        "-- eval CI fixture — eval/make_fixture.py 로 생성. 직접 수정하지 말 것.",
        f"-- 원본: document_id={doc_id} ({Path(source).name}, parser={parser})",
        "-- chunk ID 는 golden_set.jsonl 의 source_chunk_id 와 일치하도록 1부터 리매핑됨.",
        "TRUNCATE documents, chunks RESTART IDENTITY CASCADE;",
        "",
        "INSERT INTO documents (id, source, parser, status) VALUES",
        f"  (1, {_q(Path(source).name)}, {_q(parser)}, 'completed');",
        "",
    ]
    for new_id, (chunk_type, content, header, caption, page, emb) in enumerate(chunks, 1):
        page_sql = "NULL" if page is None else str(page)
        lines += [
            "INSERT INTO chunks (id, document_id, chunk_type, content, section_header, caption, page_number, embedding) VALUES",
            f"  ({new_id}, 1, {_q(chunk_type)}, {_q(content)}, {_q(header)}, {_q(caption)}, {page_sql}, {_q(emb)}::vector);",
            "",
        ]
    lines += [
        "-- 시퀀스를 fixture 이후 값으로 보정",
        f"SELECT setval('chunks_id_seq', {len(chunks)});",
        "SELECT setval('documents_id_seq', 1);",
        "",
    ]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"OK: {len(chunks)} chunks -> {OUT_PATH}")


def main() -> None:
    ap = argparse.ArgumentParser(description="eval CI용 청크 fixture 생성")
    ap.add_argument("--doc-id", type=int, required=True, help="덤프할 document id")
    args = ap.parse_args()
    make_fixture(args.doc_id)


if __name__ == "__main__":
    main()
