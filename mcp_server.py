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
def execute_shell_command(command: str, cwd: str = None, timeout: int = None) -> dict:
    """Run a shell command only for environment inspection, build, test, or runtime tasks."""
    return run_shell_tool(command, cwd=cwd, timeout=timeout)

@mcp.tool()
def run_in_terminal(command: str, cwd: str = None, timeout: int = None) -> dict:
    """Codex-compatible terminal execution tool. Use only for build/run/test tasks, not for file operations."""
    return run_in_terminal_tool(command, cwd=cwd, timeout=timeout)

@mcp.tool()
def execute_bash(command: str, cwd: str = None, timeout: int = None) -> dict:
    """Codex/OpenHands-compatible bash execution tool. Use only for build/run/test tasks."""
    return execute_bash_tool(command, cwd=cwd, timeout=timeout)

@mcp.tool()
def shell(command: str, cwd: str = None, timeout: int = None) -> dict:
    """Shell command execution alias. Use only for build/run/test tasks."""
    return shell_tool(command, cwd=cwd, timeout=timeout)

@mcp.tool()
def bash(command: str, cwd: str = None, timeout: int = None) -> dict:
    """Bash command execution alias. Use only for build/run/test tasks."""
    return bash_tool(command, cwd=cwd, timeout=timeout)

@mcp.tool()
def powershell(command: str, cwd: str = None, timeout: int = None) -> dict:
    """Windows PowerShell command executor. Use only for build/run/test tasks."""
    return powershell_tool(command, cwd=cwd, timeout=timeout)

@mcp.tool()
def cmd(command: str, cwd: str = None, timeout: int = None) -> dict:
    """Windows CMD command executor. Use only for build/run/test tasks."""
    return cmd_tool(command, cwd=cwd, timeout=timeout)

# =========================================================
# FILE TOOLS
# =========================================================

@mcp.tool()
def list_directory_files(path: str = ".") -> dict:
    """List files and directories in a path within the workspace. Use this to inspect directory contents."""
    return list_files_tool(path)

@mcp.tool()
def read_file_content(path: str) -> dict:
    """Primary tool for reading local files. Use this instead of shell commands."""
    logger.debug("read_file_content called with path=%r", path)
    return read_file_tool(path)

@mcp.tool()
def write_new_file(path: str, content: str) -> dict:
    """Primary tool for creating new files or overwriting entire file contents."""
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
    create_backup: bool = True
) -> dict:
    """Primary tool for editing existing files. Use this instead of shell commands when modifying files."""
    return replace_in_file_tool(
        path, old_code, new_code, use_regex=use_regex, 
        replace_all=replace_all, start_line=start_line, 
        end_line=end_line, create_backup=create_backup,
    )

@mcp.tool()
def search_replace_preview(
    path: str,
    old_code: str = "",
    new_code: str = "",
    use_regex: bool = False,
    replace_all: bool = False,
    context_lines: int = 3
) -> dict:
    """Preview code changes before applying them. Use before risky edits."""
    return search_replace_preview_tool(
        path, old_code, new_code, use_regex=use_regex,
        replace_all=replace_all, context_lines=context_lines,
    )

@mcp.tool()
def revert_file_backup(path: str) -> dict:
    """Revert a file to its backup version (.bak file)."""
    return revert_file_backup_tool(path)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    # 不要在这里使用 print，避免污染 MCP stdio 协议。
    mcp.run()