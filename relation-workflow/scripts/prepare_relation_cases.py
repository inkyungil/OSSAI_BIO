"""채워진 라벨링 YAML을 평가용 JSONL로 바꾼다."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import _bootstrap
from bio_relation_workflow.data import build_cases, split_note_overlap, write_cases

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
DEFAULT_AUTHORING = PROJECT_ROOT / "data" / "cases" / "relation-cases.yaml"
DEFAULT_OUTPUT = PROJECT_ROOT / "local-data" / "cases.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="라벨링 YAML을 평가 케이스로 변환")
    parser.add_argument("--authoring", type=Path, default=DEFAULT_AUTHORING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.authoring.is_file():
        parser.error(f"먼저 make_labeling_template.py를 실행하세요: {args.authoring}")

    cases = build_cases(args.authoring)
    write_cases(cases, args.output)

    labels = Counter(case.expected.relation for case in cases)
    abstained = sum(1 for case in cases if case.expected.abstained)
    overlap = split_note_overlap(cases)

    print(f"{args.output}: {len(cases)}건")
    print(f"  정답 분포 {json.dumps(labels, ensure_ascii=False)}")
    print(f"  보류 {abstained}건 ({abstained / len(cases):.1%})")
    print(f"  split {json.dumps(Counter(c.split for c in cases), ensure_ascii=False)}")
    print(
        "  후보 유형이 정답과 다른 건: "
        f"{sum(1 for c in cases if c.candidate_relation != c.expected.relation)}건"
    )
    print(
        f"  노트 {overlap['notes_used']}건 중 "
        f"{overlap['notes_in_multiple_splits']}건이 여러 split에 걸침 "
        f"(질병 family {overlap['families']}개) — day1b p8 한계로 함께 보고"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
