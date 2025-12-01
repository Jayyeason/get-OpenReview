import os
import json
import sys

SRC_DIR = "/remote-home1/bwli/get_open_review/dataset/data/iclr2025_forums_clear"
DST_DIR = "/remote-home1/bwli/get_open_review/dataset/data/iclr2025_forums_one_review"

def filter_rebuttal_chain(rc):
    if isinstance(rc, dict):
        out = {}
        for reviewer, events in rc.items():
            if isinstance(events, list):
                kept = [e for e in events if isinstance(e, dict) and e.get("version_index") == 1]
                if kept:
                    out[reviewer] = kept[0]  # 直接存储对象，不用数组包裹
        return out
    return {}

def process_one(src_path, dst_path):
    with open(src_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rc = data.get("rebuttal_chain")
    # 删除旧的 rebuttal_chain 字段，添加新的 official_review 字段
    if "rebuttal_chain" in data:
        del data["rebuttal_chain"]
    data["official_review"] = filter_rebuttal_chain(rc)
    kept_count = len(data["official_review"]) if isinstance(data["official_review"], dict) else 0
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return kept_count

def main():
    os.makedirs(DST_DIR, exist_ok=True)
    files = [f for f in os.listdir(SRC_DIR) if f.endswith(".json")]
    total = len(files)
    print("source:", SRC_DIR)
    print("dest:", DST_DIR)
    print("total:", total)
    errors = 0
    for i, fname in enumerate(sorted(files), 1):
        src = os.path.join(SRC_DIR, fname)
        dst = os.path.join(DST_DIR, fname)
        try:
            process_one(src, dst)
        except Exception:
            errors += 1
        ratio = i / total if total else 1
        bar_len = 30
        filled = int(bar_len * ratio)
        bar = "#" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r[{i}/{total}] |{bar}| {int(ratio*100)}%")
        sys.stdout.flush()
    sys.stdout.write("\n")
    print("done", total, "errors", errors)

if __name__ == "__main__":
    main()
