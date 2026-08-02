"""검토 화면을 자립 HTML 하나로 만든다 (#21).

조건 둘.

    더블클릭 실행 — 서버 없이 파일을 열면 그대로 돈다
    외부 요청 0  — CDN·폰트·이미지 어느 것도 바깥에서 받지 않는다

두 번째는 취향이 아니다. 임상 노트에서 나온 화면이 바깥으로 요청을 보내면 그 자체가
데이터 유출 경로다(`day5 p48`). 데이터는 전부 HTML 안에 JSON으로 박는다.

화면이 반드시 보여야 하는 것
- `test_only` / `live_quality` 배지 — 사전계산 결과와 실제 호출 결과를 화면에서 구분
  하지 않으면 `day5 p53`의 규율이 화면 단계에서 깨진다
- 두 임계값을 **한 화면에서** 움직이기 (`day3 p40`)
- 근거 검증 · 절제 결과 · 참조표 불일치를 근거 패널에 함께 (`day6 p18`)
- 사람 확인 큐 — 자동확정이 없다는 것을 화면으로도 보이기 (`day6 p35`)
"""

from __future__ import annotations

import argparse
import json

import _bootstrap
from bio_relation_workflow.config import load_settings, project_path
from bio_relation_workflow.data import load_cases
from bio_relation_workflow.evaluation import evaluate_operating_point
from bio_relation_workflow.evaluation.text_metrics import best_quote_similarity
from bio_relation_workflow.preprocessing import load_corpus
from bio_relation_workflow.schemas import EvaluationResult

PROJECT_ROOT = _bootstrap.PROJECT_ROOT
SPLITS = ("development", "validation", "sealed_test")
COOCCUR_VALUES = (1, 2, 3)
CONFIDENCE_VALUES = (0.0, 0.9, 0.95, 1.0, 1.0001)

# 템플릿을 파이썬 문자열이 아니라 파일로 둔다. HTML·CSS·JS가 파이썬 린터의 줄 길이
# 규칙에 걸리는 것을 피하고, 화면을 고칠 때 파이썬을 건드리지 않게 하려는 것이다.
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "dashboard.html"


def main() -> int:
    parser = argparse.ArgumentParser(description="자립 검토 화면 생성")
    parser.add_argument("--config", default="configs/relation-nim.yaml")
    parser.add_argument("--ablation-config", default="configs/relation-nim-ablation.yaml")
    parser.add_argument("--output", default="reports/relation-nim/dashboard.html")
    args = parser.parse_args()

    settings = load_settings(project_path(PROJECT_ROOT, args.config))
    base = project_path(PROJECT_ROOT, settings.paths.output)
    corpus = load_corpus(project_path(PROJECT_ROOT, settings.paths.note_corpus))
    note_texts = {note.note_id: note.text for note in corpus.notes}
    case_by_id = {
        case.sample_id: case
        for case in load_cases(project_path(PROJECT_ROOT, settings.paths.cases))
    }

    ablation_by_id: dict[str, dict] = {}
    ablation_summary = None
    ablation_settings = load_settings(project_path(PROJECT_ROOT, args.ablation_config))
    ablation_dir = project_path(PROJECT_ROOT, ablation_settings.paths.output)
    ablation_path = ablation_dir / "ablation.jsonl"
    if ablation_path.is_file():
        for line in ablation_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                ablation_by_id[row["sample_id"]] = row
    summary_path = ablation_dir / "ablation-summary.json"
    if summary_path.is_file():
        ablation_summary = json.loads(summary_path.read_text(encoding="utf-8"))

    splits_payload = []
    cases_payload = []
    grid_payload = []
    for split in SPLITS:
        results_path = base / split / "results.jsonl"
        if not results_path.is_file():
            continue
        results = [
            EvaluationResult.model_validate_json(line)
            for line in results_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        summary = json.loads((base / split / "summary.json").read_text(encoding="utf-8"))
        splits_payload.append(
            {
                "split": split,
                "record_count": summary["record_count"],
                "task_success": summary["score_averages"]["task_success"],
                "schema_validity": summary["score_averages"]["schema_validity"],
                "ppv": summary["asserted_relation"]["ppv"],
                "recall": summary["asserted_relation"]["recall"],
                "model_abstained": summary["abstention"]["model_abstained"],
                "gold_abstained": summary["abstention"]["gold_abstained"],
                "routing_counts": summary["routing_counts"],
                "hallucinations": summary["hallucinations"],
                "evidence_kind": summary["evidence_kind"],
            }
        )

        cases = [case_by_id[result.sample_id] for result in results]
        for cut in COOCCUR_VALUES:
            for threshold in CONFIDENCE_VALUES:
                cell = evaluate_operating_point(
                    cases, results, min_cooccur=cut, min_confidence=threshold
                )
                cell["split"] = split
                grid_payload.append(cell)

        for result in results:
            case = case_by_id[result.sample_id]
            verdict = result.output
            ablation = ablation_by_id.get(result.sample_id)
            cases_payload.append(
                {
                    "sample_id": case.sample_id,
                    "split": case.split,
                    "disease": case.disease,
                    "partner": case.partner,
                    "partner_label": case.partner_label,
                    "support": case.support,
                    "status": result.status,
                    "routing": result.routing,
                    "relation": verdict.relation if verdict else None,
                    "abstained": bool(verdict and verdict.abstained),
                    "abstention_reason": verdict.abstention_reason if verdict else None,
                    "confidence": verdict.confidence if verdict else None,
                    "has_output": verdict is not None,
                    "gold_relation": case.expected.relation,
                    "gold_abstained": case.expected.abstained,
                    "in_reference": case.in_reference,
                    "reference_error": case.reference_error,
                    "evidence": [
                        {
                            "quote": item.quote,
                            "note_id": item.note_id,
                            # 인용마다 따로 잰다. summary의 quote_grounding은 케이스
                            # 평균이라 인용이 둘 이상이면 개별 인용의 값이 아니다.
                            # 채점기와 같은 함수를 써서 두 숫자가 갈리지 않게 한다.
                            "similarity": round(
                                best_quote_similarity(
                                    item.quote, note_texts.get(item.note_id, "")
                                ),
                                4,
                            ),
                        }
                        for item in (verdict.evidence if verdict else [])
                    ],
                    "injection_signals": sorted(
                        {s.kind for s in result.injection.signals}
                        if result.injection
                        else set()
                    ),
                    "injection_complied": (
                        result.injection.complied if result.injection else []
                    ),
                    "ablation": (
                        {
                            "faithfulness": ablation["faithfulness"],
                            "note": ablation.get("note", ""),
                        }
                        if ablation
                        else None
                    ),
                    "notes": [
                        {"note_id": note_id, "text": note_texts[note_id]}
                        for note_id in case.note_ids
                    ],
                }
            )

    if not splits_payload:
        parser.error("표시할 결과가 없습니다")

    chosen_path = base / "operating-point" / "operating-point.json"
    operating_point = {"min_cooccur": 1, "min_confidence": 0.95}
    if chosen_path.is_file():
        chosen = json.loads(chosen_path.read_text(encoding="utf-8"))["chosen"]
        operating_point = {
            "min_cooccur": chosen["min_cooccur"],
            "min_confidence": chosen["min_confidence"],
        }

    payload = {
        "meta": {
            "model": settings.provider.model,
            "generalization": "SINGLE — 단일 분할·단일 시드, 가설 생성 수준",
        },
        "splits": splits_payload,
        "cases": cases_payload,
        "grid": grid_payload,
        "confidence_values": list(CONFIDENCE_VALUES),
        "operating_point": operating_point,
        "ablation_summary": ablation_summary,
    }
    # </script>가 데이터 안에 있으면 문서가 거기서 끊긴다.
    encoded = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE_PATH.read_text(encoding="utf-8").replace("__PAYLOAD__", encoded)

    target = project_path(PROJECT_ROOT, args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    print(f"{target}: {len(html) / 1024:.0f} KB · 케이스 {len(cases_payload)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
