"""모델 호출을 실행하고 아직 채점하지 않은 관찰값을 남긴다.

출처: src/verifiable_ai_workflow/workflow/runner.py — 구조를 그대로 따랐다.
차이는 PDF 페이지 이미지 대신 노트 텍스트를 넣는 것뿐이다. 응답을 손대지 않고
그대로 저장하는 규율은 같다.
"""

from __future__ import annotations

from pathlib import Path

from ..providers.base import ModelProvider
from ..schemas import ClinicalNote, ModelObservation, RelationCase
from .note_inputs import build_case_input, build_messages


def run_cases(
    *,
    cases: list[RelationCase],
    notes: list[ClinicalNote],
    prompt_path: str | Path,
    provider: ModelProvider,
    max_notes: int = 10,
    max_chars: int = 2000,
) -> list[ModelObservation]:
    system_prompt = Path(prompt_path).read_text(encoding="utf-8")
    note_by_id = {note.note_id: note for note in notes}
    observations: list[ModelObservation] = []
    for case in cases:
        messages = build_messages(
            case_input=build_case_input(
                case,
                note_by_id,
                max_notes=max_notes,
                max_chars=max_chars,
            ),
            system_prompt=system_prompt,
        )
        try:
            raw_output = provider.generate(case.sample_id, messages)
            model_error = None
        except Exception as exc:
            raw_output = None
            model_error = f"{type(exc).__name__}: {exc}"
        observations.append(
            ModelObservation(
                sample_id=case.sample_id,
                family_id=case.family_id,
                split=case.split,
                known_note_ids=case.note_ids,
                raw_output=raw_output,
                model_error=model_error,
                model_call=getattr(provider, "last_call", None),
                evidence_kind=provider.evidence_kind,
            )
        )
    return observations
