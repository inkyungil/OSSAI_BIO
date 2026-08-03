"""근거 절제 재질의를 실행하고 충실도를 채점한다 (#18-19, `day6 p17`).

케이스 하나당 두 번 더 묻는다.

    sufficiency        인용된 문장만 남긴 노트로 재질의
    comprehensiveness  인용된 문장만 지운 노트로 재질의

근거를 인용하지 않은 판정은 절제할 것이 없어 건너뛴다. 인용문이 노트 전체였던
경우에는 필요성 쪽 입력이 비므로 **호출하지 않고** "근거를 빼면 남는 노트가 없다"로
기록한다 — 판정이 뒤집힐 수밖에 없어 물어볼 것이 없다.

이 실행은 측정이지 조정이 아니다. 여기서 나온 값으로 프롬프트나 임계값을 고치지 않는다.
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
    require_api_key,
)
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.evaluation.relation_scoring import parse_output
from bio_relation_workflow.preprocessing import load_corpus
from bio_relation_workflow.providers.litellm_provider import LiteLLMProvider
from bio_relation_workflow.schemas import (
    EvaluationResult,
    ModelObservation,
    RelationVerdict,
)
from bio_relation_workflow.workflow import run_cases
from bio_relation_workflow.xai import ablate_notes, score_ablation

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
MODES = ("sufficiency", "comprehensiveness")


def _load_observations(path: Path) -> list[ModelObservation]:
    if not path.is_file():
        return []
    return [
        ModelObservation.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _append(path: Path, observation: ModelObservation) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(observation.model_dump_json() + "\n")
        handle.flush()


def _load_results(base: Path, splits: list[str]) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for split in splits:
        path = base / split / "results.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"먼저 {split}을 실행하세요: {path}")
        results.extend(
            EvaluationResult.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="근거 절제 재질의")
    parser.add_argument("--config", default="configs/relation-nim-ablation.yaml")
    parser.add_argument("--source-config", default="configs/relation-nim.yaml")
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--split",
        action="append",
        choices=["development", "validation", "sealed_test"],
        help="여러 번 줄 수 있다. 기본은 development + validation.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("실제 API 호출에는 --live가 필요합니다")

    splits = args.split or ["development", "validation"]
    env_path = load_project_env(PROJECT_ROOT)
    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    source = load_settings(project_path(PROJECT_ROOT, args.source_config))
    if settings.provider.model != source.provider.model:
        raise ValueError(
            "절제 재질의는 본 판정과 같은 모델이어야 합니다: "
            f"{settings.provider.model} != {source.provider.model}"
        )
    if settings.paths.prompt != source.paths.prompt:
        raise ValueError("절제 재질의는 본 판정과 같은 프롬프트를 써야 합니다")
    require_api_key(settings.provider.api_key_env, env_path=env_path)

    results = _load_results(
        project_path(PROJECT_ROOT, source.paths.output), splits
    )
    cases = {
        case.sample_id: case
        for case in load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    }
    corpus = load_corpus(project_path(PROJECT_ROOT, settings.paths.note_corpus))
    notes_by_id = {note.note_id: note for note in corpus.notes}

    # 절제 대상 — 근거를 실제로 인용한 판정만.
    targets = [
        result
        for result in results
        if result.output and result.output.evidence
    ]
    if args.limit is not None:
        targets = targets[: args.limit]
    if not targets:
        parser.error("절제할 대상이 없습니다")

    output_dir = project_path(PROJECT_ROOT, settings.paths.output)
    observations_path = output_dir / "observations.jsonl"
    existing = _load_observations(observations_path)
    if existing and not args.resume:
        parser.error("기존 실행이 있습니다. 이어서 실행하려면 --resume을 사용하세요")
    done = {observation.sample_id for observation in existing}

    # 호출이 필요한 (건, 모드) 목록. 입력이 비는 모드는 호출하지 않되, 어느 모드가
    # 비었는지를 구분해 남긴다 — 두 경우의 뜻이 정반대다.
    pending: list[tuple[EvaluationResult, str, list]] = []
    empty: dict[str, set[str]] = {mode: set() for mode in MODES}
    for result in targets:
        case = cases[result.sample_id]
        notes = [notes_by_id[note_id] for note_id in case.note_ids]
        for mode in MODES:
            ablated = ablate_notes(notes, result.output, mode=mode)
            if not ablated:
                empty[mode].add(result.sample_id)
                continue
            key = f"{result.sample_id}#{mode}"
            if key not in done:
                pending.append((result, mode, ablated))

    if len(existing) + len(pending) > settings.limits.max_requests:
        parser.error(f"설정된 상한은 {settings.limits.max_requests}건입니다")

    prompt_path = project_path(PROJECT_ROOT, settings.paths.prompt)
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
        for index, (result, mode, ablated) in enumerate(pending, start=1):
            case = cases[result.sample_id]
            # 절제로 사라진 노트가 있으므로 케이스의 note_ids도 함께 줄인다.
            probe = case.model_copy(
                update={
                    "sample_id": f"{result.sample_id}#{mode}",
                    "note_ids": [note.note_id for note in ablated],
                }
            )
            observation = run_cases(
                cases=[probe],
                notes=ablated,
                prompt_path=prompt_path,
                provider=provider,
                max_notes=settings.notes.max_notes_per_case,
                max_chars=settings.notes.max_note_chars,
            )[0]
            _append(observations_path, observation)
            print(f"[{index}/{len(pending)}] {probe.sample_id}")

    # --- 채점 ---
    by_key: dict[str, RelationVerdict | None] = {}
    for observation in _load_observations(observations_path):
        try:
            by_key[observation.sample_id] = parse_output(observation.raw_output)
        except Exception:
            by_key[observation.sample_id] = None

    outcomes = []
    for result in targets:
        sample_id = result.sample_id
        sufficiency = by_key.get(f"{sample_id}#sufficiency")
        comprehensiveness = by_key.get(f"{sample_id}#comprehensiveness")
        note = ""
        # 근거를 빼면 노트가 남지 않는다 — 빈 입력으로는 어떤 판정도 재현될 수 없으므로
        # 필요성은 물어보나 마나다. 참으로 세지 않고 측정 불가로 남긴다.
        vacuous = sample_id in empty["comprehensiveness"]
        if sample_id in empty["sufficiency"]:
            # 인용문에 대응하는 문장을 못 찾았다는 뜻이다. 충분성을 물을 수 없으므로
            # 조용히 넘기지 않고 그대로 남긴다.
            sufficiency = None
            note = "인용문에 대응하는 노트 문장을 찾지 못해 충분성 재질의 불가"
        outcome = score_ablation(
            cases[sample_id],
            result.output,
            sufficiency=sufficiency,
            comprehensiveness=comprehensiveness,
            necessity_vacuous=vacuous,
        )
        if note:
            outcome.note = note
        outcomes.append(outcome)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ablation.jsonl").write_text(
        "".join(outcome.model_dump_json() + "\n" for outcome in outcomes),
        encoding="utf-8",
    )
    print(f"\n{output_dir / 'ablation.jsonl'}: {len(outcomes)}건")
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.faithfulness] = counts.get(outcome.faithfulness, 0) + 1
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
