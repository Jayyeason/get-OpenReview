#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Use Qwen3-8B via vLLM(OpenAI-compatible) to generate weaker baseline
(rejected-side) reviews for DPO training.

- Strictness buckets are strings: "lenient", "moderate", "strict"
- Each strictness has its own system prompt persona
- Output JSON is easy to consume for later DPO data building
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
import re
import time

import openai


_GLOBAL_COUNTERS: Dict[str, int] = {"generate_err": 0}

# ===================== Base review task shared by all personas =====================

BASE_REVIEW_TASK = r"""## Your Review Task

### Role: The Academic Reviewer
You are an experienced reviewer for a top-tier ML conference (e.g., ICLR).

You will be given the full content of a research paper (possibly truncated).
Your goal is to produce a **concise, somewhat shallow review**, suitable as a weaker baseline for preference training.
Do NOT try to be perfect or extremely thorough; it is OK to miss important issues, be generic, or provide only high-level comments.

Please output a review with the following fields:

1. **Summary**: Briefly summarize the paper's main idea and contribution in 2–3 sentences.

2. **Strengths**: Describe some strengths, but you may keep this part relatively high-level or generic.

3. **Weaknesses**: Point out some weaknesses or limitations, but it is acceptable if this section is not very deep, and may miss more subtle or serious issues.

4. **Questions**: Ask a few (1–3) questions or suggestions for the authors. These can also be relatively generic and need not be very probing.

5. **Soundness** (1–4): Rate the soundness of the paper:
   - 1: Poor
   - 2: Fair
   - 3: Clear and structured
   - 4: Excellent

6. **Presentation** (1–4): Rate the quality of presentation:
   - 1: Poor
   - 2: Fair
   - 3: Good
   - 4: Excellent

7. **Contribution** (1–4): Rate the overall contribution:
   - 1: Poor
   - 2: Fair
   - 3: Good
   - 4: Excellent

8. **Rating** (1, 3, 5, 6, 8, 10): Provide a single overall score:
   - 1: Strong reject
   - 3: Reject, not good enough
   - 5: Marginally below acceptance threshold
   - 6: Marginally above acceptance threshold
   - 8: Accept, good paper
   - 10: Strong accept, highlight

9. **Confidence** (1–5): Your confidence in this review:
   - 1: Very low
   - 2: Low
   - 3: Medium
   - 4: High
   - 5: Very high

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

- `rating` must be one of: 1, 3, 5, 6, 8, 10
- `confidence`, `soundness`, `presentation`, `contribution` must be integers in their respective ranges.
- The JSON must be valid and parseable.

You may use <think> tags to organize your thoughts before providing the JSON response. The final JSON object should come after your reasoning.""".strip()


# ======================= Three strictness personas =======================

SYSTEM_PROMPT_LENIENT = f"""You are a **lenient reviewer**.

- You are **encouraging and forgiving**.
- You focus more on **potential** and positive aspects.
- You tolerate missing baselines, incomplete experiments, or unclear novelty.
- Your reviews are often **soft**, with gentle wording.

However, this model is used as a **weaker baseline reviewer**, so:
- You are allowed to be **shallow and generic**.
- You may miss important technical flaws.
- You can accept vague or poorly justified claims.

Use this lenient style when reviewing.

{BASE_REVIEW_TASK}
""".strip()

SYSTEM_PROMPT_MODERATE = f"""You are a **moderately strict reviewer**.

- You try to be fair and balanced.
- You value both strengths and weaknesses.
- You will point out problems, but your tone is not extremely harsh.
- You are more critical than a lenient reviewer, but not hyper-strict.

This model is used as a **weaker baseline reviewer**, so:
- Your analysis can still be somewhat high-level.
- You may miss deeper or subtle issues.
- You focus on obvious points rather than detailed technical flaws.

Use this moderate style when reviewing.

{BASE_REVIEW_TASK}
""".strip()

SYSTEM_PROMPT_STRICT = f"""You are a **strict reviewer**.

- You are quite critical and sensitive to weaknesses.
- You easily notice issues in methodology, experiments, and novelty.
- You tend to be skeptical and emphasize problems.

However, this model is still used as a **weaker baseline reviewer**, so:
- Your criticism may still be **generic** rather than very deep.
- You do NOT need to perform detailed line-by-line or proof-level checking.
- You may over-focus on obvious issues and ignore subtle, technical details.

Use this strict style when reviewing.

{BASE_REVIEW_TASK}
""".strip()

SYSTEM_PROMPTS: Dict[str, str] = {
    "lenient": SYSTEM_PROMPT_LENIENT,
    "moderate": SYSTEM_PROMPT_MODERATE,
    "strict": SYSTEM_PROMPT_STRICT,
}


# ============================== User Prompt ==============================

USER_PROMPT_TEMPLATE = """## Paper Content

{paper_content}
"""


class ReviewerAI:
    """Wrapper: call Qwen3-8B (vLLM OpenAI-compatible) to generate one review."""

    def __init__(
        self,
        base_url: str = "http://10.176.59.101:8002/v1",
        model_name: str = "qwen3-8b",
        user_prompt_template: Optional[str] = None,
    ):
        # vLLM OpenAI-compatible client
        self.client = openai.OpenAI(api_key="EMPTY", base_url=base_url)
        self.model_name = model_name

        if user_prompt_template is not None:
            self.user_prompt_template = user_prompt_template
        else:
            self.user_prompt_template = USER_PROMPT_TEMPLATE

        self.system_prompts = SYSTEM_PROMPTS

    # ---------- build user prompt ----------

    def build_user_prompt(
        self,
        paper_content: str,
        max_content_chars: int = 40000,
    ) -> str:
        """Build user prompt and truncate paper content by characters."""
        if len(paper_content) > max_content_chars:
            paper_content = (
                paper_content[:max_content_chars]
                + "\n\n[Paper content truncated due to length...]"
            )

        prompt = self.user_prompt_template.format(paper_content=paper_content)
        return prompt

    # ---------- clean & parse JSON from model output ----------

    def _clean_and_parse_json(self, raw: str) -> Dict[str, Any]:
        """Extract and parse JSON from raw model output."""

        content = raw.strip()

        # remove <think> ... </think> if exists
        lower = content.lower()
        if "<think>" in lower:
            end_tag = "</think>"
            if end_tag in lower:
                idx = lower.find(end_tag)
                content = content[idx + len(end_tag) :].strip()
            else:
                pos = content.find("{")
                if pos != -1:
                    content = content[pos:]

        # strip ```json ... ``` or ``` ... ```
        if content.startswith("```json"):
            content = content[len("```json") :]
        elif content.startswith("```"):
            content = content[len("```") :]
        if content.endswith("```"):
            content = content[: -len("```")]
        content = content.strip()

        # ensure starts from first '{'
        if not content.startswith("{"):
            pos = content.find("{")
            if pos != -1:
                content = content[pos:]

        # fix invalid escapes to avoid json.loads errors
        def fix_escape(m):
            ch = m.group(1)
            if ch in ['"', "\\", "/", "b", "f", "n", "r", "t", "u"]:
                return m.group(0)
            return "\\" + ch

        content = re.sub(r"\\(.)", fix_escape, content)

        data = json.loads(content)
        return data

    # ---------- main inference ----------

    def generate_review(
        self,
        paper_content: str,
        strictness: str = "moderate",  # "lenient" / "moderate" / "strict"
        temperature: float = 0.6,
        max_tokens: int = 1000,
    ) -> Dict[str, Any]:
        """Generate one review (for DPO rejected side).

        Args:
            paper_content: full or truncated paper text
            strictness: "lenient" / "moderate" / "strict"
            temperature: sampling temperature
            max_tokens: max generation tokens
        """
        strictness = strictness.lower()
        if strictness not in self.system_prompts:
            strictness = "moderate"

        system_prompt = self.system_prompts[strictness]
        user_prompt = self.build_user_prompt(paper_content)

        try:
            def _request(temp: float, mt: int):
                return self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temp,
                    max_tokens=mt,
                    response_format={"type": "json_object"},
                )

            cur_temp = temperature
            cur_max_tokens = max_tokens
            retries = 3
            attempts = 0

            while True:
                try:
                    resp = _request(cur_temp, cur_max_tokens)
                except Exception as e:
                    msg = str(e)
                    if "max_tokens" in msg or "context" in msg or "too large" in msg:
                        fb = max(400, int(cur_max_tokens * 0.5))
                        print(f"  [WARN] context too long, retry with max_tokens={fb}")
                        cur_max_tokens = fb
                        attempts += 1
                        if attempts > retries:
                            raise
                        continue
                    else:
                        print(f"  [ERROR] request failed: {e}")
                        attempts += 1
                        if attempts > retries:
                            raise
                        cur_temp = 0.3 if attempts == 1 else (0.2 if attempts == 2 else 0.1)
                        continue

                raw_text = resp.choices[0].message.content
                try:
                    data = self._clean_and_parse_json(raw_text)
                    break
                except Exception as parse_err:
                    snippet = (raw_text or "").strip()
                    if len(snippet) > 1200:
                        snippet = snippet[:1200] + "... [truncated]"
                    print(f"  [ERROR] JSON parse failed: {parse_err}")
                    print(f"  [RAW OUTPUT SNIPPET] {snippet}")
                    attempts += 1
                    if attempts > retries:
                        raise
                    cur_temp = 0.3 if attempts == 1 else (0.2 if attempts == 2 else 0.1)
                    continue

            def get_or_default(k: str, default: Any) -> Any:
                v = data.get(k, default)
                return v if v is not None else default

            review = {
                "summary": get_or_default("summary", ""),
                "strengths": get_or_default("strengths", ""),
                "weaknesses": get_or_default("weaknesses", ""),
                "questions": get_or_default("questions", ""),
                "rating": int(get_or_default("rating", 3)),
                "confidence": int(get_or_default("confidence", 3)),
                "soundness": int(get_or_default("soundness", 2)),
                "presentation": int(get_or_default("presentation", 2)),
                "contribution": int(get_or_default("contribution", 2)),
            }
            return review

        except Exception as e:
            print(f"[ERROR] generate_review failed: {e}")
            try:
                _GLOBAL_COUNTERS["generate_err"] = _GLOBAL_COUNTERS.get("generate_err", 0) + 1
            except Exception:
                pass
            return {
                "summary": f"Error: {e}",
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


# ========================= wrap to OpenReview-like content =========================

def format_review_as_openreview_content(review: Dict[str, Any]) -> Dict[str, Any]:
    """Convert flat review dict to OpenReview-like content structure.

    Example:
    {
      "summary": {"value": "..."},
      "rating":  {"value": 6},
      ...
    }
    """
    content: Dict[str, Any] = {}
    for key in ["summary", "strengths", "weaknesses", "questions"]:
        if key in review:
            content[key] = {"value": review[key]}
    for key in ["rating", "confidence", "soundness", "presentation", "contribution"]:
        if key in review and isinstance(review[key], int):
            content[key] = {"value": review[key]}
    return content


# ================================== main ===================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Use Qwen3-8B (vLLM OpenAI API) to generate weaker baseline reviews "
            "for DPO (rejected side)."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="/remote-home1/bwli/get_open_review/qwen_review/extracted_contents",
        help="Directory of paper text files; one .txt per paper, filename as paper_id.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output",
        help="Output directory path.",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://10.176.59.101:8002/v1",
        help="Qwen3-8B OpenAI-compatible API base URL (vLLM serve).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="qwen3-8b",
        help="Model name (matches vLLM --served-model-name).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=40000,
        help="Max characters of paper content to keep (truncate beyond this).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2000,
        help="Max generation tokens per review.",
    )
    parser.add_argument(
        "--paper-json-dir",
        type=str,
        default="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/iclr2025_first_review_2k",
        help="Directory of original paper JSONs (by forum id) to fetch metadata.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process first N papers (for debugging).",
    )

    args = parser.parse_args()
    strictness_list = ["lenient", "moderate", "strict"]

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"[FATAL] input dir not found: {input_dir}")
        return

    paper_files = sorted(input_dir.glob("*.txt"))
    if args.limit is not None:
        paper_files = paper_files[: args.limit]

    script_dir = Path(__file__).parent
    out_dir = Path(args.output)
    if not out_dir.is_absolute():
        out_dir = script_dir / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("Qwen3-8B Rejected Review Generator")
    print("=" * 80)
    print(f"Model      : {args.model} @ {args.base_url}")
    print(f"Input dir  : {input_dir}")
    print(f"Output dir : {out_dir}")
    print(f"Max chars Paper Input  : {args.max_chars}")
    print(f"Max tokens generate : {args.max_tokens}")
    print(f"Strictness : {strictness_list}")
    print(f"#Papers number   : {len(paper_files)}")
    print("=" * 80)

    reviewer_ai = ReviewerAI(
        base_url=args.base_url,
        model_name=args.model,
    )

    results: Dict[str, Any] = {}

    for idx, paper_file in enumerate(paper_files, 1):
        paper_id = paper_file.stem
        out_file = out_dir / f"{paper_id}.json"
        if out_file.exists() and out_file.stat().st_size > 0:
            print(f"[{idx}/{len(paper_files)}] Skip existing paper: {paper_id}")
            continue

        print(f"\n[{idx}/{len(paper_files)}] Paper: {paper_id}")
        try:
            paper_content = paper_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  [ERROR] Failed to read file: {e}")
            paper_content = f"[READ ERROR: {e}]"

        # truncate using max_chars setting
        if len(paper_content) > args.max_chars:
            paper_content = paper_content[: args.max_chars] + "\n\n[Paper content truncated due to length...]"

        # load paper metadata (forum/number/title/abstract) from JSON directory
        forum = paper_id
        number: Optional[int] = None
        title: Optional[str] = None
        abstract: Optional[str] = None
        try:
            meta_path = Path(args.paper_json_dir) / f"{paper_id}.json"
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as mf:
                    meta = json.load(mf)
                forum = meta.get("forum", forum)
                number = meta.get("number")
                title = meta.get("title")
                abstract = meta.get("abstract")
        except Exception as e:
            print(f"  [WARN] Failed to load metadata for {paper_id}: {e}")

        ai_reviews: List[Dict[str, Any]] = []

        for s in strictness_list:
            print(f"  -> Generating rejected review (strictness={s}) ...")
            start = time.time()
            review = reviewer_ai.generate_review(
                paper_content=paper_content,
                strictness=s,
                temperature=0.6,
                max_tokens=args.max_tokens,
            )
            elapsed = time.time() - start
            if review.get("rating", -1) != -1:
                print(f"     OK, rating={review.get('rating')}, time={elapsed:.1f}s")
            else:
                print(f"     FAILED, time={elapsed:.1f}s: {review.get('error')}")

            ai_reviews.append(
                {
                    "strictness": s,
                    "reviewer_id": f"ai_{s}",
                    "review": review,
                }
            )

        payload = {
            "paper_forum": forum,
            "paper_number": number,
            "paper_title": title,
            "paper_abstract": abstract,
            "ai_reviews": ai_reviews,
        }
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"  Saved: {out_file}")

    print("\nDone.")
    print(f"All results saved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
