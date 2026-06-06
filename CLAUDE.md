# CLAUDE.md

이 파일은 Claude Code가 이 저장소에서 작업할 때 **매 세션 읽는 컨텍스트**다.
짧고 정확하게 유지한다. 사용자와의 대화는 **한국어**로 한다.

> 세션 시작 시: `README.md` 와 이 파일을 읽고, `git status` 로 현재 상태를 파악한 뒤 작업한다.

---

## 1. 프로젝트

**table-rag** — 벡터 검색이 놓치는 표·숫자 데이터를, 파서 선택 + 표 인지 청킹 + 하이브리드 검색으로 잡아내는 한국어 RAG.

레포의 존재 이유(증명할 한 문장):

> 벡터 검색만으로는 문서 안 표·숫자가 안 잡힌다.
> Docling 파싱 + 표 인지 청킹 + 하이브리드 검색(dense+lexical, RRF)으로 그걸 **정량적으로** 해결했다.

이건 **포트폴리오/면접용** 프로젝트다. 따라서:

- **모든 기능은 측정 가능한 산출물(벤치마크 숫자)로 이어져야 한다.** 측정으로 이어지지 않는 기능 추가는 하지 않는다.
- 코드는 면접관이 30초 읽고 이해할 수 있게 명료해야 한다. **영리함보다 가독성.**

## 2. 작업 원칙 (Golden Rules)

1. **측정 우선** — 변경이 파싱/검색 품질에 영향을 주면, 그 효과를 `eval/` 로 보여준다.
2. **결정 재론 금지** — 아래 §3 LOCKED 결정을 임의로 바꾸지 않는다. 바꿔야 한다고 판단되면 **먼저 사용자에게 근거와 함께 질문**한다.
3. **의존성 최소화** — 새 라이브러리 추가 전 반드시 사용자 승인. **LangChain/LlamaIndex 등 무거운 RAG 프레임워크 도입 금지** (직접 구현이 학습·면접 목적).
4. **변경 후 검증** — 코드를 바꾸면 §7 검증 명령(test/lint) 통과를 확인한다. 무거운 의존성 없는 측정 코어(`src/parse/base.py`)는 항상 테스트로 보호한다.

## 3. LOCKED 기술 결정 (근거 포함 — 임의 변경 금지)

| 영역 | 선택 | 근거 |
| --- | --- | --- |
| 벡터 저장/검색 | **PostgreSQL + pgvector (HNSW, cosine)** | 단일 스토어. 별도 벡터 DB 운영 부담 제거. |
| 임베딩 | **bge-m3 / dense 1024차원** | dense·sparse·multi-vector를 한 모델에서 → 하이브리드 최적, 한국어 최상위. |
| 어휘 검색 | **pg_trgm** | contrib 기본 포함, 형태소 분석기 불필요, 숫자열 부분매칭에 강함. |
| 융합 | **RRF (k=60)** | 점수 스케일 정규화 불필요, 순위 기반이라 튜닝 최소. |
| 파서 | **Docling** (vs MarkItDown 비교군) | TableFormer로 표 구조 보존. MarkItDown은 경량 대조군. |
| API | **FastAPI** | Phase 4 서비스화. |
| LLM | **Ollama (qwen2.5)** / API 선택 | 로컬 추론 기본. |

## 4. 환경 & DB 셋업 (Windows + Docker Desktop)

### 작업 환경 전제

- **OS: Windows + Docker Desktop (WSL2 백엔드)**. 모든 docker 명령은 Docker Desktop이 실행 중이어야 동작.
- Python **3.11+**. 가상환경 활성화:
  - PowerShell: `.\.venv\Scripts\Activate.ps1`
  - (Git Bash/WSL: `source .venv/bin/activate`)
- GPU(선택): RTX 2070 Super 보유. bge-m3는 기본 **CPU**로 동작(느릴 뿐 문제없음). GPU 쓰려면 CUDA용 torch를 별도 설치. **없어도 진행 가능.**
- 셸: 명령은 **PowerShell 기준**으로 적는다. `make` 는 Windows 기본 미설치이므로 §7의 원시 명령을 쓰거나 Git Bash/WSL에서 make 사용.
- 프로젝트는 Windows 사용자 폴더 아래(예: `C:\Users\<id>\...`)에 두면 Docker Desktop의 파일 공유가 기본 동작해 bind mount(`db/init.sql`)가 문제없이 잡힌다.

### DB 처음부터 셋업 (검증 포함)

Docker Desktop이 떠 있는 상태에서, 프로젝트 루트에서:

```powershell
# 1) 컨테이너 기동 — pgvector + pg_trgm 자동 설치, db/init.sql 자동 실행
docker compose up -d

# 2) 상태 확인 (STATUS 가 healthy 될 때까지 잠시 대기)
docker compose ps

# 3) 확장 설치 확인 — 목록에 vector, pg_trgm 둘 다 보여야 정상
docker exec -it table-rag-db psql -U rag -d ragdb -c "\dx"

# 4) 스키마 확인 — documents, chunks 테이블이 보여야 정상
docker exec -it table-rag-db psql -U rag -d ragdb -c "\dt"

# (선택) psql 대화형 접속
docker exec -it table-rag-db psql -U rag -d ragdb
```

접속 정보: host `localhost`, port `5432`, db `ragdb`, user/pw `rag` / `rag`.
GUI(DBeaver/pgAdmin)로 붙어도 된다.

### DB 초기화/리셋

```powershell
docker compose down -v    # 볼륨까지 삭제 → 다음 up 때 init.sql 재실행됨
docker compose up -d
```

## 5. 저장소 구조

```
table-rag/
├── CLAUDE.md               # 이 파일
├── README.md               # 프로젝트 서사 + 벤치마크 표(채우는 중)
├── pyproject.toml          # 의존성 + ruff/pytest 설정 (canonical)
├── Makefile                # db / test / lint / compare  (make 가능 환경용)
├── .gitattributes          # 줄바꿈 정규화 (.sql 등은 LF 강제)
├── docker-compose.yml      # PostgreSQL + pgvector + pg_trgm
├── db/init.sql             # 확장 + 스키마 (chunk_type 으로 표/본문 구분)
├── eval/
│   ├── golden_set.jsonl    # 표·숫자 중심 평가 골든셋
│   └── run_eval.py         # (Phase 3) vector-only vs hybrid 비교 — 미구현
├── src/
│   ├── config.py           # pydantic-settings
│   ├── parse/              # [Phase 1] 파서 비교
│   │   ├── base.py         #   측정 코어 (무거운 의존성 0, 테스트로 보호)
│   │   ├── docling_parser.py
│   │   ├── markitdown_parser.py
│   │   └── compare.py      #   CLI: 둘 다 돌려 parser_comparison.md 생성
│   ├── index/              # [Phase 2] 미구현
│   │   ├── chunker.py      #   표 인지 청킹
│   │   ├── embedder.py     #   bge-m3 임베딩
│   │   └── ingest.py       #   파싱→청킹→임베딩→적재
│   ├── search/
│   │   └── hybrid.py       # ★ RRF 하이브리드 검색 (프로젝트 코어, 구현됨)
│   └── api/main.py         # [Phase 4] 미구현
└── tests/
    └── test_parse_metrics.py
```

## 6. 로드맵 / 현재 상태

- [x] **Phase 0** — 스캐폴드, DB 스키마, `search/hybrid.py`(RRF), 골든셋 포맷
- [x] **Phase 1** — 파서 비교 하니스(`src/parse/`), 측정 코어 테스트 통과
      · 남은 일(사용자 몫): 실제 PDF로 실측 → `eval/parser_comparison.md` 채우기 → README 근거 갱신
- [ ] **Phase 2** ← **다음 작업**
      · `index/chunker.py`: 표 인지 청킹. 표는 1청크로 유지하고 섹션 헤더/캡션을 컨텍스트로 부착. `chunk_type='table'|'text'` 부여.
      · `index/embedder.py`: bge-m3로 dense(1024) 임베딩. 무거운 import는 함수 내부 지연.
      · `index/ingest.py`: 파서→청커→임베더→`documents`/`chunks` 적재. CLI: `python -m src.index.ingest <경로>`
      · 완료 기준: `hybrid.py` 가 실제 데이터로 동작.
- [ ] **Phase 3** — `eval/run_eval.py`: vector-only vs hybrid vs +table-aware 를 골든셋으로 측정(Recall@k·MRR·숫자 정답률) → README 벤치마크 표 채우기. **이게 면접 무기 완성 지점.**
- [ ] **Phase 4** — `api/main.py`(FastAPI) + 최소 데모.

## 7. 명령어

`make` 가 되는 환경(Git Bash/WSL)과, Windows PowerShell 원시 명령을 병기한다.

| 작업 | make (Git Bash/WSL) | Windows PowerShell |
| --- | --- | --- |
| 의존성 설치 | `make setup` | `pip install -e ".[dev]"` |
| DB 기동 | `make db` | `docker compose up -d` |
| DB 종료 | `make db-down` | `docker compose down` |
| DB 완전 리셋 | — | `docker compose down -v` |
| 테스트 | `make test` | `pytest -q` |
| 린트 | `make lint` | `ruff check .` |
| 파서 비교 | `make compare PDF=data/samples/ir_2023.pdf` | `python -m src.parse.compare data/samples/ir_2023.pdf` |

> Phase 2 이후: `python -m src.index.ingest data/samples/`, `python -m eval.run_eval`
> 경로는 Windows에서도 슬래시(`/`)로 적으면 python·docker 모두 정상 동작.

## 8. 코딩 컨벤션

- Python **3.11+**, 타입힌트 필수, `dataclass` 선호.
- 한국어 주석 OK. 단 공개 함수 docstring은 간결하게.
- **무거운 import(`docling`, `FlagEmbedding`, `torch`)는 함수 내부 지연 import.** 측정/유틸 코어가 그것 없이도 import 되게 유지한다 (테스트·CI 속도).
- **SQL은 파라미터 바인딩만.** 쿼리에 f-string/문자열 포매팅으로 값 주입 금지.
- 새 모듈에는 가능한 한 가벼운 단위 테스트를 같이 둔다.
- `ruff check .` 통과.

## 9. 함정 (이미 발견됨 — 반복하지 마라)

### 환경 / Docker (Windows)

- **init.sql 은 데이터 볼륨이 비어 있을 때(첫 생성) 단 한 번만 실행된다.** `db/init.sql` 을 바꿨는데 반영이 안 되면, 컨테이너 재시작으론 안 되고 **`docker compose down -v` 로 볼륨을 지운 뒤 다시 `up`** 해야 한다.
- **`make` 는 Windows 기본 미설치.** PowerShell에서는 §7의 원시 명령을 쓰거나, Git Bash/WSL에서 make 사용.
- **줄바꿈(CRLF):** 컨테이너는 Linux다. `.gitattributes` 로 `*.sql`/`*.sh`/`Makefile` 은 LF로 강제되어 있다. 새로 추가하는 컨테이너용 스크립트도 LF 유지.
- Docker Desktop이 꺼져 있으면 모든 docker 명령이 실패한다. 먼저 실행 여부 확인.
- bge-m3는 기본 CPU 추론. 첫 실행 시 모델 다운로드로 시간이 걸린다. GPU는 선택.

### 코드

- **psycopg `%(name)s` 스타일에서 pg_trgm `%` 연산자는 `%%` 로 이스케이프.** (`search/hybrid.py` 참고)
- **bge-m3 dense 차원 = 1024.** `db/init.sql` 의 `vector(1024)` 와 항상 일치시킬 것.
- **df→markdown 에 `tabulate` 쓰지 마라** (의존성 추가됨). 직접 생성 헬퍼 사용(`docling_parser._df_to_markdown` 참고).
- **pgvector는 파이썬에서 `register_vector(conn)` 호출 후에야** 리스트/배열을 vector로 바인딩한다.
- pg_trgm은 contrib 기본 포함이라 별도 빌드 불필요. 한국어 정밀도가 더 필요하면 pg_bigm/ParadeDB(pg_search) 전환은 **제안 후 승인** 사항.

## 10. Definition of Done

- **개별 변경**: 테스트 + 린트 통과 + (검색/파싱 영향 시) eval로 효과 확인.
- **Phase 완료**: 해당 산출물(코드 + 측정 결과)이 존재하고, `README.md` 의 로드맵/벤치마크가 갱신됨.

## 11. Out of Scope (하지 마라)

- 무거운 RAG 프레임워크(LangChain 등) 도입.
- 인증/멀티테넌시/프로덕션 배포 인프라 — 이 레포는 **검색 품질 증명**에 집중한다.
- UI 과투자 — Phase 4 데모는 최소한으로.
- §3 LOCKED 결정의 임의 변경.
