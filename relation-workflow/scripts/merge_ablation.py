"""절제 결과를 본 판정과 병합해 정확도 × 충실도 교차표를 만든다 (#19).

`day6 p18` — 개별 근거와 집계 오류를 함께 읽어야 한다. 판정이 맞았는지(정확도)와
그 판정을 만든 근거가 실제로 판정을 지탱했는지(충실도)는 다른 축이며, 둘을 곱해야
"맞았지만 이유는 딴 데 있었다"가 보인다.

교차표에서 가장 중요한 칸은 **맞음 × DECORATIVE**다. 정답을 냈는데 인용은 장식이었다면
그 정답은 재현되지 않을 것이다. `day6 p17`의 "사후 설명은 인과가 아님"이 그 칸이다.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import _bootstrap
from bio_relation_workflow.config import load_settings, project_path
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.schemas import EvaluationResult
from bio_relation_workflow.xai import AblationOutcome

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
FAITHFULNESS_ORDER = (
    "FAITHFUL",
    "REDUNDANT",
    "PARTIAL",
    "DECORATIVE",
    "NECESSITY_VACUOUS",
    "NOT_APPLICABLE",
)
# 두 축을 다 잰 건만 4분류에 들어간다. 나머지는 측정되지 않은 것이지 좋은 것이 아니다.
MEASURED = ("FAITHFUL", "REDUNDANT", "PARTIAL", "DECORATIVE")


def _load_results(base: Path, splits: list[str]) -> dict[str, EvaluationResult]:
    results = {}
    for split in splits:
        path = base / split / "results.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                result = EvaluationResult.model_validate_json(line)
                results[result.sample_id] = result
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="절제 결과 병합")
    parser.add_argument("--config", default="configs/relation-nim-ablation.yaml")
    parser.add_argument("--source-config", default="configs/relation-nim.yaml")
    parser.add_argument(
        "--split",
        action="append",
        choices=["development", "validation", "sealed_test"],
    )
    args = parser.parse_args()
    splits = args.split or ["development", "validation"]

    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    source = load_settings(project_path(PROJECT_ROOT, args.source_config))
    output_dir = project_path(PROJECT_ROOT, settings.paths.output)
    ablation_path = output_dir / "ablation.jsonl"
    if not ablation_path.is_file():
        parser.error(f"먼저 run_ablation_nim.py를 실행하세요: {ablation_path}")

    outcomes = [
        AblationOutcome.model_validate_json(line)
        for line in ablation_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    results = _load_results(project_path(PROJECT_ROOT, source.paths.output), splits)
    cases = {
        case.sample_id: case
        for case in load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    }

    rows = []
    for outcome in outcomes:
        result = results.get(outcome.sample_id)
        if result is None:
            continue
        case = cases[outcome.sample_id]
        correct = (
            result.output is not None
            and result.output.relation == case.expected.relation
            and result.output.abstained == case.expected.abstained
        )
        rows.append(
            {
                "sample_id": outcome.sample_id,
                "split": outcome.split,
                "gold_relation": case.expected.relation,
                "model_relation": outcome.original_relation,
                "correct": correct,
                "sufficient": outcome.sufficient,
                "necessary": outcome.necessary,
                "faithfulness": outcome.faithfulness,
                "sufficiency_relation": outcome.sufficiency_relation,
                "comprehensiveness_relation": outcome.comprehensiveness_relation,
                "note": outcome.note,
            }
        )

    crosstab = Counter(
        ("맞음" if row["correct"] else "틀림", row["faithfulness"]) for row in rows
    )
    # 판정 극성별로도 나눈다. no_relation은 근거를 빼도 no_relation이 되기 쉬워
    # 필요성이 구조적으로 낮게 나온다 — 섞어서 평균 내면 그 사실이 가려진다.
    by_polarity = Counter(
        (
            "관계 인정" if row["model_relation"] != "no_relation" else "관계 없음",
            row["faithfulness"],
        )
        for row in rows
    )

    (output_dir / "ablation-merged.csv").write_text("", encoding="utf-8")
    with (output_dir / "ablation-merged.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "splits": splits,
        "record_count": len(rows),
        "crosstab_accuracy_by_faithfulness": {
            f"{acc}|{kind}": count for (acc, kind), count in sorted(crosstab.items())
        },
        "crosstab_polarity_by_faithfulness": {
            f"{pol}|{kind}": count for (pol, kind), count in sorted(by_polarity.items())
        },
        "faithfulness_counts": dict(Counter(row["faithfulness"] for row in rows)),
        "measured_both_axes": sum(1 for row in rows if row["faithfulness"] in MEASURED),
        "necessity_untestable": sum(
            1 for row in rows if row["faithfulness"] == "NECESSITY_VACUOUS"
        ),
        # 정답을 냈는데 근거가 장식이었던 건. 가장 위험한 칸이다.
        "correct_but_decorative": sorted(
            row["sample_id"]
            for row in rows
            if row["correct"] and row["faithfulness"] == "DECORATIVE"
        ),
        "evidence_kind": "live_quality",
        "requested_model": settings.provider.model,
    }
    (output_dir / "ablation-summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"{len(rows)}건 병합\n")
    header = f"{'':<10}" + "".join(f"{k:>16}" for k in FAITHFULNESS_ORDER)
    print("정확도 × 충실도")
    print(header)
    for acc in ("맞음", "틀림"):
        line = f"{acc:<10}" + "".join(
            f"{crosstab.get((acc, k), 0):>16}" for k in FAITHFULNESS_ORDER
        )
        print(line)
    print("\n판정 극성 × 충실도")
    print(header)
    for pol in ("관계 인정", "관계 없음"):
        line = f"{pol:<8}" + "".join(
            f"{by_polarity.get((pol, k), 0):>16}" for k in FAITHFULNESS_ORDER
        )
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
