"""
tools.py - Tool Registry and Executor for Codex Gateway

This module provides a centralized tool registry and execution framework for
the Codex Gateway system. It enables AI assistants to interact with the local
filesystem and execute shell commands safely.
"""

import os
import platform
import re
import subprocess
from pathlib import Path

# =========================================================
# PLATFORM DETECTION
# =========================================================

SYSTEM_PLATFORM = platform.system()
IS_WINDOWS = os.name == "nt"
IS_LINUX = SYSTEM_PLATFORM == "Linux"
IS_MACOS = SYSTEM_PLATFORM == "Darwin"

if IS_WINDOWS:
    DEFAULT_SHELL = "powershell"
    SHELL_HELP = "Use Windows PowerShell commands (e.g., dir, findstr)"
else:
    DEFAULT_SHELL = "bash"
    SHELL_HELP = "Use Linux/Unix shell commands (e.g., ls, grep)"

# =========================================================
# CONFIG - Security Settings
# =========================================================

# WORKSPACE root used for resolving relative file paths.
# If env var WORKSPACE is not set, fall back to current working directory.
WORKSPACE = os.environ.get("WORKSPACE") or str(Path.cwd().resolve())
COMMAND_BLACKLIST = []
COMMAND_TIMEOUT = 30

# =========================================================
# TOOL REGISTRY
# =========================================================

TOOLS = {}
TOOL_ALIASES = {}


def tool(fn):
    TOOLS[fn.__name__] = fn
    return fn


def register_tool_alias(alias_name: str, target_fn):
    TOOLS[alias_name] = target_fn
    TOOL_ALIASES[alias_name] = target_fn


# =========================================================
# INTERNAL HELPERS
# =========================================================

def _workspace_path() -> Path:
    """
    Return the workspace root as an absolute Path.
    Falls back to current working directory if WORKSPACE is invalid.
    """
    try:
        p = Path(WORKSPACE).expanduser()
        if p.exists() and p.is_dir():
            return p.resolve()
    except Exception:
        pass
    return Path.cwd().resolve()


def _normalize_path(path: str) -> Path:
    """
    Resolve a path against WORKSPACE if it is relative.
    Absolute paths are preserved.
    """
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = _workspace_path() / p
    return p.resolve()


def _is_command_blacklisted(command: str) -> bool:
    if not COMMAND_BLACKLIST:
        return False
    cmd_lower = command.lower()
    for blocked in COMMAND_BLACKLIST:
        if blocked.lower() in cmd_lower:
            return True
    return False


def _subprocess_cwd():
    """
    Return a valid cwd for subprocess execution.
    """
    root = _workspace_path()
    return str(root) if root.exists() and root.is_dir() else None


def _run_subprocess(command, *, shell=False):
    try:
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            cwd=_subprocess_cwd(),
            timeout=COMMAND_TIMEOUT,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {COMMAND_TIMEOUT} seconds"}
    except Exception as e:
        return {"error": str(e)}


# =========================================================
# TOOL: run_shell
# =========================================================

@tool
def run_shell(command: str):
    """
    Run a shell command in the system's default shell.
    """
    if _is_command_blacklisted(command):
        return {"error": "Command is blocked by blacklist"}
    return _run_subprocess(command, shell=True)


# =========================================================
# TOOL: list_files
# =========================================================

@tool
def list_files(path: str = "."):
    """
    List all files and directories in the specified path.
    """
    try:
        p = _normalize_path(path)

        if not p.exists():
            return {"error": "path not exists"}

        if not p.is_dir():
            return {"error": "path is not a directory"}

        files = []
        for item in p.iterdir():
            files.append({
                "name": item.name,
                "is_dir": item.is_dir(),
            })

        files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

        return {
            "files": files,
            "path": str(p),
        }
    except Exception as e:
        return {"error": str(e)}


# =========================================================
# TOOL: read_file
# =========================================================

@tool
def read_file(path: str):
    """
    Read the entire contents of a file.
    """
    try:
        p = _normalize_path(path)

        if not p.exists():
            return {"error": "file not exists"}

        if not p.is_file():
            return {"error": "path is not a file"}

        content = p.read_text(encoding="utf-8", errors="ignore")
        return {
            "content": content,
            "path": str(p),
        }
    except Exception as e:
        return {"error": str(e)}


# =========================================================
# TOOL: write_file
# =========================================================

@tool
def write_file(path: str, content: str):
    """
    Write content to a file, creating parent directories if needed.
    """
    try:
        p = _normalize_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "path": str(p),
            "bytes_written": len(content.encode("utf-8")),
        }
    except Exception as e:
        return {"error": str(e)}


# =========================================================
# TOOL: run_in_terminal (Codex compatibility)
# =========================================================

@tool
def run_in_terminal(command: str):
    """
    Codex/OpenHands compatible terminal execution tool.
    """
    return run_shell(command)


# =========================================================
# TOOL: execute_bash (Codex/OpenHands compatibility)
# =========================================================

@tool
def execute_bash(command: str):
    """
    Codex/OpenHands compatible bash execution tool.
    """
    return run_shell(command)


# =========================================================
# TOOL: shell (alias for run_shell)
# =========================================================

@tool
def shell(command: str):
    """
    Alias for run_shell.
    """
    return run_shell(command)


# =========================================================
# TOOL: bash (alias for run_shell)
# =========================================================

@tool
def bash(command: str):
    """
    Alias for run_shell.
    """
    return run_shell(command)


# =========================================================
# TOOL: powershell
# =========================================================

@tool
def powershell(command: str):
    """
    Run a PowerShell command on Windows.
    """
    if not IS_WINDOWS:
        return {"error": "powershell is only available on Windows"}

    if _is_command_blacklisted(command):
        return {"error": "Command is blocked by blacklist"}

    return _run_subprocess(["powershell", "-Command", command], shell=False)


# =========================================================
# TOOL: cmd
# =========================================================

@tool
def cmd(command: str):
    """
    Run a command via Windows cmd.exe.
    """
    if not IS_WINDOWS:
        return {"error": "cmd is only available on Windows"}

    if _is_command_blacklisted(command):
        return {"error": "Command is blocked by blacklist"}

    return _run_subprocess(["cmd", "/c", command], shell=False)


# =========================================================
# TOOL: replace_in_file
# =========================================================

@tool
def replace_in_file(
    path: str,
    old_code: str = "",
    new_code: str = "",
    use_regex: bool = False,
    replace_all: bool = False,
    start_line: int = None,
    end_line: int = None,
    create_backup: bool = True,
):
    """
    Enhanced code replacement tool with multiple strategies.
    """
    try:
        p = _normalize_path(path)

        if not p.exists():
            return {"error": "file not exists"}

        if not p.is_file():
            return {"error": "path is not a file"}

        content = p.read_text(encoding="utf-8", errors="ignore")
        replacements_made = 0
        method = "string"

        backup_path = None
        if create_backup:
            backup_file = p.with_suffix(p.suffix + ".bak")
            backup_file.write_text(content, encoding="utf-8")
            backup_path = str(backup_file)

        if start_line is not None or end_line is not None:
            method = "line_range"
            lines = content.splitlines(keepends=True)

            start_idx = (start_line - 1) if start_line is not None else 0
            end_idx = end_line if end_line is not None else len(lines)

            start_idx = max(0, min(start_idx, len(lines)))
            end_idx = max(start_idx, min(end_idx, len(lines)))

            replacement_lines = [new_code]
            lines[start_idx:end_idx] = replacement_lines
            new_content = "".join(lines)
            replacements_made = end_idx - start_idx

        elif use_regex:
            method = "regex"
            if replace_all:
                new_content, count = re.subn(old_code, new_code, content)
            else:
                new_content, count = re.subn(old_code, new_code, content, count=1)

            replacements_made = count
            if replacements_made == 0:
                if create_backup and backup_path:
                    try:
                        Path(backup_path).unlink()
                    except Exception:
                        pass
                return {"success": False, "error": "Pattern not found in file"}

        else:
            method = "string"
            if old_code not in content:
                if create_backup and backup_path:
                    try:
                        Path(backup_path).unlink()
                    except Exception:
                        pass
                return {"success": False, "error": "old_code not found in file"}

            if replace_all:
                new_content = content.replace(old_code, new_code)
                replacements_made = content.count(old_code)
            else:
                new_content = content.replace(old_code, new_code, 1)
                replacements_made = 1

        p.write_text(new_content, encoding="utf-8")

        return {
            "success": True,
            "path": str(p),
            "replaced": True,
            "replacements_made": replacements_made,
            "backup_path": backup_path,
            "method": method,
        }

    except Exception as e:
        return {"error": str(e)}


# =========================================================
# TOOL: search_replace_preview
# =========================================================

@tool
def search_replace_preview(
    path: str,
    old_code: str = "",
    new_code: str = "",
    use_regex: bool = False,
    replace_all: bool = False,
    context_lines: int = 3,
):
    """
    Preview changes before applying them. Shows a diff-like output.
    """
    try:
        p = _normalize_path(path)

        if not p.exists():
            return {"error": "file not exists"}

        if not p.is_file():
            return {"error": "path is not a file"}

        content = p.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        matches = []

        if use_regex:
            if replace_all:
                for match in re.finditer(old_code, content):
                    matches.append({
                        "start": match.start(),
                        "end": match.end(),
                        "matched_text": match.group(),
                    })
            else:
                match = re.search(old_code, content)
                if match:
                    matches.append({
                        "start": match.start(),
                        "end": match.end(),
                        "matched_text": match.group(),
                    })
        else:
            start = 0
            while True:
                pos = content.find(old_code, start)
                if pos == -1:
                    break
                matches.append({
                    "start": pos,
                    "end": pos + len(old_code),
                    "matched_text": old_code,
                })
                if not replace_all:
                    break
                start = pos + 1

        if not matches:
            return {
                "matches": [],
                "total_matches": 0,
                "preview": "No matches found.",
            }

        preview_lines = []
        preview_lines.append(f"Found {len(matches)} match(es) in {path}:")
        preview_lines.append("=" * 60)

        for i, match in enumerate(matches):
            start_line = content[:match["start"]].count("\n")
            end_line = content[:match["end"]].count("\n")

            preview_lines.append(f"\n[Match {i + 1}] Lines {start_line + 1}-{end_line + 1}:")
            preview_lines.append("-" * 40)

            ctx_start = max(0, start_line - context_lines)
            ctx_end = min(len(lines), end_line + context_lines + 1)

            for line_num in range(ctx_start, ctx_end):
                prefix = "  "
                if start_line <= line_num <= end_line and line_num == start_line:
                    prefix = "- "
                preview_lines.append(f"{prefix}{line_num + 1}: {lines[line_num]}")

            preview_lines.append("  ... becomes:")
            preview_lines.append(f"+ {new_code}")

        return {
            "matches": matches,
            "total_matches": len(matches),
            "preview": "\n".join(preview_lines),
        }

    except Exception as e:
        return {"error": str(e)}


# =========================================================
# TOOL: revert_file_backup
# =========================================================

@tool
def revert_file_backup(path: str):
    """
    Revert a file to its backup version (.bak).
    """
    try:
        p = _normalize_path(path)
        backup_p = p.with_suffix(p.suffix + ".bak")

        if not backup_p.exists():
            return {"error": "No backup file found"}

        content = backup_p.read_text(encoding="utf-8", errors="ignore")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "message": f"Reverted {path} from backup",
            "backup_path": str(backup_p),
        }

    except Exception as e:
        return {"error": str(e)}


# =========================================================
# BACKWARD-COMPATIBILITY ALIASES
# =========================================================

register_tool_alias("execute_shell_command", run_shell)
register_tool_alias("list_directory_files", list_files)
register_tool_alias("read_file_content", read_file)
register_tool_alias("write_new_file", write_file)
register_tool_alias("modify_file_code", replace_in_file)

register_tool_alias("run_in_terminal", run_in_terminal)
register_tool_alias("execute_bash", execute_bash)
register_tool_alias("shell", shell)
register_tool_alias("bash", bash)
register_tool_alias("powershell", powershell)
register_tool_alias("cmd", cmd)
register_tool_alias("search_replace_preview", search_replace_preview)
register_tool_alias("revert_file_backup", revert_file_backup)

# =========================================================
# OPENAI TOOLS SCHEMA
# =========================================================

OPENAI_TOOLS = [
    # ========== FILE TOOLS (Priority - Listed First) ==========
    {
        "type": "function",
        "function": {
            "name": "list_directory_files",
            "description": "List files and directories in a path within the workspace. Use this to inspect directory contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path within workspace (default: current directory)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_content",
            "description": "Primary tool for reading local files. Use this instead of shell commands like type/cat/grep when you need file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file within workspace"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_new_file",
            "description": "Primary tool for creating new files or overwriting entire file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file within workspace"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modify_file_code",
            "description": "Primary tool for editing existing files. Use this instead of shell commands, sed, perl, redirects, or scripts when modifying files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file within workspace"
                    },
                    "old_code": {
                        "type": "string",
                        "description": "The code string or regex pattern to search for"
                    },
                    "new_code": {
                        "type": "string",
                        "description": "The new code string to replace with"
                    },
                    "use_regex": {
                        "type": "boolean",
                        "description": "If True, treat old_code as a regex pattern"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "If True, replace all occurrences"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional start line number (1-indexed) for line range replacement"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional end line number (1-indexed) for line range replacement"
                    },
                    "create_backup": {
                        "type": "boolean",
                        "description": "If True, create a .bak backup file before modifying"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_replace_preview",
            "description": "Preview code changes before applying them. Use before risky edits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file within workspace"
                    },
                    "old_code": {
                        "type": "string",
                        "description": "The code string or regex pattern to search for"
                    },
                    "new_code": {
                        "type": "string",
                        "description": "The new code string to replace with"
                    },
                    "use_regex": {
                        "type": "boolean",
                        "description": "If True, treat old_code as a regex pattern"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "If True, show all matches"
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Number of context lines to show around each match"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "revert_file_backup",
            "description": "Revert a file to its backup version (.bak file).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file within workspace"
                    }
                },
                "required": ["path"]
            }
        }
    },
    # ========== TERMINAL TOOLS (Fallback - Listed After File Tools) ==========
    {
        "type": "function",
        "function": {
            "name": "execute_shell_command",
            "description": f"Run a shell command only for environment inspection, build, test, or runtime tasks. Default shell: {DEFAULT_SHELL}. {SHELL_HELP}. Do not use this tool to read, write, or modify files when dedicated file tools exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_in_terminal",
            "description": "Codex-compatible terminal execution tool. Use only for build/run/test tasks, not for file operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The terminal command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_bash",
            "description": "Codex/OpenHands-compatible bash execution tool. Use only for build/run/test tasks, not for file operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Shell command execution alias. Use only for build/run/test tasks, not for file operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Bash command execution alias. Use only for build/run/test tasks, not for file operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "powershell",
            "description": "Windows PowerShell command executor. Use only for build/run/test tasks, not for file operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The PowerShell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cmd",
            "description": "Windows CMD command executor. Use only for build/run/test tasks, not for file operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The CMD command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
]

# =========================================================
# PLATFORM INFO FOR PROMPT
# =========================================================

def get_platform_info():
    if IS_WINDOWS:
        return {
            "os": "Windows",
            "shell": "powershell",
            "commands": {
                "list_files": "dir",
                "read_file": "type",
                "search": "findstr",
                "current_dir": "cd",
            }
        }
    elif IS_MACOS:
        return {
            "os": "macOS",
            "shell": "bash",
            "commands": {
                "list_files": "ls",
                "read_file": "cat",
                "search": "grep",
                "current_dir": "pwd",
            }
        }
    else:
        return {
            "os": "Linux",
            "shell": "bash",
            "commands": {
                "list_files": "ls",
                "read_file": "cat",
                "search": "grep",
                "current_dir": "pwd",
            }
        }