#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 forumid 读取大 JSON 的 abstract 字段，调用 Qwen3-30B-A3B 模型生成评审与评分。

特点：
- 从目录 /qwen_review/extracted_contents 读取所有文件名作为 forumid
- 在 output/all_notes_readable.json 中查找对应 abstract（使用 jq 优先，失败则回退到 Python 解析）
- 默认生成 1 位严格度为 3 的评审，支持通过命令行指定严格度计划（例如 "2,3,4"）
- 支持断点续跑与并发处理
"""

import json
import argparse
import sys
import re
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

import openai
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================ Prompt 模板 ============================= #

BASE_REVIEW_TASK = """
## Your Review Task

### Role: The Strict, Precise & Insightful Academic Reviewer
You are a seasoned reviewer renowned for strict scrutiny, precision, and insight. You uphold the highest academic standards. Your primary mission is **strict scrutiny** to ensure that only high-quality research is advanced. You relentlessly identify core deficiencies and logical leaks, and your feedback must be **specific, clear, and executable**. Your goal is to drive authors toward fundamental improvements that meet the highest submission standards.

### Input Constraint
You are provided **only the paper abstract**. Base all judgments strictly on the abstract. **Do not speculate** about datasets, experiments, proofs, or results that are not explicitly stated. If information is missing, call it out as a limitation, reflect it in weaknesses, and set an appropriately **lower confidence**.

1. **Summary**: A brief summary of the paper's main contributions and approach (2-3 sentences).

2. **Strengths**: A substantive assessment of the strengths of the paper, touching on each of the following dimensions: originality, quality, clarity, and significance. Be broad in definitions of originality (new definitions, problem formulations, creative combinations, new domains, or removing limitations from prior results).

3. **Weaknesses**: A substantive assessment of the weaknesses of the paper. Focus on constructive and actionable insights on how the work could improve towards its stated goals. Be specific and avoid generic remarks. If you believe the contribution lacks novelty, provide references and explanations; if experiments are insufficient, explain why and exactly what is missing.

4. **Questions**: List up and carefully describe any questions and suggestions for the authors. Think of things where a response from the author can change your opinion, clarify a confusion, or address a limitation. This is important for a productive rebuttal and discussion phase.

5. **Soundness** (1-4): Rate the paper's soundness. Are the central claims adequately supported with evidence? Are the experimental setup and research methodology sound?
   - 1: Poor
   - 2: Fair
   - 3: Clear and structured
   - 4: Excellent

6. **Presentation** (1-4): Rate the quality of presentation. This should take into account the writing style and clarity, presentation of figures and diagrams, as well as contextualization relative to prior work.
   - 1: Poor
   - 2: Fair
   - 3: Good
   - 4: Excellent

7. **Contribution** (1-4): Rate the quality of the overall contribution this paper makes to the research area being studied. Are the questions being asked important? Does the paper bring significant originality of ideas and/or execution? Are the results valuable to share with the broader ICLR community?
   - 1: Poor
   - 2: Fair
   - 3: Good
   - 4: Excellent

8. **Rating** (1, 3, 5, 6, 8, 10): Provide an overall score for this submission:
   - 1: Strong reject
   - 3: Reject, not good enough
   - 5: Marginally below the acceptance threshold
   - 6: Marginally above the acceptance threshold
   - 8: Accept, good paper
   - 10: Strong accept, should be highlighted at the conference

9. **Confidence** (1-5): Provide a confidence score for your assessment:
   - 1: Unable to assess this paper, need opinion from different reviewers
   - 2: Willing to defend assessment, but quite likely did not understand central parts or unfamiliar with related work
   - 3: Fairly confident in assessment. Possible that did not understand some parts or unfamiliar with some related work
   - 4: Confident in assessment, but not absolutely certain. Unlikely but not impossible that did not understand some parts
   - 5: Absolutely certain about assessment. Very familiar with related work and checked details carefully

## Output Format

You must respond with a JSON object in the following format:
```json
{
  "summary": "...",
  "strengths": "...",
  "weaknesses": "...",
  "questions": "...",
  "rating": <1, 3, 5, 6, 8, or 10>,
  "confidence": <1-5>,
  "soundness": <1-4>,
  "presentation": <1-4>,
  "contribution": <1-4>
}
```

**Important**:
- `rating` must be one of: 1, 3, 5, 6, 8, 10
- `confidence`, `soundness`, `presentation`, `contribution` must be integers in their respective ranges

You may use <think> tags to organize your thoughts before providing the JSON response. The final JSON object should come after your reasoning."""

SYSTEM_PROMPT_LEVEL_1 = """You are an expert academic reviewer for a top-tier machine learning conference (ICLR).

## Your Reviewer Profile
**You are a Level 1 Encouraging Reviewer**

- **Philosophy**: You believe in nurturing innovation and giving researchers opportunities to develop ideas.
- **What you value most**: Novelty, creativity, potential impact, and fresh perspectives.
- **How you view flaws**: Minor issues are acceptable if the core idea is interesting. Limitations are seen as future work opportunities.
- **Your threshold for acceptance**: Does this paper bring something interesting to the community? If yes, you support its publication.
- **How you write weaknesses**: You frame issues constructively as "suggestions for improvement" rather than dealbreakers.
- **Typical ratings**: You commonly give 8 (good papers with novelty) or 10 (excellent innovative work).

""" + BASE_REVIEW_TASK

SYSTEM_PROMPT_LEVEL_2 = """You are an expert academic reviewer for a top-tier machine learning conference (ICLR).

## Your Reviewer Profile
**You are a Level 2 Supportive Reviewer**

- **Philosophy**: You appreciate solid scientific work and want to help good research get published.
- **What you value most**: Sound methodology, clear contributions, and well-executed experiments.
- **How you view flaws**: You acknowledge limitations but weigh them against the overall contribution.
- **Your threshold for acceptance**: Is this a solid piece of work that advances the field? You give borderline papers the benefit of doubt.
- **How you write weaknesses**: You point out concerns but emphasize the paper's merits.
- **Typical ratings**: You commonly give 6 (marginally acceptable) or 8 (solid accept).

""" + BASE_REVIEW_TASK

SYSTEM_PROMPT_LEVEL_3 = """You are an expert academic reviewer for a top-tier machine learning conference (ICLR).

## Your Reviewer Profile
**You are a Level 3 Objective Reviewer**

- **Philosophy**: You apply standard conference criteria fairly and consistently.
- **What you value most**: Balance between novelty, soundness, clarity, and significance.
- **How you view flaws**: Issues are noted objectively; significant problems affect your rating proportionally.
- **Your threshold for acceptance**: Does this paper meet the expected quality bar for ICLR?
- **How you write weaknesses**: You provide balanced critique with both strengths and weaknesses carrying equal weight.
- **Typical ratings**: You commonly give 5 (marginally below threshold) or 6 (marginally above threshold).

""" + BASE_REVIEW_TASK

SYSTEM_PROMPT_LEVEL_4 = """You are an expert academic reviewer for a top-tier machine learning conference (ICLR).

## Your Reviewer Profile
**You are a Level 4 Rigorous Reviewer**

- **Philosophy**: You hold papers to high standards because ICLR should showcase strong research.
- **What you value most**: Rigorous experimental validation, strong baselines, thorough analysis, and clear novelty over prior work.
- **How you view flaws**: Even small issues raise concerns. You need convincing evidence for all claims.
- **Your threshold for acceptance**: Only clear, well-executed contributions with strong empirical support should be accepted.
- **How you write weaknesses**: You identify issues in depth and question claims that lack sufficient support.
- **Typical ratings**: You commonly give 3 (reject, not good enough) or 5 (marginally below threshold).

""" + BASE_REVIEW_TASK

SYSTEM_PROMPT_LEVEL_5 = """You are an expert academic reviewer for a top-tier machine learning conference (ICLR).

## Your Reviewer Profile
**You are a Level 5 Highly Critical Reviewer**

- **Philosophy**: ICLR is a top venue; only exceptional work should be published.
- **What you value most**: Groundbreaking ideas, flawless execution, comprehensive experiments, and significant impact.
- **How you view flaws**: You scrutinize every detail. Missing baselines, incomplete experiments, or unclear novelty are major concerns.
- **Your threshold for acceptance**: This paper must be exceptional - truly advancing the field with rigorous validation.
- **How you write weaknesses**: You point out all limitations, gaps, and areas where the paper falls short of the highest standards.
- **Typical ratings**: You commonly give 1 (strong reject) or 3 (reject, not good enough).

""" + BASE_REVIEW_TASK

SYSTEM_PROMPTS = {
    1: SYSTEM_PROMPT_LEVEL_1,
    2: SYSTEM_PROMPT_LEVEL_2,
    3: SYSTEM_PROMPT_LEVEL_3,
    4: SYSTEM_PROMPT_LEVEL_4,
    5: SYSTEM_PROMPT_LEVEL_5,
}

USER_PROMPT_TEMPLATE = """## Paper Abstract (only input)

{paper_abstract}

## Constraints
- **Strictly abstract-only**: Base your review solely on the abstract provided. You do not have access to the full paper, methods, experiments, datasets, or detailed results.
- **No speculation**: Do not assume or infer information that is not explicitly stated in the abstract. This includes:
  - Specific experimental setups, datasets, or baselines
  - Detailed methodology or implementation details
  - Quantitative results, performance metrics, or statistical significance
  - Proofs, theoretical guarantees, or technical details
  - Related work comparisons beyond what is mentioned
- **Missing information as weakness**: If key information is missing from the abstract (e.g., no mention of experiments, unclear methodology, vague contributions), explicitly identify these gaps in the weaknesses section.
- **Confidence calibration**: Set your confidence score (1-5) appropriately:
  - Lower confidence (2-3) is typical for abstract-only reviews, as many details are unavailable
  - Only use higher confidence (4-5) if the abstract is unusually detailed and comprehensive
  - If the abstract lacks critical information, use confidence 2 or lower
- **Rating adjustment**: Avoid high ratings (8-10) if the abstract lacks sufficient detail to assess the work's quality. Missing experimental validation or unclear contributions should lower the rating.
- **Focus on what's stated**: Evaluate the abstract's clarity, stated contributions, problem formulation, and potential significance based only on what is explicitly written.
"""


class ReviewerAI:
    def __init__(
        self,
        base_url: str = "http://10.176.59.108:8003/v1",
        model_name: str = "qwen3-30b-a3b",
    ):
        self.client = openai.OpenAI(api_key="EMPTY", base_url=base_url)
        self.model_name = model_name
        self.system_prompts = SYSTEM_PROMPTS

    def build_review_prompt(self, paper_abstract: str, max_content_length: int = 4000) -> str:
        if len(paper_abstract) > max_content_length:
            paper_abstract = paper_abstract[:max_content_length] + "\n\n[摘要已截断...]"
        return USER_PROMPT_TEMPLATE.format(paper_abstract=paper_abstract)

    def generate_review(
        self,
        paper_abstract: str,
        strictness: int = 3,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        prompt = self.build_review_prompt(paper_abstract)
        try:
            system_prompt = self.system_prompts.get(strictness, self.system_prompts[3])
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            content = content.strip()

            # 去除 <think> 段
            if '<think>' in content.lower():
                think_patterns = ['</think>', '</Think>', '</THINK>']
                for pattern in think_patterns:
                    if pattern.lower() in content.lower():
                        idx = content.lower().find(pattern.lower())
                        if idx != -1:
                            content = content[idx + len(pattern):].strip()
                            break
                else:
                    json_start = content.find('{')
                    if json_start != -1:
                        content = content[json_start:]

            # 去除 markdown 代码块
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # 若开头仍有杂质，定位到第一个 {
            if not content.startswith('{'):
                json_start = content.find('{')
                if json_start != -1:
                    content = content[json_start:]

            # 修复无效转义
            def fix_escape(match):
                char = match.group(1)
                if char in ['"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u']:
                    return match.group(0)
                else:
                    return '\\\\' + char
            content = re.sub(r'\\(.)', fix_escape, content)

            review_data = json.loads(content)
            return review_data

        except json.JSONDecodeError as e:
            # 保存原始响应内容的前500字符用于调试
            error_context = ""
            if 'content' in locals():
                error_pos = getattr(e, 'pos', None)
                if error_pos:
                    start = max(0, error_pos - 100)
                    end = min(len(content), error_pos + 100)
                    error_context = f"\n错误位置附近内容: ...{content[start:end]}..."
                else:
                    error_context = f"\n原始响应前500字符: {content[:500]}"
            
            print(f"  ⚠️  JSON解析失败: {e}")
            if error_context:
                print(f"  {error_context}")
            
            return {
                "summary": f"Failed to parse JSON: {str(e)}",
                "strengths": "",
                "weaknesses": "",
                "questions": "",
                "rating": -1,
                "confidence": -1,
                "soundness": -1,
                "presentation": -1,
                "contribution": -1,
                "error": str(e),
                "raw_content_preview": content[:500] if 'content' in locals() else "N/A",
            }
        except Exception as e:
            return {
                "summary": f"Error: {str(e)}",
                "strengths": "",
                "weaknesses": "",
                "questions": "",
                "rating": -1,
                "confidence": -1,
                "soundness": -1,
                "presentation": -1,
                "contribution": -1,
                "error": str(e),
            }


def format_review_content(review_data: Dict[str, Any]) -> Dict[str, Any]:
    content: Dict[str, Any] = {}
    for key in ['summary', 'strengths', 'weaknesses', 'questions']:
        if key in review_data:
            content[key] = {"value": review_data[key]}
    for key in ['rating', 'confidence', 'soundness', 'presentation', 'contribution']:
        if key in review_data and review_data[key] != -1:
            content[key] = {"value": review_data[key]}
    return content


# 读取extracted_contend文件夹下的论文名称
def list_forum_ids(input_dir: Path, limit: Optional[int] = None) -> List[str]:
    files = sorted(input_dir.glob('*.txt'))
    if limit is not None:
        files = files[:limit]
    return [f.stem for f in files]


def build_forum_abstract_map(all_notes_path: Path, needed_ids: Set[str]) -> Dict[str, str]:
    """构建 forum -> abstract 映射（纯 Python 解析）。
    规则：
    - 仅使用投稿 note（id == forum）
    - 抽取 abstract 候选：abstract / TL;DR / tl;dr / TLDR / paper_abstract / Abstract
    - 仅保留非空摘要，避免空值覆盖
    - 支持两种输入：标准 JSON 数组或 NDJSON 行流
    """
    mapping: Dict[str, str] = {}

    def extract_abstract_variants_from_content(content: Dict[str, Any]) -> Optional[str]:
        if not isinstance(content, dict):
            return None
        candidates = ['abstract', 'Abstract', 'paper_abstract', 'tl;dr', 'TL;DR', 'TLDR']
        for k in candidates:
            v = content.get(k)
            if isinstance(v, dict):
                v = v.get('value')
            if isinstance(v, str):
                v = v.strip()
            if v:
                return v
        return None

    # 读取文件：优先按标准 JSON 数组解析，失败则按 NDJSON 逐行解析
    try:
        with open(all_notes_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                iterable = data if isinstance(data, list) else []
            except json.JSONDecodeError:
                # 可能是 NDJSON，回退到逐行解析
                f.seek(0)
                iterable = []
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        obj = json.loads(s)
                        iterable.append(obj)
                    except Exception:
                        continue
            except MemoryError:
                print('❌ 内存不足，无法加载大 JSON。请减少 needed_ids 或拆分文件。')
                return mapping
    except FileNotFoundError:
        print(f'❌ 文件不存在: {all_notes_path}')
        return mapping

    # 仅提取投稿 note（id == forum），且仅当摘要非空时设置一次
    for item in iterable:
        if not isinstance(item, dict):
            continue
        fid = item.get('forum')
        if not fid or fid not in needed_ids:
            continue
        if item.get('id') != fid:
            continue
        content = item.get('content') or {}
        abstract = extract_abstract_variants_from_content(content) or ''
        if abstract and fid not in mapping:
            mapping[fid] = abstract
    return mapping


def process_single_forum(
    forum_id: str,
    abstract_text: str,
    reviewer_ai: ReviewerAI,
    strictness_levels: List[int],
) -> Dict[str, Any]:
    reviews: List[Dict[str, Any]] = []
    print(f"  摘要长度: {len(abstract_text)}")
    for level in strictness_levels:
        start = time.time()
        review_data = reviewer_ai.generate_review(paper_abstract=abstract_text, strictness=level)
        elapsed = time.time() - start
        formatted = format_review_content(review_data)
        reviews.append({
            'reviewer_id': f'reviewer_{level}',
            'strictness': level,
            'review': formatted,
            'elapsed_sec': round(elapsed, 2),
        })
    return {
        'paper_id': forum_id,
        'source': 'abstract_only',
        'abstract': abstract_text,
        'reviews': reviews,
    }


def main():
    parser = argparse.ArgumentParser(
        description='按 abstract 调用 Qwen3-30B-A3B 生成评审与评分',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''示例：
  python model-service/qwen3-30B-abstract-reviewer.py \
    --input-dir /remote-home1/bwli/get_open_review/qwen_review/extracted_contents \
    --notes-json /remote-home1/bwli/get_open_review/output/all_notes_readable.json \
    --output model-service/qwen3-30B-abstract-reviews.json \
    --strictness-plan 3 --workers 2 --limit 50
'''
    )

    # 默认输出到脚本同目录，避免在不同工作目录下相对路径失效
    default_output_path = str(Path(__file__).resolve().parent / 'qwen3-30B-abstract-reviews.json')
    parser.add_argument('--input-dir', default='/remote-home1/bwli/get_open_review/qwen_review/extracted_contents', help='包含 forumid 的文本文件目录')
    parser.add_argument('--notes-json', default='/remote-home1/bwli/get_open_review/output/all_notes_readable.json', help='包含所有 notes 的大 JSON 文件')
    parser.add_argument('--output', default=default_output_path, help='输出 JSON 文件')
    parser.add_argument('--base-url', default='http://10.176.59.105:8004/v1', help='模型 API Base URL')
    parser.add_argument('--model', default='qwen3-30b-a3b', help='模型名称')
    parser.add_argument('--strictness-plan', default='2,3,4', help='逗号分隔的严格度列表，例如 "2,3,4" 或 "1,2,3,4,5"')
    parser.add_argument('--workers', type=int, default=1, help='并行线程数')
    parser.add_argument('--limit', type=int, default=None, help='只处理前 N 个 forumid')

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    notes_json = Path(args.notes_json)
    output_path = Path(args.output)

    if not input_dir.exists():
        print(f'❌ 输入目录不存在: {input_dir}')
        sys.exit(1)
    if not notes_json.exists():
        print(f'❌ 大 JSON 文件不存在: {notes_json}')
        sys.exit(1)

    # 列出 forumid
    forum_ids = list_forum_ids(input_dir, limit=args.limit)
    print(f'✓ 待处理 forumid 数量: {len(forum_ids)}')

    # 断点续跑加载
    results: Dict[str, Any] = {}
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                results = existing
                print(f'↻ 载入已有结果：{len(results)} 条，用于续跑')
        except Exception as e:
            print(f'⚠️  读取已有输出失败，忽略续跑数据: {e}')

    # 需要的 id 集合（过滤已完成）
    def needs_work(fid: str, strictness_levels: List[int]) -> bool:
        entry = results.get(fid)
        if not entry:
            return True
        reviews = entry.get('reviews', [])
        done_levels = {r.get('strictness') for r in reviews if isinstance(r.get('strictness'), int)}
        for lv in strictness_levels:
            if lv not in done_levels:
                return True
        return False

    strictness_levels = [int(x) for x in args.strictness_plan.split(',') if x.strip()]
    print(f'使用严格度计划: {strictness_levels}')
    todo_ids = [fid for fid in forum_ids if needs_work(fid, strictness_levels)]
    print(f'✓ 需要生成的条目: {len(todo_ids)}')

    # 建立 forum -> abstract 映射（包含待处理与已有结果两部分，便于补齐已有项的摘要）
    existing_ids: Set[str] = set(results.keys())
    needed_set: Set[str] = set(todo_ids) | existing_ids
    forum_to_abstract = build_forum_abstract_map(notes_json, needed_set)
    missing = needed_set - set(forum_to_abstract.keys())
    if missing:
        print(f'⚠️  有 {len(missing)} 个 forumid 未在大 JSON 中找到摘要（将输出空摘要）。')

    # 先为已有结果补齐摘要字段（不触发重新评审）
    patched_existing = 0
    if existing_ids:
        for fid in existing_ids:
            entry = results.get(fid) or {}
            if not entry.get('abstract'):
                abs_text = forum_to_abstract.get(fid, '')
                if abs_text:
                    entry['abstract'] = abs_text
                    results[fid] = entry
                    patched_existing += 1
        if patched_existing:
            save_results(results, output_path)
            print(f'↻ 已为 {patched_existing} 条既有结果补齐摘要字段')

    # 初始化评审 AI
    reviewer_ai = ReviewerAI(base_url=args.base_url, model_name=args.model)

    def save_results(results_dict: Dict[str, Any], path: Path):
        # 确保输出目录存在
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(results_dict, f, ensure_ascii=False, indent=2)

    # 任务生成
    tasks: List[str] = todo_ids

    if args.workers == 1:
        for idx, fid in enumerate(tasks, 1):
            abstract_text = forum_to_abstract.get(fid, '')
            if not abstract_text:
                print(f'⚠️  摘要为空，forumid={fid}（将以空摘要进行评审）')
            entry = process_single_forum(fid, abstract_text, reviewer_ai, strictness_levels)
            results[fid] = entry
            save_results(results, output_path)
            print(f'💾 已保存 ({idx}/{len(tasks)}) - {fid}')
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_single_forum, fid, forum_to_abstract.get(fid, ''), reviewer_ai, strictness_levels): fid
                for fid in tasks
            }
            for idx, future in enumerate(as_completed(futures), 1):
                fid = futures[future]
                entry = future.result()
                results[fid] = entry
                save_results(results, output_path)
                print(f'💾 已保存 ({idx}/{len(tasks)}) - {fid}')

    # 统计输出
    print('\n======== 统计 ========')
    print(f'总条目: {len(results)}')
    total_reviews = 0
    success = 0
    ratings: List[int] = []
    missing_abstract = 0
    for entry in results.values():
        if not entry.get('abstract'):
            missing_abstract += 1
        reviews = entry.get('reviews', [])
        total_reviews += len(reviews)
        for r in reviews:
            rating = (r.get('review') or {}).get('rating', {}).get('value', -1)
            if isinstance(rating, int) and rating >= 0:
                success += 1
                ratings.append(rating)
    print(f'总评审数: {total_reviews}, 成功: {success}, 失败: {total_reviews - success}')
    print(f'摘要缺失条目: {missing_abstract}')
    if ratings:
        print(f'评分范围: {min(ratings)} - {max(ratings)}, 平均: {sum(ratings)/len(ratings):.2f}')
    print(f'✅ 结果已保存: {output_path.resolve()}')


if __name__ == '__main__':
    main()