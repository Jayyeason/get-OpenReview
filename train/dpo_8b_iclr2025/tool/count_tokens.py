#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计 DPO 数据集中 Prompt+Chosen 和 Prompt+Rejected 的 Token 数量。
使用 Qwen Tokenizer。
"""

import argparse
import json
import numpy as np
from pathlib import Path
from transformers import AutoTokenizer
from typing import List, Dict
import sys

def load_jsonl(path: str) -> List[Dict]:
    data = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def get_stats(tokens: List[int], name: str):
    if not tokens:
        print(f"No data for {name}")
        return
    
    arr = np.array(tokens)
    print(f"--- {name} ---")
    print(f"  Count: {len(arr)}")
    print(f"  Mean : {np.mean(arr):.2f}")
    print(f"  Min  : {np.min(arr)}")
    print(f"  Max  : {np.max(arr)}")
    print(f"  P50  : {np.percentile(arr, 50):.2f}")
    print(f"  P90  : {np.percentile(arr, 90):.2f}")
    print(f"  P95  : {np.percentile(arr, 95):.2f}")
    print(f"  P99  : {np.percentile(arr, 99):.2f}")
    print("-" * 30)

def process_file(file_path: str, tokenizer):
    print(f"\n[INFO] Processing file: {file_path}")
    if not Path(file_path).exists():
        print(f"[ERROR] File not found: {file_path}")
        return

    data = load_jsonl(file_path)
    print(f"[INFO] Loaded {len(data)} lines.")

    prompt_chosen_lens = []
    prompt_rejected_lens = []

    for i, item in enumerate(data):
        if i % 500 == 0:
            sys.stdout.write(f"\rProcessed {i}/{len(data)}")
            sys.stdout.flush()

        prompt = item.get('prompt', '')
        chosen = item.get('chosen', '')
        rejected = item.get('rejected', '')

        # 拼接文本，模拟模型输入的格式
        # 注意：这里简单的拼接，实际训练时可能会有特殊的 chat template
        # 为了估算长度，通常直接拼接即可，或者使用 apply_chat_template
        
        # 这里假设是 DPO 格式，通常是 system/user prompt + response
        # 为了准确，我们手动拼接一下，或者直接 tokenize(prompt + chosen)
        
        text_chosen = prompt + chosen
        text_rejected = prompt + rejected

        len_chosen = len(tokenizer.encode(text_chosen))
        len_rejected = len(tokenizer.encode(text_rejected))

        prompt_chosen_lens.append(len_chosen)
        prompt_rejected_lens.append(len_rejected)

    print(f"\rProcessed {len(data)}/{len(data)}")
    
    get_stats(prompt_chosen_lens, "Prompt + Chosen Lengths")
    get_stats(prompt_rejected_lens, "Prompt + Rejected Lengths")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", required=True, help="Paths to jsonl files")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-7B-Instruct", help="Tokenizer model name or path")
    args = parser.parse_args()

    print(f"[INFO] Loading tokenizer: {args.model}")
    try:
        tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    except Exception as e:
        print(f"[ERROR] Failed to load tokenizer: {e}")
        return

    for f in args.files:
        process_file(f, tokenizer)

if __name__ == "__main__":
    main()


