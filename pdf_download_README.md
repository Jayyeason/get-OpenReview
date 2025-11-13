# PDF Downloader - 独立的 PDF 下载工具

这是一个从 OpenReview submissions.csv 中批量下载 PDF 的独立脚本，支持断点续传和多线程下载。

## 功能特性

✅ **断点续传** - 中断后可以从上次的位置继续下载  
✅ **多线程下载** - 支持并发下载，提高效率  
✅ **进度追踪** - 实时显示下载进度和统计信息  
✅ **失败重试** - 可以重新下载失败的 PDF  
✅ **彩色输出** - 清晰的状态提示和进度显示  

## 安装要求

```bash
# Python 3.6+，无需额外依赖（使用标准库）
```

## 基本用法

### 1. 基础下载

```bash
# 下载到 pdfs 目录（会自动查找 submissions.csv）
python download_pdfs.py --dir pdfs

# 或者使用绝对路径
python download_pdfs.py --dir /path/to/output/pdfs
```

### 2. 指定 CSV 文件

```bash
# 如果 submissions.csv 不在默认位置，可以手动指定
python download_pdfs.py --dir pdfs --csv /path/to/submissions.csv
```

### 3. 调整并发数

```bash
# 使用 10 个线程并发下载（默认 5 个）
python download_pdfs.py --dir pdfs --workers 10
```

### 4. 重试失败的下载

```bash
# 重新下载之前失败的 PDF
python download_pdfs.py --dir pdfs --retry-failed
```

### 5. 重新开始下载

```bash
# 清除断点文件，从头开始
python download_pdfs.py --dir pdfs --clean-start
```

## 完整参数列表

| 参数 | 必需 | 说明 | 默认值 |
|------|------|------|--------|
| `--dir` | ✅ | PDF 输出目录 | 无 |
| `--csv` | ❌ | submissions.csv 路径 | `<dir>/../submissions.csv` |
| `--workers` | ❌ | 并发下载线程数 | 5 |
| `--retry-failed` | ❌ | 重新下载失败的 PDF | False |
| `--clean-start` | ❌ | 忽略断点，重新开始 | False |
| `--timeout` | ❌ | 下载超时时间（秒） | 30 |

## 使用场景

### 场景 1: 配合主脚本使用

```bash
# 第一步：运行主脚本，跳过 PDF 下载
python run_with_resume.py --venue "ICLR.cc/2025/Conference" --out ./output --no-pdf

# 第二步：使用独立脚本下载 PDF
python download_pdfs.py --dir ./output/pdfs
```

### 场景 2: 单独下载 PDF

```bash
# 如果你已经有了 submissions.csv，可以直接下载 PDF
python download_pdfs.py --dir ./my_pdfs --csv ./data/submissions.csv --workers 10
```

### 场景 3: 网络中断后继续

```bash
# 网络恢复后，直接运行相同命令即可从断点继续
python download_pdfs.py --dir pdfs
```

### 场景 4: 下载失败重试

```bash
# 首次下载
python download_pdfs.py --dir pdfs

# 如果有部分失败，可以重试
python download_pdfs.py --dir pdfs --retry-failed
```

## 断点文件

脚本会在输出目录下创建两个断点文件：

- `.pdf_download_progress.pkl` - 二进制进度文件（用于恢复）
- `.pdf_download_state.json` - 可读的状态文件（查看进度）

### 查看进度

```bash
# 查看当前下载状态
cat pdfs/.pdf_download_state.json
```

示例输出：
```json
{
  "downloaded_count": 1250,
  "failed_count": 15,
  "total_pdfs": 2000,
  "progress_percentage": 62.5,
  "start_time": "2025-10-28T10:30:00",
  "last_update": "2025-10-28T11:45:00"
}
```

## 输出示例

```
============================================================
📥 OpenReview PDF 下载器
============================================================

📄 CSV 文件: /path/to/submissions.csv
📁 输出目录: /path/to/pdfs
🔧 并发线程: 5

✅ 从 CSV 加载了 2000 个PDF链接

📊 统计信息:
  总PDF数: 2000
  已下载: 1250
  待下载: 750

============================================================
🚀 开始下载 PDF...
============================================================

✅ 成功: AbC123.pdf
   ████████████████░░░░░░░░░░░░░░ 62.6% 1251/2000
✅ 成功: DeF456.pdf
   ████████████████░░░░░░░░░░░░░░ 62.7% 1252/2000
...

============================================================
📊 下载完成统计
============================================================
  ✅ 成功: 750
  ❌ 失败: 0
  📁 总计已下载: 2000/2000
  📊 完成度: 100.0%
============================================================

🎉 所有PDF下载完成！清理断点文件...
```

## 常见问题

### Q: CSV 文件格式要求？

A: CSV 必须包含以下字段：
- `forum` 或 `note_id` - 论文 ID
- `pdf` - PDF URL（可以是 JSON 格式 `{"value": "url"}` 或直接是 URL）

### Q: 如何提高下载速度？

A: 使用 `--workers` 增加并发数，例如 `--workers 10`

### Q: 下载失败怎么办？

A: 
1. 直接重新运行相同命令（会跳过已下载的）
2. 使用 `--retry-failed` 重试失败项

### Q: 如何清除所有进度重新开始？

A: 使用 `--clean-start` 参数

### Q: 支持代理吗？

A: 脚本使用 Python 标准库的 urllib，会自动读取系统代理设置（HTTP_PROXY、HTTPS_PROXY 环境变量）

## 与主脚本的区别

| 特性 | 主脚本 (run_with_resume.py) | PDF下载器 (download_pdfs.py) |
|------|----------------------------|------------------------------|
| 功能 | 数据爬取 + PDF下载 | 仅 PDF 下载 |
| 依赖 | openreview-py | 无（标准库） |
| 速度 | 较慢（受API限制） | 快速（多线程） |
| 适用场景 | 首次完整爬取 | 补充下载/单独下载 |

## 示例工作流

```bash
# 完整工作流示例

# 1. 快速获取数据（跳过 PDF）
python run_with_resume.py \
    --venue "ICLR.cc/2025/Conference" \
    --out ./iclr2025 \
    --no-pdf

# 2. 使用独立脚本高速下载 PDF（10线程）
python download_pdfs.py \
    --dir ./iclr2025/pdfs \
    --workers 10

# 3. 如果有失败的，重试
python download_pdfs.py \
    --dir ./iclr2025/pdfs \
    --retry-failed
```

## 许可证

与主项目保持一致

