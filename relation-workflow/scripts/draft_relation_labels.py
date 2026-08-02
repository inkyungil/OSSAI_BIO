"""노트 문형 규칙으로 정답 라벨 초안을 채운다.

**초안이다.** 사람이 규칙과 분포를 확인한 뒤에야 정답으로 쓴다. 규칙은
`data/labeling_rules.py`에 문형별로 적혀 있고 각 건에 어떤 규칙이 걸렸는지 남긴다.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

import _bootstrap
from bio_relation_workflow.data.labeling_rules import draft_label
from bio_relation_workflow.preprocessing import load_corpus

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
DEFAULT_CORPUS = PROJECT_ROOT / "local-data" / "note-corpus.json"
DEFAULT_CASES = PROJECT_ROOT / "data" / "cases" / "relation-cases.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="문형 규칙으로 정답 초안 채우기")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="파일을 쓰지 않고 분포만 출력한다",
    )
    args = parser.parse_args()

    corpus = load_corpus(args.corpus)
    note_by_id = {note.note_id: note for note in corpus.notes}
    document = yaml.safe_load(args.cases.read_text(encoding="utf-8"))

    rules = Counter()
    labels = Counter()
    by_candidate = Counter()
    for case in document["cases"]:
        notes = [note_by_id[item["note_id"]] for item in case["notes"]]
        draft = draft_label(
            notes,
            disease=case["disease"],
            partner=case["partner"],
            partner_label=case["partner_label"],
        )
        case["expected"] = {
            "relation": draft.relation,
            "note_ids": draft.note_ids,
            "abstained": draft.abstained,
        }
        case["label_rule"] = draft.rule
        case["label_origin"] = "rule-draft"
        rules[draft.rule] += 1
        key = "보류" if draft.abstained else draft.relation
        labels[key] += 1
        by_candidate[(case["candidate_relation"], key)] += 1

    if not args.dry_run:
        header = args.cases.read_text(encoding="utf-8").split("artifact_schema_version")[0]
        args.cases.write_text(
            header + yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"{args.cases}")

    total = len(document["cases"])
    print(f"라벨 초안 {total}건")
    print(f"  정답 분포 {json.dumps(labels, ensure_ascii=False)}")
    print(f"  보류 비율 {labels['보류'] / total:.1%}")
    print("  적용된 규칙")
    for rule, count in rules.most_common():
        print(f"    {count:>3}건  {rule}")
    print("  후보 유형 → 정답")
    for (candidate, actual), count in sorted(by_candidate.items()):
        mark = "=" if candidate == actual else "≠"
        print(f"    {candidate:<12} {mark} {actual:<12} {count:>3}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
