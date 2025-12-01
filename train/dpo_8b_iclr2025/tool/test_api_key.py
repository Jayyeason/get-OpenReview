from openai import OpenAI

client = OpenAI(
    api_key="sk-ae081cc1e8a6470580272505c9627b55",
    base_url="https://api.deepseek.com"
)

try:
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "user", "content": "测试一下 Deepseek 密钥是否可用"}
        ],
        max_tokens=10,
    )
    print("✅ 请求成功，模型回复：", resp.choices[0].message.content)
except Exception as e:
    print("❌ 请求失败，错误信息：", e)