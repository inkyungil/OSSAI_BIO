"""노트 문형에서 정답 라벨을 유도하는 규칙.

코퍼스의 노트는 6개 문형으로 생성된 합성 데이터다. 문형마다 관계를 진술하는지가
정해져 있으므로 판정을 규칙으로 옮길 수 있다. 사람이 100건을 따로 판단하는 대신
규칙을 확인하는 방식이라 정답의 근거가 감사 가능하다.

판정 기준은 **노트가 진술하는가**이지 의학적 사실인가가 아니다. 원본 저장소의 PDF
질의응답이 "문서에서 답을 찾는" 것과 같은 규율이다. 세상 지식으로 채우면 근거 인용을
평가할 수 없다.

문형과 진술 내용:

COMORBID   환자는 [D]와(과) [D] 병력이 있으며 [Rx]을(를) 복용 중이다
           → 관계 진술 없음. 병존만 적었고 어느 질병을 위한 약인지 말하지 않는다.
IMPROVED   [Rx] 복용 이후 [Sx]이(가) 호전되었으나 [D] 관리가 필요하다
           → 관계 진술 없음. 약물이 호전시킨 것은 증상이고 D는 여전히 관리 대상이다.
PRESENTED  [Sx]을(를) 주소로 내원… [D] 의심 소견을 보였다   → D–Sx has_symptom
COMPLAINS  [D] 환자가 [Sx]와(과) [Sx]을(를) 호소하여…       → D–Sx has_symptom
CONSIDER   추가로 [Rx] 처방을 고려한다   → 확립된 관계 아님. 고려일 뿐이다.
HEDGE      또한 [D] 가능성도 배제할 수 없다   → 질병 자체가 미확정이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..schemas import ClinicalNote

Pattern = Literal[
    "COMORBID",
    "IMPROVED",
    "PRESENTED",
    "COMPLAINS",
    "CONSIDER",
    "HEDGE",
    "UNKNOWN",
]

# 진단 근거로 인정하는 문형과, 관계 진술이 없다고 보는 문형
SYMPTOM_STATING: frozenset[Pattern] = frozenset({"PRESENTED", "COMPLAINS"})
NO_RELATION_STATING: frozenset[Pattern] = frozenset({"COMORBID", "IMPROVED"})

_RULES: tuple[tuple[Pattern, re.Pattern[str]], ...] = (
    ("COMORBID", re.compile(r"병력이 있으며.*복용 중이다")),
    ("IMPROVED", re.compile(r"복용 이후.*호전되었으나.*관리가 필요하다")),
    ("PRESENTED", re.compile(r"주소로 내원하였고.*의심 소견을 보였다")),
    ("COMPLAINS", re.compile(r"환자가.*호소하여.*시행하였다")),
    ("CONSIDER", re.compile(r"처방을 고려한다")),
    ("HEDGE", re.compile(r"가능성도 배제할 수 없다")),
)


def classify_sentence(sentence: str) -> Pattern:
    for name, pattern in _RULES:
        if pattern.search(sentence):
            return name
    return "UNKNOWN"


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=다)\.\s*", text) if part.strip()]


@dataclass(frozen=True)
class NoteEvidenceKind:
    """한 노트가 특정 개체쌍에 대해 제공하는 근거의 종류."""

    note_id: str
    kind: Literal["states_symptom", "considers_drug", "hedged", "cooccurrence_only"]
    pattern: Pattern


def evidence_kind_for_pair(
    note: ClinicalNote,
    *,
    disease: str,
    partner: str,
    partner_label: str,
) -> NoteEvidenceKind:
    sentences = split_sentences(note.text)
    classified = [(s, classify_sentence(s)) for s in sentences]

    hedged_only = any(
        disease in sentence and pattern == "HEDGE" for sentence, pattern in classified
    ) and not any(
        disease in sentence and pattern != "HEDGE" for sentence, pattern in classified
    )
    if hedged_only:
        return NoteEvidenceKind(note.note_id, "hedged", "HEDGE")

    if partner_label == "증상":
        for sentence, pattern in classified:
            if (
                pattern in SYMPTOM_STATING
                and disease in sentence
                and partner in sentence
            ):
                return NoteEvidenceKind(note.note_id, "states_symptom", pattern)
    else:
        for sentence, pattern in classified:
            if pattern == "CONSIDER" and partner in sentence:
                return NoteEvidenceKind(note.note_id, "considers_drug", pattern)

    first = classified[0][1] if classified else "UNKNOWN"
    return NoteEvidenceKind(note.note_id, "cooccurrence_only", first)


@dataclass(frozen=True)
class DraftLabel:
    relation: Literal["treats", "has_symptom", "no_relation"]
    note_ids: list[str]
    abstained: bool
    rule: str
    evidence_kinds: list[NoteEvidenceKind]


def draft_label(
    notes: list[ClinicalNote],
    *,
    disease: str,
    partner: str,
    partner_label: str,
) -> DraftLabel:
    """개체쌍 하나의 정답 초안을 유도한다.

    우선순위
      1. 증상 관계를 진술한 노트가 있으면 has_symptom (그 노트가 근거)
      2. 약물 처방을 고려만 한 노트가 있으면 보류 — 확립된 관계도, 무관계도 아니다
      3. 노트가 전부 hedge뿐이면 보류 — 질병 자체가 미확정
      4. 나머지는 no_relation — 함께 등장했을 뿐 관계를 진술하지 않았다
    """
    kinds = [
        evidence_kind_for_pair(
            note, disease=disease, partner=partner, partner_label=partner_label
        )
        for note in notes
    ]

    stating = [k for k in kinds if k.kind == "states_symptom"]
    if stating:
        return DraftLabel(
            relation="has_symptom",
            note_ids=sorted(k.note_id for k in stating),
            abstained=False,
            rule="증상 관계를 진술한 노트가 있음",
            evidence_kinds=kinds,
        )

    considering = [k for k in kinds if k.kind == "considers_drug"]
    if considering:
        return DraftLabel(
            relation="no_relation",
            note_ids=[],
            abstained=True,
            rule="약물 처방을 고려만 함 — 확립된 치료 관계로 볼 수 없음",
            evidence_kinds=kinds,
        )

    if kinds and all(k.kind == "hedged" for k in kinds):
        return DraftLabel(
            relation="no_relation",
            note_ids=[],
            abstained=True,
            rule="질병이 hedge 문장에만 등장 — 판정 불가",
            evidence_kinds=kinds,
        )

    return DraftLabel(
        relation="no_relation",
        note_ids=[],
        abstained=False,
        rule="함께 등장했을 뿐 관계를 진술하지 않음",
        evidence_kinds=kinds,
    )
