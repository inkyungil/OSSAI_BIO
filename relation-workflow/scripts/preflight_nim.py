"""설정한 모델의 가용성과 실제 응답 형식을 호출 전에 확인한다.

원본 `scripts/preflight_nvidia.py`를 따르되 관계 판정에 필요한 두 가지를 더 본다.
- 텍스트 전용 후보들의 가용 여부 (관계 판정은 이미지를 쓰지 않는다)
- --probe로 1건을 실제 호출해 JSON 파싱·지연·token 사용량을 잰다
"""

from __future__ import annotations

import argparse
import json
import urllib.request

import _bootstrap
from bio_relation_workflow.config import (
    load_project_env,
    load_settings,
    project_path,
    require_api_key,
)
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.evaluation import parse_output
from bio_relation_workflow.preprocessing import load_corpus
from bio_relation_workflow.providers.litellm_provider import LiteLLMProvider
from bio_relation_workflow.workflow import build_case_input, build_messages

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
CATALOG_URL = "https://integrate.api.nvidia.com/v1/models"

# 관계 판정은 텍스트만 쓴다. 원본 Week 1의 멀티모달 후보는 여기서 볼 이유가 없다.
TEXT_CANDIDATES = (
    "meta/llama-3.3-70b-instruct",
    "meta/llama-3.1-8b-instruct",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "deepseek-ai/deepseek-v4-flash",
    "qwen/qwen3-next-80b-a3b-instruct",
    "mistralai/mistral-small-24b-instruct",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
)


def fetch_catalog(api_key: str) -> set[str]:
    request = urllib.request.Request(
        CATALOG_URL, headers={"Authorization": f"Bearer {api_key}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        catalog = json.load(response)
    return {item["id"] for item in catalog.get("data", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description="NIM 모델 preflight")
    parser.add_argument("--config", default="configs/relation-nim.yaml")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="케이스 1건을 실제로 호출해 응답 형식·지연을 잰다",
    )
    parser.add_argument(
        "--model",
        help="config 대신 이 모델로 확인한다 (nvidia_nim/ 접두사 생략 가능)",
    )
    args = parser.parse_args()

    env_path = load_project_env(PROJECT_ROOT)
    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    if args.model:
        name = args.model
        settings.provider.model = (
            name if name.startswith("nvidia_nim/") else f"nvidia_nim/{name}"
        )
    api_key = require_api_key(settings.provider.api_key_env, env_path=env_path)
    available = fetch_catalog(api_key)

    configured = settings.provider.model.removeprefix("nvidia_nim/")
    ok = configured in available
    print(f"configured model: {configured}")
    print(f"available now   : {ok}")
    print("텍스트 후보 가용성:")
    for model in TEXT_CANDIDATES:
        mark = "O" if model in available else "-"
        here = " <- 설정됨" if model == configured else ""
        print(f"  [{mark}] {model}{here}")
    if not ok:
        print("\n설정한 모델을 지금 쓸 수 없습니다. 위 목록에서 골라 config를 고치세요.")
        return 1

    if not args.probe:
        print("\n실제 응답 형식까지 보려면 --probe를 붙이세요.")
        return 0

    cases = load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    corpus = load_corpus(project_path(PROJECT_ROOT, settings.paths.note_corpus))
    note_by_id = {note.note_id: note for note in corpus.notes}
    case = next(case for case in cases if case.split == "development")

    provider = LiteLLMProvider(
        model=settings.provider.model,
        api_key_env=settings.provider.api_key_env,
        api_base=settings.provider.api_base,
        structured_output=settings.provider.structured_output,
        max_requests=1,
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
    prompt = project_path(PROJECT_ROOT, settings.paths.prompt).read_text(
        encoding="utf-8"
    )
    messages = build_messages(
        case_input=build_case_input(
            case,
            note_by_id,
            max_notes=settings.notes.max_notes_per_case,
            max_chars=settings.notes.max_note_chars,
        ),
        system_prompt=prompt,
    )

    print(f"\nprobe: {case.sample_id}")
    raw = provider.generate(case.sample_id, messages)
    call = provider.last_call or {}
    limits = settings.limits
    print(f"  latency      : {call.get('latency_ms', 0) / 1000:.1f}s")
    print(f"  input tokens : {call.get('input_tokens')} (상한 {limits.max_input_tokens})")
    print(f"  output tokens: {call.get('output_tokens')} (상한 {limits.max_output_tokens})")
    fenced = isinstance(raw, str) and raw.strip().startswith("```")
    print(f"  code fence   : {fenced}")
    try:
        verdict = parse_output(raw)
    except Exception as exc:
        print(f"  파싱 실패: {type(exc).__name__}: {exc}")
        print(f"  원문: {str(raw)[:400]}")
        return 1
    print(f"  파싱 성공    : relation={verdict.relation} abstained={verdict.abstained}")

    total = len(cases)
    seconds = call.get("latency_ms", 0) / 1000 * total
    print(f"\n전체 {total}건 예상 소요: 약 {seconds / 60:.0f}분 (순차 실행 기준)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
