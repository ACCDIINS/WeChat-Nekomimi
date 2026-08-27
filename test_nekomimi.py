"""单元测试（无需微信客户端与真实 API Key）。"""

import re
from pathlib import Path
from unittest.mock import patch

from ai_engine import AiConfig, _clean_ai_output
from app_config import AppConfig, load_config, transform
from nekomimi import NekomimiConfig, transform as transform_rules


def test_skip_empty_and_url():
    assert transform("", AppConfig()) == ""
    assert transform("https://example.com", AppConfig()) == "https://example.com"


def test_rules_deterministic_with_seed():
    cfg = AppConfig(
        rules=NekomimiConfig(seed=42, master_chance=1.0, nya_end_chance=1.0, enable_replacements=False),
    )
    a = transform("你好！", cfg)
    b = transform("你好！", cfg)
    assert a == b
    assert "喵" in a or "主人" in a


def test_master_not_in_word_middle():
    cfg = AppConfig(
        rules=NekomimiConfig(seed=99, master_chance=1.0, nya_end_chance=0.0, enable_replacements=False),
    )
    for seed in range(100):
        cfg.rules.seed = seed
        result = transform("今天天气不错！", cfg)
        assert "主人" in result
        assert "天主人" not in result


def test_clean_ai_output():
    assert _clean_ai_output('"你好喵"', "你好") == "你好喵"


def test_ai_transform_mock():
    from app_config import TRANSFORM_CACHE

    TRANSFORM_CACHE.clear()
    cfg = AppConfig(
        ai=AiConfig(api_key="test-key", model="deepseek-chat", use_ai_chance=1.0, min_length_for_ai=0),
    )
    fake_response = {"choices": [{"message": {"content": "主人好呀喵～"}}]}

    with patch("ai_engine.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            __import__("json").dumps(fake_response).encode()
        )
        first = transform("你好", cfg)
        second = transform("你好", cfg)
        assert first == second == "主人好呀喵～"
        assert mock_urlopen.call_count == 1


def test_short_text_uses_rules_with_master():
    from app_config import TRANSFORM_CACHE

    TRANSFORM_CACHE.clear()
    cfg = AppConfig(
        ai=AiConfig(api_key="test-key", use_ai_chance=0.0, min_length_for_ai=999),
        rules=NekomimiConfig(seed=1, force_master=True, enable_replacements=False),
    )
    with patch("ai_engine.urllib.request.urlopen") as mock_urlopen:
        result = transform("测试", cfg)
        assert "主人" in result
        mock_urlopen.assert_not_called()


def test_ai_fallback_to_rules():
    from app_config import TRANSFORM_CACHE

    TRANSFORM_CACHE.clear()
    cfg = AppConfig(
        ai=AiConfig(api_key="bad", use_ai_chance=1.0, min_length_for_ai=0, fallback_to_rules=True),
        rules=NekomimiConfig(
            seed=1,
            enable_master=False,
            enable_nya=False,
            enable_particles=False,
            enable_replacements=True,
        ),
    )
    from nekomimi import WordReplacement

    cfg.rules.replacements = [WordReplacement("我", "人家", 1.0, True)]

    with patch("app_config.transform_ai", side_effect=RuntimeError("network")):
        result = transform("我想你了", cfg)
        assert "人家" in result


def test_force_master():
    cfg = NekomimiConfig(
        seed=1,
        force_master=True,
        enable_master=True,
        enable_nya=False,
        enable_replacements=False,
        enable_particles=False,
        master_chance=0.0,
    )
    assert "主人" in transform_rules("好的", cfg)


def test_greeting_with_particle_natural_master():
    """「你好呀」不应变成「你好主人呀哦」。"""
    cfg = NekomimiConfig(
        seed=20260827,
        master_chance=1.0,
        nya_end_chance=1.0,
        enable_replacements=False,
        enable_particles=False,
    )
    result = transform_rules("你好呀", cfg)
    assert "你好主人" not in result
    assert "主人" in result
    assert not result.endswith("呀哦")
    assert result.startswith("主人")


def test_load_config_file():
    example = Path(__file__).with_name("config.example.json")
    cfg = load_config(example)
    assert cfg.ai.model
    assert cfg.rules.force_master


if __name__ == "__main__":
    test_skip_empty_and_url()
    test_rules_deterministic_with_seed()
    test_master_not_in_word_middle()
    test_clean_ai_output()
    test_ai_transform_mock()
    test_short_text_uses_rules_with_master()
    test_ai_fallback_to_rules()
    test_force_master()
    test_greeting_with_particle_natural_master()
    test_load_config_file()
    print("OK")
