"""
统一配置加载与混合猫化调度。

混合策略（固定）：
  - 短句 → nekomimi 规则引擎（本地，含「主人」）
  - 长句 / 抽样 → ai_engine（需 API Key）
  - TRANSFORM_CACHE：预览与发送共用，避免重复请求
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ai_engine import AiConfig, resolve_api_key, transform_ai
from nekomimi import NekomimiConfig, _default_replacements, _should_skip, transform as transform_rules

DEFAULT_SUFFIXES = ("喵", "～喵", "喵～", "喵！")


class TransformCache:
    """预览与发送共用缓存，相同原文只调一次 API。"""

    def __init__(self, max_size: int = 128) -> None:
        self._max_size = max_size
        self._data: dict[str, str] = {}
        self._order: list[str] = []

    def _key(self, config: AppConfig, text: str) -> str:
        ai = config.ai
        rules = config.rules
        prompt_tag = hash(ai.system_prompt.strip())
        return (
            f"{ai.model}|{ai.base_url}|{ai.use_ai_chance}|{ai.min_length_for_ai}|"
            f"{rules.force_master}|{rules.master_chance}|{prompt_tag}|{text}"
        )

    def get(self, config: AppConfig, text: str) -> str | None:
        return self._data.get(self._key(config, text))

    def set(self, config: AppConfig, text: str, result: str) -> None:
        key = self._key(config, text)
        if key in self._data:
            self._order.remove(key)
        self._data[key] = result
        self._order.append(key)
        while len(self._order) > self._max_size:
            old = self._order.pop(0)
            self._data.pop(old, None)

    def clear(self) -> None:
        self._data.clear()
        self._order.clear()

    def __len__(self) -> int:
        return len(self._data)


TRANSFORM_CACHE = TransformCache()


@dataclass
class AppConfig:
    ai: AiConfig = field(default_factory=AiConfig)
    rules: NekomimiConfig = field(default_factory=NekomimiConfig)


def should_use_ai(text: str, ai: AiConfig) -> bool:
    """短句走规则；长句或低概率抽样才调 API。"""
    stripped = text.strip()
    if len(stripped) >= ai.min_length_for_ai:
        return True
    return random.random() < ai.use_ai_chance


def load_config(path: Path | str) -> AppConfig:
    p = Path(path)
    if not p.exists():
        return AppConfig()

    data = json.loads(p.read_text(encoding="utf-8"))
    ai_raw = data.get("ai", {})

    replacements = []
    for item in data.get("replacements", []):
        from nekomimi import WordReplacement

        replacements.append(
            WordReplacement(
                str(item["from"]),
                str(item["to"]),
                float(item.get("chance", 0.5)),
                bool(item.get("once", True)),
            )
        )

    rules = NekomimiConfig(
        mode="always",
        master_chance=float(data.get("master_chance", 0.72)),
        nya_end_chance=float(data.get("nya_end_chance", 0.78)),
        nya_per_sentence_chance=float(data.get("nya_per_sentence_chance", 0.55)),
        cute_particle_chance=float(data.get("cute_particle_chance", 0.22)),
        add_trailing_wave_chance=float(data.get("add_trailing_wave_chance", 0.2)),
        suffix_templates=list(data.get("suffix_templates", DEFAULT_SUFFIXES)),
        replacements=replacements or _default_replacements(),
        enable_master=bool(data.get("enable_master", True)),
        enable_nya=bool(data.get("enable_nya", True)),
        enable_replacements=bool(data.get("enable_replacements", True)),
        enable_particles=bool(data.get("enable_particles", True)),
        force_master=bool(data.get("force_master", True)),
        seed=data.get("seed"),
    )

    ai = AiConfig(
        api_key=str(ai_raw.get("api_key", "")),
        base_url=str(ai_raw.get("base_url", "https://api.deepseek.com")),
        model=str(ai_raw.get("model", "deepseek-chat")),
        timeout=float(ai_raw.get("timeout", 20)),
        temperature=float(ai_raw.get("temperature", 0.75)),
        fallback_to_rules=bool(ai_raw.get("fallback_to_rules", True)),
        system_prompt=str(ai_raw.get("system_prompt", "")),
        use_ai_chance=float(ai_raw.get("use_ai_chance", 0.12)),
        min_length_for_ai=int(ai_raw.get("min_length_for_ai", 22)),
    )

    return AppConfig(ai=ai, rules=rules)


def transform(
    text: str,
    config: AppConfig,
    on_log: Callable[[str], None] | None = None,
) -> str:
    """混合猫化：短句规则+主人，长句/抽样才调 AI；预览与发送共用缓存。"""
    if _should_skip(text):
        return text

    cached = TRANSFORM_CACHE.get(config, text)
    if cached is not None:
        if on_log:
            on_log("使用缓存（未重复调用 API）")
        return cached

    use_ai = bool(resolve_api_key(config.ai)) and should_use_ai(text, config.ai)

    if not use_ai:
        if on_log:
            on_log("规则猫化（未调用 API）")
        result = transform_rules(text, config.rules)
        TRANSFORM_CACHE.set(config, text, result)
        return result

    try:
        if on_log:
            on_log("AI 改写中…")
        result = transform_ai(text, config.ai)
        TRANSFORM_CACHE.set(config, text, result)
        return result
    except Exception as exc:
        if on_log:
            on_log(f"AI 失败: {exc}")
        if config.ai.fallback_to_rules:
            if on_log:
                on_log("已回退到规则猫化")
            result = transform_rules(text, config.rules)
            TRANSFORM_CACHE.set(config, text, result)
            return result
        return text


def preview_samples(config: AppConfig, on_log: Callable[[str], None] | None = None) -> list[tuple[str, str]]:
    samples = ("你好", "今天天气不错", "什么steam游戏", "我喜欢你", "还需要调试")
    return [(s, transform(s, config, on_log=on_log)) for s in samples]
