"""선정된 후보로 정답 라벨링 편집 틀을 만든다."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import _bootstrap
from bio_relation_workflow.data import build_labeling_template, write_labeling_template
from bio_relation_workflow.preprocessing import load_corpus
from bio_relation_workflow.schemas import CandidateSet

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
DEFAULT_CORPUS = PROJECT_ROOT / "local-data" / "note-corpus.json"
DEFAULT_CANDIDATES = PROJECT_ROOT / "local-data" / "candidates.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "cases" / "relation-cases.yaml"

SOURCE = {
    "title": "day6 관계탐색 프로토타입의 사전계산 관계 데이터",
    "license": "교육용 합성 데이터 (임상 근거 아님)",
    "revision": "day3-relation-extraction-sample",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="정답 라벨링 편집 틀 생성")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 라벨링한 파일을 덮어쓴다",
    )
    args = parser.parse_args()

    for path in (args.corpus, args.candidates):
        if not path.is_file():
            parser.error(f"먼저 prepare 단계를 실행하세요: {path}")
    if args.output.is_file() and not args.force:
        parser.error(
            f"이미 있습니다. 라벨을 지우고 다시 만들려면 --force: {args.output}"
        )

    corpus = load_corpus(args.corpus)
    candidate_set = CandidateSet.model_validate_json(
        args.candidates.read_text(encoding="utf-8")
    )
    template = build_labeling_template(candidate_set, corpus, source=SOURCE)
    write_labeling_template(template, args.output)

    cases = template["cases"]
    print(f"{args.output}")
    print(f"라벨링 대상: {len(cases)}건")
    print(f"  split {dict(Counter(c['split'] for c in cases))}")
    print(f"  층    {dict(Counter(c['stratum'] for c in cases))}")
    print(f"  노트 인용 총계: {sum(len(c['notes']) for c in cases)}건")
    print("각 case의 expected.relation을 treats / has_symptom / no_relation으로 채우세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
