"""라벨링 YAML 편집 틀을 만들고, 채워진 YAML을 평가 케이스로 바꾼다.

원본 `src/verifiable_ai_workflow/data/dataset.py`의 authoring → JSONL 흐름을 따른다.
사람이 채우는 칸은 `expected` 하나뿐이고 나머지는 후보 집합에서 미리 채워 넣는다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from ..schemas import (
    CandidatePair,
    CandidateSet,
    NoteCorpus,
    RelationCase,
)

AUTHORING_SCHEMA_VERSION = 1
# 라벨링을 시작하지 않은 칸의 표식. 이 값이 남아 있으면 build_cases가 거부한다.
UNLABELED = "TODO"


def _sample_id(candidate: CandidatePair) -> str:
    return f"{candidate.pair_id}-{candidate.disease}-{candidate.partner}"


def build_labeling_template(
    candidate_set: CandidateSet,
    corpus: NoteCorpus,
    *,
    source: dict[str, str],
) -> dict[str, Any]:
    """expected만 비운 편집 틀을 만든다."""
    note_text = {note.note_id: note.text for note in corpus.notes}
    cases = []
    for candidate in sorted(candidate_set.selected, key=lambda c: c.pair_id):
        cases.append(
            {
                "sample_id": _sample_id(candidate),
                "pair_id": candidate.pair_id,
                "disease": candidate.disease,
                "partner": candidate.partner,
                "partner_label": candidate.partner_label,
                "candidate_relation": candidate.candidate_relation,
                "support": candidate.support,
                "split": candidate.split,
                "stratum": candidate.stratum,
                "in_reference": candidate.in_reference,
                "reference_error": candidate.reference_error,
                # 읽기 전용 참고 자료. 판정은 이 문장들만 보고 내린다.
                "notes": [
                    {"note_id": note_id, "text": note_text[note_id]}
                    for note_id in candidate.note_ids
                ],
                # ↓ 사람이 채우는 칸
                "expected": {
                    "relation": UNLABELED,
                    "note_ids": [],
                    "abstained": False,
                },
            }
        )
    return {
        "artifact_schema_version": AUTHORING_SCHEMA_VERSION,
        "source": source,
        "corpus_sha256": candidate_set.corpus_sha256,
        "cases": cases,
    }


def write_labeling_template(template: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# 관계 판정 정답 라벨\n"
        "#\n"
        "# 각 case의 expected만 채운다. 나머지 값은 후보 생성 결과이므로 고치지 않는다.\n"
        "#   relation  : treats | has_symptom | no_relation\n"
        "#   note_ids  : 판정 근거가 되는 notes의 note_id. no_relation이면 비운다.\n"
        "#   abstained : 노트만으로 판정할 수 없으면 true (relation은 no_relation)\n"
        "#\n"
        f"# 판정을 시작하지 않은 칸은 {UNLABELED}로 남아 있다.\n"
    )
    target.write_text(
        header + yaml.safe_dump(template, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def build_cases(
    authoring_path: str | Path,
    *,
    default_risk_level: str = "medium",
) -> list[RelationCase]:
    source = yaml.safe_load(Path(authoring_path).read_text(encoding="utf-8"))
    if source.get("artifact_schema_version") != AUTHORING_SCHEMA_VERSION:
        raise ValueError(
            f"authoring artifact_schema_version은 {AUTHORING_SCHEMA_VERSION}이어야 합니다"
        )

    unlabeled = [
        item["sample_id"]
        for item in source["cases"]
        if item["expected"].get("relation") == UNLABELED
    ]
    if unlabeled:
        raise ValueError(
            f"라벨이 비어 있는 case가 {len(unlabeled)}건입니다: {unlabeled[:5]}"
        )

    cases = [
        RelationCase(
            sample_id=item["sample_id"],
            family_id=item["disease"],
            pair_id=item["pair_id"],
            disease=item["disease"],
            partner=item["partner"],
            partner_label=item["partner_label"],
            candidate_relation=item["candidate_relation"],
            support=item["support"],
            note_ids=[note["note_id"] for note in item["notes"]],
            split=item["split"],
            stratum=item["stratum"],
            risk_level=item.get("risk_level", default_risk_level),
            source=source["source"],
            expected=item["expected"],
            in_reference=item.get("in_reference"),
            reference_error=item.get("reference_error"),
            tags=item.get("tags", []),
        )
        for item in source["cases"]
    ]

    sample_ids = [case.sample_id for case in cases]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("sample_id는 중복될 수 없습니다")
    return cases


def write_cases(cases: list[RelationCase], output_path: str | Path) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(case.model_dump_json() + "\n" for case in cases),
        encoding="utf-8",
    )


def load_cases(path: str | Path) -> list[RelationCase]:
    return [
        RelationCase.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def split_note_overlap(cases: list[RelationCase]) -> dict[str, Any]:
    """split 사이에 겹치는 노트를 센다.

    split은 후보 단위로 배정했으므로 같은 노트가 여러 split에 나타난다. day1b p8은
    층화보다 그룹 단위 분리가 우선이라고 하므로, 이 값을 한계로 함께 보고한다.
    """
    splits_by_note: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        for note_id in case.note_ids:
            splits_by_note[note_id].add(case.split)
    shared = {n: sorted(s) for n, s in splits_by_note.items() if len(s) > 1}
    return {
        "notes_used": len(splits_by_note),
        "notes_in_multiple_splits": len(shared),
        "families": len({case.family_id for case in cases}),
        "cases_per_family": dict(
            sorted(Counter(case.family_id for case in cases).items())
        ),
    }
