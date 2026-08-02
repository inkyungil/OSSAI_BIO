"""저장 응답 provider로 관계 판정 workflow를 실행한다.

API를 호출하지 않는다. 결과는 evidence_kind=test_only이며 파싱·검증·분기 코드를
재현하는 회귀 검사용이지 모델 품질 근거가 아니다(day5 p53).
"""

from __future__ import annotations

import argparse

import _bootstrap
from bio_relation_workflow.config import load_settings, project_path
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.preprocessing import load_corpus
from bio_relation_workflow.providers import RecordedProvider
from bio_relation_workflow.workflow import run_cases

PROJECT_ROOT = _bootstrap.PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="저장 응답 관계 판정 workflow")
    parser.add_argument("--config", default="configs/relation.yaml")
    parser.add_argument("--split", choices=["development", "validation", "sealed_test"])
    args = parser.parse_args()

    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    if settings.provider.kind != "recorded":
        raise ValueError("이 명령은 API를 호출하지 않는 replay 전용입니다")

    responses_path = project_path(PROJECT_ROOT, settings.paths.recorded_responses)
    if not responses_path.is_file():
        parser.error(
            f"저장 응답이 없습니다: {responses_path}\n"
            "실제 실행 뒤 freeze_relation_responses.py로 fixture를 만드세요."
        )

    cases = load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    if args.split:
        cases = [case for case in cases if case.split == args.split]
        if not cases:
            parser.error(f"해당 split에 케이스가 없습니다: {args.split}")

    corpus = load_corpus(project_path(PROJECT_ROOT, settings.paths.note_corpus))
    observations = run_cases(
        cases=cases,
        notes=corpus.notes,
        prompt_path=project_path(PROJECT_ROOT, settings.paths.prompt),
        provider=RecordedProvider(responses_path),
        max_notes=settings.notes.max_notes_per_case,
        max_chars=settings.notes.max_note_chars,
    )

    output_path = project_path(PROJECT_ROOT, settings.paths.output) / "observations.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(observation.model_dump_json() + "\n" for observation in observations),
        encoding="utf-8",
    )
    failed = [o.sample_id for o in observations if o.model_error]
    print(f"{output_path}: {len(observations)}건")
    if failed:
        print(f"저장 응답이 없는 건 {len(failed)}: {failed[:5]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
