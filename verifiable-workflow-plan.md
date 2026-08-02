# 질병-약물-증상 관계 탐색을 검증 가능한 AI Workflow로

작성일 2026-08-02

day6 실습의 관계탐색 프로토타입(`bio/day6/relation-explorer.html`)을 OSSAI-26-1 저장소의
**검증 가능한 AI Workflow 설계·평가** 구조로 재설계하고, 텍스트 축 XAI를 추가하는 계획서다.
근거는 `bio/day6/doc/`의 KIDICO 바이오헬스 AI 7차시 슬라이드와 이 저장소의 Week 1 구현이다.

---

## 1. 출발점 — 지금 프로토타입에 빠진 것

기존 프로토타입의 데이터 구조는 이렇다.

```
candidate_edges 154  →  min_cooccur ≥ 2  →  kept_edges 69
in_reference_edges 5 / reference_error_edges 1
relation_count: treats 37, has_symptom 32
```

**"같은 노트에 2번 이상 함께 나왔다"가 유일한 판정 근거**다. 그래서 `meta.notice`에 "원인과
결과를 뜻하지 않음"이라는 면책이 걸려 있다. 근거문장 패널이 있지만 그 문장이 실제로 그 관계를
지지하는지는 아무도 채점하지 않는다. 화면은 보여주고, 판단은 통째로 사람에게 넘긴 상태다.

검증 가능한 워크플로우로 바꾼다는 것은 **동시출현 통계를 판정으로 승격시키고, 그 판정을
채점하는 것**이다.

---

## 2. 두 트랙은 남남이 아니다 — Day5가 이미 같은 사상

`day5_genai_llm.pdf`는 이 저장소와 사실상 같은 설계 사상을 가르친다.

| OSSAI 저장소 | Day5 슬라이드 |
| --- | --- |
| `evidence_kind: test_only / live_quality` | p53 "replay는 모델 성능을 대신하는 결과가 아니라 파싱·검증·분기 코드를 재현하는 고정 fixture" / "가용성 경로가 품질 게이트를 우회하지 않도록 설계" |
| `StructuredAnswer` (answer/evidence/abstained) | p49 출력 계약 = `evidence`(claim + source_quote) + `uncertainty` + `review_required` |
| `schema_validity` → `quote_grounding` → `_contains_answer_fact` | p51 validator 체인 = JSON PARSE → SCHEMA → GROUNDING → FACT CHECK(숫자·누락) → INJECTION |
| `abstained` 필수 검증 | p20 프롬프트 계약의 FAILURE = "불충분하면 uncertainty와 review_required" |
| `task_success` 게이트 | p51 "PASS ≠ 확정, 모든 통과 결과는 DRAFT_REVIEW로" |

즉 커리큘럼은 이미 이 규율을 **이론으로** 가르쳤고, day6 실습(CNN·Grad-CAM)과 관계탐색
프로토타입(사전계산 HTML)이 그것을 구현하지 않았을 뿐이다. 이 계획은 새로운 발명이 아니라
빠진 조각을 채우는 일이다.

---

## 3. XAI — 텍스트 축의 빈칸

`day6 p6`의 XAI 지형도는 세 축(사후/내재적 × 모델특정/모델불문 × 영상/정형/텍스트)인데
채워진 칸이 둘뿐이다.

- 영상 → Grad-CAM (사후·모델특정)
- 정형 → SHAP (사후·모델불문)
- **텍스트 → 비어 있음**

그리고 `day6 p22`에 반사실(Counterfactual)이 이렇게 소개된다.

> 무엇이 바뀌면 판정이 바뀌나 · 최소 변화로 결정 경계 제시
> 정직성: 임상 수용성은 높은 방향이나 **검증·실배포는 초기 단계**

Grad-CAM은 픽셀 히트맵이라 텍스트/그래프에 붙지 않는다. 대신 **근거문장 절제(ablation)**로
같은 목적을 달성하며, 이것이 텍스트 축의 빈칸을 채운다.

| 지표 | 방법 | 뜻 |
| --- | --- | --- |
| **충분성** (sufficiency) | 모델이 든 근거문장 **만** 주고 재질의 | 그 문장만으로 같은 판정이 나오나 |
| **필요성** (comprehensiveness) | 근거문장을 **빼고** 재질의 | 빼면 판정이 뒤집히나 |

근거를 뺐는데도 판정이 그대로면 그 근거는 사후에 갖다 붙인 장식이다. 모델은 다른 것을 보고
결정했고 인용은 구색이었다는 뜻이다. 이는 vision 쪽 Grad-CAM deletion metric과 같은 발상이며,
`day6 p17`이 반복해 못 박는 "사후 설명은 인과가 아님"에 대한 **정량적 답**이다.

비용은 엣지 1건당 API 3회(본 판정 + 충분성 + 필요성)이고, 결정적으로 채점되므로 LLM Judge가
필요 없다. 원 저장소가 Week 3에서야 다루는 Judge 문제를 우회한다.

---

## 4. 과제 계약

| 원 저장소 (PDF QA) | 바이오 관계추출판 |
| --- | --- |
| PDF 페이지 이미지 | 후보 쌍이 등장한 노트 문장들 |
| 질문 1건 | 후보 엣지 1건 (폐렴 ↔ 아지스로마이신) |
| `answer` | `relation`: treats / has_symptom / **no_relation** |
| `evidence.quote` + `page_number` | `evidence.quote` + `note_id` |
| `abstained` | 동시등장은 있으나 판정 불가 |
| PDF 페이지 텍스트 대조 | 원 노트 문장 대조 |

```python
class RelationVerdict(Contract):
    relation: Literal["treats", "has_symptom", "no_relation"]
    evidence: list[NoteEvidence]      # quote + note_id
    confidence: float
    abstained: bool = False
    abstention_reason: str | None = None
```

`schemas/models.py:29-38`의 validator를 그대로 승계한다. 보류면 근거를 비우고, 판정이면 근거
필수. 이 구조가 "잘 모르겠지만 아마 X일 것 같습니다" 식의 물타기를 파싱 단계에서 죽인다.

**`no_relation`을 명시적 클래스로 두는 것이 핵심이다.** 지금 프로토타입은 min_cooccur 필터로
걸러낸 85개 후보가 화면에서 그냥 사라진다. 그들이 진짜 무관계였는지 아무도 모른다. 정답셋에
넣어야 필터의 성능을 잴 수 있다.

---

## 5. 채점표

`scoring.py` 구조를 거의 그대로 재사용한다.

| 지표 | 계산 | 원 저장소 대응 |
| --- | --- | --- |
| `schema_validity` | 그대로 | 동일 |
| `relation_correct` | 정답 라벨 일치 | `answer_correct` |
| `abstention_correct` | 보류 정오 | 동일, `task_success` 필수 게이트 |
| `evidence_note_hit` | 인용 노트 ID가 정답 노트에 포함 | `evidence_coverage` |
| `quote_grounding` | 인용문이 실제 노트 텍스트에 있는가 | `_best_quote_similarity` 그대로 |
| `reference_agreement` | 참조표와 일치/충돌 | 신규 |
| `sufficiency` / `comprehensiveness` | 근거 절제 재질의 | 신규 (XAI) |

`_best_quote_similarity`(`scoring.py:86-99`)는 PDF 특화가 아니라 정규화 문자열 대조이므로 노트
텍스트에 그대로 붙는다. 인용문 환각을 잡는 장치를 공짜로 가져오는 셈이다.

`reference_agreement`는 주의가 필요하다. DATA의 `reference_notice`가 **"참조표 자체가 교육용이라
잘못된 항목이 섞여 있음"**이라 밝히고 실제로 `reference_error_edges: 1`이다. 참조표는 정답이
아니라 **세 번째 의견**으로 다뤄야 하며, 모델과 참조표가 충돌하는 케이스를 따로 모아 보여주는
것이 오히려 가장 값진 출력이다.

---

## 6. 커리큘럼에서 반드시 반영할 도메인 규율

문서를 읽고 확인한, 빠뜨리면 수업 기준으로 결함이 되는 항목들이다.

### ① split 규율 (day5 p37-38, day1b p38)

> 정책·임계값 선택은 valid에서 종료. test 결과를 보고 재선택하면 평가셋이 다시 선택셋으로 변질

원 저장소 Week 1에는 이 규율이 없다(40건 단일 세트). 그런데 `EvaluationCase`에 이미
`split: Literal["development","validation","challenge","sealed_test"]` 필드가 있다
(`schemas/models.py:91`) — 정의만 하고 쓰지 않고 있다. 바이오판에서는 실제로 굴린다.
confidence 임계값은 validation에서 고르고 sealed_test는 마지막 1회.

### ② 유병률·PPV (day3 p35-36)

민감도 90%·특이도 90%라도 유병률 1%면 PPV 8%. 관계추출로 옮기면 **화면에 표시된 관계 중 진짜
비율이 곧 PPV이고 그것이 사용자 체감의 전부다.** 따라서 `relation_correct` 평균이 아니라
"표시된 것 중 맞은 비율"을 따로 보고한다.

### ③ 흔한 개체 착시 (day3 p11-12)

> 발열은 거의 모든 질병 노트에 등장. 빈도만 보면 관련 없는 질병과도 관계처럼 보임

`has_symptom` 32건에 허브 증상이 섞여 있을 가능성이 크다. 평가셋에 **허브 개체 쌍을 별도 층**으로
넣는다. p12의 PMI·로그우도비를 baseline으로 두고 LLM 판정과 비교하면 "정교한 방법이 실제로
나은가"까지 답할 수 있다.

### ④ 프롬프트 주입 (day5 p52, OWASP LLM01)

> 임상 노트·PDF·검색 문서도 신뢰할 수 없는 입력으로 취급

노트를 통째로 LLM에 넣으므로 그대로 걸린다. 평가셋에 주입 케이스를 심어 validator가 잡아
`DRAFT_REVIEW_INJECTION`으로 라우팅하는지 본다. 보류(abstain)와는 다른 실패 유형이다.

### ⑤ 환각 4분류로 실패 태깅 (day5 p21)

NUMBER / SOURCE / OMISSION / **RELATION**(부정·시점·주체·약물 관계 반전). RELATION이 정확히 이
과제의 고유 실패 유형이다. 실패 케이스를 이 4분류로 태깅하면 오류 유형 분포가 나오고,
`day6 p18`이 요구하는 "개별 근거 + 집계 오류를 함께 읽기"를 충족한다.

### ⑥ 일반화 사다리 (day5 p39)

SINGLE → REPEAT → EXTERNAL → PROSPECTIVE. 단일 분할·단일 시드이므로 결과 보고 시
**"SINGLE — 가설 생성 수준"**이라고 명시한다.

### ⑦ 두 임계값은 같은 구조 (day3 p40)

관계 잡음컷(min_cooccur)과 분류 운영점(confidence Cut-off)은 "연속 신뢰도를 어디서 자를까"의
같은 문제다. 이 프로젝트는 두 임계값을 **한 화면에서** 보여주게 되며 그것이 day3 관통 주제의
구현이다.

---

## 7. 운영점

`day6 p30`과 워크시트 ④가 요구하는 임계값. 관계 탐색에서 놓침과 헛경보의 비용은 비대칭이다 —
**잘못된 약물-질병 연결을 보여주는 것(헛경보)이 연결을 놓치는 것보다 훨씬 나쁘다.** 따라서
confidence 임계값을 높게 잡고 그 아래는 전부 보류 → 사람 확인 큐로 보낸다.

임계값을 움직였을 때 자동표시/보류/놓침이 어떻게 변하는지가 대시보드 탭 하나가 되며,
day6 모듈2의 `threshold_tradeoff.csv`와 같은 그림이다.

`day3 p34`의 실무 방식을 따른다 — 정확도가 아니라 **지켜야 할 지표를 제약으로 걸고 나머지를
최적화**한다.

---

## 8. 화면

원 프로토타입의 "근거문장" 패널을 확장한다.

```
폐렴 → 아지스로마이신 (treats)   신뢰 0.86
근거: "…경험적 항생제로 아지스로마이신을 투여함"  [노트 N-047]
✓ 근거 검증됨 (노트 원문 일치)
✓ 근거 제거 시 판정 뒤집힘 → 실제 판단 근거
⚠ 참조표와 불일치 — 사람 확인 필요
```

`test_only` / `live_quality` 배지도 함께 노출한다. 사전계산 JSON으로 도는 화면과 실제 모델
호출 결과를 화면에서 구분하지 않으면 day5 p53의 규율이 깨진다.

---

## 9. 데이터 — 층화 60건

후보 154개 전부는 과하다. 층화 샘플로 충분하다.

| 층 | 건수 | 근거 |
| --- | ---: | --- |
| 참조표 일치 | 5 | 쉬운 양성 (단, 1건은 오류 항목) |
| kept_edges 일반 | 30 | 본류 |
| **허브 개체 쌍** | 8 | day3 p11 흔한 개체 착시 |
| 탈락 후보 (min_cooccur 미달) | 12 | 필터가 놓친 것 |
| 보류 정답 | 7 | 판정 불가 |
| **프롬프트 주입** | 3 | day5 p52 |

150개 노트가 교육용 합성 데이터라 라벨링이 실제 임상 데이터보다 빠르다. 반나절 작업.

개인정보 게이트(`day5 p48`: MINIMIZE / DE-IDENTIFY / CONTRACT / RETENTION / ALLOW)는 합성
데이터이므로 통과한다. 이 근거를 설계서에 명시한다.

---

## 10. 코드 재사용 분석

전체 2,098줄. 경계가 깨끗하게 그어져 있다.

| 층 | 파일 | 바이오 전환 시 |
| --- | --- | --- |
| **인프라** | `providers/` 206줄, `config/` 117줄, `deepeval_runner.py` 118줄, `data/dataset.py` 59줄 | **그대로** |
| **운영 스크립트** | `freeze_recorded_responses` 66, `run_workflow` 47, `evaluate_workflow` 74, `preflight_nvidia` 80 | **그대로** |
| **계약·채점** | `schemas/models.py` 118, `scoring.py` 400 | 부분 수정 |
| **도메인** | `preprocessing/pdf.py` 169, `workflow/inputs.py` 30 | 교체 |

PDF에 못 박힌 곳은 딱 두 군데다. `preprocessing/pdf.py`(pypdfium2 페이지 렌더)와
`inputs.py:17-30`(페이지 JPEG를 base64 image_url로). 나머지는 도메인을 보지 않는다.

특히 좋은 세 지점:

- **`providers/base.py:11`** — `generate(sample_id, messages)`가 전부다. messages 안이 PDF
  이미지든 노트 텍스트든 provider는 모른다. LiteLLM 170줄(비용 상한·rate limit·429 재시도·
  `last_call` 계측)이 한 줄도 안 바뀌고 넘어온다.
- **`scoring.py:18-107`** — `_normalize`, `_edit_similarity`, `_token_f1`,
  `_best_quote_similarity`, `_contains_answer_fact`. 전부 순수 문자열 함수로 PDF라는 단어가
  없다. 인용문 대조와 숫자 환각 검사가 공짜로 넘어온다.
- **`deepeval_runner.py:56-87`** — `metric_specs`가 데이터로만 돼 있어 지표 이름·임계값만
  갈아끼우면 된다. `ResultMetric`은 완전 범용.

`EvaluationCase`(`models.py:86-96`)는 이미 도메인 중립이다 — `document_id`, `split`, `source`,
`risk_level`, `question`, `expected`, `tags`. **필드를 하나도 바꾸지 않아도 된다.**

바꿔야 하는 것:

- `Evidence.page_number` → `note_id` (`models.py:17`)
- `PreparedDocument` / `PreparedPage` → 노트 컬렉션 스키마
- `DocumentSettings.render_dpi`가 필수 필드라(`settings.py:27`) 텍스트 도메인에 안 맞음 →
  섹션 전체를 optional로

인프라의 약 60%가 무료로 넘어온다. 도메인 교체 비용은 라벨링을 빼면 하루 안쪽이다.

---

## 11. 6주 과정 매핑

| 주차 | 원래 (PDF QA) | 바이오 관계추출 | 판정 |
| --- | --- | --- | --- |
| 1 | PDF 전처리·구조화·결정적 평가 | 노트 전처리·관계 판정·근거 대조 | 동형 |
| 2 | 두 provider 비교 | **의료특화(MedGemma 1.5 4B) vs 범용 모델** | **바이오가 나음** |
| 3 | LLM-as-a-Judge | 임상 판정에 Judge를 어디까지 쓸 수 있나 | 바이오가 절실 |
| 4 | prompt 최적화·멀티모달 견고성 | **표현 변형 견고성 = 도메인 시프트의 텍스트판** | **바이오가 나음** |
| 5 | 도구 호출·trace | 참조표(UMLS/DrugBank류) 조회를 도구로 | 동형 |
| 6 | CI·release 판단 | 자동확정 중지 → 사람 확인 라우팅 | 동형 |

**Week 2**가 특히 좋다. `day5 p47`이 던져놓고 넘어간 질문에 직접 답하게 된다.

> 의료 특화 사전학습은 시작점이며 현장 데이터·업무 목적에 대한 별도 검증 필요
> 예: 의학 문장을 아는 모델 ≠ 우리 기관의 규칙을 통과한 시스템

의료 특화 모델이 범용보다 실제로 나은지를 같은 정답셋으로 결정적으로 재는 것이다.

**Week 4**도 좋다. day4가 영상 도메인 시프트를 가르치고 day6 p16이 그것을 히트맵으로 다시
확인한다. 텍스트에서 같은 것을 하면 `day2 p33`의 오탈자·약어·미등록 표현 12%가 그대로 시프트
요인이 된다. 영상에서 배운 개념을 텍스트에서 재현하는 구조라 커리큘럼 연결이 자연스럽다.

---

## 12. 장벽 셋 (정직하게)

**① 정답 라벨 — 유일한 실질 장벽**

PDF QA는 답이 문서에 적혀 있어 라벨링이 받아쓰기에 가까웠다. 관계 판정은 아니다. 60건이면
반나절이지만 **이것이 없으면 나머지 전부가 못 돌아간다.** 전 주차가 이 정답셋 하나에 의존한다.

**② 멀티모달이 사라짐**

Week 1 프롬프트는 페이지 이미지를 넣는 구조인데(`inputs.py`) 관계추출은 텍스트만이다. 그러면
`nemotron-3-nano-omni`(omni = 멀티모달)를 쓸 이유가 없어져 **모델 선택부터 다시 해야 한다.**
나쁜 일은 아니고 오히려 싸고 빨라지지만 `docs/nvidia-model-catalog.md`의 후보 검토가 필요하다.

**③ 기존 버그가 복사됨**

`scripts/evaluate_workflow.py:62`가 summary의 `evidence_kind`를 `"test_only"`로 하드코딩하는데,
이 스크립트에는 `run_workflow.py:22-23` 같은 provider 검사가 없다. `--config configs/nvidia-nim.yaml`로
돌리면 실제 API 관찰값을 읽고도 summary에는 `test_only`가 찍힌다. 건별 `results.jsonl`은
`live_quality`로 맞게 남지만 실습 안내가 학생에게 보라고 하는 파일은 summary.json이다.
**복사하기 전에 고친다** — 하필 이 커리큘럼이 day5 p53에서 가장 강조하는 규율이다.

부수적으로 `scoring.py:235-244`도 알고 있어야 한다. 인용문을 PDF 추출 텍스트로 검증할 수 없으면
(표·차트값) grounding 게이트를 건너뛴다. 노트 텍스트 도메인에서는 이 우회로가 줄어들지만
로직을 그대로 옮기면 같은 구멍이 따라온다.

---

## 13. 시작 순서

1. `evaluate_workflow.py` evidence_kind 버그 수정 — 5분, 복사 전에
2. 프로토타입 `const DATA`에서 후보 추출 → 층화 라벨링 틀 생성 ← **임계 경로**
3. `RelationVerdict` 스키마 + 채점 코드 (API 없이 도는 것까지)
4. Week 1 바이오판 완주 → 이후 주차는 그때 결정

2번이 임계 경로인 이유는 라벨링에 사람 시간이 필요하고 나머지 전부가 거기 물려 있기
때문이다. 3번을 만드는 동안 병렬로 진행할 수 있다.

---

## 부록 — doc PDF 읽는 법

`bio/day6/doc/*.pdf`는 한글 파일명이라 Read 도구가 열지 못한다. ASCII 이름으로 복사한 뒤
텍스트를 추출해야 한다.

```bash
# 예시: pypdfium2로 페이지별 텍스트 추출
python -c "
import pypdfium2 as pdfium
doc = pdfium.PdfDocument('d3_kg_threshold.pdf')
for i in range(len(doc)):
    print(f'--- p{i+1} ---')
    print(doc[i].get_textpage().get_text_range())
"
```

| 파일 | 페이지 | 핵심 |
| --- | ---: | --- |
| `day1_01_의료ML개념` | 12 | 의료 ML 특수성, 누수 3유형, 임계값=판정기준 |
| `day1_02_의료데이터리터러시` | 53 | 거버넌스, 결측 메커니즘(MCAR/MAR/MNAR), 보정·Brier |
| `day2_특허NLP` | 56 | TF-IDF, 규칙 NER 최장일치, macro-F1 |
| `day3_지식그래프_임계값` | 41 | **동시출현·min_count, 중심성, ROC/AUC, 유병률·PPV** |
| `day4_vision_도메인시프트` | 51 | CNN, 도메인 시프트, Histogram Matching |
| `day5_genai_llm` | 55 | **출력 계약·validator·라우팅, replay vs live, 환각 4분류, 주입** |
| `day6_xai_service` | 40 | **XAI 지형도, Grad-CAM/SHAP 한계, 서비스 설계 4단계, 게이트 3개** |
| `01_AI_ML_DL_신경망 기초` | 38 | 이미지 슬라이드 (텍스트 거의 없음) |
| `02_CNN_RNN_Transformer_GenerativeAI_Agent` | 56 | 아키텍처 개관 |
