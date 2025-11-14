#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import argparse
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
import openai
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random

BASE_REVIEW_TASK = """
## Your Review Task

### Role: The Strict, Precise & Insightful Academic Reviewer
You are a seasoned reviewer renowned for strict scrutiny, precision, and insight. You uphold the highest academic standards. Your primary mission is **strict scrutiny** to ensure that only high-quality research is advanced. You relentlessly identify core deficiencies and logical leaks, and your feedback must be **specific, clear, and executable**. Your goal is to drive authors toward fundamental improvements that meet the highest submission standards.

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

## Additional Input: Author Rebuttal

You are also given the authors' rebuttal. Incorporate it thoughtfully:
- Identify which concerns are addressed and which remain unresolved.
- If the rebuttal provides clarifications or new evidence, reflect this in your assessment.
- Where appropriate, adjust your reasoning and overall rating in light of the rebuttal.
- Do not quote the rebuttal verbatim; summarize and critically assess its effectiveness.

## Output Format

You must respond with a JSON object in the following format:
```json
{{
  "summary": "...",
  "strengths": "...",
  "weaknesses": "...",
  "questions": "...",
  "rating": <1, 3, 5, 6, 8, or 10>,
  "confidence": <1-5>,
  "soundness": <1-4>,
  "presentation": <1-4>,
  "contribution": <1-4>
}}
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

USER_PROMPT_TEMPLATE = """## Paper Content

{paper_content}

## Author Rebuttal 

{author_rebuttal}"""

class ReviewerAI:
    def __init__(
        self,
        base_url: str = "http://10.176.59.101:8003/v1",
        model_name: str = "qwen3-30b-a3b",
        prompt_template_path: Optional[str] = None
    ):
        self.client = openai.OpenAI(api_key="EMPTY", base_url=base_url)
        self.model_name = model_name
        if prompt_template_path:
            template_file = Path(prompt_template_path)
            if not template_file.exists():
                raise FileNotFoundError(f"Prompt 模板文件不存在: {prompt_template_path}")
            self.user_prompt_template = template_file.read_text(encoding='utf-8')
            print(f"  ✓ 已加载外部 User Prompt 模板: {prompt_template_path}")
        else:
            self.user_prompt_template = USER_PROMPT_TEMPLATE
            print(f"  ✓ 使用内置 User Prompt 模板")
        self.system_prompts = SYSTEM_PROMPTS
        print(f"  ✓ 使用内置 System Prompts (5个独立级别)")

    def build_review_prompt(
        self,
        paper_content: str,
        author_rebuttal: str,
        max_content_length: int = 20000,
        max_rebuttal_length: int = 5000
    ) -> str:
        if len(paper_content) > max_content_length:
            paper_content = paper_content[:max_content_length] + "\n\n[论文内容已截断...]"
            print("论文内容阶段已截断...")
        if author_rebuttal and len(author_rebuttal) > max_rebuttal_length:
            author_rebuttal = author_rebuttal[:max_rebuttal_length] + "\n\n[作者回复已截断...]"
            print("作者回复已截断...")
        prompt = self.user_prompt_template.format(
            paper_content=paper_content,
            author_rebuttal=author_rebuttal or ""
        )
        return prompt

    def generate_review(
        self,
        paper_content: str,
        author_rebuttal: str,
        strictness: int = 3,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> Dict[str, Any]:
        prompt = self.build_review_prompt(paper_content, author_rebuttal)
        try:
            system_prompt = self.system_prompts.get(strictness, self.system_prompts[3])
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            content = response.choices[0].message.content
            content = content.strip()
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
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            if not content.startswith('{'):
                json_start = content.find('{')
                if json_start != -1:
                    content = content[json_start:]
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
            print(f"  ⚠️  JSON解析失败: {e}")
            if 'content' in locals():
                print(f"  原始响应前200字符: {content[:200]}")
                if hasattr(e, 'pos') and e.pos:
                    start = max(0, e.pos - 50)
                    end = min(len(content), e.pos + 50)
                    print(f"  错误位置附近: ...{content[start:end]}...")
            return {
                "summary": content if 'content' in locals() else "No content",
                "strengths": "Failed to parse",
                "weaknesses": "Failed to parse",
                "questions": "Failed to parse",
                "rating": -1,
                "confidence": -1,
                "soundness": -1,
                "presentation": -1,
                "contribution": -1,
                "error": str(e)
            }
        except Exception as e:
            print(f"  ❌ API调用失败: {e}")
            print(f"  Exception type: {type(e).__name__}")
            import traceback
            print(f"  Traceback: {traceback.format_exc()[:500]}")
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
                "error": str(e)
            }

def format_review_content(review_data: Dict[str, Any]) -> Dict[str, Any]:
    content = {}
    for key in ['summary', 'strengths', 'weaknesses', 'questions']:
        if key in review_data:
            content[key] = {"value": review_data[key]}
    for key in ['rating', 'confidence', 'soundness', 'presentation', 'contribution']:
        if key in review_data and review_data[key] != -1:
            content[key] = {"value": review_data[key]}
    return content

def read_author_rebuttal(forum_id: str) -> str:
    repo_root = Path(__file__).resolve().parent.parent
    author_dir = repo_root / "dataset" / "data" / "iclr2025_only_author"
    file_path = author_dir / f"{forum_id}.json"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            obj = json.load(f)
        val = obj.get('author_rebuttal')
        if isinstance(val, str):
            return val.strip()
        return ""
    except Exception as e:
        print(f"  ⚠️  读取作者回复失败: {forum_id}: {e}")
        return ""

def process_single_paper(args) -> tuple:
    paper_file, reviewer_ai, selected_reviewers, existing_entry = args
    paper_id = paper_file.stem
    print(f"\n{'='*60}")
    print(f"Processing: {paper_id}")
    existing_count = 0 if not existing_entry else len(existing_entry.get('reviews', []))
    print(f"Selected Reviewers: {', '.join([r['id'] for r in selected_reviewers])} | Existing reviews: {existing_count}")
    print(f"{'='*60}")
    try:
        paper_content = paper_file.read_text(encoding='utf-8')
        print(f"  ✓ 论文内容已加载 ({len(paper_content)} 字符)")
    except Exception as e:
        print(f"  ❌ 读取论文内容失败: {e}")
        paper_content = f"[读取失败: {e}]"
    author_text = read_author_rebuttal(paper_id)
    print(f"  ✓ 作者回复内容长度: {len(author_text)} 字符")
    reviews = []
    if existing_entry and isinstance(existing_entry, dict):
        reviews = list(existing_entry.get('reviews', []))
    if len(selected_reviewers) == 0:
        result = {
            "paper_id": paper_id,
            "reviews": reviews
        }
        print(f"  ✅ 已存在完整评审，跳过生成")
        return paper_id, result
    for reviewer in selected_reviewers:
        print(f"  🤖 {reviewer['id']} (strictness: {reviewer['strictness']}) 评审中...")
        start_time = time.time()
        review_data = reviewer_ai.generate_review(
            paper_content=paper_content,
            author_rebuttal=author_text,
            strictness=reviewer['strictness']
        )
        elapsed = time.time() - start_time
        if 'error' not in review_data:
            print(f"    ✓ 生成完成 (耗时: {elapsed:.1f}s, 评分: {review_data.get('rating', 'N/A')})")
        else:
            print(f"    ✗ 生成失败 (耗时: {elapsed:.1f}s)")
        formatted_content = format_review_content(review_data)
        review_entry = {
            "reviewer_id": reviewer['id'],
            "strictness": reviewer['strictness'],
            "review": formatted_content
        }
        reviews.append(review_entry)
    result = {
        "paper_id": paper_id,
        "reviews": reviews
    }
    print(f"  ✅ 完成，共生成 {len(reviews)} 个评审")
    return paper_id, result

def main():
    parser = argparse.ArgumentParser(
        description="AI 评审员推理脚本 - 使用 Qwen3-30B-A3B 模型模拟论文评审（包含作者回复）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python qwen3-30B-author-rebuttal-reviewer.py --workers 3 --limit 5
        """
    )
    parser.add_argument(
        '--input-dir',
        default='/remote-home1/bwli/get_open_review/qwen_review/extracted_contents',
        help='论文内容目录'
    )
    parser.add_argument(
        '--output',
        default='qwen3-30B-author-rebuttal-reviews.json',
        help='输出JSON文件路径'
    )
    parser.add_argument(
        '--base-url',
        default='http://10.176.59.108:8003/v1',
        help='Qwen3-30B-A3B API地址'
    )
    parser.add_argument(
        '--model',
        default='qwen3-30b-a3b',
        help='模型名称'
    )
    parser.add_argument(
        '--prompt-template',
        default=None,
        help='Prompt 模板文件路径（可选）'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='并行处理的线程数'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='只处理前N篇论文（用于测试）'
    )
    args = parser.parse_args()
    REVIEWERS = [
        {"id": "reviewer_2", "strictness": 2, "name": "较宽松评审员"},
        {"id": "reviewer_3", "strictness": 3, "name": "中立评审员"},
        {"id": "reviewer_4", "strictness": 4, "name": "较严格评审员"},
    ]
    strictness_plan: Optional[List[int]] = [2, 3, 4]
    if strictness_plan:
        print(f"使用固定评审员严格度计划: {strictness_plan}")
    print("=" * 80)
    print("AI 评审员推理系统 - 多评审员模式 (Qwen3-30B-A3B) + 作者回复")
    print("=" * 80)
    print(f"模型: {args.model} @ {args.base_url}")
    print(f"Prompt 模板: {'内置模板' if args.prompt_template is None else args.prompt_template}")
    print(f"输入目录: {args.input_dir}")
    print(f"输出文件: {args.output}")
    print(f"并行线程: {args.workers}")
    print(f"评审员配置: {len(REVIEWERS)} 位评审员，严格度范围 2-4")
    if strictness_plan:
        print(f"每篇论文: 使用固定严格度评审员 {strictness_plan}")
    print("=" * 80)
    print("\n📖 加载论文文件...")
    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"❌ 输入目录不存在: {input_dir}")
        return
    paper_files = sorted(input_dir.glob("*.txt"))
    if args.limit:
        paper_files = paper_files[:args.limit]
        print(f"⚠️  限制处理前 {args.limit} 篇论文")
    print(f"✓ 找到 {len(paper_files)} 篇论文")
    print(f"\n🤖 初始化 AI 评审员...")
    reviewer_ai = ReviewerAI(
        base_url=args.base_url,
        model_name=args.model,
        prompt_template_path=args.prompt_template
    )
    print(f"✓ AI 评审员已就绪")
    print(f"\n🚀 开始处理论文...")
    print(f"💾 结果将动态保存到 {args.output}")
    output_path = Path(args.output)
    results = {}
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                results = existing
                print(f"  ↻ 检测到已有输出，载入 {len(results)} 篇论文的结果以续跑")
            else:
                print("  ⚠️  现有输出不是字典结构，忽略续跑数据")
        except Exception as e:
            print(f"  ⚠️  读取已有输出失败，忽略续跑数据: {e}")
    def save_results(results_dict, output_file):
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results_dict, f, ensure_ascii=False, indent=2)
    desired_review_count = len(strictness_plan) if strictness_plan else 3
    def paper_needs_work(paper_id: str) -> bool:
        entry = results.get(paper_id)
        if not entry:
            return True
        reviews = entry.get('reviews', [])
        if strictness_plan:
            done_levels = {r.get('strictness') for r in reviews if isinstance(r.get('strictness'), int)}
            for level in strictness_plan:
                if level not in done_levels:
                    return True
            return False
        return len(reviews) < desired_review_count
    def select_missing_reviewers(paper_id: str) -> List[dict]:
        entry = results.get(paper_id)
        existing_reviews = entry.get('reviews', []) if entry else []
        done_ids = {r.get('reviewer_id') for r in existing_reviews if r.get('reviewer_id')}
        done_levels = {r.get('strictness') for r in existing_reviews if isinstance(r.get('strictness'), int)}
        if strictness_plan:
            desired_reviewers: List[dict] = []
            for level in strictness_plan:
                if level in done_levels:
                    continue
                reviewer = next((rev for rev in REVIEWERS if rev['strictness'] == level), None)
                if reviewer:
                    desired_reviewers.append(reviewer)
            return desired_reviewers
        remaining = [r for r in REVIEWERS if r['id'] not in done_ids]
        need = max(0, desired_review_count - len(existing_reviews))
        if need <= 0:
            return []
        if need >= len(remaining):
            return remaining
        return random.sample(remaining, k=need)
    if args.workers == 1:
        for idx, paper_file in enumerate(paper_files, 1):
            pid = paper_file.stem
            if not paper_needs_work(pid):
                print(f"⏭️  跳过已完成: {pid}")
                continue
            selected_reviewers = select_missing_reviewers(pid)
            entry = results.get(pid)
            paper_id, review_content = process_single_paper((
                paper_file, reviewer_ai, selected_reviewers, entry
            ))
            results[paper_id] = review_content
            save_results(results, output_path)
            print(f"  💾 已保存 ({idx}/{len(paper_files)})")
    else:
        tasks = []
        for paper_file in paper_files:
            pid = paper_file.stem
            if not paper_needs_work(pid):
                print(f"⏭️  跳过已完成: {pid}")
                continue
            selected_reviewers = select_missing_reviewers(pid)
            entry = results.get(pid)
            tasks.append((paper_file, reviewer_ai, selected_reviewers, entry))
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_single_paper, task): task[0] for task in tasks}
            for idx, future in enumerate(as_completed(futures), 1):
                paper_id, review_content = future.result()
                results[paper_id] = review_content
                save_results(results, output_path)
                print(f"  💾 已保存 ({idx}/{len(paper_files)})")
    print(f"\n✅ 所有结果已保存到 {args.output}")
    print("\n" + "=" * 80)
    print("处理完成统计")
    print("=" * 80)
    print(f"总论文数: {len(results)}")
    total_reviews = 0
    successful_reviews = 0
    all_ratings = []
    ratings_by_strictness = {1: [], 2: [], 3: [], 4: [], 5: []}
    for paper_data in results.values():
        reviews = paper_data.get('reviews', [])
        total_reviews += len(reviews)
        for review_entry in reviews:
            review = review_entry.get('review', {})
            strictness = review_entry.get('strictness', 3)
            rating = review.get('rating', {}).get('value', -1)
            if rating >= 0:
                successful_reviews += 1
                all_ratings.append(rating)
                ratings_by_strictness[strictness].append(rating)
    failed_reviews = total_reviews - successful_reviews
    print(f"总评审数: {total_reviews}")
    print(f"成功生成: {successful_reviews}")
    print(f"失败: {failed_reviews}")
    if all_ratings:
        avg_rating = sum(all_ratings) / len(all_ratings)
        print(f"\n整体平均评分: {avg_rating:.2f}")
        print(f"评分范围: {min(all_ratings)} - {max(all_ratings)}")
        print(f"\n按严格度统计:")
        for strictness in [1, 2, 3, 4, 5]:
            ratings = ratings_by_strictness[strictness]
            if ratings:
                avg = sum(ratings) / len(ratings)
                print(f"  严格度 {strictness}: 平均 {avg:.2f} (样本数: {len(ratings)})")
    print(f"\n✅ 结果已保存到: {output_path.absolute()}")

if __name__ == '__main__':
    main()