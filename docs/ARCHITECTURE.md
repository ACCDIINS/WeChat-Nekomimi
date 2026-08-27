# 架构说明（开发者）

WeChat Nekomimi 是 **Windows 专用** 小工具：在微信 PC 版按 Enter 发送前，将输入改写为猫娘语气。采用 **根目录平铺** 的 Python 模块结构（约 7 个源文件），无 `src/` 包划分。

配置字段详见 [CONFIG.md](CONFIG.md)。

---

## 目录结构

```
WeChat-Nekomimi/
├── main.py              程序入口：CMD 控制台、命令循环、启动钩子
├── hook.py              微信 Enter 拦截、剪贴板、窗口焦点、发送
├── app_config.py        配置加载、混合调度、内存缓存
├── nekomimi.py          本地规则猫化引擎
├── ai_engine.py         OpenAI 兼容 API 调用
├── ai_dataset.py        AI 改写语料持久化
├── test_nekomimi.py     单元测试（无需微信 / 真实 API）
│
├── config.example.json  配置模板（复制为 config.json 后本地填写）
├── config.json          本地配置（含 API Key，.gitignore，不上传）
├── requirements.txt     Python 依赖
├── run.bat              Windows 启动脚本（venv + main.py）
│
├── data/
│   └── ai_rewrites.jsonl   运行时生成的 AI 语料（.gitignore）
│
├── docs/
│   ├── ARCHITECTURE.md  本文档
│   └── CONFIG.md        配置项说明
│
├── README.md            用户说明
├── SECURITY.md          隐私与 API Key
└── LICENSE
```

### 运行时生成、不提交 Git 的内容

| 路径 | 说明 |
|------|------|
| `config.json` | 用户配置与 API Key |
| `venv/` | 虚拟环境 |
| `data/ai_rewrites.jsonl` | AI 改写语料 |
| `__pycache__/` | Python 字节码缓存 |

---

## 模块依赖关系

```
                    ┌─────────────┐
                    │   main.py   │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
     ┌──────────┐   ┌─────────────┐  ┌─────────────┐
     │ hook.py  │   │ app_config  │  │ ai_dataset  │
     └────┬─────┘   └──────┬──────┘  └─────────────┘
          │                │
          │         ┌──────┴──────┬────────────┐
          │         ▼             ▼            ▼
          └────► transform   nekomimi    ai_engine
                 (调度)       (规则)      (API)
```

- **main.py** 只负责 UI 与生命周期，不直接猫化文本。
- **hook.py** 只负责微信交互，猫化逻辑全部交给 `app_config.transform`。
- **app_config** 是规则与 AI 的**唯一调度入口**（微信发送、`t`/`a` 预览共用）。

---

## 各模块说明

### `main.py` — 入口与控制台

| 职责 | 说明 |
|------|------|
| 启动 | 读 `config.json`、创建 `WeChatCatHook`、后台线程跑命令循环 |
| 日志 | `log()` 带时间戳；与 `input("命令> ")` 用锁协调，避免钩子日志打乱提示符 |
| 命令 | 见下文「CMD 命令」 |
| 横幅 | `_print_banner()` 按终端显示宽度居中（中文计 2 宽） |

不处理猫化算法本身。

---

### `hook.py` — 微信发送链路

| 符号 | 职责 |
|------|------|
| `WeChatCatHook` | 全局 Enter 钩子；维护猫娘开关、强制 AI 开关、处理中标志 |
| `_on_enter_key` | 拦截 KeyDown/KeyUp；Shift+Enter 换行；微信前台才猫化 |
| `catify_and_send` | 剪切 → `transform` → 切回微信焦点 → 粘贴 → Enter |
| `_restore_wechat_focus` | AI 耗时时焦点可能跑到 CMD，粘贴前强制回到微信窗口 |
| `is_wechat_foreground` | 根据窗口标题含「微信」/「WeChat」判断前台 |

发送时 `force_ai` 取自 `hook.force_ai`（CMD `f` 或 `config.ai.force_ai_on_send`）。

---

### `app_config.py` — 配置与调度

| 符号 | 职责 |
|------|------|
| `AppConfig` | 聚合 `AiConfig` + `NekomimiConfig` |
| `load_config` | 解析 `config.json` →  dataclass |
| `should_use_ai` | 字数 ≥ 阈值必调 AI；否则按概率抽样 |
| `TransformCache` / `TRANSFORM_CACHE` | **内存**缓存，预览与发送共用，进程结束即清空 |
| `transform` | **核心调度**，见下文「transform 流水线」 |

---

### `nekomimi.py` — 本地规则引擎

纯本地、无网络。主要步骤（`transform` 内顺序）：

1. `_should_skip` — 空文本、URL、纯数字等跳过  
2. `_apply_replacements` — 词库替换（如「我→人家」，「我知道」等受保护短语不替换）  
3. `_insert_master` / `_ensure_master` — 插入「主人」  
4. `_normalize_master_position` — 纠正「好的，…，主人」→「好的主人，…」  
5. `_append_nya` — 句末「喵」等  
6. `_cute_particles` — 「呢」「～」等语气词  

特殊：`try_transform_laughter` 在 **app_config** 层调用（纯「哈哈哈」类 → 固定几种笑声，不加主人）。

---

### `ai_engine.py` — API 猫化

| 符号 | 职责 |
|------|------|
| `AiConfig` | API 地址、模型、温度、强制 AI、语料开关等 |
| `resolve_api_key` / `has_api_key` | 环境变量 `NEKOMIMI_API_KEY` 优先于配置文件 |
| `transform_ai` | POST OpenAI 兼容 `/v1/chat/completions` |
| `_clean_ai_output` | 去掉引号、markdown 等 AI 多余包装 |

密钥来源见 [SECURITY.md](../SECURITY.md)。

---

### `ai_dataset.py` — 语料持久化

| 符号 | 职责 |
|------|------|
| `save_ai_rewrite` | 每次 **AI 成功改写** 后追加一行 JSON |
| `dataset_count` | 统计语料条数（`s` 命令展示） |

与 `TRANSFORM_CACHE` 无关：语料**落盘**、重启仍在；缓存**仅内存**。

单条格式示例：

```json
{"input":"你好","output":"主人好呀～","model":"deepseek-chat","base_url":"...","ts":"..."}
```

---

### `test_nekomimi.py` — 测试

覆盖：跳过规则、主人位置、AI mock、缓存、笑声、语料保存、配置加载等。  
不依赖微信客户端与真实 API Key。

```bat
venv\Scripts\python test_nekomimi.py
```

---

## transform 流水线

所有猫化（微信发送、`t`、`a` 预览）均调用：

```python
app_config.transform(text, config, on_log=log, force_ai=False)
```

```
输入 text
  │
  ├─ _should_skip ? ──────────────────────────► 原文返回
  │
  ├─ try_transform_laughter ? ───────────────► 笑声句式（不调 AI）
  │
  ├─ TRANSFORM_CACHE 命中 ? ─────────────────► 缓存结果（不调 API）
  │
  ├─ force_ai 且无 Key ? ───────────────────► 规则猫化 + 写缓存
  │
  ├─ 不应调 AI（短句且未抽样）? ─────────────► 规则猫化 + 写缓存
  │
  ├─ 调 ai_engine.transform_ai
  │     ├─ 成功 → save_ai_rewrite（语料） + 写缓存
  │     └─ 失败且 fallback_to_rules → 规则猫化 + 写缓存
  │
  └─ 失败且无回退 ───────────────────────────► 原文返回
```

### 何时走 AI

| 条件 | 行为 |
|------|------|
| `force_ai=True`（`a` 预览 / 微信 `f` 强制 AI） | 必调 AI（有 Key 时） |
| 字数 ≥ `ai.min_length_for_ai`（默认 22） | 必调 AI |
| 否则 | 以 `ai.use_ai_chance`（默认 12%）随机 |
| 无 API Key | 始终规则猫化 |

### 缓存键说明

同一原文在以下情况视为**不同缓存**：

- `force_ai` 与混合模式不同（`t` vs `a` 结果分开存）
- 模型、`base_url`、主人相关配置、system_prompt 变化

---

## 微信发送数据流

```
用户在微信按 Enter（非 Shift+Enter）
    → hook._on_enter_key（suppress 拦截）
    → catify_and_send
        → 记录当前微信 hwnd
        → Ctrl+A / Ctrl+X 剪切输入框
        → app_config.transform(..., force_ai=hook.force_ai)
        → _restore_wechat_focus（粘贴前）
        → Ctrl+V 粘贴猫化结果
        → keyboard.send("enter") 发送
        → （钩子线程）log 猫化摘要
```

CMD 命令循环在**独立线程**；钩子回调也在**键盘库线程**。两者通过 `log()` 的锁与 `_at_prompt` 协调输出。

---

## CMD 命令（main.py）

| 命令 | 作用 |
|------|------|
| `m` | 开关猫娘模式（关则 Enter 不拦截） |
| `f` | 开关微信发送**强制 AI** |
| `t` / `t 文本` | **规则**预览（混合策略，可命中缓存） |
| `a` / `a 文本` | **强制 AI** 预览 |
| `s` | 状态：猫娘/强制 AI/概率/API Key/缓存条数/语料条数 |
| `r` | 重载 `config.json` 并清空内存缓存 |
| `q` | 退出并卸载 Enter 钩子 |
| `?` | 显示帮助 |

---

## 配置与代码的对应

| 配置文件块 | 加载到 | 主要影响 |
|------------|--------|----------|
| `ai.*` | `AiConfig` | API、抽样、强制 AI、语料开关 |
| `master_chance`、`force_master` 等 | `NekomimiConfig` | 规则猫化 |
| `replacements` | `WordReplacement[]` | 词库替换 |

`config.json` 不存在时使用代码内默认值；`run.bat` 首次运行会从 `config.example.json` 复制。

---

## 扩展点

| 需求 | 修改位置 |
|------|----------|
| 猫娘规则、主人/喵逻辑 | `nekomimi.py` |
| 词库 | `config.json` → `replacements` |
| AI 人设 | `ai_engine.DEFAULT_SYSTEM_PROMPT` 或 `config.ai.system_prompt` |
| 何时调 API | `app_config.should_use_ai()` |
| 新 API 平台 | `config.json` 的 `base_url` / `model`（OpenAI 兼容即可） |
| 换 IM 客户端 | `hook.is_wechat_foreground()`、`_find_wechat_hwnd()` |
| 语料格式 / 路径 | `ai_dataset.py` |
| 新增 CMD 命令 | `main.py` → `command_loop` |

---

## 依赖

| 依赖 | 用途 |
|------|------|
| `keyboard` | 全局 Enter 钩子（建议管理员运行 `run.bat`） |
| `pyperclip` | 剪贴板读写 |
| 标准库 `urllib` | HTTP 调 API，无额外 AI SDK |
| 标准库 `ctypes` | Windows 窗口焦点 |

Python **3.10+**，仅 **Windows + 微信 PC 版**。

---

## 设计说明（为何这样拆）

| 决策 | 原因 |
|------|------|
| 根目录平铺，无 `src/` 包 | 文件少、双击 `run.bat` 即可跑，导入简单 |
| 调度集中在 `app_config.transform` | 微信、预览、缓存、语料逻辑一处维护 |
| 内存缓存 vs jsonl 语料分离 | 缓存为省 API；语料为长期训练数据，生命周期不同 |
| `hook` 与 `main` 分文件 | 钩子在线程中运行，与控制台 UI 解耦 |

功能继续增加（多 IM、插件、Web 配置）时，再考虑 `src/nekomimi/` 分包；当前规模不必提前重构。
