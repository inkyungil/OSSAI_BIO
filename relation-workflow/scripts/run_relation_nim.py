"""NVIDIA NIM으로 관계 판정을 순차 실행하고 즉시 평가한다.

원본 `scripts/run_nvidia_nim.py` 패턴을 따른다 — --live 필수, 건별 즉시 append,
건별 즉시 채점, 상한 초과 시 중단, inconclusive가 있으면 exit 1.

원본 `scripts/evaluate_workflow.py:62`의 evidence_kind 하드코딩은 복제하지 않는다.
요약의 evidence_kind는 관찰값에서 유도하며 섞이면 실패한다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap
from bio_relation_workflow.config import (
    load_project_env,
    load_settings,
    project_path,
)
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.evaluation import build_summary, score_observations
from bio_relation_workflow.evaluation.deepeval_runner import evaluate_results
from bio_relation_workflow.preprocessing import load_corpus
from bio_relation_workflow.providers.litellm_provider import LiteLLMProvider
from bio_relation_workflow.schemas import ModelObservation
from bio_relation_workflow.workflow import run_cases

PROJECT_ROOT = _bootstrap.PROJECT_ROOT


def _load_observations(path: Path) -> list[ModelObservation]:
    if not path.is_file():
        return []
    return [
        ModelObservation.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _append_observation(path: Path, observation: ModelObservation) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(observation.model_dump_json() + "\n")
        handle.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="NVIDIA NIM 관계 판정 live batch")
    parser.add_argument("--config", default="configs/relation-nim.yaml")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--split", choices=["development", "validation", "sealed_test"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-id")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("실제 API 호출에는 --live가 필요합니다")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit은 양수여야 합니다")

    load_project_env(PROJECT_ROOT)
    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    if settings.provider.kind != "litellm":
        raise ValueError("live 설정의 provider.kind는 litellm이어야 합니다")
    if not settings.provider.api_key_env:
        raise ValueError("live 설정에 api_key_env가 필요합니다")

    all_cases = load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    cases = all_cases
    if args.split:
        cases = [case for case in cases if case.split == args.split]
    if args.sample_id:
        cases = [case for case in cases if case.sample_id == args.sample_id]
        if len(cases) != 1:
            raise ValueError(f"sample_id를 찾을 수 없습니다: {args.sample_id}")
    if not cases:
        parser.error("실행할 케이스가 없습니다")

    corpus = load_corpus(project_path(PROJECT_ROOT, settings.paths.note_corpus))
    note_texts = {note.note_id: note.text for note in corpus.notes}
    notes_by_id = {note.note_id: note for note in corpus.notes}
    prompt_path = project_path(PROJECT_ROOT, settings.paths.prompt)
    prompt_text = prompt_path.read_text(encoding="utf-8")
    scoring_context = {
        "note_texts": note_texts,
        "notes_by_id": notes_by_id,
        "prompt_text": prompt_text,
    }

    output_dir = project_path(PROJECT_ROOT, settings.paths.output)
    # 관찰값은 split을 가로질러 한 파일에 쌓는다 — --resume이 이미 끝난 건을 건너뛰는
    # 근거가 이 파일이다. 반면 채점 산출물은 split별로 갈라 놓는다. 한 요약에 두
    # split이 섞이면 "임계값은 validation에서만 고른다"는 규율을 감사할 수 없다.
    observations_path = output_dir / "observations.jsonl"
    report_dir = output_dir / args.split if args.split else output_dir
    existing = _load_observations(observations_path)
    if existing and not args.resume:
        parser.error("기존 실행이 있습니다. 이어서 실행하려면 --resume을 사용하세요")
    completed_ids = {observation.sample_id for observation in existing}
    pending = [case for case in cases if case.sample_id not in completed_ids]
    if args.limit is not None:
        pending = pending[: args.limit]
    if len(existing) + len(pending) > settings.limits.max_requests:
        parser.error(f"설정된 task 상한은 {settings.limits.max_requests}건입니다")

    if pending:
        provider = LiteLLMProvider(
            model=settings.provider.model,
            api_key_env=settings.provider.api_key_env,
            api_base=settings.provider.api_base,
            structured_output=settings.provider.structured_output,
            max_requests=len(pending),
            requests_per_minute=settings.limits.requests_per_minute,
            max_retries=settings.limits.max_retries,
            retry_initial_seconds=settings.limits.retry_initial_seconds,
            max_cost_usd=settings.limits.max_cost_usd,
            max_input_tokens=settings.limits.max_input_tokens,
            max_output_tokens=settings.limits.max_output_tokens,
            max_wall_seconds=settings.limits.max_wall_seconds,
            input_cost_per_token_usd=settings.provider.input_cost_per_token_usd,
            output_cost_per_token_usd=settings.provider.output_cost_per_token_usd,
        )
        for index, case in enumerate(pending, start=1):
            observation = run_cases(
                cases=[case],
                notes=corpus.notes,
                prompt_path=prompt_path,
                provider=provider,
                max_notes=settings.notes.max_notes_per_case,
                max_chars=settings.notes.max_note_chars,
            )[0]
            _append_observation(observations_path, observation)
            result = score_observations([case], [observation], **scoring_context)[0]
            position = len(existing) + index
            print(f"[{position}/{len(cases)}] {case.sample_id}: {result.status}")

    all_observations = _load_observations(observations_path)
    case_by_id = {case.sample_id: case for case in all_cases}
    scored = [
        observation
        for observation in all_observations
        if not args.split or case_by_id[observation.sample_id].split == args.split
    ]
    evaluated = [case_by_id[observation.sample_id] for observation in scored]
    results = score_observations(evaluated, scored, **scoring_context)

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "results.jsonl").write_text(
        "".join(result.model_dump_json() + "\n" for result in results),
        encoding="utf-8",
    )
    evaluate_results(results, evaluated, report_dir / "deepeval")

    summary = build_summary(
        results,
        evaluated,
        requested_model=settings.provider.model,
        split_filter=args.split,
        extra={"requests_per_minute": settings.limits.requests_per_minute},
    )
    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["status_counts"].get("inconclusive", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
