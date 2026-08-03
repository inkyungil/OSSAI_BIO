# 개발 계획 — 질병-약물-증상 관계 탐색 검증 워크플로우

작성일 2026-08-02. 설계 근거는 [verifiable-workflow-plan.md](verifiable-workflow-plan.md).

---

## 진행 상황 (2026-08-02 기준)

**22/22 완료.**

핵심 결과 — sealed_test 33/40, PPV 1.0, 사전등록 예측 39/40 적중.
문서 목록은 [relation-workflow/README.md](relation-workflow/README.md)에 있다.

| # | 태스크 | 상태 |
| ---: | --- | --- |
| 1 | 패키지 뼈대 | 완료 |
| 2 | 도메인 무관 코드 복사 | 완료 — 복사한 문자열 함수가 원본과 값 완전 일치 확인 |
| 3 | 노트 코퍼스 108건 | 완료 |
| 4 | 후보 재계산·층화 | 완료 — 원본 엣지 67개 100% 재현 |
| 5 | 라벨링 틀 | 완료 |
| 6 | 정답 라벨 + 주입 3건 | 완료 — 규칙 유도 초안(`label_origin: rule-draft`) |
| 7 | RelationVerdict 스키마 | 완료 |
| 8 | 관계 채점기 | 완료 |
| 9 | DeepEval 지표 | 완료 |
| 10 | 입력 빌더·프롬프트 | 완료 |
| 11 | 모델 재선정 | 완료 — `openai/gpt-oss-20b` |
| 12 | config 2종 | 완료 |
| 13 | live 실행 스크립트 | 완료 |
| 14 | replay 경로 | 완료 |
| 15 | development 실행·프롬프트 조정 | 완료 — 22/22, [tuning-log](relation-workflow/docs/tuning-log.md) |
| 16 | validation + 운영점 선택 | 완료 — 33/41, [operating-point](relation-workflow/docs/operating-point.md) |
| — | development 층화 결함 대응 | 완료 — 안 C, sealed_test 예측 사전등록 |
| 17 | fixture 고정 + 주입 탐지 | 완료 — 103건 replay 일치, 주입 3/3 탐지·저항 |
| 18 | 근거 절제 XAI 구현 | 완료 — 충분성·필요성 + 충실도 4분류 |
| 19 | 절제 실행·병합 | 완료 — 38건, DECORATIVE 0건 |
| 20 | sealed_test 최종 1회 | 완료 — 33/40, 예측 적중 39/40 |
| 21 | 대시보드 확장 | 완료 — 자립 HTML, 외부 요청 0 |
| 22 | 설계 워크시트 | 완료 — ①~⑦ + 게이트 3 |

### 확정된 결정

- **정답 기준 (A) 노트 진술 기준** — 의학 지식으로 채우지 않는다. 그 결과 `treats`
  정답이 0건이며, 이는 원본 그래프의 `treats` 37건이 노트 근거가 없다는 발견 자체다.
- **보류 경계는 `data/labeling_rules.py` 현행 규칙 유지** — 병력 나열·복용 사실·증상
  호전은 확신 있는 `no_relation`이고, 처방 "고려"와 hedge만 보류다.
- 모델 `nvidia_nim/openai/gpt-oss-20b` (지연 4~5s, code fence 없음). 선정 근거 수치는
  `configs/relation-nim.yaml` 주석에 있다.
- `max_output_tokens` 1500 (500은 잘림을 일으켰다).

### #16에서 나온 갈림길

validation 41건 중 실패 8건이 **development가 한 번도 담지 않은 두 문형**에 정확히
몰렸다(PRESENTED 단독 5건, HEDGE 단독 3건). development가 담은 네 문형은 100% 통과,
안 담은 두 문형은 0% 통과다. sealed_test 40건도 같은 문형을 8건(20%) 담고 있다.

이것은 프롬프트 결함이 아니라 **#4·#6의 층화 결함**이다. development를 문형 기준으로
층화하지 않고 support 기준으로만 나눈 것이 원인이다.

이 발견으로 프롬프트를 고치면 validation이 선택셋으로 변질된다(`day5 p37-38`). 그래서
`prompts/relation-verdict.md`는 손대지 않았다. 선택지는 셋이다.

| 안 | 내용 | 비용 | sealed_test 결과 |
| --- | --- | --- | --- |
| A | 그대로 진행 | 0 | 약 32/40 예상. 실패 원인이 문서로 설명됨 |
| B | 미라벨 후보에서 두 문형 케이스를 새로 뽑아 development를 다시 구성 → 프롬프트 재조정 → validation 재실행 | 라벨링 10~15건 + live 60여 건 재실행 | 미검증 문형이 없어짐 |
| C | 결함을 그대로 두고 sealed_test 실행 후, 실패를 **예측된 실패**로 보고 | 0 | A와 같되 예측을 먼저 기록해 검증 |

교육 자료로서는 A/C가 더 나을 수 있다 — "split 층화를 문형 기준으로 하지 않으면
무슨 일이 생기는가"의 실물 사례가 되기 때문이다. B는 시스템 품질이 목적일 때 맞다.

**→ C로 결정.** sealed_test 실행 전에 케이스 단위 예측을 등록했다
([sealed-test-prediction](relation-workflow/docs/sealed-test-prediction.md),
`data/sealed-test-prediction.json`). 예측 task_success 0.80, 실패 8건의 sample_id까지
지정돼 있다. #20 실행 후 `register_sealed_prediction.py check`로 대조한다.
프롬프트는 손대지 않는다.

### 위치와 실행 환경

2026-08-03에 `OSSAI-26-1/bio/`에서 **`C:\app\bio` 독립 저장소로 분리**했다. 이력은
`git subtree split`으로 그대로 가져왔다.

- 파이썬은 이 저장소의 `.venv` (`requirements.txt`로 재현). OSSAI의 venv를 쓰지 않는다.
- API key는 저장소 루트 `.env`. `load_project_env()`가 프로젝트 폴더에서 위로 두
  단계까지 찾고 **어느 파일을 읽었는지 돌려준다.** 분리 전에는 이 함수가 없는 경로를
  보고 조용히 넘어갔는데, 의존성 하나가 인자 없는 `load_dotenv()`로 상위 폴더의
  다른 프로젝트 `.env`를 우연히 집어서 동작하고 있었다. 옮기면서 드러난 결함이다.
- `day6/`는 강의 자료 72MB라 `.gitignore`에 있다. 저장소에 넣으려면 그 줄을 지운다.

### 재시작할 때

세션을 새로 열면 이 문서와 `relation-workflow/docs/tuning-log.md`를 먼저 읽는다.
생성물(`local-data/`, `reports/`)은 디스크에 남아 있으므로 데이터 준비를 다시 돌릴
필요가 없다. 단, `prepare_relation_notes.py`를 다시 돌리면 주입 노트가 날아간다.

리포트는 split별로 갈라 둔다 — 관찰값만 `reports/relation-nim/observations.jsonl`에
함께 쌓고(`--resume`의 근거), 채점 산출물은 `development/`, `validation/`,
`operating-point/` 아래로 들어간다. 한 요약에 두 split이 섞이면 규율을 감사할 수 없다.

---

## 0. 원칙

**기존 `src/verifiable_ai_workflow/`는 수정하지 않는다.** 읽기 전용 참조로만 쓰고, 필요한 코드는
출처 주석과 함께 복사한다. bio는 `relation-workflow/` 자립 프로젝트로 만든다.

의존성은 루트 `.venv`를 그대로 재사용한다. litellm·pydantic·deepeval·pyyaml·python-dotenv·
pytest·ruff가 이미 설치돼 있고, 텍스트 도메인이라 pypdfium2는 필요 없다. 루트 `pyproject.toml`도
건드리지 않고 scripts에서 `sys.path`를 부트스트랩한다.

```
relation-workflow/
├── src/bio_relation_workflow/
│   ├── config/          settings(NoteSettings), secrets      ← 복사 + 수정
│   ├── schemas/         relation.py (RelationVerdict 등)      ← 신규
│   ├── preprocessing/   notes.py (노트 코퍼스 로더)            ← 신규
│   ├── providers/       base, recorded, litellm_provider      ← 복사, 수정 없음
│   ├── workflow/        note_inputs, runner                   ← 신규
│   ├── evaluation/      text_metrics, relation_scoring,
│   │                    deepeval_runner                       ← 복사 + 신규
│   └── xai/             ablation.py                           ← 신규
├── scripts/
├── configs/             relation.yaml, relation-nim.yaml
├── prompts/             relation-verdict.md
├── data/cases/          bio-relation.yaml (라벨링 결과)
└── tests/
```

산출물은 프로젝트 안에 둔다 — 노트 코퍼스·후보는 `relation-workflow/local-data/`,
실행 결과는 `relation-workflow/reports/`. 둘 다 `relation-workflow/.gitignore`로
제외하므로 루트 `.gitignore`도 건드리지 않는다.

---

## 1. 확정된 데이터 사실

`day6/relation-explorer.html`의 `const DATA`를 파싱해 확인했다.

| 항목 | 값 |
| --- | ---: |
| 중심 개체 선택지 | 12 |
| 개체 총계 | 30 (질병 12 · 약물 10 · 증상 8) |
| 그래프 엣지 (고유) | **67** |
| 노트 원문 (note_id 유일) | **108** |
| 노트에서 재계산한 개체쌍 | **212** |
| ├ support 1 | 122 |
| ├ support 2 | 64 |
| ├ support 3 | 21 |
| ├ support 4 | 4 |
| └ support 5 | 1 |
| relation 분포 | treats 37 · has_symptom 30 |
| in_reference / reference_error | 5 / 1 |

**재계산 검증 통과** — 노트 108건에서 개체 동시출현을 다시 계산하니 원본 엣지 67개가 100%
재현됐다. 이 회귀 검사를 P1-2에 코드로 박는다.

### 이전 추정에서 정정된 것

| 항목 | 이전 | 실제 |
| --- | --- | --- |
| 그래프 엣지 | 69 | **67** (`summary.kept_edges`는 69지만 `max_neighbors=10` 컷으로 2개 빠짐) |
| 노트 원문 | 확보 불확실 | **108건 확보** (원본 150 중 HTML에 실린 것) |
| 탈락 후보 | HTML에 없어 불가 | **노트에서 재계산해 122건 확보** |
| 라벨링 규모 | 60건 층화 | **100건** (67은 전수라 샘플링 편향 없음, split 3분할에 필요) |

### 과제가 시시하지 않다는 근거

노트가 템플릿 문형이라 규칙 baseline이 강하겠지만, 관계를 실제로 진술하지 않는 문장이 많다.

```
"환자는 고혈압와(과) 고지혈증 병력이 있으며 인슐린을(를) 복용 중이다"
  → 고지혈증~인슐린이 후보로 잡힘. 인슐린은 당뇨약 → no_relation

"인슐린 복용 이후 발열이(가) 호전되었으나 고지혈증 관리가 필요하다"
  → 발열~인슐린이 treats처럼 보이는 템플릿 문장 → 우연 동시출현

"…또한 베체트병 가능성도 배제할 수 없다"
  → hedge 문장 → 보류(abstain) 재료
```

인슐린이 약물 허브라 아무 질병하고나 붙는다. `day3 p11`의 흔한 개체 착시가 실데이터에 있다.

---

## 2. 데이터셋 구성

**라벨링 100건** = kept 67 전수 + support=1에서 33건(허브 개체 쌍 우선).

| split | 건수 | 용도 |
| --- | ---: | --- |
| development | 20 | 프롬프트 조정 — 여기서만 프롬프트를 고친다 |
| validation | 40 | confidence 임계값 선택 |
| sealed_test | 40 | 최종 1회 (`day5 p37-38`) |

여기에 프롬프트 주입 케이스 3건(`day5 p52`, OWASP LLM01)을 별도로 심는다.
보류 정답 목표 비율은 7~10%.

---

## 3. 단계와 태스크

전체 22개. 의존 관계는 태스크에 설정돼 있고 `/tasks`로 확인할 수 있다.

### Phase 0 — 뼈대 (반나절)

| # | 태스크 | 완료 기준 |
| ---: | --- | --- |
| 1 | relation-workflow 독립 패키지 뼈대 | `check_environment.py` import 성공 |
| 2 | 도메인 무관 코드 복사 (원본 수정 없음) | 복사한 text_metrics가 원본 테스트와 같은 값 |

### Phase 1 — 데이터 (하루, 라벨링 포함) · **임계 경로**

| # | 태스크 | 완료 기준 |
| ---: | --- | --- |
| 3 | HTML DATA에서 노트 코퍼스 108건 추출 | note_id 108, text 유일성, 개체 30 |
| 4 | 개체쌍 후보 재계산 + 층화 100건 선정 | 재계산 ∩ 원본 == 67 |
| 5 | 라벨링 YAML 틀 생성 | `build_cases`가 파싱 가능 |
| 6 | 정답 라벨링 100건 + 주입 3건 | 보류 7~10%, 층별 라벨 분포 확인 |

### Phase 2 — 계약·채점 (반나절, API 없음)

| # | 태스크 | 완료 기준 |
| ---: | --- | --- |
| 7 | RelationVerdict 스키마 | 보류에 근거 넣으면 ValidationError |
| 8 | 관계 채점기 (7지표 + 환각 4분류 태깅) | 정답/오답/보류/환각인용 단위 테스트 |
| 9 | DeepEval metric_specs 관계판 | 관계 결과로 TestRun 생성 |

### Phase 3 — 실행 경로 (반나절)

| # | 태스크 | 완료 기준 |
| ---: | --- | --- |
| 10 | 노트 입력 빌더 + 출력 계약 프롬프트 | 프롬프트가 RelationVerdict 전 필드 명시 |
| 11 | 텍스트 전용 NIM 모델 재선정 + preflight | preflight 통과, 1건 JSON 파싱 성공 |
| 12 | config 2종 (relation / relation-nim) | `load_settings` 검증 통과 |
| 13 | `run_relation_nim.py` | `--limit 1` 실행 성공 |
| 14 | replay 경로 (run / evaluate) | fixture replay가 live와 동일 결과 |

### Phase 4 — 실행과 운영점 (반나절)

| # | 태스크 | 완료 기준 |
| ---: | --- | --- |
| 15 | development 20건 실행 + 프롬프트 조정 | `schema_validity` 1.0 |
| 16 | validation 41건 실행 + 임계값 선택 | 완료 — `min_cooccur=1`, `confidence≥0.95` |
| 17 | fixture 고정 + 주입 탐지 검증 | 완료 — 3건 전부 탐지·저항, 정상 노트 오탐 0 |

### Phase 5 — XAI 절제 (반나절)

| # | 태스크 | 완료 기준 |
| ---: | --- | --- |
| 18 | 근거 절제 구현 (충분성 / 필요성) | 완료 — 4분류 + NECESSITY_VACUOUS |
| 19 | 절제 실행 및 결과 병합 | 완료 — 38건, DECORATIVE 0 |

### Phase 6 — 마무리 (반나절)

| # | 태스크 | 완료 기준 |
| ---: | --- | --- |
| 20 | sealed_test 최종 1회 | 완료 — 6항목 충족, 예측 39/40 |
| 21 | 대시보드 확장 | 완료 — 회귀 테스트로 외부 요청 0 강제 |
| 22 | 설계 워크시트 | 완료 — 체크박스 전부 충족 |

**총 3~4일** (라벨링 반나절 포함).

---

## 4. 의존 그래프

```
1 ──┬─ 2 ──┬────────────── 8 ── 9
    │      │               │
    │      └─ 7 ──┬── 8    │
    │             └─ 10 ─┐ │
    ├─ 11 ──────────────┼─┤
    └─ 12 ──────────────┴─┼── 13 ──┐
                          └── 14 ──┤
3 ── 4 ── 5 ── 6 ─────────────────┴── 15 ── 16 ──┬── 17
                                                  ├── 20 ──┬── 21
                                       18 ────────┴── 19 ──┴── 22
```

Phase 1(데이터)과 Phase 0·2·3(코드)은 **병렬 진행 가능**하다. 라벨링에 사람 시간이 드니
3 → 4 → 5를 먼저 돌려 라벨링을 시작해두고, 그 사이 코드를 만드는 것이 최단 경로다.

---

## 5. 각 단계에서 지킬 규율

설계 문서 6절의 항목이 어느 태스크에서 강제되는지.

| 규율 | 출처 | 강제 지점 |
| --- | --- | --- |
| replay ≠ 모델 성능 (evidence_kind) | day5 p53 | #13, #14 — 하드코딩 금지, observation에서 유도 |
| 임계값은 validation, test는 1회 | day5 p37-38 | #15(프롬프트만), #16(임계값), #20(1회) |
| 유병률·PPV 보고 | day3 p35-36 | #20 summary |
| 흔한 개체 착시 | day3 p11-12 | #4 허브 개체 쌍 층 |
| 프롬프트 주입 | day5 p52 | #6 케이스 작성, #17 탐지 검증 |
| 환각 4분류 | day5 p21 | #8 태깅, #20 분포 |
| 일반화 사다리 명시 | day5 p39 | #20 "SINGLE — 가설 생성 수준" |
| 두 임계값은 같은 구조 | day3 p40 | #16 min_cooccur + confidence 동시 노출 |
| 자동확정 금지 → 사람 검토 | day6 p35, day5 p51 | #16 보류 큐, #21 화면 |
| 사후 설명 ≠ 인과 | day6 p17 | #18, #19 절제로 정량화 |

---

## 6. 원본에서 복제하지 않을 것

**`scripts/evaluate_workflow.py:62`** — summary의 `evidence_kind`를 `"test_only"`로 하드코딩하고,
`run_workflow.py:22-23` 같은 provider 검사도 없다. `--config configs/nvidia-nim.yaml`로 돌리면
live 관찰값을 읽고도 summary에는 `test_only`가 찍힌다. 건별 `results.jsonl`은 맞게 남지만
실습 안내가 보라고 하는 파일은 summary.json이다.

**원본은 수정하지 않되 bio판은 처음부터 observations에서 유도한다** (#13, #14). 하필 이
커리큘럼이 `day5 p53`에서 가장 강조하는 규율이라 그대로 옮기면 안 된다.

**`scoring.py:235-244`** — 인용문을 원문 텍스트로 검증할 수 없으면 grounding 게이트를 건너뛴다.
PDF의 표·차트를 위한 예외인데, 노트 텍스트 도메인에는 그런 사각이 없으므로 bio판에서는
**게이트를 우회하지 않는다**.

---

## 7. 알려진 한계 (결과 보고 시 명시)

- 노트 108건은 원본 150건의 일부다. HTML에 실리지 않은 42건은 복구할 수 없다.
- 노트가 템플릿 문형이라 규칙 baseline이 실제보다 강하게 나올 수 있다. PMI·로그우도비
  baseline을 함께 재서 비교 기준으로 삼는다(`day3 p12`).
- 단일 분할·단일 시드 → `day5 p39` 사다리에서 **SINGLE, 가설 생성 수준**.
- 참조표는 정답이 아니라 세 번째 의견이다. 교육용이라 오류 항목이 섞여 있다
  (`reference_error_edges: 1`).
- 교육용 합성 데이터이며 임상 성능 근거가 아니다.
