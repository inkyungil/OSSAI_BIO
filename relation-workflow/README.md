# 질병-약물-증상 관계 판정 workflow

임상 노트에서 뽑은 후보 개체쌍이 실제 관계인지 판정하고, 근거 인용과 보류까지 결정적으로
평가한다. 판정 근거가 실제 판단 이유였는지는 근거 절제(ablation)로 따로 측정한다.

설계 근거는 [../verifiable-workflow-plan.md](../verifiable-workflow-plan.md),
개발 순서는 [../development-plan.md](../development-plan.md)에 있다.

## 출신과 독립

원래 `OSSAI-26-1` 저장소 안 `bio/`에 있었고, 그 저장소의 `src/verifiable_ai_workflow/`
(PDF 질의응답)와 **같은 규율을 따르되 별도 패키지**로 만들었다. 도메인 무관 코드는
출처 주석과 함께 복사했고 원본은 수정하지 않았다.

지금은 `C:\app\bio`로 떨어져 나와 스스로 돌아간다. 의존성은 이 폴더의 `.venv`이고,
API key는 저장소 루트 `.env`에서 읽는다. `scripts/_bootstrap.py`가 `src/`를 import
경로에 올리므로 패키지 설치는 필요 없다. 텍스트 도메인이라 pypdfium2·pillow도 없다.

## 환경 확인

`C:\app\bio`(저장소 루트)에서 실행한다.

```bash
.venv/Scripts/python.exe relation-workflow/scripts/check_environment.py
```

## 데이터 준비 순서

순서를 지켜야 한다. 주입 노트를 합친 뒤 `prepare_relation_notes.py`를 다시 돌리면
코퍼스가 초기화된다.

```bash
P=relation-workflow/scripts
.venv/Scripts/python.exe $P/prepare_relation_notes.py       # ① 노트 108건 복원
.venv/Scripts/python.exe $P/prepare_relation_candidates.py  # ② 후보 123쌍, 층화 100건
.venv/Scripts/python.exe $P/make_labeling_template.py       # ③ 라벨링 편집 틀
.venv/Scripts/python.exe $P/draft_relation_labels.py        # ④ 문형 규칙으로 초안 채우기
.venv/Scripts/python.exe $P/merge_injection_cases.py        # ⑤ 주입 3건 합치기
.venv/Scripts/python.exe $P/prepare_relation_cases.py       # ⑥ 평가용 JSONL
```

②는 원본 그래프 엣지 67개 재현을 회귀 검사로 강제한다. 어긋나면 거기서 멈춘다.
④의 라벨은 문형 규칙에서 유도한 **초안**이며 각 건에 `label_origin: rule-draft`와
적용된 규칙이 적혀 있다. 규칙은 `data/labeling_rules.py`에 문형별로 정리돼 있다.

## 실행 순서

split 규율을 지키는 순서다. 프롬프트는 development에서만 고치고, 임계값은 validation에서만
고르며, sealed_test는 마지막에 한 번만 본다 (`day5 p37-38`).

```bash
P=relation-workflow/scripts
.venv/Scripts/python.exe $P/run_relation_nim.py --live --split development
.venv/Scripts/python.exe $P/run_relation_nim.py --live --split validation --resume
.venv/Scripts/python.exe $P/select_operating_point.py          # 운영점 선택 (validation 전용)
.venv/Scripts/python.exe $P/run_ablation_nim.py --live         # 근거 절제 (XAI)
.venv/Scripts/python.exe $P/merge_ablation.py
.venv/Scripts/python.exe $P/register_sealed_prediction.py register   # 최종 실행 전 예측 등록
.venv/Scripts/python.exe $P/run_relation_nim.py --live --split sealed_test --resume
.venv/Scripts/python.exe $P/register_sealed_prediction.py check
.venv/Scripts/python.exe $P/apply_operating_point.py           # 운영점 적용 (재선택 아님)
.venv/Scripts/python.exe $P/freeze_relation_responses.py       # 회귀 fixture 고정
.venv/Scripts/python.exe $P/build_dashboard.py                 # 자립 검토 화면
```

관찰값은 `reports/relation-nim/observations.jsonl`에 split을 가로질러 쌓이고(`--resume`의
근거), 채점 산출물은 split별 폴더로 갈라진다. 한 요약에 두 split이 섞이면 규율을 감사할 수
없기 때문이다.

## 결과 문서

| 문서 | 내용 |
| --- | --- |
| [docs/tuning-log.md](docs/tuning-log.md) | 프롬프트 조정 기록 — 여기 없는 조정은 없어야 한다 |
| [docs/operating-point.md](docs/operating-point.md) | 운영점 선택 근거와 두 임계값 격자 |
| [docs/sealed-test-prediction.md](docs/sealed-test-prediction.md) | 최종 실행 **전에** 등록한 예측 |
| [docs/sealed-test-result.md](docs/sealed-test-result.md) | 최종 결과와 예측 대조 (39/40 적중) |
| [docs/injection-and-ablation.md](docs/injection-and-ablation.md) | 주입 탐지·저항, 근거 절제 충실도 |
| [docs/design-worksheet.md](docs/design-worksheet.md) | 설계 워크시트 ①~⑦ + 게이트 3 |

## 검토 화면

`build_dashboard.py`가 `reports/relation-nim/dashboard.html` 한 파일을 만든다. 더블클릭하면
열리고 **외부 요청이 0건**이다 — CDN·폰트·이미지·fetch 어느 것도 없다. 임상 노트에서 나온
화면이 바깥으로 요청을 보내면 그 자체가 데이터 유출 경로이기 때문이며,
`tests/test_dashboard.py`가 이것을 회귀로 지킨다.

화면은 자기 계산을 파이썬 결과와 대조해, 다르면 붉은 배너로 드러낸다.

## 폴더

```text
src/bio_relation_workflow/
├── config/          YAML과 .env를 읽는다
├── schemas/         노트, 후보 개체쌍, 관계 판정과 평가 결과 계약
├── preprocessing/   임상 노트 코퍼스를 호출 전에 준비
├── providers/       실제 LiteLLM 또는 저장 응답 replay
├── workflow/        후보 개체쌍, 노트와 provider 연결
├── evaluation/      결정적 metric과 DeepEval
└── xai/             근거 절제로 사후 설명의 충실도 측정

scripts/             실행 진입점 (_bootstrap.py가 import 경로 처리)
configs/             실행 설정 YAML
prompts/             출력 계약 프롬프트
templates/           검토 화면 HTML 템플릿
docs/                조정 기록·운영점·최종 결과·설계 워크시트
data/cases/          사람이 편집하는 정답 라벨 YAML
data/recorded/       회귀용 응답 fixture
local-data/          노트 코퍼스·후보 등 생성물 (git 제외)
reports/             실행 결과·검토 화면 (git 제외)
tests/
```

## 데이터 출처

`day6/relation-explorer.html`(day6 실습의 관계탐색 프로토타입)의 사전계산 JSON에서 노트
108건과 개체 30종을 추출한다. day3 관계추출 실습의 산출물이며 **교육용 합성 데이터**다.
실제 환자 기록이 아니고 임상 성능 근거도 아니다.
