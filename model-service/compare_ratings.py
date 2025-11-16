import argparse
import json
import re
from collections import defaultdict, OrderedDict

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--num", type=int, default=1000)
    p.add_argument("--json", type=str, default="/remote-home1/bwli/get_open_review/model-service/qwen3-30B-author-rebuttal-reviews.json")
    p.add_argument("--true", type=str, default="/remote-home1/bwli/get_open_review/output/all_notes_readable.json")
    return p.parse_args()

def load_ai_reviews(path, limit):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f, object_pairs_hook=OrderedDict)
    items = []
    for pid in data.keys():
        entry = data[pid]
        items.append((pid, entry.get("reviews", [])))
        if limit is not None and len(items) >= limit:
            break
    return items

def to_number(x):
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        m = re.search(r"[-+]?\d+(?:\.\d+)?", x)
        if m:
            try:
                return float(m.group(0))
            except Exception:
                return None
    return None

def load_true_ratings(path):
    with open(path, "r", encoding="utf-8") as f:
        notes = json.load(f)
    ratings = defaultdict(list)
    for note in notes:
        replyto = note.get("replyto")
        if not replyto:
            continue
        c = note.get("content", {})
        r = c.get("rating")
        if not isinstance(r, dict):
            continue
        v = to_number(r.get("value"))
        if v is None:
            continue
        ratings[replyto].append(v)
    return ratings

def mean(xs):
    return sum(xs) / len(xs) if xs else None

def main():
    args = parse_args()
    ai_items = load_ai_reviews(args.json, args.num)
    true_map = load_true_ratings(args.true)
    metrics = {}
    for pid, reviews in ai_items:
        tvals = true_map.get(pid, [])
        tmean = mean(tvals)
        if tmean is None:
            continue
        for r in reviews:
            rid = r.get("reviewer_id")
            rv = r.get("review", {}).get("rating", {})
            aval = to_number(rv.get("value"))
            if aval is None:
                continue
            err = aval - tmean
            m = metrics.get(rid)
            if not m:
                m = {"count": 0, "mse": 0.0, "mae": 0.0}
                metrics[rid] = m
            m["count"] += 1
            m["mse"] += err * err
            m["mae"] += abs(err)
    for rid, m in metrics.items():
        if m["count"] > 0:
            m["mse"] = m["mse"] / m["count"]
            m["mae"] = m["mae"] / m["count"]
        else:
            m["mse"] = None
            m["mae"] = None
    print(json.dumps({"per_reviewer": metrics}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
