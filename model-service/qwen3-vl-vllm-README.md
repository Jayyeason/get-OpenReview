# Qwen3-VL vLLM 服务

Qwen3-VL-8B-Instruct 视觉语言模型的 vLLM 部署服务。

## 📊 服务配置

- **模型**: Qwen3-VL-8B-Instruct
- **GPU**: 2x NVIDIA RTX 4090 D (张量并行)
- **显存**: ~48GB 总计
- **上下文长度**: 8192 tokens
- **API 端点**: `http://localhost:8000/v1`
- **模型名称**: `qwen-vl-max`

## 🚀 快速开始

### 提交 Slurm 作业

```bash
cd /remote-home1/bwli/get_open_review/model-service
sbatch qwen-vl-sbatch.sh
```

### 查看作业状态

```bash
squeue -u $USER
```

### 查看日志

```bash
tail -f qwen-vl-vllm-slurm.log
```

### 更多操作

```bash
# 查看作业详细信息
scontrol show job <JOB_ID>

# 查看特定用户的所有作业
squeue -u $USER

# 查看日志最后 100 行
tail -n 100 qwen-vl-vllm-slurm.log
```

### 测试 API

```bash
# 测试服务是否可用
curl http://localhost:8000/v1/models

# 查看 GPU 使用情况
nvidia-smi
```

## ⚙️ 配置参数

编辑 `qwen-vl-sbatch.sh` 修改以下参数：

### Slurm 资源配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--partition` | `fnlp-4090d` | 分区名称 |
| `--nodelist` | `fnlp-4090-59108` | 指定节点 |
| `--gres=gpu` | `2` | GPU 数量 |
| `--cpus-per-task` | `12` | CPU 核心数 |
| `--mem-per-cpu` | `4G` | 每核心内存（总计 48GB） |

### 模型服务配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MODEL_PATH` | `/remote-home1/share/models/Qwen/Qwen3-VL-8B-Instruct` | 模型路径 |
| `PORT` | `8000` | API 服务端口 |
| `HOST` | `0.0.0.0` | 监听地址（0.0.0.0 允许外部访问） |
| `TENSOR_PARALLEL_SIZE` | `2` | GPU 数量（1=单卡，2=双卡并行） |
| `--max-model-len` | `8192` | 最大上下文长度 |
| `--gpu-memory-utilization` | `0.9` | GPU 显存使用率 |

## 🔧 常见问题

### 端口被占用

```bash
# 查看占用端口的进程
lsof -i :8000

# 或查找 vllm 进程
ps aux | grep "vllm serve"

# 停止作业
scancel <JOB_ID>
```

### 作业失败

```bash
# 查看日志找到错误原因
tail -n 100 qwen-vl-vllm-slurm.log

# 检查节点状态
sinfo -N -l

# 重新提交作业
sbatch qwen-vl-sbatch.sh
```

### 清空日志

```bash
# 备份旧日志
mv qwen-vl-vllm-slurm.log qwen-vl-vllm-slurm.log.backup
```

## 🔗 API 使用

### Python 示例

```python
import openai
import base64

# 初始化客户端
client = openai.OpenAI(
    api_key="EMPTY",
    base_url="http://localhost:8000/v1"
)

# 读取图片并转换为 base64
with open("image.jpg", "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode()

# 发送请求
response = client.chat.completions.create(
    model="qwen-vl-max",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "描述这张图片中的内容"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                }
            ]
        }
    ]
)

print(response.choices[0].message.content)
```

### 配置说明

服务配置已硬编码在 `process_pdf_fully.py` 中：

```python
# vLLM 服务配置
base_url = "http://localhost:8000/v1"
model_name = "qwen-vl-max"
```

如需修改端口或模型名称，请同步更新 `qwen-vl-vllm.sh` 和 `process_pdf_fully.py` 文件。

---

**提示**: 确保服务完全启动后再调用 API（约需 30-60 秒加载模型）。

