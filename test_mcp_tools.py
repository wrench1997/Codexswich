"""
测试 MCP 工具函数 - 直接调用 tools.py 中的工具
"""

from tools import (
    run_shell,
    list_files,
    read_file,
    write_file,
    replace_in_file,
    search_replace_preview,
    powershell,
    cmd,
)


def test_list_files():
    """测试列出目录文件"""
    print("=" * 60)
    print("测试 list_files")
    print("=" * 60)
    result = list_files(".")
    print(result)
    return result


def test_read_file():
    """测试读取文件"""
    print("\n" + "=" * 60)
    print("测试 read_file - 读取 README.md")
    print("=" * 60)
    result = read_file("README.md")
    if "error" in result:
        print(f"错误：{result['error']}")
    else:
        print(f"文件路径：{result['path']}")
        print(f"内容预览：{result['content'][:200]}...")
    return result


def test_run_shell():
    """测试执行 Shell 命令"""
    print("\n" + "=" * 60)
    print("测试 run_shell - 执行 dir 命令")
    print("=" * 60)
    result = run_shell("dir")
    print(result)
    return result


def test_powershell():
    """测试 PowerShell 命令"""
    print("\n" + "=" * 60)
    print("测试 powershell - 获取当前目录")
    print("=" * 60)
    result = powershell("Get-Location")
    print(result)
    return result


def test_cmd():
    """测试 CMD 命令"""
    print("\n" + "=" * 60)
    print("测试 cmd - 执行 ver 命令")
    print("=" * 60)
    result = cmd("ver")
    print(result)
    return result


def test_write_file():
    """测试写入文件"""
    print("\n" + "=" * 60)
    print("测试 write_file - 创建测试文件")
    print("=" * 60)
    result = write_file("test_output.txt", "这是一个测试文件\n用于验证写入功能")
    print(result)
    return result


def test_search_replace_preview():
    """测试替换预览"""
    print("\n" + "=" * 60)
    print("测试 search_replace_preview")
    print("=" * 60)
    # 先创建一个测试文件
    write_file("test_edit.txt", "Hello World\nThis is a test\nHello Again")
    
    result = search_replace_preview(
        "test_edit.txt",
        old_code="Hello",
        new_code="Hi",
        replace_all=True,
        context_lines=1
    )
    print(result.get("preview", result))
    return result


def run_all_tests():
    """运行所有测试"""
    print("开始运行 MCP 工具测试...\n")
    
    test_list_files()
    test_read_file()
    test_run_shell()
    test_powershell()
    test_cmd()
    test_write_file()
    test_search_replace_preview()
    
    print("\n" + "=" * 60)
    print("所有测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
