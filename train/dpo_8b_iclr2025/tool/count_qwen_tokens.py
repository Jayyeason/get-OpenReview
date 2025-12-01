#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Optional, Dict, Any
import sys

from transformers import AutoTokenizer


def load_tokenizer(path: Optional[str]) -> Any:
    candidates = []
    if path:
        candidates.append(path)
    candidates.extend([
        "/remote-home1/share/models/Qwen/Qwen3-8B",
        "Qwen/Qwen3-8B",
    ])
    last_err = None
    for p in candidates:
        try:
            return AutoTokenizer.from_pretrained(p, trust_remote_code=True)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Failed to load Qwen tokenizer. Provide --tokenizer. Last error: {last_err}")


def process_file(file_path: Path, tokenizer: Any, limit: Optional[int], threshold: int) -> Dict[str, Any]:
    total_pc = 0
    total_pr = 0
    count = 0
    missing = 0
    exceed_pc = 0
    exceed_pr = 0
    exceed_any = 0
    total_lines = None
    if not limit:
        try:
            with file_path.open("r", encoding="utf-8") as f2:
                total_lines = sum(1 for _ in f2)
        except Exception:
            total_lines = None
    with file_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if limit and count >= limit:
                break
            line = line.strip()
            if not line:
                if total_lines is not None and (i == 1 or i % 200 == 0 or i == total_lines):
                    ratio = i / total_lines if total_lines else 1
                    bar_len = 30
                    filled = int(bar_len * ratio)
                    bar = "#" * filled + "-" * (bar_len - filled)
                    sys.stdout.write(f"\r[{i}/{total_lines}] |{bar}| {int(ratio*100)}%")
                    sys.stdout.flush()
                elif total_lines is None and (i == 1 or i % 200 == 0):
                    sys.stdout.write(f"\r{file_path.name}: lines {i}, samples {count}, missing {missing}")
                    sys.stdout.flush()
                continue
            try:
                obj = json.loads(line)
            except Exception:
                if total_lines is not None and (i == 1 or i % 200 == 0 or i == total_lines):
                    ratio = i / total_lines if total_lines else 1
                    bar_len = 30
                    filled = int(bar_len * ratio)
                    bar = "#" * filled + "-" * (bar_len - filled)
                    sys.stdout.write(f"\r[{i}/{total_lines}] |{bar}| {int(ratio*100)}%")
                    sys.stdout.flush()
                elif total_lines is None and (i == 1 or i % 200 == 0):
                    sys.stdout.write(f"\r{file_path.name}: lines {i}, samples {count}, missing {missing}")
                    sys.stdout.flush()
                continue
            prompt = obj.get("prompt", "")
            chosen = obj.get("chosen")
            rejected = obj.get("rejected")
            if chosen is None or rejected is None:
                missing += 1
                if total_lines is not None and (i == 1 or i % 200 == 0 or i == total_lines):
                    ratio = i / total_lines if total_lines else 1
                    bar_len = 30
                    filled = int(bar_len * ratio)
                    bar = "#" * filled + "-" * (bar_len - filled)
                    sys.stdout.write(f"\r[{i}/{total_lines}] |{bar}| {int(ratio*100)}%")
                    sys.stdout.flush()
                elif total_lines is None and (i == 1 or i % 200 == 0):
                    sys.stdout.write(f"\r{file_path.name}: lines {i}, samples {count}, missing {missing}")
                    sys.stdout.flush()
                continue
            text_c = f"{prompt}{chosen}"
            text_r = f"{prompt}{rejected}"
            try:
                tokens_c = tokenizer.encode(text_c, add_special_tokens=False)
                tokens_r = tokenizer.encode(text_r, add_special_tokens=False)
            except Exception:
                tokens_c = tokenizer(text_c, add_special_tokens=False).get("input_ids", [])
                tokens_r = tokenizer(text_r, add_special_tokens=False).get("input_ids", [])
            total_pc += len(tokens_c)
            total_pr += len(tokens_r)
            count += 1
            if len(tokens_c) > threshold:
                exceed_pc += 1
            if len(tokens_r) > threshold:
                exceed_pr += 1
            if len(tokens_c) > threshold or len(tokens_r) > threshold:
                exceed_any += 1
            if total_lines is not None and (i == 1 or i % 200 == 0 or i == total_lines):
                ratio = i / total_lines if total_lines else 1
                bar_len = 30
                filled = int(bar_len * ratio)
                bar = "#" * filled + "-" * (bar_len - filled)
                sys.stdout.write(f"\r[{i}/{total_lines}] |{bar}| {int(ratio*100)}%")
                sys.stdout.flush()
            elif total_lines is None and (i == 1 or i % 200 == 0):
                sys.stdout.write(f"\r{file_path.name}: lines {i}, samples {count}, missing {missing}")
                sys.stdout.flush()
    if total_lines is not None:
        sys.stdout.write("\n")
    avg_pc = (total_pc / count) if count else 0.0
    avg_pr = (total_pr / count) if count else 0.0
    return {
        "file": str(file_path),
        "samples": count,
        "missing": missing,
        "prompt_plus_chosen_total_tokens": total_pc,
        "prompt_plus_rejected_total_tokens": total_pr,
        "prompt_plus_chosen_avg_tokens": avg_pc,
        "prompt_plus_rejected_avg_tokens": avg_pr,
        "threshold": threshold,
        "prompt_plus_chosen_exceed_threshold": exceed_pc,
        "prompt_plus_rejected_exceed_threshold": exceed_pr,
        "either_pair_exceed_threshold": exceed_any,
    }


def main():
    parser = argparse.ArgumentParser(description="统计 DPO 数据集中 prompt+chosen 与 prompt+rejected 的 Qwen tokenizer token 数")
    parser.add_argument(
        "--files",
        nargs="+",
        default=[
            "/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/dpo_data_8k/eval_iclr_dpo_all.jsonl",
            "/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/dpo_data_8k/train_iclr_dpo_all.jsonl",
        ],
        help="待统计的 JSONL 文件路径列表",
    )
    parser.add_argument("--tokenizer", default="", help="Qwen tokenizer 路径或名称；可留空使用默认候选")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 行用于快速验证；0 表示处理全部")
    parser.add_argument("--threshold", type=int, default=8192, help="超过该 token 数的样本会计数")
    args = parser.parse_args()

    tok = load_tokenizer(args.tokenizer or None)
    lim = args.limit if args.limit and args.limit > 0 else None

    results = []
    for fp in args.files:
        p = Path(fp)
        if not p.exists():
            print(json.dumps({"file": str(p), "error": "not_found"}, ensure_ascii=False))
            continue
        res = process_file(p, tok, lim, args.threshold)
        print(json.dumps(res, ensure_ascii=False))
        results.append(res)


if __name__ == "__main__":
    main()
