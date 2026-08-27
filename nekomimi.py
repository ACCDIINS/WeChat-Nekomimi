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


# 纯笑声：不加主人，随机保留或改成猫娘笑
_LAUGHTER_PATTERN = re.compile(
    r"^(?:"
    r"哈{2,}|呵{2,}|嘿{2,}|嘻{2,}|"
    r"233+|"
    r"[wW]{2,}|"
    r"[hH]{2,}"
    r")$",
)
_LAUGHTER_OUTPUTS = ("哈哈哈", "笑死我了喵", "笑死人家了喵")


def try_transform_laughter(text: str, config: NekomimiConfig | None = None) -> str | None:
    """纯「哈哈哈」类笑声 → 哈哈哈 / 笑死我了喵 / 笑死人家了喵。"""
    stripped = text.strip()
    if not _LAUGHTER_PATTERN.fullmatch(stripped):
        return None
    rng = _rng(config or NekomimiConfig())
    trailing = text[len(text.rstrip()) :]
    return rng.choice(_LAUGHTER_OUTPUTS) + trailing


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


# 「我知道/我想…」里的「我」不改成「人家」
_PROTECTED_I_PHRASES = (
    "我知道",
    "我想",
    "我要",
    "我会",
    "我是",
    "我在",
    "我来",
    "我给",
    "我能",
    "我不",
    "我自己",
)


def _apply_replacements(text: str, rules: list[WordReplacement], rng: random.Random) -> str:
    result = text
    sorted_rules = sorted(rules, key=lambda r: len(r.src), reverse=True)
    for rule in sorted_rules:
        if rule.src not in result:
            continue
        if rule.dst in result:
            continue
        if rule.src == "我" and any(p in result for p in _PROTECTED_I_PHRASES):
            continue
        if rng.random() > rule.chance:
            continue
        count = 1 if rule.once else -1
        result = result.replace(rule.src, rule.dst, count)
    return result


# 应答/礼貌语后接逗号时，优先「好的主人，…」而非句尾「…，主人」
_LEAD_PHRASES = ("没问题", "对不起", "谢谢", "你好", "好的", "可以", "行")


def _try_insert_master_natural(text: str) -> str | None:
    """在常见应答语后自然插入「主人」，匹配则返回新文本，否则 None。"""
    if "主人" in text:
        return None
    for src in _LEAD_PHRASES:
        idx = text.find(src)
        if idx == -1:
            continue
        dst = src + "主人"
        if dst in text:
            continue
        after = text[idx + len(src) :]
        if not after:
            return text.replace(src, dst, 1)
        if after[0] in "，,、；;：:":
            return text.replace(src, dst, 1)
        # 「你好呀」等：短语后紧跟语气词，不用「你好主人呀」
        if src == "你好" and after[0] in CUTE_ENDINGS:
            return None
    return None


def _normalize_master_position(text: str) -> str:
    """纠正「…，主人」语序（含短句「喜欢你，主人喵」）。"""
    for src in _LEAD_PHRASES:
        if not text.startswith(src):
            continue
        pos = text.rfind("，主人")
        if pos <= len(src):
            continue
        middle = text[len(src) : pos]
        if not middle.startswith("，"):
            continue
        suffix = text[pos + len("，主人") :]
        return f"{src}主人{middle}{suffix}"

    pos = text.rfind("，主人")
    if pos <= 0:
        return text
    before = text[:pos]
    after = text[pos + len("，主人") :]
    if "主人" in before or "，" in before:
        return text
    return f"主人，{before}{after}"


def _master_prefix(text: str, rng: random.Random) -> str:
    return rng.choice(("主人，", "主人~")) + text


def _insert_master(text: str, chance: float, rng: random.Random) -> str:
    if "主人" in text or rng.random() > chance:
        return text

    natural = _try_insert_master_natural(text)
    if natural is not None:
        return natural

    # 无逗号短句一律句首「主人，」（避免「喜欢你，主人喵」）
    if "，" not in text and "," not in text:
        return _master_prefix(text, rng)

    # 含逗号也优先句首，不再随机句尾
    return _master_prefix(text, rng)


def _ensure_master(text: str, rng: random.Random) -> str:
    """保证句中出现「主人」称呼（自然位置）。"""
    if "主人" in text:
        return text
    natural = _try_insert_master_natural(text)
    if natural is not None:
        return natural
    return _master_prefix(text, rng)


def _pick_suffix(config: NekomimiConfig, rng: random.Random) -> str:
    templates = [s for s in config.suffix_templates if s]
    return rng.choice(templates or list(DEFAULT_SUFFIXES))


def _already_has_nya(clause: str) -> bool:
    """句末已有「喵」或「～喵」类后缀时不再叠加。"""
    core = clause.rstrip()
    if not core:
        return False
    if core.endswith("喵"):
        return True
    return core.endswith(("～", "~")) and "喵" in core[-4:]


def _append_nya_to_clause(clause: str, chance: float, config: NekomimiConfig, rng: random.Random) -> str:
    if rng.random() > chance:
        return clause

    core = clause.rstrip()
    if not core or _already_has_nya(core):
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
    core = text.rstrip()
    # 句末已有「喵」时不再叠「呢」「～」，避免「喵呢！」
    if core.endswith("喵") or core.endswith(("喵！", "喵～", "～喵")):
        return text

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


# 常见短句：规则难做语义改写，用语料未命中时的兜底模板（含「喵」）
_EXACT_PHRASE_VARIANTS: dict[str, tuple[str, ...]] = {
    "你好": ("主人好呀喵～", "主人好喵～", "喵～主人好呀"),
    "在吗": ("主人，在的喵～", "在呢主人喵", "人家在呢主人"),
    "晚安": ("主人晚安喵～", "晚安主人喵～", "人家祝主人晚安喵"),
    "早安": ("主人早呀喵～", "早呀主人喵～"),
    "早上好": ("主人早呀喵～", "早呀主人喵～"),
    "我喜欢你": ("人家最喜欢主人了喵～", "人家也最喜欢主人了喵～"),
    "想你了": ("人家想主人了喵～", "想主人了喵～"),
    "对不起": ("对不起主人喵～", "人家错了主人喵～"),
    "谢谢": ("谢谢主人喵～", "多谢主人喵～"),
}


def _try_exact_phrase(text: str, rng: random.Random) -> str | None:
    """整句命中常见口语时直接返回猫娘句式（跳过随机叠词规则）。"""
    key = text.strip()
    variants = _EXACT_PHRASE_VARIANTS.get(key)
    if not variants:
        return None
    trailing = text[len(text.rstrip()) :]
    return rng.choice(variants) + trailing


def transform(text: str, config: NekomimiConfig | None = None) -> str:
    """将普通聊天文本转为猫娘风格。"""
    if config is None:
        config = NekomimiConfig()

    rng = _rng(config)

    if _should_skip(text):
        return text

    original_trailing = text[len(text.rstrip()) :]
    body = text.rstrip()

    exact = _try_exact_phrase(text, rng)
    if exact is not None:
        return exact

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

    if config.enable_master:
        body = _normalize_master_position(body)

    return body + original_trailing


