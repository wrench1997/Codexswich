import json
import os
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

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://112.111.7.91:7980/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3.5-397B-A17B-FP8")
app = FastAPI()

# =========================================================
# REGEX
# =========================================================

THINK_RE = re.compile(r"<think>.*?</think>", re.S)

# 修复：兼容 AI 画蛇添足加引号的情况，如 <function="name">
TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=[\"\']?(?P<name>[^>\"\']+)[\"\']?>\s*(?P<body>.*?)</function>\s*</tool_call>",
    re.S,
)
# 修复：兼容 <parameter="name">
PARAM_RE = re.compile(
    r"<parameter=[\"\']?(?P<name>[^>\"\']+)[\"\']?>\s*(?P<value>.*?)</parameter>", 
    re.S
)

# =========================================================
# MEMORY
# =========================================================

RESPONSES: dict[str, dict[str, Any]] = {}

STRICT_FILE_TOOL_MODE = True

FILE_TOOL_NAMES = {
    "list_directory_files",
    "read_file_content",
    "write_new_file",
    "modify_file_code",
    "search_replace_preview",
    "revert_file_backup",
}

TERMINAL_TOOL_NAMES = {
    "execute_shell_command",
    "run_in_terminal",
    "execute_bash",
    "shell",
    "bash",
    "powershell",
    "cmd",
}


def get_tool_name(tool: Any) -> str:
    if not isinstance(tool, Mapping):
        return ""

    fn = tool.get("function")
    if isinstance(fn, Mapping):
        return str(fn.get("name", "")).strip()

    return str(tool.get("name", "")).strip()


def is_file_tool_name(name: str) -> bool:
    lowered = (name or "").lower()
    return any(lowered.endswith(t) for t in FILE_TOOL_NAMES)

def is_terminal_tool_name(name: str) -> bool:
    lowered = (name or "").lower()
    return any(lowered.endswith(t) for t in TERMINAL_TOOL_NAMES)


def looks_like_file_task(text: str | None) -> bool:
    lowered = (text or "").lower()
    keywords = (
        "file", "files", "folder", "directory", "workspace",
        "read", "open", "show", "inspect", "list", "find", "search",
        "edit", "modify", "replace", "write", "create", "save", "update", "patch", "fix",
        "code", "source", "content",
    )
    return any(k in lowered for k in keywords)


def looks_like_terminal_task(text: str | None) -> bool:
    lowered = (text or "").lower()
    keywords = (
        "build", "run", "test", "compile", "execute",
        "terminal", "shell", "powershell", "cmd", "bash",
        "git", "npm", "pnpm", "yarn", "pip", "poetry", "cargo", "make", "cmake",
        "install", "launch", "start",
    )
    return any(k in lowered for k in keywords)


def get_last_real_user_text_from_messages(messages) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") != "user":
            continue
        text = extract_text_content(msg.get("content", ""))
        text = text.strip()
        if not text:
            continue
        if text.startswith("<tool_response>") and text.endswith("</tool_response>"):
            continue
        return text
    return ""


def get_last_real_user_text_from_input_items(input_items) -> str:
    for item in reversed(input_items or []):
        if item.get("type", "message") != "message":
            continue
        if item.get("role", "user") != "user":
            continue
        text = extract_text_content(item.get("content", []))
        text = text.strip()
        if not text:
            continue
        if text.startswith("<tool_response>") and text.endswith("</tool_response>"):
            continue
        return text
    return ""


def prioritize_tools(tools, user_text: str | None = None):
    """
    1) 文件工具优先
    2) 终端工具靠后
    3) 可选：明显文件任务时，仅暴露文件工具
    """
    flat = flatten_tools(tools)
    if not flat:
        return []

    if STRICT_FILE_TOOL_MODE and looks_like_file_task(user_text) and not looks_like_terminal_task(user_text):
        file_only = [t for t in flat if is_file_tool_name(get_tool_name(t))]
        if file_only:
            flat = file_only

    ranked = []
    for idx, tool in enumerate(flat):
        name = get_tool_name(tool)
        if is_file_tool_name(name):
            bucket = 0
        elif is_terminal_tool_name(name):
            bucket = 2
        else:
            bucket = 1
        ranked.append((bucket, idx, name.lower(), tool))

    ranked.sort(key=lambda x: (x[0], x[2], x[1]))
    return [t for _, _, _, t in ranked]

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

    think_idx = text.rfind("<think>")
    if think_idx != -1 and "</think>" not in text[think_idx:]:
        text = text[:think_idx]

    tool_idx = text.find("<tool_call")
    if tool_idx != -1:
        text = text[:tool_idx]

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


def parse_xml_tool_calls(text: str, available_tools=None):
    """
    从文本中解析出一个或多个 XML tool_call。
    加入强力容错：自动匹配 MCP 客户端带前缀的工具名（如 mymcp__read_file_content）。
    """
    calls = []
    
    # 提取当前客户端所有合法的工具名
    valid_tool_names = []
    if available_tools:
        valid_tool_names = [get_tool_name(t) for t in flatten_tools(available_tools)]
        
    for m in TOOL_CALL_RE.finditer(text):
        fn_name = m.group("name").strip()
        body = m.group("body").strip()

        # ==========================================
        # 核心修复：前缀自动修正机制
        # 如果 AI 输出了 'read_file_content'，但客户端要求 'mymcp__read_file_content'
        # 我们在这里自动把它纠正过来。
        # ==========================================
        if valid_tool_names and fn_name not in valid_tool_names:
            for real_name in valid_tool_names:
                # 匹配 mymcp__name 或 mymcp-name
                if real_name.endswith(f"__{fn_name}") or real_name.endswith(f"-{fn_name}"):
                    fn_name = real_name
                    break

        args = {}
        param_matches = list(PARAM_RE.finditer(body))
        
        if param_matches:
            # 正常情况：按 <parameter> 标签解析
            for p in param_matches:
                key = p.group("name").strip()
                val = parse_parameter_value(p.group("value"))
                args[key] = val
        else:
            # 兜底情况：AI 偷懒，直接在 function 里面输出了 JSON
            try:
                args = json.loads(body)
                if not isinstance(args, dict):
                    args = {}
            except Exception:
                pass
                
        print(f"========== [Gateway Debug] 解析到工具调用 ==========")
        print(f"Tool Name (修正后): {fn_name}")
        print(f"Arguments: {args}")
        print(f"====================================================")

        calls.append({
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
                "name": fn_name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        })

    return calls


def parse_xml_tool_call(text: str, available_tools=None):
    """
    兼容旧接口：只返回第一个 tool_call。
    """
    calls = parse_xml_tool_calls(text, available_tools)
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

def build_tool_system_prompt(tools, user_text: str | None = None):
    tools = prioritize_tools(tools, user_text=user_text)
    if not tools:
        return ""

    file_tools = [t for t in tools if is_file_tool_name(get_tool_name(t))]
    terminal_tools = [t for t in tools if is_terminal_tool_name(get_tool_name(t))]

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
    ])

    if file_tools:
        out.extend([
            "Preferred file tools (use these first for workspace/file tasks):",
        ])
        for t in file_tools:
            out.append(f"- {get_tool_name(t)}")
        out.append("")

    if terminal_tools:
        out.extend([
            "Fallback terminal tools (use only when file tools cannot solve the task):",
        ])
        for t in terminal_tools:
            out.append(f"- {get_tool_name(t)}")
        out.append("")

    out.extend([
        "TOOL PRIORITY:",
        "1. For reading file contents, use read_file_content first.",
        "2. For editing existing files, use modify_file_code first.",
        "3. For creating or overwriting files, use write_new_file.",
        "4. For inspecting directories, use list_directory_files.",
        "5. For safe pre-edit checking, use search_replace_preview.",
        "6. For rollback, use revert_file_backup.",
        "7. Use shell/terminal tools only if no dedicated file tool can do the job.",
        "",
        "HARD RULES:",
        "- Never use shell commands to read, write, or edit files when dedicated file tools exist.",
        "- Do not guess local file contents. Use read_file_content.",
        "- Do not use terminal commands for simple file replacements when modify_file_code exists.",
        "- For workspace/file tasks, file tools are preferred over command-line tools.",
        "- If a tool is needed, output only XML <tool_call> blocks and nothing else.",
        "- Include every required parameter.",
        "- Preserve user-provided string values verbatim when possible.",
        "- For object or array parameter values, write valid JSON inside the parameter body.",
        "- If no tool is needed, answer normally.",
        "",
        "FILE TOOL OPERATING RULES:",
        "- read_file_content is the primary file-reading tool.",
        "- modify_file_code is the primary file-editing tool.",
        "- write_new_file is for new files or complete overwrites.",
        "- search_replace_preview should be used before risky edits.",
    ])

    if user_text and looks_like_file_task(user_text) and not looks_like_terminal_task(user_text):
        out.extend([
            "",
            "TASK CLASSIFICATION:",
            "This request appears to be a file/workspace task. Prefer file tools before any terminal tool.",
        ])

    return "\n".join(out)

# =========================================================
# MESSAGE CONVERTER
# =========================================================

def convert_openai_messages(messages, tools=None):
    user_text = get_last_real_user_text_from_messages(messages)
    tool_prompt = build_tool_system_prompt(tools, user_text=user_text)

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
    user_text = get_last_real_user_text_from_input_items(input_items)
    tool_prompt = build_tool_system_prompt(tools, user_text=user_text)

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
# VLLM
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


async def vllm_complete(payload):
    async with httpx.AsyncClient(timeout=1800) as client:
        r = await client.post(f"{VLLM_BASE_URL}/chat/completions", json=payload)

    if r.status_code >= 400:
        return {
            "__error__": {
                "status_code": r.status_code,
                "text": r.text,
            }
        }

    try:
        return r.json()
    except Exception as e:
        return {
            "__error__": {
                "status_code": r.status_code,
                "text": f"Failed to parse JSON: {e}",
            }
        }

# =========================================================
# CHAT COMPLETION RESPONSE BUILDERS
# =========================================================

def build_chat_tool_calls(tool_calls):
    out = []
    for tc in tool_calls:
        out.append({
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["function"]["name"],
                "arguments": tc["function"]["arguments"],
            },
        })
    return out


def build_chat_completion_json(model: str, text: str, tool_calls):
    message = {
        "role": "assistant",
    }

    if tool_calls:
        message["content"] = None
        message["tool_calls"] = build_chat_tool_calls(tool_calls)
        finish_reason = "tool_calls"
    else:
        message["content"] = strip_think(text)
        finish_reason = "stop"

    return {
        "id": f"chatcmpl_{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish_reason,
        }],
    }


def make_chat_chunk(chunk_id: str, model: str, delta: dict[str, Any], finish_reason: str | None = None):
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }


async def chat_completion_stream(payload, model: str, tools=None):
    chunk_id = f"chatcmpl_{uuid.uuid4().hex[:8]}"
    accumulated = ""
    emitted_length = 0

    yield f"data: {json.dumps(make_chat_chunk(chunk_id, model, {'role': 'assistant'}), ensure_ascii=False)}\n\n"

    async for chunk in vllm_stream(payload):
        if chunk == "[DONE]":
            tool_calls = parse_xml_tool_calls(accumulated, available_tools=tools)

            if tool_calls:
                delta = {
                    "tool_calls": build_chat_tool_calls(tool_calls),
                }
                yield f"data: {json.dumps(make_chat_chunk(chunk_id, model, delta, finish_reason='tool_calls'), ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps(make_chat_chunk(chunk_id, model, {}, finish_reason='stop'), ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
            return

        if "__error__" in chunk:
            err = chunk["__error__"]
            error_payload = {
                "error": {
                    "message": str(err),
                    "type": "server_error",
                }
            }
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
        if delta:
            accumulated += delta

        emit_text = get_emit_text(accumulated)
        new_text = emit_text[emitted_length:]

        if new_text:
            emitted_length = len(emit_text)
            yield f"data: {json.dumps(make_chat_chunk(chunk_id, model, {'content': new_text}), ensure_ascii=False)}\n\n"

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
                    tool_calls = parse_xml_tool_calls(accumulated, available_tools=tools)
                    
                    output_items = []
                    output_index = 0

                    # 修复无限死循环：只要给客户端发了 message 开始事件，就必须发 done 闭合它！
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

                    # 工具调用项结算
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

                    # 空输出兜底
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

    # NON-STREAM
    data = await vllm_complete(payload)
    if "__error__" in data:
        return JSONResponse({
            "id": response_id,
            "object": "response",
            "created_at": int(time.time()),
            "status": "failed",
            "model": model,
            "error": data["__error__"],
            "output": [],
        })

    text = data["choices"][0]["message"].get("content", "")
    tool_calls = parse_xml_tool_calls(text, available_tools=tools)
    emit_text = get_emit_text(text)

    output_items = []

    # 关键修复：只要有 tool_call，就不要把文本也混进最终 output
    if not tool_calls:
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

# =========================================================
# CHAT COMPLETIONS API
# =========================================================

@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    stream = body.get("stream", False)
    model = body.get("model", MODEL_NAME)
    tools = body.get("tools")

    messages = convert_openai_messages(body.get("messages", []), tools)

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": body.get("temperature", 0.2),
        "extra_body": {
            "enable_thinking": True,
        },
    }

    if stream:
        return StreamingResponse(chat_completion_stream(payload, model, tools), media_type="text/event-stream")

    data = await vllm_complete(payload)
    if "__error__" in data:
        return JSONResponse({
            "error": data["__error__"],
        }, status_code=500)

    text = data["choices"][0]["message"].get("content", "")
    tool_calls = parse_xml_tool_calls(text, available_tools=tools)
    emit_text = get_emit_text(text)

    response = build_chat_completion_json(model, emit_text, tool_calls)
    return JSONResponse(response)