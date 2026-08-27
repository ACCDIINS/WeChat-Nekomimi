@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "config.json" (
    echo 未找到 config.json，正在从 config.example.json 复制...
    copy /Y "config.example.json" "config.json" >nul
    echo 请编辑 config.json 填入 ai.api_key 后重新运行。
    pause
    exit /b 0
)

if not exist "venv\Scripts\python.exe" (
    echo 首次运行，正在创建虚拟环境...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo 若改写不生效或重复发送，请右键「以管理员身份运行」此脚本。
echo API Key 请配置在 config.json 或环境变量 NEKOMIMI_API_KEY 中。
echo.
python main.py
pause
