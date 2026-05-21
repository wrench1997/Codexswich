"""
tools.py - Tool Registry and Executor for Codex Gateway

This module provides a centralized tool registry and execution framework for
the Codex Gateway system. It enables AI assistants to interact with the local
filesystem and execute shell commands safely.

Main Features:
    - Cross-platform shell command execution (Windows, Linux, macOS)
    - File system operations (read, write, list directories)
    - Tool registration and discovery
    - OpenAI function calling schema generation

Available Tools:
    - run_shell: Execute shell commands
    - list_files: List directory contents
    - read_file: Read file contents
    - write_file: Write content to files
    - powershell: Windows PowerShell commands (Windows only)
    - cmd: Windows CMD commands (Windows only)
    - bash: Bash shell commands

Example:
    >>> from tools import TOOLS
    >>> result = TOOLS['list_files']('.')
    >>> print(result['files'])

Author: Codex Gateway Team
Version: 1.0.0
"""

import subprocess
import os
import re
import platform
from pathlib import Path

# =========================================================
# PLATFORM DETECTION
# =========================================================

SYSTEM_PLATFORM = platform.system()
IS_WINDOWS = os.name == "nt"
IS_LINUX = SYSTEM_PLATFORM == "Linux"
IS_MACOS = SYSTEM_PLATFORM == "Darwin"

# Default shell based on platform
if IS_WINDOWS:
    DEFAULT_SHELL = "powershell"
    SHELL_HELP = "Use Windows PowerShell commands (e.g., dir, type, findstr)"
else:
    DEFAULT_SHELL = "bash"
    SHELL_HELP = "Use Linux/Unix shell commands (e.g., ls, cat, grep)"

# =========================================================
# CONFIG - Security Settings
# =========================================================

# 工作目录（无限制）
# 如果设置为具体路径，所有工具操作将被限制在该目录内
# 当前为 None，表示无目录限制
WORKSPACE = None

# 命令黑名单 - 已禁用
# 预留功能，可用于阻止危险命令的执行
# 例如：["rm -rf", "del /s", "format"]
# 当前为空列表，表示不阻止任何命令
COMMAND_BLACKLIST = []

# 命令执行超时（秒）
# 防止长时间运行的命令阻塞系统
# 超过此时长的命令将被强制终止
COMMAND_TIMEOUT = 30

# =========================================================
# TOOL REGISTRY
# =========================================================

TOOLS = {}

def tool(fn):
    """
    Decorator to register a function as a tool.
    
    This decorator automatically adds the decorated function to the
    TOOLS registry dictionary, making it available for discovery
    and execution by the Codex Gateway system.
    
    Args:
        fn: The function to register as a tool.
        
    Returns:
        The original function (unchanged).
        
    Example:
        >>> @tool
        >>> def my_custom_tool(arg: str):
        >>>     return {"result": arg}
        >>> 
        >>> # my_custom_tool is now available in TOOLS dict
        >>> TOOLS['my_custom_tool']('hello')
    """
    TOOLS[fn.__name__] = fn
    return fn


# =========================================================
# TOOL: run_shell
# =========================================================

@tool
def run_shell(command: str):
    """
    Run a shell command in the system's default shell.
    
    Executes the given command using the platform's default shell
    (PowerShell on Windows, bash on Linux/macOS). The command runs
    with the permissions of the current user.
    
    Args:
        command (str): The shell command to execute.
        
    Returns:
        dict: A dictionary containing one of the following:
            - On success:
                {
                    "stdout": str,      # Standard output
                    "stderr": str,      # Standard error
                    "returncode": int   # Exit code (0 = success)
                }
            - On timeout:
                {
                    "error": str        # Timeout error message
                }
            - On exception:
                {
                    "error": str        # Exception message
                }
                
    Example:
        >>> run_shell("dir")  # Windows
        >>> run_shell("ls -la")  # Linux/macOS
        
    Note:
        - Commands are subject to COMMAND_TIMEOUT (default: 30 seconds)
        - WORKSPACE setting is used as the working directory if configured
    """
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=WORKSPACE,
            timeout=COMMAND_TIMEOUT,
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
        
    except subprocess.TimeoutExpired:
        return {
            "error": f"Command timed out after {COMMAND_TIMEOUT} seconds"
        }
    except Exception as e:
        return {
            "error": str(e)
        }


# =========================================================
# TOOL: list_files
# =========================================================

@tool
def list_files(path: str = "."):
    """
    List all files and directories in the specified path.
    
    Args:
        path (str): The directory path to list. Defaults to current directory (".").
                   Can be relative or absolute.
        
    Returns:
        dict: A dictionary containing one of the following:
            - On success:
                {
                    "files": [          # List of file/directory info
                        {
                            "name": str,    # File/directory name
                            "is_dir": bool  # True if directory, False if file
                        },
                        ...
                    ],
                    "path": str         # Resolved absolute path
                }
            - On error:
                {
                    "error": str        # Error message
                }
                
    Example:
        >>> list_files(".")
        >>> list_files("c:\\Users\\admin\\Desktop")
        
    Note:
        - Returns both files and directories
        - Does not recurse into subdirectories
    """
    
    try:
        p = Path(path)
        p = p.resolve()
        
        if not p.exists():
            return {
                "error": "path not exists"
            }
        
        if not p.is_dir():
            return {
                "error": "path is not a directory"
            }
        
        files = []
        for item in p.iterdir():
            files.append({
                "name": item.name,
                "is_dir": item.is_dir(),
            })
        
        return {
            "files": files,
            "path": str(p),
        }
        
    except Exception as e:
        return {
            "error": str(e)
        }


# =========================================================
# TOOL: read_file
# =========================================================

@tool
def read_file(path: str):
    """
    Read the entire contents of a file.
    
    Args:
        path (str): The file path to read. Can be relative or absolute.
        
    Returns:
        dict: A dictionary containing one of the following:
            - On success:
                {
                    "content": str,     # File contents (UTF-8 encoded)
                    "path": str         # Resolved absolute path
                }
            - On error:
                {
                    "error": str        # Error message
                }
                
    Example:
        >>> read_file("c:\\Users\\admin\\Desktop\\Codexswich\\tools.py")
        
    Note:
        - Files are read with UTF-8 encoding
        - Invalid UTF-8 sequences are ignored (errors="ignore")
        - Large files are loaded entirely into memory
    """
    
    try:
        p = Path(path)
        p = p.resolve()
        
        if not p.exists():
            return {
                "error": "file not exists"
            }
        
        if not p.is_file():
            return {
                "error": "path is not a file"
            }
        
        content = p.read_text(encoding="utf-8", errors="ignore")
        
        return {
            "content": content,
            "path": str(p),
        }
        
    except Exception as e:
        return {
            "error": str(e)
        }


# =========================================================
# TOOL: run_in_terminal (Codex compatibility)
# =========================================================

@tool
def run_in_terminal(command: str):
    """
    Codex/OpenHands compatible terminal execution tool.
    Alias for run_shell().
    """
    return run_shell(command)


# =========================================================
# TOOL: execute_bash (Codex/OpenHands compatibility)
# =========================================================

@tool
def execute_bash(command: str):
    """
    Codex/OpenHands compatible bash execution tool.
    Alias for run_shell().
    """
    return run_shell(command)


# =========================================================
# TOOL: shell (alias for run_shell)
# =========================================================

@tool
def shell(command: str):
    """
    Run a shell command. Alias for run_shell.
    
    This is a convenience alias that provides the same functionality
    as run_shell(). Use whichever name is more convenient.
    
    Args:
        command (str): The shell command to execute.
        
    Returns:
        dict: Same return format as run_shell().
        
    See Also:
        run_shell: The primary shell execution function.
    """
    return run_shell(command)


# =========================================================
# TOOL: bash (alias for run_shell)
# =========================================================

@tool
def bash(command: str):
    """
    Run a bash command. Alias for run_shell.
    
    On Linux/macOS, this executes in the bash shell.
    On Windows, this executes via the default shell (PowerShell).
    
    Args:
        command (str): The bash/shell command to execute.
        
    Returns:
        dict: Same return format as run_shell().
        
    Note:
        On Windows, bash-specific syntax may not work as expected
        since commands are executed via PowerShell.
        
    See Also:
        run_shell: The primary shell execution function.
        powershell: For Windows PowerShell-specific commands.
    """
    return run_shell(command)


# =========================================================
# TOOL: powershell (Windows native)
# =========================================================

@tool
def powershell(command: str):
    """
    Run a PowerShell command on Windows.
    
    This function specifically invokes PowerShell, making it ideal for
    Windows-specific administration tasks and scripting.
    
    Args:
        command (str): The PowerShell command to execute.
        
    Returns:
        dict: A dictionary containing one of the following:
            - On success:
                {
                    "stdout": str,      # Standard output
                    "stderr": str,      # Standard error
                    "returncode": int   # Exit code
                }
            - On platform error:
                {
                    "error": str        # "powershell is only available on Windows"
                }
            - On timeout/exception:
                {
                    "error": str        # Error message
                }
                
    Example:
        >>> powershell("Get-ChildItem")
        >>> powershell("Get-Process")
        
    Note:
        Only available on Windows systems. Returns an error on Linux/macOS.
    """
    if not IS_WINDOWS:
        return {"error": "powershell is only available on Windows"}
    
    try:
        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            cwd=WORKSPACE,
            timeout=COMMAND_TIMEOUT,
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
        
    except subprocess.TimeoutExpired:
        return {
            "error": f"Command timed out after {COMMAND_TIMEOUT} seconds"
        }
    except Exception as e:
        return {"error": str(e)}


# =========================================================
# TOOL: cmd (Windows cmd.exe)
# =========================================================

@tool
def cmd(command: str):
    """
    Run a command via Windows cmd.exe (Command Prompt).
    
    This function specifically invokes the legacy Windows Command Prompt,
    which is useful for running batch files and legacy Windows commands.
    
    Args:
        command (str): The cmd.exe command to execute.
        
    Returns:
        dict: A dictionary containing one of the following:
            - On success:
                {
                    "stdout": str,      # Standard output
                    "stderr": str,      # Standard error
                    "returncode": int   # Exit code
                }
            - On platform error:
                {
                    "error": str        # "cmd is only available on Windows"
                }
            - On timeout/exception:
                {
                    "error": str        # Error message
                }
                
    Example:
        >>> cmd("dir")
        >>> cmd("type filename.txt")
        
    Note:
        Only available on Windows systems. Returns an error on Linux/macOS.
    """
    if not IS_WINDOWS:
        return {"error": "cmd is only available on Windows"}
    
    try:
        result = subprocess.run(
            ["cmd", "/c", command],
            capture_output=True,
            text=True,
            cwd=WORKSPACE,
            timeout=COMMAND_TIMEOUT,
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
        
    except subprocess.TimeoutExpired:
        return {
            "error": f"Command timed out after {COMMAND_TIMEOUT} seconds"
        }
    except Exception as e:
        return {"error": str(e)}


# =========================================================
# TOOL: replace_in_file (enhanced version)
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
    
    Supports:
    - Exact string matching (default)
    - Regular expression matching
    - Line range replacement
    - Single or multiple replacements
    - Automatic backup before modification
    
    Args:
        path (str): The file path to modify. Can be relative or absolute.
        old_code (str): The code string or regex pattern to search for.
        new_code (str): The new code string to replace with.
        use_regex (bool): If True, treat old_code as a regex pattern.
        replace_all (bool): If True, replace all occurrences. If False, only first.
        start_line (int): Optional start line number (1-indexed) for range replacement.
        end_line (int): Optional end line number (1-indexed) for range replacement.
        create_backup (bool): If True, create a .bak backup file before modifying.
        
    Returns:
        dict: A dictionary containing one of the following:
            - On success:
                {
                    "success": True,
                    "path": str,
                    "replaced": True,
                    "replacements_made": int,   # Number of replacements
                    "backup_path": str,         # Path to backup file (if created)
                    "method": str               # "regex", "line_range", or "string"
                }
            - On not found:
                {
                    "success": False,
                    "error": "Pattern not found in file"
                }
            - On error:
                {
                    "error": str
                }
                
    Example:
        >>> # Simple string replacement
        >>> replace_in_file("test.py", "old_func", "new_func")
        
        >>> # Regex replacement
        >>> replace_in_file("test.py", r"def\\s+\\w+", "def new_name", use_regex=True)
        
        >>> # Replace all occurrences
        >>> replace_in_file("test.py", "foo", "bar", replace_all=True)
        
        >>> # Line range replacement
        >>> replace_in_file("test.py", start_line=10, end_line=20, new_code="new code")
    """
    
    try:
        p = Path(path)
        p = p.resolve()
        
        if not p.exists():
            return {"error": "file not exists"}
        
        if not p.is_file():
            return {"error": "path is not a file"}
        
        content = p.read_text(encoding="utf-8", errors="ignore")
        original_content = content
        replacements_made = 0
        method = "string"
        
        # Create backup if requested
        backup_path = None
        if create_backup:
            backup_file = p.with_suffix(p.suffix + ".bak")
            backup_file.write_text(content, encoding="utf-8")
            backup_path = str(backup_file)
        
        # Strategy 1: Line range replacement
        if start_line is not None or end_line is not None:
            method = "line_range"
            lines = content.splitlines(keepends=True)
            
            # Convert to 0-indexed
            start_idx = (start_line - 1) if start_line is not None else 0
            end_idx = end_line if end_line is not None else len(lines)
            
            # Ensure valid range
            start_idx = max(0, min(start_idx, len(lines)))
            end_idx = max(start_idx, min(end_idx, len(lines)))
            
            # Replace the range
            lines[start_idx:end_idx] = [new_code] if new_code else []
            new_content = "".join(lines)
            replacements_made = end_idx - start_idx
            
        # Strategy 2: Regex replacement
        elif use_regex:
            method = "regex"
            import re
            
            if replace_all:
                new_content, count = re.subn(old_code, new_code, content)
                replacements_made = count
            else:
                new_content, count = re.subn(old_code, new_code, content, count=1)
                replacements_made = count
                
            if replacements_made == 0:
                if create_backup and backup_path:
                    try:
                        Path(backup_path).unlink()
                    except:
                        pass
                return {"success": False, "error": "Pattern not found in file"}
                
        # Strategy 3: Simple string replacement
        else:
            method = "string"
            if old_code not in content:
                if create_backup and backup_path:
                    try:
                        Path(backup_path).unlink()
                    except:
                        pass
                return {"success": False, "error": "old_code not found in file"}
            
            if replace_all:
                new_content = content.replace(old_code, new_code)
                replacements_made = content.count(old_code)
            else:
                new_content = content.replace(old_code, new_code, 1)
                replacements_made = 1
        
        # Write the new content
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
    
    Args:
        path (str): The file path to examine.
        old_code (str): The code string or regex pattern to search for.
        new_code (str): The new code string to replace with.
        use_regex (bool): If True, treat old_code as a regex pattern.
        replace_all (bool): If True, show all matches. If False, show first only.
        context_lines (int): Number of context lines to show around each match.
        
    Returns:
        dict: A dictionary containing:
            - "matches": List of match objects with context
            - "total_matches": Total number of matches found
            - "preview": Human-readable preview of changes
    """
    
    try:
        import re
        
        p = Path(path)
        p = p.resolve()
        
        if not p.exists():
            return {"error": "file not exists"}
        
        if not p.is_file():
            return {"error": "path is not a file"}
        
        content = p.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        
        matches = []
        
        if use_regex:
            # Find all regex matches with positions
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
            # Find all string matches
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
        
        # Build preview with context
        preview_lines = []
        preview_lines.append(f"Found {len(matches)} match(es) in {path}:")
        preview_lines.append("=" * 60)
        
        for i, match in enumerate(matches):
            # Find line numbers
            start_line = content[:match["start"]].count("\n")
            end_line = content[:match["end"]].count("\n")
            
            preview_lines.append(f"\n[Match {i+1}] Lines {start_line + 1}-{end_line + 1}:")
            preview_lines.append("-" * 40)
            
            # Show context
            ctx_start = max(0, start_line - context_lines)
            ctx_end = min(len(lines), end_line + context_lines + 1)
            
            for line_num in range(ctx_start, ctx_end):
                prefix = "  "
                if start_line <= line_num <= end_line:
                    if line_num == start_line:
                        prefix = "- "  # Old code
                    else:
                        prefix = "  "
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
    
    Args:
        path (str): The file path to revert.
        
    Returns:
        dict: Result of the revert operation.
    """
    
    try:
        p = Path(path)
        p = p.resolve()
        backup_p = p.with_suffix(p.suffix + ".bak")
        
        if not backup_p.exists():
            return {"error": "No backup file found"}
        
        if not p.exists():
            # Restore from backup
            content = backup_p.read_text(encoding="utf-8")
            p.write_text(content, encoding="utf-8")
        else:
            # Overwrite current with backup
            content = backup_p.read_text(encoding="utf-8")
            p.write_text(content, encoding="utf-8")
        
        return {
            "success": True,
            "message": f"Reverted {path} from backup",
            "backup_path": str(backup_p),
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
    
    This function will create the file if it doesn't exist, or overwrite
    it if it does. Parent directories are created automatically.
    
    Args:
        path (str): The file path to write to. Can be relative or absolute.
        content (str): The text content to write to the file.
        
    Returns:
        dict: A dictionary containing one of the following:
            - On success:
                {
                    "success": True,        # Operation succeeded
                    "path": str,            # Resolved absolute path
                    "bytes_written": int    # Number of bytes written
                }
            - On error:
                {
                    "error": str            # Error message
                }
                
    Example:
        >>> write_file("test.txt", "Hello, World!")
        >>> write_file("subdir\\file.txt", "Content")  # Creates subdir if needed
        
    Note:
        - Files are written with UTF-8 encoding
        - Existing files will be overwritten without warning
        - Parent directories are created if they don't exist
    """
    
    try:
        p = Path(path)
        p = p.resolve()
        
        # Create parent directories if needed
        p.parent.mkdir(parents=True, exist_ok=True)
        
        p.write_text(content, encoding="utf-8")
        
        return {
            "success": True,
            "path": str(p),
            "bytes_written": len(content),
        }
        
    except Exception as e:
        return {
            "error": str(e)
        }


# =========================================================
# OPENAI TOOLS SCHEMA
# =========================================================

# This schema is used for OpenAI function calling.
# It defines the structure and parameters that the AI model
# should use when invoking tools.
#
# Unified tool names for Codex compatibility:
# - shell: Execute shell commands
# - read_file: Read file contents
# - write_file: Write file contents
# - list_files: List directory contents

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": f"Run a shell command in the workspace directory. Default shell: {DEFAULT_SHELL}. {SHELL_HELP}",
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
            "name": "list_files",
            "description": "List files in a directory within the workspace",
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
            "name": "read_file",
            "description": "Read the contents of a file within the workspace",
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
            "name": "write_file",
            "description": "Write content to a file within the workspace",
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
            "name": "replace_in_file",
            "description": "Enhanced code replacement with regex, line range, and backup support",
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
                        "description": "If True, treat old_code as a regex pattern (default: False)"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "If True, replace all occurrences (default: False)"
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
                        "description": "If True, create a .bak backup file before modifying (default: True)"
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
            "description": "Preview code changes before applying them. Shows matches with context.",
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
                        "description": "If True, treat old_code as a regex pattern (default: False)"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "If True, show all matches (default: False)"
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Number of context lines to show around each match (default: 3)"
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
            "description": "Revert a file to its backup version (.bak file)",
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
]

# =========================================================
# PLATFORM INFO FOR PROMPT
# =========================================================

def get_platform_info():
    """
    Get platform-specific information for system prompts.
    
    Returns platform detection results including the operating system,
    default shell, and common command equivalents for that platform.
    This is useful for generating context-aware system prompts.
    
    Returns:
        dict: A dictionary containing:
            - "os" (str): Operating system name ("Windows", "macOS", or "Linux")
            - "shell" (str): Default shell name
            - "commands" (dict): Common command equivalents:
                - "list_files": Command to list directory contents
                - "read_file": Command to display file contents
                - "search": Command to search within files
                - "current_dir": Command to show current directory
                
    Example:
        >>> info = get_platform_info()
        >>> print(f"Running on {info['os']}")
        >>> print(f"Use '{info['commands']['list_files']}' to list files")
        
    Note:
        Linux and macOS share the same command set (Unix-style).
    """
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
