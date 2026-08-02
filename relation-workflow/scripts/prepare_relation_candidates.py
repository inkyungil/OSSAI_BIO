"""노트에서 관계 후보를 재계산하고 층화·split을 배정한다.

원본 그래프 엣지 재현을 회귀 검사로 강제한다. 재계산 결과가 원본과 어긋나면 이후 모든
평가의 전제가 무너지므로 여기서 멈춘다.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import _bootstrap
from bio_relation_workflow.preprocessing import (
    assign_splits,
    build_candidates,
    extract_embedded_data,
    load_corpus,
)

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
BIO_ROOT = PROJECT_ROOT.parent
DEFAULT_SOURCE = BIO_ROOT / "day6" / "relation-explorer.html"
DEFAULT_CORPUS = PROJECT_ROOT / "local-data" / "note-corpus.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "local-data" / "candidates.json"


def read_reference_edges(html_path: Path) -> dict[tuple[str, str], dict[str, bool]]:
    """원본 그래프가 참조표와 대조한 엣지만 읽는다."""
    data = extract_embedded_data(html_path.read_text(encoding="utf-8"))
    marks: dict[tuple[str, str], dict[str, bool]] = {}
    for graph in data["graphs"].values():
        for edge in graph["edges"]:
            marks[(edge["source"], edge["target"])] = {
                "in_reference": bool(edge["in_reference"]),
                "reference_error": bool(edge["reference_error"]),
            }
    return marks


def read_original_edges(html_path: Path) -> set[tuple[tuple[str, str], str]]:
    data = extract_embedded_data(html_path.read_text(encoding="utf-8"))
    return {
        (tuple(sorted((edge["source"], edge["target"]))), edge["relation"])
        for graph in data["graphs"].values()
        for edge in graph["edges"]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="관계 후보 재계산과 층화")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-cooccur", type=int, default=2)
    parser.add_argument("--target-total", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260802)
    args = parser.parse_args()

    if not args.corpus.is_file():
        parser.error(f"먼저 prepare_relation_notes.py를 실행하세요: {args.corpus}")

    corpus = load_corpus(args.corpus)
    candidate_set = build_candidates(
        corpus,
        reference_edges=read_reference_edges(args.source),
        min_cooccur=args.min_cooccur,
    )

    # --- 회귀 검사: 원본 그래프 엣지 재현 ---
    original = read_original_edges(args.source)
    recomputed = {
        ((tuple(sorted((c.disease, c.partner)))), c.candidate_relation)
        for c in candidate_set.candidates
        if c.support >= args.min_cooccur
    }
    if recomputed != original:
        parser.error(
            "원본 엣지 재현 실패 — "
            f"원본에만 {sorted(original - recomputed)}, "
            f"재계산에만 {sorted(recomputed - original)}"
        )
    candidate_set.provenance["original_edges_reproduced"] = len(original)

    assign_splits(candidate_set, target_total=args.target_total, seed=args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        candidate_set.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    def counts(values) -> str:
        return json.dumps(Counter(values), ensure_ascii=False)

    selected = candidate_set.selected
    support = dict(sorted(Counter(c.support for c in candidate_set.candidates).items()))
    print(f"{args.output}")
    print(f"회귀 검사 통과 — 원본 엣지 {len(original)}개 100% 재현")
    print(f"후보 전체: {len(candidate_set.candidates)}쌍 support 분포 {support}")
    print(f"허브 개체: {candidate_set.hub_entities}")
    print(f"선정: {len(selected)}건")
    print(f"  층       {counts(c.stratum for c in selected)}")
    print(f"  후보관계 {counts(c.candidate_relation for c in selected)}")
    for split in ("development", "validation", "sealed_test"):
        rows = [c for c in selected if c.split == split]
        print(f"  {split:<12} {len(rows):>3}건 {counts(c.stratum for c in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
