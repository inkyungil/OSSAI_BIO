"""validation에서 고른 운영점을 sealed_test에 그대로 적용한다 (#20).

**선택이 아니라 적용이다.** 임계값은 `select_operating_point.py`가 validation에서
이미 골랐고, 여기서는 그 값을 읽어 쓰기만 한다. sealed_test 결과를 보고 임계값을
다시 고르면 평가셋이 선택셋으로 변질된다(`day5 p37-38`).

그 규율을 코드로 지킨다 — 저장된 운영점 파일이 없으면 실행을 거부하고, 격자 스윕은
아예 하지 않는다.
"""

from __future__ import annotations

import argparse
import json

import _bootstrap
from bio_relation_workflow.config import load_settings, project_path
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.evaluation import evaluate_operating_point
from bio_relation_workflow.schemas import EvaluationResult

PROJECT_ROOT = _bootstrap.PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="운영점 적용 (선택 아님)")
    parser.add_argument("--config", default="configs/relation-nim.yaml")
    parser.add_argument("--split", default="sealed_test")
    args = parser.parse_args()

    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    output_dir = project_path(PROJECT_ROOT, settings.paths.output)
    chosen_path = output_dir / "operating-point" / "operating-point.json"
    if not chosen_path.is_file():
        parser.error(
            f"운영점이 아직 선택되지 않았습니다: {chosen_path}. "
            "validation에서 먼저 고르세요 (select_operating_point.py)"
        )
    registered = json.loads(chosen_path.read_text(encoding="utf-8"))
    if registered["split"] != "validation":
        parser.error("운영점은 validation에서 고른 것이어야 합니다")
    chosen = registered["chosen"]

    results_path = output_dir / args.split / "results.jsonl"
    if not results_path.is_file():
        parser.error(f"먼저 {args.split}을 실행하세요: {results_path}")
    results = [
        EvaluationResult.model_validate_json(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    all_cases = load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    case_by_id = {case.sample_id: case for case in all_cases}
    cases = [case_by_id[result.sample_id] for result in results]

    applied = evaluate_operating_point(
        cases,
        results,
        min_cooccur=chosen["min_cooccur"],
        min_confidence=chosen["min_confidence"],
    )
    payload = {
        "applied_to": args.split,
        "operating_point": {
            "min_cooccur": chosen["min_cooccur"],
            "min_confidence": chosen["min_confidence"],
        },
        "chosen_on": "validation",
        "ppv_floor_used_at_selection": registered["ppv_floor"],
        "validation_result": {
            key: chosen[key]
            for key in ("auto_show", "ppv", "silent_miss", "review_queue", "recall_shown")
        },
        f"{args.split}_result": applied,
        "evidence_kind": results[0].evidence_kind,
    }
    target = output_dir / args.split / "operating-point-applied.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
