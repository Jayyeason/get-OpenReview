#!/usr/bin/env python3
"""
根据目录中的文件名（forumid）筛选 structured_review_conversations.json 并输出到
qwen_review/review_conversations_{N}.json（N为匹配到的forum数）。目录输入通过 --dir。
"""

import json
import os
import argparse
from typing import Set

DEFAULT_DIR = "/remote-home1/bwli/get_open_review/qwen_review/extracted_contents"
DEFAULT_INPUT = "/remote-home1/bwli/get_open_review/output/structured_review_conversations.json"
DEFAULT_OUTDIR = "/remote-home1/bwli/get_open_review/qwen_review"

def collect_forum_ids_from_dir(dir_path: str) -> Set[str]:
    ids: Set[str] = set()
    if not os.path.isdir(dir_path):
        raise FileNotFoundError(f"目录不存在: {dir_path}")
    for name in os.listdir(dir_path):
        full = os.path.join(dir_path, name)
        if os.path.isdir(full):
            continue
        base, ext = os.path.splitext(name)
        if not base:
            continue
        # 仅收集常见文本文件名；若无扩展名也接受
        if ext.lower() in (".txt", ""):
            ids.add(base)
    return ids

def extract_by_dir(dir_path: str, input_file: str = DEFAULT_INPUT, output_dir: str = DEFAULT_OUTDIR):
    forum_ids = collect_forum_ids_from_dir(dir_path)
    print(f"目录 {dir_path} 中共识别 forumid 数: {len(forum_ids)}")

    print(f"正在读取结构化文件: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("输入JSON顶层应为字典：forumid -> 记录")

    keys = set(data.keys())
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
    print(f"- 输入目录 forumid 总数: {len(forum_ids)}")
    print(f"- 匹配并写入条目数: {len(selected)}")
    print(f"- 未匹配条目数: {len(missing)}")

def main():
    parser = argparse.ArgumentParser(description='根据目录中文件名（forumid）筛选structured_review_conversations.json并输出')
    parser.add_argument('--dir', default=DEFAULT_DIR, help='包含以forumid命名文件的目录路径（默认: qwen_review/extracted_contents）')
    parser.add_argument('--input', default=DEFAULT_INPUT, help='结构化输入JSON路径（默认: output/structured_review_conversations.json）')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR, help='输出目录（默认: qwen_review）')

    args = parser.parse_args()
    dir_path = args.dir or DEFAULT_DIR
    extract_by_dir(dir_path, input_file=args.input, output_dir=args.outdir)

if __name__ == "__main__":
    main()