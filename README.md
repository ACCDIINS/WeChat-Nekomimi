# WeChat Nekomimi / 微信猫娘助手

在微信 PC 版发送消息前，自动将输入改写为猫娘语气（「主人」「喵」等）。短句走**本地规则**，长句或抽样才调用 **OpenAI 兼容 API**。

> **平台**：Windows + 微信 PC 客户端  
> **语言**：Python 3.10+

---

## 功能

- 按 **Enter** 发送前自动猫化，**Shift+Enter** 换行不受影响
- 短句本地规则（省 API）；超过 22 字或低概率抽样才调 AI
- 可强制每条消息出现「主人」
- 预览与发送相同原文共用缓存，不重复请求 API
- 支持 DeepSeek / Kimi / 通义等 OpenAI 兼容 API

---

## 安装与运行

**1. 获取项目**

```bash
git clone https://github.com/ACCDIINS/WeChat-Nekomimi.git
cd WeChat-Nekomimi
```

**2. 配置**

```bat
copy config.example.json config.json
```

用记事本打开 `config.json`，在 `ai.api_key` 填入你的 API Key。  
也可设置环境变量 `NEKOMIMI_API_KEY`，无需写进文件。

**3. 启动**

双击 `run.bat`。首次运行会自动创建虚拟环境并安装依赖。

若改写不生效，请右键 **以管理员身份运行** `run.bat`。

手动启动：

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**4. 使用**

1. 保持 CMD 窗口运行  
2. 打开微信聊天，输入文字  
3. 按 **Enter** 发送  

---

## CMD 命令

| 命令 | 说明 |
|------|------|
| `m` | 开关猫娘模式 |
| `f` | 开关微信发送强制 AI |
| `t` / `t 文本` | 规则预览 |
| `a` / `a 文本` | AI 预览（需 API Key） |
| `s` | 查看状态 |
| `r` | 重载 config.json |
| `q` | 退出 |
| `?` | 帮助 |

---

## 配置说明

完整字段见 [docs/CONFIG.md](docs/CONFIG.md)。

```json
{
  "ai": {
    "api_key": "你的密钥",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "use_ai_chance": 0.12,
    "min_length_for_ai": 22
  },
  "force_master": true,
  "master_chance": 0.72
}
```

换 API 平台只改 `base_url` 和 `model` 即可，无需改代码。

---

## 项目结构

```
main.py              入口
hook.py              微信 Enter 拦截
app_config.py        配置与调度
nekomimi.py          本地规则猫化
ai_engine.py         API 调用
config.example.json  配置模板
config.json          本地配置（自行创建）
run.bat              启动脚本
docs/                详细文档
```

二次开发见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---

## 测试

```bat
venv\Scripts\python test_nekomimi.py
```

依赖：`keyboard`、`pyperclip`

---

## 隐私说明

- 短句猫化在本地完成，不上传网络  
- 调用 AI 时，仅发送**当前这一条**待发出消息到你配置的 API 服务商  
- 详见 [SECURITY.md](SECURITY.md)

---

## 许可证

[MIT](LICENSE) · 作者 [@ACCDIINS](https://github.com/ACCDIINS)

---

## 免责声明

本工具仅供学习交流。使用全局键盘钩子需自行评估风险；因使用本软件产生的账号或数据问题，作者不承担责任。
