# -*- coding: utf-8 -*-
"""健康风险:中暑病例风险地图(2013–2025 上海实测病例)。

三图层(热力图 / 病例点 / 街道重症比例)+ 多维筛选 + 统计面板。
数据引擎 heatcase.py;街道边界复用 cooling_jiedao.geojson。
"""
import json
import os

import numpy as np
import pandas as pd
import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

import heatcase
from geo import _add_basemap, _lerp_hex
from theme import HEALTH_GREEN, GREEN_DEEP, page_header

SEV_MAP = {"重症": 1, "轻症": 0}
SEX_MAP = {"男": 0, "女": 1}
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@st.cache_resource(show_spinner=False)
def _jiedao_geojson():
    with open(os.path.join(_ROOT, "cooling_jiedao.geojson"), encoding="utf-8") as f:
        return json.load(f)


def _ratio_color(r):
    """重症比例 0→1:浅黄→深红;无数据灰。"""
    if r is None or not np.isfinite(r):
        return "#E0E0E0"
    return _lerp_hex("#FFF4D6", "#C0392B", min(max(r, 0), 1))


def _count_color(v, vmax):
    if v <= 0:
        return "#EEEEEE"
    return _lerp_hex("#EAF7EF", GREEN_DEEP, min(v / (vmax + 1e-9), 1))


def _build_map(f, mlon, mlat, sel, layer, metric, basemap):
    """f=全部匹配病例(choropleth 用);mlon/mlat/sel=上图子集(热力图/点用)。"""
    m = folium.Map(location=[31.17, 121.45], zoom_start=10, tiles=None, control_scale=True)
    _add_basemap(m, basemap)

    if layer == "病例热力图":
        sev = f["severe"][sel]
        w = np.where(sev == 1, 1.8, 1.0)                    # 重症权重略高
        data = [[float(la), float(lo), float(ww)] for la, lo, ww in zip(mlat, mlon, w)]
        if data:
            HeatMap(data, radius=10, blur=14, min_opacity=0.2, max_zoom=13,
                    gradient={0.3: "#2C7BB6", 0.55: "#FFFFBF", 0.8: "#FDAE61",
                              1.0: "#D7191C"}).add_to(m)

    elif layer == "病例点分布":
        sev = f["severe"][sel]; dth = f["death"][sel]; age = f["age"][sel]; yr = f["year"][sel]
        n = len(mlon)
        order = np.arange(n) if n <= 2500 else np.linspace(0, n - 1, 2500).astype(int)
        for i in order:
            if dth[i] == 1:
                col, r = "#111111", 3.2
            elif sev[i] == 1:
                col, r = "#D7191C", 2.6
            else:
                col, r = "#2C7BB6", 2.2
            folium.CircleMarker(
                [float(mlat[i]), float(mlon[i])], radius=r, color=col, weight=0,
                fill=True, fill_color=col, fill_opacity=0.65,
                tooltip=f"{int(yr[i])}年 · {'重症' if sev[i] else '轻症'}"
                        f"{' · 死亡' if dth[i] else ''} · {int(age[i])}岁"
            ).add_to(m)

    else:  # 街道重症比例 / 病例数 choropleth(用全部病例,粗定位也落在正确街道)
        cnt, sev = heatcase.jiedao_agg(f["jd"], f["severe"])
        vmax = int(cnt.max()) if cnt.max() > 0 else 1
        gj = _jiedao_geojson()
        feats = []
        for ft in gj["features"]:
            j = ft["properties"]["idx"]; nm = ft["properties"]["NAME"]
            c = int(cnt[j]); sv = int(sev[j])
            rr = (sv / c) if c >= 3 else None          # <3 例比例不稳,置灰
            fill = _ratio_color(rr) if metric == "重症比例" else _count_color(c, vmax)
            feats.append({"type": "Feature", "geometry": ft["geometry"], "properties": {
                "NAME": nm, "病例数": c, "重症数": sv, "_fill": fill,
                "重症比例": "—" if rr is None else f"{rr*100:.0f}%"}})
        folium.GeoJson(
            {"type": "FeatureCollection", "features": feats},
            style_function=lambda ftr: {"fillColor": ftr["properties"]["_fill"],
                                        "color": "#bbb", "weight": 0.5, "fillOpacity": 0.72},
            highlight_function=lambda ft: {"weight": 2, "color": HEALTH_GREEN},
            tooltip=folium.GeoJsonTooltip(fields=["NAME", "病例数", "重症数", "重症比例"],
                                          aliases=["街道", "病例数", "重症数", "重症比例"])).add_to(m)
    return m


def page_heatcase_map():
    page_header(
        "健康风险 · 中暑病例风险地图",
        "2013–2025 年上海高温中暑病例监测实测数据(5,349 例)。按年份/严重程度/人群/职业筛选,"
        "以热力图、病例点、街道重症比例三种方式可视化热相关健康风险的空间分布。"
        "与「热相关重症风险」页(模型推断)互补:此页为实证病例分布。")

    mt = heatcase.meta()
    occ_labels = mt["occ_labels"]

    with st.expander("筛选条件", expanded=True):
        prec_zh = st.radio(
            "地理编码精度(仅影响热力图/病例点)", ["仅精确定位(推荐)", "全部(含街镇中心点)"],
            horizontal=True,
            help="地址粗到“乡镇/区县”会被吸附到同一中心点造成虚假热点,故热力图/病例点默认只用"
                 f"精确定位(门址/小区/道路/POI 等)的 {mt['n_precise']:,} 例。"
                 "统计指标与街道聚合不受此影响,始终用全部病例。")
        precise_only = prec_zh.startswith("仅精确")
        c1, c2, c3 = st.columns(3)
        basis_zh = c1.radio("坐标基准", ["现住地", "中暑发生地"], horizontal=True,
                            help=f"现住地全有({mt['n']:,});中暑发生地仅 {mt['n_onset']:,} 例有坐标")
        yrs = c2.slider("年份范围", mt["year_min"], mt["year_max"],
                        (mt["year_min"], mt["year_max"]))
        death_only = c3.checkbox("仅看死亡病例", help=f"全市共 {mt['n_death']} 例死亡")
        c4, c5 = st.columns(2)
        sev_zh = c4.multiselect("严重程度", ["重症", "轻症"], default=["重症", "轻症"])
        sex_zh = c5.multiselect("性别", ["男", "女"], default=["男", "女"])
        ages_zh = st.multiselect("年龄段", [g[2] for g in heatcase.AGE_GROUPS],
                                 default=[g[2] for g in heatcase.AGE_GROUPS])
        occ_zh = st.multiselect("职业", occ_labels, default=occ_labels)

    f = heatcase.filter_cases(
        years=yrs,
        severe=tuple(SEV_MAP[s] for s in sev_zh) or (0, 1),
        sexes=tuple(SEX_MAP[s] for s in sex_zh) or (0, 1),
        age_groups=[(g[0], g[1]) for g in heatcase.AGE_GROUPS if g[2] in ages_zh],
        occs=[occ_labels.index(o) for o in occ_zh],
        death_only=death_only)

    n = f["n"]
    nsev = int(f["severe"].sum()); ndth = int(f["death"].sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("筛选后病例数", f"{n:,}")
    m2.metric("重症占比", f"{(nsev/n*100) if n else 0:.1f}%", help=f"重症 {nsev:,} 例")
    m3.metric("死亡病例", f"{ndth:,}")
    st.caption("以上指标、右侧统计、街道聚合均基于**全部**匹配病例;热力图/病例点另按地理编码精度过滤。")

    if n == 0:
        st.warning("当前筛选条件下无病例,请放宽条件。")
        return

    basis = "onset" if basis_zh == "中暑发生地" else "home"
    mlon, mlat, sel = heatcase.map_points(f, basis=basis, precise_only=precise_only)
    n_map = len(mlon)

    layer = st.radio("地图图层", ["病例热力图", "病例点分布", "街道重症比例"], horizontal=True)
    colmap, colstat = st.columns([1.6, 1], gap="large")
    with colmap:
        cc1, cc2 = st.columns([1, 1])
        bm = cc1.selectbox("底图", ["浅色地图", "街道地图"], key="hc_base",
                           label_visibility="collapsed")
        metric = "重症比例"
        if layer == "街道重症比例":
            metric = cc2.selectbox("着色指标", ["重症比例", "病例数"], key="hc_metric",
                                   label_visibility="collapsed")
        st_folium(_build_map(f, mlon, mlat, sel, layer, metric, bm), key="hc_map",
                  width=None, height=540, returned_objects=[])
        legend = {"病例热力图": f"🔵低 → 🔴高 病例密度(重症加权)。上图 {n_map:,} 个"
                              f"{'精确定位' if precise_only else ''}点(共 {n:,} 例,"
                              f"{'粗定位不上图但计入统计' if precise_only else '含粗定位'})。",
                  "病例点分布": f"🔴 重症　🔵 轻症　⚫ 死亡;点击看年份/严重度/年龄。上图 {n_map:,} 点"
                              f"{'(仅精确定位)' if precise_only else ''},超 2500 抽样。",
                  "街道重症比例": "按**现住地**街道聚合(用全部病例);填色=重症比例(<3 例置灰)或病例数。悬停看明细。"}
        st.caption(legend[layer])
    with colstat:
        st.markdown("**年度病例趋势**")
        yc = pd.Series(f["year"]).value_counts().sort_index()
        st.bar_chart(yc, height=180)
        st.markdown("**年龄段构成**")
        ag = []
        for lo, hi, lab in heatcase.AGE_GROUPS:
            ag.append({"年龄段": lab, "病例数": int(((f["age"] >= lo) & (f["age"] <= hi)).sum())})
        st.bar_chart(pd.DataFrame(ag).set_index("年龄段")["病例数"], height=170)
        st.markdown("**职业构成(前 6)**")
        oc = pd.Series([occ_labels[int(o)] for o in f["occ"]]).value_counts().head(6)
        st.dataframe(oc.rename("病例数").reset_index().rename(columns={"index": "职业"}),
                     hide_index=True, use_container_width=True, height=240)

    with st.expander("数据与说明", expanded=False):
        st.markdown(
            "- **数据**:2013–2025 年上海市高温中暑病例监测,经纬度地理编码(WGS84),"
            f"上海范围内 {mt['n']:,} 例(已剔除市外异常坐标)。\n"
            "- **严重程度**:按「中暑诊断」分重症 / 轻症;重症亚型含热射病 / 热痉挛 / 热衰竭 / 混合型。\n"
            "- **坐标基准**:默认现住地(全有);「中暑发生地」仅部分病例有坐标,更贴近暴露地点但样本少。\n"
            "- **街道聚合**:归入与纳凉设施同一套 230 街道边界;重症比例 <3 例的街道置灰(样本太小不稳)。\n"
            "- 本页为**实证病例分布**,反映报告与人口分布,非发病率(未除以人口);用于风险研判,非精确定点。")
