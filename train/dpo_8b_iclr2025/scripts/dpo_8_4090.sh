#!/bin/bash

#SBATCH --partition=fnlp-4090d
#SBATCH --job-name=qwen3_8b_dpo_train
# 移除 --nodelist 限制，让 Slurm 自动分配可用节点
# 如果必须使用特定节点，请确保该节点没有其他作业占用 GPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:8
#SBATCH --cpus-per-task=8
#SBATCH --mem-per-cpu=4G
#SBATCH --output=qwen3-8b-dpo-8gpu.log

######################### 1. 激活环境 #########################
source ~/.bashrc
# TODO: 如果你有专门的 llama-factory 环境，在这里改掉
conda activate /remote-home1/bwli/miniconda3/envs/dpo

# 检查并安装 bitsandbytes（用于 8bit 优化器，节省显存）
if ! python -c "import bitsandbytes" 2>/dev/null; then
    echo "bitsandbytes 未安装，正在安装..."
    pip install bitsandbytes>=0.39.0
fi

######################### 2. 清理残留进程和 GPU 显存 ######################
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORCE_CLEAN_SCRIPT="${SCRIPT_DIR}/force_clean_gpu.sh"

if [ -f "$FORCE_CLEAN_SCRIPT" ]; then
    echo "使用强制清理脚本清理 GPU 显存..."
    bash "$FORCE_CLEAN_SCRIPT"
else
    echo "强制清理脚本不存在，使用基本清理方法..."
    echo "=========================================="
    echo "清理残留进程和显存..."
    # 查找并终止可能残留的训练进程
    pkill -9 -f "llamafactory-cli" 2>/dev/null || true
    pkill -9 -f "torchrun.*llamafactory" 2>/dev/null || true
    pkill -9 -f "python.*launcher.py" 2>/dev/null || true
    # 等待进程完全退出和显存释放（显存释放需要更长时间）
    echo "等待进程退出和显存释放..."
    sleep 10
    # 尝试清理 CUDA 缓存（如果 Python 可用）
    python3 -c "import torch; torch.cuda.empty_cache()" 2>/dev/null || true
    sleep 5
    echo "清理完成"
    echo "=========================================="
fi

######################### 3. 基本信息打印 ######################
echo "=========================================="
echo "作业分配信息:"
echo "节点名称      : $(hostname)"
echo "节点IP地址    : $(hostname -I | awk '{print $1}')"
echo "作业ID        : $SLURM_JOB_ID"
echo "分区          : $SLURM_JOB_PARTITION"
echo "节点列表      : $SLURM_JOB_NODELIST"
echo "=========================================="

echo "环境检查:"
which python
echo "Python版本: $(python --version)"
echo "LLaMA-Factory 版本: $(python -c 'import llamafactory, inspect; print(getattr(llamafactory, \"__version__\", \"unknown\"))' 2>/dev/null || echo 'not found')"
echo "=========================================="

######################### 4. 训练配置 #########################
# 项目根目录（按你实际情况改）
PROJECT_ROOT="/remote-home1/bwli/get_open_review/train/dpo_8b_iclr2025"
CONFIG_PATH="${PROJECT_ROOT}/configs/dpo.yaml"

# 显卡设置：单机 8 卡
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

# NCCL / 通信相关（常用的一些安全设置）
export NCCL_DEBUG=INFO
export NCCL_IB_DISABLE=0
export NCCL_SOCKET_IFNAME=^lo,docker
export OMP_NUM_THREADS=4

# PyTorch 内存管理（避免内存碎片化）
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

echo "使用配置文件: ${CONFIG_PATH}"
echo "CUDA_VISIBLE_DEVICES = ${CUDA_VISIBLE_DEVICES}"
echo "=========================================="


######################### 5. 启动 DPO 训练 ####################
cd /remote-home1/bwli/LLaMA-Factory   # 很重要！进入仓库目录（可选但推荐）

echo "开始使用 llamafactory-cli 启动 LLaMA-Factory DPO 训练..."
echo "=========================================="
# 注意：llamafactory-cli 内部会自动调用 torchrun，不需要外层再调用
# GPU 数量已在第40行通过 CUDA_VISIBLE_DEVICES 设置

srun llamafactory-cli train "${CONFIG_PATH}"