# codex_gateway.py
#
# 完整版 Codex CLI / OpenAI Responses API / ChatCompletions
# -> vLLM Qwen3.5 Gateway
#
# 支持:
# - Codex CLI
# - OpenAI SDK
# - /v1/chat/completions
# - /v1/responses
# - streaming
# - Qwen <think> 过滤
# - XML tool_call -> OpenAI tool_calls
# - tool result 回注
# - response polling
# - SSE
#
# 安装:
# pip install fastapi uvicorn httpx
#
# 启动:
# uvicorn codex_gateway:app --host 0.0.0.0 --port 8080
#
# 配置:
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

app = FastAPI()

# =========================================================
# CONFIG
# =========================================================

VLLM_BASE = "http://112.111.7.91:7980/v1"

MODEL_NAME = "Qwen/Qwen3.5-397B-A17B-FP8"

# =========================================================
# XML TOOL PARSER
# =========================================================

TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=(?P<name>[^>]+)>\s*(?P<body>.*?)</function>\s*</tool_call>",
    re.S,
)

PARAM_RE = re.compile(
    r"<parameter=(?P<name>[^>]+)>\s*(?P<value>.*?)</parameter>",
    re.S,
)

THINK_RE = re.compile(
    r"<think>.*?</think>",
    re.S,
)

# =========================================================
# MEMORY
# =========================================================

RESPONSES: dict[str, dict[str, Any]] = {}

# =========================================================
# HELPERS
# =========================================================

def strip_think(text: str) -> str:
    return THINK_RE.sub("", text).strip()


def parse_xml_tool_call(text: str):

    m = TOOL_CALL_RE.search(text)

    if not m:
        return None

    name = m.group("name").strip()
    body = m.group("body")

    args = {}

    for p in PARAM_RE.finditer(body):
        args[p.group("name").strip()] = p.group("value").strip()

    return {
        "id": f"call_{uuid.uuid4().hex[:8]}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }


def build_xml_tool_call(
    name: str,
    args: dict[str, Any],
):

    out = [
        "<tool_call>",
        f"<function={name}>",
    ]

    for k, v in args.items():

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

def tools_prompt(tools):

    if not tools:
        return ""

    out = [
        "When calling a tool output EXACTLY:",
        "",
        "<tool_call>",
        "<function=name>",
        "<parameter=arg>",
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
        out.append(f"Description: {fn.get('description', '')}")
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

def convert_messages(
    messages,
    tools=None,
):

    out = []

    system_prompt = tools_prompt(tools)

    inserted_system = False

    for msg in messages:

        role = msg["role"]

        # -----------------------------------------
        # SYSTEM
        # -----------------------------------------

        if role == "system":

            content = msg.get("content", "")

            if system_prompt:
                content += "\n\n" + system_prompt

            out.append({
                "role": "system",
                "content": content,
            })

            inserted_system = True
            continue

        # -----------------------------------------
        # TOOL RESULT
        # -----------------------------------------

        if role == "tool":

            content = msg.get("content", "")

            out.append({
                "role": "user",
                "content": (
                    "<tool_response>\n"
                    f"{content}\n"
                    "</tool_response>"
                )
            })

            continue

        # -----------------------------------------
        # TOOL CALLS
        # -----------------------------------------

        if role == "assistant" and msg.get("tool_calls"):

            xml_blocks = []

            for tc in msg["tool_calls"]:

                fn = tc["function"]

                args = json.loads(fn["arguments"])

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

    if not inserted_system and system_prompt:

        out.insert(0, {
            "role": "system",
            "content": system_prompt,
        })

    return out


# =========================================================
# VLLM STREAM
# =========================================================

async def vllm_stream(payload):

    async with httpx.AsyncClient(timeout=None) as client:

        async with client.stream(
            "POST",
            f"{VLLM_BASE}/chat/completions",
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
async def chat(req: Request):

    body = await req.json()

    stream = body.get("stream", False)

    payload = dict(body)

    payload["messages"] = convert_messages(
        body.get("messages", []),
        body.get("tools"),
    )

    # =====================================================
    # NON STREAM
    # =====================================================

    if not stream:

        async with httpx.AsyncClient(timeout=1800) as client:

            r = await client.post(
                f"{VLLM_BASE}/chat/completions",
                json=payload,
            )

        data = r.json()

        try:

            msg = data["choices"][0]["message"]

            content = msg.get("content", "") or ""

            content = strip_think(content)

            tc = parse_xml_tool_call(content)

            if tc:

                msg["tool_calls"] = [tc]
                msg["content"] = None

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

        async for chunk in vllm_stream(payload):

            if chunk == "[DONE]":

                yield "data: [DONE]\n\n"
                return

            try:

                delta = (
                    chunk["choices"][0]
                    .get("delta", {})
                    .get("content", "")
                )

                if delta:
                    accumulated += delta

                clean = strip_think(accumulated)

                tc = parse_xml_tool_call(clean)

                # TOOL CALL

                if tc:

                    out = {
                        "id": chunk.get("id"),
                        "object": "chat.completion.chunk",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "tool_calls": [tc]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                    }

                    yield f"data: {json.dumps(out)}\n\n"
                    yield "data: [DONE]\n\n"

                    return

                # NORMAL TEXT

                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            except Exception:
                continue

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

    model = body.get("model", MODEL_NAME)

    stream = body.get("stream", False)

    response_id = f"resp_{uuid.uuid4().hex[:8]}"

    input_items = body.get("input", [])

    tools = body.get("tools")

    messages = []

    for item in input_items:

        role = item.get("role", "user")

        texts = []

        for c in item.get("content", []):

            if c.get("type") in (
                "input_text",
                "output_text",
                "text",
            ):
                texts.append(c.get("text", ""))

        messages.append({
            "role": role,
            "content": "\n".join(texts),
        })

    payload = {
        "model": model,
        "messages": convert_messages(
            messages,
            tools,
        ),
        "stream": True,
        "temperature": body.get("temperature", 0.2),
    }

    # =====================================================
    # NON STREAM
    # =====================================================

    if not stream:

        async with httpx.AsyncClient(timeout=1800) as client:

            r = await client.post(
                f"{VLLM_BASE}/chat/completions",
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
                    "id": f"msg_{uuid.uuid4().hex[:8]}",
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

        full_text = ""

        # -----------------------------------------
        # created
        # -----------------------------------------

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
                }
            })
            + "\n\n"
        )

        # -----------------------------------------
        # in_progress
        # -----------------------------------------

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

        # -----------------------------------------
        # output item added
        # -----------------------------------------

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

        accumulated = ""

        async for chunk in vllm_stream(payload):

            if chunk == "[DONE]":

                # output text done

                yield (
                    "data: "
                    + json.dumps({
                        "type": "response.output_text.done",
                        "item_id": item_id,
                        "output_index": 0,
                        "content_index": 0,
                    })
                    + "\n\n"
                )

                # item done

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
                        }
                    })
                    + "\n\n"
                )

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

                # completed

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

            try:

                delta = (
                    chunk["choices"][0]
                    .get("delta", {})
                    .get("content", "")
                )

                if not delta:
                    continue

                accumulated += delta

                clean = strip_think(accumulated)

                tc = parse_xml_tool_call(clean)

                # =====================================
                # TOOL CALL
                # =====================================

                if tc:

                    ev = {
                        "type": "response.output_item.added",
                        "output_index": 0,
                        "item": {
                            "id": tc["id"],
                            "type": "function_call",
                            "status": "completed",
                            "call_id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        }
                    }

                    yield (
                        "data: "
                        + json.dumps(ev, ensure_ascii=False)
                        + "\n\n"
                    )

                    continue

                # =====================================
                # TEXT DELTA
                # =====================================

                delta = strip_think(delta)

                if not delta:
                    continue

                full_text += delta

                ev = {
                    "type": "response.output_text.delta",
                    "item_id": item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "delta": delta,
                }

                yield (
                    "data: "
                    + json.dumps(ev, ensure_ascii=False)
                    + "\n\n"
                )

            except Exception as e:
                print(e)

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
    )


# =========================================================
# RESPONSE POLLING
# =========================================================

@app.get("/v1/responses/{response_id}")
async def get_response(response_id: str):

    response = RESPONSES.get(response_id)

    if response:
        return response

    return {
        "id": response_id,
        "object": "response",
        "status": "completed",
        "output": [],
    }