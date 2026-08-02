"""프롬프트 주입 탐지 결과와 라우팅 결정의 계약 (`day5 p51-52`).

탐지 규칙 자체는 `evaluation/injection.py`에 있다. 여기에는 파일로 저장되고 함수
사이를 오가는 값만 둔다.
"""

from __future__ import annotations

from typing import Literal

from .notes import Contract

InjectionKind = Literal[
    "OVERRIDE_INSTRUCTION",
    "SYSTEM_PROMPT_EXFILTRATION",
    "FABRICATE_EVIDENCE",
    "ROLE_SWITCH",
]

# day5 p51 validator 체인의 종착점. `APPROVED`가 없는 것이 이 목록의 요점이다 —
# 어떤 경로로도 자동확정에 도달하지 않는다 (day6 p35).
RoutingDecision = Literal[
    "REJECT_SCHEMA",
    "REJECT_GROUNDING",
    "DRAFT_REVIEW_INJECTION",
    "DRAFT_REVIEW_ABSTAIN",
    "DRAFT_REVIEW",
]


class InjectionSignal(Contract):
    note_id: str
    kind: InjectionKind
    matched: str


class InjectionReport(Contract):
    """한 케이스의 주입 탐지·저항 결과.

    탐지(`signals`)와 저항(`complied`가 비어 있음)은 다른 것이다. 모델이 지시를
    물리쳤어도 그 노트에 주입이 있었다는 사실은 사람에게 알려야 한다.
    """

    signals: list[InjectionSignal] = []
    complied: list[InjectionKind] = []

    @property
    def detected(self) -> bool:
        return bool(self.signals)

    @property
    def resisted(self) -> bool:
        return not self.complied
