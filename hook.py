"""
微信 PC 版 Enter 键拦截与发送流程。

注意：
  - 使用 hook_key 同时拦截 Enter 的 KeyDown / KeyUp，避免微信重复发送
  - 用 Ctrl+X 剪切而非复制，确保输入框在猫化前被清空
  - Windows 下建议以管理员身份运行（keyboard 低层钩子）
"""

from __future__ import annotations

import ctypes
import time
from typing import Callable

import keyboard
import pyperclip

from app_config import AppConfig, transform

user32 = ctypes.windll.user32

COPY_PAUSE = 0.12
PASTE_PAUSE = 0.10


def is_wechat_foreground() -> bool:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value
    return "微信" in title or "WeChat" in title.lower()


def _hotkey(*keys: str, pause: float = 0.05) -> None:
    for key in keys[:-1]:
        keyboard.press(key)
    keyboard.press(keys[-1])
    keyboard.release(keys[-1])
    for key in reversed(keys[:-1]):
        keyboard.release(key)
    time.sleep(pause)


def _cut_input_text() -> str:
    """剪切输入框内容（清空输入框，避免与后续发送冲突）。"""
    for attempt in range(3):
        _hotkey("ctrl", "a", pause=0.04)
        _hotkey("ctrl", "x", pause=COPY_PAUSE + attempt * 0.03)
        text = pyperclip.paste()
        if text is not None and text != "":
            return text
    return pyperclip.paste() or ""


def _paste_input_text(text: str) -> None:
    pyperclip.copy(text)
    _hotkey("ctrl", "v", pause=PASTE_PAUSE)


def catify_and_send(config: AppConfig, on_log: Callable[[str], None] | None = None) -> None:
    """剪切输入框 → 猫化 → 粘贴 → 发送（只发一条）。"""
    def log(msg: str) -> None:
        if on_log:
            on_log(msg)

    saved_clip = pyperclip.paste()
    keyboard.block_key("enter")
    try:
        original = _cut_input_text()

        if not original.strip():
            return

        converted = transform(original, config, on_log=log)
        _paste_input_text(converted)

        if converted != original:
            preview_old = original[:20] + ("…" if len(original) > 20 else "")
            preview_new = converted[:30] + ("…" if len(converted) > 30 else "")
            log(f"猫化: {preview_old} → {preview_new}")

        time.sleep(0.05)
        keyboard.send("enter")
    except Exception as exc:
        if on_log:
            on_log(f"处理失败: {exc}")
        keyboard.send("enter")
    finally:
        keyboard.unblock_key("enter")
        time.sleep(0.03)
        try:
            pyperclip.copy(saved_clip)
        except Exception:
            pass


class WeChatCatHook:
    def __init__(self, config: AppConfig, on_log: Callable[[str], None] | None = None):
        self.config = config
        self.on_log = on_log
        self._enabled = True
        self._enter_hook = None
        self._processing = False
        self._block_next_enter_up = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def toggle(self) -> bool:
        self._enabled = not self._enabled
        return self._enabled

    def _on_enter_key(self, event: keyboard.KeyboardEvent) -> bool:
        """
        hook_key + suppress：return False 拦截按键。
        on_press_key 会放行 Enter 的 KeyUp，微信可能在 KeyUp 时发出原文 → 必须拦截 KeyUp。
        """
        if event.event_type == keyboard.KEY_UP:
            if self._block_next_enter_up:
                self._block_next_enter_up = False
                return False
            return True

        # --- KEY_DOWN ---
        if self._processing:
            if self.on_log:
                self.on_log("上一条还在改写中，请稍候…")
            self._block_next_enter_up = True
            return False

        if keyboard.is_pressed("shift"):
            self._block_next_enter_up = True
            keyboard.send("shift+enter")
            return False

        if not self._enabled or not is_wechat_foreground():
            return True

        self._processing = True
        self._block_next_enter_up = True
        try:
            catify_and_send(self.config, self.on_log)
        finally:
            self._processing = False
        return False

    def start(self) -> None:
        self._enter_hook = keyboard.hook_key("enter", self._on_enter_key, suppress=True)

    def stop(self) -> None:
        if self._enter_hook is not None:
            keyboard.unhook(self._enter_hook)
            self._enter_hook = None
