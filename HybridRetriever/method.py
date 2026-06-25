"""Retrieval scoring helpers for HybridRetriever."""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable


def vector_search(query_vector: Iterable[float], chunk_vectors: dict[str, list[float]]) -> dict[str, float]:
    query = list(query_vector)
    return {chunk_id: _cosine_similarity(query, vector) for chunk_id, vector in chunk_vectors.items()}


def bm25_search(query_text: str, chunks: dict[str, str]) -> dict[str, float]:
    query_terms = _char_tokens(query_text)
    if not query_terms or not chunks:
        return {chunk_id: 0.0 for chunk_id in chunks}

    docs = {chunk_id: _char_tokens(content) for chunk_id, content in chunks.items()}
    doc_count = len(docs)
    avg_len = sum(len(tokens) for tokens in docs.values()) / doc_count if doc_count else 0.0
    doc_freq: Counter[str] = Counter()
    for tokens in docs.values():
        doc_freq.update(set(tokens))

    k1 = 1.5
    b = 0.75
    scores: dict[str, float] = {}
    for chunk_id, tokens in docs.items():
        if not tokens:
            scores[chunk_id] = 0.0
            continue
        term_freq = Counter(tokens)
        score = 0.0
        doc_len = len(tokens)
        for term in query_terms:
            tf = term_freq.get(term, 0)
            if tf == 0:
                continue
            idf = math.log(1 + (doc_count - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            denominator = tf + k1 * (1 - b + b * doc_len / avg_len) if avg_len else tf + k1
            score += idf * (tf * (k1 + 1)) / denominator
        scores[chunk_id] = float(score)
    return scores


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left or not right:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(lvalue * rvalue for lvalue, rvalue in zip(left, right)) / (left_norm * right_norm)


def _char_tokens(text: str) -> list[str]:
    return [char.lower() for char in text if not char.isspace()]
