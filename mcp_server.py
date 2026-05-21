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
    【注意】执行系统 Shell/终端 命令。
    【严禁行为】：绝对不可以使用此工具来读取、写入或修改文件！
    严禁在此工具中使用 Get-Content、Set-Content、cat、sed、echo >、Out-File、Add-Content 等命令！
    
    对于文件的读取、覆盖或修改，你必须去调用专门的文件处理工具（如 read_file_content、modify_file_code、write_new_file）。
    此工具仅限用于：运行编译命令 (npm/cargo/zig build)、启动脚本、查询系统环境、搜索文件内容 (grep/findstr) 等。
    """
    return run_shell(command)


@mcp.tool()
def run_in_terminal(command: str):
    """
    【注意】Codex 兼容的终端执行工具。
    【严禁行为】：绝对不可以使用此工具来读取、写入或修改文件！
    严禁使用 Get-Content、Set-Content、cat、sed、echo >、Out-File 等文件操作命令！
    
    此工具仅限用于：运行编译命令、启动脚本、查询系统环境等。
    对于文件操作，必须使用专门的文件工具（如 read_file_content、modify_file_code、write_new_file）。
    """
    return run_in_terminal(command)


@mcp.tool()
def execute_bash(command: str):
    """
    【注意】Codex/OpenHands 兼容的 bash 执行器。
    【严禁行为】：绝对不可以使用此工具来读取、写入或修改文件！
    严禁使用 cat、sed、awk、echo > 等文件操作命令！
    
    此工具仅限用于：运行编译命令、启动脚本、查询系统环境等。
    对于文件操作，必须使用专门的文件工具（如 read_file_content、modify_file_code、write_new_file）。
    """
    return execute_bash(command)


@mcp.tool()
def shell(command: str):
    """
    【注意】Shell 命令执行别名。
    【严禁行为】：绝对不可以使用此工具来读取、写入或修改文件！
    严禁使用 Get-Content、Set-Content、cat、sed、echo >、Out-File 等文件操作命令！
    
    此工具仅限用于：运行编译命令、启动脚本、查询系统环境等。
    对于文件操作，必须使用专门的文件工具（如 read_file_content、modify_file_code、write_new_file）。
    """
    return shell(command)


@mcp.tool()
def bash(command: str):
    """
    【注意】Bash 命令执行别名。
    【严禁行为】：绝对不可以使用此工具来读取、写入或修改文件！
    严禁使用 cat、sed、awk、echo > 等文件操作命令！
    
    此工具仅限用于：运行编译命令、启动脚本、查询系统环境等。
    对于文件操作，必须使用专门的文件工具（如 read_file_content、modify_file_code、write_new_file）。
    """
    return bash(command)


@mcp.tool()
def powershell(command: str):
    """
    【注意】Windows PowerShell 命令执行器。
    【严禁行为】：绝对不可以使用此工具来读取、写入或修改文件！
    严禁使用 Get-Content、Set-Content、Add-Content、Out-File、echo > 等文件操作命令！
    
    此工具仅限用于：运行编译命令、启动脚本、查询系统环境等。
    对于文件操作，必须使用专门的文件工具（如 read_file_content、modify_file_code、write_new_file）。
    """
    return powershell(command)


@mcp.tool()
def cmd(command: str):
    """
    【注意】Windows CMD 命令执行器。
    【严禁行为】：绝对不可以使用此工具来读取、写入或修改文件！
    严禁使用 type、copy con、echo > 等文件操作命令！
    
    此工具仅限用于：运行编译命令、启动脚本、查询系统环境等。
    对于文件操作，必须使用专门的文件工具（如 read_file_content、modify_file_code、write_new_file）。
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
    【强制要求】这是修改代码和文本文件的唯一指定工具！
    当需要修改现有文件中的代码时，必须调用此工具，绝对不要使用终端命令！
    
    相比终端命令，此工具绝对安全，且会自动创建备份文件，支持正则替换和范围修改。
    
    Args:
        path: 要修改的文件路径。
        old_code: 要搜索的代码字符串或正则表达式（必须先调用 read_file_content 确认内容存在）。
        new_code: 要替换成的新代码字符串。
        use_regex: 如果为 True，将 old_code 视为正则表达式。
        replace_all: 如果为 True，替换所有匹配项。
        start_line: 可选的起始行号 (1-indexed)，用于范围替换。
        end_line: 可选的结束行号 (1-indexed)，用于范围替换。
        create_backup: 如果为 True，在修改前创建.bak 备份文件（默认开启）。
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
