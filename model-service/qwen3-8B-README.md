# AI 评审员推理脚本说明

使用部署在 `10.176.59.101:8002` 的 Qwen3-8B 模型模拟学术论文评审员。

## 功能特性

- 🤖 **自动评审生成**：基于论文内容和元数据生成结构化评审
- 💬 **上下文感知**：自动包含评审对话历史（作者回复、后续讨论等）作为上下文
- ⚡ **并行处理**：支持多线程并行处理多篇论文
- 📊 **结构化输出**：生成标准的评审 JSON 格式
- 📝 **可自定义 Prompt**：支持内置模板或外部文件，方便修改和调整
- 🔄 **增量保存**：每完成一篇论文立即保存，防止数据丢失

## 输出格式说明

脚本会为每篇论文的**每个原始 reviewer** 生成一个对应的 AI 评审，输出格式与 `review_conversations_100.json` 保持一致：

```json
{
  "paper_id": {
    "paper_info": {
      // 保留原始论文信息
      "title": "...",
      "abstract": "...",
      "keywords": [...],
      "primary_area": "...",
      ...
    },
    "ai_review": [
      {
        "id": "原始reviewer的id",
        "signatures": ["原始reviewer的signatures"],
        "content": {
          "summary": {"value": "AI生成的摘要"},
          "strengths": {"value": "AI生成的优点"},
          "weaknesses": {"value": "AI生成的缺点"},
          "questions": {"value": "AI生成的问题"},
          "rating": {"value": 7},
          "confidence": {"value": 4},
          "soundness": {"value": 3},
          "presentation": {"value": 3},
          "contribution": {"value": 3},
          "flag_for_ethics_review": {"value": ["No ethics review needed."]},
          "code_of_conduct": {"value": "Yes"}
        }
      },
      // 如果有多个reviewer，会为每个生成一个评审
      {...}
    ]
  }
}
```

### 重要特性

- ✅ **保留原始结构**：输出格式与输入的 `review_conversations_100.json` 完全兼容
- ✅ **保留 reviewer 信息**：每个 AI 评审使用原始 reviewer 的 `id` 和 `signatures`
- ✅ **多 reviewer 支持**：如果论文有 N 个 reviewer，会生成 N 个 AI 评审
- ✅ **标准化内容**：所有字段采用 `{"value": ...}` 格式，符合 OpenReview 标准
- ✅ **自动上下文感知**：智能检测并包含作者回复和评审者后续讨论

### 对话上下文自动处理

脚本会自动检测每个评审线程中的对话历史：

- 如果评审后**有作者回复或后续讨论**，会自动提取并作为上下文
- 上下文包括：作者回复 (Author)、评审者跟进 (Reviewer)、Area Chair 意见等
- **不包括第一条初始评审**（因为那正是我们要生成的）
- 自动识别角色并格式化为结构化上下文

这使得 AI 在生成评审时能够：
- 考虑作者的解释和补充
- 参考其他评审者的意见
- 生成更全面、更准确的评审

## 使用方法

### 基本用法

```bash
cd /remote-home1/bwli/get_open_review/model-service

# 最简单的使用（自动包含对话上下文）
python review_inference.py
```

**注意**：脚本会**自动检测并包含**评审对话历史（如作者回复、评审者后续评论等）作为生成上下文，无需额外参数。

### 并行处理

```bash
# 使用 3 个线程并行处理
python review_inference.py --workers 3

# 使用 5 个线程
python review_inference.py --workers 5
```

### 测试运行

```bash
# 只处理前 5 篇论文（用于测试）
python review_inference.py --limit 5

# 测试单篇论文
python review_inference.py --limit 1

# 测试单篇 + 并行
python review_inference.py --limit 10 --workers 3
```

### 自定义配置

```bash
# 指定输出文件
python review_inference.py --output my_custom_reviews.json

# 使用不同的模型服务
python review_inference.py --base-url http://another-server:8003/v1 --model another-model

# 使用自定义 User Prompt 模板（可选）
python review_inference.py --prompt-template my_custom_prompt.txt

# 完整自定义
python review_inference.py \
  --json /path/to/review_data.json \
  --extracted-contents /path/to/extracted_texts \
  --output /path/to/output.json \
  --workers 4 \
  --prompt-template custom_prompt.txt
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--json` | `../qwen_review/review_conversations_100.json` | 评审数据 JSON 文件路径 |
| `--extracted-contents` | `../qwen_review/extracted_contents` | 提取的论文文本目录 |
| `--output` | `ai_generated_reviews.json` | 输出 JSON 文件路径 |
| `--base-url` | `http://10.176.59.101:8002/v1` | Qwen3-8B API 地址 |
| `--model` | `qwen3-8b` | 模型名称 |
| `--prompt-template` | `None`（使用内置模板） | 可选：自定义 User Prompt 模板文件路径 |
| `--workers` | `1` | 并行处理的线程数 |
| `--limit` | `None` | 可选：限制处理前 N 篇论文（用于测试） |

## 输入数据要求

### 1. 评审数据 JSON

格式：
```json
{
  "paper_id": {
    "paper_info": {
      "title": "...",
      "abstract": "...",
      "keywords": [...],
      "primary_area": "..."
    },
    "conversations": [...]
  }
}
```

### 2. 提取的论文内容

- 位置：`extracted_contents/` 目录
- 格式：`{paper_id}.txt`
- 内容：论文的完整文本内容

## 详细输出示例

完整的输出文件示例请参考：`output_format_example.json`

每篇论文包含：
- **paper_info**: 完整的论文元数据（从输入JSON复制）
- **ai_review**: AI生成的评审列表（每个原始reviewer对应一个）

### 多 Reviewer 示例

如果一篇论文有 3 个 reviewer，输出会包含 3 个 AI 评审：

```json
{
  "paper_id": {
    "paper_info": {...},
    "ai_review": [
      {
        "id": "reviewer1_id",
        "signatures": ["Reviewer_A"],
        "content": {...}  // AI为Reviewer A生成的评审
      },
      {
        "id": "reviewer2_id", 
        "signatures": ["Reviewer_B"],
        "content": {...}  // AI为Reviewer B生成的评审
      },
      {
        "id": "reviewer3_id",
        "signatures": ["Reviewer_C"],
        "content": {...}  // AI为Reviewer C生成的评审
      }
    ]
  }
}
```

## 性能建议

- **串行处理** (`--workers 1`)：最稳定，适合测试
- **2-3 线程**：推荐配置，平衡速度和稳定性
- **4-5 线程**：需要确保 API 服务有足够容量
- **不建议超过 5 线程**：可能导致 API 过载

### 预期处理时间

**注意**：脚本会为每篇论文的**每个 reviewer** 生成一个评审，所以总评审数 = Σ(每篇论文的reviewer数量)

假设：
- 100 篇论文
- 平均每篇 4.5 个 reviewer（基于当前数据集）
- 总共需要生成约 **450 个评审**

时间估算：
- **单线程**：约 450 × 40秒 = 300 分钟（5小时）
- **3 线程**：约 100-150 分钟（1.5-2.5小时）
- **5 线程**：约 60-90 分钟（1-1.5小时）

## 运行时输出说明

脚本运行时会显示详细的进度信息：

```
==================================================================================
AI 评审员推理系统
==================================================================================
模型: qwen3-8b @ http://10.176.59.101:8002/v1
Prompt 模板: 内置模板
输入数据: ../qwen_review/review_conversations_100.json
论文内容: ../qwen_review/extracted_contents
输出文件: ai_generated_reviews.json
并行线程: 3
==================================================================================

📖 加载评审数据...
✓ 加载了 100 篇论文

🤖 初始化 AI 评审员...
  ✓ 使用内置 User Prompt 模板
  ✓ 使用内置 System Prompt
✓ AI 评审员已就绪

🚀 开始处理论文...
💾 结果将动态保存到 ai_generated_reviews.json

============================================================
Processing: paper_id_xxx
============================================================
  ✓ 论文内容已加载 (25630 字符)
  标题: Example Paper Title...
  原始评审数: 4
  🤖 为 Reviewer 1 生成评审（包含 2 条后续对话）...
    ✓ 生成完成 (耗时: 8.5s, 评分: 7)
  🤖 为 Reviewer 2 生成评审（无后续对话）...
    ✓ 生成完成 (耗时: 7.2s, 评分: 6)
  ...
  ✅ 完成，共生成 4 个AI评审
  💾 已保存 (1/100)
```

## 示例工作流

```bash
# 1. 先测试单篇论文（会为该论文的所有 reviewer 生成评审）
python review_inference.py --limit 1

# 2. 检查输出格式
cat ai_generated_reviews.json | jq '.[].ai_review | length'  # 查看每篇论文生成了几个评审

# 3. 满意后处理更多论文
python review_inference.py --limit 10 --workers 3

# 4. 最后处理全部（建议使用并行）
python review_inference.py --workers 3 --output final_reviews.json
```

## 故障排除

### API 连接失败
```bash
# 检查 Qwen3-8B 服务是否运行
curl http://10.176.59.101:8002/v1/models
```

### JSON 解析失败
- 模型可能生成了不规范的 JSON
- 尝试降低并发数 (`--workers 1`)
- 检查生成的原始响应

### 论文内容文件缺失
- 确保先运行了 `process_pdf_fully.py`
- 检查 `extracted_contents/` 目录

## 依赖环境

```bash
pip install openai
```

## 注意事项

⚠️ **重要提示**：
1. 确保 Qwen3-8B 服务正在运行
2. 论文内容会被截断至 10000 字符（可在代码中调整 `max_content_length` 参数）
3. API 调用可能较慢，100 篇论文预计需要 30-60 分钟（取决于服务器性能）
4. 建议先用 `--limit` 参数测试小批量
5. 脚本支持增量保存，中途中断可以继续处理未完成的论文

## 鲁棒性特性

### 智能 JSON 解析

代码实现了多层次的 JSON 解析策略（第 186-223 行）：

1. **自动清理 `<think>` 标签**：支持 Qwen 模型的 Chain-of-Thought 推理
2. **移除 Markdown 代码块**：自动处理 ` ```json ` 等标记
3. **智能定位 JSON**：如果有多余文本，自动查找第一个 `{` 开始的 JSON
4. **错误容忍**：解析失败时仍保存原始响应，不会中断整个流程

### 错误处理

- API 调用失败会记录错误但继续处理其他论文
- JSON 解析失败会保存原始响应并标记 `rating: -1`
- 每完成一篇论文立即保存到磁盘（防止进度丢失）

## Prompt 架构说明

### 双层 Prompt 设计

本系统采用**分离式 Prompt 架构**：

#### **System Prompt**（固定，在代码中）
包含任务指令，定义在 `review_inference.py` 顶部的 `SYSTEM_PROMPT` 常量中（第 23-84 行）：
- AI 角色定义："You are an expert academic reviewer for a top-tier machine learning conference (ICLR)."
- 评审任务详细说明（Summary, Strengths, Weaknesses, Questions）
- 评分标准：
  - **Rating** (1-10): 论文质量总评分
  - **Confidence** (1-5): 评审者信心水平
  - **Soundness** (1-4): 技术严谨性
  - **Presentation** (1-4): 表达质量
  - **Contribution** (1-4): 贡献度
- JSON 输出格式要求
- 支持 `<think>` 标签进行 Chain-of-Thought 推理

#### **User Prompt**（动态，可自定义）
包含论文数据，有两种来源：
1. **内置模板**（默认）：定义在 `USER_PROMPT_TEMPLATE` 常量中（第 87-102 行）
2. **外部文件**（可选）：通过 `--prompt-template` 参数指定

包含内容：
- 论文信息（标题、摘要、关键词、领域）
- 论文内容（自动截断至 10000 字符）
- 自动生成的讨论上下文（如果存在作者回复或后续对话）

### 为什么这样设计？

- ✅ **职责分离**：指令和数据分开
- ✅ **节省 tokens**：任务指令不会重复
- ✅ **更好的遵守**：System prompt 权重更高，模型更容易遵循格式
- ✅ **易于维护**：修改评分标准改代码，修改数据格式改模板

### 自定义 User Prompt 模板

如果需要自定义 User Prompt（论文数据的展示格式），可以创建外部模板文件。

#### 模板变量

模板支持以下变量（使用 Python 的 `.format()` 语法）：

- `{title}` - 论文标题
- `{abstract}` - 论文摘要
- `{keywords}` - 关键词列表（已格式化为逗号分隔字符串）
- `{primary_area}` - 主题领域
- `{paper_content}` - 论文内容（自动截断至 10000 字符）
- `{conversation_section}` - 对话历史（自动生成，如果存在则包含）

#### 创建自定义模板

```bash
# 1. 创建自定义模板文件（参考内置模板格式）
cat > my_custom_prompt.txt << 'EOF'
## Paper Information

**Title:** {title}

**Abstract:** {abstract}

**Keywords:** {keywords}

**Primary Area:** {primary_area}

## Paper Content (Extracted)

{paper_content}

## Conversation Content (Author and Reviewer)
{conversation_section}
EOF

# 2. 使用自定义模板运行
python review_inference.py --prompt-template my_custom_prompt.txt
```

### 自定义 System Prompt

如果需要修改**评审标准或任务指令**，需要编辑 `review_inference.py` 文件顶部的 `SYSTEM_PROMPT` 常量（第 23-84 行）：

```python
# 在文件顶部找到 SYSTEM_PROMPT
SYSTEM_PROMPT = """You are an expert academic reviewer for a top-tier machine learning conference (ICLR). 

## Your Review Task

You will be provided with a research paper...

5. **Rating**: An integer score from 1-10, where:
   - 1-3: Strong reject  # 可以修改这里
   - 4-5: Reject
   - 6: Weak accept
   - 7-8: Accept
   - 9-10: Strong accept
...
```

**注意**：修改后需要重启脚本才能生效。

### 调整评审标准

你可以在 `SYSTEM_PROMPT` 中修改：
- 评分标准（1-10 分的定义）
- 评审维度（当前有 summary, strengths, weaknesses, questions 等）
- 输出格式要求
- 语气和风格（如更严格或更宽容）
- AI 角色定位（如不同会议、不同领域的评审者）

## 扩展开发

### 调整生成参数

在 `ReviewerAI.generate_review()` 方法中（第 159-253 行）调整：
- `temperature`: 控制生成随机性（0.0-1.0，默认 0.7）
- `max_tokens`: 最大生成长度（默认 2000）
- `max_content_length`: 论文内容截断长度（默认 10000 字符）

示例：
```python
review_data = reviewer_ai.generate_review(
    paper_info=paper_info,
    paper_content=paper_content,
    conversation_context=thread_context,
    temperature=0.5,  # 更确定性的输出
    max_tokens=3000   # 更长的评审
)
```

### 添加后处理

在 `process_single_paper()` 函数（第 329-413 行）中添加评审内容的验证和后处理逻辑。

### 修改对话上下文提取

在 `extract_conversation_thread_context()` 函数（第 256-305 行）中自定义如何提取和格式化对话历史。

当前逻辑：
- 提取每个对话线程中**除第一条消息外**的所有消息
- 自动识别角色（Author、Reviewer、Area Chair）
- 提取多个字段（comment、response、questions 等）

### Chain-of-Thought 支持

系统支持 Qwen 模型的 `<think>` 标签进行推理，代码会自动清理这些标签（第 189-205 行）。如果需要查看模型的推理过程，可以在这部分添加日志输出。

