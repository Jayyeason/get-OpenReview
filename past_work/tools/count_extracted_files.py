#!/usr/bin/env python3
import argparse
import os
import sys

def count_text_files(directory: str, extension: str = ".txt") -> int:
    ext = extension.lower()
    total = 0
    for root, dirs, files in os.walk(directory):
        for name in files:
            if name.lower().endswith(ext):
                total += 1
    return total

def main():
    parser = argparse.ArgumentParser(description="统计目录中的文本文件数量")
    parser.add_argument(
        "--dir",
        default="/remote-home1/bwli/get_open_review/qwen_review/extracted_contents",
        help="要统计的目录路径",
    )
    parser.add_argument(
        "--ext",
        default=".txt",
        help="文件扩展名（默认 .txt）",
    )
    args = parser.parse_args()

    directory = args.dir
    if not os.path.isdir(directory):
        print(f"目录不存在: {directory}", file=sys.stderr)
        sys.exit(1)

    count = count_text_files(directory, args.ext)
    print(f"目录: {directory}")
    print(f"扩展名: {args.ext.lower()}")
    print(f"文件数量: {count}")

if __name__ == "__main__":
    main()