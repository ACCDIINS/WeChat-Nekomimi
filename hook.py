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
kernel32 = ctypes.windll.kernel32

SW_RESTORE = 9

COPY_PAUSE = 0.12
PASTE_PAUSE = 0.10
FOCUS_PAUSE = 0.10


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def is_wechat_foreground() -> bool:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    title = _window_title(hwnd)
    return "微信" in title or "WeChat" in title.lower()


def _find_wechat_hwnd() -> int:
    found: list[int] = []

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if "微信" in title or "WeChat" in title.lower():
            found.append(hwnd)
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_callback)
    user32.EnumWindows(enum_proc, 0)
    return found[0] if found else 0


def _restore_wechat_focus(wechat_hwnd: int) -> bool:
    """AI 改写耗时时焦点可能跑到 CMD，粘贴前须切回微信。"""
    hwnd = wechat_hwnd or _find_wechat_hwnd()
    if not hwnd:
        return False

    user32.ShowWindow(hwnd, SW_RESTORE)
    foreground = user32.GetForegroundWindow()
    if foreground == hwnd:
        return True

    fg_thread = user32.GetWindowThreadProcessId(foreground, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    current_thread = kernel32.GetCurrentThreadId()

    if fg_thread:
        user32.AttachThreadInput(current_thread, fg_thread, True)
    if target_thread:
        user32.AttachThreadInput(current_thread, target_thread, True)
    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    finally:
        if target_thread:
            user32.AttachThreadInput(current_thread, target_thread, False)
        if fg_thread:
            user32.AttachThreadInput(current_thread, fg_thread, False)

    time.sleep(FOCUS_PAUSE)
    return user32.GetForegroundWindow() == hwnd


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


def catify_and_send(
    config: AppConfig,
    on_log: Callable[[str], None] | None = None,
    *,
    hook: WeChatCatHook | None = None,
) -> None:
    """剪切输入框 → 猫化 → 粘贴 → 发送（只发一条）。"""
    def log(msg: str) -> None:
        if on_log:
            on_log(msg)

    saved_clip = pyperclip.paste()
    wechat_hwnd = user32.GetForegroundWindow()
    try:
        original = _cut_input_text()

        if not original.strip():
            return

        converted = transform(
            original,
            config,
            on_log=log,
            force_ai=hook.force_ai if hook is not None else False,
        )

        if not _restore_wechat_focus(wechat_hwnd):
            log("无法切回微信窗口，请手动点回微信后重试")
            _paste_input_text(original)
            if hook is not None:
                hook._suppress_enter_remaining = 2
            keyboard.send("enter")
            return

        _paste_input_text(converted)

        if converted != original:
            preview_old = original[:20] + ("…" if len(original) > 20 else "")
            preview_new = converted[:30] + ("…" if len(converted) > 30 else "")
            log(f"猫化: {preview_old} → {preview_new}")

        time.sleep(0.05)
        _restore_wechat_focus(wechat_hwnd)
        if hook is not None:
            hook._suppress_enter_remaining = 2
        keyboard.send("enter")
    except Exception as exc:
        if on_log:
            on_log(f"处理失败: {exc}")
        _restore_wechat_focus(wechat_hwnd)
        if hook is not None:
            hook._suppress_enter_remaining = 2
        keyboard.send("enter")
    finally:
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
        self._suppress_enter_remaining = 0
        self._force_ai = config.ai.force_ai_on_send

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def force_ai(self) -> bool:
        return self._force_ai

    def toggle(self) -> bool:
        self._enabled = not self._enabled
        return self._enabled

    def toggle_force_ai(self) -> bool:
        self._force_ai = not self._force_ai
        return self._force_ai

    def sync_from_config(self, config: AppConfig) -> None:
        self.config = config
        self._force_ai = config.ai.force_ai_on_send

    def _on_enter_key(self, event: keyboard.KeyboardEvent) -> bool:
        """
        hook_key + suppress：return False 拦截按键。
        on_press_key 会放行 Enter 的 KeyUp，微信可能在 KeyUp 时发出原文 → 必须拦截 KeyUp。
        """
        if self._suppress_enter_remaining > 0:
            self._suppress_enter_remaining -= 1
            return False

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
            catify_and_send(self.config, self.on_log, hook=self)
        finally:
            self._processing = False
        return False

    def start(self) -> None:
        if self._enter_hook is None:
            self._enter_hook = keyboard.hook_key("enter", self._on_enter_key, suppress=True)

    def stop(self) -> None:
        if self._enter_hook is None:
            return
        remover = self._enter_hook
        self._enter_hook = None
        try:
            remover()
        except KeyError:
            pass
