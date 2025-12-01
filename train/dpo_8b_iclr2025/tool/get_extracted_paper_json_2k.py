import os
import shutil

SRC_TXT_DIR = "/remote-home1/bwli/get_open_review/qwen_review/extracted_contents"
SRC_JSON_DIR = "/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/iclr2025_first_review"
DST_JSON_DIR = "/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025/data/iclr2025_first_review_2k"


def main():
    os.makedirs(DST_JSON_DIR, exist_ok=True)
    txt_files = [f for f in os.listdir(SRC_TXT_DIR) if f.endswith(".txt")]
    copied = 0
    missing = 0
    for fname in txt_files:
        forum_id = os.path.splitext(fname)[0]
        src_json = os.path.join(SRC_JSON_DIR, forum_id + ".json")
        dst_json = os.path.join(DST_JSON_DIR, forum_id + ".json")
        if os.path.exists(src_json):
            shutil.copy2(src_json, dst_json)
            copied += 1
        else:
            missing += 1
    print(f"copied={copied} missing={missing} from={SRC_JSON_DIR} to={DST_JSON_DIR}")


if __name__ == "__main__":
    main()

