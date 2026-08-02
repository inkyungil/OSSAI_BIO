# sealed_test 사전등록 예측

2026-08-02 · **sealed_test를 실행하기 전에** 작성했다. 등록본은
[`data/sealed-test-prediction.json`](../data/sealed-test-prediction.json)이고
`scripts/register_sealed_prediction.py register`가 만들었다.

---

## 왜 예측을 먼저 적는가

#16에서 validation 실패 8건이 development가 한 번도 담지 않은 두 문형에 **예외 없이**
몰린 것을 발견했다([operating-point.md](operating-point.md) 4절). 그 발견으로
프롬프트를 고치면 validation이 선택셋으로 변질되므로(`day5 p37-38`) 고치지 않기로 했다.

대신 같은 실패가 sealed_test에서 **어느 케이스에** 날지를 미리 적어둔다. 실행 후에
"그래서 그렇게 된 것"이라고 설명하는 것과, 먼저 적어둔 것이 맞는 것은 증거의 무게가
다르다. 층화 결함이라는 진단이 맞다면 예측은 케이스 단위로 맞아야 한다.

예측의 입력은 **케이스의 노트 문형뿐이고 모델을 호출하지 않았다.** 문형은 라벨링
시점에 정해진 데이터 속성이므로 이것을 보는 것은 sealed_test 결과를 엿보는 것이 아니다.

---

## 예측 규칙

validation에서 문형별로 관측된 모델 행동을 그대로 옮긴 것이다. 예외가 한 건도 없었다.

| 문형 | 예측 판정 | 근거 (validation) |
| --- | --- | --- |
| COMPLAINS | `has_symptom` | 7건 전부 통과 |
| CONSIDER | 보류 | 3건 전부 통과 |
| 동시출현만 | `no_relation` | 23건 전부 통과 |
| PRESENTED 단독 | `no_relation` (오답) | 5건 전부 실패 — "의심 소견"을 확립된 진술로 안 봄 |
| HEDGE 단독 | `no_relation`, 보류 안 함 (오답) | 3건 전부 실패 — 프롬프트에 규칙이 있는데도 |

---

## 예측값

| 지표 | 예측 |
| --- | ---: |
| task_success | **0.80** (32/40) |
| schema_validity | 1.0 |
| relation_correct | 0.925 (PRESENTED 3건만 틀림) |
| abstention_correct | 0.875 (HEDGE 5건만 틀림) |
| 모델 보류 / 정답 보류 | 3 / 8 |
| asserted / PPV / recall | 11 / 1.0 / 0.7857 |
| 환각 OMISSION | 3 |

**실패할 8건** — PRESENTED 단독 3건 `C028-고혈압-기침` `C051-심부전-어지럼증`
`C063-폐렴-호흡곤란`, HEDGE 단독 5건 `C037-길랑바레증후군-와파린`
`C076-길랑바레증후군-기침` `C077-길랑바레증후군-메트포르민` `C090-모야모야병-기침`
`C092-모야모야병-와파린`.

나머지 32건은 전부 통과한다고 예측한다.

---

## 대조 방법 (#20 이후)

```
python scripts/register_sealed_prediction.py check
```

케이스 단위로 예측 통과/실패와 실제를 맞춰보고 `prediction_accuracy`를 낸다.

- **예측이 맞으면** — 실패의 원인이 모델 능력이 아니라 **development split이 문형을
  빠뜨린 것**이라는 진단이 검증된다. `day5 p37-38`의 split 규율이 왜 있는지에 대한
  실물 증거가 된다.
- **예측이 빗나가면** — 진단이 틀렸다는 뜻이다. 그 경우 문형 말고 다른 요인이 있으며,
  결과 보고에 그렇게 적는다. 예측을 사후에 고쳐 맞추지 않는다.

어느 쪽이든 sealed_test는 한 번만 돌리고 그 결과로 프롬프트·임계값을 다시 고르지 않는다.
