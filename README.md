# Codex Gateway

基于 FastAPI 的 Qwen3.5 模型网关，提供 OpenAI 兼容的 Responses API，支持流式输出和工具调用（XML 格式）。

## 功能特性

- ✅ OpenAI Responses API 兼容
- ✅ 流式输出（SSE）
- ✅ 工具调用（XML 格式）
- ✅ 自动过滤  思考过程
- ✅ 支持 Qwen3.5-397B 大模型

## 环境要求

- Python 3.8+
- FastAPI
- Uvicorn
- httpx

## 安装依赖

```bash
pip install fastapi uvicorn[standard] httpx
```

## 启动服务

### 开发模式（自动重载）

```bash
uvicorn codex_gateway:app --host 0.0.0.0 --port 8080 --reload
```

### 生产模式（多 Worker）

```bash
uvicorn codex_gateway:app --host 0.0.0.0 --port 8080 --workers 4
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `codex_gateway:app` | 模块名:FastAPI 实例名 |
| `--host 0.0.0.0` | 监听所有网络接口 |
| `--port 8080` | 端口号（可自定义） |
| `--reload` | 开发模式，代码变更自动重启 |
| `--workers N` | 生产模式，启动 N 个 worker 进程 |

## API 端点

### 1. 获取模型列表

```bash
curl http://localhost:8080/v1/models
```

**响应示例：**
```json
{
  "object": "list",
  "data": [{
    "id": "Qwen/Qwen3.5-397B-A17B-FP8",
    "object": "model",
    "owned_by": "qwen",
    "context_length": 262144
  }]
}
```

### 2. Responses API（流式）

```bash
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": [
      {"type": "message", "role": "user", "content": "你好"}
    ],
    "stream": true
  }'
```

### 3. Responses API（非流式）

```bash
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": [
      {"type": "message", "role": "user", "content": "你好"}
    ],
    "stream": false
  }'
```

### 4. 获取响应状态

```bash
curl http://localhost:8080/v1/responses/{response_id}
```

## 工具调用格式

当需要使用工具时，模型会输出 XML 格式的工具调用：

```xml
<tool_call>
<function=tool_name>
<parameter=param1>
value1
</parameter>
<parameter=param2>
value2
</parameter>
</function>
</tool_call>
```

### 带工具调用的请求示例

```bash
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": [
      {"type": "message", "role": "user", "content": "帮我查询天气"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "parameters": {
            "type": "object",
            "properties": {
              "city": {"type": "string"}
            },
            "required": ["city"]
          }
        }
      }
    ],
    "stream": true
  }'
```

## 配置说明

在 `codex_gateway.py` 中修改以下配置：

```python
VLLM_BASE_URL = "http://112.111.7.91:7980/v1"  # vLLM 服务地址
MODEL_NAME = "Qwen/Qwen3.5-397B-A17B-FP8"      # 模型名称
```

## 注意事项

1. **流式输出**：推荐使用 `stream: true` 以获得更好的响应体验
2. **工具调用**：工具描述会自动添加到 system prompt 中
3. **思考过程**：模型输出的  标签会被自动过滤
4. **端口占用**：如果 8080 端口被占用，可更换为其他端口（如 `--port 8080`）

## 许可证

MIT License
