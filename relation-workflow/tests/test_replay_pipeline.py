"""replay 경로 통합 — 저장 응답으로 실행·채점·요약이 끝까지 도는지.

실제 API 응답이 아직 없으므로 정답에서 만든 stub 응답으로 배관을 검사한다. 이 stub은
모델 품질 표본이 아니다. 실제 응답과의 일치 확인은 fixture를 고정한 뒤에 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bio_relation_workflow.evaluation import build_summary, score_observations
from bio_relation_workflow.providers import RecordedProvider
from bio_relation_workflow.workflow import run_cases

# 상위 폴더 이름에 기대지 않는다. 프로젝트를 옮겨도 따라온다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT = PROJECT_ROOT / "prompts" / "relation-verdict.md"


def _stub_response(case, note_texts, *, corrupt=False):
    """정답을 그대로 따르는 응답. corrupt=True면 인용문을 날조한다."""
    if case.expected.abstained:
        return {
            "relation": "no_relation",
            "evidence": [],
            "confidence": 0.2,
            "abstained": True,
            "abstention_reason": "노트가 관계를 진술하지 않음",
            "tool_requests": [],
        }
    evidence = []
    for note_id in case.expected.note_ids:
        text = note_texts[note_id]
        quote = "완전히 지어낸 문장이다" if corrupt else text[:20]
        evidence.append(
            {"evidence_id": f"e{len(evidence) + 1}", "quote": quote, "note_id": note_id}
        )
    return {
        "relation": case.expected.relation,
        "evidence": evidence,
        "confidence": 0.8,
        "abstained": False,
        "abstention_reason": None,
        "tool_requests": [],
    }


@pytest.fixture
def stub_fixture(tmp_path, cases, corpus):
    note_texts = {note.note_id: note.text for note in corpus.notes}
    selected = cases[:12]
    path = tmp_path / "responses.jsonl"
    path.write_text(
        "".join(
            json.dumps(
                {
                    "sample_id": case.sample_id,
                    "response": _stub_response(
                        case, note_texts, corrupt=(index == 0)
                    ),
                },
                ensure_ascii=False,
            )
            + "\n"
            for index, case in enumerate(selected)
        ),
        encoding="utf-8",
    )
    return path, selected, note_texts


def test_replay_runs_and_scores(stub_fixture, corpus):
    path, selected, note_texts = stub_fixture

    observations = run_cases(
        cases=selected,
        notes=corpus.notes,
        prompt_path=PROMPT,
        provider=RecordedProvider(path),
    )
    assert len(observations) == len(selected)
    assert all(o.evidence_kind == "test_only" for o in observations)
    assert not any(o.model_error for o in observations)

    results = score_observations(selected, observations, note_texts=note_texts)
    summary = build_summary(results, selected, requested_model="stub")

    assert summary["evidence_kind"] == "test_only"
    assert summary["record_count"] == len(selected)
    assert summary["generalization"].startswith("SINGLE")


def test_replay_flags_fabricated_quote(stub_fixture, corpus):
    path, selected, note_texts = stub_fixture
    observations = run_cases(
        cases=selected,
        notes=corpus.notes,
        prompt_path=PROMPT,
        provider=RecordedProvider(path),
    )
    results = score_observations(selected, observations, note_texts=note_texts)
    first = results[0]
    if selected[0].expected.note_ids:
        # 날조한 인용문은 grounding gate에서 걸려야 한다.
        assert first.scores["quote_grounding"] < 0.8
        assert first.status == "failed"
        assert "SOURCE" in first.hallucinations


def test_missing_response_becomes_model_error(tmp_path, cases, corpus):
    path = tmp_path / "empty.jsonl"
    path.write_text(
        json.dumps({"sample_id": "없는-건", "response": {}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    observations = run_cases(
        cases=cases[:1],
        notes=corpus.notes,
        prompt_path=PROMPT,
        provider=RecordedProvider(path),
    )
    assert observations[0].model_error
    assert "저장 응답이 없습니다" in observations[0].model_error

    note_texts = {note.note_id: note.text for note in corpus.notes}
    results = score_observations(cases[:1], observations, note_texts=note_texts)
    assert results[0].status == "inconclusive"


def test_summary_refuses_mixed_evidence_kinds(cases, corpus):
    from bio_relation_workflow.evaluation import resolve_evidence_kind
    from bio_relation_workflow.schemas import EvaluationResult

    def _result(kind):
        return EvaluationResult(
            sample_id="x",
            family_id="폐렴",
            split="development",
            status="passed",
            scores={},
            reasons={},
            evidence_kind=kind,
        )

    with pytest.raises(ValueError, match="섞였습니다"):
        resolve_evidence_kind([_result("test_only"), _result("live_quality")])
