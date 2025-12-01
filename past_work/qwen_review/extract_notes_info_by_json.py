#!/usr/bin/env python3
"""
从指定 JSON 文件（--json）中提取 forumid（按顶层键），
在 structured_review_conversations.json 中筛选对应数据，
并输出为 qwen_review/review_conversations_{N}.json（N为匹配条数）。

参考 extract_notes_info_by_extracted.py 的参数风格与输出格式。
"""

import json
import os
import argparse
from typing import Set

DEFAULT_JSON = \
    "/remote-home1/bwli/get_open_review/model-service/qwen3-30B-reviews.json"
DEFAULT_INPUT = \
    "/remote-home1/bwli/get_open_review/output/structured_review_conversations.json"
DEFAULT_OUTDIR = \
    "/remote-home1/bwli/get_open_review/qwen_review"


def collect_forum_ids_from_json(json_path: str) -> Set[str]:
    """从 JSON 顶层键收集 forumid。顶层必须为字典。"""
    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"JSON 文件不存在: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("输入 JSON 顶层应为字典：forumid -> 记录")
    return set(map(str, data.keys()))


def extract_by_json(json_path: str, input_file: str = DEFAULT_INPUT, output_dir: str = DEFAULT_OUTDIR):
    forum_ids = collect_forum_ids_from_json(json_path)
    print(f"来源 JSON {json_path} 顶层 forumid 数: {len(forum_ids)}")

    print(f"正在读取结构化文件: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("结构化输入 JSON 顶层应为字典：forumid -> 记录")

    keys = set(map(str, data.keys()))
    matched = forum_ids & keys
    missing = forum_ids - keys

    print(f"可匹配 forumid 数: {len(matched)}")
    if missing:
        print(f"未在结构化文件中找到的 forumid 数: {len(missing)}")

    selected = {fid: data[fid] for fid in matched}

    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"review_conversations_{len(selected)}.json")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)

    print(f"已保存筛选结果到: {output_file}")
    print("\n统计信息:")
    print(f"- 来源 JSON forumid 总数: {len(forum_ids)}")
    print(f"- 匹配并写入条目数: {len(selected)}")
    print(f"- 未匹配条目数: {len(missing)}")


def main():
    parser = argparse.ArgumentParser(
        description='根据 JSON 顶层键（forumid）筛选 structured_review_conversations.json 并输出')
    parser.add_argument('--json', default=DEFAULT_JSON,
                        help='包含论坛 ID 的 JSON（默认: model-service/qwen3-30B-re.json）')
    parser.add_argument('--input', default=DEFAULT_INPUT,
                        help='结构化输入 JSON 路径（默认: output/structured_review_conversations.json）')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
                        help='输出目录（默认: qwen_review）')

    args = parser.parse_args()
    json_path = args.json or DEFAULT_JSON
    extract_by_json(json_path, input_file=args.input, output_dir=args.outdir)


if __name__ == "__main__":
    main()