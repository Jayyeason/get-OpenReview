#!/usr/bin/env python3
"""
根据 --ai 和 --true 两个输入文件，分别按论文结果状态（accept/reject/withdrawn）
计算评分均值并输出。

输入：
- --ai   /remote-home1/bwli/get_open_review/model-service/qwen3-30B-reviews.json
- --true /remote-home1/bwli/get_open_review/qwen_review/review_conversations_352.json

输出：
- 打印两份数据的各状态评分均值，以及评分条数与论文数。

说明：
- AI 数据的评分来自 reviews[*].review.rating.value
- 真实数据的评分来自 conversations 中各条评审 note 的 rating.value
- conversations 可能为列表的列表，脚本会递归遍历。
"""

import argparse
import json
import os
import re
from typing import Any, Dict, List, Tuple


def normalize_state(state: Any) -> str | None:
    if state is None:
        return None
    s = str(state).strip().lower()
    # 常见同义映射
    if s in {"accept", "accepted"}:
        return "accept"
    if s in {"reject", "rejected", "desk-reject", "desk_reject"}:
        return "reject"
    if s in {"withdraw", "withdrawn"}:
        return "withdrawn"
    return s if s in {"accept", "reject", "withdrawn"} else None


def parse_rating(val: Any) -> float | None:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        m = re.search(r"[-+]?\d+(?:\.\d+)?", val)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def walk_collect_ratings(node: Any, out: List[float]) -> None:
    if isinstance(node, dict):
        rat = node.get("rating")
        if isinstance(rat, dict):
            v = parse_rating(rat.get("value"))
            if v is not None:
                out.append(v)
        # 也可能存在嵌套 review 结构
        review = node.get("review")
        if isinstance(review, dict):
            rat2 = review.get("rating")
            if isinstance(rat2, dict):
                v2 = parse_rating(rat2.get("value"))
                if v2 is not None:
                    out.append(v2)
        # 深度遍历字典中的子项以防遗漏
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                walk_collect_ratings(v, out)
    elif isinstance(node, list):
        for el in node:
            walk_collect_ratings(el, out)


def collect_true_groups(true_data: Dict[str, Any]) -> Tuple[Dict[str, List[float]], Dict[str, int]]:
    ratings_by_state: Dict[str, List[float]] = {"accept": [], "reject": [], "withdrawn": []}
    paper_counts: Dict[str, int] = {"accept": 0, "reject": 0, "withdrawn": 0}
    for _, item in true_data.items():
        state = normalize_state(item.get("result", {}).get("state"))
        if state not in ratings_by_state:
            continue
        paper_counts[state] += 1
        conv = item.get("conversations", [])
        tmp: List[float] = []
        walk_collect_ratings(conv, tmp)
        ratings_by_state[state].extend(tmp)
    return ratings_by_state, paper_counts


def collect_ai_groups(ai_data: Dict[str, Any]) -> Tuple[
    Dict[str, List[float]],
    Dict[str, int],
    Dict[str, List[float]],
    Dict[str, Dict[str, List[float]]],
]:
    ratings_by_state: Dict[str, List[float]] = {"accept": [], "reject": [], "withdrawn": []}
    paper_counts: Dict[str, int] = {"accept": 0, "reject": 0, "withdrawn": 0}
    reviewer_ratings: Dict[str, List[float]] = {}
    reviewer_state_ratings: Dict[str, Dict[str, List[float]]] = {}
    for _, item in ai_data.items():
        state = normalize_state(item.get("result", {}).get("state"))
        if state not in ratings_by_state:
            continue
        paper_counts[state] += 1
        reviews = item.get("reviews", [])
        for rev in reviews:
            review_obj = rev.get("review", {})
            rat = review_obj.get("rating")
            if isinstance(rat, dict):
                v = parse_rating(rat.get("value"))
                if v is not None:
                    ratings_by_state[state].append(v)
                    reviewer_id = rev.get("reviewer_id")
                    if isinstance(reviewer_id, str) and reviewer_id.strip():
                        reviewer_ratings.setdefault(reviewer_id, []).append(v)
                        reviewer_state_ratings.setdefault(reviewer_id, {
                            "accept": [],
                            "reject": [],
                            "withdrawn": []
                        })
                        reviewer_state_ratings[reviewer_id][state].append(v)
    return ratings_by_state, paper_counts, reviewer_ratings, reviewer_state_ratings


def compute_means(ratings_by_state: Dict[str, List[float]]) -> Dict[str, float | None]:
    out: Dict[str, float | None] = {}
    for state, vals in ratings_by_state.items():
        out[state] = (sum(vals) / len(vals)) if vals else None
    return out


def main():
    parser = argparse.ArgumentParser(description="按论文结果状态计算 AI 与真实数据的评分均值")
    parser.add_argument("--ai", required=True, help="AI 评审 JSON 路径，如 model-service/qwen3-30B-reviews.json")
    parser.add_argument("--true", required=True, help="真实对话 JSON 路径，如 qwen_review/review_conversations_352.json")
    args = parser.parse_args()

    # 读取 AI
    if not os.path.isfile(args.ai):
        raise FileNotFoundError(f"AI 评审文件不存在: {args.ai}")
    with open(args.ai, "r", encoding="utf-8") as f:
        ai_data = json.load(f)
    if not isinstance(ai_data, dict):
        raise ValueError("AI 输入 JSON 顶层应为字典：paper_id -> 记录")

    # 读取真实
    if not os.path.isfile(args.true):
        raise FileNotFoundError(f"真实数据文件不存在: {args.true}")
    with open(args.true, "r", encoding="utf-8") as f:
        true_data = json.load(f)
    if not isinstance(true_data, dict):
        raise ValueError("真实输入 JSON 顶层应为字典：forum_id -> 记录")

    ai_ratings, ai_papers, reviewer_ratings, reviewer_state_ratings = collect_ai_groups(ai_data)
    true_ratings, true_papers = collect_true_groups(true_data)

    ai_means = compute_means(ai_ratings)
    true_means = compute_means(true_ratings)

    def fmt_mean(x: float | None) -> str:
        return f"{x:.4f}" if isinstance(x, float) else "N/A"

    print("Dataset: TRUE (真实数据)")
    for s in ("accept", "reject", "withdrawn"):
        print(f"- {s}: mean={fmt_mean(true_means[s])} | ratings={len(true_ratings[s])} | papers={true_papers[s]}")

    print("\nDataset: AI (模型评审)")
    for s in ("accept", "reject", "withdrawn"):
        print(f"- {s}: mean={fmt_mean(ai_means[s])} | ratings={len(ai_ratings[s])} | papers={ai_papers[s]}")

    if reviewer_ratings:
        reviewer_means = compute_means(reviewer_ratings)
        print("\nAI Reviewer Averages (模型评审员均分)")
        for reviewer_id in sorted(reviewer_ratings):
            scores = reviewer_ratings[reviewer_id]
            mean_str = fmt_mean(reviewer_means[reviewer_id])
            print(f"- {reviewer_id}: mean={mean_str} | ratings={len(scores)}")
            state_means = compute_means(reviewer_state_ratings.get(reviewer_id, {}))
            for state in ("accept", "reject", "withdrawn"):
                vals = reviewer_state_ratings.get(reviewer_id, {}).get(state, [])
                if vals:
                    print(f"    · {state}: mean={fmt_mean(state_means.get(state))} | ratings={len(vals)}")


if __name__ == "__main__":
    main()