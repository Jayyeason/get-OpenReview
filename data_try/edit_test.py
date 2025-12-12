import openreview
import json
import os
from datetime import datetime, timezone

client = openreview.api.OpenReviewClient(baseurl='https://api2.openreview.net')
NOTE_ID = 'tf47Fc9Sze'
try:
    # 尝试使用 get_note_edits (通常是这个)
    edits = client.get_note_edits(note_id=NOTE_ID)
except AttributeError:
    # 如果该版本SDK不支持，尝试 get_edits
    edits = client.get_edits(note_id=NOTE_ID)

def to_iso_time(ms):
    if not ms:
        return None
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.isoformat()

# 自定义序列化函数，递归处理对象
def serialize_openreview_object(obj):
    if isinstance(obj, list):
        return [serialize_openreview_object(item) for item in obj]
    if isinstance(obj, dict):
        return {key: serialize_openreview_object(value) for key, value in obj.items()}
    if hasattr(obj, '__dict__'):
        # convert object to dict
        d = obj.__dict__.copy()
        # Add cdate_iso if cdate exists
        if 'cdate' in d and d['cdate']:
            d['cdate_iso'] = to_iso_time(d['cdate'])
        return serialize_openreview_object(d)
    return obj

# 将 Edit 对象转换为字典列表
edits_data = [serialize_openreview_object(edit) for edit in edits]

# 写入 JSON 文件
output_file = 'edits_dump.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(edits_data, f, ensure_ascii=False, indent=4)

print(f"Successfully saved {len(edits)} edits to {output_file}")


