"""sealed_test 결과를 **실행하기 전에** 예측해 고정하고, 나중에 대조한다.

#16에서 validation 실패 8건이 development가 한 번도 담지 않은 두 문형에 정확히
몰린 것을 발견했다. 그 발견으로 프롬프트를 고치면 validation이 선택셋이 되므로
(`day5 p37-38`) 고치지 않기로 했다. 대신 **같은 실패가 sealed_test에서 어디에
날지를 미리 적어두고** 최종 1회 실행으로 대조한다.

사후에 "그래서 그렇게 된 것"이라고 말하는 것과, 미리 적어둔 것이 맞는 것은 증거의
무게가 다르다. 이 스크립트가 그 차이를 만든다.

예측의 입력은 **케이스 메타데이터(노트 문형)뿐이며 모델을 호출하지 않는다.** 문형은
라벨링 시점에 이미 정해진 데이터 속성이므로 이것을 보는 것은 sealed_test 결과를
엿보는 것이 아니다.

    register  data/sealed-test-prediction.json 을 만든다 (실행 전 1회)
    check     실제 sealed_test 결과와 대조한다 (실행 후)
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import _bootstrap
from bio_relation_workflow.config import load_settings, project_path
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.data.labeling_rules import draft_label
from bio_relation_workflow.preprocessing import load_corpus
from bio_relation_workflow.schemas import EvaluationResult, RelationCase

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
PREDICTION_PATH = "data/sealed-test-prediction.json"

# validation 41건에서 문형별로 관측된 모델 행동. 예외 없이 갈렸으므로 그대로 옮긴다.
#   문형 → (예측 relation, 예측 abstained, 근거)
PATTERN_BEHAVIOR: dict[str, tuple[str, bool, str]] = {
    "COMPLAINS": (
        "has_symptom",
        False,
        "validation에서 COMPLAINS 근거 7건 전부 통과",
    ),
    "PRESENTED": (
        "no_relation",
        False,
        "validation에서 PRESENTED 단독 5건 전부 실패 — "
        "모델이 '의심 소견'을 확립된 진술로 보지 않는다",
    ),
    "CONSIDER": (
        "no_relation",
        True,
        "validation에서 CONSIDER 3건 전부 보류 성공",
    ),
    "HEDGE": (
        "no_relation",
        False,
        "validation에서 HEDGE 단독 3건 전부 실패 — "
        "프롬프트에 규칙이 있는데도 보류하지 않았다",
    ),
    "COOCCURRENCE": (
        "no_relation",
        False,
        "validation에서 동시출현만 23건 전부 통과",
    ),
}


def evidence_pattern(case: RelationCase, notes_by_id: dict[str, Any]) -> str:
    """이 케이스의 정답을 지탱하는 문형. 여러 개면 우선순위가 높은 쪽."""
    draft = draft_label(
        [notes_by_id[note_id] for note_id in case.note_ids],
        disease=case.disease,
        partner=case.partner,
        partner_label=case.partner_label,
    )
    kinds = {k.pattern for k in draft.evidence_kinds if k.kind != "cooccurrence_only"}
    # COMPLAINS가 하나라도 있으면 모델은 그것을 근거로 관계를 인정했다.
    for pattern in ("COMPLAINS", "PRESENTED", "CONSIDER", "HEDGE"):
        if pattern in kinds:
            return pattern
    return "COOCCURRENCE"


def predict(cases: list[RelationCase], notes_by_id: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in sorted(cases, key=lambda c: c.sample_id):
        pattern = evidence_pattern(case, notes_by_id)
        relation, abstained, rationale = PATTERN_BEHAVIOR[pattern]
        will_pass = (
            relation == case.expected.relation
            and abstained == case.expected.abstained
        )
        rows.append(
            {
                "sample_id": case.sample_id,
                "pattern": pattern,
                "gold_relation": case.expected.relation,
                "gold_abstained": case.expected.abstained,
                "predicted_relation": relation,
                "predicted_abstained": abstained,
                "predicted_status": "passed" if will_pass else "failed",
                "rationale": rationale,
            }
        )

    predicted_failures = [r for r in rows if r["predicted_status"] == "failed"]
    relation_correct = sum(
        1 for r in rows if r["predicted_relation"] == r["gold_relation"]
    )
    abstention_correct = sum(
        1 for r in rows if r["predicted_abstained"] == r["gold_abstained"]
    )
    asserted = [r for r in rows if r["predicted_relation"] != "no_relation"]
    gold_positive = [r for r in rows if r["gold_relation"] != "no_relation"]
    asserted_correct = [
        r for r in asserted if r["predicted_relation"] == r["gold_relation"]
    ]
    total = len(rows)
    return {
        "registered_for": "sealed_test",
        "basis": "케이스 노트 문형 + validation에서 관측된 문형별 모델 행동",
        "model_was_called": False,
        "record_count": total,
        "cases": rows,
        "predicted_summary": {
            "task_success": round(1 - len(predicted_failures) / total, 4),
            "schema_validity": 1.0,
            "relation_correct": round(relation_correct / total, 4),
            "abstention_correct": round(abstention_correct / total, 4),
            "model_abstained": sum(1 for r in rows if r["predicted_abstained"]),
            "gold_abstained": sum(1 for r in rows if r["gold_abstained"]),
            "asserted": len(asserted),
            "ppv": (
                round(len(asserted_correct) / len(asserted), 4) if asserted else None
            ),
            "recall": (
                round(len(asserted_correct) / len(gold_positive), 4)
                if gold_positive
                else None
            ),
            "hallucination_OMISSION": sum(
                1 for r in predicted_failures if r["pattern"] == "PRESENTED"
            ),
        },
        "predicted_failures": [r["sample_id"] for r in predicted_failures],
        "pattern_behavior": {
            key: {"relation": v[0], "abstained": v[1], "rationale": v[2]}
            for key, v in PATTERN_BEHAVIOR.items()
        },
    }


def check(prediction: dict[str, Any], results: list[EvaluationResult]) -> dict[str, Any]:
    predicted = {row["sample_id"]: row for row in prediction["cases"]}
    actual = {result.sample_id: result for result in results}
    missing = sorted(set(predicted) - set(actual))
    if missing:
        raise ValueError(f"결과에 없는 케이스가 있습니다: {missing}")

    hits, misses = [], []
    for sample_id, row in predicted.items():
        result = actual[sample_id]
        record = {
            "sample_id": sample_id,
            "pattern": row["pattern"],
            "predicted": row["predicted_status"],
            "actual": result.status,
            "actual_relation": result.output.relation if result.output else None,
            "actual_abstained": result.output.abstained if result.output else None,
        }
        (hits if row["predicted_status"] == result.status else misses).append(record)
    return {
        "checked": len(predicted),
        "prediction_hits": len(hits),
        "prediction_accuracy": round(len(hits) / len(predicted), 4),
        "mispredicted": misses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="sealed_test 예측 사전등록·대조")
    parser.add_argument("mode", choices=["register", "check"])
    parser.add_argument("--config", default="configs/relation-nim.yaml")
    parser.add_argument(
        "--force", action="store_true", help="이미 등록된 예측을 덮어쓴다"
    )
    args = parser.parse_args()

    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    prediction_path = project_path(PROJECT_ROOT, PREDICTION_PATH)

    if args.mode == "register":
        if prediction_path.is_file() and not args.force:
            parser.error(
                f"이미 등록돼 있습니다: {prediction_path}. "
                "사전등록을 결과 본 뒤에 고치면 의미가 없으므로 --force가 필요합니다"
            )
        all_cases = load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
        cases = [case for case in all_cases if case.split == "sealed_test"]
        if not cases:
            parser.error("sealed_test 케이스가 없습니다")
        corpus = load_corpus(project_path(PROJECT_ROOT, settings.paths.note_corpus))
        notes_by_id = {note.note_id: note for note in corpus.notes}
        payload = predict(cases, notes_by_id)
        prediction_path.parent.mkdir(parents=True, exist_ok=True)
        prediction_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"등록: {prediction_path}")
        print(json.dumps(payload["predicted_summary"], ensure_ascii=False, indent=2))
        print(f"\n실패 예측 {len(payload['predicted_failures'])}건")
        for sample_id in payload["predicted_failures"]:
            row = next(r for r in payload["cases"] if r["sample_id"] == sample_id)
            print(f"  {sample_id:<28} {row['pattern']}")
        return 0

    if not prediction_path.is_file():
        parser.error(f"등록된 예측이 없습니다: {prediction_path}")
    results_path = (
        project_path(PROJECT_ROOT, settings.paths.output)
        / "sealed_test"
        / "results.jsonl"
    )
    if not results_path.is_file():
        parser.error(f"먼저 sealed_test를 실행하세요: {results_path}")
    results = [
        EvaluationResult.model_validate_json(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = check(
        json.loads(prediction_path.read_text(encoding="utf-8")), results
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
