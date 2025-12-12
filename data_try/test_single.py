import openreview
import json
import os
from datetime import datetime, timezone

client = openreview.api.OpenReviewClient(baseurl='https://api2.openreview.net')
submissions = client.get_notes(id='zmmfsJpYcq', details='replies')

def to_iso_time(ms):
    if not ms:
        return None
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.isoformat()

# 获取脚本所在的目录，用于存放 JSON 文件
script_dir = os.path.dirname(os.path.abspath(__file__))

for i, s in enumerate(submissions):
    # 使用 submission ID 作为文件名，确保唯一性
    file_name = f"{s.id}.json"
    file_path = os.path.join(script_dir, file_name)
    
    # 使用 vars(s) 获取对象的所有属性（包括 number, details 等）
    # copy() 是为了避免修改原始对象
    data = vars(s).copy()
    
    # 增加 ISO 时间戳
    if 'cdate' in data and data['cdate']:
        data['cdate_iso'] = to_iso_time(data['cdate'])
    if 'mdate' in data and data['mdate']:
        data['mdate_iso'] = to_iso_time(data['mdate'])
    if 'tcdate' in data and data['tcdate']:
        data['tcdate_iso'] = to_iso_time(data['tcdate'])
    if 'tmdate' in data and data['tmdate']:
        data['tmdate_iso'] = to_iso_time(data['tmdate'])

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    
    print(f"Saved: {file_path}")
