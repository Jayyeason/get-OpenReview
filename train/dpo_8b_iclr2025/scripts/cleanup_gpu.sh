#!/bin/bash
# 清理残留的训练进程和显存（适用于 Slurm 环境）

echo "=========================================="
echo "清理残留进程和显存..."
echo "=========================================="

# 获取当前用户和 Slurm 作业信息
CURRENT_USER=$(whoami)
if [ -n "$SLURM_JOB_ID" ]; then
    echo "当前 Slurm 作业ID: $SLURM_JOB_ID"
    echo "当前用户: $CURRENT_USER"
fi
echo ""

# 1. 查找并终止可能残留的训练进程（只清理当前用户的进程）
echo "1. 查找残留进程（仅当前用户: $CURRENT_USER）..."
PROCESSES=$(ps aux | grep "^$CURRENT_USER" | grep -E "llamafactory-cli|torchrun.*llamafactory|python.*launcher.py" | grep -v grep | grep -v "defunct")

if [ -z "$PROCESSES" ]; then
    echo "   未发现残留进程"
else
    echo "   发现以下残留进程:"
    echo "$PROCESSES" | awk '{print "   PID:", $2, "CMD:", $11, $12, $13, $14, $15}'
    echo ""
    echo "2. 终止残留进程..."
    # 只终止当前用户的进程
    pkill -9 -u "$CURRENT_USER" -f "llamafactory-cli" 2>/dev/null || true
    pkill -9 -u "$CURRENT_USER" -f "torchrun.*llamafactory" 2>/dev/null || true
    pkill -9 -u "$CURRENT_USER" -f "python.*launcher.py" 2>/dev/null || true
    echo "   进程已终止"
fi

# 2. 等待进程完全退出和显存释放
echo "3. 等待进程完全退出和显存释放..."
sleep 10

# 3. 尝试清理 CUDA 缓存（如果 Python 可用）
echo "4. 清理 CUDA 缓存..."
if command -v python3 &> /dev/null; then
    python3 -c "import torch; torch.cuda.empty_cache(); print('   CUDA 缓存已清理')" 2>/dev/null || echo "   无法清理 CUDA 缓存（可能未安装 PyTorch）"
else
    echo "   Python3 不可用，跳过 CUDA 缓存清理"
fi

# 4. 再次检查
echo "5. 再次检查残留进程..."
REMAINING=$(ps aux | grep "^$CURRENT_USER" | grep -E "llamafactory-cli|torchrun.*llamafactory|python.*launcher.py" | grep -v grep | grep -v "defunct")

if [ -z "$REMAINING" ]; then
    echo "   ✓ 所有残留进程已清理"
else
    echo "   ⚠️  仍有残留进程:"
    echo "$REMAINING" | awk '{print "   PID:", $2, "CMD:", $11, $12, $13, $14, $15}'
    echo "   请手动检查并终止（kill -9 <PID>）"
fi

echo "=========================================="
echo "清理完成！"
echo "=========================================="

