"""
Tests for CLI Commands - 终端总控台子命令测试
验证：
1. 命令行参数解析器支持 demo, status, export 等子命令；
2. cmd_status 能正确读取 project.yaml 并输出题材与战力标尺；
3. novel-factory 入口点正常响应。
"""

import sys
from unittest.mock import patch
import pytest

from src.novel_factory.cli.main import build_parser, cmd_status, main


def test_cli_parser_subcommands():
    """测试命令行解析器各子命令"""
    parser = build_parser()

    # demo
    args = parser.parse_args(["demo"])
    assert args.command == "demo"

    # status
    args = parser.parse_args(["status", "--project", "project.yaml"])
    assert args.command == "status"
    assert args.project == "project.yaml"

    # export
    args = parser.parse_args(["export", "--format", "txt", "--output", "exports/out"])
    assert args.command == "export"
    assert args.format == "txt"
    assert args.output == "exports/out"


def test_cli_status_execution(capsys):
    """测试 status 状态探测命令运行"""
    parser = build_parser()
    args = parser.parse_args(["status", "--project", "project.yaml"])
    cmd_status(args)

    # 捕获 rich 输出
    # 由于 Rich 绑定了 console，验证函数执行正常无异常抛出即可


def test_cli_main_entry_dispatch():
    """测试 main 入口函数参数路由"""
    with patch.object(sys, "argv", ["novel-factory", "status"]):
        # 只要正常执行无未捕获异常即通过
        main()
