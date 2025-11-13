# OpenReview 论文处理工具集

批量处理OpenReview论文的PDF和评审数据的工具脚本。

## 工具列表

### 1. extract_notes.py
从完整的评审数据中提取指定数量的论文信息。

**用法：**
```bash
# 提取前100个论文（默认）
python extract_notes.py

# 提取指定数量
python extract_notes.py --num 50
```

### 2. copy_pdfs_from_output.py
根据JSON文件批量复制对应的PDF文件。

**用法：**
```bash
# 使用默认配置
python copy_pdfs_from_output.py

# 自定义参数
python copy_pdfs_from_output.py --json review_conversations_100.json --source /path/to/source --output pdfs --workers 8
```

**参数：**
- `--json`: JSON文件路径（默认：review_conversations_100.json）
- `--source`: 源PDF目录（默认：/remote-home1/bwli/get_open_review/output/pdfs）
- `--output`: 输出目录（默认：pdfs）
- `--workers`: 并发线程数（默认：4）

### 3. process_pdf_fully.py
批量提取PDF文本内容，使用vLLM部署的qwen-vl-max模型。

**用法：**
```bash
# 使用默认配置（pdfs/ -> extracted_contents/）
python process_pdf_fully.py

# 自定义路径
python process_pdf_fully.py --input /path/to/pdfs --output /path/to/output
```

**参数：**
- `--input`: PDF输入文件夹（默认：pdfs）
- `--output`: 文本输出文件夹（默认：extracted_contents）

**注意：** 需要vLLM服务运行在 `http://10.176.59.101:8001/v1`

## 典型工作流程

```bash
# 1. 提取前100个论文的评审数据
python extract_notes.py --num 100

# 2. 复制对应的PDF文件
python copy_pdfs_from_output.py

# 3. 批量提取PDF文本
python process_pdf_fully.py
```

## 依赖环境

- Python 3.7+
- pdf2image, Pillow, openai, pdfplumber
- Poppler (系统依赖)
- vLLM服务（用于PDF文本提取）

