# table-rag

**PDF 표·숫자에 특화한 한국어 하이브리드 RAG.**  
Docling 파싱 + 표 인지 청킹 + pg_trgm 하이브리드 검색(RRF)으로 벡터 검색의 숫자 매칭 한계를 정량적으로 해결한 포트폴리오 프로젝트.

---

## 문제 정의

IR 보고서·통계 자료의 표 데이터는 일반 RAG 파이프라인에서 두 단계에서 실패한다.

**1단계 — 파싱 실패**: 대부분의 경량 파서(MarkItDown 등)는 PDF 표를 CID 코드나 평탄화된 문자열로 변환해 표 구조 자체가 사라진다.

**2단계 — 검색 실패**: 파싱이 성공해도 "부채비율 44.3%"처럼 짧은 수치는 임베딩 공간에서 다른 분기의 유사한 수치("44.1%", "45.7%")와 코사인 거리가 거의 동일하다. 벡터 검색만으로는 특정 수치가 담긴 청크를 rank 1에 올릴 수 없다.

---

## 해결 방법

### 1. 파서: Docling (TableFormer)

TableFormer 모델로 표 구조를 인식해 pipe-delimited 마크다운으로 보존한다.  
MarkItDown(경량 대조군)과 비교했을 때 한국어 PDF 표에서 셀 구조·수치가 그대로 추출된다.

### 2. 표 인지 청킹

```
표 블록  → 1청크 (분할 금지)
           section_header + caption을 컨텍스트로 부착
본문 블록 → 800자 슬라이딩 윈도우
```

표를 청크 경계에서 쪼개면 행 간 맥락이 깨진다. 표 전체를 하나의 청크로 유지하고 섹션 헤더와 캡션을 메타데이터로 붙여 검색 시 컨텍스트를 제공한다.

### 3. 하이브리드 검색: pg_trgm word_similarity + RRF

**핵심 발견**: `similarity(query, content)` 는 긴 자연어 쿼리에서 threshold(0.3)를 전혀 넘지 못해 lexical 채널이 항상 비어있었다.

원인은 `similarity`가 두 문자열의 trigram 합집합 대비 교집합 비율을 계산하기 때문이다. 긴 쿼리는 trigram 수가 많아 분모가 크고, 짧은 수치 하나만 공유하면 유사도가 0.04 수준으로 떨어진다.

**해결**: 질문에서 숫자 패턴을 추출해 짧은 토큰으로 변환한 뒤 `word_similarity(token, content)` 로 매칭한다. `word_similarity`는 토큰이 content의 어느 부분 문자열에 포함되는지를 측정하므로, 짧은 수치도 정확하게 해당 표 청크를 찾는다.

```python
# 숫자 토큰 추출 우선순위: 소수점 > 천단위 > 2-3자리 독립 숫자 (연도 제외)
"부채비율 44.3%를 기록한 시점의 자산총계는?"  →  token: "44.3%"
"자산총계 8,084억원 분기의 자본총계는?"       →  token: "8,084"
"영업이익이 37억원인 분기의 IT 매출은?"        →  token: "37"
```

dense + lexical 두 채널의 순위를 RRF(k=60)로 융합한다. 점수 스케일 정규화가 필요 없고 어느 한 채널이 약해도 다른 채널이 보완한다.

---

## 벤치마크 결과

문서: 포스코DX 2026년 1Q IR 자료 (재무표 3개 포함)  
골든셋: 10개 질문 (모두 수치를 포함한 재무 질문)

| 지표 | vector-only | **hybrid (RRF)** | delta |
|------|:-----------:|:----------------:|:-----:|
| Recall@1 | 0.700 | **1.000** | **+0.300** |
| Recall@5 | 1.000 | 1.000 | — |
| MRR@10 | 0.820 | **1.000** | **+0.180** |
| 숫자정답률@5 | 1.000 | 1.000 | — |

vector-only는 의미적으로 유사한 텍스트 청크를 표보다 먼저 반환하는 반면, hybrid는 수치 토큰 매칭으로 정확한 표 청크를 rank 1에 올렸다.

---

## 아키텍처

```
PDF
 └─ Docling (TableFormer)
      ├─ 표 청크  ──────────────────────────────────────────┐
      └─ 본문 청크 (800자)                                  │
            │                                              │
            └─ bge-m3 (dense 1024차원)                     │
                  ├─ pgvector HNSW ── dense rank           │
                  └─ pg_trgm word_similarity               │
                        (숫자 토큰 추출) ── lexical rank   │
                              │                            │
                              └── RRF (k=60) ─────────────┘
                                       │
                                    최종 순위
```

---

## 기술 스택 & 설계 결정

| 영역 | 선택 | 이유 |
|------|------|------|
| 파서 | **Docling** (vs MarkItDown 비교) | TableFormer로 표 셀 구조 보존. MarkItDown은 한국어 PDF에서 CID 코드 출력 |
| 벡터 저장소 | **PostgreSQL + pgvector** (HNSW, cosine) | 별도 벡터 DB 없이 단일 스토어. 운영 부담 최소화 |
| 임베딩 | **BAAI/bge-m3** (dense 1024d) | 한국어 MTEB 상위권, dense·sparse·multi-vector를 한 모델에서 지원 |
| 어휘 검색 | **pg_trgm** `word_similarity` | contrib 기본 포함, 부분 매칭으로 짧은 수치도 직접 검색 가능 |
| 융합 | **RRF** (k=60) | 점수 스케일 정규화 불필요, 순위 기반이라 채널 간 가중치 튜닝 최소 |
| API | **FastAPI** + uvicorn | 비동기 지원, 자동 Swagger 문서 |

---

## 빠른 시작

**사전 조건**: Python 3.11+, Docker Desktop

```bash
# 1. 의존성 설치
pip install -e ".[dev]"

# 2. DB 기동 (pgvector + pg_trgm 자동 설치)
docker compose up -d

# 3. PDF 인제스트
python -m src.index.ingest data/samples/report.pdf --parser docling

# 4. CLI 검색 테스트
python -m src.search.hybrid "영업이익이 37억원인 분기의 IT 매출은"

# 5. API 서버 실행
uvicorn src.api.main:app --reload --port 8000

# 6. Next.js 프론트엔드 실행
cd frontend
npm run dev
```

서버 실행 후:
- `http://localhost:3000` — 프리미엄 다크 모드 RAG 대시보드 데모 페이지 (추천)
- `http://localhost:8000` — 검색 데모 페이지 (FastAPI 빌트인 최소 HTML)
- `http://localhost:8000/docs` — Swagger UI

```bash
# 7. 벤치마크 (vector-only vs hybrid 비교)
python -m eval.run_eval
```

---

## API

```
POST /search   {"query": "부채비율 44.3%를 기록한 시점의 자산총계는?", "k": 5}
               → {query, lexical_token, hits: [{chunk_id, chunk_type, content, score}]}

GET  /health   → {"status": "ok", "chunk_count": N}
GET  /         → 검색 데모 페이지 (HTML)
GET  /docs     → Swagger UI
```

응답의 `lexical_token` 필드에서 pg_trgm이 어떤 수치를 매칭했는지 확인할 수 있다.

---

## 프로젝트 구조

```
table-rag/
├── src/
│   ├── parse/
│   │   ├── base.py            # 파서 측정 코어 (의존성 없음, 항상 테스트 가능)
│   │   ├── docling_parser.py  # Docling 파서
│   │   ├── markitdown_parser.py
│   │   └── compare.py         # CLI: 두 파서 비교 → parser_comparison.md
│   ├── index/
│   │   ├── chunker.py         # 표 인지 청킹
│   │   ├── embedder.py        # bge-m3 싱글톤 (지연 로드)
│   │   └── ingest.py          # CLI: PDF → DB 적재
│   ├── search/
│   │   └── hybrid.py          # RRF 하이브리드 검색 + 숫자 토큰 추출 ★
│   ├── api/
│   │   └── main.py            # FastAPI 앱
│   └── config.py              # pydantic-settings
├── eval/
│   ├── golden_set.jsonl        # 평가 질문 10개
│   └── run_eval.py             # vector-only vs hybrid 비교
├── tests/
│   ├── test_parse_metrics.py
│   └── test_chunker.py
├── db/init.sql                 # pgvector + pg_trgm 스키마
└── docker-compose.yml
```
