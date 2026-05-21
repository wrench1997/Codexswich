from mcp.server.fastmcp import FastMCP
from tools import (
    run_shell,
    list_files,
    read_file,
    write_file,
    replace_in_file,
    search_replace_preview,
    revert_file_backup,
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


@mcp.tool()
def replace_in_file_tool(
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
    
    Args:
        path: The file path to modify.
        old_code: The code string or regex pattern to search for.
        new_code: The new code string to replace with.
        use_regex: If True, treat old_code as a regex pattern.
        replace_all: If True, replace all occurrences.
        start_line: Optional start line number (1-indexed) for range replacement.
        end_line: Optional end line number (1-indexed) for range replacement.
        create_backup: If True, create a .bak backup file before modifying.
    """
    return replace_in_file(
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
def search_replace_preview_tool(
    path: str,
    old_code: str = "",
    new_code: str = "",
    use_regex: bool = False,
    replace_all: bool = False,
    context_lines: int = 3,
):
    """
    Preview changes before applying them. Shows a diff-like output.
    
    Args:
        path: The file path to examine.
        old_code: The code string or regex pattern to search for.
        new_code: The new code string to replace with.
        use_regex: If True, treat old_code as a regex pattern.
        replace_all: If True, show all matches.
        context_lines: Number of context lines to show around each match.
    """
    return search_replace_preview(
        path,
        old_code,
        new_code,
        use_regex=use_regex,
        replace_all=replace_all,
        context_lines=context_lines,
    )


@mcp.tool()
def revert_file_backup_tool(path: str):
    """
    Revert a file to its backup version (.bak).
    
    Args:
        path: The file path to revert.
    """
    return revert_file_backup(path)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    mcp.run()
