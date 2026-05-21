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
def execute_shell_command(command: str):
    """
    【强制要求】执行系统 Shell 命令。
    当你需要查看环境、运行编译、执行脚本、搜索文件 (grep/findstr) 时，必须调用此工具。
    如果是 Windows 系统请使用 powershell 语法，Linux 请使用 bash 语法。
    切勿自己猜测命令执行结果，必须通过此工具获取真实输出！
    """
    return run_shell(command)


@mcp.tool()
def run_in_terminal(command: str):
    """
    【强制要求】Codex 兼容的终端执行工具。
    当需要执行任何命令行操作时，必须调用此工具获取真实输出，严禁猜测结果！
    """
    return run_in_terminal(command)


@mcp.tool()
def execute_bash(command: str):
    """
    【强制要求】Codex/OpenHands 兼容的 bash 执行器。
    当需要在类 Unix 环境中执行命令时必须使用此工具。
    """
    return execute_bash(command)


@mcp.tool()
def shell(command: str):
    """
    【强制要求】Shell 命令执行别名。
    通用 shell 命令执行入口，必须调用此工具而非自己猜测输出。
    """
    return shell(command)


@mcp.tool()
def bash(command: str):
    """
    【强制要求】Bash 命令执行别名。
    专门用于 bash 环境下的命令执行。
    """
    return bash(command)


@mcp.tool()
def powershell(command: str):
    """
    【强制要求】Windows PowerShell 命令执行器。
    当在 Windows 系统上执行命令时，必须优先使用此工具。
    """
    return powershell(command)


@mcp.tool()
def cmd(command: str):
    """
    【强制要求】Windows CMD 命令执行器。
    当需要执行传统 CMD 命令时必须调用此工具。
    """
    return cmd(command)


# =========================================================
# FILE TOOLS
# =========================================================

@mcp.tool()
def list_directory_files(path: str = "."):
    """
    【强制要求】列出指定目录下的所有文件和文件夹。
    当用户问"当前目录下有什么"、"帮我看看项目结构"时，必须优先调用此工具。
    切勿凭记忆或猜测目录内容！
    """
    return list_files(path)


@mcp.tool()
def read_file_content(path: str):
    """
    【强制要求】读取并查看本地文件的完整内容。
    当用户要求你分析代码、修改代码、或者询问某个文件里的逻辑时，
    你绝对不能凭记忆猜测，必须先调用此工具读取文件的真实内容！
    """
    return read_file(path)


@mcp.tool()
def write_new_file(path: str, content: str):
    """
    向指定路径写入全新的文件。如果目录不存在会自动创建。
    当需要创建新代码文件或覆盖现有文件时使用此工具。
    """
    return write_file(path, content)


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
    【强制要求】高级代码修改工具。用于在现有文件中替换特定代码块。
    在使用此工具前，你必须先调用 read_file_content 确认 old_code 是文件中真实存在的字符串。
    严禁凭空猜测文件内容进行修改！
    
    Args:
        path: 要修改的文件路径。
        old_code: 要搜索的代码字符串或正则表达式。
        new_code: 要替换成的新代码字符串。
        use_regex: 如果为 True，将 old_code 视为正则表达式。
        replace_all: 如果为 True，替换所有匹配项。
        start_line: 可选的起始行号 (1-indexed)，用于范围替换。
        end_line: 可选的结束行号 (1-indexed)，用于范围替换。
        create_backup: 如果为 True，在修改前创建.bak 备份文件。
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
def search_replace_preview(
    path: str,
    old_code: str = "",
    new_code: str = "",
    use_regex: bool = False,
    replace_all: bool = False,
    context_lines: int = 3,
):
    """
    在应用更改前预览修改效果。显示类似 diff 的输出。
    建议在正式修改前先调用此工具确认变更范围。
    
    Args:
        path: 要检查的文件路径。
        old_code: 要搜索的代码字符串或正则表达式。
        new_code: 要替换成的新代码字符串。
        use_regex: 如果为 True，将 old_code 视为正则表达式。
        replace_all: 如果为 True，显示所有匹配项。
        context_lines: 在每个匹配项周围显示的行数。
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
def revert_file_backup(path: str):
    """
    将文件恢复到备份版本 (.bak)。
    当修改出错需要回滚时调用此工具。
    
    Args:
        path: 要恢复的文件路径。
    """
    return revert_file_backup(path)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    mcp.run()
