#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import re
import time
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from collections import deque

from ReviewMT.src.nature_make import content
import openreview
from tqdm import tqdm

# ========== 配置区域 ==========
VENUE_ID = "ICLR.cc/2025/Conference"
BASEURL = "https://api2.openreview.net"
OUT_DIR = "/remote-home1/bwli/get_open_review/dataset/data/iclr2025_forums_clear"  # 每篇论文一个 <forum>.json

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


def classify_reply(reply: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not reply:
        return None
    note_id = reply.get("id")
    cdate: int = reply.get("cdate")
    replyto = reply.get("replyto")
    invitations: List[str] = reply.get("invitations", []) or []
    signatures: List[str] = reply.get("signatures", []) or []

    def endswith_any(suffixes: List[str]) -> bool:
        return any(invitation.endswith(suffix) for invitation in invitations for suffix in suffixes)

    if endswith_any(["Official_Review"]):
        role = "reviewer"
        reply_type = "review"
    elif endswith_any(["Meta_Review"]):
        role = "area_chair"
        reply_type = "meta_review"
    elif endswith_any(["Decision"]):
        role = "program_chair"
        reply_type = "decision"
    elif endswith_any(["Official_Comment", "Comment", "Public_Comment"]):
        if any("Authors" in signature for signature in signatures):
            role = "author"
            reply_type = "author_comment"
        elif any("Reviewer" in signature for signature in signatures):
            role = "reviewer"
            reply_type = "reviewer_comment"
        else:
            role = "other"
            reply_type = "other_comment"
    else:
        role = "other"
        reply_type = "other_comment"
    return {
        "note_id": note_id,
        "forum": reply.get("forum"),
        "cdate": cdate,
        "replyto": replyto,
        "signatures": signatures,
        "role": role,
        "reply_type": reply_type,
        "content": reply.get("content", {}) or {},  
    }


def get_review_versions(
    client: "openreview.api.OpenReviewClient",
    event_basic: Dict[str, Any],
) -> List[Dict[str, Any]]:
    
    note_id = event_basic["note_id"]
    
    # 拿到reviewer的 version快照
    try:
        edits = api_call(client.get_note_edits, note_id=note_id) or []
    except Exception as e:
        print(f"[WARN] get_note_edits failed for note {note_id}: {e}")
        edits = []

    versions: List[Dict[str, Any]] = []
    
    # 1. 收集历史 Edits 并按时间排序
    if edits:
        # 按创建时间正序排序 (Oldest -> Newest)
        edits = sorted(edits, key=lambda e: e.cdate or 0)
        
        for edit in edits:
            note = edit.note
            content = note.content or {}
            # 忽略无内容的 edit
            if not content:
                continue
            
            # 简单的去重逻辑：如果和上一个版本内容一致，则跳过
            if versions and versions[-1]["content"] == content:
                continue

            versions.append({
                "note_id": note.id,
                "edit_id": edit.id,
                "cdate": edit.cdate,
                "replyto": event_basic["replyto"],
                "content": content,
            })

    # 2. 处理当前最新状态
    current_content = event_basic["content"] or {}
    
    # 如果没有历史版本，或者当前内容与最后一个历史版本不同，则将当前内容作为最新版本追加
    if not versions or (current_content and versions[-1]["content"] != current_content):
        # 注意：这里的时间戳我们优先使用 mdate (修改时间)，如果没有则用 cdate
        current_time = event_basic.get("mdate", event_basic.get("cdate"))
        
        versions.append({
            "note_id": note_id,
            "edit_id": None,
            "cdate": current_time,
            "replyto": event_basic["replyto"],
            "content": current_content,
        })

    # 3. 分配版本号
    for i, version in enumerate(versions, start=1):
        version["version_index"] = i

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
    for event in events:
        content = event.get("content") or {}
        if "withdrawal_confirmation" in content:
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
    client = openreview.api.OpenReviewClient(baseurl=BASEURL)
    os.makedirs(OUT_DIR, exist_ok=True)

    print("[INFO] Loading submissions with replies ...")
    # 这一调用内部会做很多请求，无法逐次限速；若此处触发 429，交给 openreview 内部处理。
    # 我们仍用 api_call 包一层，以便遇到网络瞬时错误时重试。
    submissions = api_call(
        client.get_all_notes,
        invitation=f"{VENUE_ID}/-/Submission",
        details="replies"
    )
    print(f"[INFO] Loaded {len(submissions)} submissions")

    skipped = 0
    processed = 0
    errors = 0

    for idx, submission in enumerate(tqdm(submissions, desc="Processing submissions")):
        paper_data = vars(submission).copy()
        forum_id = paper_data['forum']
        out_path = os.path.join(OUT_DIR, f"{forum_id}.json")
        out_tmp = out_path + ".tmp"

        # 断点续跑：已有且非空则跳过
        if not OVERWRITE_EXISTING and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            skipped += 1
            if skipped % REQUEST_LOG_EVERY == 0:
                print(f"[INFO] Skipped {skipped} existing files...")
            continue
        try:
            number = paper_data.get('number')
            
            content = paper_data.get('content', {})
            title = content.get('title', {}).get('value', '')
            # 使用 .get().get() 链式调用，防止字段不存在导致的 KeyError
            abstract = content.get('abstract', {}).get('value', '')
            
            details = paper_data.get('details', {})
            raw_replies = (details.get("replies", []) or [])
            events: List[Dict[str, Any]] = []

            # 分类 + 展开事件
            for reply in raw_replies:
                event_basic = classify_reply(reply)

                # 对于评审查找评审的各种版本
                if event_basic["reply_type"] == "review":
                    versions = get_review_versions(client, event_basic)
                    for version in versions:
                        ms = version["cdate"] or 0
                        events.append({
                            "note_id": version["note_id"],
                            "edit_id": version["edit_id"],
                            "replyto": version["replyto"],
                            "signatures": event_basic.get("signatures"),
                            "actor": "reviewer",
                            "event_type": "review_version",
                            "version_index": version["version_index"],
                            "timestamp": to_iso_time(ms),
                            "time_ms": ms,
                            "content": version["content"],
                        })
                else:
                    ms = event_basic["cdate"] or 0
                    events.append({
                        "note_id": event_basic["note_id"],
                        "replyto": event_basic["replyto"],
                        "actor": event_basic["role"], 
                        "event_type": event_basic["type"],
                        "timestamp": to_iso_time(ms),
                        "time_ms": ms,
                        "signatures": event_basic.get("signatures"),
                        "content": event_basic["content"],
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
                decision = detect_decision_from_events(events)
                per_reviewer, global_events = build_per_reviewer_chains(events)
                

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