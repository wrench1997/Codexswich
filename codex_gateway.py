# codex_qwen_gateway.py
#
# 纯中转协议层：
#
# Codex CLI / OpenAI SDK
#            ⇅
# OpenAI Responses API
# OpenAI Chat Completions
#            ⇅
# Qwen3.5 XML Tool Calling
#            ⇅
# vLLM
#
# 特点：
# - 不执行工具
# - 只做协议转换
# - 完整兼容 Codex CLI
# - 支持 Responses API
# - 支持 streaming
# - 支持 OpenAI tool_calls
# - 支持 Qwen XML tool_call
# - 自动过滤 <think>
#
# 安装:
# pip install fastapi uvicorn httpx
#
# 启动:
# uvicorn codex_qwen_gateway:app --host 0.0.0.0 --port 8080
#
# 使用:
# export OPENAI_BASE_URL=http://127.0.0.1:8080/v1
# export OPENAI_API_KEY=dummy

import json
import re
import time
import uuid
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

THINK_RE = re.compile(
    r"<think>.*?</think>",
    re.S,
)

TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=(?P<name>[^>]+)>\s*(?P<body>.*?)</function>\s*</tool_call>",
    re.S,
)

PARAM_RE = re.compile(
    r"<parameter=(?P<name>[^>]+)>\s*(?P<value>.*?)</parameter>",
    re.S,
)

# =========================================================
# MEMORY
# =========================================================

RESPONSES: dict[str, dict[str, Any]] = {}

# =========================================================
# HELPERS
# =========================================================

def sse(data):
    return (
        "event: message\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


def strip_think(text: str) -> str:
    return THINK_RE.sub("", text).strip()


def flatten_tools(tools):

    if not tools:
        return []

    out = []

    for tool in tools:

        if tool.get("type") == "namespace":

            out.extend(
                tool.get("tools", [])
            )

        else:
            out.append(tool)

    return out


def parse_xml_tool_call(text: str):

    # ▼ 将原来的 fullmatch 替换为 search，以允许前面带有普通文本
    m = TOOL_CALL_RE.search(text)

    if not m:
        return None

    fn_name = m.group("name").strip()

    body = m.group("body")

    args = {}

    for p in PARAM_RE.finditer(body):

        args[p.group("name").strip()] = (
            p.group("value").strip()
        )

    return {
        "id": f"call_{uuid.uuid4().hex[:8]}",
        "type": "function",
        "function": {
            "name": fn_name,
            "arguments": json.dumps(
                args,
                ensure_ascii=False,
            ),
        },
    }


def build_xml_tool_call(
    name: str,
    arguments: dict[str, Any],
):

    out = [
        "<tool_call>",
        f"<function={name}>",
    ]

    for k, v in arguments.items():

        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)

        out.extend([
            f"<parameter={k}>",
            str(v),
            "</parameter>",
        ])

    out.extend([
        "</function>",
        "</tool_call>",
    ])

    return "\n".join(out)


# =========================================================
# TOOL PROMPT
# =========================================================

def build_tool_system_prompt(tools):

    tools = flatten_tools(tools)

    if not tools:
        return ""

    out = [
        "When calling a tool, output EXACTLY:",
        "",
        "<tool_call>",
        "<function=tool_name>",
        "<parameter=name>",
        "value",
        "</parameter>",
        "</function>",
        "</tool_call>",
        "",
        "No extra text after </tool_call>",
        "",
        "# Tools",
    ]

    for tool in tools:

        fn = tool.get("function", {})

        out.append("")
        out.append(f"Tool: {fn.get('name')}")
        out.append(
            f"Description: {fn.get('description', '')}"
        )
        out.append("Parameters:")

        out.append(
            json.dumps(
                fn.get("parameters", {}),
                ensure_ascii=False,
                indent=2,
            )
        )

    return "\n".join(out)


# =========================================================
# MESSAGE CONVERTER
# =========================================================

def convert_openai_messages(
    messages,
    tools=None,
):

    tools = flatten_tools(tools)

    out = []

    tool_prompt = build_tool_system_prompt(tools)

    inserted_system = False

    for msg in messages:

        role = msg.get("role", "")

        # -------------------------------------------------
        # SYSTEM
        # -------------------------------------------------

        if role == "system":

            content = msg.get("content", "")

            if tool_prompt:
                content += "\n\n" + tool_prompt

            out.append({
                "role": "system",
                "content": content,
            })

            inserted_system = True

            continue

        # -------------------------------------------------
        # TOOL RESPONSE (OpenAI Chat Completions format)
        # -------------------------------------------------

        if role == "tool":

            content = msg.get("content", "")

            out.append({
                "role": "user",
                "content": (
                    "<tool_response>\n"
                    f"{content}\n"
                    "</tool_response>"
                ),
            })

            continue

        # -------------------------------------------------
        # ASSISTANT TOOL CALLS
        # -------------------------------------------------

        if role == "assistant" and msg.get("tool_calls"):

            xml_blocks = []

            for tc in msg["tool_calls"]:

                fn = tc["function"]

                args = json.loads(
                    fn["arguments"]
                )

                xml_blocks.append(
                    build_xml_tool_call(
                        fn["name"],
                        args,
                    )
                )

            out.append({
                "role": "assistant",
                "content": "\n".join(xml_blocks),
            })

            continue

        out.append(msg)

    if not inserted_system and tool_prompt:

        out.insert(0, {
            "role": "system",
            "content": tool_prompt,
        })

    return out


def convert_responses_input(
    input_items,
    tools=None,
):
    """
    Convert Responses API input items to Chat Completions messages.
    
    Supports:
    - type: message (role: user/assistant/system)
    - type: function_call_output (tool results)
    """

    tools = flatten_tools(tools)

    messages = []

    tool_prompt = build_tool_system_prompt(tools)

    inserted_system = False

    for item in input_items:

        item_type = item.get("type", "message")

        # -------------------------------------------------
        # FUNCTION CALL OUTPUT (tool results)
        # -------------------------------------------------

        if item_type == "function_call_output":

            output = item.get("output", "")
            call_id = item.get("call_id", "")

            # Convert to Chat Completions tool message format
            messages.append({
                "role": "tool",
                "content": output,
                "tool_call_id": call_id,
            })

            continue

        # -------------------------------------------------
        # MESSAGE (user/assistant/system)
        # -------------------------------------------------

        if item_type == "message":

            role = item.get("role", "user")

            # Extract text from content array
            texts = []

            content = item.get("content", [])

            if isinstance(content, str):
                texts = [content]
            elif isinstance(content, list):
                for c in content:
                    if c.get("type") in ("input_text", "output_text", "text"):
                        texts.append(c.get("text", ""))

            text_content = "\n".join(texts)

            # -------------------------------------------------
            # SYSTEM
            # -------------------------------------------------

            if role == "system":

                if tool_prompt:
                    text_content += "\n\n" + tool_prompt

                messages.append({
                    "role": "system",
                    "content": text_content,
                })

                inserted_system = True

                continue

            # -------------------------------------------------
            # USER / ASSISTANT
            # -------------------------------------------------

            messages.append({
                "role": role,
                "content": text_content,
            })

            continue

    # Add tool prompt as system if not already present
    if not inserted_system and tool_prompt:

        messages.insert(0, {
            "role": "system",
            "content": tool_prompt,
        })

    return messages


# =========================================================
# VLLM STREAM
# =========================================================

async def vllm_stream(payload):

    async with httpx.AsyncClient(timeout=None) as client:

        async with client.stream(
            "POST",
            f"{VLLM_BASE_URL}/chat/completions",
            json=payload,
        ) as r:

            async for line in r.aiter_lines():

                if not line:
                    continue

                if not line.startswith("data:"):
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
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "owned_by": "qwen",
                "permission": [],
                "context_length": 262144,
            }
        ],
    }


# =========================================================
# CHAT COMPLETIONS
# =========================================================

@app.post("/v1/chat/completions")
async def chat_completions(req: Request):

    body = await req.json()

    stream = body.get("stream", False)

    payload = dict(body)

    payload["messages"] = convert_openai_messages(
        body.get("messages", []),
        body.get("tools"),
    )

    # =====================================================
    # NON STREAM
    # =====================================================

    if not stream:

        async with httpx.AsyncClient(timeout=1800) as client:

            r = await client.post(
                f"{VLLM_BASE_URL}/chat/completions",
                json=payload,
            )

        data = r.json()

        try:

            msg = data["choices"][0]["message"]

            content = msg.get("content", "") or ""

            content = strip_think(content)

            tc = parse_xml_tool_call(content)

            if tc:

                msg["content"] = None
                msg["tool_calls"] = [tc]

                data["choices"][0]["finish_reason"] = (
                    "tool_calls"
                )

            else:
                msg["content"] = content

        except Exception:
            pass

        return JSONResponse(data)

    # =====================================================
    # STREAM
    # =====================================================

    async def event_stream():

        accumulated = ""
        tool_call_detected = False
        tool_call_data = None

        async for chunk in vllm_stream(payload):

            if chunk == "[DONE]":

                # If tool call was detected, send it now at the end
                if tool_call_detected and tool_call_data:

                    tc = tool_call_data

                    out = {
                        "id": chunk.get(
                            "id",
                            "chatcmpl-tool",
                        ),
                        "object": "chat.completion.chunk",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": tc["id"],
                                            "type": "function",
                                            "function": {
                                                "name": tc["function"]["name"],
                                                "arguments": tc["function"]["arguments"],
                                            },
                                        }
                                    ]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                    }

                    yield (
                        "data: "
                        + json.dumps(
                            out,
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )

                yield "data: [DONE]\n\n"
                return

            try:

                choice = chunk.get("choices", [{}])[0]
                finish_reason = choice.get("finish_reason")

                delta = (
                    choice
                    .get("delta", {})
                    .get("content", "")
                )

                if delta:
                    accumulated += delta

                clean = strip_think(accumulated)

                tc = parse_xml_tool_call(clean)

                # =====================================
                # TOOL CALL DETECTED
                # =====================================

                if tc and not tool_call_detected:

                    tool_call_detected = True
                    tool_call_data = tc

                    # Continue to accumulate, don't send yet
                    # Wait for stream to finish to ensure complete args

                # =====================================
                # NORMAL TEXT (only if no tool call)
                # =====================================

                if not tool_call_detected and delta:

                    out = {
                        "id": chunk.get(
                            "id",
                            "chatcmpl",
                        ),
                        "object": "chat.completion.chunk",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "content": delta
                                },
                                "finish_reason": None,
                            }
                        ],
                    }

                    yield (
                        "data: "
                        + json.dumps(
                            out,
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )

            except Exception as e:
                print(e)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


# =========================================================
# RESPONSES API
# =========================================================

@app.post("/v1/responses")
async def responses(req: Request):

    body = await req.json()

    stream = body.get("stream", False)

    model = body.get(
        "model",
        MODEL_NAME,
    )

    response_id = (
        f"resp_{uuid.uuid4().hex[:8]}"
    )

    tools = body.get("tools")

    input_items = body.get("input", [])

    # Use the new converter that supports function_call_output
    messages = convert_responses_input(
        input_items,
        tools,
    )

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": body.get(
            "temperature",
            0.2,
        ),
    }

    # =====================================================
    # NON STREAM
    # =====================================================

    if not stream:

        async with httpx.AsyncClient(timeout=1800) as client:

            r = await client.post(
                f"{VLLM_BASE_URL}/chat/completions",
                json=payload,
            )

        data = r.json()

        text = (
            data["choices"][0]
            ["message"]
            .get("content", "")
        )

        text = strip_think(text)

        response = {
            "id": response_id,
            "object": "response",
            "created_at": int(time.time()),
            "status": "completed",
            "model": model,
            "output": [
                {
                    "id": (
                        f"msg_{uuid.uuid4().hex[:8]}"
                    ),
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": text,
                        }
                    ],
                }
            ],
        }

        RESPONSES[response_id] = response

        return response

    # =====================================================
    # STREAM
    # =====================================================

    async def stream_events():

        item_id = f"msg_{uuid.uuid4().hex[:8]}"
        tool_item_id = None

        full_text = ""

        tool_call_detected = False
        tool_call_sent = False
        tool_args = ""

        message_item_created = False
        content_part_created = False

        # =====================================================
        # response.created
        # =====================================================

        yield (
            "data: "
            + json.dumps({
                "type": "response.created",
                "response": {
                    "id": response_id,
                    "object": "response",
                    "created_at": int(time.time()),
                    "status": "in_progress",
                    "model": model,
                    "output": [],
                }
            })
            + "\n\n"
        )

        # =====================================================
        # response.in_progress
        # =====================================================

        yield (
            "data: "
            + json.dumps({
                "type": "response.in_progress",
                "response": {
                    "id": response_id,
                    "object": "response",
                    "status": "in_progress",
                    "model": model,
                }
            })
            + "\n\n"
        )

        accumulated = ""
        finish_reason = None

        async for chunk in vllm_stream(payload):

            # -------------------------------------------------
            # upstream done
            # -------------------------------------------------

            if chunk == "[DONE]":

                # Get finish_reason from last chunk if available
                if finish_reason is None:
                    finish_reason = "stop"

                # =================================================
                # HANDLE TOOL CALL COMPLETION
                # =================================================

                if tool_call_detected and not tool_call_sent:

                    # Send the function_call item now
                    tool_item_id = f"fc_{uuid.uuid4().hex[:8]}"

                    # function_call item added
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.output_item.added",
                            "output_index": 0,
                            "item": {
                                "id": tool_item_id,
                                "type": "function_call",
                                "status": "in_progress",
                                "call_id": f"call_{uuid.uuid4().hex[:8]}",
                                "name": "tool",
                                "arguments": "",
                            }
                        }, ensure_ascii=False)
                        + "\n\n"
                    )

                    # arguments delta
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.function_call_arguments.delta",
                            "item_id": tool_item_id,
                            "output_index": 0,
                            "delta": tool_args,
                        }, ensure_ascii=False)
                        + "\n\n"
                    )

                    # arguments done
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.function_call_arguments.done",
                            "item_id": tool_item_id,
                            "output_index": 0,
                            "arguments": tool_args,
                        }, ensure_ascii=False)
                        + "\n\n"
                    )

                    # output_item.done for function_call
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.output_item.done",
                            "output_index": 0,
                            "item": {
                                "id": tool_item_id,
                                "type": "function_call",
                                "status": "completed",
                                "call_id": f"call_{uuid.uuid4().hex[:8]}",
                                "name": "tool",
                                "arguments": tool_args,
                            }
                        }, ensure_ascii=False)
                        + "\n\n"
                    )

                    tool_call_sent = True

                    # completed response
                    final_response = {
                        "id": response_id,
                        "object": "response",
                        "created_at": int(time.time()),
                        "status": "completed",
                        "model": model,
                        "output": [
                            {
                                "id": tool_item_id,
                                "type": "function_call",
                                "status": "completed",
                                "call_id": f"call_{uuid.uuid4().hex[:8]}",
                                "name": "tool",
                                "arguments": tool_args,
                            }
                        ],
                    }

                    RESPONSES[response_id] = final_response

                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.completed",
                            "response": final_response,
                        }, ensure_ascii=False)
                        + "\n\n"
                    )

                    yield "data: [DONE]\n\n"

                    return

                # =================================================
                # HANDLE TEXT MESSAGE COMPLETION
                # =================================================

                # Close content_part if it was opened
                if content_part_created:

                    # output_text.done
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.output_text.done",
                            "item_id": item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "text": full_text,
                        })
                        + "\n\n"
                    )

                    # content_part.done
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.content_part.done",
                            "item_id": item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "part": {
                                "type": "output_text",
                                "text": full_text,
                            }
                        })
                        + "\n\n"
                    )

                # Close message item if it was opened
                if message_item_created:

                    # output_item.done for message
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.output_item.done",
                            "output_index": 0,
                            "item": {
                                "id": item_id,
                                "type": "message",
                                "role": "assistant",
                                "status": "completed",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": full_text,
                                    }
                                ],
                            }
                        })
                        + "\n\n"
                    )

                # completed response
                final_response = {
                    "id": response_id,
                    "object": "response",
                    "created_at": int(time.time()),
                    "status": "completed",
                    "model": model,
                    "output": [
                        {
                            "id": item_id,
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": full_text,
                                }
                            ],
                        }
                    ],
                }

                RESPONSES[response_id] = final_response

                yield (
                    "data: "
                    + json.dumps({
                        "type": "response.completed",
                        "response": final_response,
                    }, ensure_ascii=False)
                    + "\n\n"
                )

                yield "data: [DONE]\n\n"

                return

            # -------------------------------------------------
            # upstream error
            # -------------------------------------------------

            if "__error__" in chunk:

                yield (
                    "data: "
                    + json.dumps({
                        "type": "response.failed",
                        "error": chunk.get("__error__"),
                    })
                    + "\n\n"
                )

                yield "data: [DONE]\n\n"

                return

            try:

                choice = chunk.get("choices", [{}])[0]
                finish_reason = choice.get("finish_reason")

                delta = (
                    choice
                    .get("delta", {})
                    .get("content", "")
                )

                if delta:
                    accumulated += delta

                clean = strip_think(accumulated)

                tc = parse_xml_tool_call(clean)

                # =================================================
                # TOOL CALL DETECTED
                # =================================================

                if tc and not tool_call_detected:

                    tool_call_detected = True
                    tool_args = tc["function"]["arguments"]

                    # Continue accumulating to ensure we have complete args
                    # Don't send yet, wait for stream to finish

                # =================================================
                # NORMAL TEXT DELTA
                # =================================================

                # Skip if we're in tool_call mode
                if tool_call_detected:
                    continue

                if not delta:
                    continue

                # Strip think tags from delta
                clean_delta = strip_think(delta)

                if not clean_delta:
                    continue

                # Skip XML tags themselves
                if "<tool_call>" in accumulated or "</tool_call>" in accumulated:
                    continue

                full_text += clean_delta

                # Create message item lazily (only when we have actual text)
                if not message_item_created:

                    message_item_created = True

                    # output_item.added for message
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.output_item.added",
                            "output_index": 0,
                            "item": {
                                "id": item_id,
                                "type": "message",
                                "role": "assistant",
                                "status": "in_progress",
                                "content": [],
                            }
                        })
                        + "\n\n"
                    )

                    # content_part.added
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "response.content_part.added",
                            "item_id": item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "part": {
                                "type": "output_text",
                                "text": "",
                            }
                        })
                        + "\n\n"
                    )

                    content_part_created = True

                # output_text.delta
                yield (
                    "data: "
                    + json.dumps({
                        "type": "response.output_text.delta",
                        "item_id": item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": clean_delta,
                    }, ensure_ascii=False)
                    + "\n\n"
                )

            except Exception as e:

                yield (
                    "data: "
                    + json.dumps({
                        "type": "response.failed",
                        "error": str(e),
                    })
                    + "\n\n"
                )

                yield "data: [DONE]\n\n"

                return

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
    )


# =========================================================
# RESPONSE POLLING
# =========================================================

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