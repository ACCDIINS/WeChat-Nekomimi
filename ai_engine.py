"""
OpenAI 兼容 API 猫娘改写引擎。

支持任何实现 POST /v1/chat/completions 的服务商（DeepSeek、Kimi、通义等）。
密钥来源（优先级从高到低）：
  1. 环境变量 NEKOMIMI_API_KEY
  2. config.json → ai.api_key
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

DEFAULT_SYSTEM_PROMPT = """你是微信聊天「猫娘语气」改写器。把用户原句改写成自然、可爱的猫娘口吻。

硬性要求：
1. 只输出改写后的单条消息正文，不要解释、不要引号、不要 markdown
2. 必须保留原意，专有名词（英文、游戏名、品牌、数字）原样保留
3. 必须称呼对方为「主人」（至少出现一次，自然嵌入，不要生硬堆砌）
4. 常用「人家」自称，句末加「喵」或「～」，整体像猫娘说话
5. 禁止在词语中间插入「主人」或「喵」
6. 长度与原文接近，不要明显变长
7. 链接、验证码、命令类文本原样返回"""


@dataclass
class AiConfig:
    """AI 相关配置，字段说明见 docs/CONFIG.md。"""

    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    timeout: float = 20.0
    temperature: float = 0.75
    fallback_to_rules: bool = True
    system_prompt: str = ""
    # 混合模式下：短句默认不调 API，仅长句或随机抽样才调
    use_ai_chance: float = 0.12
    min_length_for_ai: int = 22


def resolve_api_key(config: AiConfig) -> str:
    """读取 API Key；勿将返回值写入日志。"""
    return (os.environ.get("NEKOMIMI_API_KEY") or config.api_key or "").strip()


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _clean_ai_output(text: str, original: str) -> str:
    result = text.strip()
    if result.startswith("```"):
        result = re.sub(r"^```[\w]*\n?", "", result)
        result = re.sub(r"\n?```$", "", result).strip()
    for wrap in ('"', "'", "「", "」", "『", "』"):
        if len(result) >= 2 and result.startswith(wrap) and result.endswith(wrap):
            result = result[1:-1].strip()
    if result.startswith(("改写：", "改写:", "输出：", "输出:")):
        result = re.split(r"[:：]", result, maxsplit=1)[1].strip()
    # AI 偶尔返回空或过短，回退原文
    if not result or (len(original) > 4 and len(result) < len(original) * 0.3):
        return original
    return result


def transform_ai(text: str, config: AiConfig) -> str:
    api_key = resolve_api_key(config)
    if not api_key:
        raise ValueError("未配置 API Key，请在 config.json 的 ai.api_key 填写，或设置环境变量 NEKOMIMI_API_KEY")

    system = config.system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
    }

    req = urllib.request.Request(
        _chat_completions_url(config.base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=config.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {exc.code}: {detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络错误: {exc.reason}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"API 响应格式异常: {body}") from exc

    return _clean_ai_output(str(content), text)
