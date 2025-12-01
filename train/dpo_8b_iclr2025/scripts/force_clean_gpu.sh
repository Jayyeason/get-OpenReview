#!/bin/bash
# 强制清理 GPU 显存（在计算节点上运行）

echo "=========================================="
echo "强制清理 GPU 显存..."
echo "=========================================="

CURRENT_USER=$(whoami)
echo "当前用户: $CURRENT_USER"
echo ""

# 1. 查找并终止当前用户的所有 Python/PyTorch 进程
echo "1. 查找占用 GPU 的进程..."
if command -v nvidia-smi &> /dev/null; then
    # 获取占用 GPU 的进程 PID
    GPU_PIDS=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | tr -d ' ')
    
    if [ -n "$GPU_PIDS" ]; then
        echo "发现占用 GPU 的进程:"
        for pid in $GPU_PIDS; do
            # 检查进程是否属于当前用户
            if ps -p "$pid" -o user= 2>/dev/null | grep -q "^$CURRENT_USER"; then
                process_info=$(ps -p "$pid" -o pid,user,cmd --no-headers 2>/dev/null)
                echo "  PID $pid: $process_info"
                echo "  终止进程..."
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
    else
        echo "  未发现占用 GPU 的进程"
    fi
else
    echo "  nvidia-smi 不可用，使用通用方法清理..."
    # 通用方法：终止当前用户的 Python 进程
    pkill -9 -u "$CURRENT_USER" -f "python.*llamafactory" 2>/dev/null || true
    pkill -9 -u "$CURRENT_USER" -f "torchrun" 2>/dev/null || true
fi

# 2. 等待进程退出
echo ""
echo "2. 等待进程退出和显存释放..."
sleep 10

# 3. 清理 CUDA 缓存
echo ""
echo "3. 清理 CUDA 缓存..."
if command -v python3 &> /dev/null; then
    python3 << 'PYTHON_SCRIPT'
import torch
import sys

if not torch.cuda.is_available():
    print("  CUDA 不可用")
    sys.exit(0)

print(f"  CUDA 可用，设备数量: {torch.cuda.device_count()}")

for i in range(torch.cuda.device_count()):
    torch.cuda.set_device(i)
    torch.cuda.empty_cache()
    torch.cuda.ipc_collect()
    
    allocated = torch.cuda.memory_allocated(i) / 1024**2
    reserved = torch.cuda.memory_reserved(i) / 1024**2
    
    print(f"  GPU {i}: 已分配 {allocated:.2f} MB, 已保留 {reserved:.2f} MB")

# 强制同步所有设备
torch.cuda.synchronize()
print("  ✓ CUDA 缓存已清理")
PYTHON_SCRIPT
else
    echo "  Python3 不可用，跳过 CUDA 缓存清理"
fi

# 4. 再次检查
echo ""
echo "4. 再次检查 GPU 使用情况..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits | \
        awk -F', ' '{printf "  GPU %s: %s MB / %s MB\n", $1, $2, $3}'
fi

echo ""
echo "=========================================="
echo "清理完成！"
echo "=========================================="

