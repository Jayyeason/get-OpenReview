# OpenReview 断点续传下载器

## 功能特性

这是基于原始 `run.py` 改进的版本，新增了以下断点续传功能：

### 🔄 断点续传
- **自动保存进度**: 每处理一定数量的论坛后自动保存下载进度
- **智能恢复**: 程序中断后重新运行时自动从断点继续下载
- **数据去重**: 避免重复下载已存在的数据
- **进度可视化**: 实时显示下载进度和完成百分比

### 📊 进度跟踪
- **二进制进度文件**: `.download_progress.pkl` 存储详细的下载状态
- **可读状态文件**: `.download_state.json` 提供人类可读的进度信息
- **多层级跟踪**: 分别跟踪投稿、论坛和notes的处理状态

### 📄 PDF下载功能
- **异步PDF下载**: 使用多线程并发下载PDF文件，提高效率
- **PDF进度跟踪**: 独立跟踪PDF下载进度，支持断点续传
- **可配置工作线程**: 支持自定义PDF下载并发数（默认3个线程）
- **跳过PDF选项**: 可选择跳过PDF下载以加快数据收集速度
- **智能PDF处理**: 仅为投稿论文下载PDF，评论等不下载PDF

### 🛡️ 数据安全
- **增量写入**: 新数据以追加模式写入，避免覆盖已有数据
- **异常处理**: 网络错误或API限制时保存当前进度
- **用户中断保护**: Ctrl+C 中断时安全保存进度

### 🎨 用户体验
- **彩色输出**: 使用ANSI颜色代码提供清晰的状态指示
- **实时进度条**: PDF下载显示详细的进度条和统计信息
- **详细日志**: 提供丰富的状态信息和错误提示

## 使用方法

### 基本用法
```bash
# 开始新的下载任务
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output

# 从断点继续下载（自动检测）
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output
```

### 高级选项
```bash
# 清理断点，重新开始
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output --clean-start

# 调整进度保存频率（每5个论坛保存一次）
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output --progress-interval 5

# 设置更快的下载速度（谨慎使用）
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output --sleep 0.2

# 限制下载数量进行测试
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output --limit 10

# 配置PDF下载选项
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output --pdf-workers 5  # 使用5个PDF下载线程
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output --no-pdf        # 跳过PDF下载

# 使用认证（如果需要）
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output --username your_email --password your_password

# 自定义API端点
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output --baseurl "https://api2.openreview.net"
```

### 完整参数列表
- `--venue`: 会议ID（必需），如 "ICLR.cc/2025/Conference" 或 "TMLR"
- `--out`: 输出目录（必需）
- `--baseurl`: OpenReview API地址（默认: https://api2.openreview.net）
- `--username`: OpenReview用户名（可选）
- `--password`: OpenReview密码（可选）
- `--sleep`: 请求间隔秒数（默认: 0.5）
- `--limit`: 限制下载论文数量，用于测试（可选）
- `--pdf-workers`: PDF下载并发线程数（默认: 3）
- `--no-pdf`: 跳过PDF下载以加快数据收集
- `--clean-start`: 忽略断点文件，重新开始下载
- `--progress-interval`: 每处理多少个论坛保存一次进度（默认: 10）

在下载后，可以使用ndjson_to_json_converter.py去将all_notes.ndjson转换为JSON格式，方便阅读

## 独立PDF下载器

项目还提供了一个独立的PDF下载脚本 `pdf_downloader.py`，可以从CSV、JSON或NDJSON文件中批量下载PDF，支持断点续传。

### PDF下载器特性

- **🔄 断点续传**: 支持中断后继续下载，进度自动保存
- **🚀 多线程下载**: 支持并发下载，可自定义线程数
- **📁 多格式支持**: 支持从 CSV、JSON、NDJSON 文件读取PDF链接
- **🎯 智能去重**: 自动跳过已下载的PDF文件
- **🎨 友好界面**: 彩色输出和实时进度显示
- **🛡️ 错误处理**: 完善的错误处理和重试机制

### PDF下载器使用方法

#### 基本用法
```bash
# 从CSV文件下载PDF到output/pdfs目录
python pdf_downloader.py --input submissions.csv --dir output

# 从NDJSON文件下载PDF
python pdf_downloader.py --input all_notes.ndjson --dir output

# 从JSON文件下载PDF
python pdf_downloader.py --input data.json --dir output
```

#### 高级选项
```bash
# 使用更多线程加速下载（默认3个线程）
python pdf_downloader.py --input submissions.csv --dir output --workers 5

# 设置下载超时时间（默认30秒）
python pdf_downloader.py --input submissions.csv --dir output --timeout 60

# 重试之前失败的下载
python pdf_downloader.py --input submissions.csv --dir output --retry-failed

# 忽略断点文件，重新开始下载
python pdf_downloader.py --input submissions.csv --dir output --clean-start

# 测试模式：只下载前10个PDF
python pdf_downloader.py --input submissions.csv --dir output --limit 10
```

#### 完整参数列表
- `--input`: 输入文件路径（必需，支持 .csv, .json, .ndjson）
- `--dir`: 输出目录（默认 "output"，PDF保存到 `<dir>/pdfs`）
- `--workers`: 并发线程数（默认 3）
- `--timeout`: 下载超时时间（默认 30秒）
- `--clean-start`: 忽略断点文件，重新开始
- `--retry-failed`: 重试之前失败的下载
- `--limit`: 限制下载数量（测试用）

### 断点续传机制

PDF下载器会在输出目录下创建 `.download` 文件夹，包含：
- `.pdf_download_progress.pkl`: 二进制进度文件（程序内部使用）
- `.pdf_download_state.json`: 可读的状态文件（查看进度用）

#### 如何恢复中断的下载

1. **自动恢复**（推荐）：
   ```bash
   # 直接重新运行相同的命令，脚本会自动从断点继续
   python pdf_downloader.py --input submissions.csv --dir output
   ```

2. **重试失败的下载**：
   ```bash
   # 如果想重试之前失败的下载
   python pdf_downloader.py --input submissions.csv --dir output --retry-failed
   ```

3. **完全重新开始**：
   ```bash
   # 如果想忽略之前的进度，重新开始
   python pdf_downloader.py --input submissions.csv --dir output --clean-start
   ```

### 输入文件格式要求

#### CSV格式
CSV文件需要包含 `pdf` 列，例如：
```csv
forum,note_id,title,pdf
forum1,note1,Paper Title 1,https://openreview.net/pdf?id=abc123
forum2,note2,Paper Title 2,/pdf?id=def456
```

#### JSON格式
```json
[
  {
    "forum": "forum1",
    "pdf": "https://openreview.net/pdf?id=abc123",
    "title": "Paper Title 1"
  }
]
```

#### NDJSON格式
```json
{"forum": "forum1", "pdf": "https://openreview.net/pdf?id=abc123", "title": "Paper Title 1"}
{"forum": "forum2", "pdf": "/pdf?id=def456", "title": "Paper Title 2"}
```

### 状态文件示例
`.pdf_download_state.json` 文件内容示例：
```json
{
  "downloaded_pdfs_count": 150,
  "failed_pdfs_count": 5,
  "total_pdfs": 200,
  "success_rate": 75.0,
  "start_time": "2024-01-15T10:30:00",
  "last_update": "2024-01-15T11:45:00"
}
```

## 文件说明

### 输出文件
- `submissions.csv`: 投稿列表，包含论文基本信息
- `all_notes.ndjson`: 所有notes的压缩NDJSON格式，包含论文、评审、回复等完整数据
- `reviews.csv`: 评审数据的结构化CSV格式
- `pdfs/`: PDF文件目录，存储下载的论文PDF文件
  - 文件命名格式: `{forum_id}.pdf`
  - 仅包含投稿论文的PDF，不包含评审意见的PDF

### 进度文件
- `.download_progress.pkl`: 二进制进度文件（程序内部使用）
  - 存储已处理的论坛ID、note ID和PDF下载状态
  - 支持快速断点恢复
- `.download_state.json`: 可读的下载状态文件
  - 提供人类可读的进度信息
  - 包含时间戳、百分比等统计数据

### 示例状态文件内容
```json
{
  "processed_submissions": 150,
  "total_submissions": 3000,
  "processed_forums_count": 150,
  "processed_notes_count": 2847,
  "downloaded_pdfs_count": 145,
  "progress_percentage": 5.0,
  "start_time": "2024-01-15T10:30:00",
  "last_update": "2024-01-15T11:45:00",
  "venue": "ICLR.cc/2025/Conference"
}
```

## 断点续传原理

### 1. 进度跟踪
- 使用 `set` 数据结构记录已处理的论坛ID和note ID
- 每个阶段完成后立即更新进度状态
- 定期将进度持久化到磁盘

### 2. 数据去重
- 启动时检查已存在的输出文件
- 解析已下载的数据，提取ID列表
- 跳过已存在的数据，只下载新内容

### 3. 增量写入
- NDJSON文件以追加模式打开
- JSON数组在内存中累积，最后一次性写入
- CSV文件重新生成（包含所有数据）

### 4. 异常恢复
- 捕获网络异常和用户中断
- 在异常发生时保存当前进度
- 下次启动时从最后保存的状态继续

## 性能优化建议

### 1. 调整下载间隔
```bash
# 保守设置（推荐）
--sleep 0.5

# 平衡设置
--sleep 0.3

# 激进设置（可能触发限制）
--sleep 0.2
```

### 2. 调整进度保存频率  
```bash
# 频繁保存（更安全，但I/O开销大）
--progress-interval 5

# 标准设置
--progress-interval 10

# 较少保存（性能更好，但断点间隔大）
--progress-interval 20
```
