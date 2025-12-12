#!/usr/bin/env python
# -*- coding: utf-8 -*-

from inspect import signature
import json
import os
import re
import time
from typing import List, Dict, Any
from datetime import datetime, timezone
from collections import deque
import openreview
from tqdm import tqdm

# ========== 配置区域 ==========
VENUE_ID = "ICLR.cc/2024/Conference"
BASEURL = "https://api2.openreview.net"
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "iclr2024")

# ---- 速率限制 / 重试配置 ----
MAX_CALLS_PER_MIN = 80          # 每 60s 最多调用数（低于服务端 200 的上限，留余量）
MAX_RETRIES = 8                  # 单次 API 调用最大重试次数
BASE_BACKOFF_SEC = 1.0           # 指数退避起始等待
REQUEST_LOG_EVERY = 20          # 打印跳过/处理进度频率

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
    m = re.search(r"try again in\s+(\d+)\s+seconds", msg, re.IGNORECASE)
    if m:
        return max(1.0, float(m.group(1)) + 0.5)
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
            # 429 限流错误：按建议等待
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
    latest_review: Dict[str, Any],
) -> List[Dict[str, Any]]:
    
    note_id = latest_review["id"]
    
    # 拿到reviewer的 version快照
    try:
        edits = api_call(client.get_note_edits, note_id=note_id) or []
    except Exception as e:
        print(f"[WARN] get_note_edits failed for note {note_id}: {e}")
        edits = []

    versions: List[Dict[str, Any]] = []
    last_content = None

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
            if content == last_content:
                continue
            last_content = content

            versions.append({
                "note_id": note.id,
                "replyto": latest_review["replyto"],
                "actor": "reviewer",
                "signatures": note.signatures,
                "event_type": "review_version",
                "edit_id": edit.id,
                "version_index": len(versions) + 1,
                "time_stamp": to_iso_time(edit.cdate),
                "time_ms": edit.cdate,
                "summary": content["summary"]['value'],
                "strengths": content["strengths"]['value'],
                "weaknesses": content["weaknesses"]['value'], 
                "questions": content["questions"]['value'],
                "soundness": content["soundness"]['value'], 
                "presentation": content["presentation"]['value'],
                "contribution": content["contribution"]['value'], 
                "rating": content["rating"]['value'],
                "confidence": content["confidence"]['value'],
            })

    # 2. 处理当前最新状态
    current_content = latest_review.get("content", {})
    
    # 如果没有历史版本，或者当前内容与最后一个历史版本不同，则将当前内容作为最新版本追加
    if not versions or (current_content and current_content != last_content):
        # 注意：这里的时间戳我们优先使用 mdate (修改时间)，如果没有则用 cdate
        current_time = latest_review.get("mdate", latest_review.get("cdate"))
        # current_content 已经在上面获取过了，不需要重新获取
        
        versions.append({
            "note_id": note_id,
            "replyto": latest_review["replyto"],
            "actor": "reviewer",
            "signatures": latest_review['signatures'],
            "event_type": "review_version",
            "edit_id": None,
            "version_index": len(versions) + 1,
            "time_stamp": to_iso_time(current_time),
            "time_ms": current_time,
            "summary": current_content["summary"]['value'],
            "strengths": current_content["strengths"]['value'],
            "weaknesses": current_content["weaknesses"]['value'],
            "soundness": current_content["soundness"]['value'],
            "questions": current_content["questions"]['value'], 
            "presentation": current_content["presentation"]['value'],
            "contribution": current_content["contribution"]['value'], 
            "rating": current_content["rating"]['value'],
            "confidence": current_content["confidence"]['value'],
        })

    # # 3. 分配版本号
    # for i, version in enumerate(versions, start=1):
    #     version["version_index"] = i
    return versions


def to_iso_time(ms: int) -> str:
    if not ms:
        return None
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.isoformat()


def build_per_reviewer_chains(
    events: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    review_roots: List[Dict[str, Any]] = [
        event for event in events
        if event.get("event_type") == "review_version"
        and event.get("version_index") == 1
    ]

    per_reviewer: Dict[str, List[Dict[str, Any]]] = {}
    note_to_reviewer: Dict[str, str] = {}

    for root_review in review_roots:
        # Review的id
        reviewer_id = next((signature.split("/")[-1] for signature in root_review["signatures"] if "Reviewer" in signature), None)
        
        if not reviewer_id:
            continue
        per_reviewer.setdefault(reviewer_id, []).append(root_review)
        note_to_reviewer[root_review["note_id"]] = reviewer_id

    for event in events:
        if event.get("event_type") == "review_version":
            note_id = event["note_id"]
            review_id = note_to_reviewer.get(note_id)
            if review_id and event not in per_reviewer.get(review_id, []):
                per_reviewer[review_id].append(event)

    # 通过 replyto 传播归属
    changed = True
    while changed:
        changed = False
        for event in events:
            note_id = event.get("note_id")
            if not note_id or note_id in note_to_reviewer:
                continue
            replyto = event.get("replyto")
            if replyto and replyto in note_to_reviewer:
                note_to_reviewer[note_id] = note_to_reviewer[replyto]
                changed = True

    # 分配非 review 事件
    for event in events:
        if event.get("event_type") == "review_version":
            continue
        note_id = event.get("note_id")
        review_id = note_to_reviewer.get(note_id)
        if review_id:
            per_reviewer.setdefault(review_id, []).append(event)

    # 每条链按时间排序
    for review_id, evts in per_reviewer.items():
        evts.sort(key=lambda x: x.get("time_ms") or 0)

    return per_reviewer

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
            record = {
                'forum_id':forum_id,
                'number': submission.number,
                'title': submission.content['title']['value'],
                'abstract': submission.content['abstract']['value'],
                'meta_review': '',
                'comments_on_reviewer_discussion': '',
                'decision': '',
                'number_of_reviewers': 0,
                'rebuttal_chains': {}
            }

            # 过滤撤稿 和 桌面拒稿
            venue_value = submission.content.get('venue', {}).get('value', '')
            if 'Withdrawn' in venue_value or 'Desk Rejected' in venue_value:
                skipped += 1
                if skipped % REQUEST_LOG_EVERY == 0:
                    print(f"[INFO] Skipped {skipped} withdrawn/rejected submissions...")
                continue

            details = submission.details
            Official_Review = [
                reply for reply in details["replies"] 
                if reply["invitations"][0].endswith("Official_Review")
            ]
            Review_Comment = [
                reply for reply in details["replies"] 
                if reply["invitations"][0].endswith("Official_Comment") 
                and any("Reviewer" in signature for signature in reply.get("signatures", []))
            ]
            Author_Comment = [
                reply for reply in details["replies"] 
                if reply["invitations"][0].endswith("Official_Comment") 
                and any("Authors" in s for s in reply.get("signatures", []))
            ]

            Meta_Review = next((reply for reply in details["replies"] if reply["invitations"][0].endswith("Meta_Review")), None)
            Decision = next((reply for reply in details["replies"] if reply["invitations"][0].endswith("Decision")), None)
            
            # 填充Decision
            if Decision:
                record['decision'] = Decision.get("content", {}).get("decision", {}).get("value")

            # 填充MetaReview
            if Meta_Review:
                meta_content = Meta_Review.get("content", {})
                record['meta_review'] = meta_content.get("metareview", {}).get("value")
                record['comments_on_reviewer_discussion'] = meta_content.get("comments_on_reviewer_discussion", {}).get("value", "")


            events: List[Dict[str, Any]] = []
            # 1. Process Official Reviews
            for latest_review in Official_Review:
                versions = get_review_versions(client, latest_review)
                for version in versions:
                    events.append(version)

            # 2. Process Review_Comments
            for reply in Review_Comment:
                ms = reply.get("cdate") or 0
                events.append({
                    "note_id": reply.get("id"),
                    "replyto": reply.get("replyto"),
                    "actor": "reviewer",                   
                    "signatures": reply.get("signatures"),
                    "event_type": "reviewer_comment",
                    "timestamp": to_iso_time(ms),
                    "time_ms": ms,
                    "content": reply.get("content", {}).get("comment", {}).get("value"),
                })

            # 3. Process Author Comments
            for reply in Author_Comment:
                ms = reply.get("cdate") or 0
                events.append({
                    "note_id": reply.get("id"),
                    "replyto": reply.get("replyto"),
                    "actor": "author",
                    "signatures": reply.get("signatures"),
                    "event_type": "author_comment",
                    "timestamp": to_iso_time(ms),
                    "time_ms": ms,
                    "content": reply.get("content", {}).get("comment", {}).get("value"),
                })

            if events:
                events.sort(key=lambda event: event.get("time_ms") or 0)
                per_reviewer = build_per_reviewer_chains(events)
                record['number_of_reviewers'] = len(per_reviewer)
                record['rebuttal_chains'] = per_reviewer

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