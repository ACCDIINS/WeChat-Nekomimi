"""
纯本地猫娘规则引擎（无网络、无 AI）。

负责：词库替换、插入「主人」、句末「喵」、语气词。
配置项见 NekomimiConfig 与 docs/CONFIG.md。
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["punctuation", "always"]

END_PUNCT = "。！？!?~～…"
TRAILING_PUNCT = re.compile(r"([。！？!?~～…]+)$")
DEFAULT_SUFFIXES = ("喵", "～喵", "喵～", "喵！")
# 句末已有这些语气词时不再叠后缀（避免「你好呀哦」）
CUTE_ENDINGS = ("喵", "～", "~", "呀", "哦", "呢", "嘛", "啦", "哒", "呐", "哇", "哈")

DEFAULT_REPLACEMENTS: tuple[dict[str, object], ...] = (
    {"from": "为什么", "to": "为什么呀", "chance": 0.55, "once": True},
    {"from": "什么", "to": "什么呀", "chance": 0.45, "once": True},
    {"from": "不要", "to": "不要嘛", "chance": 0.45, "once": True},
    {"from": "可以吗", "to": "可以嘛", "chance": 0.5, "once": True},
    {"from": "好不好", "to": "好嘛", "chance": 0.45, "once": True},
    {"from": "好的", "to": "好哒", "chance": 0.4, "once": True},
    {"from": "好吧", "to": "好嘛", "chance": 0.4, "once": True},
    {"from": "没有", "to": "没有啦", "chance": 0.35, "once": True},
    {"from": "不知道", "to": "不知道啦", "chance": 0.35, "once": True},
    {"from": "我", "to": "人家", "chance": 0.28, "once": True},
    {"from": "你", "to": "主人", "chance": 0.12, "once": True},
    {"from": "嗯", "to": "嗯嗯", "chance": 0.25, "once": True},
    {"from": "哦", "to": "哦～", "chance": 0.2, "once": True},
    {"from": "啥", "to": "啥子", "chance": 0.3, "once": True},
)


@dataclass
class WordReplacement:
    src: str
    dst: str
    chance: float = 0.5
    once: bool = True


def _default_replacements() -> list[WordReplacement]:
    return [
        WordReplacement(str(r["from"]), str(r["to"]), float(r.get("chance", 0.5)), bool(r.get("once", True)))
        for r in DEFAULT_REPLACEMENTS
    ]


@dataclass
class NekomimiConfig:
    """参考 QQ 猫娘输入法的可配置项。"""

    mode: Mode = "always"
    master_chance: float = 0.72
    nya_end_chance: float = 0.78
    nya_per_sentence_chance: float = 0.55
    cute_particle_chance: float = 0.18
    add_trailing_wave_chance: float = 0.15
    suffix_templates: list[str] = field(default_factory=lambda: list(DEFAULT_SUFFIXES))
    replacements: list[WordReplacement] = field(default_factory=_default_replacements)
    enable_master: bool = True
    enable_nya: bool = True
    enable_replacements: bool = True
    enable_particles: bool = True
    force_master: bool = True
    seed: int | None = None


def _rng(config: NekomimiConfig) -> random.Random:
    return random.Random(config.seed) if config.seed is not None else random


def _should_skip(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith(("/", "http://", "https://", "www.")):
        return True
    if stripped.count("喵") >= 3:
        return True
    # 纯数字/验证码类消息不改
    if re.fullmatch(r"[\d\s\-+]+", stripped):
        return True
    return False


def _has_punctuation(text: str) -> bool:
    return any(ch in END_PUNCT for ch in text) or text.rstrip().endswith(tuple("，,、；;：:"))


def _split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in END_PUNCT:
            parts.append("".join(buf))
            buf = []
    if buf:
        parts.append("".join(buf))
    return parts if parts else [text]


def _apply_replacements(text: str, rules: list[WordReplacement], rng: random.Random) -> str:
    result = text
    sorted_rules = sorted(rules, key=lambda r: len(r.src), reverse=True)
    for rule in sorted_rules:
        if rule.src not in result:
            continue
        if rule.dst in result:
            continue
        if rng.random() > rule.chance:
            continue
        count = 1 if rule.once else -1
        result = result.replace(rule.src, rule.dst, count)
    return result


def _insert_master(text: str, chance: float, rng: random.Random) -> str:
    if "主人" in text or rng.random() > chance:
        return text

    mode = rng.choice(("prefix", "suffix", "after_phrase", "after_comma"))

    if mode == "prefix":
        return rng.choice(("主人，", "主人~")) + text

    if mode == "suffix":
        m = TRAILING_PUNCT.search(text)
        if m:
            punct = m.group(1)
            core = text[: m.start()].rstrip("，,、")
            return f"{core}，主人{punct}"
        return text.rstrip("，,、") + "，主人"

    if mode == "after_phrase":
        phrases = (
            ("好的", "好的主人"),
            ("谢谢", "谢谢主人"),
            ("你好", "你好主人"),
            ("对不起", "对不起主人"),
            ("没问题", "没问题主人"),
        )
        phrase_list = list(phrases)
        rng.shuffle(phrase_list)
        for src, dst in phrase_list:
            idx = text.find(src)
            if idx == -1 or dst in text:
                continue
            rest = text[idx + len(src) :].lstrip()
            # 短语后还有正文（如「你好呀」）→ 用前缀，避免「你好主人呀」
            if rest and rest[0] not in END_PUNCT and rest[0] not in "，,、；;：:":
                return rng.choice(("主人，", "主人~")) + text
            return text.replace(src, dst, 1)
        m = TRAILING_PUNCT.search(text)
        if m:
            punct = m.group(1)
            core = text[: m.start()].rstrip("，,、")
            return f"{core}，主人{punct}"
        return text.rstrip("，,、") + "，主人"

    if mode == "after_comma":
        for sep in ("，", ",", "、"):
            idx = text.find(sep)
            if idx != -1:
                return text[: idx + len(sep)] + "主人" + text[idx + len(sep) :]
        return rng.choice(("主人，", "主人~")) + text

    return text


def _ensure_master(text: str, rng: random.Random) -> str:
    """保证句中出现「主人」称呼（自然位置）。"""
    if "主人" in text:
        return text
    if len(text) <= 10:
        return rng.choice(("主人，", "主人~", "主人 ")) + text
    m = TRAILING_PUNCT.search(text)
    if m:
        punct = m.group(1)
        core = text[: m.start()].rstrip("，,、")
        return f"{core}，主人{punct}"
    return text.rstrip("，,、") + "，主人"


def _pick_suffix(config: NekomimiConfig, rng: random.Random) -> str:
    templates = [s for s in config.suffix_templates if s]
    return rng.choice(templates or list(DEFAULT_SUFFIXES))


def _append_nya_to_clause(clause: str, chance: float, config: NekomimiConfig, rng: random.Random) -> str:
    if rng.random() > chance:
        return clause

    core = clause.rstrip()
    if not core or core.endswith(CUTE_ENDINGS):
        return clause

    trailing_ws = clause[len(core) :]
    suffix = _pick_suffix(config, rng)
    m = TRAILING_PUNCT.search(core)
    if m:
        punct = m.group(1)
        body = core[: m.start()].rstrip()
        if not body:
            return clause
        return body + suffix + punct + trailing_ws

    return core + suffix + trailing_ws


def _append_nya(text: str, chance: float, per_sentence: float, config: NekomimiConfig, rng: random.Random) -> str:
    sentences = _split_sentences(text.rstrip())
    trailing_ws = text[len(text.rstrip()) :]

    if len(sentences) <= 1:
        body = _append_nya_to_clause(text.rstrip(), chance, config, rng)
        return body + trailing_ws

    converted = [_append_nya_to_clause(s, per_sentence, config, rng) for s in sentences]
    return "".join(converted) + trailing_ws


def _cute_particles(text: str, chance: float, wave_chance: float, rng: random.Random) -> str:
    if rng.random() > chance:
        result = text
    else:
        result = text
        if rng.random() < 0.12 and "呢" not in result and len(result) < 40:
            m = TRAILING_PUNCT.search(result.rstrip())
            if m:
                punct = m.group(1)
                core = result[: m.start()].rstrip()
                result = core + "呢" + punct + result[len(result.rstrip()) :]
            elif not result.rstrip().endswith("呢"):
                result = result.rstrip() + "呢" + result[len(result.rstrip()) :]

    if rng.random() < wave_chance and not result.rstrip().endswith(("～", "~", "喵", "喵～", "～喵")):
        m = TRAILING_PUNCT.search(result.rstrip())
        if m:
            punct = m.group(1)
            core = result[: m.start()].rstrip()
            result = core + "～" + punct + result[len(result.rstrip()) :]
        else:
            result = result.rstrip() + "～" + result[len(result.rstrip()) :]

    return result


def transform(text: str, config: NekomimiConfig | None = None) -> str:
    """将普通聊天文本转为猫娘风格。"""
    if config is None:
        config = NekomimiConfig()

    rng = _rng(config)

    if _should_skip(text):
        return text

    original_trailing = text[len(text.rstrip()) :]
    body = text.rstrip()

    # 标点触发模式：无标点时只做轻量替换，不加喵/主人
    punctuation_mode = config.mode == "punctuation"
    if punctuation_mode and not _has_punctuation(body):
        if config.enable_replacements:
            body = _apply_replacements(body, config.replacements, rng)
        return body + original_trailing

    if config.enable_replacements:
        body = _apply_replacements(body, config.replacements, rng)

    if config.enable_master:
        body = _insert_master(body, config.master_chance, rng)

    if config.enable_nya:
        body = _append_nya(body, config.nya_end_chance, config.nya_per_sentence_chance, config, rng)

    if config.enable_particles:
        body = _cute_particles(body, config.cute_particle_chance, config.add_trailing_wave_chance, rng)

    if config.enable_master and config.force_master:
        body = _ensure_master(body, rng)

    return body + original_trailing


def preview_samples_rules(config: NekomimiConfig | None = None) -> list[tuple[str, str]]:
    """内置示例，便于在 CMD 里预览效果。"""
    cfg = config or NekomimiConfig()
    samples = ("你好", "今天天气不错", "好的没问题", "你在干嘛", "为什么呀")
    fixed = NekomimiConfig(
        mode=cfg.mode,
        master_chance=cfg.master_chance,
        nya_end_chance=cfg.nya_end_chance,
        nya_per_sentence_chance=cfg.nya_per_sentence_chance,
        cute_particle_chance=cfg.cute_particle_chance,
        add_trailing_wave_chance=cfg.add_trailing_wave_chance,
        suffix_templates=cfg.suffix_templates,
        replacements=cfg.replacements,
        enable_master=cfg.enable_master,
        enable_nya=cfg.enable_nya,
        enable_replacements=cfg.enable_replacements,
        enable_particles=cfg.enable_particles,
        seed=20260827,
    )
    return [(s, transform(s, fixed)) for s in samples]
