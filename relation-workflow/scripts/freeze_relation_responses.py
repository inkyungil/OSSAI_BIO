"""승인된 실제 응답을 API 없는 회귀 fixture로 고정한다.

출처 규율: src/../scripts/freeze_recorded_responses.py — 전체 성공 + provider 오류 없음
조건을 그대로 지킨다. 부분 실패한 실행을 회귀 기준으로 굳히면 안 된다.
"""

from __future__ import annotations

import argparse
import json

import _bootstrap
from bio_relation_workflow.config import load_settings, project_path
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.schemas import ModelObservation

PROJECT_ROOT = _bootstrap.PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="실제 응답 fixture 고정")
    parser.add_argument("--config", default="configs/relation-nim.yaml")
    parser.add_argument("--output", default="data/recorded/relation-responses.jsonl")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="일부 split만 고정한다. 전수 실행이 아님을 fixture에 남긴다.",
    )
    args = parser.parse_args()

    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    observations_path = (
        project_path(PROJECT_ROOT, settings.paths.output) / "observations.jsonl"
    )
    if not observations_path.is_file():
        parser.error(f"실행 결과가 없습니다: {observations_path}")

    observations = [
        ModelObservation.model_validate_json(line)
        for line in observations_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if any(observation.evidence_kind != "live_quality" for observation in observations):
        parser.error("실제 API 응답만 fixture로 고정할 수 있습니다")
    if any(observation.model_error for observation in observations):
        parser.error("provider 오류가 있는 실행은 fixture로 고정할 수 없습니다")

    cases = load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    expected_ids = {case.sample_id for case in cases}
    actual_ids = {observation.sample_id for observation in observations}
    if actual_ids != expected_ids and not args.allow_partial:
        parser.error(
            "준비된 전체 케이스의 실행 결과가 필요합니다: "
            f"missing={sorted(expected_ids - actual_ids)[:5]} "
            "(일부만 고정하려면 --allow-partial)"
        )

    target = project_path(PROJECT_ROOT, args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(
            json.dumps(
                {
                    "sample_id": observation.sample_id,
                    "response": observation.raw_output,
                    "model_call": observation.model_call,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
            for observation in observations
        ),
        encoding="utf-8",
    )
    print(f"{target}: {len(observations)}건")
    if actual_ids != expected_ids:
        print(f"부분 고정 — 전체 {len(expected_ids)}건 중 {len(actual_ids)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
