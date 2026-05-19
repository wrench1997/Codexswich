from mcp.server.fastmcp import FastMCP
from tools import (
    run_shell,
    list_files,
    read_file,
    write_file,
    powershell,
    cmd,
    bash,
    shell,
    run_in_terminal,
    execute_bash,
)

mcp = FastMCP("codex-tools")


# =========================================================
# TERMINAL TOOLS
# =========================================================

@mcp.tool()
def run_shell_tool(command: str):
    """
    Execute a shell command.
    """
    return run_shell(command)


@mcp.tool()
def run_in_terminal_tool(command: str):
    """
    Codex-compatible terminal execution tool.
    """
    return run_in_terminal(command)


@mcp.tool()
def execute_bash_tool(command: str):
    """
    Codex/OpenHands compatible bash executor.
    """
    return execute_bash(command)


@mcp.tool()
def shell_tool(command: str):
    """
    Shell alias.
    """
    return shell(command)


@mcp.tool()
def bash_tool(command: str):
    """
    Bash alias.
    """
    return bash(command)


@mcp.tool()
def powershell_tool(command: str):
    """
    Windows PowerShell executor.
    """
    return powershell(command)


@mcp.tool()
def cmd_tool(command: str):
    """
    Windows CMD executor.
    """
    return cmd(command)


# =========================================================
# FILE TOOLS
# =========================================================

@mcp.tool()
def list_files_tool(path: str = "."):
    """
    List files in a directory.
    """
    return list_files(path)


@mcp.tool()
def read_file_tool(path: str):
    """
    Read a file.
    """
    return read_file(path)


@mcp.tool()
def write_file_tool(path: str, content: str):
    """
    Write content to a file.
    """
    return write_file(path, content)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    mcp.run()
