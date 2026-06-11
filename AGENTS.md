# Agentic Ruler Simulator (ARS) 架构设计

## 1. 项目愿景

打造一个基于大模型驱动的统治模拟器，融合《欧陆风云》《十字军之王》《维多利亚》《英白拉多：罗马》和全战系列里“国家机器、人物性格、派系利益”彼此牵制的体验。

首版目标不是做复杂地图或多人系统，而是做一个本地单人可玩的文字策略核心：玩家以统治者身份发布政策，系统让多个派系 Agent 独立反应，再由 Arbiter 汇总为叙事和数值变化。

## 2. 系统架构：1 + N

### 2.1 The Arbiter（中枢协调者）

职责：

- 逻辑解析：将玩家的模糊文字指令转化为具体数值变化。
- 状态维护：管理资源、稳定、威望、合法性、危机和历史。
- 冲突调解：综合派系反馈，决定最终后果。
- 世界构建：开局时生成世界观、派系和初始危机。

输出：

- 更新后的 `GameState`。
- 派系反馈、数值变化和阶段性叙事总结。

### 2.2 Faction Agents（动态派系）

每个派系是一个独立 Agent，包含双层结构：

- 利益层：基于权力来源的长期诉求，例如武力、经济、信仰、土地、技术。
- 人格层：当前领袖的性格，例如顽固、贪婪、胆小、鲁莽、精明。

职责：

- 对玩家政策进行评价、游说、威胁、支持或讨价还价。
- 保留自己的记忆摘要，影响后续态度。
- 为 Arbiter 提供建议性的数值影响。

## 3. 核心数据对象

```json
{
  "world_metadata": {
    "setting": "架空中世纪",
    "era": "继承危机后的摄政初年",
    "key_resource": "银税"
  },
  "global_stats": {
    "treasury": 100,
    "stability": 72,
    "prestige": 50,
    "legitimacy": 58
  },
  "factions": [
    {
      "id": "fac_nobility",
      "name": "高地诸侯",
      "power_origin": "封地与骑士",
      "clout": 34,
      "approval": 52,
      "leader": {
        "name": "罗德里克公爵",
        "traits": ["骄傲", "顽固"]
      }
    }
  ],
  "history_log": []
}
```

## 4. 游戏循环

1. Input：玩家输入文本指令，例如“加税并安抚军队”。
2. Process：Arbiter 将指令广播给所有 Faction Agents。
3. Dialogue：派系根据利益和领袖人格做出反馈。
4. Action：Arbiter 综合反馈，计算最终 JSON 状态更新。
5. Output：前端显示派系对话、数值变化和当前局势描述。

## 5. 首版技术选型

- 后端：Python + FastAPI。
- Agent：LangChain Structured Output，缺少云端配置时使用本地 Mock 逻辑。
- 前端：Streamlit。
- 持久化：SQLite，每回合完整保存，可回滚。
- 模式：本地单人，不设计多人、账号、房间或同步。

