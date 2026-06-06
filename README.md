# table-rag

벡터 검색이 놓치는 표·숫자 데이터를, **Docling 파싱 + 표 인지 청킹 + 하이브리드 검색(dense+lexical, RRF)** 으로 잡아내는 한국어 RAG.

> 벡터 검색만으로는 문서 안 표·숫자가 안 잡힌다.
> Docling 파싱 + 표 인지 청킹 + 하이브리드 검색(dense+lexical, RRF)으로 그걸 **정량적으로** 해결했다.

---

## 벤치마크 결과 (Phase 3)

문서: 포스코DX 2026년 1Q IR 자료 (PDF, 표 3개 포함)  
골든셋: 10개 질문 (모두 재무표 숫자 기반)  
평가 지표: Recall@k, MRR@10, 숫자정답률@5

| 지표 | vector-only | hybrid (RRF) | delta |
|------|------------|--------------|-------|
| Recall@1 | 0.700 | **1.000** | **+0.300** |
| Recall@5 | 1.000 | 1.000 | 0.000 |
| Recall@10 | 1.000 | 1.000 | 0.000 |
| MRR@10 | 0.820 | **1.000** | **+0.180** |
| 숫자정답률@5 | 1.000 | 1.000 | 0.000 |

**핵심 결과**: 숫자가 포함된 질문("부채비율 44.3%를 기록한 시점의 자산총계는?")에서 vector-only는 의미적으로 유사한 다른 표/텍스트를 먼저 반환하는 반면, hybrid는 pg_trgm `word_similarity`로 숫자 패턴을 정확히 매칭해 Recall@1 +30%p 개선.

---

## 아키텍처

```
PDF
 └─ Docling (TableFormer) ──→ Markdown (표 구조 보존)
      └─ 표 인지 청킹
            ├─ 표 → 1청크 (section_header + caption 부착)
            └─ 본문 → 800자 슬라이딩 윈도우
                  └─ bge-m3 임베딩 (dense 1024차원)
                        ├─ pgvector HNSW → dense 검색
                        └─ pg_trgm (word_similarity) → lexical 검색
                              └─ RRF (k=60) 융합 → 최종 순위
```

### LOCKED 기술 결정

| 영역 | 선택 | 근거 |
|------|------|------|
| 벡터 저장/검색 | PostgreSQL + pgvector (HNSW, cosine) | 단일 스토어, 별도 벡터 DB 불필요 |
| 임베딩 | bge-m3 dense 1024차원 | 한국어 SOTA, dense·sparse·multi-vector 지원 |
| 어휘 검색 | pg_trgm (word_similarity) | contrib 기본 포함, 숫자 부분매칭 강점 |
| 융합 | RRF (k=60) | 점수 정규화 불필요, 순위 기반 |
| 파서 | Docling (vs MarkItDown 비교군) | TableFormer로 표 구조 보존 |

---

## 설치 및 실행

### 환경 요구사항

- Python 3.11+
- Docker Desktop (Windows: WSL2 백엔드)
- GPU 선택사항 (bge-m3는 CPU로도 동작)

### 셋업

```powershell
# 의존성 설치
pip install -e ".[dev]"

# DB 기동 (pgvector + pg_trgm)
docker compose up -d

# 확장 설치 확인
docker exec table-rag-db psql -U rag -d ragdb -c "\dx"
```

### PDF 인제스트

```powershell
python -m src.index.ingest data/samples/your.pdf --parser docling
```

### 검색 테스트

```powershell
python -m src.search.hybrid "부채비율 44.3%를 기록한 시점의 자산총계는"
```

### 벤치마크 실행

```powershell
python -m eval.run_eval
```

---

## 로드맵

- [x] **Phase 0** — 스캐폴드, DB 스키마, hybrid.py (RRF), 골든셋 포맷
- [x] **Phase 1** — 파서 비교 하니스 (Docling vs MarkItDown)
- [x] **Phase 2** — 표 인지 청킹, bge-m3 임베딩, ingest 파이프라인
- [x] **Phase 3** — vector-only vs hybrid 벤치마크 → Recall@1 +0.300, MRR +0.180
- [ ] **Phase 4** — FastAPI + 최소 데모

---

## 구조

```
table-rag/
├── src/
│   ├── parse/          # Docling / MarkItDown 파서 + 비교 CLI
│   ├── index/          # 청킹 + bge-m3 임베딩 + DB 인제스트
│   ├── search/         # RRF 하이브리드 검색 (핵심)
│   └── config.py       # pydantic-settings
├── eval/
│   ├── golden_set.jsonl
│   └── run_eval.py
├── db/init.sql         # pgvector + pg_trgm 스키마
├── docker-compose.yml
└── tests/
```
