#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 评审员推理脚本（3级严格度）
使用 Qwen3-30B-A3B 模型模拟学术论文评审。

特点：
- 固定三位评审员：宽松 / 中等 / 严格
- 每篇论文按顺序使用三位评审员生成评审
- 支持断点续跑、并行处理
"""

import argparse
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import openai


# ============================================================================
# Prompt 模板配置区 - 保持 BASE_REVIEW_TASK 不变
# ============================================================================

BASE_REVIEW_TASK = """
## Your Review Task

### Role: The Strict, Precise & Insightful Academic Reviewer
You are a seasoned reviewer renowned for strict scrutiny, precision, and insight. You uphold the highest academic standards. Your primary mission is **strict scrutiny** to ensure that only high-quality research is advanced. You relentlessly identify core deficiencies and logical leaks, and your feedback must be **specific, clear, and executable**. Your goal is to drive authors toward fundamental improvements that meet the highest submission standards.

### Core Knowledge & Abilities
- **Cutting-Edge Acumen**: Track frontier theory, latest methods, and community trends in real time; assess relevance and novelty.
- **Theoretical Mastery**: Possess systematic and critical understanding of classical theories and core paradigms; judge appropriateness of their application.
- **Logical Scrutiny**: Detect logical fallacies, inconsistencies, or latent biases in research design, inference, and data interpretation.
- **Standards Awareness**: Be familiar with review standards, preferences, and gatekeeping across top-tier conferences and specialized journals.

### Key Review Criteria
- **Originality & Contribution**: Does the work present clear and valuable new insights? Is the contribution incremental or truly groundbreaking?
- **Research Question**: Is the problem crisply defined? Are its academic value and/or practical significance strong?
- **Literature Review**: Is the review comprehensive, deep, and critical (not a simple list)? Does it identify the research gap accurately?
- **Methodological Rigor**: Is the design scientific and optimal for the question? Are sampling choices, data collection, and processing transparent, standardized, and reproducible?
- **Data Analysis & Results**: Are methods appropriate? Are results clear and accurate? Are interpretations rigorous and justified?
- **Discussion & Conclusion**: Do the authors interpret results deeply, engage with theory and prior work, and present evidence-based conclusions while honestly acknowledging limitations?
- **Logic & Expression**: Are arguments coherent and consistent? Is the academic language precise and professional?

### Strict Review Policy
- Maintain a strict, precise, and insightful tone; avoid vague praise or marketing language.
- Ground every judgment in evidence from the paper (methods, datasets, baselines, metrics, settings). If information is missing, explicitly state "Missing" and explain its impact.
- Identify core deficiencies and logical flaws decisively; provide numbered, actionable suggestions the authors can execute.
- Treat novelty rigorously: check overlaps with prior work; demand strong baselines/ablations and statistical significance when applicable.

### Workflow: Target-Oriented Comprehensive Review
1. Identify target claims and contributions; list required evidence for each.
2. Map evidence to claims; check completeness against baselines, ablations, datasets, metrics, and settings.
3. Diagnose failure points: unsupported claims, missing baselines, ambiguous novelty, flawed methodology, or weak analysis.
4. Propose corrective actions: numbered, prioritized, and feasible; specify experiments, analyses, or clarifications required for acceptance.
5. Calibrate soundness/presentation/contribution and overall rating using the defined scales; state confidence and rationale.

You will be provided with a research paper. Please provide a comprehensive review with the following components:

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
```
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


# ============================================================================
# 三个级别的 System Prompt（宽松 / 中等 / 严格）
# ============================================================================

SYSTEM_PROMPT_LENIENT = """You are an expert academic reviewer for a top-tier machine learning conference (ICLR).

## Your Reviewer Profile
**You are a Lenient Reviewer (Encouraging)**

- **Philosophy**: You celebrate promising ideas and nurture early-stage innovation.
- **What you value most**: Novelty, potential impact, creative combinations, and cross-domain insights.
- **How you treat flaws**: If the core idea is compelling, you tolerate fixable weaknesses in experiments or writing.
- **Tone and writing style**: Highlight strengths, reframe issues as improvements, deliver constructive and motivating feedback.
- **Scoring tendency**: You lean toward acceptance when the idea has potential; your ratings usually fall between 6 and 8.
- **Rating constraint**: The `rating` field must be chosen strictly from {1, 3, 5, 6, 8, 10}. No other numbers are permitted.

""" + BASE_REVIEW_TASK

SYSTEM_PROMPT_BALANCED = """You are an expert academic reviewer for a top-tier machine learning conference (ICLR).

## Your Reviewer Profile
**You are a Balanced Reviewer (Objective)**

- **Philosophy**: You apply the official review criteria faithfully and weigh pros against cons fairly.
- **What you value most**: A well-balanced combination of novelty, methodological soundness, reproducibility, and clarity.
- **How you treat flaws**: You acknowledge strengths and weaknesses in equal measure, grounding every judgment in evidence.
- **Tone and writing style**: Direct, transparent, and actionable—clearly list strengths, shortcomings, and concrete next steps.
- **Scoring tendency**: You map closely to the conference decision threshold; ratings typically cluster around 5 or 6.
- **Rating constraint**: The `rating` field must be chosen strictly from {1, 3, 5, 6, 8, 10}. No other numbers are permitted.

""" + BASE_REVIEW_TASK

SYSTEM_PROMPT_STRICT = """You are an expert academic reviewer for a top-tier machine learning conference (ICLR).

## Your Reviewer Profile
**You are a Strict Reviewer (Highly Critical)**

- **Philosophy**: ICLR should showcase only the most rigorous and groundbreaking work.
- **What you value most**: Flawless methodology, compelling theoretical or empirical contributions, and unambiguous novelty.
- **How you treat flaws**: Even minor gaps are serious; every claim must be backed by strong evidence or ablations.
- **Tone and writing style**: Thoroughly document weaknesses, highlight risks, and demand precise corrective actions.
- **Scoring tendency**: You are conservative—ratings commonly fall between 1 and 5 unless the paper is exceptional.
- **Rating constraint**: The `rating` field must be chosen strictly from {1, 3, 5, 6, 8, 10}. No other numbers are permitted.

""" + BASE_REVIEW_TASK

SYSTEM_PROMPTS: Dict[int, str] = {
    1: SYSTEM_PROMPT_LENIENT,
    3: SYSTEM_PROMPT_BALANCED,
    5: SYSTEM_PROMPT_STRICT,
}


USER_PROMPT_TEMPLATE = """## Paper Content

{paper_content}"""


REVIEWERS: List[Dict[str, Any]] = [
    {"id": "reviewer_lenient", "strictness": 1, "name": "宽松评审员"},
    {"id": "reviewer_balanced", "strictness": 3, "name": "中等评审员"},
    {"id": "reviewer_strict", "strictness": 5, "name": "严格评审员"},
]

STRICTNESS_SEQUENCE = [reviewer["strictness"] for reviewer in REVIEWERS]


class ReviewerAI:
    """AI 评审员包装器"""

    def __init__(
        self,
        base_url: str = "http://10.176.59.101:8003/v1",
        model_name: str = "qwen3-30b-a3b",
        prompt_template_path: Optional[str] = None,
    ) -> None:
        self.client = openai.OpenAI(api_key="EMPTY", base_url=base_url)
        self.model_name = model_name

        if prompt_template_path:
            template_file = Path(prompt_template_path)
            if not template_file.exists():
                raise FileNotFoundError(f"Prompt 模板文件不存在: {prompt_template_path}")
            self.user_prompt_template = template_file.read_text(encoding="utf-8")
            print(f"  ✓ 已加载外部 User Prompt 模板: {prompt_template_path}")
        else:
            self.user_prompt_template = USER_PROMPT_TEMPLATE
            print("  ✓ 使用内置 User Prompt 模板")

        self.system_prompts = SYSTEM_PROMPTS
        print("  ✓ 已加载三种严格度的 System Prompt")

    def build_review_prompt(self, paper_content: str, max_content_length: int = 10000) -> str:
        if len(paper_content) > max_content_length:
            paper_content = paper_content[:max_content_length] + "\n\n[论文内容已截断...]"
        return self.user_prompt_template.format(paper_content=paper_content)

    def generate_review(
        self,
        paper_content: str,
        strictness: int,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        prompt = self.build_review_prompt(paper_content)
        try:
            system_prompt = self.system_prompts[strictness]
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content.strip()

            # 移除 <think> 内容
            if "<think>" in content.lower():
                lower_content = content.lower()
                end_tag = "</think>"
                idx = lower_content.find(end_tag)
                if idx != -1:
                    content = content[idx + len(end_tag) :].strip()
                else:
                    brace_idx = content.find("{")
                    if brace_idx != -1:
                        content = content[brace_idx:]

            # 移除 markdown 代码块
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            if not content.startswith("{"):
                brace_idx = content.find("{")
                if brace_idx != -1:
                    content = content[brace_idx:]

            def fix_escape(match: re.Match[str]) -> str:
                char = match.group(1)
                if char in ['"', "\\", "/", "b", "f", "n", "r", "t", "u"]:
                    return match.group(0)
                return "\\\\" + char

            content = re.sub(r"\\(.)", fix_escape, content)
            review_data = json.loads(content)
            return review_data

        except json.JSONDecodeError as exc:
            print(f"  ⚠️ JSON 解析失败: {exc}")
            if "content" in locals():
                snippet = content[:200]
                print(f"  原始响应前200字符: {snippet}")
            return {
                "summary": "JSON decode error",
                "strengths": "",
                "weaknesses": "",
                "questions": "",
                "rating": -1,
                "confidence": -1,
                "soundness": -1,
                "presentation": -1,
                "contribution": -1,
                "error": str(exc),
            }
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  ❌ API 调用失败: {exc}")
            return {
                "summary": f"Error: {exc}",
                "strengths": "",
                "weaknesses": "",
                "questions": "",
                "rating": -1,
                "confidence": -1,
                "soundness": -1,
                "presentation": -1,
                "contribution": -1,
                "error": str(exc),
            }


def format_review_content(review_data: Dict[str, Any]) -> Dict[str, Any]:
    content: Dict[str, Any] = {}
    for key in ["summary", "strengths", "weaknesses", "questions"]:
        if key in review_data:
            content[key] = {"value": review_data[key]}
    for key in ["rating", "confidence", "soundness", "presentation", "contribution"]:
        if key in review_data and review_data[key] != -1:
            content[key] = {"value": review_data[key]}
    return content


def paper_needs_work(results: Dict[str, Any], paper_id: str) -> bool:
    entry = results.get(paper_id)
    if not entry:
        return True
    reviews = entry.get("reviews", [])
    done_levels = {r.get("strictness") for r in reviews}
    for level in STRICTNESS_SEQUENCE:
        if level not in done_levels:
            return True
    return False


def select_missing_reviewers(results: Dict[str, Any], paper_id: str) -> List[Dict[str, Any]]:
    entry = results.get(paper_id)
    done_levels = set()
    if entry:
        for review in entry.get("reviews", []):
            level = review.get("strictness")
            if isinstance(level, int):
                done_levels.add(level)
    return [rev for rev in REVIEWERS if rev["strictness"] not in done_levels]


def save_results(results: Dict[str, Any], output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)


def process_single_paper(args: Any) -> Any:
    paper_file, reviewer_ai, selected_reviewers, existing_entry = args
    paper_id = paper_file.stem

    print("\n" + "=" * 60)
    print(f"Processing: {paper_id}")
    existing_count = 0 if not existing_entry else len(existing_entry.get("reviews", []))
    print(
        f"Selected Reviewers: {', '.join([r['id'] for r in selected_reviewers])} | Existing reviews: {existing_count}"
    )
    print("=" * 60)

    try:
        paper_content = paper_file.read_text(encoding="utf-8")
        print(f"  ✓ 论文内容已加载 ({len(paper_content)} 字符)")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"  ❌ 读取论文内容失败: {exc}")
        paper_content = f"[读取失败: {exc}]"

    reviews = []
    if existing_entry and isinstance(existing_entry, dict):
        reviews = list(existing_entry.get("reviews", []))

    for reviewer in selected_reviewers:
        strictness = reviewer["strictness"]
        reviewer_id = reviewer["id"]
        print(f"  🤖 {reviewer_id} (strictness: {strictness}) 评审中...")

        start_time = time.time()
        review_data = reviewer_ai.generate_review(paper_content, strictness=strictness)
        elapsed = time.time() - start_time

        if "error" not in review_data:
            print(f"    ✓ 生成完成 (耗时: {elapsed:.1f}s, 评分: {review_data.get('rating', 'N/A')})")
        else:
            print(f"    ✗ 生成失败 (耗时: {elapsed:.1f}s)")

        formatted_content = format_review_content(review_data)
        reviews.append(
            {
                "reviewer_id": reviewer_id,
                "strictness": strictness,
                "review": formatted_content,
            }
        )

    result = {"paper_id": paper_id, "reviews": reviews}
    print(f"  ✅ 完成，共生成 {len(reviews)} 个评审")
    return paper_id, result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI 评审员推理脚本 - 三严格度模式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python qwen3-30B-reviewer-3levels.py
  python qwen3-30B-reviewer-3levels.py --limit 10 --workers 2
""",
    )

    parser.add_argument(
        "--input-dir",
        default="/remote-home1/bwli/get_open_review/qwen_review/extracted_contents",
        help="论文内容目录（默认: /remote-home1/bwli/get_open_review/qwen_review/extracted_contents）",
    )

    parser.add_argument(
        "--output",
        default="qwen3-30B-reviews-3levels.json",
        help="输出 JSON 文件路径（默认: qwen3-30B-reviews-3levels.json）",
    )

    parser.add_argument(
        "--base-url",
        default="http://10.176.59.101:8003/v1",
        help="Qwen3-30B-A3B API 地址（默认: http://10.176.59.101:8003/v1）",
    )

    parser.add_argument(
        "--model",
        default="qwen3-30b-a3b",
        help="模型名称（默认: qwen3-30b-a3b）",
    )

    parser.add_argument(
        "--prompt-template",
        default=None,
        help="自定义 User Prompt 模板路径（可选）",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="并行处理线程数（默认: 1）",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="只处理前 N 篇论文（调试用）",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("AI 评审员推理系统 - 三严格度模式 (Qwen3-30B-A3B)")
    print("=" * 80)
    print(f"模型: {args.model} @ {args.base_url}")
    print(f"Prompt 模板: {'内置模板' if args.prompt_template is None else args.prompt_template}")
    print(f"输入目录: {args.input_dir}")
    print(f"输出文件: {args.output}")
    print(f"并行线程: {args.workers}")
    print(f"评审员配置: {', '.join([r['name'] for r in REVIEWERS])}")
    print(f"严格度序列: {STRICTNESS_SEQUENCE}")
    print("=" * 80)

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在: {input_dir}")

    paper_files = sorted(input_dir.glob("*.txt"))
    if args.limit:
        paper_files = paper_files[: args.limit]
        print(f"⚠️  限制处理前 {len(paper_files)} 篇论文")

    print(f"✓ 找到 {len(paper_files)} 篇论文")

    reviewer_ai = ReviewerAI(
        base_url=args.base_url,
        model_name=args.model,
        prompt_template_path=args.prompt_template,
    )
    print("✓ AI 评审员已就绪")

    output_path = Path(args.output)
    results: Dict[str, Any] = {}

    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
            if isinstance(existing, dict):
                results = existing
                print(f"  ↻ 检测到已有输出，载入 {len(results)} 篇论文的结果以续跑")
            else:
                print("  ⚠️ 现有输出不是字典结构，忽略续跑数据")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  ⚠️ 读取已有输出失败，忽略续跑数据: {exc}")

    print("\n🚀 开始处理论文...")
    print(f"💾 结果将动态保存到 {output_path}")

    if args.workers == 1:
        for idx, paper_file in enumerate(paper_files, 1):
            paper_id = paper_file.stem
            if not paper_needs_work(results, paper_id):
                print(f"⏭️  跳过已完成: {paper_id}")
                continue

            selected = select_missing_reviewers(results, paper_id)
            entry = results.get(paper_id)
            paper_id, review_content = process_single_paper(
                (paper_file, reviewer_ai, selected, entry)
            )
            results[paper_id] = review_content
            save_results(results, output_path)
            print(f"  💾 已保存 ({idx}/{len(paper_files)})")
    else:
        tasks = []
        for paper_file in paper_files:
            paper_id = paper_file.stem
            if not paper_needs_work(results, paper_id):
                print(f"⏭️  跳过已完成: {paper_id}")
                continue
            selected = select_missing_reviewers(results, paper_id)
            entry = results.get(paper_id)
            tasks.append((paper_file, reviewer_ai, selected, entry))

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_map = {executor.submit(process_single_paper, task): task[0] for task in tasks}
            for idx, future in enumerate(as_completed(future_map), 1):
                paper_id, review_content = future.result()
                results[paper_id] = review_content
                save_results(results, output_path)
                print(f"  💾 已保存 ({idx}/{len(tasks)})")

    print("\n✅ 所有结果已保存")
    print("\n" + "=" * 80)
    print("处理完成统计")
    print("=" * 80)
    print(f"总论文数: {len(results)}")

    total_reviews = 0
    successful_reviews = 0
    all_ratings: List[float] = []
    ratings_by_reviewer: Dict[str, List[float]] = {r["id"]: [] for r in REVIEWERS}

    for paper_data in results.values():
        reviews = paper_data.get("reviews", [])
        total_reviews += len(reviews)
        for entry in reviews:
            review = entry.get("review", {})
            reviewer_id = entry.get("reviewer_id")
            rating_val = review.get("rating", {}).get("value", -1)
            if isinstance(rating_val, (int, float)) and rating_val >= 0:
                successful_reviews += 1
                all_ratings.append(float(rating_val))
                if reviewer_id in ratings_by_reviewer:
                    ratings_by_reviewer[reviewer_id].append(float(rating_val))

    failed_reviews = total_reviews - successful_reviews

    print(f"总评审数: {total_reviews}")
    print(f"成功生成: {successful_reviews}")
    print(f"失败: {failed_reviews}")

    if all_ratings:
        avg_rating = sum(all_ratings) / len(all_ratings)
        print(f"\n整体平均评分: {avg_rating:.2f}")
        print(f"评分范围: {min(all_ratings)} - {max(all_ratings)}")

        print("\n按评审员统计:")
        for reviewer in REVIEWERS:
            rid = reviewer["id"]
            scores = ratings_by_reviewer[rid]
            if scores:
                reviewer_avg = sum(scores) / len(scores)
                print(f"  {reviewer['name']} ({rid}): 平均 {reviewer_avg:.2f} (样本数: {len(scores)})")

    print(f"\n✅ 结果已保存到: {output_path.resolve()}")


if __name__ == "__main__":
    main()


