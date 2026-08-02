"""결정적 정량 점수를 로컬 DeepEval TestRun으로 저장한다.

출처: src/verifiable_ai_workflow/evaluation/deepeval_runner.py — ResultMetric은 수정 없이
복사. 차이는 metric_specs를 관계 판정 지표로 바꾼 것뿐이다.

임계값 규율도 그대로다. threshold=0인 지표는 원인 분석용이고, 실제 pass/fail은 필수
지표와 같은 기준으로 계산된 task_success가 결정한다.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval import evaluate
from deepeval.evaluate import AsyncConfig, CacheConfig, DisplayConfig
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

from ..schemas import EvaluationResult, RelationCase

METRIC_SPECS: tuple[tuple[str, str, float], ...] = (
    ("json_object_only", "JSON 단독 반환 (진단)", 0.0),
    ("schema_validity", "JSON 구조", 1.0),
    ("relation_correct", "관계 정답", 1.0),
    ("abstention_correct", "판정 보류", 1.0),
    ("note_id_valid", "인용 노트 범위", 1.0),
    ("evidence_note_hit", "근거 노트 적중", 1.0),
    ("quote_grounding", "인용문 노트 원문 일치", 0.0),
    # 게이트 자체는 필수다. 평균은 진단용이고 통과 여부가 라우팅을 정한다.
    ("quote_gate", "인용 근거 게이트", 1.0),
    ("reference_agreement", "참조표 일치 (진단)", 0.0),
    ("confidence", "모델 신뢰도 (진단)", 0.0),
    ("task_success", "전체 성공", 1.0),
)


class ResultMetric(BaseMetric):
    async_mode = False

    def __init__(
        self,
        score_name: str,
        display_name: str,
        values: dict[str, float],
        reasons: dict[str, str],
        *,
        threshold: float,
    ) -> None:
        self.score_name = score_name
        self.display_name = display_name
        self.values = values
        self.reasons = reasons
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        del args, kwargs
        self.score = self.values[test_case.name]
        self.reason = self.reasons[test_case.name]
        self.success = self.score >= self.threshold
        self.error = None
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self) -> str:
        return self.display_name


def deterministic_metrics(results: list[EvaluationResult]) -> list[BaseMetric]:
    return [
        ResultMetric(
            score_name,
            display_name,
            {result.sample_id: result.scores[score_name] for result in results},
            {result.sample_id: result.reasons[score_name] for result in results},
            threshold=threshold,
        )
        for score_name, display_name, threshold in METRIC_SPECS
    ]


def _question(case: RelationCase) -> str:
    return (
        f"{case.disease} — {case.partner}({case.partner_label}) 사이에 "
        f"노트가 진술하는 관계는 무엇인가?"
    )


def evaluate_results(
    results: list[EvaluationResult],
    cases: list[RelationCase],
    results_folder: str | Path,
) -> None:
    case_by_id = {case.sample_id: case for case in cases}
    test_cases = [
        LLMTestCase(
            name=result.sample_id,
            input=_question(case_by_id[result.sample_id]),
            actual_output=(
                result.output.model_dump_json() if result.output else str(result.raw_output)
            ),
            expected_output=case_by_id[result.sample_id].expected.model_dump_json(),
        )
        for result in results
    ]
    evaluate(
        test_cases=test_cases,
        metrics=deterministic_metrics(results),
        async_config=AsyncConfig(run_async=False),
        cache_config=CacheConfig(write_cache=False, use_cache=False),
        display_config=DisplayConfig(
            show_indicator=False,
            print_results=False,
            inspect_after_run=False,
            results_folder=str(results_folder),
        ),
    )
