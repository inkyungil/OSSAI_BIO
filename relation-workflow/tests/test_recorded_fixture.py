"""고정한 fixture를 replay하면 live와 같은 결과가 나오는가.

`day5 p53` — replay 결과는 코드 회귀 근거이지 모델 품질 근거가 아니다. 그 구분이
성립하려면 **replay가 live와 채점까지 정확히 같아야** 한다. 다르면 fixture는 회귀
기준이 될 수 없다.

같아야 하는 것: status · scores · routing · hallucinations · 주입 탐지 결과
달라야 하는 것: evidence_kind (`test_only` vs `live_quality`) — 이것이 유일하다.

fixture나 live 결과가 없으면 건너뛴다. 둘 다 생성물이라 저장소에 없을 수 있다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bio_relation_workflow.evaluation import score_observations
from bio_relation_workflow.providers import RecordedProvider
from bio_relation_workflow.schemas import EvaluationResult
from bio_relation_workflow.workflow import run_cases

PROJECT_ROOT = Path(__file__).resolve().parents[1]

FIXTURE = PROJECT_ROOT / "data" / "recorded" / "relation-responses.jsonl"
PROMPT = PROJECT_ROOT / "prompts" / "relation-verdict.md"
LIVE_SPLITS = ("development", "validation", "sealed_test")


def _live_results() -> dict[str, EvaluationResult]:
    live: dict[str, EvaluationResult] = {}
    for split in LIVE_SPLITS:
        path = PROJECT_ROOT / "reports" / "relation-nim" / split / "results.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                result = EvaluationResult.model_validate_json(line)
                live[result.sample_id] = result
    return live


@pytest.fixture(scope="module")
def replayed(cases, corpus):
    if not FIXTURE.is_file():
        pytest.skip(f"먼저 freeze_relation_responses.py를 실행하세요: {FIXTURE}")
    frozen_ids = {
        json.loads(line)["sample_id"]
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    selected = [case for case in cases if case.sample_id in frozen_ids]
    observations = run_cases(
        cases=selected,
        notes=corpus.notes,
        prompt_path=PROMPT,
        provider=RecordedProvider(FIXTURE),
    )
    results = score_observations(
        selected,
        observations,
        note_texts={note.note_id: note.text for note in corpus.notes},
        notes_by_id={note.note_id: note for note in corpus.notes},
        prompt_text=PROMPT.read_text(encoding="utf-8"),
    )
    return {result.sample_id: result for result in results}


def test_fixture_replays_without_provider_error(replayed):
    assert replayed
    assert all(r.evidence_kind == "test_only" for r in replayed.values())
    assert all(r.status != "inconclusive" for r in replayed.values())


def test_replay_matches_live_on_everything_but_evidence_kind(replayed):
    live = _live_results()
    shared = sorted(set(replayed) & set(live))
    if not shared:
        pytest.skip("비교할 live 결과가 없습니다")

    mismatches = []
    for sample_id in shared:
        a, b = replayed[sample_id], live[sample_id]
        if (a.status, a.scores, a.routing, a.hallucinations) != (
            b.status,
            b.scores,
            b.routing,
            b.hallucinations,
        ):
            mismatches.append(sample_id)
    assert not mismatches, f"replay와 live가 다릅니다: {mismatches}"


def test_replay_reproduces_injection_findings(replayed):
    live = _live_results()
    shared = sorted(set(replayed) & set(live))
    if not shared:
        pytest.skip("비교할 live 결과가 없습니다")
    for sample_id in shared:
        assert replayed[sample_id].injection == live[sample_id].injection


def test_replay_is_never_counted_as_model_quality(replayed):
    """evidence_kind가 섞이면 요약이 거부해야 한다 (day5 p53)."""
    from bio_relation_workflow.evaluation import resolve_evidence_kind

    assert resolve_evidence_kind(list(replayed.values())) == "test_only"
