# codex_qwen_gateway.py
import json
import re
import time
import uuid
from collections.abc import Mapping
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# =========================================================
# CONFIG
# =========================================================

VLLM_BASE_URL = "http://112.111.7.91:7980/v1"
MODEL_NAME = "Qwen/Qwen3.5-397B-A17B-FP8"
app = FastAPI()

# =========================================================
# REGEX
# =========================================================

THINK_RE = re.compile(r"<think>.*?</think>", re.S)
TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=(?P<name>[^>]+)>\s*(?P<body>.*?)</function>\s*</tool_call>",
    re.S,
)
PARAM_RE = re.compile(r"<parameter=(?P<name>[^>]+)>\s*(?P<value>.*?)</parameter>", re.S)

# =========================================================
# MEMORY
# =========================================================

RESPONSES: dict[str, dict[str, Any]] = {}

# =========================================================
# HELPERS
# =========================================================

def extract_text_content(content: Any) -> str:
    """
    将 OpenAI / Responses / MCP 风格 content 统一提取为纯文本。
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
                continue
            if not isinstance(c, Mapping):
                continue
            t = c.get("type")
            if t in ("input_text", "output_text", "text"):
                parts.append(c.get("text", ""))
        return "\n".join(parts)

    return str(content)


def strip_think(text: str) -> str:
    return THINK_RE.sub("", text).strip()


def get_emit_text(text: str) -> str:
    """
    流式安全文本提取器：屏蔽 <think> 和 <tool_call> 标签及其残缺部分。
    """
    text = THINK_RE.sub("", text)

    # 屏蔽未闭合的 <think>
    think_idx = text.rfind("<think>")
    if think_idx != -1 and "</think>" not in text[think_idx:]:
        text = text[:think_idx]

    # 屏蔽开始的 <tool_call> 及后续全部内容
    tool_idx = text.find("<tool_call")
    if tool_idx != -1:
        text = text[:tool_idx]

    # 屏蔽可能出现在末尾的截断标签
    partials = [
        "<tool_call", "<tool_cal", "<tool_ca", "<tool_c", "<tool_", "<tool",
        "<thin", "<thi", "<th", "<t", "<",
    ]
    for p in partials:
        if text.endswith(p):
            text = text[:-len(p)]
            break

    return text


def flatten_tools(tools):
    """
    将 namespace 工具扁平化为普通列表。
    """
    if not tools:
        return []

    if isinstance(tools, Mapping):
        return [tools]

    out = []
    for tool in tools:
        if isinstance(tool, Mapping) and tool.get("type") == "namespace":
            inner = tool.get("tools", [])
            if isinstance(inner, list):
                out.extend(inner)
        else:
            out.append(tool)
    return out


def parse_parameter_value(raw: str):
    """
    尽量把 XML parameter 内容还原成正确类型：
    - JSON object / array / number / bool / string
    - 失败则保留原始字符串
    """
    raw = raw.strip()
    if raw == "":
        return ""

    try:
        return json.loads(raw)
    except Exception:
        return raw


def parse_xml_tool_calls(text: str):
    """
    从文本中解析出一个或多个 XML tool_call。
    """
    calls = []
    for m in TOOL_CALL_RE.finditer(text):
        fn_name = m.group("name").strip()
        body = m.group("body")

        args = {}
        for p in PARAM_RE.finditer(body):
            key = p.group("name").strip()
            val = parse_parameter_value(p.group("value"))
            args[key] = val

        calls.append({
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
                "name": fn_name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        })

    return calls


def parse_xml_tool_call(text: str):
    """
    兼容旧接口：只返回第一个 tool_call。
    """
    calls = parse_xml_tool_calls(text)
    return calls[0] if calls else None


def build_xml_tool_call(name: str, arguments: dict[str, Any]):
    out = ["<tool_call>", f"<function={name}>"]
    for k, v in arguments.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        elif v is None:
            v = ""
        out.extend([f"<parameter={k}>", str(v), "</parameter>"])
    out.extend(["</function>", "</tool_call>"])
    return "\n".join(out)


def normalize_tool_arguments(arguments: Any) -> dict[str, Any]:
    """
    将 OpenAI tool_call.arguments 规范化成 dict。
    """
    if isinstance(arguments, Mapping):
        return dict(arguments)

    if isinstance(arguments, str):
        raw = arguments.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, Mapping):
                return dict(parsed)
            return {"arguments": parsed}
        except Exception:
            return {"arguments": raw}

    return {}


# =========================================================
# TOOL PROMPT
# =========================================================

def build_tool_system_prompt(tools):
    tools = flatten_tools(tools)
    if not tools:
        return ""

    out = [
        "# Tools",
        "",
        "You have access to the following functions:",
        "",
        "<tools>",
    ]

    for tool in tools:
        out.append(json.dumps(tool, ensure_ascii=False))

    out.extend([
        "</tools>",
        "",
        "When calling a tool, output one or more XML blocks in exactly this format and nothing after the final </tool_call>:",
        "",
        "<tool_call>",
        "<function=example_function_name>",
        "<parameter=example_parameter_1>",
        "value_1",
        "</parameter>",
        "<parameter=example_parameter_2>",
        "This is the value for the second parameter",
        "that can span",
        "multiple lines",
        "</parameter>",
        "</function>",
        "</tool_call>",
        "",
        "CRITICAL RULES FOR ASSISTANT:",
        "1. If the user request involves the workspace, files, directories, terminal output, code editing, or build/run actions, you should prefer tools first.",
        "2. Do not guess local file contents or command outputs. Use the available tools.",
        "3. Copy the exact tool name from the JSON above. If the tool name has a prefix, you must include the full prefix.",
        "4. Put any reasoning or natural language BEFORE the first <tool_call>, never after the last </tool_call>.",
        "5. For object or array parameter values, write valid JSON inside the parameter body.",
        "6. If no tool is needed, answer normally.",
        "",
        "CRITICAL FILE OPERATION RULES:",
        "- Never use shell commands to read or edit files when dedicated file tools exist.",
        "- Use the dedicated file tools for file reads, writes, and edits.",
        "- Do not hallucinate file contents.",
    ])

    return "\n".join(out)


# =========================================================
# MESSAGE CONVERTER
# =========================================================

def convert_openai_messages(messages, tools=None):
    tool_prompt = build_tool_system_prompt(tools)
    out = []
    tool_prompt_added = False

    for msg in messages:
        role = msg.get("role", "")
        content = extract_text_content(msg.get("content", ""))

        if role in ("system", "developer"):
            if tool_prompt and not tool_prompt_added:
                content = (content + "\n\n" + tool_prompt).strip() if content else tool_prompt
                tool_prompt_added = True
            out.append({"role": "system", "content": content})
            continue

        if role == "tool":
            out.append({
                "role": "user",
                "content": f"<tool_response>\n{content}\n</tool_response>"
            })
            continue

        if role == "assistant" and msg.get("tool_calls"):
            blocks = []
            if content.strip():
                blocks.append(content)

            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                args = normalize_tool_arguments(fn.get("arguments", {}))
                blocks.append(build_xml_tool_call(fn_name, args))

            out.append({"role": "assistant", "content": "\n\n".join(blocks)})
            continue

        out.append(msg)

    if not tool_prompt_added and tool_prompt:
        out.insert(0, {"role": "system", "content": tool_prompt})

    return out


def convert_responses_input(input_items, tools=None):
    tool_prompt = build_tool_system_prompt(tools)
    messages = []
    tool_prompt_added = False

    for item in input_items:
        item_type = item.get("type", "message")

        if item_type == "function_call_output":
            messages.append({
                "role": "tool",
                "content": extract_text_content(item.get("output", "")),
            })
            continue

        if item_type == "message":
            role = item.get("role", "user")
            content = item.get("content", [])
            text_content = extract_text_content(content)

            if role in ("system", "developer"):
                if tool_prompt and not tool_prompt_added:
                    text_content = (text_content + "\n\n" + tool_prompt).strip() if text_content else tool_prompt
                    tool_prompt_added = True
                messages.append({"role": "system", "content": text_content})
                continue

            messages.append({"role": role, "content": text_content})

    if not tool_prompt_added and tool_prompt:
        messages.insert(0, {"role": "system", "content": tool_prompt})

    return messages


# =========================================================
# VLLM STREAM
# =========================================================

async def vllm_stream(payload):
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{VLLM_BASE_URL}/chat/completions", json=payload) as r:
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    yield "[DONE]"
                    return
                try:
                    yield json.loads(data)
                except Exception:
                    continue


# =========================================================
# MODELS
# =========================================================

@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [{
            "id": MODEL_NAME,
            "object": "model",
            "owned_by": "qwen",
            "permission": [],
            "context_length": 262144,
        }],
    }


# =========================================================
# RESPONSES API
# =========================================================

@app.post("/v1/responses")
async def responses(req: Request):
    body = await req.json()
    stream = body.get("stream", False)
    model = body.get("model", MODEL_NAME)
    response_id = f"resp_{uuid.uuid4().hex[:8]}"
    tools = body.get("tools")

    messages = convert_responses_input(body.get("input", []), tools)

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": body.get("temperature", 0.2),
        "extra_body": {
            "enable_thinking": True,
        },
    }

    # =====================================
    # STREAM
    # =====================================
    if stream:
        async def stream_events():
            item_id = f"msg_{uuid.uuid4().hex[:8]}"

            def make_event(event_type, event_payload):
                payload_dict = {"type": event_type, **event_payload}
                return f"data: {json.dumps(payload_dict, ensure_ascii=False)}\n\n"

            yield make_event("response.created", {
                "response": {
                    "id": response_id,
                    "object": "response",
                    "created_at": int(time.time()),
                    "status": "in_progress",
                    "model": model,
                    "output": [],
                }
            })
            yield make_event("response.in_progress", {
                "response": {
                    "id": response_id,
                    "object": "response",
                    "status": "in_progress",
                    "model": model,
                }
            })

            accumulated = ""
            emitted_length = 0
            full_text = ""
            message_item_created = False
            content_part_created = False

            async for chunk in vllm_stream(payload):
                if chunk == "[DONE]":
                    tool_calls = parse_xml_tool_calls(accumulated)

                    output_items = []
                    output_index = 0

                    # 1) 文本项结算
                    if message_item_created:
                        text_item = {
                            "id": item_id,
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": full_text}],
                        }

                        if content_part_created:
                            yield make_event("response.output_text.done", {
                                "item_id": item_id,
                                "output_index": 0,
                                "content_index": 0,
                                "text": full_text,
                            })
                            yield make_event("response.content_part.done", {
                                "item_id": item_id,
                                "output_index": 0,
                                "content_index": 0,
                                "part": {"type": "output_text", "text": full_text},
                            })

                        yield make_event("response.output_item.done", {
                            "output_index": 0,
                            "item": text_item,
                        })

                        output_items.append(text_item)
                        output_index += 1

                    # 2) 工具调用项结算
                    for tc in tool_calls:
                        tool_item_id = f"fc_{uuid.uuid4().hex[:8]}"
                        tool_args = tc["function"]["arguments"]
                        tool_name = tc["function"]["name"]

                        yield make_event("response.output_item.added", {
                            "output_index": output_index,
                            "item": {
                                "id": tool_item_id,
                                "type": "function_call",
                                "status": "in_progress",
                                "call_id": tc["id"],
                                "name": tool_name,
                                "arguments": "",
                            }
                        })
                        yield make_event("response.function_call_arguments.delta", {
                            "item_id": tool_item_id,
                            "output_index": output_index,
                            "delta": tool_args,
                        })
                        yield make_event("response.function_call_arguments.done", {
                            "item_id": tool_item_id,
                            "output_index": output_index,
                            "arguments": tool_args,
                        })

                        func_item = {
                            "id": tool_item_id,
                            "type": "function_call",
                            "status": "completed",
                            "call_id": tc["id"],
                            "name": tool_name,
                            "arguments": tool_args,
                        }
                        yield make_event("response.output_item.done", {
                            "output_index": output_index,
                            "item": func_item,
                        })

                        output_items.append(func_item)
                        output_index += 1

                    # 3) 空输出兜底
                    if not output_items:
                        text_item = {
                            "id": item_id,
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": ""}],
                        }
                        yield make_event("response.output_item.added", {
                            "output_index": 0,
                            "item": {
                                "id": item_id,
                                "type": "message",
                                "role": "assistant",
                                "status": "in_progress",
                                "content": [],
                            }
                        })
                        yield make_event("response.output_item.done", {
                            "output_index": 0,
                            "item": text_item,
                        })
                        output_items.append(text_item)

                    final_resp = {
                        "id": response_id,
                        "object": "response",
                        "created_at": int(time.time()),
                        "status": "completed",
                        "model": model,
                        "output": output_items,
                    }
                    RESPONSES[response_id] = final_resp
                    yield make_event("response.completed", {"response": final_resp})
                    yield "data: [DONE]\n\n"
                    return

                if "__error__" in chunk:
                    yield make_event("response.failed", {"error": chunk.get("__error__")})
                    yield "data: [DONE]\n\n"
                    return

                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    accumulated += delta

                emit_text = get_emit_text(accumulated)
                new_text = emit_text[emitted_length:]

                if new_text:
                    if not message_item_created:
                        message_item_created = True
                        content_part_created = True
                        yield make_event("response.output_item.added", {
                            "output_index": 0,
                            "item": {
                                "id": item_id,
                                "type": "message",
                                "role": "assistant",
                                "status": "in_progress",
                                "content": [],
                            }
                        })
                        yield make_event("response.content_part.added", {
                            "item_id": item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "part": {"type": "output_text", "text": ""},
                        })

                    yield make_event("response.output_text.delta", {
                        "item_id": item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": new_text,
                    })
                    emitted_length = len(emit_text)
                    full_text += new_text

        return StreamingResponse(stream_events(), media_type="text/event-stream")

    # =====================================
    # NON-STREAMING (兜底)
    # =====================================
    async with httpx.AsyncClient(timeout=1800) as client:
        r = await client.post(f"{VLLM_BASE_URL}/chat/completions", json=payload)

    data = r.json()
    text = data["choices"][0]["message"].get("content", "")

    tool_calls = parse_xml_tool_calls(text)
    emit_text = get_emit_text(text)

    output_items = []

    if emit_text.strip() or not tool_calls:
        text_item = {
            "id": f"msg_{uuid.uuid4().hex[:8]}",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": strip_think(emit_text)}],
        }
        output_items.append(text_item)

    for tc in tool_calls:
        output_items.append({
            "id": f"fc_{uuid.uuid4().hex[:8]}",
            "type": "function_call",
            "status": "completed",
            "call_id": tc["id"],
            "name": tc["function"]["name"],
            "arguments": tc["function"]["arguments"],
        })

    response = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": output_items,
    }
    RESPONSES[response_id] = response
    return JSONResponse(response)


@app.get("/v1/responses/{response_id}")
async def get_response(response_id: str):
    if response_id in RESPONSES:
        return RESPONSES[response_id]
    return {
        "id": response_id,
        "object": "response",
        "status": "completed",
        "output": [],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    return JSONResponse({"error": "Please use /v1/responses API for streaming Agent."})