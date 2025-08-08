import json
from openai import OpenAI
import os
import math

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def evaluate_rag(query, response, context):
    prompt = f"""너는 RAG 시스템의 응답을 평가하는 AI 평가자입니다.

사용자의 질의:
{query}

RAG 시스템의 응답:
{response}

RAG가 참고한 문서(context):
{context}

다음 기준에 따라 평가하세요:
1. 응답이 질의에 대해 얼마나 정확한지 (정확성)
2. 참고 문서에 기반한 응답인지 여부 (근거 기반성)
3. 응답이 얼마나 이해하기 쉬운지 (명확성)

위 세 기준 각각에 대해 1~5 점으로 평가하고, 간단한 이유도 포함해주세요. 아래 형식을 따라 주세요:

정확성: 4/5 - 응답은 대부분 정확하지만 일부 세부정보 부족
근거 기반성: 5/5 - 응답은 명확히 문서 기반임
명확성: 5/5 - 간결하고 이해하기 쉬움
"""

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return completion.choices[0].message.content

def evaluate_from_jsonl(jsonl_path):
    with open(jsonl_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        item = json.loads(line)
        query = item["query"]
        response = item["response"]
        context = item["context"]

        print(f"\n===== 질의 {i+1} 평가 중 =====")
        evaluation = evaluate_rag(query, response, context)
        print(evaluation)

def load_jsonl(path):
    results = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            results[item["query"]] = [tuple(idx) for idx in item["indices"]]
    return results


def load_gold(path):
    with open(path, "r", encoding="utf-8") as f:
        gold_dict = {}
        for line in f:
            item = json.loads(line)
            query = item["query"]
            chunk_id = item.get("chunk_id", [])
            gold_dict[query] = [tuple(cid) for cid in chunk_id]  # (doc_id, page)
        return gold_dict

def evaluate_recall_at_k(retrieved_dict, gold_dict, k=3):
    total_gold = 0
    total_hit = 0

    for query, retrieved_ids in retrieved_dict.items(): # retrieved_ids는 chunk_id 리스트
        gold_ids = gold_dict.get(query) 
        if not gold_ids:
            continue

        retrieved_topk = set(retrieved_ids[:k])
        gold_set = set(gold_ids)

        hit_count = len(retrieved_topk & gold_set)  # 교집합
        total_hit += hit_count
        total_gold += len(gold_set)

    recall = total_hit / total_gold if total_gold else 0.0
    print(f"Strict Recall@{k}: {recall:.4f} ({total_hit}/{total_gold})")
    return recall

def f1_score_at_k(retrieved_dict, gold_dict, k=-1):
    total_true_positives = 0
    total_false_positives = 0
    total_false_negatives = 0
    total_gold = 0

    for query, retrieved_ids in retrieved_dict.items():
        gold_ids = gold_dict.get(query)
        if not gold_ids:
            continue
        
        retrieved_topk = set(retrieved_ids[:k]) if k > 0 else set(retrieved_ids)
        gold_set = set(gold_ids)

        true_positives = retrieved_topk.intersection(gold_set)
        false_positives = retrieved_topk - gold_set
        false_negatives = gold_set - retrieved_topk    

        total_true_positives += len(true_positives)
        total_false_positives += len(false_positives)
        total_false_negatives += len(false_negatives)

        total_gold += len(gold_set)

    total_precision = total_true_positives / total_gold if total_gold > 0 else 0
    total_recall = total_true_positives /total_gold if total_gold > 0 else 0
    total_f1_score = 2 * (total_precision * total_recall) / (total_precision + total_recall) if total_precision + total_recall > 0 else 0

    if k == -1:
        print(f"Strict precision: {total_precision:.4f}")
        print(f"Strict recall: {total_recall:.4f}")
        print(f"Strict f1_score: {total_f1_score:.4f}")
    else: 
        print(f"Strict precision@{k}: {total_precision:.4f}")
        print(f"Strict recall@{k}: {total_recall:.4f}")
        print(f"Strict f1_score@{k}: {total_f1_score:.4f}")

    return total_precision, total_recall, total_f1_score

def evaluate_ndcg_at_k(retrieved_dict, gold_dict, k=3):

    total_ndcg = 0.0
    query_count = 0

    for query, retrieved_ids in retrieved_dict.items():
        gold_ids = set(gold_dict.get(query, []))
        if not gold_ids:
            continue

        # DCG 계산
        dcg = 0.0
        for rank, chunk_id in enumerate(retrieved_ids[:k], start=1):
            if chunk_id in gold_ids:
                dcg += 1 / math.log2(rank + 1)

        # 이상적인 DCG(IDCG) 계산
        ideal_hits = min(len(gold_ids), k)
        idcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))

        ndcg = dcg / idcg if idcg > 0 else 0.0
        total_ndcg += ndcg
        query_count += 1

    avg_ndcg = total_ndcg / query_count if query_count else 0.0
    print(f"nDCG@{k}: {avg_ndcg:.4f}")
    
    return avg_ndcg