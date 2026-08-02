"""실행 결과를 요약한다.

원본 `scripts/evaluate_workflow.py:62`는 summary의 evidence_kind를 "test_only"로
하드코딩하고 provider 검사도 하지 않는다. live 관찰값을 넣어도 test_only로 찍히는데,
실습 안내가 학생에게 보라고 하는 파일이 하필 summary다. **여기서는 관찰값에서
유도하고 섞여 있으면 거부한다.**

리포트에 반드시 남기는 것
- evidence_kind — 이 숫자가 모델 품질 근거인지 코드 회귀 결과인지
- PPV — 화면에 표시될 관계 중 맞은 비율. 사용자 체감은 이 값이다(day3 p35-36)
- 환각 4분류 분포 (day5 p21)
- 일반화 사다리 위치 (day5 p39)
- 라우팅 분포 — APPROVED가 없다는 것을 숫자로 보인다 (day5 p51, day6 p35)
- 주입 탐지·저항 (day5 p52)
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..schemas import EvaluationResult, RelationCase
from .injection import injection_report_summary

# day5 p39. 단일 분할·단일 시드이므로 가설 생성 수준이다.
GENERALIZATION_LEVEL = "SINGLE — 단일 분할·단일 시드, 가설 생성 수준"


def resolve_evidence_kind(results: list[EvaluationResult]) -> str:
    kinds = {result.evidence_kind for result in results}
    if not kinds:
        raise ValueError("결과가 비어 있어 evidence_kind를 정할 수 없습니다")
    if len(kinds) > 1:
        raise ValueError(
            f"저장 응답과 실제 응답이 섞였습니다: {sorted(kinds)}. "
            "품질 게이트를 우회하지 않으려면 따로 실행하세요."
        )
    return kinds.pop()


def asserted_precision(
    results: list[EvaluationResult],
    cases: list[RelationCase],
) -> dict[str, Any]:
    """모델이 관계를 인정한 건 중 맞은 비율.

    화면에 실제로 표시될 관계가 이것이므로 사용자 체감 지표다. 전체 정확도는
    no_relation이 다수라 높게 나오지만 그 숫자로는 화면 품질을 알 수 없다.
    """
    expected_by_id = {case.sample_id: case.expected for case in cases}
    asserted = [
        result
        for result in results
        if result.output
        and not result.output.abstained
        and result.output.relation != "no_relation"
    ]
    correct = [
        result
        for result in asserted
        if result.output.relation == expected_by_id[result.sample_id].relation
    ]
    gold_positive = [
        case for case in cases if case.expected.relation != "no_relation"
    ]
    found = [
        result
        for result in asserted
        if expected_by_id[result.sample_id].relation != "no_relation"
        and result.output.relation == expected_by_id[result.sample_id].relation
    ]
    return {
        "asserted": len(asserted),
        "asserted_correct": len(correct),
        "ppv": round(len(correct) / len(asserted), 4) if asserted else None,
        "gold_positive": len(gold_positive),
        "recall": (
            round(len(found) / len(gold_positive), 4) if gold_positive else None
        ),
    }


def abstention_report(
    results: list[EvaluationResult],
    cases: list[RelationCase],
) -> dict[str, Any]:
    expected_by_id = {case.sample_id: case.expected for case in cases}
    model_abstained = [r for r in results if r.output and r.output.abstained]
    gold_abstained = [c for c in cases if c.expected.abstained]
    agreed = [
        r
        for r in model_abstained
        if expected_by_id[r.sample_id].abstained
    ]
    return {
        "model_abstained": len(model_abstained),
        "gold_abstained": len(gold_abstained),
        "agreed": len(agreed),
        "over_abstained": len(model_abstained) - len(agreed),
        "missed_abstention": len(gold_abstained) - len(agreed),
    }


def build_summary(
    results: list[EvaluationResult],
    cases: list[RelationCase],
    *,
    requested_model: str,
    split_filter: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not results:
        raise ValueError("요약할 결과가 없습니다")
    score_names = tuple(results[0].scores)
    hallucinations = Counter(
        kind for result in results for kind in result.hallucinations
    )
    summary: dict[str, Any] = {
        "record_count": len(results),
        "target_count": len(cases),
        "split": split_filter or "all",
        "split_counts": dict(Counter(result.split for result in results)),
        "status_counts": dict(Counter(result.status for result in results)),
        "score_averages": {
            name: round(
                sum(result.scores[name] for result in results) / len(results), 4
            )
            for name in score_names
        },
        "asserted_relation": asserted_precision(results, cases),
        "abstention": abstention_report(results, cases),
        "hallucinations": dict(hallucinations),
        # day5 p51 — 어떤 경로로도 APPROVED가 없다는 것이 이 분포의 요점이다.
        "routing_counts": dict(Counter(result.routing for result in results)),
        "injection": injection_report_summary(results),
        # 하드코딩하지 않는다. 관찰값에서 유도하고 섞이면 위에서 실패한다.
        "evidence_kind": resolve_evidence_kind(results),
        "judge_status": "not_requested",
        "requested_model": requested_model,
        "generalization": GENERALIZATION_LEVEL,
    }
    if extra:
        summary.update(extra)
    return summary
