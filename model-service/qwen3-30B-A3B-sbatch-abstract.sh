#!/bin/bash

#SBATCH --partition=fnlp-4090d
#SBATCH --nodelist=fnlp-4090-59105
#SBATCH --job-name=qwen3_30b_a3b_vllm_service
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=4
#SBATCH --mem-per-cpu=4G
#SBATCH --output=qwen3-30b-a3b-vllm-slurm-abstract.log
###SBATCH --kill-on-bad-exit=1

# 激活 conda 环境
source ~/.bashrc
conda activate /remote-home1/qfwu/miniconda3/envs/diffuser

# 获取并输出当前节点信息
echo "=========================================="
echo "作业分配信息:"
echo "节点名称: $(hostname)"
echo "节点IP地址: $(hostname -I | awk '{print $1}')"
echo "作业ID: $SLURM_JOB_ID"
echo "分区: $SLURM_JOB_PARTITION"
echo "节点列表: $SLURM_JOB_NODELIST"
echo "分配的GPU: $CUDA_VISIBLE_DEVICES"
echo "=========================================="

# 检查环境
echo "环境检查:"
which python
echo "Python版本: $(python --version)"
echo "Transformers版本: $(python -c 'import transformers; print(transformers.__version__)')"
echo "vLLM版本: $(python -c 'import vllm; print(vllm.__version__)')"
echo "=========================================="

# 配置参数
MODEL_PATH="/remote-home1/share/models/Qwen/Qwen3-30B-A3B"
PORT=8004
HOST="0.0.0.0"
TENSOR_PARALLEL_SIZE=4

# 启动 vLLM 服务
echo "启动 Qwen3-30B-A3B (MoE) vLLM 服务..."
echo "模型路径: ${MODEL_PATH}"
echo "监听地址: ${HOST}:${PORT}"
echo "GPU数量: ${TENSOR_PARALLEL_SIZE}"
echo "=========================================="

# 启动服务（前台运行，让 Slurm 管理进程）
vllm serve ${MODEL_PATH} \
    --host ${HOST} \
    --port ${PORT} \
    --served-model-name qwen3-30b-a3b \
    --trust-remote-code \
    --tensor-parallel-size ${TENSOR_PARALLEL_SIZE} \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.75 \
    --dtype auto

# 注意：不使用 & 后台运行，让 Slurm 管理进程生命周期