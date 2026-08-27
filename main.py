"""
微信猫娘助手 — 程序入口。

启动全局 Enter 钩子，并在 CMD 窗口提供控制命令。
配置文件：config.json（由 config.example.json 复制后本地填写）
"""

from __future__ import annotations

import sys
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

from ai_engine import resolve_api_key
from app_config import TRANSFORM_CACHE, load_config, preview_samples, transform
from hook import WeChatCatHook

CONFIG_PATH = Path(__file__).with_name("config.json")
_BANNER_INNER_WIDTH = 38


def _display_width(text: str) -> int:
    """终端显示宽度（中文等宽字符计 2）。"""
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
    return width


def _pad_center(text: str, inner_width: int) -> str:
    gap = inner_width - _display_width(text)
    if gap <= 0:
        return text
    left = gap // 2
    return " " * left + text + " " * (gap - left)


def _print_banner() -> None:
    bar = "─" * _BANNER_INNER_WIDTH
    lines = ("微信猫娘助手", "Nekomimi for WeChat")
    print()
    print(f"  ╭{bar}╮")
    for line in lines:
        print(f"  │{_pad_center(line, _BANNER_INNER_WIDTH)}│")
    print(f"  ╰{bar}╯")
    print()


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _print_help() -> None:
    print("窗口命令:")
    print("  m      开关猫娘模式")
    print("  t      预览剪贴板猫化效果")
    print("  t 文本  预览指定文本")
    print("  d      内置示例预览")
    print("  c      清空预览缓存")
    print("  s      查看当前状态")
    print("  r      重新加载 config.json")
    print("  q      退出程序")
    print("  ?      显示帮助")
    print("-" * 42)


def main() -> None:
    _print_banner()
    _print_help()
    print("用法: 微信输入后按 Enter 发送 → 自动加主人/喵")
    print("说明: 短句走本地规则，超过 22 字或偶尔抽样才调 AI")
    print("配置: 编辑 config.json（API Key、主人概率等）")
    print()

    config = load_config(CONFIG_PATH)
    hook = WeChatCatHook(config, on_log=log)
    hook.start()

    if not resolve_api_key(config.ai):
        log("⚠ 未配置 API Key，将全部使用规则猫化")
    log("猫娘模式已开启")

    stop = threading.Event()

    def reload_config() -> None:
        nonlocal config
        config = load_config(CONFIG_PATH)
        hook.config = config
        TRANSFORM_CACHE.clear()
        log("已重载 config.json（缓存已清空）")

    def preview_text(text: str) -> None:
        if not text.strip():
            log("请输入要预览的文本，例如: t 你好")
            return
        log(f"原文: {text}")
        log(f"猫化: {transform(text, config, on_log=log)}")

    def preview_clipboard() -> None:
        import pyperclip

        preview_text(pyperclip.paste())

    def demo_samples() -> None:
        log("--- 内置示例 ---")
        for src, dst in preview_samples(config, on_log=log):
            log(f"  {src}  →  {dst}")

    def show_status() -> None:
        log(f"猫娘模式: {'开启' if hook.enabled else '关闭'}")
        log(f"主人: 强制={'开' if config.rules.force_master else '关'} · 概率 {config.rules.master_chance:.0%}")
        log(f"AI: 超过 {config.ai.min_length_for_ai} 字必调 · 短句抽样 {config.ai.use_ai_chance:.0%}")
        log(f"API Key: {'已配置' if resolve_api_key(config.ai) else '未配置'} · 模型 {config.ai.model}")
        log(f"预览缓存: {len(TRANSFORM_CACHE)} 条")

    def toggle() -> None:
        on = hook.toggle()
        log("猫娘模式已开启" if on else "猫娘模式已关闭")

    def quit_app() -> None:
        log("正在退出…")
        hook.stop()
        stop.set()

    def command_loop() -> None:
        while not stop.is_set():
            try:
                raw = input("命令> ").strip()
            except (EOFError, KeyboardInterrupt):
                quit_app()
                break

            if not raw:
                continue

            parts = raw.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd in ("q", "quit", "exit"):
                quit_app()
                break
            if cmd in ("m", "toggle"):
                toggle()
            elif cmd in ("t", "preview"):
                if arg:
                    preview_text(arg)
                else:
                    preview_clipboard()
            elif cmd in ("d", "demo"):
                demo_samples()
            elif cmd in ("s", "status"):
                show_status()
            elif cmd in ("r", "reload"):
                reload_config()
            elif cmd in ("c", "clear"):
                TRANSFORM_CACHE.clear()
                log("预览缓存已清空")
            elif cmd in ("?", "help"):
                _print_help()
            else:
                log(f"未知命令: {raw}，输入 ? 查看帮助")

    cmd_thread = threading.Thread(target=command_loop, daemon=True)
    cmd_thread.start()

    try:
        stop.wait()
    except KeyboardInterrupt:
        quit_app()

    sys.exit(0)


if __name__ == "__main__":
    main()
