from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
import streamlit as st


API_BASE_URL = os.getenv("ARS_API_BASE_URL", "http://127.0.0.1:8000")
POST_TIMEOUT_SECONDS = float(os.getenv("ARS_FRONTEND_POST_TIMEOUT_SECONDS", "1500"))
PRESETS = ["架空中世纪", "古典帝国", "黑暗奇幻"]
STAT_LABELS = {
    "treasury": "国库",
    "stability": "稳定",
    "prestige": "威望",
    "legitimacy": "合法性",
}
STANCE_LABELS = {
    "support": "✅ 支持",
    "oppose": "⛔ 反对",
    "bargain": "🤝 议价",
    "neutral": "⏳ 观望",
}


st.set_page_config(page_title="Agentic Ruler Simulator", page_icon="♟", layout="wide")


def api_get(path: str) -> Any:
    with httpx.Client(timeout=20) as client:
        response = client.get(f"{API_BASE_URL}{path}")
        response.raise_for_status()
        return response.json()


def api_post(path: str, payload: dict[str, Any]) -> Any:
    with httpx.Client(timeout=POST_TIMEOUT_SECONDS) as client:
        response = client.post(f"{API_BASE_URL}{path}", json=payload)
        response.raise_for_status()
        return response.json()


def load_games() -> list[dict[str, Any]]:
    try:
        return api_get("/api/games")
    except Exception:
        return []


def load_state(game_id: str) -> dict[str, Any] | None:
    try:
        return api_get(f"/api/games/{game_id}/state")
    except Exception as exc:
        st.error(f"读取存档失败：{exc}")
        return None


def load_turns(game_id: str) -> list[dict[str, Any]]:
    try:
        return api_get(f"/api/games/{game_id}/turns")
    except Exception as exc:
        st.error(f"读取回合历史失败：{exc}")
        return []


def current_turn_resolution(
    state: dict[str, Any] | None, turns: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not state or not turns:
        return None
    current_turn = state.get("turn_number")
    record = next(
        (turn for turn in reversed(turns) if turn.get("turn_number") == current_turn),
        None,
    )
    if not record:
        return None
    resolution = record.get("resolution") or {}
    if "opening_narrative" in resolution:
        return {
            "narrative": resolution["opening_narrative"],
            "reactions": [],
            "stat_changes": {},
            "faction_changes": [],
        }
    if "narrative" in resolution:
        return resolution
    return {
        "narrative": record.get("narrative", ""),
        "reactions": [],
        "stat_changes": {},
        "faction_changes": [],
    }


def render_stat(label: str, value: int, suffix: str = "") -> None:
    st.metric(label, f"{value}{suffix}")


def render_faction(faction: dict[str, Any]) -> None:
    st.markdown(f"**{faction['name']}**")
    st.caption(f"{faction['leader']['name']} · {'、'.join(faction['leader']['traits'])}")
    st.progress(faction["clout"] / 100, text=f"影响力 {faction['clout']}")
    st.progress(faction["approval"] / 100, text=f"好感 {faction['approval']}")


def set_game(game_id: str, state: dict[str, Any] | None = None) -> None:
    st.session_state.game_id = game_id
    st.session_state.state = state if state else load_state(game_id)
    st.session_state.turns = load_turns(game_id)
    st.session_state.last_resolution = current_turn_resolution(
        st.session_state.state,
        st.session_state.turns,
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.title("ARS")
        games = load_games()
        if games:
            labels = {
                f"{game['title']} · 回合 {game['current_turn']}": game["game_id"]
                for game in games
            }
            current_label = next(
                (
                    label
                    for label, game_id in labels.items()
                    if game_id == st.session_state.get("game_id")
                ),
                next(iter(labels)),
            )
            selected_label = st.selectbox("存档", list(labels), index=list(labels).index(current_label))
            if st.button("载入", use_container_width=True):
                set_game(labels[selected_label])
                st.rerun()
        else:
            st.caption("暂无本地存档")

        state = st.session_state.get("state")
        if not state:
            return

        st.divider()
        st.subheader("国势")
        stats = state["global_stats"]
        col_a, col_b = st.columns(2)
        with col_a:
            render_stat("国库", stats["treasury"])
            render_stat("威望", stats["prestige"])
        with col_b:
            render_stat("稳定", stats["stability"])
            render_stat("合法性", stats["legitimacy"])

        st.divider()
        st.subheader("派系")
        for faction in state["factions"]:
            render_faction(faction)
            st.write("")

        st.divider()
        st.subheader("回滚")
        turns = st.session_state.get("turns", [])
        if turns:
            turn_options = [turn["turn_number"] for turn in turns]
            selected_turn = st.selectbox("目标回合", turn_options, index=len(turn_options) - 1)
            if st.button("回滚到此回合", use_container_width=True):
                try:
                    state = api_post(
                        f"/api/games/{st.session_state.game_id}/rollback",
                        {"turn_number": selected_turn},
                    )
                    set_game(st.session_state.game_id, state)
                    st.rerun()
                except Exception as exc:
                    st.error(f"回滚失败：{exc}")


def render_new_game() -> None:
    st.title("Agentic Ruler Simulator")
    with st.form("new_game"):
        col_a, col_b = st.columns([1, 1])
        with col_a:
            preset = st.selectbox("默认剧本", PRESETS)
            ruler_name = st.text_input("统治者名", value="无名统治者")
        with col_b:
            custom_setting = st.text_area(
                "自定义剧本",
                height=150,
                placeholder="例如：一个海上城邦刚赢得独立，但贵族舰队、商人议会和神秘教团都想塑造新政权。",
            )
        submitted = st.form_submit_button("开局", use_container_width=True)
    if submitted:
        try:
            with st.spinner("正在生成世界与派系，免费模型可能需要较长时间..."):
                result = api_post(
                    "/api/games",
                    {
                        "preset": preset,
                        "custom_setting": custom_setting,
                        "ruler_name": ruler_name,
                    },
                )
            set_game(result["game_id"], result["state"])
            st.session_state.last_resolution = {
                "narrative": result["opening_narrative"],
                "reactions": [],
                "stat_changes": {},
                "faction_changes": [],
            }
            st.rerun()
        except Exception as exc:
            st.error(f"开局失败：{exc}")


def render_game(state: dict[str, Any]) -> None:
    metadata = state["world_metadata"]
    st.title(metadata["setting"])
    st.caption(
        f"{metadata['era']} · 关键资源：{metadata['key_resource']} · "
        f"统治者：{metadata['ruler_name']} · 回合 {state['turn_number']}"
    )

    crises = state.get("current_crises", [])
    if crises:
        st.warning("当前危机：" + " / ".join(crises))

    last_resolution = st.session_state.get("last_resolution")
    if last_resolution:
        st.markdown("### 局势")
        st.write(last_resolution["narrative"])
        reactions = last_resolution.get("reactions", [])
        if reactions:
            st.markdown("### 御前会议")
            for reaction in reactions:
                faction = next(
                    (
                        item
                        for item in state["factions"]
                        if item["id"] == reaction["faction_id"]
                    ),
                    None,
                )
                name = faction["name"] if faction else reaction["faction_id"]
                stance = STANCE_LABELS.get(reaction["stance"], reaction["stance"])
                with st.expander(f"{stance} · {name}", expanded=True):
                    st.write(reaction["public_statement"])
                    st.caption(reaction["demand"])

        stat_changes = last_resolution.get("stat_changes", {})
        faction_changes = last_resolution.get("faction_changes", [])
        if stat_changes or faction_changes:
            st.markdown("### 变化")
            cols = st.columns(4)
            stats = state["global_stats"]
            for index, key in enumerate(["treasury", "stability", "prestige", "legitimacy"]):
                delta = stat_changes.get(key, 0)
                with cols[index]:
                    st.metric(STAT_LABELS[key], stats[key], delta=delta)
            for change in faction_changes:
                faction = next(
                    (item for item in state["factions"] if item["id"] == change["faction_id"]),
                    None,
                )
                faction_name = faction["name"] if faction else change["faction_id"]
                st.caption(
                    f"{faction_name}：好感 {change['approval_delta']:+d}，"
                    f"影响力 {change['clout_delta']:+d}。{change.get('reason', '')}"
                )

    st.markdown("### 诏令")
    with st.form("turn_form", clear_on_submit=True):
        command = st.text_area(
            "输入政策或命令",
            height=120,
            placeholder="例如：提高城市关税，用新增收入修复边境要塞，并要求教会公开支持王室。",
        )
        submitted = st.form_submit_button("颁布", use_container_width=True)
    if submitted and command.strip():
        try:
            with st.spinner("正在召集派系并等待 Arbiter 结算，慢速模型请耐心等待..."):
                result = api_post(
                    f"/api/games/{st.session_state.game_id}/turns",
                    {"command": command.strip()},
                )
            st.session_state.state = result["state"]
            st.session_state.turns = load_turns(st.session_state.game_id)
            st.session_state.last_resolution = result
            st.rerun()
        except Exception as exc:
            st.error(f"回合结算失败：{exc}")

    with st.expander("史册", expanded=False):
        for entry in reversed(state.get("history_log", [])):
            created = datetime.fromisoformat(entry["created_at"]).strftime("%Y-%m-%d %H:%M")
            st.markdown(f"**回合 {entry['turn_number']} · {entry['title']}**")
            st.caption(created)
            st.write(entry["summary"])


def main() -> None:
    if "game_id" not in st.session_state:
        st.session_state.game_id = None
    if "state" not in st.session_state:
        st.session_state.state = None
    if "turns" not in st.session_state:
        st.session_state.turns = []
    if "last_resolution" not in st.session_state:
        st.session_state.last_resolution = None
    render_sidebar()
    state = st.session_state.get("state")
    if not state:
        render_new_game()
    else:
        render_game(state)


if __name__ == "__main__":
    main()

