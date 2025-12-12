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
            meta_paper_info = {
                'forum_id':forum_id,
                'title': submission.content['title']['value'],
                'abstract': submission.content['abstract']['value'],
                'meta_review': '',
                'comments_on_reviewer_discussion': '',
                'decision': '',
                'number_of_reviewers': 0,
                'rebuttal_chains': {}
            }

            # 过滤撤稿
            if submission.content.get('venue', {}).get('value') == 'ICLR 2025 Conference Withdrawn Submission':
                skipped += 1
                if skipped % REQUEST_LOG_EVERY == 0:
                    print(f"[INFO] Skipped {skipped} withdrawn submissions...")
                continue

            details = submission.details
            Official_Review = [reply for reply in details["replies"] if reply["invitations"][0].endswith("Official_Review")]
            Official_Comment = [
                reply for reply in details["replies"] 
                if reply["invitations"][0].endswith("Official_Comment") 
                and not any("Authors" in s for s in reply.get("signatures", []))
            ]
            Author_Comment = [reply for reply in details["replies"] 
                if reply["invitations"][0].endswith("Official_Comment") 
                and any("Authors" in s for s in reply.get("signatures", []))
            ]
            Meta_Review = next((reply for reply in details["replies"] if reply["invitations"][0].endswith("Meta_Review")), None)
            Decision = next((reply for reply in details["replies"] if reply["invitations"][0].endswith("Decision")), None)
            
            # 填充Decision
            meta_paper_info['decision'] = Decision["content"]["decision"]["value"]
            # 填充MetaReview
            meta_paper_info['meta_review'] = Meta_Review["content"]["metareview"]["value"]
            meta_paper_info['comments_on_reviewer_discussion'] = Meta_Review["content"]["comments_on_reviewer_discussion"]["value"]

            
            events: List[Dict[str, Any]] = []
            # 1. Process Official Reviews
            for reply in Official_Review:
                event_basic = {
                    "note_id": reply.get("id"),
                    "forum": reply.get("forum"),
                    "cdate": reply.get("cdate"),
                    "replyto": reply.get("replyto"),
                    "signatures": reply.get("signatures", []),
                    "role": "reviewer",
                    "reply_type": "review",
                    "content": reply.get("content", {})
                }
                
                versions = get_review_versions(client, event_basic)
                for version in versions:
                    ms = version["cdate"] or 0
                    events.append({
                        "note_id": version["note_id"],
                        "edit_id": version["edit_id"],
                        "replyto": version["replyto"],
                        "signatures": event_basic["signatures"],
                        "actor": "reviewer",
                        "event_type": "review_version",
                        "version_index": version["version_index"],
                        "timestamp": to_iso_time(ms),
                        "time_ms": ms,
                        "content": version["content"],
                    })

            # 2. Process Official Comments (Only Reviewers)
            for reply in Official_Comment:
                # 只保留 Reviewer 的评论，忽略 AC 或其他人的评论
                if not any("Reviewer" in s for s in reply.get("signatures", [])):
                    continue
                    
                ms = reply.get("cdate") or 0
                events.append({
                    "note_id": reply.get("id"),
                    "replyto": reply.get("replyto"),
                    "actor": "reviewer",
                    "event_type": "reviewer_comment",
                    "timestamp": to_iso_time(ms),
                    "time_ms": ms,
                    "signatures": reply.get("signatures"),
                    "content": reply.get("content", {}),
                })

            # 3. Process Author Comments
            for reply in Author_Comment:
                ms = reply.get("cdate") or 0
                events.append({
                    "note_id": reply.get("id"),
                    "replyto": reply.get("replyto"),
                    "actor": "author",
                    "event_type": "author_comment",
                    "timestamp": to_iso_time(ms),
                    "time_ms": ms,
                    "signatures": reply.get("signatures"),
                    "content": reply.get("content", {}),
                })

            if not events:
                record = {
                    "forum": forum_id,
                    "number": getattr(submission, 'number', None),
                    "title": meta_paper_info['title'],
                    "abstract": meta_paper_info['abstract'],
                    "decision": None,
                    "rebuttal_chain": {},
                    "meta_review_info": meta_paper_info
                }
            else:
                events.sort(key=lambda e: e.get("time_ms") or 0)
                decision = meta_paper_info['decision'] or detect_decision_from_events(events)
                per_reviewer, _ = build_per_reviewer_chains(events)
                
                record = {
                    "forum": forum_id,
                    "number": getattr(submission, 'number', None),
                    "title": meta_paper_info['title'],
                    "abstract": meta_paper_info['abstract'],
                    "decision": decision,
                    "rebuttal_chain": per_reviewer,
                    "meta_review_info": meta_paper_info
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