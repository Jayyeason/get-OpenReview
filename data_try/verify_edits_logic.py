import openreview
import json
import os
import random
import glob

# 初始化客户端
client = openreview.api.OpenReviewClient(baseurl='https://api2.openreview.net')

# 获取 data_try/submissions_json 下的所有 json 文件
json_files = glob.glob('/remote-home1/bwli/get_open_review/data_try/submissions_json/*.json')
if not json_files:
    print("No JSON files found in data_try/submissions_json/")
    exit(1)

# 随机抽取 20 个文件
sample_files = random.sample(json_files, min(20, len(json_files)))

print(f"Sampling {len(sample_files)} notes for verification...\n")

stats = {
    "total": 0,
    "edits_found": 0,
    "edits_match_latest_content": 0,
    "edits_match_latest_time": 0,
    "missing_latest_in_edits": 0
}

for file_path in sample_files:
    stats["total"] += 1
    # 从文件名提取 Note ID (假设文件名就是 ID.json)
    note_id = os.path.basename(file_path).replace('.json', '')
    
    print(f"[{stats['total']}/{len(sample_files)}] Checking Note ID: {note_id}")
    
    try:
        # 1. 获取最新状态
        latest_note = client.get_note(note_id)
        
        # 2. 获取 Edits
        try:
            edits = client.get_note_edits(note_id=note_id)
        except Exception:
            try:
                edits = client.get_edits(note_id=note_id)
            except Exception:
                edits = []
        
        edits.sort(key=lambda x: x.cdate or 0)
        
        if not edits:
            print(f"  -> No edits found. (Latest mdate: {latest_note.mdate})")
            stats["missing_latest_in_edits"] += 1
            continue
            
        stats["edits_found"] += 1
        last_edit = edits[-1]
        
        # 3. 验证时间戳
        time_match = (last_edit.cdate == latest_note.mdate)
        if time_match:
            stats["edits_match_latest_time"] += 1
            
        # 4. 验证内容 (简单比较 JSON 字符串)
        content_match = False
        if last_edit.note.content and latest_note.content:
            snapshot_json = json.dumps(last_edit.note.content, sort_keys=True)
            latest_json = json.dumps(latest_note.content, sort_keys=True)
            content_match = (snapshot_json == latest_json)
            
        if content_match:
            stats["edits_match_latest_content"] += 1
            
        # 综合判定
        is_missing = not (time_match or content_match)
        if is_missing:
            stats["missing_latest_in_edits"] += 1
            print(f"  -> Edits found ({len(edits)}), but LATEST IS MISSING in history.")
            print(f"     Last Edit Time: {last_edit.cdate}")
            print(f"     Latest Note Time: {latest_note.mdate}")
        else:
            print(f"  -> Latest version FOUND in edits. (Time match: {time_match}, Content match: {content_match})")
            
    except Exception as e:
        print(f"  -> Error processing {note_id}: {e}")

print("\n" + "="*40)
print("FINAL STATISTICS")
print("="*40)
print(f"Total Notes Checked: {stats['total']}")
print(f"Notes with Edits:    {stats['edits_found']}")
print(f"Latest Version Found in Edits (Time):    {stats['edits_match_latest_time']}")
print(f"Latest Version Found in Edits (Content): {stats['edits_match_latest_content']}")
print("-" * 20)
print(f"MISSING Latest in Edits: {stats['missing_latest_in_edits']} ({(stats['missing_latest_in_edits']/stats['total'])*100:.1f}%)")
print("="*40)
