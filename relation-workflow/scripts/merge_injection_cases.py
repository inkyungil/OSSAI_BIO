"""주입 평가용 합성 노트와 케이스를 코퍼스·라벨 파일에 합친다.

주입 노트는 동시출현 통계에 넣지 않는다. 후보 생성 규칙이 만든 것이 아니라 평가를 위해
직접 작성한 것이므로, 재계산 회귀 검사(원본 엣지 67개 재현)를 오염시키면 안 된다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

import _bootstrap
from bio_relation_workflow.preprocessing import load_corpus, write_corpus
from bio_relation_workflow.schemas import ClinicalNote

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
DEFAULT_INJECTIONS = PROJECT_ROOT / "data" / "injection-notes.yaml"
DEFAULT_CORPUS = PROJECT_ROOT / "local-data" / "note-corpus.json"
DEFAULT_CASES = PROJECT_ROOT / "data" / "cases" / "relation-cases.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="주입 노트·케이스 합치기")
    parser.add_argument("--injections", type=Path, default=DEFAULT_INJECTIONS)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args()

    injections = yaml.safe_load(args.injections.read_text(encoding="utf-8"))
    corpus = load_corpus(args.corpus)
    known = {entity.entity_id for entity in corpus.entities}

    existing_notes = {note.note_id for note in corpus.notes}
    added_notes = 0
    for item in injections["notes"]:
        if item["note_id"] in existing_notes:
            continue
        unknown = set(item["entities"]) - known
        if unknown:
            parser.error(f"사전에 없는 개체입니다: {sorted(unknown)}")
        corpus.notes.append(
            ClinicalNote(
                note_id=item["note_id"],
                text=item["text"].strip(),
                entities=sorted(set(item["entities"])),
            )
        )
        added_notes += 1
    corpus.provenance["injection_notes"] = sorted(
        item["note_id"] for item in injections["notes"]
    )
    write_corpus(corpus, args.corpus)

    document = yaml.safe_load(args.cases.read_text(encoding="utf-8"))
    existing_cases = {case["pair_id"] for case in document["cases"]}
    note_text = {note.note_id: note.text for note in corpus.notes}
    added_cases = 0
    for item in injections["cases"]:
        if item["pair_id"] in existing_cases:
            continue
        document["cases"].append(
            {
                "sample_id": f"{item['pair_id']}-{item['disease']}-{item['partner']}",
                "pair_id": item["pair_id"],
                "disease": item["disease"],
                "partner": item["partner"],
                "partner_label": item["partner_label"],
                "candidate_relation": item["candidate_relation"],
                "support": len(item["note_ids"]),
                "split": item["split"],
                "stratum": item["stratum"],
                "risk_level": item["risk_level"],
                "in_reference": None,
                "reference_error": None,
                "notes": [
                    {"note_id": note_id, "text": note_text[note_id]}
                    for note_id in item["note_ids"]
                ],
                "expected": item["expected"],
                "label_rule": item["label_rule"],
                "label_origin": item["label_origin"],
                "tags": item["tags"],
            }
        )
        added_cases += 1

    header = args.cases.read_text(encoding="utf-8").split("artifact_schema_version")[0]
    args.cases.write_text(
        header + yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print(f"{args.corpus}: 주입 노트 {added_notes}건 추가 (전체 {len(corpus.notes)}건)")
    print(f"{args.cases}: 주입 케이스 {added_cases}건 추가 (전체 {len(document['cases'])}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
