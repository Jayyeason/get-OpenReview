#!/bin/bash

# ============================================================
# 打包 conda dpo 环境为 .tar 镜像（不压缩）
# 使用方法：
#   bash pack_dpo_env_tar.sh [output_path]
# ============================================================

set -e

# 环境路径
ENV_PATH="/remote-home1/bwli/miniconda3/envs/dpo"
ENV_NAME="dpo"

# 输出路径（如果未指定，使用当前目录）
OUTPUT_PATH="${1:-/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025}"
OUTPUT_FILE="${OUTPUT_PATH}/${ENV_NAME}_env_$(date +%Y%m%d_%H%M%S).tar"

echo "=========================================="
echo "打包 conda 环境: ${ENV_NAME}"
echo "环境路径: ${ENV_PATH}"
echo "输出文件: ${OUTPUT_FILE}"
echo "=========================================="

# 检查环境是否存在
if [ ! -d "$ENV_PATH" ]; then
    echo "错误: 环境路径不存在: ${ENV_PATH}"
    exit 1
fi

# 检查输出目录是否存在
OUTPUT_DIR=$(dirname "$OUTPUT_FILE")
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "创建输出目录: ${OUTPUT_DIR}"
    mkdir -p "$OUTPUT_DIR"
fi

echo "开始打包（不压缩，纯 .tar 格式）..."
echo "这可能需要一些时间（环境大小约 34GB，打包后可能更大）..."

# 打包环境，排除缓存和临时文件
# --exclude 选项排除：
# - __pycache__: Python 缓存
# - *.pyc: Python 编译文件
# - .cache: 各种缓存目录
# - pip cache
# - conda cache
# - 临时文件
tar -cf "$OUTPUT_FILE" \
    -C "$(dirname "$ENV_PATH")" \
    --exclude="*.pyc" \
    --exclude="__pycache__" \
    --exclude="*.pyo" \
    --exclude="*.pyd" \
    --exclude=".cache" \
    --exclude="pip" \
    --exclude="*.egg-info" \
    --exclude=".pytest_cache" \
    --exclude=".mypy_cache" \
    --exclude=".ipynb_checkpoints" \
    --exclude="*.log" \
    --exclude="*.tmp" \
    --exclude="*.swp" \
    --exclude="*.swo" \
    --exclude="*~" \
    "$(basename "$ENV_PATH")"

# 检查打包是否成功
if [ $? -eq 0 ]; then
    echo "=========================================="
    echo "✓ 打包成功！"
    echo "输出文件: ${OUTPUT_FILE}"
    echo "文件大小: $(du -h "$OUTPUT_FILE" | cut -f1)"
    echo "=========================================="
    echo ""
    echo "恢复环境的方法："
    echo "1. 解压到目标位置："
    echo "   tar -xf ${OUTPUT_FILE} -C /path/to/miniconda3/envs/"
    echo ""
    echo "2. 或者解压到自定义位置后，创建软链接："
    echo "   tar -xf ${OUTPUT_FILE} -C /custom/path/"
    echo "   ln -s /custom/path/${ENV_NAME} /path/to/miniconda3/envs/${ENV_NAME}"
    echo ""
    echo "3. 激活环境："
    echo "   conda activate ${ENV_NAME}"
    echo ""
    echo "注意：如果需要在其他机器上使用，可能需要："
    echo "- 修改环境中的绝对路径（如果有硬编码的路径）"
    echo "- 确保 Python 版本兼容"
    echo "=========================================="
else
    echo "✗ 打包失败！"
    exit 1
fi

