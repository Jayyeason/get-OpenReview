# OpenReview 数据字段详细说明文档

## 概述

本文档详细说明了从 OpenReview 平台抓取的数据中各个字段的含义和用途。数据以 NDJSON（Newline Delimited JSON）格式存储在 `all_notes.ndjson` 文件中，每行代表一个 note（笔记/条目）。

## 数据结构类型

OpenReview 中的数据主要包含以下几种类型的条目：
1. **论文提交（Submissions）** - 作者提交的论文
2. **评审意见（Reviews）** - 评审员的评审报告
3. **评论回复（Comments）** - 对论文或评审的回复
4. **撤稿声明（Withdrawals）** - 论文撤稿声明
5. **决定通知（Decisions）** - 会议的接收/拒绝决定

## 核心字段说明

### 基础标识字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `id` | String | 条目的唯一标识符 | `"ahI3J6wSLJ"` |
| `forum` | String | 所属论文的论坛ID，通常是论文提交的ID | `"5sRnsubyAK"` |
| `replyto` | String | 回复的目标ID，如果是顶级条目则与forum相同 | `"5sRnsubyAK"` |

### 时间戳字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `cdate` | Number | 创建时间戳（毫秒） | `1732259449478` |
| `mdate` | Number | 最后修改时间戳（毫秒） | `1732259449478` |

### 权限控制字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `signatures` | Array | 签名者身份列表 | `["ICLR.cc/2025/Conference/Submission14296/Authors"]` |
| `writers` | Array | 有写权限的身份列表 | `["ICLR.cc/2025/Conference"]` |
| `readers` | Array | 有读权限的身份列表 | `["everyone"]` |
| `nonreaders` | Array | 被禁止阅读的身份列表 | `[]` |

### 邀请和许可字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `invitations` | Array | 相关的邀请类型列表 | `["ICLR.cc/2025/Conference/Submission14296/-/Withdrawal"]` |
| `license` | String | 内容许可证 | `"CC BY 4.0"` |

## 内容字段（content）

`content` 字段是一个对象，包含条目的具体内容。不同类型的条目有不同的内容结构：

### 论文提交内容字段

| 字段名 | 说明 | 示例 |
|--------|------|------|
| `title` | 论文标题 | `{"value": "Paper Title Here"}` |
| `abstract` | 论文摘要 | `{"value": "Abstract content..."}` |
| `authors` | 作者列表 | `{"value": ["Author1", "Author2"]}` |
| `authorids` | 作者ID列表 | `{"value": ["~Author1", "~Author2"]}` |
| `keywords` | 关键词 | `{"value": ["ML", "AI", "Deep Learning"]}` |
| `primary_area` | 主要研究领域 | `{"value": "machine learning"}` |
| `code_of_ethics` | 伦理声明 | `{"value": "I acknowledge..."}` |
| `submission_guidelines` | 提交指南确认 | `{"value": "I certify..."}` |

### 评审内容字段

| 字段名 | 说明 | 评分范围 |
|--------|------|----------|
| `summary` | 评审总结 | `{"value": "The paper introduces..."}` |
| `soundness` | 技术可靠性评分 | 1-4 分 |
| `presentation` | 表达清晰度评分 | 1-4 分 |
| `contribution` | 贡献度评分 | 1-4 分 |
| `strengths` | 论文优点 | `{"value": "Strong points..."}` |
| `weaknesses` | 论文缺点 | `{"value": "Weak points..."}` |
| `questions` | 问题和建议 | `{"value": "Questions for authors..."}` |
| `flag_for_ethics_review` | 伦理审查标记 | `{"value": ["No ethics review needed."]}` |
| `rating` | 总体评分 | 1-10 分 |
| `confidence` | 评审员信心度 | 1-5 分 |
| `code_of_conduct` | 行为准则确认 | `{"value": "Yes"}` |

### 撤稿内容字段

| 字段名 | 说明 |
|--------|------|
| `withdrawal_confirmation` | 撤稿确认声明 |

## 常见邀请类型（invitations）

| 邀请类型 | 说明 |
|----------|------|
| `Conference/-/Submission` | 论文提交 |
| `Conference/Paper123/-/Official_Review` | 官方评审 |
| `Conference/Paper123/-/Official_Comment` | 官方评论 |
| `Conference/Paper123/-/Withdrawal` | 论文撤稿 |
| `Conference/Paper123/-/Decision` | 接收决定 |
| `Conference/-/Edit` | 编辑权限 |

## 身份标识说明

### 签名者身份（signatures）
- `Conference/Paper123/Authors` - 论文作者
- `Conference/Paper123/Reviewer_ABC` - 评审员（匿名化）
- `Conference/Program_Chairs` - 程序主席
- `Conference/Area_Chairs` - 领域主席

### 用户ID格式
- `~FirstName_LastName1` - 注册用户的标准格式
- `Conference/Paper123/Reviewer_ABC` - 匿名评审员


## 数据完整性

- 每个 note 都有唯一的 `id`
- `forum` 字段将相关的 notes 关联到同一篇论文
- `replyto` 字段构建了评论的层次结构
- 时间戳记录了完整的时间线信息

