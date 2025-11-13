#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, json, re
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Any, Optional

# --------- 工具函数 ---------
def iso_from_ms(ms: int) -> str:
    if not isinstance(ms, int):
        return None
    try:
        return datetime.utcfromtimestamp(ms / 1000.0).isoformat() + "+00:00"
    except Exception:
        return None

def short_reviewer_id_from_sigs(sigs: List[str]) -> Optional[str]:
    if not sigs:
        return None
    for s in sigs:
        m = re.search(r"(Reviewer_[A-Za-z0-9]+)", s or "")
        if m:
            return m.group(1)
    return None

def is_author_signature(sig: str) -> bool:
    return bool(sig and (sig.endswith("/Authors") or sig.endswith("/Authors/") or sig.endswith("Authors")))

def is_reviewer_signature(sig: str) -> bool:
    return bool(sig and "Reviewer_" in sig)

def normalize_content(content: Any) -> Dict[str, Any]:
    """OpenReview 常见是 {key: {value: ...}}，原样兼容；若已是 value 则包一下。"""
    if not isinstance(content, dict):
        return {}
    out = {}
    for k, v in content.items():
        if isinstance(v, dict) and "value" in v:
            out[k] = {"value": v.get("value")}
        else:
            out[k] = v
    return out

def detect_decision(candidates_objs: List[Dict[str, Any]]) -> Optional[str]:
    texts = []
    # 先看撤稿
    for n in candidates_objs:
        c = n.get("content") or {}
        if "withdrawal_confirmation" in c:
            return "Withdrawn"
        for k, v in c.items():
            vv = v.get("value") if isinstance(v, dict) else v
            if isinstance(vv, str) and re.search(r"withdraw", vv, re.I):
                return "Withdrawn"

    for n in candidates_objs:
        c = n.get("content") or {}
        for key in ["decision", "Decision", "final_decision", "venue", "venueid", "recommendation", "title", "comment"]:
            v = c.get(key)
            vv = v.get("value") if isinstance(v, dict) else v
            if isinstance(vv, str):
                texts.append(vv)

    blob = " ".join(texts)
    if not blob:
        return None
    if re.search(r"\b(accept|oral|spotlight|poster)\b", blob, re.I):
        return "Accept"
    if re.search(r"\b(reject|desk\s*reject)\b", blob, re.I):
        return "Reject"
    return None

def extract_abstract_from_rootlike(doc: Dict[str, Any]) -> Optional[str]:
    # 尝试从 doc 顶层或 root-like 节点里读
    for k in ["abstract", "Abstract", "paper_abstract", "tl;dr", "TL;DR", "TLDR"]:
        v = doc.get(k)
        if isinstance(v, dict):
            v = v.get("value")
        if isinstance(v, str) and v.strip():
            return v.strip()
    root = doc.get("root") or doc.get("head") or {}
    if isinstance(root, dict):
        c = root.get("content") or {}
        for k in ["abstract", "Abstract", "paper_abstract", "tl;dr", "TL;DR", "TLDR"]:
            v = c.get(k)
            if isinstance(v, dict):
                v = v.get("value")
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None

# --------- 事件生成与链构建 ---------
def derive_all_events_from_doc(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    兼容多种输入：
    1) 原始 notes（doc['notes'] 是 OpenReview 笔记数组）
    2) 已经拆成 per_reviewer 列表或映射（从里面收集 events）
    3) global/others 里的讨论项
    """
    evs: Dict[str, Dict[str, Any]] = {}

    # 情况 1：原始 notes
    if isinstance(doc.get("notes"), list):
        for n in doc["notes"]:
            note_id = n.get("id")
            if not note_id:
                continue
            cdate = n.get("cdate", 0)
            # 尝试推断 actor/event_type
            sigs = n.get("signatures") or []
            actor = "other"
            etype = "other"
            if any(is_author_signature(s) for s in sigs):
                actor, etype = "author", "author_comment"
            elif any(is_reviewer_signature(s) for s in sigs):
                actor = "reviewer"
                inv = (n.get("invitation") or "").lower()
                if "official_review" in inv or re.search(r"/review$", inv):
                    etype = "review_version"
                else:
                    etype = "reviewer_comment"
            else:
                inv = (n.get("invitation") or "").lower()
                if "comment" in inv:
                    etype = "other_comment"

            evs[note_id] = {
                "time": iso_from_ms(cdate),
                "time_ms": cdate,
                "actor": actor,
                "event_type": etype,
                "version_index": 1,
                "note_id": note_id,
                "replyto": n.get("replyto"),
                "signatures": sigs,
                "content": normalize_content(n.get("content") or {}),
                "original": n.get("original"),
                "invitation": n.get("invitation"),
            }

    # 情况 2：per_reviewer 列表
    pr = doc.get("per_reviewer")
    if isinstance(pr, list):
        for r in pr:
            for e in r.get("events", []):
                nid = e.get("note_id")
                if not nid:
                    continue
                # 以输入为准（这些通常已经有 actor/event_type）
                evs[nid] = {
                    "time": e.get("time"),
                    "time_ms": e.get("time_ms"),
                    "actor": e.get("actor"),
                    "event_type": e.get("event_type"),
                    "version_index": e.get("version_index", 1),
                    "note_id": nid,
                    "replyto": e.get("replyto"),
                    "signatures": e.get("signatures", []),
                    "content": normalize_content(e.get("content") or {}),
                    "original": e.get("original"),
                    "invitation": e.get("invitation"),
                }
    # 情况 3：per_reviewer 映射
    if isinstance(pr, dict):
        for _, lst in pr.items():
            if not isinstance(lst, list):
                continue
            for e in lst:
                nid = e.get("note_id")
                if not nid:
                    continue
                evs[nid] = {
                    "time": e.get("time"),
                    "time_ms": e.get("time_ms"),
                    "actor": e.get("actor"),
                    "event_type": e.get("event_type"),
                    "version_index": e.get("version_index", 1),
                    "note_id": nid,
                    "replyto": e.get("replyto"),
                    "signatures": e.get("signatures", []),
                    "content": normalize_content(e.get("content") or {}),
                    "original": e.get("original"),
                    "invitation": e.get("invitation"),
                }

    # 情况 4：global / others
    for k in ["global", "others", "misc"]:
        if isinstance(doc.get(k), list):
            for e in doc[k]:
                nid = e.get("note_id")
                if not nid:
                    continue
                evs[nid] = {
                    "time": e.get("time"),
                    "time_ms": e.get("time_ms"),
                    "actor": e.get("actor", "other"),
                    "event_type": e.get("event_type", "other"),
                    "version_index": e.get("version_index", 1),
                    "note_id": nid,
                    "replyto": e.get("replyto"),
                    "signatures": e.get("signatures", []),
                    "content": normalize_content((e.get("content") or {})),
                    "original": e.get("original"),
                    "invitation": e.get("invitation"),
                }

    return list(evs.values())

def build_children_map(all_events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    children = defaultdict(list)
    by_id = {e.get("note_id"): e for e in all_events}
    for e in all_events:
        parent = e.get("replyto")
        if parent and parent in by_id:
            children[parent].append(e)
    # 时间排序
    for pid in children:
        children[pid].sort(key=lambda x: (x.get("time_ms") or 0))
    return children

def group_review_versions(review_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将同一 review 的多版合并（优先用 original 分桶；没有 original 就按 note_id；若 note_id 相同且带 version_index，则按 version_index 升序）
    """
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in review_nodes:
        key = r.get("original") or r.get("note_id")
        buckets[key].append(r)

    out = []
    for key, arr in buckets.items():
        # 先按 time 再按 version_index
        arr.sort(key=lambda x: ((x.get("time_ms") or 0), x.get("version_index", 1)))
        for i, n in enumerate(arr, 1):
            n["_version_group_id"] = key
            # 如果 note_id 相同，我们就尊重已有 version_index；否则从 1..N
            if sum(1 for x in arr if x.get("note_id") == n.get("note_id")) == len(arr):
                # 全都同一个 note_id：用 version_index（若未给则用 i）
                n["_version_index"] = n.get("version_index", i)
            else:
                n["_version_index"] = i
            out.append(n)
    # 再整体时间排序
    out.sort(key=lambda x: (x.get("time_ms") or 0, x.get("_version_index", 1)))
    return out

def walk_thread(start: Dict[str, Any], children_map: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    res = []
    dq = deque([start])
    seen = set()
    while dq:
        cur = dq.popleft()
        cid = cur.get("note_id")
        if cid in seen:
            continue
        seen.add(cid)
        res.append(cur)
        for ch in children_map.get(cid, []):
            dq.append(ch)
    res.sort(key=lambda x: (x.get("time_ms") or 0))
    return res

def event_actor_type(ev: Dict[str, Any], reviewer_short: Optional[str]) -> str:
    sigs = ev.get("signatures") or []
    if any(is_author_signature(s) for s in sigs):
        return "author"
    if reviewer_short and any(reviewer_short in s for s in sigs):
        return "reviewer"
    if any(is_reviewer_signature(s) for s in sigs):
        return "reviewer"
    return "other"

def force_review_first(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not events:
        return events
    # 保障第一条是 review_version
    events.sort(key=lambda x: (0 if x.get("event_type") == "review_version" else 1, x.get("time_ms") or 0))
    return events

def build_output_for_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    forum = doc.get("forum")
    number = doc.get("number")
    title = doc.get("title")

    all_events = derive_all_events_from_doc(doc)
    # children map 基于所有事件（跨评审/作者）
    children_map = build_children_map(all_events)

    # 找所有“评审的正式评审”作为线程起点
    start_reviews = []
    for e in all_events:
        if e.get("event_type") == "review_version":
            # replyto 通常指向 forum/root review 入口
            start_reviews.append(e)

    # 分 reviewer 短 ID 组织
    per_reviewer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    # 先对每位评审的多版评审进行分桶
    by_reviewer = defaultdict(list)
    for rv in start_reviews:
        rid = short_reviewer_id_from_sigs(rv.get("signatures") or [])
        if not rid:
            continue
        by_reviewer[rid].append(rv)

    used_note_ids = set()

    for rid, reviews in by_reviewer.items():
        versioned = group_review_versions(reviews)
        for rv in versioned:
            thread = walk_thread(rv, children_map)
            # 事件化 + 标准字段
            out_events = []
            for ev in thread:
                nid = ev.get("note_id")
                if nid in used_note_ids:
                    continue
                actor = event_actor_type(ev, rid)
                # 重写 version：仅对起始评审生效；其他评论 version=1
                version_index = ev.get("_version_index", 1) if nid == rv.get("note_id") else 1
                note_id_for_group = rv.get("_version_group_id", rv.get("note_id")) if nid == rv.get("note_id") else ev.get("note_id")

                out_events.append({
                    "time": ev.get("time") or iso_from_ms(ev.get("time_ms") or 0),
                    "time_ms": ev.get("time_ms"),
                    "actor": actor,
                    "event_type": ev.get("event_type") if nid == rv.get("note_id") else (
                        "author_comment" if actor == "author" else ("reviewer_comment" if actor == "reviewer" else ev.get("event_type") or "other")
                    ),
                    "version_index": version_index,
                    "note_id": note_id_for_group,
                    "replyto": ev.get("replyto"),
                    "signatures": ev.get("signatures", []),
                    "content": ev.get("content", {}),
                })
                used_note_ids.add(nid)

            out_events.sort(key=lambda x: (x.get("time_ms") or 0))
            out_events = force_review_first(out_events)
            per_reviewer[rid].extend(out_events)

    # 如果没有识别出任何评审链，退化为把所有事件按 reviewer 短签名粗分（以防某些输入缺失 event_type）
    if not per_reviewer and all_events:
        for ev in sorted(all_events, key=lambda x: (x.get("time_ms") or 0)):
            rid = short_reviewer_id_from_sigs(ev.get("signatures") or [])
            if rid:
                per_reviewer[rid].append({
                    "time": ev.get("time") or iso_from_ms(ev.get("time_ms") or 0),
                    "time_ms": ev.get("time_ms"),
                    "actor": event_actor_type(ev, rid),
                    "event_type": ev.get("event_type") or "other",
                    "version_index": ev.get("version_index", 1),
                    "note_id": ev.get("note_id"),
                    "replyto": ev.get("replyto"),
                    "signatures": ev.get("signatures", []),
                    "content": ev.get("content", {}),
                })

    # abstract 与 decision
    abstract = doc.get("abstract")
    if not abstract:
        abstract = extract_abstract_from_rootlike(doc)

    decision = doc.get("decision")
    if not decision:
        # 用 global/notes 里线索推断
        candidates = []
        if isinstance(doc.get("global"), list):
            candidates.extend(doc["global"])
        # 如果是原始 notes 输入，顺带看看
        if isinstance(doc.get("notes"), list):
            for n in doc["notes"]:
                candidates.append({"content": n.get("content") or {}})
        decision = detect_decision(candidates) if candidates else None

    return {
        "forum": forum,
        "number": number,
        "title": title,
        "abstract": abstract,
        "decision": decision,
        "per_reviewer": per_reviewer
    }

# --------- 主流程：从 STDIN 读取，STDOUT 输出 ---------
def main():
    raw = sys.stdin.read()
    if not raw.strip():
        print("[]", end="")
        return
    data = json.loads(raw)

    if isinstance(data, list):
        out = [build_output_for_doc(d) for d in data if isinstance(d, dict)]
    elif isinstance(data, dict):
        out = build_output_for_doc(data)
    else:
        out = []

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

if __name__ == "__main__":
    main()