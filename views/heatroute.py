# -*- coding: utf-8 -*-
"""健康风险:凉爽路径规划(统一入口,两种模式)。

- 全市 · 百度路线:百度 directionlite 路线 + 沿路 100m 实测 LST 热暴露 + 凉爽途经点绕行。
- 中心城区 · 绿荫路网:街景路网上多目标最短路(距离 + 低温 LST + 绿视率 S_veget 加权)。
共享起终点(地图点选 / 地址搜索)。引擎 heatroute.py(百度+LST)、roadnet.py(图路由)。
"""
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

import heatroute
import roadnet
from geo import _add_basemap
from theme import page_header

_SH = (120.85, 30.67, 122.05, 31.90)
ROUTE_STYLE = {"最短": ("#8a8a8a", 4), "最凉": ("#2C7BB6", 4),
               "最荫": ("#2E9E5B", 4), "自定义": ("#E8731F", 7)}


def _get_ak():
    try:
        return st.secrets.get("baidu_ak", "") or ""
    except Exception:
        return ""


def _in_sh(p):
    return bool(p) and _SH[0] <= p[0] <= _SH[2] and _SH[1] <= p[1] <= _SH[3]


def _pick_map(o, d, bbox=None):
    m = folium.Map(location=[31.24, 121.47], zoom_start=12, tiles=None, control_scale=True)
    _add_basemap(m, "浅色地图")
    if bbox:
        folium.Rectangle([[bbox[1], bbox[0]], [bbox[3], bbox[2]]], color="#2E9E5B",
                         weight=1, fill=False, dash_array="4,6", tooltip="绿荫路网覆盖范围").add_to(m)
    if o:
        folium.Marker([o[1], o[0]], tooltip="起点", icon=folium.Icon(color="green", icon="play")).add_to(m)
    if d:
        folium.Marker([d[1], d[0]], tooltip="终点", icon=folium.Icon(color="red", icon="stop")).add_to(m)
    return m


# ───────────────────────── 全市 · 百度路线 ─────────────────────────
def _baidu_result_map(routes, o, d):
    """各路线按沿路实测 LST 分段着色,推荐路线加绿色光晕 + 徽标。"""
    import branca.colormap as cm
    m = folium.Map(location=[31.23, 121.47], zoom_start=13, tiles=None, control_scale=True)
    _add_basemap(m, "浅色地图")
    all_lst = [z for r in routes for (_, _, z) in r["heat"]["samples"] if z is not None]
    if all_lst:
        vmin, vmax = float(np.percentile(all_lst, 5)), float(np.percentile(all_lst, 95))
        if vmax - vmin < 3:
            vmin, vmax = vmin - 1.5, vmax + 1.5
    else:
        vmin, vmax = 38.0, 52.0
    cmap = cm.LinearColormap(["#2C7BB6", "#7FCDBB", "#FFFFBF", "#FDAE61", "#D7191C"],
                             vmin=vmin, vmax=vmax, caption="沿路地表温度 LST (°C)")

    def col(z):
        return "#9e9e9e" if z is None else cmap(min(max(z, vmin), vmax))

    cool_i = int(np.argmin([r["heat"]["mean_lst"] for r in routes]))
    folium.PolyLine([(p[1], p[0]) for p in routes[cool_i]["heat"]["samples"]],
                    color="#1B6B3A", weight=13, opacity=0.30).add_to(m)
    for i, r in enumerate(routes):
        pts = r["heat"]["samples"]
        if len(pts) < 2:
            continue
        is_cool = (i == cool_i); w = 6 if is_cool else 4
        step = max(1, len(pts) // 150)
        for k in range(0, len(pts) - 1, step):
            a = pts[k]; b = pts[min(k + step, len(pts) - 1)]
            z = a[2] if a[2] is not None else b[2]
            folium.PolyLine([(a[1], a[0]), (b[1], b[0])], color=col(z), weight=w,
                            opacity=0.95 if is_cool else 0.7).add_to(m)
        mid = pts[len(pts) // 2]; bg = "#1B6B3A" if is_cool else "#555"
        folium.Marker([mid[1], mid[0]], icon=folium.DivIcon(html=(
            f"<div style='background:{bg};color:#fff;border-radius:10px;padding:1px 7px;"
            f"font-size:11px;font-weight:700;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.4)'>"
            f"{i+1}·{r['heat']['mean_lst']:.0f}°C{' 最凉' if is_cool else ''}</div>"),
            icon_size=(0, 0))).add_to(m)
    cmap.add_to(m)
    folium.Marker([o[1], o[0]], tooltip="起点", icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker([d[1], d[0]], tooltip="终点", icon=folium.Icon(color="red", icon="stop")).add_to(m)
    lats = [p[1] for r in routes for p in r["path"]]; lngs = [p[0] for r in routes for p in r["path"]]
    if lats:
        m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], padding=(30, 30))
    return m


def _baidu_section(o, d, ak):
    if not ak:
        st.info("「全市·百度路线」模式需要百度 AK(上方配置)。或切到「中心城区·绿荫路网」用地图点选,无需 AK。")
        return
    c1, c3 = st.columns([2, 1])
    mode = c1.radio("出行方式", ["步行", "骑行", "驾车"], horizontal=True, key="hr_mode")
    plan = c3.button("🧭 规划路线", type="primary", use_container_width=True,
                     disabled=not (_in_sh(o) and _in_sh(d)), key="hr_plan")
    add_detours = st.checkbox(
        "生成更凉绕行备选(两侧采样 LST 挑低温途经点;会多调几次百度 API)",
        value=(mode in ("步行", "骑行")), key="hr_detour",
        help="百度对步行/骑行常只返 1 条路线;勾选后用途经点强造更凉备选,代价是多调 API、里程略增。")

    if plan:
        try:
            with st.spinner("调用百度路线规划 + 计算热暴露…" + ("(含绕行备选,稍候)" if add_detours else "")):
                routes = heatroute.plan_cool_routes(o, d, mode_zh=mode, ak=ak,
                                                    add_detours=add_detours, n_detours=2)
                for r in routes:
                    r["heat"] = heatroute.route_heat(r["path"])
                seen, uniq = set(), []
                for r in routes:
                    if not np.isfinite(r["heat"]["mean_lst"]):
                        continue
                    key = (round((r["distance"] or 0) / 150), round(r["heat"]["mean_lst"], 1))
                    if key in seen:
                        continue
                    seen.add(key); uniq.append(r)
                direct = [r for r in uniq if r.get("kind") != "绕行"]
                detours = sorted([r for r in uniq if r.get("kind") == "绕行"],
                                 key=lambda r: r["heat"]["mean_lst"])
                uniq = direct + detours[:3]
                if not uniq:
                    st.warning("百度未返回可用路线,请换起终点或出行方式。")
                else:
                    bd_mean = min((r["heat"]["mean_lst"] for r in direct), default=9e9)
                    st.session_state["hr_routes"] = uniq
                    st.session_state["hr_n_detour"] = len(detours)
                    st.session_state["hr_detour_cooler"] = any(
                        r["heat"]["mean_lst"] < bd_mean - 0.3 for r in detours)
        except Exception as e:
            st.error(f"路线规划失败:{e}\n\n请检查 AK 是否有效、是否放开服务端调用(IP 白名单),"
                     "以及起终点是否在可达范围。")

    routes = st.session_state.get("hr_routes")
    if not routes:
        return
    cool_i = int(np.argmin([r["heat"]["mean_lst"] for r in routes]))
    fast_i = int(np.argmin([r["distance"] for r in routes]))
    cr = routes[cool_i]
    st.success(
        f"推荐**路线{cool_i+1}(最凉)**:沿路均温 {cr['heat']['mean_lst']:.1f}°C、"
        f"高温(>{heatroute.HOT_THRESHOLD:.0f}°C)路段 {cr['heat']['hot_len_m']:.0f}m、"
        f"全程 {cr['distance']/1000:.1f}km / {cr['duration']//60}分钟。"
        + ("" if cool_i == fast_i else f" 最短的是路线{fast_i+1}。"))
    nd = st.session_state.get("hr_n_detour", 0)
    if nd and not st.session_state.get("hr_detour_cooler"):
        st.info(f"已探索 {nd} 条绕行备选(地图上较细的线),均未比直达明显更凉——该区域热环境较均匀;"
                "在有公园/水体/绿廊处绕行更可能找到凉爽路线。")
    rows = []
    for i, r in enumerate(routes):
        h = r["heat"]; tag = []
        if i == cool_i: tag.append("最凉")
        if i == fast_i: tag.append("最短")
        rows.append({"路线": f"路线{i+1}", "类型": r.get("kind", "直达"), "标签": "/".join(tag) or "—",
                     "距离(km)": round(r["distance"] / 1000, 2), "时长(分)": int(r["duration"] // 60),
                     "均温(°C)": round(h["mean_lst"], 1), "最高(°C)": round(h["max_lst"], 1),
                     "高温路段(m)": int(h["hot_len_m"]), "累计暴露(°C·km)": round(h["exposure"] / 1000, 1)})
    colmap, coltab = st.columns([1.4, 1], gap="large")
    with colmap:
        st_folium(_baidu_result_map(routes, o, d), key="hr_result", width=None, height=460,
                  returned_objects=[])
        st.caption("线条**按沿路实测 LST 分段着色**(右下色带 🔵凉→🔴热);**推荐(最凉)**加绿色光晕+粗线,"
                   "其余较细线为**已探索备选**;徽标=编号·均温;绿/红标记为起/终点。")
    with coltab:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("**累计暴露** = 沿路 ∫LST·路程(°C·km),综合温度与里程;越低越凉。热暴露对**步行/骑行**最有意义。")
    grid = np.linspace(0, 100, 60); prof = {}
    for i, r in enumerate(routes):
        samp = r["heat"]["samples"]; dist = np.array(r["heat"].get("dist", []))
        lst = np.array([s[2] if s[2] is not None else np.nan for s in samp], float)
        if len(dist) != len(lst) or len(dist) < 2 or dist[-1] <= 0:
            continue
        valid = np.isfinite(lst)
        if valid.sum() < 2:
            continue
        prof[f"路线{i+1}"] = np.interp(grid, (dist / dist[-1] * 100.0)[valid], lst[valid])
    if prof:
        dfp = pd.DataFrame(prof, index=np.round(grid).astype(int)); dfp.index.name = "路程(%)"
        st.markdown("**沿程地表温度剖面 · 各路线对比**")
        st.line_chart(dfp, height=240)
        st.caption("横轴=路程百分比,纵轴=该位置实测 LST(°C);曲线整体越低越凉,有红峰处=途经高温段。")


# ───────────────────────── 中心城区 · 绿荫路网 ─────────────────────────
def _roadnet_result_map(routes, o, d):
    m = folium.Map(location=[31.24, 121.48], zoom_start=13, tiles=None, control_scale=True)
    _add_basemap(m, "浅色地图")
    for lab in ["最短", "最凉", "最荫", "自定义"]:
        r = routes.get(lab)
        if not r:
            continue
        col, w = ROUTE_STYLE[lab]
        folium.PolyLine([(la, ln) for ln, la in r["coords"]], color=col, weight=w,
                        opacity=0.9 if lab == "自定义" else 0.6,
                        tooltip=f"{lab}:{r['length_m']:.0f}m · 均温{r['mean_lst']:.1f}°C · "
                                f"绿视{r['mean_veg']:.2f}").add_to(m)
    folium.Marker([o[1], o[0]], tooltip="起点", icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker([d[1], d[0]], tooltip="终点", icon=folium.Icon(color="red", icon="stop")).add_to(m)
    lats = [p[1] for r in routes.values() if r for p in r["coords"]]
    lngs = [p[0] for r in routes.values() if r for p in r["coords"]]
    if lats:
        m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], padding=(30, 30))
    return m


def _roadnet_section(o, d):
    o_ok = bool(o) and roadnet.in_network(*o); d_ok = bool(d) and roadnet.in_network(*d)
    c1, c2, c3 = st.columns([1.4, 1.4, 1])
    w_heat = c1.slider("低温权重(避热)", 0.0, 3.0, 1.5, 0.5, key="rr_wheat",
                       help="越大越倾向走地表温度低的路,可能绕远")
    w_shade = c2.slider("绿荫权重(遮荫)", 0.0, 3.0, 1.5, 0.5, key="rr_wshade",
                        help="越大越倾向走绿视率高、遮荫好的路")
    plan = c3.button("🧭 规划路径", type="primary", use_container_width=True,
                     disabled=not (o_ok and d_ok), key="rr_plan")
    if (o and not o_ok) or (d and not d_ok):
        st.caption("⚠️ 起点或终点不在绿荫路网范围内(虚线框),请在框内选点,或改用「全市·百度路线」。")

    if plan:
        with st.spinner("多目标最短路求解中…"):
            routes = {lab: roadnet.route(o, d, wh, ws) for lab, wh, ws in roadnet.PRESETS}
            routes["自定义"] = roadnet.route(o, d, w_heat, w_shade)
            st.session_state["rr_routes"] = {k: v for k, v in routes.items() if v}

    routes = st.session_state.get("rr_routes")
    if not routes:
        return
    cust = routes.get("自定义")
    if cust:
        base = routes.get("最短")
        extra = (cust["length_m"] - base["length_m"]) if base else 0
        st.success(
            f"自定义方案(低温权重 {w_heat}、绿荫权重 {w_shade}):{cust['length_m']:.0f}m、"
            f"沿路均温 {cust['mean_lst']:.1f}°C、平均绿视率 {cust['mean_veg']:.2f}、遮荫路段 "
            f"{cust['shade_ratio']*100:.0f}%" + (f",比最短路多走 {extra:.0f}m。" if base else "。"))
    colmap, coltab = st.columns([1.5, 1], gap="large")
    with colmap:
        st_folium(_roadnet_result_map(routes, o, d), key="rr_result", width=None, height=460,
                  returned_objects=[])
        st.caption("⬛最短　🔵最凉　🟢最荫　🟠自定义(加粗)。绿/红标记为起/终点。")
    with coltab:
        rows = []
        for lab in ["最短", "最凉", "最荫", "自定义"]:
            r = routes.get(lab)
            if not r:
                continue
            rows.append({"方案": lab, "距离(m)": int(r["length_m"]), "均温(°C)": round(r["mean_lst"], 1),
                         "平均绿视率": round(r["mean_veg"], 3), "遮荫路段(%)": int(r["shade_ratio"] * 100)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("均温=沿路实测 LST(长度加权);绿视率/遮荫来自街景 S_veget(越高越荫凉)。")


# ───────────────────────── 统一页面 ─────────────────────────
def page_heatroute():
    page_header(
        "健康风险 · 清凉路径规划",
        "给定起终点,评估并对比凉爽出行路线。两种模式:**全市·百度路线**(实路网 + 沿路实测 LST 热暴露)、"
        "**中心城区·绿荫路网**(街景路网上 距离+低温+绿视率 加权的多目标最短路)。")

    engine = st.radio("规划模式", ["全市 · 百度路线(热暴露)", "中心城区 · 绿荫路网(热+绿荫)"],
                      horizontal=True, key="hr_engine")
    is_road = engine.startswith("中心城区")

    ak = _get_ak()
    if not ak:
        ak = st.text_input("百度地图 AK(百度路线 / 地址搜索需要;绿荫路网点选不需要)", type="password",
                           help="写入 .streamlit/secrets.toml 的 baidu_ak;云端在 Secrets 配置。AK 需放开服务端调用。")

    # 地址搜索(共享,需 AK)
    with st.expander("🔍 用地址搜索起终点", expanded=False):
        ac1, ac2, ac3 = st.columns([2, 2, 1])
        addr_o = ac1.text_input("起点地址", key="hr_addr_o", placeholder="如:同济大学")
        addr_d = ac2.text_input("终点地址", key="hr_addr_d", placeholder="如:鲁迅公园")
        ac3.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if ac3.button("📍 定位", use_container_width=True, disabled=not ak):
            try:
                msgs = []
                if addr_o.strip():
                    lng, lat, info = heatroute.geocode(addr_o, ak, return_raw=True)
                    st.session_state["hr_o"] = (round(lng, 6), round(lat, 6)); msgs.append(f"起点→{info['name']}")
                if addr_d.strip():
                    lng, lat, info = heatroute.geocode(addr_d, ak, return_raw=True)
                    st.session_state["hr_d"] = (round(lng, 6), round(lat, 6)); msgs.append(f"终点→{info['name']}")
                st.session_state["hr_geomsg"] = "　|　".join(msgs)
                st.session_state.pop("hr_routes", None); st.session_state.pop("rr_routes", None)
                st.rerun()
            except Exception as e:
                st.error(f"地址解析失败:{e}")
        if not ak:
            st.caption("配置 AK 后可用地址搜索;否则直接在下方地图点选起终点。")
        elif st.session_state.get("hr_geomsg"):
            st.caption("✅ 已定位　" + st.session_state["hr_geomsg"])

    if st.button("🗑 清除起终点"):
        for k in ("hr_o", "hr_d", "hr_routes", "rr_routes", "hr_lastclick", "hr_geomsg"):
            st.session_state.pop(k, None)
        st.rerun()

    o = st.session_state.get("hr_o"); d = st.session_state.get("hr_d")
    tip = "点击地图选**起点**" if not o else ("点击地图选**终点**" if not d else "起终点已设")
    st.caption(f"📍 {tip}　|　起点 {('%.4f,%.4f' % (o[1],o[0])) if o else '—'}　终点 "
               f"{('%.4f,%.4f' % (d[1],d[0])) if d else '—'}")

    bbox = roadnet.meta()["bbox"] if is_road else None
    out = st_folium(_pick_map(o, d, bbox), key="hr_pick", width=None, height=360,
                    returned_objects=["last_clicked"])
    lc = out.get("last_clicked") if out else None
    if lc:
        p = (round(lc["lng"], 6), round(lc["lat"], 6))
        if st.session_state.get("hr_lastclick") != p:
            st.session_state["hr_lastclick"] = p
            if not st.session_state.get("hr_o"):
                st.session_state["hr_o"] = p
            elif not st.session_state.get("hr_d"):
                st.session_state["hr_d"] = p
            else:
                st.session_state["hr_o"] = p; st.session_state["hr_d"] = None
            st.session_state.pop("hr_routes", None); st.session_state.pop("rr_routes", None)
            st.rerun()

    if is_road:
        _roadnet_section(o, d)
    else:
        _baidu_section(o, d, ak)
