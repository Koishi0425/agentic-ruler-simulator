# Agentic Ruler Simulator

一个本地单人文字策略模拟器。玩家以统治者身份发布政策，多个派系 Agent 根据利益和领袖人格进行反馈，Arbiter 汇总为叙事、数值变化和新局势。

## 功能

- FastAPI 后端：游戏状态、Agent 编排、SQLite 存档、回滚。
- Streamlit 前端：开局、国势面板、派系面板、诏令输入、史册。
- 地缘战略层：本国领土、邻国、威胁、情报、动员、战争疲劳和回合报告。
- 战略动作：扩张、外交、动员、建设、进攻。
- OpenAI 兼容 LLM 配置：支持 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。
- Mock 模式：没有 LangChain 或云端密钥时也能试玩完整循环。

## 启动

1. 安装依赖：

```powershell
python -m pip install -r requirements.txt
```

2. 复制配置：

```powershell
Copy-Item .env.example .env
```

3. 启动后端：

```powershell
python -m uvicorn backend.main:app --reload --port 8000
```

4. 启动前端：

```powershell
python -m streamlit run frontend/app.py
```

前端默认访问 `http://localhost:8501`，后端默认访问 `http://127.0.0.1:8000`。

## 配置

`.env.example` 中的 `ARS_USE_MOCK_LLM=true` 会强制使用本地 Mock 逻辑。要使用真实云端模型，请安装 LangChain 相关依赖，配置 API Key，并将该值设为 `false` 或删除。

```env
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
ARS_LLM_TIMEOUT_SECONDS=600
ARS_FRONTEND_POST_TIMEOUT_SECONDS=1500
ARS_USE_MOCK_LLM=false
```

免费或低优先级模型可能响应很慢。`ARS_LLM_TIMEOUT_SECONDS` 控制后端单次模型调用最长等待时间，`ARS_FRONTEND_POST_TIMEOUT_SECONDS` 控制前端等待后端回合结算的时间。

## API

- `POST /api/games`：创建新游戏。
- `GET /api/games`：列出本地存档。
- `GET /api/games/{game_id}/state`：读取当前状态。
- `POST /api/games/{game_id}/turns`：提交玩家指令并结算回合。
- `GET /api/games/{game_id}/turns`：读取回合历史。
- `POST /api/games/{game_id}/rollback`：回滚到指定回合。

## 战略玩法

诏令可以继续使用自由文本，也可以包含更明确的战略动作：

- `进攻北境汗国边境矿山`
- `派使者改善与南洋商贸邦联关系`
- `动员边境军镇`
- `在铁矿区修筑要塞`
- `开拓高地边疆`

每回合会同时结算内廷派系反馈和外部世界压力。侧边栏会显示地缘政治看板，主区域会显示经济、边境、情报、派系和军事五类回合报告。

## 测试

```powershell
python -m pytest
```
