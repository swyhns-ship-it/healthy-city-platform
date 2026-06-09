# -*- coding: utf-8 -*-
"""健康资源:纳凉设施布局优化(MCLP 最大覆盖选址 + 街道公平性)。"""
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

import cooling_mclp
from geo import _add_basemap, _lerp_hex
from theme import HEALTH_GREEN, GREEN_DEEP, page_header


@st.cache_data(show_spinner=False)
def _cooling_base(cover, scheme):
    return cooling_mclp.base_stats(cover, scheme)


@st.cache_data(show_spinner="正在求解 MCLP…")
def _cooling_solve(cover, scheme, K, alpha):
    return cooling_mclp.solve(cover, scheme, K, alpha)


@st.cache_data(show_spinner="正在批量求解各 K…")
def _cooling_sweep(cover, scheme, alpha):
    return cooling_mclp.sweep(cover, scheme, alpha=alpha)


@st.cache_resource(show_spinner=False)
def _cooling_geojson():
    import json, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # views/ 的上一级=仓库根
    p = os.path.join(root, "cooling_jiedao.geojson")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _cov_color(v, lo, hi):
    """街道覆盖率配色:浅绿(低)→深绿(高);无数据灰。"""
    if v is None or not np.isfinite(v):
        return "#DDDDDD"
    t = (v - lo) / (hi - lo + 1e-9)
    return _lerp_hex("#EAF7EF", GREEN_DEEP, min(max(t, 0.0), 1.0))


def build_cooling_map(res, show_existing=False, basemap="街道地图"):
    """纳凉设施选址地图:街道覆盖率 choropleth + 新增选址(★+服务圈)+(可选)现状点。"""
    m = folium.Map(location=[31.17, 121.45], zoom_start=10, tiles=None, control_scale=True)
    _add_basemap(m, basemap)

    # 街道覆盖率 choropleth(优化后)
    sa = res["street_after"]; sb = res["street_before"]
    vals = [v for v in sa.values() if np.isfinite(v)]
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 1.0)
    gj = _cooling_geojson()
    feats = []
    for f in gj["features"]:
        nm = f["properties"]["NAME"]
        cb, ca = sb.get(nm), sa.get(nm)
        feats.append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "NAME": nm,
            "优化前": "—" if cb is None or not np.isfinite(cb) else f"{cb*100:.1f}%",
            "优化后": "—" if ca is None or not np.isfinite(ca) else f"{ca*100:.1f}%"}})
    folium.GeoJson(
        {"type": "FeatureCollection", "features": feats},
        style_function=lambda ft: {
            "fillColor": _cov_color(sa.get(ft["properties"]["NAME"]), lo, hi),
            "color": "#9ec7ad", "weight": 0.5, "fillOpacity": 0.72},
        highlight_function=lambda ft: {"weight": 2, "color": HEALTH_GREEN},
        tooltip=folium.GeoJsonTooltip(fields=["NAME", "优化前", "优化后"],
                                      aliases=["街道", "优化前", "优化后"])).add_to(m)

    # 现状纳凉点(抽样,避免 1.1 万点卡顿)
    if show_existing:
        cl = cooling_mclp._state()["cool_ll"]
        step = max(1, len(cl) // 1500)
        for lon, lat in cl[::step]:
            folium.CircleMarker([lat, lon], radius=1.2, color="#7a7a7a", weight=0,
                                fill=True, fill_color="#7a7a7a", fill_opacity=0.5).add_to(m)

    # 新增覆盖的小区(蓝点)
    s = cooling_mclp._state()
    if len(res["newly_idx"]):
        for lon, lat in s["res_ll"][res["newly_idx"]]:
            folium.CircleMarker([lat, lon], radius=2, color="#1f6feb", weight=0,
                                fill=True, fill_color="#1f6feb", fill_opacity=0.7).add_to(m)

    # 新增选址点:★ + 服务圈
    for (lon, lat), jd in zip(res["sel_ll"], res["sel_jd"]):
        folium.Circle([lat, lon], radius=res["cover_dist"], color="#E8731F", weight=1,
                      fill=True, fill_color="#E8731F", fill_opacity=0.08).add_to(m)
        folium.Marker(
            [lat, lon],
            icon=folium.DivIcon(
                html="<div style='font-size:20px;line-height:20px;color:#E8731F;"
                     "text-shadow:0 0 3px #fff,0 0 2px #000'>★</div>",
                icon_size=(20, 20), icon_anchor=(10, 10)),
            tooltip=f"新增纳凉点 · {jd}").add_to(m)
    return m


def page_cooling_layout():
    """健康资源 · 纳凉设施布局优化(MCLP 最大覆盖选址 + 街道公平性)。"""
    page_header(
        "健康资源 · 纳凉设施布局优化",
        "基于上海 11,383 处现状纳凉点、16,337 个小区(需求点)与 230 个街道,用 MCLP"
        "(最大覆盖选址)优化新增纳凉设施位置。可调覆盖半径、需求权重、新增数量 K 与街道公平性 α,"
        "现场求解(整数规划),展示覆盖率提升与街道公平性变化。")

    c1, c2, c3 = st.columns(3)
    with c1:
        cover = st.slider("覆盖半径(米)", 300, 1000, 500, 50,
                          help="居民到最近纳凉点的可接受步行距离")
    with c2:
        scheme = st.selectbox("需求权重方案", list(cooling_mclp.WEIGHT_SCHEMES.keys()),
                              format_func=lambda k: cooling_mclp.WEIGHT_SCHEMES[k],
                              help="按何种指标衡量一个小区被覆盖的价值")
    with c3:
        alpha = st.slider("街道公平性权重 α", 0.0, 1.0, 0.0, 0.1,
                          help="0=纯总覆盖最大化;越大越向覆盖率最低的街道倾斜")

    base = _cooling_base(cover, scheme)
    st.caption(f"现状(不新增):加权覆盖率 **{base['coverage']*100:.2f}%**、"
               f"按数覆盖 {base['count_coverage']*100:.1f}%({base['n_covered']:,}/{base['n_res']:,} 小区)、"
               f"街道公平性 Gini {base['gini']:.3f}。")

    tab1, tab2 = st.tabs(["单方案求解 · 选址地图", "K 扫描 · 边际效益与拐点"])

    with tab1:
        K = st.slider("新增纳凉设施数量 K", 1, 50, 10, 1, key="cool_K")
        res = _cooling_solve(cover, scheme, int(K), alpha)
        d_cov = (res["coverage_after"] - res["coverage_before"]) * 100
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("加权覆盖率", f"{res['coverage_after']*100:.2f}%", delta=f"{d_cov:+.2f} pct")
        m2.metric("覆盖小区数", f"{res['count_after']:,}",
                  delta=f"+{res['count_after'] - res['count_before']:,}")
        m3.metric("街道公平性 Gini", f"{res['gini_after']:.3f}",
                  delta=f"{res['gini_after'] - res['gini_before']:+.3f}", delta_color="inverse")
        m4.metric("新增覆盖小区", f"{res['n_newly']:,} 个")

        colmap, colside = st.columns([1.5, 1], gap="large")
        with colmap:
            cc1, cc2 = st.columns([1, 1])
            with cc1:
                bm = st.selectbox("底图", ["街道地图", "浅色地图"], key="cool_base",
                                  label_visibility="collapsed")
            with cc2:
                show_ex = st.checkbox("叠加现状纳凉点(抽样)", value=False, key="cool_ex")
            st_folium(build_cooling_map(res, show_ex, bm), key="cool_map",
                      width=None, height=540, returned_objects=[])
            st.caption("街道填色=优化后加权覆盖率(越绿越高)。🟠★ 新增选址 + 500m 服务圈;"
                       "🔵 新增覆盖的小区。鼠标悬停街道看优化前后覆盖率。")
        with colside:
            st.markdown("**覆盖率提升最大的街道**")
            sb, sa = res["street_before"], res["street_after"]
            rows = []
            for nm in sa:
                if np.isfinite(sa[nm]) and np.isfinite(sb.get(nm, np.nan)):
                    rows.append({"街道": nm, "优化前": sb[nm], "优化后": sa[nm],
                                 "提升": sa[nm] - sb[nm]})
            df = pd.DataFrame(rows).sort_values("提升", ascending=False).head(10)
            df["优化前"] = (df["优化前"] * 100).round(1)
            df["优化后"] = (df["优化后"] * 100).round(1)
            df["提升"] = (df["提升"] * 100).round(2)
            st.dataframe(df.reset_index(drop=True), hide_index=True, use_container_width=True,
                         height=388)
            st.markdown("**本次选址街道**")
            st.caption("、".join(res["sel_jd"]))

    with tab2:
        st.caption("固定上面的覆盖半径/权重/α,扫描 K=5…45,看边际覆盖增量与街道公平性如何随 K 变化,"
                   "并自动识别「拐点」给出建议 K。")
        rows = _cooling_sweep(cover, scheme, alpha)
        ek = cooling_mclp.elbow_k(rows)
        df = pd.DataFrame(rows)
        df["覆盖率%"] = (df["coverage"] * 100).round(2)
        df["边际增量%"] = (df["marginal"] * 100).round(2)
        df["街道Gini"] = df["gini"].round(3)
        st.success(f"拐点建议:新增约 **K = {ek}** 个,之后边际覆盖增量明显递减。")
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**K vs 加权覆盖率**")
            st.line_chart(df.set_index("K")["覆盖率%"], height=240)
        with g2:
            st.markdown("**各 K 的边际覆盖增量**")
            st.bar_chart(df.set_index("K")["边际增量%"], height=240)
        st.markdown("**K vs 街道公平性 Gini**(越低越公平)")
        st.line_chart(df.set_index("K")["街道Gini"], height=220)
        st.dataframe(df[["K", "覆盖率%", "边际增量%", "街道Gini"]], hide_index=True,
                     use_container_width=True)

    with st.expander("模型与方法(MCLP + 街道公平性)", expanded=False):
        st.markdown(
            "- **模型**:最大覆盖选址问题(Maximal Covering Location Problem),整数规划,PuLP/CBC 求解。\n"
            "- **需求点**:16,337 个小区质心,权重可选 健康脆弱度 / 人口 / 地表温度 / 均等。\n"
            "- **覆盖**:小区到任一纳凉点 ≤ 覆盖半径 即视为被覆盖;现状 11,383 处纳凉点先确定已覆盖部分。\n"
            "- **候选点**:未覆盖小区质心 + 街道质心,200m 去重(约 1,400+ 个)。\n"
            "- **目标**:`max (1-α)·Σ wᵢyᵢ + α·min_d(街道覆盖率)`,约束新增设施数 = K。\n"
            "  α>0 时加入街道公平性软约束,牺牲少量总覆盖换取最弱街道的覆盖提升。\n"
            "- **公平性度量**:各街道加权覆盖率的 Gini 系数(越低越均衡)。\n"
            "- 数据为上海实测,模型用于规划阶段的设施布局**辅助研判**,非最终选址依据。")
