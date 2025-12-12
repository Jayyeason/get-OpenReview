#!/usr/bin/env python3
"""
将 iclr2025_ds_judge_strictness 数据转换为新的审稿格式

转换规则:
- forum -> paper_forum
- number -> paper_number
- title -> paper_title
- official_review (dict) -> official_reviews (list)
- 每个审稿人评论中:
  - deepseek_judge_strictness 提升到顶层
  - reviewer_id 从 Reviewer_XXX 提取为 XXX，或根据规则设置
  - content -> review，并扁平化 {"value": ...} 结构
"""

import os
import json
import argparse
from typing import Dict, Any, List, Optional


def flatten_content(content: Dict[str, Any], include_optional_fields: bool = False) -> Dict[str, Any]:
    """
    将 content 字段中的嵌套结构扁平化
    
    例如:
    {"summary": {"value": "..."}} -> {"summary": "..."}
    {"rating": {"value": 6}} -> {"rating": 6}
    
    Args:
        content: 原始 content 字典
        include_optional_fields: 是否包含可选字段（flag_for_ethics_review, code_of_conduct等）
    """
    flattened = {}
    
    # 核心字段（始终包含）
    core_fields = [
        "summary", "strengths", "weaknesses", "questions",
        "rating", "confidence", "soundness", "presentation", "contribution"
    ]
    
    # 可选字段
    optional_fields = [
        "flag_for_ethics_review", "code_of_conduct", "details_of_ethics_concerns"
    ]
    
    fields_to_flatten = core_fields
    if include_optional_fields:
        fields_to_flatten = core_fields + optional_fields
    
    for field in fields_to_flatten:
        if field in content:
            field_value = content[field]
            # 如果是字典且包含 "value" 键，提取 value
            if isinstance(field_value, dict) and "value" in field_value:
                flattened[field] = field_value["value"]
            else:
                flattened[field] = field_value
    
    return flattened


def convert_review(
    reviewer_key: str, 
    review_data: Dict[str, Any],
    include_optional_fields: bool = False
) -> Optional[Dict[str, Any]]:
    """
    转换单个审稿人评论
    
    Args:
        reviewer_key: 审稿人键，如 "Reviewer_YeXr"
        review_data: 审稿人数据字典
        include_optional_fields: 是否包含可选字段
    
    Returns:
        转换后的审稿人评论字典，如果数据无效则返回 None
    """
    # 提取 deepseek_judge_strictness
    strictness = review_data.get("deepseek_judge_strictness", "moderate")
    
    # 提取 content
    content = review_data.get("content")
    if not isinstance(content, dict):
        return None
    
    # 扁平化 content
    review = flatten_content(content, include_optional_fields=include_optional_fields)
    
    # 提取 reviewer_id
    reviewer_id = reviewer_key
    
    return {
        "deepseek_judge_strictness": strictness,
        "reviewer_id": reviewer_id,
        "review": review
    }


def convert_paper(
    paper_data: Dict[str, Any],
    include_optional_fields: bool = False
) -> Dict[str, Any]:
    """
    转换单篇论文数据
    
    Args:
        paper_data: 原始论文数据字典
        include_optional_fields: 是否包含可选字段
    
    Returns:
        转换后的论文数据字典
    """
    # 转换顶层字段
    converted = {
        "paper_forum": paper_data.get("forum", ""),
        "paper_number": paper_data.get("number", 0),
        "paper_title": paper_data.get("title", ""),
        "official_reviews": []
    }
    
    # 转换审稿人评论
    official_review = paper_data.get("official_review", {})
    if isinstance(official_review, dict):
        for reviewer_key, review_data in official_review.items():
            converted_review = convert_review(
                reviewer_key, 
                review_data,
                include_optional_fields=include_optional_fields
            )
            if converted_review:
                converted["official_reviews"].append(converted_review)
    
    return converted


def process_directory(
    input_dir: str,
    output_dir: str,
    overwrite: bool = False,
    include_optional_fields: bool = False
) -> tuple[int, int, int]:
    """
    处理整个目录的数据转换
    
    Args:
        input_dir: 输入目录路径
        output_dir: 输出目录路径
        overwrite: 是否覆盖已存在的文件
        include_optional_fields: 是否包含可选字段
    
    Returns:
        (成功数, 跳过数, 错误数)
    """
    os.makedirs(output_dir, exist_ok=True)
    
    json_files = [f for f in os.listdir(input_dir) if f.endswith(".json")]
    total = len(json_files)
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for i, filename in enumerate(sorted(json_files), 1):
        input_path = os.path.join(input_dir, filename)
        output_path = os.path.join(output_dir, filename)
        
        # 检查是否已存在
        if not overwrite and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            skip_count += 1
            print(f"[{i}/{total}] SKIP: {filename} (已存在)")
            continue
        
        try:
            # 读取原始数据
            with open(input_path, "r", encoding="utf-8") as f:
                paper_data = json.load(f)
            
            # 转换数据
            converted_data = convert_paper(
                paper_data,
                include_optional_fields=include_optional_fields
            )
            
            # 保存转换后的数据
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(converted_data, f, ensure_ascii=False, indent=2)
            
            success_count += 1
            review_count = len(converted_data.get("official_reviews", []))
            print(f"[{i}/{total}] OK: {filename} ({review_count} reviews)")
            
        except Exception as e:
            error_count += 1
            print(f"[{i}/{total}] ERROR: {filename} - {str(e)}")
    
    return success_count, skip_count, error_count


def main():
    parser = argparse.ArgumentParser(
        description="将 ICLR 2025 审稿数据转换为新的审稿格式"
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        default="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/iclr2025_ds_judge_strictness",
        help="输入目录，包含原始 JSON 文件"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/iclr2025_ds_form",
        help="输出目录，保存转换后的 JSON 文件"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已存在的输出文件"
    )
    parser.add_argument(
        "--include-optional-fields",
        action="store_true",
        help="包含可选字段（flag_for_ethics_review, code_of_conduct等）"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("ICLR 2025 审稿数据格式转换")
    print("=" * 70)
    print(f"输入目录: {args.input_dir}")
    print(f"输出目录: {args.output_dir}")
    print(f"覆盖模式: {args.overwrite}")
    print(f"包含可选字段: {args.include_optional_fields}")
    print("=" * 70)
    
    success, skip, error = process_directory(
        args.input_dir,
        args.output_dir,
        args.overwrite,
        include_optional_fields=args.include_optional_fields
    )
    
    print("=" * 70)
    print("转换完成!")
    print(f"成功: {success}")
    print(f"跳过: {skip}")
    print(f"错误: {error}")
    print(f"总计: {success + skip + error}")
    print("=" * 70)


if __name__ == "__main__":
    main()

