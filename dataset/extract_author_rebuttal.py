import os
import json

BASE_DIR = os.path.dirname(__file__)
IN_DIR = os.path.join(BASE_DIR, "data", "iclr2025_forums")
OUT_DIR = os.path.join(BASE_DIR, "data", "iclr2025_only_author")

def extract_comment_text(content):
    if not isinstance(content, dict):
        return None
    v = content.get("comment")
    if isinstance(v, dict):
        v = v.get("value")
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return None

def process_file(in_path, out_dir):
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    comments = []
    chains = data.get("rebuttal_chain") or {}
    for evts in chains.values():
        for e in evts or []:
            if e.get("actor") == "author":
                t = extract_comment_text(e.get("content"))
                if t:
                    comments.append(t)
    others = data.get("other_review") or []
    for e in others:
        if e.get("actor") == "author":
            t = extract_comment_text(e.get("content"))
            if t:
                comments.append(t)
    new_data = dict(data)
    new_data.pop("rebuttal_chain", None)
    new_data.pop("other_review", None)
    new_data["author_rebuttal"] = "\n\n".join(comments)
    os.makedirs(out_dir, exist_ok=True)
    fname = os.path.basename(in_path)
    out_path = os.path.join(out_dir, fname)
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, out_path)
    return len(comments), out_path

def main():
    print(f"[INFO] Input: {IN_DIR}")
    print(f"[INFO] Output: {OUT_DIR}")
    files = [n for n in os.listdir(IN_DIR) if n.endswith('.json')]
    print(f"[INFO] Found {len(files)} JSON files")
    processed = 0
    empty = 0
    for name in files:
        if not name.endswith(".json"):
            continue
        in_path = os.path.join(IN_DIR, name)
        count, out_path = process_file(in_path, OUT_DIR)
        processed += 1
        if count == 0:
            empty += 1
        if processed % 200 == 0:
            print(f"[INFO] Processed {processed} files...")
    print(f"[INFO] Done. Total: {processed}, empty author replies: {empty}")

if __name__ == "__main__":
    main()