import logging
import os
from pathlib import Path

# Ensure relative paths are resolved against the current workspace by default.
# You can override this externally by setting WORKSPACE before starting the server.
os.environ.setdefault("WORKSPACE", str(Path.cwd().resolve()))

from mcp.server.fastmcp import FastMCP

import tools as tools_module
from tools import (
    run_shell as run_shell_tool,
    list_files as list_files_tool,
    read_file as read_file_tool,
    write_file as write_file_tool,
    replace_in_file as replace_in_file_tool,
    search_replace_preview as search_replace_preview_tool,
    revert_file_backup as revert_file_backup_tool,
    powershell as powershell_tool,
    cmd as cmd_tool,
    bash as bash_tool,
    shell as shell_tool,
    run_in_terminal as run_in_terminal_tool,
    execute_bash as execute_bash_tool,
)

# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger("codex-tools")

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    _handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_handler)

logger.setLevel(logging.INFO)
logger.propagate = False

# Keep module-level workspace in sync
tools_module.WORKSPACE = os.environ.get("WORKSPACE", str(Path.cwd().resolve()))

mcp = FastMCP("codex-tools")

# =========================================================
# TERMINAL TOOLS
# =========================================================

@mcp.tool()
def execute_shell_command(command: str):
    """
    执行系统 Shell/终端命令。
    不要用它来读写或修改文件。
    """
    return run_shell_tool(command)


@mcp.tool()
def run_in_terminal(command: str):
    """
    Codex 兼容的终端执行工具。
    """
    return run_in_terminal_tool(command)


@mcp.tool()
def execute_bash(command: str):
    """
    Codex/OpenHands 兼容的 bash 执行器。
    """
    return execute_bash_tool(command)


@mcp.tool()
def shell(command: str):
    """
    Shell 命令执行别名。
    """
    return shell_tool(command)


@mcp.tool()
def bash(command: str):
    """
    Bash 命令执行别名。
    """
    return bash_tool(command)


@mcp.tool()
def powershell(command: str):
    """
    Windows PowerShell 命令执行器。
    """
    return powershell_tool(command)


@mcp.tool()
def cmd(command: str):
    """
    Windows CMD 命令执行器。
    """
    return cmd_tool(command)

# =========================================================
# FILE TOOLS
# =========================================================

@mcp.tool()
def list_directory_files(path: str = "."):
    """
    列出指定目录下的文件和文件夹。
    """
    return list_files_tool(path)


@mcp.tool()
def read_file_content(path: str):
    """
    读取并查看本地文件的完整内容。
    MCP 安全版：不向 stdout 输出任何调试信息。
    """
    logger.debug("read_file_content called with path=%r", path)
    result = read_file_tool(path)
    logger.debug("read_file_content completed")
    return result


@mcp.tool()
def write_new_file(path: str, content: str):
    """
    写入一个新文件，或覆盖现有文件。
    """
    return write_file_tool(path, content)


@mcp.tool()
def modify_file_code(
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
    修改现有文件内容的唯一推荐工具。
    """
    return replace_in_file_tool(
        path,
        old_code,
        new_code,
        use_regex=use_regex,
        replace_all=replace_all,
        start_line=start_line,
        end_line=end_line,
        create_backup=create_backup,
    )


@mcp.tool()
def search_replace_preview(
    path: str,
    old_code: str = "",
    new_code: str = "",
    use_regex: bool = False,
    replace_all: bool = False,
    context_lines: int = 3,
):
    """
    在应用更改前预览替换效果。
    """
    return search_replace_preview_tool(
        path,
        old_code,
        new_code,
        use_regex=use_regex,
        replace_all=replace_all,
        context_lines=context_lines,
    )


@mcp.tool()
def revert_file_backup(path: str):
    """
    恢复文件到 .bak 备份版本。
    """
    return revert_file_backup_tool(path)

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    # 不要在这里使用 print，避免污染 MCP stdio 协议。
    mcp.run()