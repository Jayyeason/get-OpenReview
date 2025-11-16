#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
从 OpenReview 抽取 ICLR 2025 的完整评审交互数据（带速率限制与断点续跑）。

输出（每篇论文一个 JSON 文件，文件名为 <forum>.json）：

{
  "forum": "zxg6601zoc",
  "title": "...",
  "abstract": "...",                 # 摘要
  "decision": "Accept|Reject|Withdrawn|null",  # 尽力从事件中判定
  "rebuttal_chain": {                # 每位评审一条链
    "Reviewer_XXXX": [
      {
        "time": "...ISO...",
        "time_ms": 1730...,
        "actor": "reviewer" | "author" | "ac" | "pc" | "other",
        "event_type": "review_version" | "author_comment" | ...,
        "version_index": 1,         # 仅 review_version 有
        "note_id": "...",
        "replyto": "... or null ...",
        "signatures": [...原始签名列表...],
        "content": {...原始 content ...}
      },
      ...
    ],
    "Reviewer_YYYY": [ ... ]
  },
  "other_review": [                  # 不属于任何具体 reviewer 链的事件
    # meta_review, decision, general comment 等
  ]
}
"""

import json
import os
import re
import time
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from collections import deque

import openreview
from tqdm import tqdm

# ========== 配置区域 ==========
VENUE_ID = "ICLR.cc/2025/Conference"
BASEURL = "https://api2.openreview.net"
OUT_DIR = "./data/iclr2025_forum_clear"  # 每篇论文一个 <forum>.json

# ---- 速率限制 / 重试配置 ----
MAX_CALLS_PER_MIN = 180          # 每 60s 最多调用数（低于服务端 200 的上限，留余量）
MAX_RETRIES = 8                  # 单次 API 调用最大重试次数
BASE_BACKOFF_SEC = 1.0           # 指数退避起始等待
REQUEST_LOG_EVERY = 200          # 打印跳过/处理进度频率

# 断点续跑：当输出 JSON 文件已存在且非空时，默认跳过
OVERWRITE_EXISTING = False
# ==============================


# ---- 简单滑窗限速（全局）----
_CALL_TIMES = deque()  # 记录每次 API 调用的时间点（monotonic 秒）

def _throttle():
    """在每次 API 调用前调用，保证 60s 内不超过 MAX_CALLS_PER_MIN 次。"""
    now = time.monotonic()
    window = 60.0
    # 清理过期时间戳
    while _CALL_TIMES and (now - _CALL_TIMES[0]) > window:
        _CALL_TIMES.popleft()
    if len(_CALL_TIMES) >= MAX_CALLS_PER_MIN:
        # 等到最早一次调用滚出 60s 窗口
        sleep_sec = window - (now - _CALL_TIMES[0]) + 0.01
        if sleep_sec > 0:
            time.sleep(sleep_sec)
    _CALL_TIMES.append(time.monotonic())


def _sleep_from_rate_limit_msg(msg: str) -> float:
    """
    解析 OpenReview 429 信息中的推荐等待秒数，没有则给一个保守等待。
    示例信息：
      'Too many requests: ... Please try again in 4 seconds (2025-11-13-5800379)'
    """
    m = re.search(r"try again in\s+(\d+)\s+seconds", msg, re.IGNORECASE)
    if m:
        return max(1.0, float(m.group(1)) + 0.5)
    # 没有明确建议时，给一个温和等待
    return 4.0


def api_call(fn, *args, **kwargs):
    """
    为 openreview 客户端方法提供统一的：限速 + 自动重试（429/瞬时错误）。
    """
    last_exc = None
    backoff = BASE_BACKOFF_SEC
    for attempt in range(1, MAX_RETRIES + 1):
        _throttle()
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            msg = str(e)
            # 429 限流
            if ("Too many requests" in msg) or ("RateLimitError" in msg) or ("status': 429" in msg) or ("status\": 429" in msg):
                wait = _sleep_from_rate_limit_msg(msg)
            else:
                # 其它瞬时错误：指数退避
                wait = min(60.0, backoff)
                backoff *= 1.6
            time.sleep(wait)
    # 多次重试仍失败，抛出
    raise last_exc


# ========== OpenReview 基本封装 ==========
def build_client() -> "openreview.api.OpenReviewClient":
    return openreview.api.OpenReviewClient(baseurl=BASEURL)


def get_submission_name(client: "openreview.api.OpenReviewClient",
                        venue_id: str) -> str:
    venue_group = api_call(client.get_group, venue_id)
    content = getattr(venue_group, "content", {}) or {}
    sub_field = content.get("submission_name", {})
    if isinstance(sub_field, dict):
        return sub_field.get("value", "Submission")
    return "Submission"


def extract_title_from_content(content: Dict[str, Any]) -> str:
    if not content:
        return ""
    t = content.get("title", "")
    if isinstance(t, dict):
        return t.get("value", "")
    if isinstance(t, str):
        return t
    return ""


def extract_abstract_from_content(content: Dict[str, Any]) -> Optional[str]:
    if not isinstance(content, dict):
        return None
    candidates = ["abstract", "Abstract", "paper_abstract", "tl;dr", "TL;DR", "TLDR"]
    for k in candidates:
        v = content.get(k)
        if isinstance(v, dict):
            v = v.get("value")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def classify_reply(r: Dict[str, Any]) -> Dict[str, Any]:
    invitations: List[str] = r.get("invitations", []) or []
    sigs: List[str] = r.get("signatures", []) or []
    nid: str = r.get("id")
    cdate: int = r.get("cdate")
    replyto = r.get("replyto")

    def endswith_any(suffixes: List[str]) -> bool:
        return any(inv.endswith(sfx) for inv in invitations for sfx in suffixes)

    if endswith_any(["Official_Review"]):
        role = "reviewer"
        rtype = "review"
    elif endswith_any(["Meta_Review"]):
        role = "ac"
        rtype = "meta_review"
    elif endswith_any(["Decision"]):
        role = "pc"
        rtype = "decision"
    elif endswith_any(["Rebuttal"]):
        role = "author"
        rtype = "rebuttal"
    elif endswith_any(["Official_Comment", "Comment", "Public_Comment"]):
        if any("Authors" in s for s in sigs):
            role = "author"
            rtype = "author_comment"
        elif any("Area_Chair" in s or "Area_Chairs" in s or "AC" in s for s in sigs):
            role = "ac"
            rtype = "ac_comment"
        elif any("Reviewer" in s for s in sigs):
            role = "reviewer"
            rtype = "reviewer_comment"
        else:
            role = "other"
            rtype = "comment"
    else:
        role = "other"
        rtype = "other"

    return {
        "note_id": nid,
        "forum": r.get("forum"),
        "cdate": cdate,
        "replyto": replyto,
        "role": role,
        "type": rtype,
        "signatures": sigs,
        "content": r.get("content", {}) or {},
        "invitations": invitations,
    }


def get_review_versions(
    client: "openreview.api.OpenReviewClient",
    evt_basic: Dict[str, Any],
) -> List[Dict[str, Any]]:
    note_id = evt_basic["note_id"]

    try:
        edits = api_call(client.get_note_edits, note_id=note_id) or []
    except Exception as e:
        print(f"[WARN] get_note_edits failed for note {note_id}: {e}")
        edits = []

    versions: List[Dict[str, Any]] = []
    root_content = evt_basic["content"] or {}
    versions.append({
        "note_id": note_id,
        "version_index": 1,
        "cdate": evt_basic["cdate"],
        "replyto": evt_basic["replyto"],
        "signatures": evt_basic["signatures"] or [],
        "content": root_content,
    })

    if edits:
        edits = sorted(edits, key=lambda e: e.cdate or 0)
        prev_content = root_content
        for e in edits:
            note = e.note
            content = note.content or {}
            if not content:
                continue
            if content == prev_content:
                continue
            versions.append({
                "note_id": note.id,
                "cdate": e.cdate,
                "replyto": evt_basic["replyto"],
                "signatures": note.signatures or [],
                "content": content,
            })
            prev_content = content

    for i, v in enumerate(versions, start=1):
        v["version_index"] = i

    return versions


def to_iso_time(ms: int) -> str:
    if not ms:
        return None
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.isoformat()


def extract_reviewer_short_id(signatures: List[str]) -> Optional[str]:
    sigs = signatures or []
    for s in sigs:
        if "Reviewer" in s:
            return s.split("/")[-1]
    return None


def build_per_reviewer_chains(
    events: List[Dict[str, Any]]
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    review_roots: List[Dict[str, Any]] = [
        e for e in events
        if e.get("event_type") == "review_version"
        and e.get("version_index") == 1
    ]

    per_reviewer: Dict[str, List[Dict[str, Any]]] = {}
    note_to_reviewer: Dict[str, str] = {}

    for root in review_roots:
        short_id = extract_reviewer_short_id(root.get("signatures") or [])
        if not short_id:
            continue
        per_reviewer.setdefault(short_id, []).append(root)
        note_to_reviewer[root["note_id"]] = short_id

    for e in events:
        if e.get("event_type") == "review_version":
            nid = e["note_id"]
            rid = note_to_reviewer.get(nid)
            if rid and e not in per_reviewer.get(rid, []):
                per_reviewer[rid].append(e)

    # 通过 replyto 传播归属
    changed = True
    while changed:
        changed = False
        for e in events:
            nid = e.get("note_id")
            if not nid or nid in note_to_reviewer:
                continue
            replyto = e.get("replyto")
            if replyto and replyto in note_to_reviewer:
                note_to_reviewer[nid] = note_to_reviewer[replyto]
                changed = True

    # 分配非 review 事件
    for e in events:
        if e.get("event_type") == "review_version":
            continue
        nid = e.get("note_id")
        rid = note_to_reviewer.get(nid)
        if rid:
            per_reviewer.setdefault(rid, []).append(e)

    # 每条链按时间排序
    for rid, evts in per_reviewer.items():
        evts.sort(key=lambda x: x.get("time_ms") or 0)

    assigned_ids = {
        ev.get("note_id")
        for evts in per_reviewer.values()
        for ev in evts
        if ev.get("note_id")
    }

    global_events = [e for e in events if e.get("note_id") not in assigned_ids]
    global_events.sort(key=lambda x: x.get("time_ms") or 0)

    return per_reviewer, global_events


# ---------- 决策解析 ----------
def _collect_strings_from_content(content: Dict[str, Any]) -> List[str]:
    out = []
    if not isinstance(content, dict):
        return out
    for _, v in content.items():
        if isinstance(v, dict) and "value" in v and isinstance(v["value"], str):
            out.append(v["value"])
        elif isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, str):
                    out.append(it)
                elif isinstance(it, dict) and "value" in it and isinstance(it["value"], str):
                    out.append(it["value"])
    return out


def detect_decision_from_events(events: List[Dict[str, Any]]) -> Optional[str]:
    # 1) 优先判断 Withdrawn
    for e in events:
        c = e.get("content") or {}
        if "withdrawal_confirmation" in c:
            return "Withdrawn"
        texts = " ".join(_collect_strings_from_content(c)).lower()
        if re.search(r"\bwithdraw(n|al|)\b", texts):
            return "Withdrawn"

    # 2) 决策文本
    texts = []
    for e in events:
        if e.get("event_type") == "decision":
            texts += _collect_strings_from_content(e.get("content") or {})
    if not texts:
        for e in events:
            c = e.get("content") or {}
            for k in ["decision", "Decision", "final_decision", "venue", "venueid", "recommendation", "title", "comment"]:
                v = c.get(k)
                if isinstance(v, dict) and "value" in v and isinstance(v["value"], str):
                    texts.append(v["value"])
                elif isinstance(v, str):
                    texts.append(v)

    blob = " ".join(texts).lower().strip()
    if not blob:
        return None
    if re.search(r"\b(accept|oral|spotlight|poster)\b", blob):
        return "Accept"
    if re.search(r"\b(reject|desk\s*reject)\b", blob):
        return "Reject"
    return None


def main():
    client = build_client()
    submission_name = get_submission_name(client, VENUE_ID)
    print(f"[INFO] submission_name = {submission_name}")

    os.makedirs(OUT_DIR, exist_ok=True)

    print("[INFO] Loading submissions with replies ...")
    # 这一调用内部会做很多请求，无法逐次限速；若此处触发 429，交给 openreview 内部处理。
    # 我们仍用 api_call 包一层，以便遇到网络瞬时错误时重试。
    submissions = api_call(
        client.get_all_notes,
        invitation=f"{VENUE_ID}/-/{submission_name}",
        details="replies"
    )
    print(f"[INFO] Loaded {len(submissions)} submissions")

    skipped = 0
    processed = 0
    errors = 0

    for idx, sub in enumerate(tqdm(submissions, desc="Processing submissions")):
        forum_id = sub.forum
        out_path = os.path.join(OUT_DIR, f"{forum_id}.json")
        out_tmp = out_path + ".tmp"

        # 断点续跑：已有且非空则跳过
        if not OVERWRITE_EXISTING and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            skipped += 1
            if skipped % REQUEST_LOG_EVERY == 0:
                print(f"[INFO] Skipped {skipped} existing files...")
            continue

        try:
            number = getattr(sub, "number", None)
            title = extract_title_from_content(sub.content or {})
            abstract = extract_abstract_from_content(sub.content or {})

            raw_replies = (sub.details.get("replies", []) or [])
            events: List[Dict[str, Any]] = []

            # 分类 + 展开事件
            for r in raw_replies:
                evt_basic = classify_reply(r)

                if evt_basic["type"] == "review":
                    versions = get_review_versions(client, evt_basic)
                    for v in versions:
                        ms = v["cdate"] or 0
                        events.append({
                            "time": to_iso_time(ms),
                            "time_ms": ms,
                            "actor": "reviewer",
                            "event_type": "review_version",
                            "version_index": v["version_index"],
                            "note_id": v["note_id"],
                            "replyto": v["replyto"],
                            "signatures": v["signatures"],
                            "content": v["content"],
                        })
                else:
                    ms = evt_basic["cdate"] or 0
                    events.append({
                        "time": to_iso_time(ms),
                        "time_ms": ms,
                        "actor": evt_basic["role"],       # 'author' / 'ac' / 'reviewer' / 'pc' / 'other'
                        "event_type": evt_basic["type"],  # 'author_comment' / 'reviewer_comment' / ...
                        "note_id": evt_basic["note_id"],
                        "replyto": evt_basic["replyto"],
                        "signatures": evt_basic["signatures"],
                        "content": evt_basic["content"],
                    })

            if not events:
                record = {
                    "forum": forum_id,
                    "number": number,
                    "title": title,
                    "abstract": abstract,
                    "decision": None,
                    "rebuttal_chain": {},
                    "other_review": [],
                }
            else:
                events.sort(key=lambda e: e.get("time_ms") or 0)
                per_reviewer, global_events = build_per_reviewer_chains(events)
                decision = detect_decision_from_events(events)

                record = {
                    "forum": forum_id,
                    "number": number,
                    "title": title,
                    "abstract": abstract,
                    "decision": decision,
                    "rebuttal_chain": per_reviewer,
                    "other_review": global_events,
                }

            # 原子写入：先写 .tmp，再 rename
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_tmp, "w", encoding="utf-8") as f_out:
                json.dump(record, f_out, ensure_ascii=False, indent=2)
            os.replace(out_tmp, out_path)

            processed += 1
            if processed % REQUEST_LOG_EVERY == 0:
                print(f"[INFO] Processed {processed} submissions...")
        except Exception as e:
            errors += 1
            # 清理可能残留的 tmp 文件，避免下次 resume 识别为已完成
            try:
                if os.path.exists(out_tmp):
                    os.remove(out_tmp)
            except Exception:
                pass
            print(f"[ERROR] Failed on forum={forum_id}: {e}")

    print(f"[INFO] Done. Total: {len(submissions)}, processed: {processed}, skipped: {skipped}, errors: {errors}")
    print(f"[INFO] Saved JSON files under {OUT_DIR}/")


if __name__ == "__main__":
    main()