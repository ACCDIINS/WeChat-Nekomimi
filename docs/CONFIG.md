# 配置说明

配置文件路径：`config.json`（从 `config.example.json` 复制）。

## `ai` — 大模型 API（OpenAI 兼容）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `api_key` | string | `""` | API 密钥；也可用环境变量 `NEKOMIMI_API_KEY` |
| `base_url` | string | DeepSeek 地址 | 兼容 OpenAI `/v1/chat/completions` 的基址 |
| `model` | string | `deepseek-chat` | 模型名称 |
| `timeout` | number | `20` | 请求超时（秒） |
| `temperature` | number | `0.75` | 采样温度 |
| `fallback_to_rules` | bool | `true` | API 失败时回退本地规则 |
| `system_prompt` | string | `""` | 自定义系统提示词；空则使用内置猫娘 prompt |
| `use_ai_chance` | number | `0.12` | 短句随机调用 AI 的概率（0~1） |
| `min_length_for_ai` | number | `22` | 超过此字数必调 AI |

### 常用 `base_url` / `model`

```json
// DeepSeek
"base_url": "https://api.deepseek.com",
"model": "deepseek-chat"

// Kimi
"base_url": "https://api.moonshot.cn/v1",
"model": "moonshot-v1-8k"

// 通义千问
"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
"model": "qwen-turbo"
```

## 规则猫化

| 字段 | 说明 |
|------|------|
| `force_master` | `true` 时每条消息至少出现一次「主人」 |
| `master_chance` | 额外插入「主人」的概率 |
| `nya_end_chance` | 句末加「喵」的概率 |
| `suffix_templates` | 句末后缀候选 |
| `replacements` | 词库替换 `{ from, to, chance, once }` |

## 调用策略（固定混合逻辑）

1. 短句 → 本地规则（不调 API）
2. 字数 > `min_length_for_ai` → 调 API
3. 否则按 `use_ai_chance` 抽样调 API
4. 预览与发送相同原文共用缓存，不重复扣费
