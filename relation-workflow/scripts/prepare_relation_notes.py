"""프로토타입 HTML에서 임상 노트 코퍼스를 복원해 저장한다."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import _bootstrap
from bio_relation_workflow.preprocessing import build_corpus, write_corpus

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
# 입력은 같은 bio/ 아래 day6 실습 폴더의 관계탐색 프로토타입이다. 경로를 바꾸려면 --source.
BIO_ROOT = PROJECT_ROOT.parent
DEFAULT_SOURCE = BIO_ROOT / "day6" / "relation-explorer.html"
DEFAULT_OUTPUT = PROJECT_ROOT / "local-data" / "note-corpus.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="임상 노트 코퍼스 복원")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expect-notes", type=int, default=108)
    parser.add_argument("--expect-entities", type=int, default=30)
    args = parser.parse_args()

    if not args.source.is_file():
        parser.error(f"원본 HTML을 찾을 수 없습니다: {args.source}")

    corpus = build_corpus(args.source)

    if len(corpus.notes) != args.expect_notes:
        parser.error(
            f"노트 수가 기대와 다릅니다: {len(corpus.notes)} != {args.expect_notes}"
        )
    if len(corpus.entities) != args.expect_entities:
        parser.error(
            f"개체 수가 기대와 다릅니다: {len(corpus.entities)} != {args.expect_entities}"
        )

    write_corpus(corpus, args.output)

    label_counts = Counter(entity.label for entity in corpus.entities)
    without_entity = [note.note_id for note in corpus.notes if not note.entities]
    nested = corpus.provenance["nested_entities"]

    print(f"{args.output}")
    print(f"노트: {len(corpus.notes)}건 (원본 {corpus.provenance['notes_in_source']}건 중)")
    print(f"개체: {len(corpus.entities)}종 {dict(label_counts)}")
    entity_counts = Counter(len(note.entities) for note in corpus.notes)
    print(f"노트당 개체 수 분포: {dict(sorted(entity_counts.items()))}")
    print(f"개체가 없는 노트: {len(without_entity)}건 {without_entity[:5]}")
    print(f"중첩 개체(최장 일치 필요): {len(nested)}쌍 {nested[:5]}")
    print(f"source_sha256: {corpus.source_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
