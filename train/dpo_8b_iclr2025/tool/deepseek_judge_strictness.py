import os
import json
import argparse
import re
import time
import sys
from typing import Dict, Any, List, Optional

import requests


DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
# 你可以换成 deepseek-v3 / deepseek-r1 等，具体看你账号支持的模型
DEEPSEEK_MODEL = "deepseek-chat"


SYSTEM_PROMPT = """
You are a seasoned ICLR Senior PC member. Your task is to assess a reviewer's strictness based on a single review.

Instructions

- Consider only this single review. Do not infer or assume other reviewers' opinions.
- Use both numeric scores and the textual tone/content: does the reviewer emphasize strengths or weaknesses, how strong are the criticisms, and what is the attitude (encouraging vs. strongly discouraging acceptance).
- Output exactly one uppercase letter from A to J representing strictness. No explanations or extra text.

Strictness Scale (A–J)

- A: Extremely lenient — almost entirely positive, highly forgiving of problems, strongly inclined to accept.
- B: Very lenient — mostly positive, weaknesses are few/minor; focuses on potential and positive aspects.
- C: Moderately lenient — lists pros and cons seriously but overall positive; weaknesses framed as improvements.
- D: Slightly lenient — balanced but slightly positive; willing to give a chance while noting issues.
- E: Balanced–Slightly lenient — neutral-to-positive; balanced assessment and slightly inclined to accept.
- F: Balanced–Slightly strict — neutral-to-negative; points out concrete issues and raises cautious skepticism.
- G: Moderately strict — sensitive to weaknesses, many specific issues; overall negative and inclined to reject.
- H: Strict — stresses serious problems (method reliability, insufficient evidence, limited contribution); clearly discourages acceptance.
- I: Very strict — strong reservations or denial; believes severe flaws exist; almost entirely negative.
- J: Extremely strict — considers the submission clearly unsuitable for the venue; strongly negative; strongly recommends rejection.

Bucket Mapping

- A–C → lenient
- D–G → moderate
- H–J → strict

Field Definitions

1. Summary: A brief summary of the paper's main contributions and approach (2–3 sentences).
2. Strengths: A substantive assessment of strengths (originality, quality, clarity, significance). Be broad about originality (new definitions, formulations, creative combinations, new domains, removing prior limitations).
3. Weaknesses: A substantive assessment of weaknesses. Be constructive and actionable. If novelty is lacking, provide references and details; if experiments are insufficient, explain exactly what is missing.
4. Questions: List and carefully describe questions/suggestions for the authors that could change your opinion or clarify confusions; important for rebuttal/discussion.
5. Soundness (1–4): Are central claims supported? Is methodology sound?
   - 1: Poor
   - 2: Fair
   - 3: Clear and structured
   - 4: Excellent
6. Presentation (1–4): Writing clarity, figures/diagrams quality, and context vs. prior work.
   - 1: Poor
   - 2: Fair
   - 3: Good
   - 4: Excellent
7. Contribution (1–4): Importance of questions, originality of ideas/execution, value to ICLR community.
   - 1: Poor
   - 2: Fair
   - 3: Good
   - 4: Excellent
8. Rating (1, 3, 5, 6, 8, 10): Overall score.
   - 1: Strong reject
   - 3: Reject, not good enough
   - 5: Marginally below threshold
   - 6: Marginally above threshold
   - 8: Accept, good paper
   - 10: Strong accept, highlight
9. Confidence (1–5): Confidence in assessment.
   - 1: Unable to assess; need different reviewers
   - 2: Will defend but likely misunderstood central parts or unfamiliar with related work
   - 3: Fairly confident; possible some parts misunderstood or unfamiliar
   - 4: Confident but not absolutely certain; unlikely but possible some misunderstandings
   - 5: Absolutely certain; very familiar and checked details carefully

Output Format

- Output exactly one uppercase letter: A, B, C, D, E, F, G, H, I, or J.
- Do not output explanations, punctuation, or extra lines.
""".strip()


def build_user_prompt(
    paper: Dict[str, Any],
    review_content: Dict[str, Any],
    reviewer_id: str,
) -> str:
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")

    def gv(field: str, default: str = "N/A") -> str:
        return review_content.get(field, {}).get("value", default)

    summary = gv("summary", "")
    strengths = gv("strengths", "")
    weaknesses = gv("weaknesses", "")
    questions = gv("questions", "")
    rating = gv("rating", "N/A")
    confidence = gv("confidence", "N/A")
    soundness = gv("soundness", "N/A")
    presentation = gv("presentation", "N/A")
    contribution = gv("contribution", "N/A")

    prompt = f"""
Below is an ICLR paper and a single review. Based on the review content and scores, judge the reviewer's strictness (A–J). Consider only this one review.

Paper

Title:
{title}

Abstract:
{abstract}

Reviewer ID:
{reviewer_id}

Reviewer Report

Summary:
{summary}

Strengths:
{strengths}

Weaknesses:
{weaknesses}

Questions:
{questions}

Scoring
- Overall Rating (1,3,5,6,8,10): {rating}
- Confidence (1–5): {confidence}
- Soundness (1–4): {soundness}
- Presentation (1–4): {presentation}
- Contribution (1–4): {contribution}

Task

Choose one letter in A–J that best reflects the reviewer's strictness, considering scores, the balance and strength of pros/cons, the attitude toward weaknesses, and overall tone.

Output exactly one uppercase letter (A–J). Do not output any explanations or extra text.
""".strip()

    return prompt


def call_deepseek(api_key: str, user_prompt: str) -> str:
    """调用 DeepSeek API，返回模型输出文本"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        # 为了稳定输出一个字母，设温度低一点，max_tokens 设小一点
        "temperature": 0.2,
        "max_tokens": 4,
    }

    resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    try:
        text = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Unexpected DeepSeek response: {data}") from e

    return text.strip()


def parse_strict_level(text: str) -> Optional[str]:
    """
    从模型输出中提取 A–J 的单个大写字母。
    即使模型不完全遵守“只输出一个字母”，我们也尽量从中找出第一个合法字母。
    """
    # 先看是不是单字母
    if text in list("ABCDEFGHIJ"):
        return text

    # 否则用正则找第一个独立的合法字母
    m = re.search(r"\b([A-J])\b", text)
    if m:
        return m.group(1)

    # 再退一步：找所有大写 A–J
    m = re.search(r"([A-J])", text)
    if m:
        return m.group(1)

    return None


def map_level_to_bucket(level: str) -> str:
    """
    A/B/C → lenient
    D/E/F/G → moderate
    H/I/J → strict
    """
    if level in ["A", "B", "C"]:
        return "lenient"
    if level in ["D", "E", "F", "G"]:
        return "moderate"
    if level in ["H", "I", "J"]:
        return "strict"
    return "unknown"


def _get_content_from_official(ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c = (ev or {}).get("content")
    return c if isinstance(c, dict) and c else None


def process_paper(
    paper_json: Dict[str, Any],
    api_key: str,
    sleep_sec: float = 0.5,
) -> List[Dict[str, Any]]:
    results = []
    official_review = paper_json.get("official_review", {})
    if not isinstance(official_review, dict) or not official_review:
        return results
    for reviewer_id, ev in official_review.items():
        content = _get_content_from_official(ev)
        if not content:
            continue
        user_prompt = build_user_prompt(paper_json, content, reviewer_id)
        raw_output = call_deepseek(api_key, user_prompt)
        level = parse_strict_level(raw_output)
        if level is None:
            print(f"[WARN] cannot parse strict level (reviewer={reviewer_id}, output={raw_output!r}), skip.")
            continue
        bucket = map_level_to_bucket(level)
        print(f"[PRED] forum={paper_json.get('forum')} reviewer={reviewer_id} level={level}")
        record = {
            "paper_forum": paper_json.get("forum"),
            "paper_number": paper_json.get("number"),
            "paper_title": paper_json.get("title"),
            "reviewer_id": reviewer_id,
            "strict_level": level,
            "strict_bucket": bucket,
            "raw_model_output": raw_output,
            "review_content": content,
        }
        results.append(record)
        print(f"[OK] paper={paper_json.get('number')} reviewer={reviewer_id} level={level} bucket={bucket}")
        if sleep_sec > 0:
            time.sleep(sleep_sec)
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Label review strictness (A–J) using DeepSeek for OpenReview ICLR reviews."
    )
    parser.add_argument("--input_dir", type=str, default="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/iclr2025_first_review_2k", help="输入目录，内含每论文一个 JSON")
    parser.add_argument("--output_dir", type=str, default="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/iclr2025_ds_judge_strictness", help="输出目录，默认为目标路径")
    parser.add_argument("--overwrite", action="store_true", help="若存在输出文件则覆盖")
    parser.add_argument("--sleep", type=float, default=0.5, help="每次 API 调用之间的休眠秒数")
    args = parser.parse_args()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("请先在环境变量中设置 DEEPSEEK_API_KEY")

    in_dir = args.input_dir
    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)
    files = [f for f in os.listdir(in_dir) if f.endswith(".json")]
    total = len(files)
    errors = 0
    for i, fname in enumerate(sorted(files), 1):
        src = os.path.join(in_dir, fname)
        dst = os.path.join(out_dir, fname)
        if (not args.overwrite) and os.path.exists(dst) and os.path.getsize(dst) > 0:
            ratio = i / total if total else 1
            bar_len = 30
            filled = int(bar_len * ratio)
            bar = "#" * filled + "-" * (bar_len - filled)
            sys.stdout.write(f"\r[{i}/{total}] |{bar}| {int(ratio*100)}%")
            sys.stdout.flush()
            continue
        try:
            with open(src, "r", encoding="utf-8") as f:
                paper_json = json.load(f)
            records = process_paper(paper_json, api_key, sleep_sec=args.sleep)
            out_data = dict(paper_json)
            out_data.pop("other_review", None)
            off = out_data.get("official_review")
            if isinstance(off, dict):
                for rec in records:
                    rid = rec.get("reviewer_id")
                    level = rec.get("strict_level")
                    bucket = rec.get("strict_bucket")
                    ev = off.get(rid)
                    if isinstance(ev, dict):
                        new_ev: Dict[str, Any] = {}
                        order = [
                            "time",
                            "time_ms",
                            "actor",
                            "event_type",
                            "version_index",
                            "note_id",
                            "replyto",
                            "signatures",
                        ]
                        for k in order:
                            if k in ev:
                                new_ev[k] = ev[k]
                        new_ev["deepseek_judge_strictness"] = bucket
                        if "content" in ev:
                            new_ev["content"] = ev["content"]
                        for k, v in ev.items():
                            if k not in new_ev:
                                new_ev[k] = v
                        off[rid] = new_ev
            with open(dst, "w", encoding="utf-8") as f_out:
                json.dump(out_data, f_out, ensure_ascii=False, indent=2)
        except Exception:
            errors += 1
        ratio = i / total if total else 1
        bar_len = 30
        filled = int(bar_len * ratio)
        bar = "#" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r[{i}/{total}] |{bar}| {int(ratio*100)}%")
        sys.stdout.flush()
    sys.stdout.write("\n")
    print(f"Done. total={total} errors={errors} output_dir={out_dir}")


if __name__ == "__main__":
    main()
