"""운영점(임계값) 선택. **validation split에서만 부른다.**

`day3 p40` — 관계 잡음컷(min_cooccur)과 분류 운영점(confidence cut-off)은 "연속
신뢰도를 어디서 자를까"라는 같은 문제다. 그래서 두 축을 하나의 격자로 함께 쓸어본다.

`day3 p34` — 정확도를 최대화하지 않는다. 지켜야 할 지표를 제약으로 걸고 나머지를
최적화한다. 관계 탐색에서 놓침과 헛경보의 비용은 비대칭이다(`day6 p30`). 잘못된
약물-질병 연결을 화면에 띄우는 쪽이 훨씬 나쁘므로 **PPV를 제약으로 걸고** 그 아래에서
자동표시되는 정답 관계 수를 최대화한다.

라우팅 정책 — 한 후보가 갈 수 있는 곳은 넷이다.

    filtered      support < min_cooccur       모델에 가지도 않는다
    review_queue  보류했거나 confidence < 임계값  사람 확인 큐 (day6 p35)
    auto_show     관계 인정 + 임계값 이상        화면에 표시
    auto_drop     no_relation + 임계값 이상      조용히 버림

`auto_drop`이 이 정책의 유일한 무성(無聲) 실패 경로다. 정답이 관계인데 여기로 가면
사람도 못 보고 화면에도 없다. 그래서 `silent_miss`를 따로 센다.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Literal

from ..schemas import EvaluationResult, RelationCase

Route = Literal["filtered", "review_queue", "auto_show", "auto_drop"]

# 화면에 뜬 관계 중 진짜 비율의 하한. 헛경보가 놓침보다 비싸다는 판단을 숫자로 못박은
# 것이며, 이 값을 바꾸는 것이 곧 비용 비대칭을 바꾸는 것이다.
PPV_FLOOR = 0.95


def route_case(
    case: RelationCase,
    result: EvaluationResult,
    *,
    min_cooccur: int,
    min_confidence: float,
) -> Route:
    if case.support < min_cooccur:
        return "filtered"
    verdict = result.output
    # 스키마를 못 지킨 응답은 판정이 없다. 사람에게 보낸다.
    if verdict is None or verdict.abstained:
        return "review_queue"
    if verdict.confidence < min_confidence:
        return "review_queue"
    return "auto_show" if verdict.relation != "no_relation" else "auto_drop"


def evaluate_operating_point(
    cases: list[RelationCase],
    results: list[EvaluationResult],
    *,
    min_cooccur: int,
    min_confidence: float,
) -> dict[str, Any]:
    case_by_id = {case.sample_id: case for case in cases}
    counts: dict[Route, int] = {
        "filtered": 0,
        "review_queue": 0,
        "auto_show": 0,
        "auto_drop": 0,
    }
    shown_correct = 0
    silent_miss = 0
    queued_needing_human = 0
    filtered_positive = 0

    for result in results:
        case = case_by_id[result.sample_id]
        expected = case.expected
        # 사람이 봐야 하는 건 — 진짜 관계이거나, 정답이 보류인 건.
        needs_human = expected.relation != "no_relation" or expected.abstained
        route = route_case(
            case, result, min_cooccur=min_cooccur, min_confidence=min_confidence
        )
        counts[route] += 1
        if route == "auto_show" and result.output.relation == expected.relation:
            shown_correct += 1
        if route == "auto_drop" and needs_human:
            silent_miss += 1
        if route == "review_queue" and needs_human:
            queued_needing_human += 1
        if route == "filtered" and needs_human:
            filtered_positive += 1

    gold_positive = sum(1 for c in cases if c.expected.relation != "no_relation")
    shown = counts["auto_show"]
    queued = counts["review_queue"]
    return {
        "min_cooccur": min_cooccur,
        "min_confidence": round(min_confidence, 4),
        "filtered": counts["filtered"],
        "auto_show": shown,
        "auto_show_correct": shown_correct,
        # 화면에 뜬 것 중 맞은 비율. 사용자 체감은 이 값이다 (day3 p35-36).
        "ppv": round(shown_correct / shown, 4) if shown else None,
        "auto_drop": counts["auto_drop"],
        # 사람도 못 보고 화면에도 없는 건. 이 정책의 진짜 비용이다.
        "silent_miss": silent_miss + filtered_positive,
        "silent_miss_by_filter": filtered_positive,
        "review_queue": queued,
        # 큐에 들어간 것 중 실제로 사람 손이 필요한 비율. 낮으면 큐가 낭비다.
        "queue_precision": round(queued_needing_human / queued, 4) if queued else None,
        "recall_shown": (
            round(shown_correct / gold_positive, 4) if gold_positive else None
        ),
    }


def sweep(
    cases: list[RelationCase],
    results: list[EvaluationResult],
    *,
    cooccur_values: list[int] | None = None,
    confidence_values: list[float] | None = None,
) -> list[dict[str, Any]]:
    """두 임계값 격자를 쓸어 각 칸의 결과를 낸다."""
    if not results:
        raise ValueError("스윕할 결과가 없습니다")
    splits = {result.split for result in results}
    if splits != {"validation"}:
        # 규율을 문서가 아니라 코드로 지킨다 (day5 p37-38).
        raise ValueError(
            f"운영점은 validation에서만 고른다. 받은 split: {sorted(splits)}"
        )
    if cooccur_values is None:
        cooccur_values = sorted({case.support for case in cases})
    if confidence_values is None:
        # 관측된 confidence 값 자체가 후보 절단점이다. 그 사이에는 아무 건도 없다.
        observed = sorted(
            {result.output.confidence for result in results if result.output}
        )
        confidence_values = observed + [1.0001]
    return [
        evaluate_operating_point(
            cases, results, min_cooccur=cut, min_confidence=threshold
        )
        for cut in cooccur_values
        for threshold in confidence_values
    ]


def confidence_calibration(
    cases: list[RelationCase],
    results: list[EvaluationResult],
) -> list[dict[str, Any]]:
    """confidence 값별 실제 정답률.

    임계값이 의미를 가지려면 confidence가 맞고 틀림을 갈라야 한다. 이 표가 평평하면
    임계값을 어디에 두든 품질은 변하지 않으며, 그 사실 자체를 기록해야 한다.
    """
    case_by_id = {case.sample_id: case for case in cases}
    buckets: dict[float, list[EvaluationResult]] = {}
    for result in results:
        value = result.output.confidence if result.output else 0.0
        buckets.setdefault(value, []).append(result)
    rows = []
    for value in sorted(buckets):
        group = buckets[value]
        correct = sum(
            1
            for r in group
            if r.output
            and r.output.relation == case_by_id[r.sample_id].expected.relation
            and r.output.abstained == case_by_id[r.sample_id].expected.abstained
        )
        rows.append(
            {
                "confidence": value,
                "count": len(group),
                "correct": correct,
                "accuracy": round(correct / len(group), 4),
            }
        )
    return rows


def select_operating_point(
    grid: list[dict[str, Any]],
    *,
    ppv_floor: float = PPV_FLOOR,
) -> dict[str, Any]:
    """제약 우선 선택 (day3 p34).

    PPV 하한을 만족하는 칸 중에서 자동표시된 정답 관계 수를 최대화하고, 같으면
    무성 놓침이 적은 쪽, 그다음 큐가 짧은 쪽을 고른다. 자동표시가 0건인 칸은
    PPV가 정의되지 않으므로 제약을 "만족"한 것으로 치지 않는다.
    """
    feasible = [
        cell
        for cell in grid
        if cell["ppv"] is not None and cell["ppv"] >= ppv_floor
    ]
    if not feasible:
        raise ValueError(
            f"PPV {ppv_floor} 이상을 만족하는 운영점이 없습니다. "
            "제약을 낮추기 전에 모델을 고치는 것이 순서입니다."
        )
    return min(
        feasible,
        key=lambda cell: (
            -cell["auto_show_correct"],
            cell["silent_miss"],
            cell["review_queue"],
            cell["min_cooccur"],
            -cell["min_confidence"],
        ),
    )


def write_tradeoff_csv(grid: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(grid[0]))
        writer.writeheader()
        writer.writerows(grid)
