from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import Sequence

from app.misconceptions.dataset.clusterer import (
    QuestionClusterer,
    normalize_question_text,
    token_jaccard_similarity,
)
from app.misconceptions.dataset.schemas import (
    LeakageCheckResult,
    MisconceptionSample,
    SplitStats,
)


class LeakageError(ValueError):
    """Raised when data leakage between splits is detected."""


class LeakFreeSplitter:
    """Partitions dataset into Train / Validation / Test sets strictly at the
    Question Cluster level to guarantee zero leakage between splits.
    """

    def __init__(
        self,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        random_seed: int = 42,
    ) -> None:
        total = train_ratio + val_ratio + test_ratio
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Ratios must sum to 1.0, got {total}")
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.random_seed = random_seed

    def split(
        self, samples: list[MisconceptionSample]
    ) -> tuple[list[MisconceptionSample], list[MisconceptionSample], list[MisconceptionSample]]:
        """Split samples into (train, val, test) guaranteeing zero cluster overlap."""
        if not samples:
            return [], [], []

        # Ensure cluster_id is present
        if any(s.cluster_id is None for s in samples):
            clusterer = QuestionClusterer()
            samples = clusterer.assign_clusters(samples)

        # 1. Group samples by cluster
        cluster_to_samples: dict[str, list[MisconceptionSample]] = defaultdict(list)
        for s in samples:
            assert s.cluster_id is not None
            cluster_to_samples[s.cluster_id].append(s)

        # 2. Sort clusters deterministically for reproducibility
        rng = random.Random(self.random_seed)
        cluster_ids = sorted(cluster_to_samples.keys())
        rng.shuffle(cluster_ids)

        total_samples_count = len(samples)
        target_train_count = int(total_samples_count * self.train_ratio)
        target_val_count = int(total_samples_count * self.val_ratio)

        train_clusters: set[str] = set()
        val_clusters: set[str] = set()
        test_clusters: set[str] = set()

        curr_train_count = 0
        curr_val_count = 0

        # Greedy allocation by cluster size
        for cid in cluster_ids:
            c_size = len(cluster_to_samples[cid])
            if curr_train_count + c_size <= target_train_count or (
                curr_train_count == 0 and len(cluster_ids) >= 3
            ):
                train_clusters.add(cid)
                curr_train_count += c_size
            elif curr_val_count + c_size <= target_val_count or (
                curr_val_count == 0 and len(cluster_ids) >= 2
            ):
                val_clusters.add(cid)
                curr_val_count += c_size
            else:
                test_clusters.add(cid)

        # Fallback: if test or val is empty but we have enough clusters, rebalance
        if not test_clusters and len(train_clusters) > 1:
            moved = train_clusters.pop()
            test_clusters.add(moved)
        if not val_clusters and len(train_clusters) > 1:
            moved = train_clusters.pop()
            val_clusters.add(moved)

        # 3. Assign split tags to samples
        train_samples: list[MisconceptionSample] = []
        val_samples: list[MisconceptionSample] = []
        test_samples: list[MisconceptionSample] = []

        for cid, s_list in cluster_to_samples.items():
            if cid in train_clusters:
                split_name = "train"
                target_list = train_samples
            elif cid in val_clusters:
                split_name = "val"
                target_list = val_samples
            else:
                split_name = "test"
                target_list = test_samples

            for s in s_list:
                s.split = split_name
                target_list.append(s)

        # 4. Strict leakage verification
        leak_result = self.verify_leak_free(train_samples, val_samples, test_samples)
        if not leak_result.is_leak_free:
            raise LeakageError(f"Cross-split leakage detected: {leak_result.notes}")

        return train_samples, val_samples, test_samples

    def verify_leak_free(
        self,
        train_samples: Sequence[MisconceptionSample],
        val_samples: Sequence[MisconceptionSample],
        test_samples: Sequence[MisconceptionSample],
    ) -> LeakageCheckResult:
        """Verify absolute independence between train, validation, and test splits."""
        train_clusters = {s.cluster_id for s in train_samples if s.cluster_id}
        val_clusters = {s.cluster_id for s in val_samples if s.cluster_id}
        test_clusters = {s.cluster_id for s in test_samples if s.cluster_id}

        train_val_cluster = len(train_clusters & val_clusters)
        train_test_cluster = len(train_clusters & test_clusters)
        val_test_cluster = len(val_clusters & test_clusters)

        # Question text normalized overlap
        train_texts = {normalize_question_text(s.question) for s in train_samples}
        val_texts = {normalize_question_text(s.question) for s in val_samples}
        test_texts = {normalize_question_text(s.question) for s in test_samples}

        tv_text = len(train_texts & val_texts)
        tt_text = len(train_texts & test_texts)
        vt_text = len(val_texts & test_texts)

        # Near-duplicate cross-split check
        near_duplicate_leaks = 0
        for t1 in train_texts:
            for t2 in val_texts | test_texts:
                if token_jaccard_similarity(t1, t2) >= 0.60:
                    near_duplicate_leaks += 1

        is_leak_free = (
            train_val_cluster == 0
            and train_test_cluster == 0
            and val_test_cluster == 0
            and tv_text == 0
            and tt_text == 0
            and vt_text == 0
            and near_duplicate_leaks == 0
        )

        notes = (
            "Zero question leakage verified across all splits."
            if is_leak_free
            else f"Leakage detected: cluster overlaps (tv={train_val_cluster}, tt={train_test_cluster}, vt={val_test_cluster}), "
            f"text overlaps (tv={tv_text}, tt={tt_text}, vt={vt_text}), near_dups={near_duplicate_leaks}"
        )

        return LeakageCheckResult(
            is_leak_free=is_leak_free,
            train_val_cluster_overlap=train_val_cluster,
            train_test_cluster_overlap=train_test_cluster,
            val_test_cluster_overlap=val_test_cluster,
            train_val_question_text_overlap=tv_text,
            train_test_question_text_overlap=tt_text,
            val_test_question_text_overlap=vt_text,
            notes=notes,
        )

    def calculate_split_stats(
        self,
        samples: Sequence[MisconceptionSample],
        split_name: str,
    ) -> SplitStats:
        """Calculate statistics for a single split partition."""
        cluster_ids = sorted(list({s.cluster_id for s in samples if s.cluster_id}))
        return SplitStats(
            sample_count=len(samples),
            percentage=0.0,  # calculated in caller relative to total
            question_clusters_count=len(cluster_ids),
            cluster_ids=cluster_ids,
        )
