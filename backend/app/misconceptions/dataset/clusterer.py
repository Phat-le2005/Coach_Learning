from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from typing import Sequence

from app.misconceptions.dataset.schemas import MisconceptionSample


def normalize_question_text(text: str) -> str:
    """Normalize question text by lowercasing, stripping accents, removing punctuation and LaTeX spacing."""
    if not text:
        return ""
    # NFKD decomposition
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = without_accents.lower()
    # Remove punctuation, math delimiters $, \
    cleaned = re.sub(r"[\$\\(){}\[\].,;:!?+\-*\/=<>_\"']", " ", lowered)
    tokens = cleaned.split()
    return " ".join(tokens)


def token_jaccard_similarity(text1: str, text2: str) -> float:
    """Calculate token-level Jaccard similarity between two texts."""
    tokens1 = set(normalize_question_text(text1).split())
    tokens2 = set(normalize_question_text(text2).split())
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union if union > 0 else 0.0


class DisjointSet:
    """Disjoint Set Union (DSU) for transitive cluster merging."""

    def __init__(self, elements: Sequence[str]) -> None:
        self.parent = {e: e for e in elements}

    def find(self, i: str) -> str:
        if self.parent[i] == i:
            return i
        self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i: str, j: str) -> None:
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            # Deterministic merge to smaller string
            if root_i < root_j:
                self.parent[root_j] = root_i
            else:
                self.parent[root_i] = root_j


class QuestionClusterer:
    """Clusters identical and near-duplicate questions to prevent cross-split data leakage.
    
    Any questions sharing token Jaccard similarity >= similarity_threshold are merged
    into the same cluster.
    """

    def __init__(self, similarity_threshold: float = 0.60) -> None:
        self.similarity_threshold = similarity_threshold

    def assign_clusters(
        self, samples: list[MisconceptionSample]
    ) -> list[MisconceptionSample]:
        """Group samples by question similarity and set `cluster_id` on each sample."""
        if not samples:
            return []

        # 1. Map unique normalized question texts
        unique_texts: list[str] = []
        text_to_samples: dict[str, list[MisconceptionSample]] = defaultdict(list)

        for s in samples:
            norm = normalize_question_text(s.question)
            if norm not in text_to_samples:
                unique_texts.append(norm)
            text_to_samples[norm].append(s)

        # 2. Build DSU over unique question texts
        dsu = DisjointSet(unique_texts)

        # 3. Detect near-duplicate pairs
        n = len(unique_texts)
        for i in range(n):
            t1 = unique_texts[i]
            for j in range(i + 1, n):
                t2 = unique_texts[j]
                sim = token_jaccard_similarity(t1, t2)
                if sim >= self.similarity_threshold:
                    dsu.union(t1, t2)

        # 4. Generate cluster IDs from root canonical representations
        root_to_cluster_id: dict[str, str] = {}
        for text in unique_texts:
            root = dsu.find(text)
            if root not in root_to_cluster_id:
                h = hashlib.sha256(root.encode("utf-8")).hexdigest()[:10]
                root_to_cluster_id[root] = f"cluster_{h}"

        # 5. Assign cluster IDs to all samples
        for text, sample_list in text_to_samples.items():
            cluster_id = root_to_cluster_id[dsu.find(text)]
            for s in sample_list:
                s.cluster_id = cluster_id

        return samples
