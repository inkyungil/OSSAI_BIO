"""validation 결과에서 운영점(두 임계값)을 고르고 근거를 파일로 남긴다.

`day5 p37-38` — 임계값 선택은 validation에서 끝낸다. 이 스크립트는 sealed_test
결과를 아예 읽지 않으며, validation이 아닌 split을 넣으면 `sweep`이 거부한다.

산출물
    operating-point/threshold-tradeoff.csv   두 임계값 격자 전체
    operating-point/calibration.csv          confidence 값별 실제 정답률
    operating-point/operating-point.json     선택된 운영점과 선택 근거
"""

from __future__ import annotations

import argparse
import csv
import json

import _bootstrap
from bio_relation_workflow.config import load_settings, project_path
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.evaluation import (
    PPV_FLOOR,
    confidence_calibration,
    select_operating_point,
    sweep,
    write_tradeoff_csv,
)
from bio_relation_workflow.schemas import EvaluationResult

PROJECT_ROOT = _bootstrap.PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="운영점 선택 (validation 전용)")
    parser.add_argument("--config", default="configs/relation-nim.yaml")
    parser.add_argument(
        "--ppv-floor",
        type=float,
        default=PPV_FLOOR,
        help="화면에 뜬 관계 중 진짜 비율의 하한. 이것이 제약이다 (day3 p34).",
    )
    args = parser.parse_args()

    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    output_dir = project_path(PROJECT_ROOT, settings.paths.output)
    results_path = output_dir / "validation" / "results.jsonl"
    if not results_path.is_file():
        parser.error(f"먼저 validation을 실행하세요: {results_path}")

    results = [
        EvaluationResult.model_validate_json(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    all_cases = load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    case_by_id = {case.sample_id: case for case in all_cases}
    cases = [case_by_id[result.sample_id] for result in results]

    grid = sweep(cases, results)
    calibration = confidence_calibration(cases, results)

    report_dir = output_dir / "operating-point"
    write_tradeoff_csv(grid, report_dir / "threshold-tradeoff.csv")
    with (report_dir / "calibration.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(calibration[0]))
        writer.writeheader()
        writer.writerows(calibration)

    chosen = select_operating_point(grid, ppv_floor=args.ppv_floor)

    # confidence 임계값이 실제로 무언가를 가르는지. 관측된 confidence가 한 값뿐이거나
    # 정답률이 값에 따라 변하지 않으면 임계값은 선택 가능한 손잡이가 아니다.
    accuracies = {row["accuracy"] for row in calibration}
    distinct_confidences = [row["confidence"] for row in calibration]
    payload = {
        "split": "validation",
        "record_count": len(results),
        "ppv_floor": args.ppv_floor,
        "chosen": chosen,
        "confidence_calibration": calibration,
        "confidence_is_actionable": len(distinct_confidences) > 1
        and len(accuracies) > 1,
        "distinct_confidence_values": distinct_confidences,
        "evidence_kind": results[0].evidence_kind,
        "requested_model": settings.provider.model,
    }
    (report_dir / "operating-point.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"격자 {len(grid)}칸 · PPV 제약 {args.ppv_floor}")
    print("\n선택된 운영점")
    print(json.dumps(chosen, ensure_ascii=False, indent=2))
    print("\nconfidence 보정")
    for row in calibration:
        print(
            f"  conf={row['confidence']:<5} n={row['count']:<3} "
            f"정답률={row['accuracy']}"
        )
    if not payload["confidence_is_actionable"]:
        print(
            "\n주의 — confidence가 맞고 틀림을 가르지 못한다. "
            "임계값은 선택 가능한 손잡이가 아니며, 이 사실을 보고에 남긴다."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
