"""루트 pyproject를 건드리지 않고 이 프로젝트의 src를 test 경로에 올린다."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

CORPUS_PATH = PROJECT_ROOT / "local-data" / "note-corpus.json"
CANDIDATES_PATH = PROJECT_ROOT / "local-data" / "candidates.json"
CASES_PATH = PROJECT_ROOT / "local-data" / "cases.jsonl"


@pytest.fixture(scope="session")
def corpus():
    """생성된 노트 코퍼스. 없으면 해당 test를 건너뛴다."""
    if not CORPUS_PATH.is_file():
        pytest.skip(f"먼저 prepare_relation_notes.py를 실행하세요: {CORPUS_PATH}")
    from bio_relation_workflow.preprocessing import load_corpus

    return load_corpus(CORPUS_PATH)


@pytest.fixture(scope="session")
def candidates():
    """생성된 후보 집합. 없으면 해당 test를 건너뛴다."""
    if not CANDIDATES_PATH.is_file():
        pytest.skip(
            f"먼저 prepare_relation_candidates.py를 실행하세요: {CANDIDATES_PATH}"
        )
    from bio_relation_workflow.schemas import CandidateSet

    return CandidateSet.model_validate_json(
        CANDIDATES_PATH.read_text(encoding="utf-8")
    )


@pytest.fixture(scope="session")
def cases():
    """라벨링을 마친 평가 케이스. 없으면 해당 test를 건너뛴다."""
    if not CASES_PATH.is_file():
        pytest.skip(f"먼저 prepare_relation_cases.py를 실행하세요: {CASES_PATH}")
    from bio_relation_workflow.data import load_cases

    return load_cases(CASES_PATH)
