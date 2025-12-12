#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 conversations JSON 中的每篇论文的 result.state 合并写入 AI 评审结果 JSON。

示例：
  python tools/add_result_to_reviews.py \
    --json /remote-home1/bwli/get_open_review/qwen_review/review_conversations_100.json \
    --reviews /remote-home1/bwli/get_open_review/model-service/qwen3-30B-reviews.json \
    --inplace

参数：
  --json     指向 conversations JSON（包含 result.state），必填
  --reviews  指向 AI 评审 JSON（30B 或 8B），默认 qwen3-30B-reviews.json
  --output   输出文件路径；若未指定且未使用 --inplace，则生成 *.with_result.json
  --inplace  直接覆盖输入的评审 JSON 文件
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Tuple


def load_json(path: str) -> Any:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def pick_result(obj: Dict[str, Any]) -> Dict[str, Any]:
    """从 conversations 的条目里提取 result 字段形状，返回 {"state": ...} 或 None。"""
    if not isinstance(obj, dict):
        return None
    res = obj.get('result')
    if isinstance(res, dict) and 'state' in res:
        # 只保留与状态相关的字段
        return {"state": res.get('state')}
    # 可选：从其它字段推断，这里保持简单，如缺失则返回 None
    return None


def resolve_output_path(reviews_path: str, output: str, inplace: bool) -> str:
    if inplace:
        return reviews_path
    if output:
        return output
    base, ext = os.path.splitext(reviews_path)
    if not ext:
        ext = '.json'
    return f"{base}.with_result{ext}"


def merge_result(conversations_path: str, reviews_path: str, output_path: str) -> Tuple[int, int, int]:
    conversations = load_json(conversations_path)
    reviews_data = load_json(reviews_path)

    updated = 0
    missing = 0
    total = 0

    def get_conv_entry(paper_id: str):
        if isinstance(conversations, dict):
            return conversations.get(paper_id)
        # 若 conversations 是列表，尝试线性查找（不推荐，但兼容）
        if isinstance(conversations, list):
            for item in conversations:
                if isinstance(item, dict) and item.get('paper_id') == paper_id:
                    return item
        return None

    # 评审 JSON 顶层通常是 {paper_id: {...}} 映射；也兼容列表
    if isinstance(reviews_data, dict):
        for key, entry in reviews_data.items():
            total += 1
            paper_id = None
            if isinstance(entry, dict):
                paper_id = entry.get('paper_id') or (key if isinstance(key, str) else None)
                conv_entry = get_conv_entry(paper_id) if paper_id else None
                result_obj = pick_result(conv_entry) if conv_entry else None
                if result_obj:
                    entry['result'] = result_obj
                    updated += 1
                else:
                    entry['result'] = {"state": "unknown"}
                    missing += 1
    elif isinstance(reviews_data, list):
        for entry in reviews_data:
            total += 1
            if not isinstance(entry, dict):
                missing += 1
                continue
            paper_id = entry.get('paper_id')
            conv_entry = get_conv_entry(paper_id) if paper_id else None
            result_obj = pick_result(conv_entry) if conv_entry else None
            if result_obj:
                entry['result'] = result_obj
                updated += 1
            else:
                entry['result'] = {"state": "unknown"}
                missing += 1
    else:
        print("不支持的评审 JSON 顶层结构", file=sys.stderr)
        sys.exit(2)

    ensure_dir(output_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(reviews_data, f, ensure_ascii=False, indent=2)

    return total, updated, missing


def main():
    parser = argparse.ArgumentParser(description="将 result.state 合并到 AI 评审 JSON")
    parser.add_argument(
        "--json",
        default="/remote-home1/bwli/get_open_review/output/structured_review_conversations.json",
        help="conversations JSON 路径（包含 result.state）",
    )
    parser.add_argument(
        "--reviews",
        default="/remote-home1/bwli/get_open_review/model-service/qwen3-30B-reviews.json",
        help="AI 评审 JSON 路径（30B 或 8B）",
    )
    parser.add_argument(
        "--output",
        default="",
        help="输出文件路径；未指定且未 --inplace 时生成 *.with_result.json",
    )
    parser.add_argument(
        "--inplace",
        action="store_true",
        help="覆盖写入到 --reviews 指定的文件",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.json):
        print(f"conversations JSON 不存在: {args.json}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.reviews):
        print(f"评审 JSON 不存在: {args.reviews}", file=sys.stderr)
        sys.exit(1)

    output_path = resolve_output_path(args.reviews, args.output, args.inplace)
    total, updated, missing = merge_result(args.json, args.reviews, output_path)

    print("合并完成：")
    print(f"  conversations: {args.json}")
    print(f"  reviews:       {args.reviews}")
    print(f"  输出文件:       {output_path}")
    print(f"  总论文数:       {total}")
    print(f"  更新成功:       {updated}")
    print(f"  缺失标注:       {missing} (写入 'unknown')")


if __name__ == "__main__":
    main()