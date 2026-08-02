"""저장된 관찰값을 채점하고 DeepEval 결과와 요약을 만든다.

evidence_kind는 관찰값에서 유도한다. 하드코딩하지 않는다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap
from bio_relation_workflow.config import load_settings, project_path
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.evaluation import build_summary, score_observations
from bio_relation_workflow.evaluation.deepeval_runner import evaluate_results
from bio_relation_workflow.preprocessing import load_corpus
from bio_relation_workflow.schemas import ModelObservation

PROJECT_ROOT = _bootstrap.PROJECT_ROOT


def load_observations(path: Path) -> list[ModelObservation]:
    return [
        ModelObservation.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="관계 판정 결정적 평가")
    parser.add_argument("--config", default="configs/relation.yaml")
    parser.add_argument("--split", choices=["development", "validation", "sealed_test"])
    args = parser.parse_args()

    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    output_dir = project_path(PROJECT_ROOT, settings.paths.output)
    observations_path = output_dir / "observations.jsonl"
    if not observations_path.is_file():
        parser.error(f"먼저 workflow를 실행하세요: {observations_path}")

    all_cases = load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    corpus = load_corpus(project_path(PROJECT_ROOT, settings.paths.note_corpus))
    note_texts = {note.note_id: note.text for note in corpus.notes}
    notes_by_id = {note.note_id: note for note in corpus.notes}
    # 주입이 시스템 프롬프트를 뽑아내려 했는지 대조하려면 프롬프트 원문이 필요하다.
    prompt_text = project_path(PROJECT_ROOT, settings.paths.prompt).read_text(
        encoding="utf-8"
    )

    observations = load_observations(observations_path)
    case_by_id = {case.sample_id: case for case in all_cases}
    # run 스크립트와 같은 규칙 — split을 주면 그 split만 채점하고 하위 폴더에 쓴다.
    if args.split:
        observations = [
            observation
            for observation in observations
            if case_by_id[observation.sample_id].split == args.split
        ]
        if not observations:
            parser.error(f"{args.split} split의 관찰값이 없습니다")
    report_dir = output_dir / args.split if args.split else output_dir
    cases = [case_by_id[observation.sample_id] for observation in observations]

    results = score_observations(
        cases,
        observations,
        note_texts=note_texts,
        notes_by_id=notes_by_id,
        prompt_text=prompt_text,
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "results.jsonl").write_text(
        "".join(result.model_dump_json() + "\n" for result in results),
        encoding="utf-8",
    )
    evaluate_results(results, cases, report_dir / "deepeval")

    summary = build_summary(
        results,
        cases,
        requested_model=settings.provider.model,
        split_filter=args.split,
    )
    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["status_counts"].get("inconclusive", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
