"""문자열 대조에 쓰는 도메인 무관 함수.

출처: src/verifiable_ai_workflow/evaluation/scoring.py:18-107 — 수정 없이 발췌.
PDF에 묶인 부분이 없는 순수 함수라 관계 판정에 그대로 쓴다. 원본 동작이 바뀌면 안 되므로
tests/test_text_metrics.py가 원본과 같은 입력에 같은 값을 내는지 지킨다.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", normalized)


def numbers(text: str) -> list[str]:
    return re.findall(r"-?\d+(?:\.\d+)?", unicodedata.normalize("NFKC", text))


def similarity(actual: str, expected: str) -> float:
    return SequenceMatcher(None, normalize(actual), normalize(expected)).ratio()


def edit_similarity(actual: str, expected: str) -> float:
    """DocVQA ANLS 계산에 쓰는 정규화 Levenshtein similarity."""
    left = normalize(actual)
    right = normalize(expected)
    if not left or not right:
        return float(left == right)

    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + int(left_character != right_character),
                )
            )
        previous = current
    return 1 - previous[-1] / max(len(left), len(right))


def tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.findall(r"-?\d+(?:\.\d+)?|[a-z]+|[가-힣]+", normalized)


def token_f1(actual: str, expected: str) -> float:
    actual_counts: dict[str, int] = {}
    expected_counts: dict[str, int] = {}
    for token in tokens(actual):
        actual_counts[token] = actual_counts.get(token, 0) + 1
    for token in tokens(expected):
        expected_counts[token] = expected_counts.get(token, 0) + 1
    if not actual_counts or not expected_counts:
        return float(actual_counts == expected_counts)
    overlap = sum(
        min(count, expected_counts.get(token, 0))
        for token, count in actual_counts.items()
    )
    precision = overlap / sum(actual_counts.values())
    recall = overlap / sum(expected_counts.values())
    return (
        2 * precision * recall / (precision + recall) if precision + recall else 0.0
    )


def best_quote_similarity(quote: str, source_text: str) -> float:
    """인용문이 원문 어딘가와 얼마나 일치하는지. 1.0이면 그대로 포함된다."""
    needle = normalize(quote)
    haystack = normalize(source_text)
    if not needle or not haystack:
        return 0.0
    if needle in haystack:
        return 1.0

    window_size = min(len(haystack), max(len(needle), round(len(needle) * 1.4)))
    step = max(1, len(needle) // 4)
    return max(
        SequenceMatcher(None, needle, haystack[start : start + window_size]).ratio()
        for start in range(0, max(1, len(haystack) - window_size + 1), step)
    )


def contains_fact(text: str, fact: str) -> bool:
    """숫자가 있으면 숫자 일치로, 없으면 정규화 문자열 포함으로 본다."""
    fact_numbers = numbers(fact)
    if fact_numbers:
        return all(number in numbers(text) for number in fact_numbers)
    normalized_fact = normalize(fact)
    return bool(normalized_fact and normalized_fact in normalize(text))
