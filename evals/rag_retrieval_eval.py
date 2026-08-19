"""Shared, deterministic retrieval metrics for the GOA RAG evaluations."""


import json
import math
import sys
import httpx
from typing import List, Set
RAG_QUERY_URL = "http://localhost:8084/query"
INTERNAL_API_KEY = "supersecret_internal_key_123"


def relevant_at_1(results: List[str], relevant_ids: Set[str]) -> float:
    """Returns 1.0 if top retrieved document ID (results[0]) is in relevant_ids, else 0.0."""
    if not results or not relevant_ids:
        return 0.0
    return 1.0 if results[0] in relevant_ids else 0.0


def recall_at_15(results: List[str], relevant_ids: Set[str]) -> float:
    """Calculates recall@15: fraction of ground-truth relevant_ids found within top-15 retrieved IDs."""
    if not results or not relevant_ids:
        return 0.0
    found = set(results[:15]) & set(relevant_ids)
    return len(found) / float(len(relevant_ids))


def recall_at_k(results: List[str], relevant_ids: Set[str], k: int) -> float:
    """Fraction of labelled relevant documents present in the first ``k`` results."""

    if not results or not relevant_ids:
        return 0.0
    return len(set(results[:k]) & relevant_ids) / float(len(relevant_ids))


def ndcg_at_k(results: List[str], relevant_ids: Set[str], k: int) -> float:
    """Binary-relevance nDCG at ``k`` for a hand-labelled document set."""

    if not results or not relevant_ids:
        return 0.0
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, document_id in enumerate(results[:k], 1)
        if document_id in relevant_ids
    )
    ideal_hits = min(len(relevant_ids), k)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal


def reciprocal_rank(results: List[str], relevant_ids: Set[str]) -> float:
    """Calculates Reciprocal Rank (1/rank of first relevant chunk). Returns 0.0 if not found."""
    if not results or not relevant_ids:
        return 0.0
    for rank_idx, doc_id in enumerate(results, 1):
        if doc_id in relevant_ids:
            return 1.0 / float(rank_idx)
    return 0.0



def run_retrieval_eval(dataset_path: str = "evals/golden_dataset.json"):
    """
    Executes retrieval evaluation against live RAG service.
    Fails loudly with exit code 1 if service is unreachable.
    """
    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Dataset file not found at {dataset_path}")
        sys.exit(1)
    eval_items = data.get("rag_retrieval", [])
    if not eval_items:
        eval_items = [item for item in data.get("rag", []) if "relevant_document_ids" in item]
    if not eval_items:
        print("Error: No evaluation items with 'relevant_document_ids' found in dataset.")
        sys.exit(1)
    r1_scores: List[float] = []
    rec15_scores: List[float] = []
    mrr_scores: List[float] = []
    print("\n========================================================")
    print(f"       RAG RETRIEVAL EVALUATION ({len(eval_items)} items)")
    print("========================================================\n")
    with httpx.Client(timeout=15.0) as client:
        for idx, item in enumerate(eval_items, 1):
            question = item["question"]
            relevant_ids = set(item.get("relevant_document_ids", []))
            payload = {"question": question, "userId": "eval-harness"}
            headers = {"X-Internal-Api-Key": INTERNAL_API_KEY, "Content-Type": "application/json"}
            try:
                response = client.post(RAG_QUERY_URL, json=payload, headers=headers)
                response.raise_for_status()
                res_data = response.json()
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                print(f"\n[FATAL] RAG Service call failed for query '{question}': {exc}")
                print("Infrastructure failure detected — exiting non-zero.")
                sys.exit(1)
            retrieved_sources = res_data.get("sources", [])
            retrieved_ids = [s["id"] for s in retrieved_sources if isinstance(s, dict) and "id" in s]
            r1 = relevant_at_1(retrieved_ids, relevant_ids)
            rec15 = recall_at_15(retrieved_ids, relevant_ids)
            rr = reciprocal_rank(retrieved_ids, relevant_ids)
            r1_scores.append(r1)
            rec15_scores.append(rec15)
            mrr_scores.append(rr)
            print(f"[{idx:2d}/{len(eval_items)}] Question: '{question[:50]}...'")
            print(f"     MRR = {rr:.3f} | rel@1 = {r1:.2f} | rec@15 = {rec15:.2f}")
    avg_mrr = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0.0
    avg_r1 = sum(r1_scores) / len(r1_scores) if r1_scores else 0.0
    avg_rec15 = sum(rec15_scores) / len(rec15_scores) if rec15_scores else 0.0
    print("\n========================================================")
    print(" SUMMARY METRICS")
    print(f"   Mean Reciprocal Rank (MRR): {avg_mrr:.4f}")
    print(f"   Mean relevant@1:           {avg_r1 * 100:.2f}% ({sum(r1_scores)}/{len(r1_scores)})")
    print(f"   Mean recall@15:            {avg_rec15 * 100:.2f}%")
    print("========================================================\n")
    return {"mrr": avg_mrr, "relevant_at_1": avg_r1, "recall_at_15": avg_rec15}
if __name__ == "__main__":
    dataset_file = sys.argv[1] if len(sys.argv) > 1 else "evals/golden_dataset.json"
    run_retrieval_eval(dataset_file)
