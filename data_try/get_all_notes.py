import openreview
import json
import os

client = openreview.api.OpenReviewClient(baseurl='https://api2.openreview.net')
submissions = client.get_notes(invitation='ICLR.cc/2024/Conference/-/Submission',details='replies')

# 获取脚本所在的目录，用于存放 JSON 文件
script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, '2024_submissions_json')

# 如果目录不存在，则创建
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

for i, s in enumerate(submissions):
    # 使用 submission ID 作为文件名，确保唯一性
    file_name = f"{s.id}.json"
    file_path = os.path.join(output_dir, file_name)
    
    # 使用 vars(s) 获取对象的所有属性（包括 number, details 等）
    # copy() 是为了避免修改原始对象
    data = vars(s).copy()
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    
    print(f"Saved: {file_path}")
