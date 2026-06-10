# -*- coding: utf-8 -*-
"""智能助手 · 对话引导页。

用自然语言对话引导用户使用平台各功能:DeepSeek 给「回复 + 选项 + 动作」,
选项渲染成按钮、需要地点/范围时内嵌地图点选/圈选,意图明确后一键预填参数并跳转到对应模块页。
引擎 llm_agent.py、知识底座 platform_manual.py。
"""
import os

import numpy as np
import streamlit as st
import folium
from streamlit_folium import st_folium

import llm_agent
import platform_manual as pm
import ems_response
from geo import _add_basemap, build_draw_map, gcj2wgs, in_shanghai
from theme import page_header

# 拟人化头像:不同功能用不同"人物"。图片放 assets/(没有则用 emoji 兜底)。
_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_AVA_GROUP1 = {"page_ems_response", "page_health_resource", "page_bike"}   # 用第一张(猫)


def _ava_file(stem):
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(_ASSETS, stem + ext)
        if os.path.exists(p):
            return p
    return None


def _avatar(page):
    """按当前功能返回头像(文件路径,缺失则 emoji)。page=None 为未分配。"""
    if page in _AVA_GROUP1:
        return _ava_file("avatar_1") or "🐱"
    if page:
        return _ava_file("avatar_2") or "🧑‍⚕️"
    return _ava_file("avatar_3") or "🤖"

WELCOME = ("你好!我是健康城市平台的智能助手 🤖 \n\n"
           "用一句话告诉我你想解决什么问题,我会帮你**找到合适的功能、讲清怎么操作、推荐参数**;"
           "需要选择时直接点按钮,需要地点或范围时在地图上点一下或圈一下即可。")
WELCOME_OPTIONS = [
    {"label": "评估某地急救多快到", "value": "我想知道某个地点救护车大概多久能到"},
    {"label": "看中暑高发在哪", "value": "我想看上海中暑病例的空间分布"},
    {"label": "规划方案算健康影响", "value": "我有一个城市规划方案,想定量算它对健康的影响"},
    {"label": "促进片区骑行", "value": "我想让一个片区的居民更多骑共享单车"},
]
# 允许助手预填的安全 session 键(其余忽略,防止给目标控件塞非法值)
_SAFE_PREFILL = {"hr_o", "hr_d", "ems_incident", "bk_poly", "bk_day", "hc_prov", "hc_city"}


def _get_key():
    try:
        return st.secrets.get("deepseek_api_key", "") or ""
    except Exception:
        return ""


def _baidu_ak():
    try:
        return st.secrets.get("baidu_ak", "") or ""
    except Exception:
        return ""


# ——— 急救反应时间:对话内直接出结果(混合模式示范)———
def _compute_ems_inline(point, ak):
    slon, slat, sd = ems_response.nearest_station(*point)
    cands = ems_response.plan_candidate_routes((slon, slat), point, ak)
    if not cands:
        return None
    for r in cands:
        r["feat"] = ems_response.compute_features(r["path"])
        r["pred"] = ems_response.predict(r["feat"])
    best = int(np.argmin([r["pred"]["seconds"] for r in cands]))
    return {"station": (slon, slat), "sdist": sd, "routes": cands,
            "best_i": best, "incident": point}


def _render_ems_result(res):
    rb = res["routes"][res["best_i"]]; pred = rb["pred"]
    sec = pred["seconds"]; grade = pred["sec_bin"]
    grade_zh = {"4min": "4分钟内", "8min": "4–8分钟", "12min": "8–12分钟", "Delay": "延误(>12分)"}.get(grade, grade)
    with st.container(border=True):
        c1, c2 = st.columns([1, 1.4])
        with c1:
            st.metric("预测到场时间", f"{sec/60:.1f} 分", help=f"分级:{grade_zh}")
            st.caption(f"分级 **{grade_zh}** · 最近急救站直线 {res['sdist']/1000:.1f} km · "
                       f"共 {len(res['routes'])} 条候选路线")
        with c2:
            st_, inc = res["station"], res["incident"]
            m = folium.Map(location=[inc[1], inc[0]], zoom_start=13, tiles=None, control_scale=True)
            _add_basemap(m, "浅色地图")
            folium.PolyLine([(p[1], p[0]) for p in rb["path"]], color="#D7191C", weight=5,
                            opacity=0.85).add_to(m)
            folium.Marker([st_[1], st_[0]], tooltip="最近急救站",
                          icon=folium.Icon(color="green", icon="plus", prefix="fa")).add_to(m)
            folium.Marker([inc[1], inc[0]], tooltip="事发点",
                          icon=folium.Icon(color="red", icon="plus-sign")).add_to(m)
            lats = [p[1] for p in rb["path"]]; lngs = [p[0] for p in rb["path"]]
            m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], padding=(25, 25))
            st_folium(m, key="asst_ems_map", width=None, height=240, returned_objects=[])


def _submit(text, key, hidden=False):
    """把一条用户消息发给助手,追加回复,刷新。hidden=True 的消息只发给模型、不在界面显示。"""
    st.session_state.asst_history.append({"role": "user", "content": text, "hidden": hidden})
    try:
        with st.spinner("助手思考中…"):
            data = llm_agent.chat(st.session_state.asst_history, key)
    except Exception as e:
        data = {"reply": f"(调用 DeepSeek 失败:{e})", "options": [], "action": {"type": "none"}}
    page = (data.get("action") or {}).get("page") or st.session_state.get("asst_cur_page")
    st.session_state["asst_cur_page"] = page
    st.session_state.asst_history.append(
        {"role": "assistant", "content": data.get("reply", ""), "page": page})
    st.session_state.asst_last = data
    st.rerun()


def _click_map():
    g = st.session_state.get("asst_geom") or {}
    m = folium.Map(location=[31.23, 121.47], zoom_start=11, tiles=None, control_scale=True)
    _add_basemap(m, "浅色地图")
    if g.get("point"):
        folium.Marker([g["point"][1], g["point"][0]], tooltip="已选点",
                      icon=folium.Icon(color="red", icon="map-marker")).add_to(m)
    return m


def _do_navigate(action):
    """应用预填(白名单)+ 地图几何 → 目标 session 键,然后跳转。"""
    reg = st.session_state.get("_nav_pages") or {}
    page = action.get("page")
    if page not in reg:
        st.warning(f"未找到目标页面:{page}"); return
    geom = st.session_state.get("asst_geom") or {}
    for k, v in (action.get("prefill") or {}).items():
        if k in _SAFE_PREFILL:
            st.session_state[k] = v
    if page == "page_ems_response" and geom.get("point"):
        st.session_state["ems_incident"] = tuple(geom["point"])
    elif page == "page_bike" and geom.get("poly"):
        st.session_state["bk_poly"] = geom["poly"]
    elif page == "page_heatroute" and geom.get("point"):
        st.session_state["hr_o"] = tuple(geom["point"])
    st.switch_page(reg[page])


def page_assistant():
    page_header("🤖 智能助手 · 对话引导",
                "用自然语言告诉我你想做什么,我来引导你用好平台功能:推荐模块、讲清操作、给参数选项,"
                "需要时在对话里点选项或在地图上点选/圈选,确定后一键带着参数跳转到对应功能页。")
    key = _get_key()
    if not key:
        st.warning("未配置 DeepSeek API Key —— 请在 `.streamlit/secrets.toml` 写入 "
                   "`deepseek_api_key = \"sk-...\"`(云端在 Settings → Secrets 配置)。")
        return

    if "asst_history" not in st.session_state:
        st.session_state.asst_history = []
        st.session_state.asst_last = {"reply": WELCOME, "options": WELCOME_OPTIONS,
                                      "action": {"type": "none"}}

    if st.button("🗑 重新开始对话"):
        for k in ("asst_history", "asst_last", "asst_geom", "asst_geom_mark",
                  "asst_ems_result", "asst_cur_page"):
            st.session_state.pop(k, None)
        st.rerun()

    # —— 对话历史 ——
    with st.chat_message("assistant", avatar=_avatar(None)):
        st.markdown(WELCOME)
    for msg in st.session_state.asst_history:
        if msg.get("hidden"):
            continue
        av = _avatar(msg.get("page")) if msg["role"] == "assistant" else None
        with st.chat_message(msg["role"], avatar=av):
            st.markdown(msg["content"])

    # —— 内联计算结果(急救反应时间)——
    if st.session_state.get("asst_ems_result"):
        _render_ems_result(st.session_state["asst_ems_result"])

    # —— 当前轮的交互组件(选项 / 地图 / 跳转)——
    last = st.session_state.get("asst_last") or {}
    action = last.get("action") or {"type": "none"}

    opts = last.get("options") or []
    if opts:
        st.caption("👇 点选或直接在下方输入")
        cols = st.columns(min(len(opts), 4))
        for i, o in enumerate(opts):
            if cols[i % len(cols)].button(o["label"], key=f"opt_{len(st.session_state.asst_history)}_{i}",
                                          use_container_width=True):
                _submit(o.get("value") or o["label"], key)

    if action.get("type") == "need_map":
        mode = action.get("map_mode", "click")
        st.markdown("**请在地图上" + ("圈定一个范围" if mode == "draw" else "点选一个位置") + "**(上海范围):")
        if mode == "draw":
            out = st_folium(build_draw_map("浅色地图"), key="asst_draw", width=None, height=380,
                            returned_objects=["last_active_drawing"])
            d = out.get("last_active_drawing") if out else None
            if d and d.get("geometry", {}).get("type") == "Polygon":
                coords = [(x, y) for x, y in d["geometry"]["coordinates"][0]]
                mark = (round(coords[0][0], 5), round(coords[0][1], 5), len(coords))
                if st.session_state.get("asst_geom_mark") != mark:
                    st.session_state["asst_geom_mark"] = mark
                    st.session_state["asst_geom"] = {"poly": coords}
                    cx = sum(p[0] for p in coords) / len(coords)
                    cy = sum(p[1] for p in coords) / len(coords)
                    _submit(f"我在地图上圈定了一个范围(约 {len(coords)} 个顶点,中心约 {cy:.4f},{cx:.4f})。", key)
        else:
            out = st_folium(_click_map(), key="asst_click", width=None, height=380,
                            returned_objects=["last_clicked"])
            lc = out.get("last_clicked") if out else None
            if lc:
                p = (round(lc["lng"], 6), round(lc["lat"], 6))
                if st.session_state.get("asst_geom_mark") != p:
                    st.session_state["asst_geom_mark"] = p
                    st.session_state["asst_geom"] = {"point": p}
                    ak = _baidu_ak()
                    # 急救反应时间:对话内直接算并展示(混合模式)
                    if action.get("page") == "page_ems_response" and in_shanghai(*p) and ak:
                        res = None
                        try:
                            with st.spinner("正在计算急救反应时间…"):
                                res = _compute_ems_inline(p, ak)
                        except Exception:
                            res = None
                        if res:
                            st.session_state["asst_ems_result"] = res
                            rb = res["routes"][res["best_i"]]["pred"]
                            _submit(f"(系统已算出结果并展示给用户,不要再说'正在计算')最近急救站直线 "
                                    f"{res['sdist']/1000:.1f}km;模型预测最短路线到场 {rb['seconds']/60:.1f} 分,"
                                    f"分级 {rb['sec_bin']},共 {len(res['routes'])} 条候选。请用一两句话解读"
                                    f"(可达性好不好),并告诉用户想看多候选详细路线和沿途变量可进入功能页。",
                                    key, hidden=True)
                        else:
                            _submit(f"我在地图上选定了位置 {p[0]},{p[1]},但未能算出结果(可能AK或网络问题)。", key)
                    else:
                        inside = "" if in_shanghai(*p) else "(注意:似乎不在上海范围)"
                        _submit(f"我在地图上选定了位置:经度 {p[0]}、纬度 {p[1]}{inside}。", key)

    if action.get("type") == "navigate":
        m = pm.get_module(action.get("page"))
        label = f"前往「{m['title']}」页" if m else "前往对应功能页"
        st.success("已为你匹配好功能,可带参数跳转:")
        if st.button("🚀 " + label + "(已预填可用参数)", type="primary"):
            _do_navigate(action)

    # —— 输入框 ——
    text = st.chat_input("说说你想做什么…")
    if text:
        _submit(text, key)
