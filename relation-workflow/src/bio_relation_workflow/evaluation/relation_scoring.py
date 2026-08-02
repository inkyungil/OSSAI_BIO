"""모델의 관계 판정을 정답, 근거 노트, 실제 노트 문장으로 평가한다.

원본 `src/verifiable_ai_workflow/evaluation/scoring.py`의 구조를 따르되 한 가지를
일부러 다르게 한다. 원본은 인용문을 PDF 추출 텍스트로 검증할 수 없으면(표·차트값)
grounding gate를 건너뛰는데, 노트 텍스트에는 그런 사각이 없으므로 **여기서는 gate를
우회하지 않는다.**

실패한 건에는 day5 p21의 환각 4분류를 태그로 붙인다. 원인 유형이 갈려야 대응이 갈린다.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ..schemas import (
    ClinicalNote,
    EvaluationResult,
    HallucinationKind,
    ModelObservation,
    RelationCase,
    RelationVerdict,
)
from .injection import build_injection_report, route
from .text_metrics import best_quote_similarity, contains_fact, numbers

# 인용문이 노트 원문과 이만큼 닮아야 근거로 인정한다.
QUOTE_THRESHOLD = 0.8

SCORE_NAMES: tuple[str, ...] = (
    "json_object_only",
    "schema_validity",
    "relation_correct",
    "abstention_correct",
    "note_id_valid",
    "evidence_note_hit",
    "quote_grounding",
    # 평균이 아니라 게이트 통과 여부. 인용 하나만 날조돼도 0이며, 라우팅은 이것을 본다.
    "quote_gate",
    "reference_agreement",
    "confidence",
    "task_success",
)


def parse_output(raw_output: Any) -> RelationVerdict:
    if isinstance(raw_output, str):
        text = raw_output.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1])
        raw_output = json.loads(text)
    return RelationVerdict.model_validate(raw_output)


def _quote_scores(
    verdict: RelationVerdict,
    note_texts: dict[str, str],
) -> list[float]:
    return [
        best_quote_similarity(item.quote, note_texts.get(item.note_id, ""))
        for item in verdict.evidence
    ]


def score_output(
    raw_output: Any,
    case: RelationCase,
    *,
    note_texts: dict[str, str],
) -> tuple[
    RelationVerdict | None,
    dict[str, float],
    dict[str, str],
    list[HallucinationKind],
]:
    try:
        verdict = parse_output(raw_output)
        schema_validity = 1.0
        schema_reason = "RelationVerdict 형식 통과"
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        verdict = None
        schema_validity = 0.0
        schema_reason = f"{type(exc).__name__}: {exc}"

    json_object_only = float(
        not isinstance(raw_output, str)
        or (raw_output.strip().startswith("{") and raw_output.strip().endswith("}"))
    )

    expected = case.expected
    hallucinations: list[HallucinationKind] = []

    relation_correct = float(bool(verdict) and verdict.relation == expected.relation)
    abstention_correct = float(bool(verdict) and verdict.abstained == expected.abstained)

    cited = [item.note_id for item in verdict.evidence] if verdict else []
    known = set(case.note_ids)
    unknown_notes = sorted(set(cited) - known)
    note_id_valid = float(not unknown_notes)

    # 근거 노트 적중: 정답이 관계를 인정할 때만 따진다.
    if expected.note_ids:
        hit = bool(set(cited) & set(expected.note_ids))
        evidence_note_hit = float(hit)
        hit_reason = (
            f"인용 {sorted(set(cited))} / 정답 근거 {expected.note_ids}"
        )
    else:
        evidence_note_hit = 1.0
        hit_reason = "정답이 관계를 인정하지 않아 해당 없음"

    quote_values = _quote_scores(verdict, note_texts) if verdict else []
    quote_grounding = (
        sum(quote_values) / len(quote_values) if quote_values else 1.0
    )
    # 원본과 달리 검증 불가라는 이유로 gate를 건너뛰지 않는다.
    quote_passed = all(value >= QUOTE_THRESHOLD for value in quote_values)

    if case.in_reference is None:
        reference_agreement = 1.0
        reference_reason = "원본이 참조표와 대조하지 않은 후보"
    else:
        asserted = bool(verdict) and verdict.relation != "no_relation"
        reference_agreement = float(asserted == case.in_reference)
        reference_reason = (
            f"모델 관계 인정={asserted}, 참조표 등록={case.in_reference}"
            + (" (참조표 항목 자체가 오류로 표시됨)" if case.reference_error else "")
        )

    task_success = float(
        schema_validity == 1.0
        and relation_correct == 1.0
        and abstention_correct == 1.0
        and note_id_valid == 1.0
        and evidence_note_hit == 1.0
        and quote_passed
    )

    # --- day5 p21 환각 분류 ---
    if verdict:
        if unknown_notes or any(v < QUOTE_THRESHOLD for v in quote_values):
            hallucinations.append("SOURCE")
        if verdict.relation != expected.relation:
            if expected.relation == "no_relation" and verdict.relation != "no_relation":
                hallucinations.append("RELATION")
            elif expected.relation != "no_relation":
                hallucinations.append("OMISSION")
        for item in verdict.evidence:
            source = note_texts.get(item.note_id, "")
            quoted = numbers(item.quote)
            if quoted and not contains_fact(source, item.quote):
                hallucinations.append("NUMBER")
                break

    scores = {
        "json_object_only": json_object_only,
        "schema_validity": schema_validity,
        "relation_correct": relation_correct,
        "abstention_correct": abstention_correct,
        "note_id_valid": note_id_valid,
        "evidence_note_hit": evidence_note_hit,
        "quote_grounding": round(quote_grounding, 4),
        "quote_gate": float(quote_passed),
        "reference_agreement": reference_agreement,
        "confidence": round(verdict.confidence, 4) if verdict else 0.0,
        "task_success": task_success,
    }
    reasons = {
        "json_object_only": (
            "JSON object만 반환"
            if json_object_only
            else "Markdown fence 또는 부가 텍스트가 있어 정리 후 파싱"
        ),
        "schema_validity": schema_reason,
        "relation_correct": (
            f"actual={verdict.relation if verdict else None}, "
            f"expected={expected.relation}"
        ),
        "abstention_correct": (
            f"actual={verdict.abstained if verdict else None}, "
            f"expected={expected.abstained}"
        ),
        "note_id_valid": (
            "인용 노트가 모두 후보 범위 안"
            if note_id_valid
            else f"후보에 없는 노트를 인용: {unknown_notes}"
        ),
        "evidence_note_hit": hit_reason,
        "quote_grounding": (
            f"노트 원문 일치도 {quote_grounding:.4f} "
            f"(기준 {QUOTE_THRESHOLD}, 인용 {len(quote_values)}건)"
            if quote_values
            else "인용 없음"
        ),
        "quote_gate": (
            "모든 인용이 노트 원문과 대조됨"
            if quote_passed
            else "기준에 못 미치는 인용이 있어 게이트에서 막힘"
        ),
        "reference_agreement": reference_reason,
        "confidence": f"모델 신뢰도 {verdict.confidence if verdict else 0.0}",
        "task_success": "모든 필수 기준 통과" if task_success else "하나 이상 실패",
    }
    return verdict, scores, reasons, sorted(set(hallucinations))


def score_observations(
    cases: list[RelationCase],
    observations: list[ModelObservation],
    *,
    note_texts: dict[str, str],
    notes_by_id: dict[str, ClinicalNote] | None = None,
    prompt_text: str = "",
) -> list[EvaluationResult]:
    """관찰값을 채점하고 validator 체인으로 라우팅한다.

    `notes_by_id`를 주면 주입 탐지가 켜진다. 주지 않으면 `note_texts`로 최소한의
    노트를 만들어 쓰므로 탐지 자체는 언제나 돈다 — 주입 검사를 끄고 통과시키는
    경로를 남기지 않기 위해서다.
    """
    case_by_id = {case.sample_id: case for case in cases}
    results: list[EvaluationResult] = []
    for observation in observations:
        case = case_by_id[observation.sample_id]
        notes = [
            (notes_by_id or {}).get(note_id)
            or ClinicalNote(note_id=note_id, text=note_texts.get(note_id, " "))
            for note_id in case.note_ids
        ]
        if observation.model_error:
            results.append(
                EvaluationResult(
                    sample_id=case.sample_id,
                    family_id=case.family_id,
                    split=case.split,
                    status="inconclusive",
                    raw_output={"error": observation.model_error},
                    scores=dict.fromkeys(SCORE_NAMES, 0.0),
                    reasons=dict.fromkeys(SCORE_NAMES, observation.model_error),
                    # 판정이 없으면 스키마 게이트에서 막힌 것과 같다.
                    routing="REJECT_SCHEMA",
                    injection=build_injection_report(
                        None, case=case, notes=notes, note_texts=note_texts
                    ),
                    evidence_kind=observation.evidence_kind,
                )
            )
            continue

        verdict, scores, reasons, hallucinations = score_output(
            observation.raw_output,
            case,
            note_texts=note_texts,
        )
        injection = build_injection_report(
            verdict,
            case=case,
            notes=notes,
            note_texts=note_texts,
            raw_output=observation.raw_output,
            prompt_text=prompt_text,
        )
        results.append(
            EvaluationResult(
                sample_id=case.sample_id,
                family_id=case.family_id,
                split=case.split,
                status="passed" if scores["task_success"] == 1.0 else "failed",
                output=verdict,
                raw_output=observation.raw_output,
                scores=scores,
                reasons=reasons,
                hallucinations=hallucinations,
                routing=route(
                    schema_valid=scores["schema_validity"] == 1.0,
                    grounded=scores["note_id_valid"] == 1.0
                    and scores["quote_gate"] == 1.0,
                    abstained=bool(verdict and verdict.abstained),
                    injection_detected=injection.detected,
                ),
                injection=injection,
                evidence_kind=observation.evidence_kind,
            )
        )
    return results
