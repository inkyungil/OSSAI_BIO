"""검토 화면이 자립인지 (#21).

"외부 요청 0"은 취향이 아니다. 임상 노트에서 나온 화면이 바깥으로 요청을 보내면
그 자체가 데이터 유출 경로다(`day5 p48`). 눈으로 보는 대신 테스트로 지킨다.

생성물이 없으면 건너뛴다. `reports/`는 저장소에 없다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = PROJECT_ROOT / "templates" / "dashboard.html"
BUILT = PROJECT_ROOT / "reports" / "relation-nim" / "dashboard.html"

# 바깥으로 나가는 통로. 하나라도 있으면 자립이 아니다.
OUTBOUND = (
    r"https?://",
    r"//cdn\.",
    r"\bfetch\s*\(",
    r"XMLHttpRequest",
    r"WebSocket",
    r"\bimport\s*\(",
    r"<link\b",
    r"<img\b",
    r"<iframe\b",
    r"<script[^>]+\bsrc=",
    r"@import",
    r"url\(\s*['\"]?https?:",
)


def _read(path: Path) -> str:
    if not path.is_file():
        pytest.skip(f"먼저 build_dashboard.py를 실행하세요: {path}")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [TEMPLATE, BUILT])
def test_no_outbound_request_of_any_kind(path):
    text = _read(path)
    found = [pattern for pattern in OUTBOUND if re.search(pattern, text)]
    assert not found, f"{path.name}에 외부 요청 통로가 있습니다: {found}"


def test_data_is_embedded_not_loaded():
    """더블클릭 실행 조건 — file:// 에서 fetch는 막히므로 데이터가 박혀 있어야 한다."""
    text = _read(BUILT)
    match = re.search(
        r'<script id="payload" type="application/json">(.*?)</script>',
        text,
        re.DOTALL,
    )
    assert match, "인라인 payload가 없습니다"
    payload = json.loads(match.group(1).replace("<\\/", "</"))
    assert payload["cases"], "케이스가 비어 있습니다"
    assert payload["splits"], "split 요약이 비어 있습니다"


def test_evidence_kind_badge_is_present_for_every_split():
    """day5 p53 — 저장 응답 결과와 실제 호출 결과를 화면에서 구분해야 한다."""
    payload = json.loads(
        re.search(
            r'<script id="payload" type="application/json">(.*?)</script>',
            _read(BUILT),
            re.DOTALL,
        )
        .group(1)
        .replace("<\\/", "</")
    )
    for split in payload["splits"]:
        assert split["evidence_kind"] in {"test_only", "live_quality"}


def test_no_routing_bucket_is_an_approval():
    payload = json.loads(
        re.search(
            r'<script id="payload" type="application/json">(.*?)</script>',
            _read(BUILT),
            re.DOTALL,
        )
        .group(1)
        .replace("<\\/", "</")
    )
    for split in payload["splits"]:
        assert all("APPROVED" not in key for key in split["routing_counts"])


def test_both_thresholds_are_exposed_together():
    """day3 p40 — 두 임계값은 한 화면에 있어야 한다."""
    text = _read(TEMPLATE)
    assert 'id="th-mc"' in text and 'id="th-cf"' in text


def test_screen_recomputation_is_self_checked():
    """화면이 파이썬과 다른 숫자를 보이면 배너로 드러나야 한다."""
    text = _read(TEMPLATE)
    assert "function selfCheck" in text
    assert "selfcheck" in text
