# 架构说明（开发者）

## 模块职责

```
main.py          入口：CMD 命令行、加载配置、启动钩子
hook.py          微信 Enter 拦截、剪贴板读写、发送
app_config.py    配置加载、混合调度、预览/发送缓存
nekomimi.py      纯本地规则猫化（主人/喵/词库替换）
ai_engine.py     OpenAI 兼容 API 调用
test_nekomimi.py 单元测试
```

## 数据流

```
用户按 Enter（微信前台）
    → hook.WeChatCatHook._on_enter_key（拦截 KeyDown/KeyUp）
    → hook.catify_and_send
        → Ctrl+X 剪切输入框文本
        → app_config.transform
            → 命中缓存？直接返回
            → 应调 AI？ai_engine.transform_ai
            → 否则 nekomimi.transform（规则）
        → Ctrl+V 粘贴
        → keyboard.send("enter") 发送
```

## 扩展点

| 需求 | 修改位置 |
|------|----------|
| 调整猫娘规则 | `nekomimi.py`、`config.json` 的 `replacements` |
| 调整 AI 人设 | `ai_engine.DEFAULT_SYSTEM_PROMPT` 或 `config.ai.system_prompt` |
| 何时调 API | `app_config.should_use_ai()` |
| 支持新 API 平台 | 仅需改 `config.json` 的 `base_url` / `model`（OpenAI 兼容） |
| 换 IM 客户端 | `hook.is_wechat_foreground()` 窗口标题判断 |

## 测试

```bat
venv\Scripts\python test_nekomimi.py
```

## 依赖

- `keyboard` — 全局键盘钩子（Windows 建议管理员运行）
- `pyperclip` — 剪贴板
- 标准库 `urllib` — HTTP，无额外 AI SDK
