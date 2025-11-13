#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
从 OpenReview 抽取 ICLR 2025 的完整评审交互数据。

结构（每篇论文一个 JSON 文件，文件名为 <forum>.json）：

{
  "forum": "zxg6601zoc",
  "number": 1371,
  "title": "...",
  "abstract": "...",                 # ★ 新增
  "decision": "Accept|Reject|Withdrawn|null",  # ★ 新增（尽力从事件中判定）
  "per_reviewer": {
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
  "global": [
    # 不属于任何具体 reviewer 链的事件：meta_review, decision,
    # 对整个 forum 的 general comment 等
  ]
}
"""

import json
import os
import re
from typing import List, Dict, Any, Tuple, Optional

from datetime import datetime, timezone

import openreview
from tqdm import tqdm


# ========== 配置区域 ==========
VENUE_ID = "ICLR.cc/2025/Conference"
BASEURL = "https://api2.openreview.net"

OUT_DIR = "./data/iclr2025_forums"  # 每篇论文一个 <forum>.json
# ==============================


def build_client() -> "openreview.api.OpenReviewClient":
    """构建 OpenReview v2 client（匿名访问，不带用户名密码）"""
    client = openreview.api.OpenReviewClient(
        baseurl=BASEURL
    )
    return client


def get_submission_name(client: "openreview.api.OpenReviewClient",
                        venue_id: str) -> str:
    """从 venue group 里拿 submission_name，拿不到就退回 'Submission'"""
    venue_group = client.get_group(venue_id)
    content = getattr(venue_group, "content", {}) or {}
    sub_field = content.get("submission_name", {})
    if isinstance(sub_field, dict):
        return sub_field.get("value", "Submission")
    return "Submission"


def extract_title_from_content(content: Dict[str, Any]) -> str:
    """
    兼容一下不同 schema 的 title：
      - 新版：{"title": {"value": "xxx"}}
      - 有些情况：{"title": "xxx"}
    """
    if not content:
        return ""
    t = content.get("title", "")
    if isinstance(t, dict):
        return t.get("value", "")
    if isinstance(t, str):
        return t
    return ""


def extract_abstract_from_content(content: Dict[str, Any]) -> Optional[str]:
    """
    尽力从 submission.content 取摘要。常见键：
      abstract / Abstract / paper_abstract / TL;DR / TLDR / tl;dr
    """
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
    """
    把一条 reply 粗分类：评审 / rebuttal / AC comment / meta-review / decision / 其它

    输入 r 是 submission.details['replies'] 里的一个 dict，典型字段：
      - id, forum, cdate, signatures, invitations, content, replyto, ...
    """
    invitations: List[str] = r.get("invitations", []) or []
    sigs: List[str] = r.get("signatures", []) or []
    nid: str = r.get("id")
    cdate: int = r.get("cdate")
    replyto = r.get("replyto")

    def endswith_any(suffixes: List[str]) -> bool:
        return any(inv.endswith(sfx) for inv in invitations for sfx in suffixes)

    # 1) 正式评审
    if endswith_any(["Official_Review"]):
        role = "reviewer"
        rtype = "review"

    # 2) Meta-review（AC 总结）
    elif endswith_any(["Meta_Review"]):
        role = "ac"
        rtype = "meta_review"

    # 3) 最终 decision
    elif endswith_any(["Decision"]):
        role = "pc"
        rtype = "decision"

    # 4) 专门的 Rebuttal 表单（如果会议启用）
    elif endswith_any(["Rebuttal"]):
        role = "author"
        rtype = "rebuttal"

    # 5) Comment / Official_Comment / Public_Comment
    elif endswith_any(["Official_Comment", "Comment", "Public_Comment"]):
        # 根据签名猜是谁
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
    """
    对于一条“评审 note”（原始 reply 已经被 classify_reply 处理成 evt_basic），
    构造完整版本序列 v1, v2, ...

    - v1：用原始 reply 的内容（evt_basic），时间 = 原始 cdate
    - v2+：用 get_note_edits(note_id=...) 返回的各版本快照，时间 = edit.cdate
    """
    note_id = evt_basic["note_id"]

    # 先尝试拿 edits（可能为空）
    try:
        edits = client.get_note_edits(note_id=note_id) or []
    except Exception as e:
        print(f"[WARN] get_note_edits failed for note {note_id}: {e}")
        edits = []

    versions: List[Dict[str, Any]] = []

    # v1 = 原始评审
    versions.append({
        "note_id": note_id,
        "version_index": 1,
        "cdate": evt_basic["cdate"],
        "replyto": evt_basic["replyto"],
        "signatures": evt_basic["signatures"] or [],
        "content": evt_basic["content"] or {},
    })

    # v2, v3, ... = edit 之后的版本
    if edits:
        edits = sorted(edits, key=lambda e: e.cdate or 0)
        idx_base = 2
        for i, e in enumerate(edits):
            note = e.note
            versions.append({
                "note_id": note.id,
                "version_index": idx_base + i,
                "cdate": e.cdate,
                "replyto": evt_basic["replyto"],  # 评审的 replyto 通常固定为 forum
                "signatures": note.signatures or [],
                "content": note.content or {},
            })

    return versions


def to_iso_time(ms: int) -> str:
    """把毫秒时间戳转换成 ISO8601 字符串，UTC 时区"""
    if not ms:
        return None
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.isoformat()


def extract_reviewer_short_id(signatures: List[str]) -> Optional[str]:
    """
    从 signatures 里抽取 reviewer 的短 id：
    "ICLR.cc/2025/Conference/Submission7754/Reviewer_8r4h" → "Reviewer_8r4h"
    """
    sigs = signatures or []
    for s in sigs:
        if "Reviewer" in s:
            return s.split("/")[-1]
    return None


def build_per_reviewer_chains(
    events: List[Dict[str, Any]]
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """
    把所有事件按 reviewer 分成多条 rebuttal 链。

    输入：同一个 submission 的所有事件（已经有 time_ms / time / replyto 等）
    输出：
      - per_reviewer: { "Reviewer_xxx": [events...], ... }
      - global_events: [events...]   # 没法归到某个 reviewer 的，放这里
    """

    # 1) 找出所有 root review（version_index == 1 的 review_version）
    review_roots: List[Dict[str, Any]] = [
        e for e in events
        if e.get("event_type") == "review_version"
        and e.get("version_index") == 1
    ]

    # reviewer_id -> list of events
    per_reviewer: Dict[str, List[Dict[str, Any]]] = {}
    # note_id -> reviewer_id （用于通过 replyto 传播归属）
    note_to_reviewer: Dict[str, str] = {}

    # 1.1 初始化每个 reviewer 的链，并把 root review 放进去
    for root in review_roots:
        short_id = extract_reviewer_short_id(root.get("signatures") or [])
        if not short_id:
            continue

        if short_id not in per_reviewer:
            per_reviewer[short_id] = []

        per_reviewer[short_id].append(root)
        note_to_reviewer[root["note_id"]] = short_id

    # 1.2 把同一个 review 的其它版本（v2, v3, ...）也加入各自 reviewer
    for e in events:
        if e.get("event_type") == "review_version":
            nid = e["note_id"]
            rid = note_to_reviewer.get(nid)
            if rid and e not in per_reviewer[rid]:
                per_reviewer[rid].append(e)

    # 2) 用 replyto 关系，把非 review 事件，也归到对应 reviewer 链

    # 2.1 构建 note_id -> 事件 的索引（如果需要可以扩展）
    id_to_event: Dict[str, Dict[str, Any]] = {
        e["note_id"]: e for e in events if e.get("note_id")
    }

    # 2.2 通过 replyto 把 note_id 的归属往下传播；多轮直到稳定
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

    # 2.3 把非 review 事件按 note_to_reviewer 分配到 per_reviewer
    for e in events:
        if e.get("event_type") == "review_version":
            continue
        nid = e.get("note_id")
        rid = note_to_reviewer.get(nid)
        if rid:
            if rid not in per_reviewer:
                per_reviewer[rid] = []
            per_reviewer[rid].append(e)

    # 3) 对每个 reviewer 的链按时间排序
    for rid, evts in per_reviewer.items():
        evts.sort(key=lambda x: x.get("time_ms") or 0)

    # 4) 剩下没分配到任何 reviewer 的事件 → global
    assigned_ids = set(
        ev["note_id"]
        for evts in per_reviewer.values()
        for ev in evts
        if ev.get("note_id")
    )

    global_events = [
        e for e in events
        if e.get("note_id") not in assigned_ids
    ]
    global_events.sort(key=lambda x: x.get("time_ms") or 0)

    return per_reviewer, global_events


# ---------- 新增：决策解析 ----------
def _collect_strings_from_content(content: Dict[str, Any]) -> List[str]:
    out = []
    if not isinstance(content, dict):
        return out
    for k, v in content.items():
        if isinstance(v, dict) and "value" in v:
            val = v.get("value")
            if isinstance(val, str):
                out.append(val)
        elif isinstance(v, str):
            out.append(v)
        # 保守处理：列表中的字符串
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, str):
                    out.append(it)
                elif isinstance(it, dict) and "value" in it and isinstance(it["value"], str):
                    out.append(it["value"])
    return out


def detect_decision_from_events(events: List[Dict[str, Any]]) -> Optional[str]:
    """
    优先判断 Withdrawn；否则在 decision 事件与常见字段中搜索。
    返回：
      - "Withdrawn" | "Accept" | "Reject" | None
    """
    # 1) 撤稿优先：看任何事件 content 是否包含 withdrawal_confirmation 或关键词
    for e in events:
        c = e.get("content") or {}
        if "withdrawal_confirmation" in c:
            return "Withdrawn"
        texts = " ".join(_collect_strings_from_content(c)).lower()
        if re.search(r"\bwithdraw(n|al|)\b", texts):
            return "Withdrawn"

    # 2) 决策文本（优先扫描 event_type == decision）
    texts = []
    for e in events:
        if e.get("event_type") == "decision":
            texts += _collect_strings_from_content(e.get("content") or {})
    # 若决策事件里没有，再全表扫描可能含“venue/decision/recommendation”的字段
    if not texts:
        for e in events:
            c = e.get("content") or {}
            for k in ["decision", "Decision", "final_decision", "venue", "venueid", "recommendation", "title", "comment"]:
                v = c.get(k)
                if isinstance(v, dict) and "value" in v and isinstance(v["value"], str):
                    texts.append(v["value"])
                elif isinstance(v, str):
                    texts.append(v)

    blob = " ".join(texts).lower()
    if not blob.strip():
        return None

    # Accept 的常见标记：accept / oral / spotlight / poster
    if re.search(r"\b(accept|oral|spotlight|poster)\b", blob):
        return "Accept"
    # Reject 的常见标记
    if re.search(r"\b(reject|desk\s*reject)\b", blob):
        return "Reject"

    return None


def main():
    client = build_client()
    submission_name = get_submission_name(client, VENUE_ID)
    print(f"[INFO] submission_name = {submission_name}")

    # 创建输出目录
    os.makedirs(OUT_DIR, exist_ok=True)

    print("[INFO] Loading submissions with replies ...")
    submissions = client.get_all_notes(
        invitation=f"{VENUE_ID}/-/{submission_name}",
        details="replies"
    )
    print(f"[INFO] Loaded {len(submissions)} submissions")

    for sub in tqdm(submissions, desc="Processing submissions"):
        forum_id = sub.forum
        number = getattr(sub, "number", None)
        title = extract_title_from_content(sub.content or {})
        abstract = extract_abstract_from_content(sub.content or {})  # ★ 新增

        raw_replies = sub.details.get("replies", []) or []
        events: List[Dict[str, Any]] = []

        # 遍历所有 reply，先分类，再展开成事件
        for r in raw_replies:
            evt_basic = classify_reply(r)

            # 1) 评审：展开为 review_version(v1,v2,...) 序列
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

            # 2) 其它类型：rebuttal / comment / meta-review / decision ...
            else:
                ms = evt_basic["cdate"] or 0
                events.append({
                    "time": to_iso_time(ms),
                    "time_ms": ms,
                    "actor": evt_basic["role"],      # 'author' / 'ac' / 'reviewer' / 'pc' / 'other'
                    "event_type": evt_basic["type"], # 'author_comment' / 'reviewer_comment' / ...
                    "note_id": evt_basic["note_id"],
                    "replyto": evt_basic["replyto"],
                    "signatures": evt_basic["signatures"],
                    "content": evt_basic["content"],
                })

        # 可能没有任何事件（极少），也写空结构
        if not events:
            record = {
                "forum": forum_id,
                "number": number,
                "title": title,
                "abstract": abstract,               # ★ 新增
                "decision": None,                   # ★ 新增
                "per_reviewer": {},
                "global": [],
            }
        else:
            # 先整体按时间排序（便于 debug）
            events.sort(key=lambda e: e.get("time_ms") or 0)

            # 构造 per_reviewer 链 + global 事件
            per_reviewer, global_events = build_per_reviewer_chains(events)

            # 依据所有事件推断接收结果（优先从 decision / withdrawal）
            decision = detect_decision_from_events(events)

            record = {
                "forum": forum_id,
                "number": number,
                "title": title,
                "abstract": abstract,               # ★ 新增
                "decision": decision,               # ★ 新增
                "per_reviewer": per_reviewer,
                "global": global_events,
            }

        out_path = os.path.join(OUT_DIR, f"{forum_id}.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f_out:
            json.dump(record, f_out, ensure_ascii=False, indent=2)

    print(f"[INFO] Done. Saved {len(submissions)} JSON files under {OUT_DIR}/")


if __name__ == "__main__":
    main()