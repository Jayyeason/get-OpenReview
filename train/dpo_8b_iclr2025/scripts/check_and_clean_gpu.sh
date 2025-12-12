#!/bin/bash
# 检查并清理 GPU 显存（在计算节点上运行）

echo "=========================================="
echo "检查 GPU 显存使用情况..."
echo "=========================================="

# 检查 nvidia-smi 是否可用
if ! command -v nvidia-smi &> /dev/null; then
    echo "错误: nvidia-smi 不可用"
    exit 1
fi

# 显示 GPU 使用情况
echo "当前 GPU 使用情况:"
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits | \
    awk -F', ' '{printf "GPU %s: %s MB / %s MB (使用率: %s%%)\n", $1, $3, $4, $5}'

echo ""
echo "占用 GPU 的进程:"
nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid --format=csv,noheader | \
    awk -F', ' '{printf "PID: %s, 进程: %s, 显存: %s, GPU: %s\n", $1, $2, $3, $4}'

echo ""
echo "=========================================="
echo "清理选项:"
echo "=========================================="
echo "1. 清理当前用户的进程（自动）"
echo "2. 查看所有占用 GPU 的进程"
echo "3. 手动清理（需要进程 PID）"
echo "=========================================="

# 获取当前用户
CURRENT_USER=$(whoami)
echo "当前用户: $CURRENT_USER"
echo ""

# 查找当前用户的进程
USER_PROCESSES=$(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null | \
    while IFS=',' read pid name mem; do
        if ps -p "${pid// /}" -o user= 2>/dev/null | grep -q "^$CURRENT_USER"; then
            echo "${pid// /} $name $mem"
        fi
    done)

if [ -z "$USER_PROCESSES" ]; then
    echo "✓ 当前用户没有占用 GPU 的进程"
else
    echo "发现当前用户的进程占用 GPU:"
    echo "$USER_PROCESSES" | while read pid name mem; do
        echo "  PID: $pid, 进程: $name, 显存: $mem"
        echo "  终止进程: kill -9 $pid"
    done
fi

echo ""
echo "=========================================="
echo "清理 CUDA 缓存（如果 Python 可用）..."
echo "=========================================="
if command -v python3 &> /dev/null; then
    python3 << 'PYTHON_SCRIPT'
import torch
if torch.cuda.is_available():
    print(f"CUDA 可用，设备数量: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        torch.cuda.set_device(i)
        torch.cuda.empty_cache()
        allocated = torch.cuda.memory_allocated(i) / 1024**2
        reserved = torch.cuda.memory_reserved(i) / 1024**2
        print(f"GPU {i}: 已分配 {allocated:.2f} MB, 已保留 {reserved:.2f} MB")
    print("✓ CUDA 缓存已清理")
else:
    print("CUDA 不可用")
PYTHON_SCRIPT
else
    echo "Python3 不可用，跳过 CUDA 缓存清理"
fi

echo ""
echo "=========================================="
echo "检查完成！"
echo "=========================================="

