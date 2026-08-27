"""单元测试（无需微信客户端与真实 API Key）。"""

import re
from pathlib import Path
from unittest.mock import patch

from ai_engine import AiConfig, _clean_ai_output
from app_config import AppConfig, load_config, transform
from nekomimi import NekomimiConfig, try_transform_laughter, transform as transform_rules


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
        first = transform("mock预览句", cfg)
        second = transform("mock预览句", cfg)
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
        result = transform("我等你", cfg)
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


def test_normalize_wrong_master_suffix():
    from nekomimi import _normalize_master_position

    assert _normalize_master_position("好的，我知道了，主人") == "好的主人，我知道了"
    assert _normalize_master_position("好的，我知道了，主人喵！") == "好的主人，我知道了喵！"


def test_acknowledgement_master_natural():
    """「好的，我知道了」→「好的主人，我知道了喵」类语序。"""
    cfg = NekomimiConfig(
        seed=1,
        master_chance=1.0,
        nya_end_chance=1.0,
        enable_replacements=False,
        enable_particles=False,
    )
    result = transform_rules("好的，我知道了", cfg)
    assert "好的主人，" in result
    assert "知道了，主人" not in result


def test_no_replacement_wo_in_wozhidao():
    cfg = NekomimiConfig(
        seed=1,
        master_chance=0.0,
        force_master=False,
        enable_nya=False,
        enable_particles=False,
        enable_replacements=True,
    )
    from nekomimi import WordReplacement

    cfg.replacements = [WordReplacement("我", "人家", 1.0, True)]
    result = transform_rules("好的，我知道了", cfg)
    assert "人家" not in result


def test_short_affection_master_prefix():
    cfg = NekomimiConfig(
        seed=1,
        master_chance=1.0,
        nya_end_chance=1.0,
        enable_replacements=False,
        enable_particles=False,
    )
    result = transform_rules("喜欢你", cfg)
    assert result.startswith("主人")
    assert "喜欢你，主人" not in result


def test_nya_after_particle():
    cfg = NekomimiConfig(
        seed=3,
        master_chance=0.0,
        force_master=False,
        nya_end_chance=1.0,
        enable_replacements=False,
        enable_particles=False,
    )
    result = transform_rules("你好呀", cfg)
    assert "喵" in result


def test_exact_phrase_nihao():
    cfg = NekomimiConfig(seed=1, enable_replacements=False)
    result = transform_rules("你好", cfg)
    assert result in ("主人好呀喵～", "主人好喵～", "喵～主人好呀")


def test_dataset_lookup_in_transform():
    import json
    import tempfile

    import ai_dataset
    from app_config import TRANSFORM_CACHE

    TRANSFORM_CACHE.clear()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ai_rewrites.jsonl"
        ai_dataset._DATA_DIR = Path(tmp)
        ai_dataset._DATA_FILE = path
        ai_dataset.invalidate_lookup_cache()
        path.write_text(
            json.dumps({"input": "测试语料", "output": "语料命中喵～", "model": "x"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        cfg = AppConfig(
            ai=AiConfig(api_key="", use_ai_chance=0.0, min_length_for_ai=999, use_dataset_lookup=True),
        )
        assert transform("测试语料", cfg) == "语料命中喵～"

        cfg.ai.use_dataset_lookup = False
        TRANSFORM_CACHE.clear()
        result = transform("测试语料", cfg)
        assert result == "语料命中喵～" or "喵" in result


def test_save_ai_rewrite():
    import json
    import tempfile

    import ai_dataset

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ai_rewrites.jsonl"
        ai_dataset._DATA_DIR = Path(tmp)
        ai_dataset._DATA_FILE = path

        ai_dataset.save_ai_rewrite("你好", "主人好呀喵", model="deepseek-chat", enabled=True)
        ai_dataset.save_ai_rewrite("你好", "主人好呀喵", model="deepseek-chat", enabled=True)
        assert ai_dataset.dataset_count() == 1

        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["input"] == "你好"
        assert rows[0]["output"] == "主人好呀喵"


def test_laughter_transform():
    cfg = AppConfig(rules=NekomimiConfig(seed=1))
    assert try_transform_laughter("哈哈哈", cfg.rules) in ("哈哈哈", "笑死我了喵", "笑死人家了喵")
    assert try_transform_laughter("你好", cfg.rules) is None
    result = transform("哈哈哈", cfg)
    assert result in ("哈哈哈", "笑死我了喵", "笑死人家了喵")
    assert "主人" not in result


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
    test_normalize_wrong_master_suffix()
    test_acknowledgement_master_natural()
    test_no_replacement_wo_in_wozhidao()
    test_short_affection_master_prefix()
    test_nya_after_particle()
    test_exact_phrase_nihao()
    test_dataset_lookup_in_transform()
    test_save_ai_rewrite()
    test_laughter_transform()
    test_load_config_file()
    print("OK")
