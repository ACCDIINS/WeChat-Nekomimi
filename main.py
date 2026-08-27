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

from ai_engine import API_KEY_EMPTY_HINT, has_api_key
from app_config import TRANSFORM_CACHE, load_config, transform
from ai_dataset import dataset_count, invalidate_lookup_cache
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


def _print_cmd_line(cmd: str, desc: str, cmd_width: int = 10) -> None:
    """命令帮助行：按终端显示宽度对齐命令列与说明。"""
    gap = cmd_width - _display_width(cmd)
    if gap < 1:
        gap = 1
    print(f"\t{cmd}{' ' * gap}{desc}")


def _print_banner() -> None:
    bar = "─" * _BANNER_INNER_WIDTH
    lines = ("微信猫娘助手", "Nekomimi for WeChat")
    print()
    print(f"  ╭{bar}╮")
    for line in lines:
        print(f"  │{_pad_center(line, _BANNER_INNER_WIDTH)}│")
    print(f"  ╰{bar}╯")
    print()


PROMPT = "命令> "
_console_lock = threading.Lock()
_at_prompt = threading.Event()


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    with _console_lock:
        if _at_prompt.is_set():
            sys.stdout.write("\n")
        print(f"[{ts}] {msg}", flush=True)
        if _at_prompt.is_set():
            sys.stdout.write(PROMPT)
            sys.stdout.flush()


def _print_help() -> None:
    print("\t窗口命令有下面这些喵~\n")
    rows = (
        ("m", "猫娘模式开关"),
        ("f", "微信发送强制使用AI开关"),
        ("t", "规则预览（剪贴板）"),
        ("t 文本", "规则预览（指定文本）"),
        ("a", "AI 预览（剪贴板，需API Key）"),
        ("a 文本", "AI 预览（指定文本）"),
        ("s", "查看当前状态"),
        ("r", "重新加载config.json"),
        ("q", "退出程序"),
        ("?", "显示帮助"),
    )
    for cmd, desc in rows:
        _print_cmd_line(cmd, desc)
    print("\n")
    print("-" * 50)


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

    if not has_api_key(config.ai):
        log(API_KEY_EMPTY_HINT)
        log("长句与 a 命令 AI 预览将仅使用规则猫化")
    log("猫娘模式已开启")

    stop = threading.Event()

    def reload_config() -> None:
        nonlocal config
        config = load_config(CONFIG_PATH)
        hook.sync_from_config(config)
        TRANSFORM_CACHE.clear()
        invalidate_lookup_cache()
        log("已重载 config.json（缓存已清空）")
        if not has_api_key(config.ai):
            log(API_KEY_EMPTY_HINT)

    def preview_text(text: str, *, force_ai: bool = False) -> None:
        if not text.strip():
            hint = "a 你好" if force_ai else "t 你好"
            log(f"请输入要预览的文本，例如: {hint}")
            return
        log(f"原文: {text}")
        log(f"猫化: {transform(text, config, on_log=log, force_ai=force_ai)}")

    def preview_clipboard(*, force_ai: bool = False) -> None:
        import pyperclip

        preview_text(pyperclip.paste(), force_ai=force_ai)

    def show_status() -> None:
        log(f"猫娘模式: {'开启' if hook.enabled else '关闭'}")
        log(f"微信强制 AI: {'开启' if hook.force_ai else '关闭'}")
        log(f"主人: 强制={'开' if config.rules.force_master else '关'} · 概率 {config.rules.master_chance:.0%}")
        log(f"喵: 句末 {config.rules.nya_end_chance:.0%} · 分句 {config.rules.nya_per_sentence_chance:.0%}")
        log(f"AI: 超过 {config.ai.min_length_for_ai} 字必调 · 短句抽样 {config.ai.use_ai_chance:.0%}")
        if has_api_key(config.ai):
            log(f"API Key: 已配置 · 模型 {config.ai.model}")
        else:
            log(API_KEY_EMPTY_HINT)
        log(f"预览缓存: {len(TRANSFORM_CACHE)} 条")
        log(f"AI 语料: {dataset_count()} 条（data/ai_rewrites.jsonl）")

    def toggle() -> None:
        on = hook.toggle()
        log("猫娘模式已开启" if on else "猫娘模式已关闭")

    def toggle_force_ai() -> None:
        on = hook.toggle_force_ai()
        if on and not has_api_key(config.ai):
            log(API_KEY_EMPTY_HINT)
        log("微信发送强制 AI 已开启" if on else "微信发送强制 AI 已关闭")

    def quit_app() -> None:
        if stop.is_set():
            return
        log("正在退出…")
        hook.stop()
        stop.set()

    def command_loop() -> None:
        while not stop.is_set():
            _at_prompt.set()
            try:
                try:
                    raw = input(PROMPT).strip()
                except (EOFError, KeyboardInterrupt):
                    quit_app()
                    break
            finally:
                _at_prompt.clear()

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
            elif cmd in ("f", "forceai"):
                toggle_force_ai()
            elif cmd in ("t", "preview"):
                if arg:
                    preview_text(arg)
                else:
                    preview_clipboard()
            elif cmd in ("a", "ai"):
                if arg:
                    preview_text(arg, force_ai=True)
                else:
                    preview_clipboard(force_ai=True)
            elif cmd in ("s", "status"):
                show_status()
            elif cmd in ("r", "reload"):
                reload_config()
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
