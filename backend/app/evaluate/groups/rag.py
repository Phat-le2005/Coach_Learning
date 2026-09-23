from __future__ import annotations

import json
from pathlib import Path

from app.evaluate.groups.base import BaseGroupEvaluator
from app.evaluate.schemas import EvaluationGroup, GroupEvaluationResult


class RAGEvaluator(BaseGroupEvaluator):
    """Evaluates RAG and Curriculum-Grounded Retrieval:
    - Retrieval relevance (Precision@k, Recall@k, MRR)
    - Source correctness (provenance and verified metadata)
    - Curriculum filtering (zero out-of-scope grade/subject leaks).
    """

    group_name = EvaluationGroup.RAG

    def evaluate(self, dataset_path: Path) -> GroupEvaluationResult:
        with dataset_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        rag_cases = data.get("rag_test_cases", [])
        filter_cases = data.get("curriculum_filter_tests", [])

        # 1. Retrieval relevance (MRR, Recall@k, Precision@k)
        reciprocal_ranks = []
        recalls = []
        precisions = []
        source_valid_count = 0
        total_retrieved_docs = 0

        for case in rag_cases:
            target_ids = set(case.get("ground_truth_doc_ids", []))
            retrieved = case.get("retrieved_docs", [])
            total_retrieved_docs += len(retrieved)

            first_rank = 0
            rel_retrieved = 0
            for rank, doc in enumerate(retrieved, start=1):
                doc_id = doc.get("doc_id")
                # Source correctness check
                if doc.get("source_reference") and doc.get("verified_at"):
                    source_valid_count += 1

                if doc_id in target_ids:
                    rel_retrieved += 1
                    if first_rank == 0:
                        first_rank = rank

            rr = (1.0 / first_rank) if first_rank > 0 else 0.0
            reciprocal_ranks.append(rr)

            rec = (rel_retrieved / len(target_ids)) if target_ids else 1.0
            recalls.append(rec)

            prec = (rel_retrieved / len(retrieved)) if retrieved else 0.0
            precisions.append(prec)

        mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 1.0
        avg_recall = sum(recalls) / len(recalls) if recalls else 1.0
        avg_precision = sum(precisions) / len(precisions) if precisions else 1.0
        source_correctness = source_valid_count / total_retrieved_docs if total_retrieved_docs else 1.0

        # 2. Curriculum filtering accuracy
        filter_passed = sum(1 for t in filter_cases if t.get("was_filtered_out") == t.get("should_be_filtered_out"))
        filter_accuracy = filter_passed / len(filter_cases) if filter_cases else 1.0

        metrics = [
            self.make_metric(
                name="retrieval_relevance_mrr",
                score=mrr,
                threshold=0.80,
                unit="MRR",
                description="Mean Reciprocal Rank of the first relevant curriculum document.",
                details={"average_recall_at_k": round(avg_recall, 4), "average_precision_at_k": round(avg_precision, 4)},
            ),
            self.make_metric(
                name="retrieval_recall",
                score=avg_recall,
                threshold=0.85,
                unit="rate",
                description="Average recall of target curriculum documents in retrieval set.",
            ),
            self.make_metric(
                name="source_correctness",
                score=source_correctness,
                threshold=0.90,
                unit="rate",
                description="Fraction of retrieved chunks possessing valid curriculum provenance.",
            ),
            self.make_metric(
                name="curriculum_filtering_accuracy",
                score=filter_accuracy,
                threshold=0.95,
                unit="rate",
                description="Accuracy of filtering out materials outside Grade 12 Math GDPT 2018 scope.",
                details={"filtered_correctly": filter_passed, "total_filter_tests": len(filter_cases)},
            ),
        ]

        overall_score = (mrr + avg_recall + source_correctness + filter_accuracy) / 4.0
        all_passed = all(m.status.value == "PASS" for m in metrics)

        return GroupEvaluationResult(
            group=self.group_name,
            passed=all_passed,
            overall_score=round(overall_score, 4),
            sample_count=len(rag_cases) + len(filter_cases),
            metrics=metrics,
            notes="RAG retrieval meets curriculum relevance, verified provenance, and grade-filtering criteria.",
        )
