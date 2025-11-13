# System Prompt 架构改进说明

## 📋 修改概述

将原来的**单一System Prompt模板**（通过`{strictness}`占位符切换）改为**5个独立的System Prompt**，每个严格度级别一个。

## 🔄 修改前 vs 修改后

### ❌ 修改前（旧架构）

```python
SYSTEM_PROMPT = """You are an expert academic reviewer...

## Your Reviewer Profile
**Strictness Level**: {strictness}/5

**Level 1 (Encouraging Reviewer):**
- ...

**Level 2 (Supportive Reviewer):**
- ...

**Level 3 (Objective Reviewer):**
- ...

**Level 4 (Rigorous Reviewer):**
- ...

**Level 5 (Highly Critical Reviewer):**
- ...

## Your Review Task
...
"""

# 使用时
system_prompt = SYSTEM_PROMPT.format(strictness=strictness)
```

**问题：**
- ❌ 单个prompt包含所有5个级别的描述（冗长）
- ❌ AI需要阅读所有级别才能找到自己的角色
- ❌ 可能导致混淆或角色不清晰
- ❌ 难以单独优化某个级别的prompt

### ✅ 修改后（新架构）

```python
# 1. 共享的评审任务说明
BASE_REVIEW_TASK = """
## Your Review Task
...
"""

# 2. 5个独立的System Prompt
SYSTEM_PROMPT_LEVEL_1 = """You are an expert academic reviewer...

## Your Reviewer Profile
**You are a Level 1 Encouraging Reviewer**
- ...
""" + BASE_REVIEW_TASK

SYSTEM_PROMPT_LEVEL_2 = """...""" + BASE_REVIEW_TASK
SYSTEM_PROMPT_LEVEL_3 = """...""" + BASE_REVIEW_TASK
SYSTEM_PROMPT_LEVEL_4 = """...""" + BASE_REVIEW_TASK
SYSTEM_PROMPT_LEVEL_5 = """...""" + BASE_REVIEW_TASK

# 3. 映射字典
SYSTEM_PROMPTS = {
    1: SYSTEM_PROMPT_LEVEL_1,
    2: SYSTEM_PROMPT_LEVEL_2,
    3: SYSTEM_PROMPT_LEVEL_3,
    4: SYSTEM_PROMPT_LEVEL_4,
    5: SYSTEM_PROMPT_LEVEL_5,
}

# 使用时
system_prompt = self.system_prompts.get(strictness, self.system_prompts[3])
```

**优势：**
- ✅ 每个prompt只包含对应级别的描述（简洁）
- ✅ AI角色定位清晰，专注于单一人格
- ✅ 更容易针对每个级别单独优化
- ✅ 代码结构更清晰，易于维护

## 📊 数据对比

| 维度 | 旧架构 | 新架构 |
|------|--------|--------|
| **Prompt长度** | ~6000字符（包含所有5个level） | ~4500字符（单个level） |
| **信息噪音** | 高（包含不相关的4个level） | 低（只有当前level） |
| **角色清晰度** | 中（需要从5个中识别） | 高（直接声明角色） |
| **可维护性** | 低（修改一个影响全部） | 高（独立修改） |
| **可扩展性** | 低（难以添加新级别） | 高（易于添加新级别） |

## 🎯 Prompt结构

### 新架构的Prompt结构

每个独立的System Prompt包含两部分：

```
┌─────────────────────────────────────┐
│ 1. 评审员人格描述（Level特定）       │
│    - Philosophy（哲学）              │
│    - What you value most（看重什么） │
│    - How you view flaws（如何看待缺陷）│
│    - Threshold（接收门槛）            │
│    - How you write（写作风格）        │
│    - Typical ratings（典型评分）      │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 2. BASE_REVIEW_TASK（共享）         │
│    - 评审任务说明                     │
│    - 9个评审维度                      │
│    - 输出格式要求（JSON）             │
└─────────────────────────────────────┘
```

## 💻 代码修改详情

### 1. Prompt定义部分（第21-176行）

```python
# 新增：BASE_REVIEW_TASK
BASE_REVIEW_TASK = """
## Your Review Task
...
"""

# 新增：5个独立的SYSTEM_PROMPT
SYSTEM_PROMPT_LEVEL_1 = """...""" + BASE_REVIEW_TASK
SYSTEM_PROMPT_LEVEL_2 = """...""" + BASE_REVIEW_TASK
SYSTEM_PROMPT_LEVEL_3 = """...""" + BASE_REVIEW_TASK
SYSTEM_PROMPT_LEVEL_4 = """...""" + BASE_REVIEW_TASK
SYSTEM_PROMPT_LEVEL_5 = """...""" + BASE_REVIEW_TASK

# 新增：映射字典
SYSTEM_PROMPTS = {
    1: SYSTEM_PROMPT_LEVEL_1,
    2: SYSTEM_PROMPT_LEVEL_2,
    3: SYSTEM_PROMPT_LEVEL_3,
    4: SYSTEM_PROMPT_LEVEL_4,
    5: SYSTEM_PROMPT_LEVEL_5,
}
```

### 2. ReviewerAI.__init__ 方法（第209-211行）

```python
# 修改前
self.system_prompt_template = SYSTEM_PROMPT
print(f"  ✓ 使用内置 System Prompt")

# 修改后
self.system_prompts = SYSTEM_PROMPTS
print(f"  ✓ 使用内置 System Prompts (5个独立级别)")
```

### 3. ReviewerAI.generate_review 方法（第250-251行）

```python
# 修改前
system_prompt = self.system_prompt_template.format(strictness=strictness)

# 修改后
system_prompt = self.system_prompts.get(strictness, self.system_prompts[3])
```

## 🧪 测试验证

已通过测试验证：
- ✅ 5个System Prompt都正确创建
- ✅ 每个prompt只包含对应级别的描述
- ✅ 不包含其他级别的描述（独立性）
- ✅ BASE_REVIEW_TASK在两个文件中内容一致
- ✅ 代码语法正确，无错误

## 📝 受影响的文件

1. ✅ `qwen3-8B-reviewer.py` - 已修改
2. ✅ `qwen3-30B-reviewer.py` - 已修改

两个文件的修改完全一致，保持代码同步。

## 🚀 使用方式

使用方式**完全不变**，向后兼容：

```bash
# 使用方式完全相同
python qwen3-8B-reviewer.py --limit 5

# 内部实现改进，但接口不变
```

## 💡 后续优化建议

现在每个级别的prompt都是独立的，可以：

1. **针对性优化**：根据实际效果，单独调整某个级别的描述
2. **A/B测试**：为某个级别测试不同的prompt版本
3. **添加示例**：在某些级别的prompt中添加评审示例
4. **调整评分倾向**：修改"Typical ratings"来降低整体评分基线

例如，如果Level 5评分还是太高，可以只修改：

```python
SYSTEM_PROMPT_LEVEL_5 = """You are an expert academic reviewer...

**Typical ratings**: You commonly give 1 (strong reject) or 3 (reject, not good enough).
You RARELY give scores above 5. Most papers do not meet the exceptional bar required.
"""
```

而不影响其他4个级别！

## ✨ 总结

这次改进：
- ✅ 提高了Prompt的清晰度和专注度
- ✅ 降低了AI的认知负担
- ✅ 提升了代码的可维护性
- ✅ 为后续优化打下良好基础
- ✅ 完全向后兼容，无需修改使用方式

修改日期：2025-11-02


