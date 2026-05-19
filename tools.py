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
