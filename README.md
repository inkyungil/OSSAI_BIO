# bio — 질병·약물·증상 관계 판정 워크플로

## 왜 이 판정을 검증해야 하나

임상 노트에서 "이 약이 이 병을 치료한다", "이 병이 이 증상을 동반한다"를 뽑아내는 일은
한 번 뽑고 끝나지 않는다. 그 결과는 지식그래프에 쌓이고, 검색에 실리고, 다음 사람의
판단 근거가 된다. **틀린 관계는 조용히 퍼지고, 퍼진 뒤에는 출처를 되짚기 어렵다.**
바이오 도메인에서 이 판정을 검증해야 하는 이유는 네 가지다.

**1. 동시출현은 관계가 아니다.** 같은 노트에 당뇨병과 메트포르민이 함께 나왔다는 사실은
상관이지 인과가 아니다. 같은 노트에 자주 등장하는 흔한 약과 흔한 병은 아무 관계가 없어도
붙는다. 출발점이던 프로토타입은 "2번 이상 함께 나왔다"가 유일한 근거였고, 그래서 화면에
"원인과 결과를 뜻하지 않음"이라는 면책을 달아야 했다. **면책을 다는 대신 채점하는 것**이
이 워크플로의 목적이다.

**2. 근거가 있다는 것과 그 근거가 이유였다는 것은 다르다.** LLM은 판정과 함께 그럴듯한
인용 문장을 붙인다. 그 문장이 노트에 실재하는지는 확인할 수 있지만(`quote_grounding`),
그 문장이 실제로 판단을 지탱했는지는 다른 질문이다. 임상에서 근거는 사람이 검토하라고
붙이는 것이므로, 장식이면 검토자를 잘못된 안심으로 이끈다. 이 프로젝트가 **근거 절제**로
따로 측정하는 것이 그것이다.

**3. 임상에서는 모른다고 말할 수 있어야 한다.** "폐렴 의증", "…일 가능성을 고려함" 같은
문장은 확립된 관계가 아니다. 이걸 관계로 승격시키면 미확정 소견이 확정 사실로 굳는다.
그래서 정답 중에는 **보류가 정답인 케이스**가 따로 있고, 보류 여부를 별도 지표로 채점한다.

**4. 놓치는 것과 잘못 단언하는 것은 비용이 다르다.** 관계를 놓치면 사람이 더 찾아보면
되지만, 없는 관계를 단언하면 그대로 지나간다. 그래서 정확도 한 숫자가 아니라 **PPV(단언한
것 중 맞은 비율)와 재현율을 갈라서** 보고, 어느 쪽으로 치우칠지를 운영점으로 명시해 고른다.

여기에 하나 더 — 임상 노트는 외부로 나가면 안 되는 데이터다. 그래서 검토 화면은 네트워크
요청이 **0건**이고, 그 사실 자체를 테스트가 지킨다.

---

## 무엇을 만드나

임상 노트에서 뽑은 후보 개체쌍이 실제 관계인지 LLM으로 판정하고, **그 판정을 채점한다.**
동시출현 통계로 그린 관계 그래프를 검증 가능한 판정으로 승격시키는 것이 목표다.

판정 근거로 인용한 문장이 실제 판단 이유였는지는 **근거 절제(ablation)** 로 따로 측정한다.
근거를 지우면 판정이 바뀌는지 보는 방식이며, 텍스트 축 XAI에 해당한다.

> **데이터 출처와 한계**
> 노트 108건과 개체 30종은 day6 실습의 관계탐색 프로토타입이 담고 있던 사전계산 JSON에서
> 추출했다. day3 관계추출 실습의 산출물이며 **교육용 합성 데이터**다.
> **실제 환자 기록이 아니고, 이 저장소의 수치는 임상 성능 근거가 아니다.**

## 빠른 시작

`C:\app\bio`(이 폴더)에서 실행한다. 별도 설치는 필요 없다 — 이 폴더의 `.venv`를 그대로 쓴다.

```powershell
# 환경 확인
.venv\Scripts\python.exe relation-workflow\run.py check

# 회귀 테스트 (저장 응답 replay — API 호출 없음)
.venv\Scripts\python.exe relation-workflow\run.py test

# 결과 열람
start relation-workflow\reports\relation-nim\dashboard.html
```

`.venv`가 없다면 `requirements.txt`로 만든다 (버전 고정).

```powershell
uv venv
uv pip install -r requirements.txt
```

## 러너 — 순서가 곧 규율이다

`relation-workflow/run.py`가 단계를 순서와 게이트째로 실행한다. 명령을 줄이려고 만든 것이
아니라, **사람이 지키던 규율을 코드가 거부하게** 만들려고 만들었다. 사람이 지키는 규율은
급할 때 깨지고 깨져도 흔적이 남지 않는다.

```powershell
.venv\Scripts\python.exe relation-workflow\run.py check        # 환경 확인
.venv\Scripts\python.exe relation-workflow\run.py prepare      # 데이터 준비 ①~⑥
.venv\Scripts\python.exe relation-workflow\run.py develop --live   # development + validation + 운영점
.venv\Scripts\python.exe relation-workflow\run.py ablate --live    # 근거 절제 (XAI)
.venv\Scripts\python.exe relation-workflow\run.py seal --live      # 예측 등록 → sealed_test → 대조 → 적용
.venv\Scripts\python.exe relation-workflow\run.py freeze       # 회귀 fixture 고정
.venv\Scripts\python.exe relation-workflow\run.py dashboard    # 검토 화면 생성
.venv\Scripts\python.exe relation-workflow\run.py test         # replay 회귀 테스트
```

어느 단계든 `--dry-run`을 붙이면 무엇이 돌지만 보여주고 아무것도 실행하지 않는다.

### 러너가 거부하는 것

| 게이트 | 거부 이유 |
| --- | --- |
| 운영점 없이 `seal` | 운영점을 sealed_test 보고 고르면 그 순간 sealed_test가 선택셋이 된다 |
| 이미 실행된 `seal` 재실행 | 한 번만 보기로 한 split. 결과를 본 뒤 다시 돌리면 사전등록 예측의 검증이 아니다 |
| 예측 미등록 상태의 sealed 실행 | 등록 단계가 먼저 돌고, 실패하면 거기서 멈춘다 |
| `--live` 없는 실제 호출 | 비용이 드는 실행은 직접 적어야 한다 |
| 코퍼스가 있는데 `prepare` | 다시 돌리면 노트 코퍼스가 초기화되고 주입 노트 병합이 되돌아간다 |

게이트에 걸리면 **한 줄도 실행되지 않고** 종료 코드 2로 멈춘다. 절반만 돈 상태가 제일
해석하기 어렵기 때문이다. 정말 넘어야 한다면 `--force`가 있지만, 그건 기록에 남기라는 뜻이다.

모든 단계를 한 번에 도는 `all`은 **일부러 없다.** 그런 명령이 있으면 sealed_test가 다른
단계에 섞여 무심코 소비된다.

---

## 검증 결과

모델 `nvidia_nim/openai/gpt-oss-20b`, 케이스 103건(development 22 / validation 41 /
sealed_test 40). `evidence_kind: live_quality`.

### split별 채점

| | development 22 | validation 41 | **sealed_test 40** |
| --- | --- | --- | --- |
| 통과 / 실패 | 22 / 0 | 33 / 8 | **33 / 7** |
| task_success | 1.0 | 0.805 | **0.825** |
| relation_correct | 1.0 | 0.878 | **0.925** |
| abstention_correct | 1.0 | 0.927 | **0.900** |
| PPV (단언한 것 중 정답) | 1.0 | 1.0 | **1.0** |
| 재현율 | 1.0 | 0.583 | **0.786** |
| quote_grounding | 0.997 | 1.000 | **1.000** |
| schema_validity / JSON 계약 | 1.0 | 1.0 | **1.0** |
| 누락형 환각(OMISSION) | 0 | 5 | **3** |

**PPV가 세 split 모두 1.0이다.** 관계를 인정한 건 전부 맞았고, 틀린 방향은 전부 "놓침"이다.
임상에서 원하는 치우침이 이쪽이므로 의도한 결과지만, 재현율 0.786은 **관계 14건 중 3건을
놓쳤다**는 뜻이기도 하다. 보류는 8건이 정답인데 4건만 보류했다(`missed_abstention: 4`).
과잉 보류는 0건이다.

출력 계약은 완전히 지켜졌다 — JSON만 반환, 스키마 유효, 인용 문장은 sealed_test에서 100%
노트에 실재한다. 즉 **파싱·검증 층은 흔들리지 않았고, 남은 오차는 전부 판단의 문제다.**

### 사전등록한 예측과의 대조 — 39/40

sealed_test를 돌리기 **전에** 문형별 예측을 등록해 고정했다(모델 호출 없이 케이스
메타데이터만 사용). 실행 후 대조 결과:

```
checked 40 · prediction_hits 39 · prediction_accuracy 0.975
빗나간 1건: C092-모야모야병-와파린 (HEDGE)
  예측 failed → 실제 passed (no_relation, 보류함)
```

빗나간 방향이 **예상보다 좋은 쪽**이다. validation에서 HEDGE 문형은 3건 전부 보류에
실패했기에 실패를 예측했는데, sealed_test에서는 보류에 성공했다. 사후에 "그래서 그렇게 된
것"이라고 말하는 것과 미리 적어둔 것이 맞는 것은 증거의 무게가 다르다.

### 운영점 — validation에서만 골랐다

PPV 하한 0.95를 걸고 격자에서 고른 값은 `min_cooccur=1, min_confidence=0.95`다.

| | validation (선택) | sealed_test (적용) |
| --- | --- | --- |
| 자동 노출 | 7건 (전부 정답, PPV 1.0) | 9건 (전부 정답, **PPV 1.0**) |
| 검토 큐 | 9건 (정밀도 0.667) | 14건 (정밀도 0.786) |
| 조용한 누락 | 5건 | 2건 |
| 노출 재현율 | 0.583 | **0.643** |

sealed_test에 적용한 것이지 **다시 고른 것이 아니다.** 선택은 validation에서 끝났다.

### confidence는 믿을 만한가 — 부분적으로만

validation 41건의 confidence 값별 실제 정답률이다.

| confidence | 건수 | 정답률 |
| --- | --- | --- |
| 1.00 | 9 | 0.889 |
| 0.95 | 23 | 0.826 |
| 0.90 | 5 | **0.400** |
| 0.00 | 4 | 1.000 |

값이 4개뿐이고 단조롭지도 않다. **0.9라고 말한 5건 중 3건이 틀렸다.** 그래서 임계값을
0.95로 잡아 0.9 구간을 통째로 검토 큐로 보낸다. confidence를 신뢰도로 읽으면 안 되고,
**분류 경계로만** 쓸 수 있다는 뜻이다.

### 근거 절제 — 여기가 가장 약하다

development + validation 38건에서 근거를 지우고 판정이 바뀌는지 봤다.

| 판정 | 건수 | 뜻 |
| --- | --- | --- |
| REDUNDANT | 15 | 근거를 지워도 판정이 그대로 — 인용이 이유가 아니었다 |
| NECESSITY_VACUOUS | 12 | 필요성을 시험할 수 없는 구조 |
| **FAITHFUL** | **10** | 근거를 지우니 판정이 바뀜 — 인용이 실제 이유였다 |
| NOT_APPLICABLE | 1 | 해당 없음 |

**충실한 근거는 38건 중 10건뿐이다.** 두 축을 모두 측정할 수 있었던 건 25건이고 12건은
필요성 검증이 불가능했다. 다만 "맞혔는데 근거는 장식"인 조합(`correct_but_decorative`)은
**0건**이다.

이 숫자는 성과가 아니라 한계다. 판정이 맞아도 인용 근거가 실제 이유였다고 말할 수 있는
경우는 소수이며, 검토자가 근거 문장만 보고 안심하면 안 된다는 뜻이다.

### 프롬프트 주입

세 split에 주입 케이스가 1건씩 심겨 있다(`INJ001`, `INJ002`, `INJ003`).

```
탐지 3/3 · 저항 3/3 · 순응 0건 · 전용 큐 격리 3/3 (DRAFT_REVIEW_INJECTION)
```

### 통과해도 확정이 아니다

라우팅은 전 split에서 `DRAFT_REVIEW` 계열뿐이다 — sealed_test 기준 `DRAFT_REVIEW` 35,
`DRAFT_REVIEW_ABSTAIN` 4, `DRAFT_REVIEW_INJECTION` 1. **자동 승인 경로가 없다.**
채점 통과는 사람 검토 대기 상태이지 확정이 아니다.

### 회귀 검증

```
191 passed in 1.03s
```

저장 응답 replay라 API 호출 없이 돈다. 이건 **모델 품질이 아니라 파싱·검증·분기 코드가
재현되는지**를 지키는 것이다(`evidence_kind: test_only`). 검토 화면의 외부 요청 0건도
여기서 회귀로 지켜진다.

### 이 결과가 주장하지 않는 것

`generalization: SINGLE` — 단일 분할·단일 시드다. **가설 생성 수준이며 일반화 주장이
아니다.** 모델·시드·코퍼스를 바꾸면 달라질 수 있다.

---

## 결과는 어디서 보나

웹 서버가 없다. 상시 구동되는 서비스가 아니라 **터미널로 돌리고 파일로 본다.**

| | 무엇 |
| --- | --- |
| 터미널 | 워크플로 실행·채점. 산출물은 `relation-workflow/reports/` 아래 JSON·JSONL·CSV |
| 브라우저 | `reports/relation-nim/dashboard.html` 한 파일. 더블클릭하면 열린다 (`file://`) |

검토 화면은 **외부 요청이 0건**이다 — CDN·폰트·이미지·fetch 어느 것도 없이 한 파일에
인라인돼 있다. 임상 노트에서 나온 화면이 바깥으로 요청을 보내면 그 자체가 데이터 유출
경로이기 때문이며, `tests/test_dashboard.py`가 이것을 회귀로 지킨다.
화면은 자기 계산을 파이썬 결과와 대조해, 다르면 붉은 배너로 드러낸다.

## 문서

| 문서 | 내용 |
| --- | --- |
| [relation-workflow/README.md](relation-workflow/README.md) | 스크립트 단위 실행 · 데이터 준비 · 폴더 구조 |
| [verifiable-workflow-plan.md](verifiable-workflow-plan.md) | 설계 근거 — 왜 이렇게 만들었나 |
| [development-plan.md](development-plan.md) | 개발 순서 |
| [docs/operating-point.md](relation-workflow/docs/operating-point.md) | 운영점 선택 근거와 두 임계값 격자 |
| [docs/sealed-test-prediction.md](relation-workflow/docs/sealed-test-prediction.md) | 최종 실행 **전에** 등록한 예측 |
| [docs/sealed-test-result.md](relation-workflow/docs/sealed-test-result.md) | 최종 결과와 예측 대조 |
| [docs/injection-and-ablation.md](relation-workflow/docs/injection-and-ablation.md) | 주입 탐지·저항, 근거 절제 충실도 |
| [docs/tuning-log.md](relation-workflow/docs/tuning-log.md) | 프롬프트 조정 기록 — 여기 없는 조정은 없어야 한다 |
| [docs/design-worksheet.md](relation-workflow/docs/design-worksheet.md) | 설계 워크시트 ①~⑦ + 게이트 3 |

## 구조

```text
C:\app\bio\
├── .venv/                      실행 환경 (git 제외)
├── .env                        NVIDIA_NIM_API_KEY (git 제외)
├── requirements.txt            버전 고정
├── verifiable-workflow-plan.md
├── development-plan.md
└── relation-workflow/
    ├── run.py                  단계 러너 (순서·게이트 강제)
    ├── src/bio_relation_workflow/
    ├── scripts/                실행 진입점
    ├── docs/                   결과 문서
    ├── local-data/             노트·후보·케이스 (git 제외)
    └── reports/                실행 결과·검토 화면 (git 제외)
```

원래 `OSSAI-26-1` 저장소 안 `bio/`에 있었고, 그 저장소의 `src/verifiable_ai_workflow/`(PDF
질의응답)와 **같은 규율을 따르되 별도 패키지**로 만들었다. 지금은 독립 저장소로 떨어져 나와
스스로 돌아간다.
