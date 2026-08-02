"""노트 코퍼스에서 관계 후보 개체쌍을 다시 만들고 층화·split을 배정한다.

원본 프로토타입은 동시출현 빈도(min_cooccur)만으로 후보를 걸렀고 탈락한 쌍은 저장하지
않았다. 노트에서 다시 계산하면 탈락 후보까지 복원되며, 그것이 필터의 성능을 재는 재료다.

허브 개체는 day3 p11의 "흔한 개체 착시"를 겨냥한 층이다. 발열·인슐린처럼 연결이 많은
개체는 아무 질병하고나 붙어 후보가 되므로 따로 뽑아 평가한다.
"""

from __future__ import annotations

import itertools
import random
from collections import Counter, defaultdict

from ..schemas import CandidatePair, CandidateSet, NoteCorpus

# 원본 DATA.settings.relation_rules와 같다. (질병 유형, 상대 유형) → 후보 관계
RELATION_RULES: dict[tuple[str, str], str] = {
    ("질병", "약물"): "treats",
    ("질병", "증상"): "has_symptom",
}

SPLIT_RATIO: tuple[tuple[str, float], ...] = (
    ("development", 0.20),
    ("validation", 0.40),
    ("sealed_test", 0.40),
)


def _pair_key(
    left: str,
    right: str,
    labels: dict[str, str],
) -> tuple[str, str, str, str] | None:
    """(질병, 상대, 상대유형, 후보관계). 규칙에 없는 조합이면 None."""
    for disease, partner in ((left, right), (right, left)):
        relation = RELATION_RULES.get((labels[disease], labels[partner]))
        if relation:
            return disease, partner, labels[partner], relation
    return None


def count_cooccurrence(
    corpus: NoteCorpus,
) -> dict[tuple[str, str, str, str], list[str]]:
    """규칙을 통과한 개체쌍별 등장 노트 목록.

    주입 평가용으로 직접 쓴 노트는 제외한다. 후보 생성 규칙이 만든 것이 아니므로
    원본 엣지 재현 회귀 검사를 오염시키면 안 된다.
    """
    labels = {entity.entity_id: entity.label for entity in corpus.entities}
    injected = set(corpus.provenance.get("injection_notes", []))
    occurrences: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    for note in corpus.notes:
        if note.note_id in injected:
            continue
        for left, right in itertools.combinations(note.entities, 2):
            key = _pair_key(left, right, labels)
            if key:
                occurrences[key].append(note.note_id)
    return {key: sorted(set(value)) for key, value in occurrences.items()}


def hub_entities(
    occurrences: dict[tuple[str, str, str, str], list[str]],
    *,
    top_ratio: float = 0.2,
) -> list[str]:
    """연결 수 상위 상대 개체(약물·증상). 상위 top_ratio 비율을 허브로 본다.

    질병은 모든 관계의 한쪽 끝이라 구조적으로 연결 수가 높다. 세면 질병만 상위를
    차지해 층의 목적을 놓친다. day3 p11이 말한 착시는 여러 질병에 두루 붙는 상대
    개체 쪽이다 — 항응고제 와파린이 협심증·천식과도 후보가 되는 식이다.
    """
    degree = Counter(partner for _, partner, _, _ in occurrences)
    if not degree:
        return []
    cutoff = max(1, round(len(degree) * top_ratio))
    ranked = sorted(degree.items(), key=lambda item: (-item[1], item[0]))
    threshold = ranked[cutoff - 1][1]
    return sorted(name for name, count in degree.items() if count >= threshold)


def _stratum(*, support: int, min_cooccur: int, is_hub: bool, in_reference: bool) -> str:
    if support >= min_cooccur:
        if in_reference:
            return "reference"
        return "kept_hub" if is_hub else "kept"
    return "dropped_hub" if is_hub else "dropped"


def build_candidates(
    corpus: NoteCorpus,
    *,
    reference_edges: dict[tuple[str, str], dict[str, bool]] | None = None,
    min_cooccur: int = 2,
    hub_top_ratio: float = 0.2,
) -> CandidateSet:
    occurrences = count_cooccurrence(corpus)
    hubs = set(hub_entities(occurrences, top_ratio=hub_top_ratio))
    references = reference_edges or {}

    candidates: list[CandidatePair] = []
    ordered = sorted(occurrences.items(), key=lambda item: (-len(item[1]), item[0]))
    for index, ((disease, partner, partner_label, relation), note_ids) in enumerate(
        ordered, start=1
    ):
        support = len(note_ids)
        marks = references.get((disease, partner)) or references.get((partner, disease))
        in_reference = marks["in_reference"] if marks else None
        candidates.append(
            CandidatePair(
                pair_id=f"C{index:03d}",
                disease=disease,
                partner=partner,
                partner_label=partner_label,
                candidate_relation=relation,
                support=support,
                note_ids=note_ids,
                in_reference=in_reference,
                reference_error=marks["reference_error"] if marks else None,
                stratum=_stratum(
                    support=support,
                    min_cooccur=min_cooccur,
                    is_hub=partner in hubs,
                    in_reference=bool(in_reference),
                ),
            )
        )

    return CandidateSet(
        corpus_sha256=corpus.source_sha256,
        min_cooccur=min_cooccur,
        relation_rules={f"{k[0]}-{k[1]}": v for k, v in RELATION_RULES.items()},
        hub_entities=sorted(hubs),
        candidates=candidates,
        provenance={
            "notes": len(corpus.notes),
            "entities": len(corpus.entities),
            "candidate_pairs": len(candidates),
            "hub_top_ratio": hub_top_ratio,
        },
    )


def assign_splits(
    candidate_set: CandidateSet,
    *,
    target_total: int,
    keep_all_strata: tuple[str, ...] = ("reference", "kept_hub", "kept"),
    seed: int,
) -> CandidateSet:
    """층을 유지하며 라벨링 대상을 고르고 split을 배정한다.

    keep_all_strata에 든 층은 전수 선정한다. 표본이 아니므로 샘플링 편향이 없다.
    나머지 층에서 target_total을 채울 만큼만 층 비율에 맞춰 뽑는다.
    """
    rng = random.Random(seed)
    by_stratum: dict[str, list[CandidatePair]] = defaultdict(list)
    for candidate in candidate_set.candidates:
        by_stratum[candidate.stratum].append(candidate)

    selected: list[CandidatePair] = []
    for stratum in keep_all_strata:
        selected.extend(by_stratum.get(stratum, []))

    remaining_strata = [s for s in sorted(by_stratum) if s not in keep_all_strata]
    quota = target_total - len(selected)
    if quota < 0:
        raise ValueError(
            f"전수 선정 층이 {len(selected)}건이라 목표 {target_total}건을 넘습니다"
        )
    pool_total = sum(len(by_stratum[s]) for s in remaining_strata)
    taken = 0
    for position, stratum in enumerate(remaining_strata, start=1):
        pool = sorted(by_stratum[stratum], key=lambda c: c.pair_id)
        if position == len(remaining_strata):
            take = quota - taken
        else:
            take = round(quota * len(pool) / pool_total) if pool_total else 0
        take = min(take, len(pool))
        selected.extend(rng.sample(pool, take))
        taken += take

    for stratum in sorted({candidate.stratum for candidate in selected}):
        members = sorted(
            (c for c in selected if c.stratum == stratum),
            key=lambda c: c.pair_id,
        )
        rng.shuffle(members)
        start = 0
        for position, (split, ratio) in enumerate(SPLIT_RATIO, start=1):
            end = len(members) if position == len(SPLIT_RATIO) else start + round(
                len(members) * ratio
            )
            for candidate in members[start:end]:
                candidate.split = split
            start = end

    candidate_set.provenance["selected"] = len(selected)
    candidate_set.provenance["split_seed"] = seed
    return candidate_set
