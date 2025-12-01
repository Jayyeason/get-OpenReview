#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 DPO 训练数据：

- human review 作为 chosen
- Qwen3-8B 生成的同 strictness 评审作为 rejected

目录约定（可用命令行参数覆盖）：
  raw_dir        # deepseek 打好 strictness 的人类评审
  ai_dir         # qwen3-8B 生成的 AI 评审
  text_dir       # 论文全文（可选）
  out_dir        # 本脚本输出的 DPO jsonl
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import random


# ------------------------ 基础工具函数 ------------------------


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] 读取 JSON 失败: {path} | {e}")
        return None


def dump_jsonl_line(f, obj: Dict[str, Any]):
    line = json.dumps(obj, ensure_ascii=False)
    f.write(line + "\n")


# ------------------------ 提取 human review ------------------------


def extract_human_reviews(paper: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从 raw/<paper_id>.json 里提取信息。

    输入结构示例见用户提供的数据：
    {
      "paper_forum": "...",
      "paper_number": ...,
      "paper_title": "...",
      "paper_abstract": "...",   # 可能不存在
      "official_reviews": [
        {
          "deepseek_judge_strictness": "strict",
          "reviewer_id": "Reviewer_xxx",
          "review": { ... }
        },
        ...
      ]
    }

    返回列表，每个元素形如：
    {
      "bucket": "lenient/moderate/strict",
      "reviewer_id": "...",
      "paper_forum": "...",
      "paper_title": "...",
      "paper_abstract": "...",
      "review": { summary/strengths/... }
    }
    """
    paper_forum = paper.get("paper_forum", "")
    paper_title = paper.get("paper_title", "")
    paper_abstract = paper.get("paper_abstract", "")

    official_reviews = paper.get("official_reviews", [])
    results: List[Dict[str, Any]] = []

    if not isinstance(official_reviews, list):
        return results

    for item in official_reviews:
        if not isinstance(item, dict):
            continue

        bucket = item.get("deepseek_judge_strictness")  # lenient / moderate / strict
        reviewer_id = item.get("reviewer_id")
        review = item.get("review", {})

        if bucket not in ("lenient", "moderate", "strict"):
            continue
        if not reviewer_id or not isinstance(review, dict):
            continue

        human_review = {
            "summary": review.get("summary", ""),
            "strengths": review.get("strengths", ""),
            "weaknesses": review.get("weaknesses", ""),
            "questions": review.get("questions", ""),
            "rating": review.get("rating", None),
            "confidence": review.get("confidence", None),
            "soundness": review.get("soundness", None),
            "presentation": review.get("presentation", None),
            "contribution": review.get("contribution", None),
        }

        results.append(
            {
                "bucket": bucket,
                "reviewer_id": reviewer_id,
                "paper_forum": paper_forum,
                "paper_title": paper_title,
                "paper_abstract": paper_abstract,
                "review": human_review,
            }
        )

    return results


# ------------------------ 提取 AI review ------------------------


def build_ai_review_map(ai_json: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    从 8b_generated/<paper_id>.json 中构建 strictness -> review 映射。

    结构示例：
    {
      "paper_forum": "...",
      "paper_abstract": "...",
      "ai_reviews": [
        {
          "strictness": "lenient",
          "reviewer_id": "ai_lenient",
          "review": { ... }
        },
        ...
      ]
    }

    返回：
      {
        "lenient":  { summary/strengths/... },
        "moderate": {...},
        "strict":   {...}
      }
    """
    ai_reviews = ai_json.get("ai_reviews", [])
    mapping: Dict[str, Dict[str, Any]] = {}

    if not isinstance(ai_reviews, list):
        return mapping

    for item in ai_reviews:
        if not isinstance(item, dict):
            continue
        bucket = item.get("strictness")
        review = item.get("review", {})
        if bucket not in ("lenient", "moderate", "strict"):
            continue
        if not isinstance(review, dict):
            continue

        mapping[bucket] = {
            "summary": review.get("summary", ""),
            "strengths": review.get("strengths", ""),
            "weaknesses": review.get("weaknesses", ""),
            "questions": review.get("questions", ""),
            "rating": review.get("rating", None),
            "confidence": review.get("confidence", None),
            "soundness": review.get("soundness", None),
            "presentation": review.get("presentation", None),
            "contribution": review.get("contribution", None),
        }

    return mapping


# ------------------------ 构造 prompt ------------------------


def build_prompt(
    bucket: str,
    paper_title: str,
    paper_abstract: str,
    paper_text: str,
    max_text_chars: int = 40000,
) -> str:
    """
    构造 DPO 的 prompt 文本。

    - bucket: lenient / moderate / strict
    - paper_text 过长时截断到 max_text_chars
    """
    strict_desc = {
        "lenient": (
            "You are a relatively LENIENT ICLR reviewer. "
            "You focus on potential and are forgiving of minor flaws. "
            "You write encouraging, soft reviews and are comfortable accepting papers "
            "with incomplete experiments or unclear novelty."
        ),
        "moderate": (
            "You are a MODERATE ICLR reviewer. "
            "You balance strengths and weaknesses and apply standard conference criteria. "
            "You are fair and balanced: you recognize contributions but also clearly point out limitations."
        ),
        "strict": (
            "You are a STRICT ICLR reviewer. "
            "You emphasize weaknesses, demand strong evidence, and are cautious about acceptance. "
            "You are sensitive to methodological flaws, weak experiments, and unclear novelty."
        ),
    }.get(bucket, "You are an ICLR reviewer.")

    if paper_text and len(paper_text) > max_text_chars:
        paper_text = (
            paper_text[:max_text_chars]
            + "\n\n[Paper content truncated for length in this training sample.]"
        )

    prompt = f"""You are an ICLR conference reviewer.

Reviewer strictness profile:
{strict_desc}

You must read the following paper and write a full ICLR-style review.

Your output MUST satisfy all of the following:

1. It MUST be a single valid JSON object (no extra text, no markdown).
2. It MUST contain exactly the following fields:
   - summary      (string)
   - strengths    (string)
   - weaknesses   (string)
   - questions    (string)
   - rating       (integer, one of 1, 3, 5, 6, 8, 10)
   - confidence   (integer in [1, 5])
   - soundness    (integer in [1, 4])
   - presentation (integer in [1, 4])
   - contribution (integer in [1, 4])
3. Do NOT add any extra fields.

For example (values are illustrative only, DO NOT copy literally):

{{
  "summary": "This paper proposes a new method for modeling spatial-temporal counting processes and evaluates it on several real-world datasets.",
  "strengths": "1) The problem is practically relevant. 2) The empirical results suggest improvements over baselines.",
  "weaknesses": "1) The novelty compared to prior work is not fully clarified. 2) Some experimental details are missing.",
  "questions": "1) How sensitive is the method to hyperparameters? 2) Can the approach scale to larger datasets?",
  "rating": 3,
  "confidence": 4,
  "soundness": 2,
  "presentation": 3,
  "contribution": 2
}}

Paper information:

Title:
{paper_title}

Abstract:
{paper_abstract}

Full Text:
{paper_text}

Now write ONLY the JSON object, without any extra explanation."""
    return prompt


# ------------------------ 主逻辑 ------------------------


def main():
    parser = argparse.ArgumentParser(
        description="构建 ICLR2025 DPO 数据集（lenient/moderate/strict 三个桶）"
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/raw/iclr2025_ds_form",
        help="带有 deepseek_judge_strictness 的 human review 目录（绝对路径或相对路径）",
    )
    parser.add_argument(
        "--ai-dir",
        type=str,
        default="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/8b_generated",
        help="Qwen3-8B 生成评审所在目录（8b_generated）",
    )
    parser.add_argument(
        "--text-dir",
        type=str,
        default="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/extracted_contents",
        help="论文全文 .txt 所在目录）",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/dpo_data",
        help="输出 DPO jsonl 目录",
    )
    parser.add_argument(
        "--max-paper-chars",
        type=int,
        default=40000,
        help="单篇论文在 prompt 中保留的最大字符数（包含正文；超出会截断）",
    )

    parser.add_argument(
        "--eval-count",
        type=int,
        default=200,
        help="划分多少篇论文作为评测集（剩余的作为训练集）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子",
    )

    args = parser.parse_args()

    raw_dir = Path(args.raw_dir).resolve()
    ai_dir = Path(args.ai_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    text_dir = Path(args.text_dir).resolve() if args.text_dir else None

    print(f"[INFO] raw_dir  = {raw_dir}")
    print(f"[INFO] ai_dir   = {ai_dir}")
    print(f"[INFO] text_dir = {text_dir if text_dir else '(disabled)'}")
    print(f"[INFO] out_dir  = {out_dir}")
    print(f"[INFO] max_paper_chars = {args.max_paper_chars}")

    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        raw_files = sorted(raw_dir.glob("*.json"))
        print(f"[INFO] 在 raw_dir 中发现 {len(raw_files)} 篇论文")

        # 随机打乱并划分
        random.seed(args.seed)
        random.shuffle(raw_files)

        eval_count = args.eval_count
        eval_files_set = set(raw_files[:eval_count])
        train_files_set = set(raw_files[eval_count:])

        print(f"[INFO] 划分: Train={len(train_files_set)}, Eval={len(eval_files_set)} (Seed={args.seed})")

        # 准备输出文件句柄：train 和 eval 分别创建一套
        modes = ["train", "eval"]
        buckets = ["lenient", "moderate", "strict", "all"]

        # handles[mode][bucket] -> file object
        handles = {m: {} for m in modes}
        paths = {m: {} for m in modes}

        for m in modes:
            for b in buckets:
                fname = f"{m}_iclr_dpo_{b}.jsonl"  # e.g., train_iclr_dpo_lenient.jsonl
                p = out_dir / fname
                paths[m][b] = p
                handles[m][b] = open(p, "w", encoding="utf-8")

        # 统计计数
        total_pairs = {m: {b: 0 for b in buckets} for m in modes}

        for idx, raw_path in enumerate(raw_files, 1):
            paper = load_json(raw_path)
            if not paper:
                continue

            # 判断当前论文属于 train 还是 eval
            mode = "eval" if raw_path in eval_files_set else "train"

            paper_forum = paper.get("paper_forum") or raw_path.stem
            paper_title = paper.get("paper_title", "")
            paper_abstract = paper.get("paper_abstract", "")

            # 论文全文（可选）
            paper_text = ""
            if text_dir is not None:
                text_path = text_dir / f"{paper_forum}.txt"
                if text_path.exists():
                    try:
                        paper_text = text_path.read_text(encoding="utf-8")
                    except Exception as e:
                        print(f"[WARN] 读取全文失败: {text_path} | {e}")

            human_reviews = extract_human_reviews(paper)
            if not human_reviews:
                continue

            ai_path = ai_dir / f"{paper_forum}.json"
            if not ai_path.exists():
                continue
            ai_json = load_json(ai_path)
            if not ai_json:
                continue

            ai_review_map = build_ai_review_map(ai_json)
            if not ai_review_map:
                continue

            for hr in human_reviews:
                bucket = hr["bucket"]
                if bucket not in ai_review_map:
                    continue

                prompt = build_prompt(
                    bucket=bucket,
                    paper_title=paper_title,
                    paper_abstract=paper_abstract,
                    paper_text=paper_text,
                    max_text_chars=args.max_paper_chars,
                )

                chosen_obj = hr["review"]
                rejected_obj = ai_review_map[bucket]

                chosen = json.dumps(chosen_obj, ensure_ascii=False)
                rejected = json.dumps(rejected_obj, ensure_ascii=False)

                dpo_sample = {
                    "prompt": prompt,
                    "chosen": chosen,
                    "rejected": rejected,
                    "bucket": bucket,
                    "paper_forum": paper_forum,
                }

                dump_jsonl_line(handles[mode][bucket], dpo_sample)
                dump_jsonl_line(handles[mode]["all"], dpo_sample)
                total_pairs[mode][bucket] += 1

            if idx % 100 == 0:
                print(
                    f"[PROGRESS] {idx}/{len(raw_files)} | "
                    f"Current mode: {mode} | "
                    f"Train(L/M/S)={total_pairs['train']['lenient']}/{total_pairs['train']['moderate']}/{total_pairs['train']['strict']} | "
                    f"Eval(L/M/S)={total_pairs['eval']['lenient']}/{total_pairs['eval']['moderate']}/{total_pairs['eval']['strict']}"
                )

        print("\n[DONE] DPO 数据构建完成")
        for m in modes:
            print(f"--- {m.upper()} SET ---")
        for b in ("lenient", "moderate", "strict"):
            print(f"  - {b:8s}: {total_pairs[m][b]} 对样本 -> {paths[m][b].name}")

    finally:
        for m in handles:
            for f in handles[m].values():
                try:
                    f.close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()