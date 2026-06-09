# -*- coding: utf-8 -*-
"""健康风险:热相关重症风险诊断(局部建成环境 → LST → 重症化风险)。"""
import numpy as np
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium

import green_lst
import heat_risk
from geo import _add_basemap, add_drisk_grid
from theme import page_header


VAR_ZH_HEAT = {"MODIS_LST": "当天地表温度", "dw_built": "建成密度",
               "dis_ems": "到最近急救站距离"}
VAR_DIR_HEAT = {"MODIS_LST": "越热→越重", "dw_built": "越密→越重",
                "dis_ems": "越远→越重"}


@st.cache_data(show_spinner=False)
def _poly_means_cached(poly_key):
    return green_lst.polygon_means([list(p) for p in poly_key])


@st.cache_data(show_spinner=False)
def _chain_cached(poly_key, targets_key):
    poly = [list(p) for p in poly_key]
    targets = dict(targets_key)
    f = green_lst.compute_lst_delta(poly, targets=targets)
    if f.get("n_cells", 0) == 0:
        return f
    sd = heat_risk.severity_delta(f["rows"], f["cols"], f["dlst"])
    return {"lat": f["lat"], "lon": f["lon"], "dlst": f["dlst"], "inside": f["inside"],
            "drisk": sd["drisk"], "dlst_mean_inside": f["dlst_mean_inside"],
            "dlst_min": f["dlst_min"], "dlst_max": f["dlst_max"],
            "mean_drisk": sd["mean_drisk"], "min_drisk": sd["min_drisk"],
            "area_down_ha": sd["area_down_ha"], "n_cells": f["n_cells"]}


def _heat_diag():
    """① 风险诊断:局部建成环境 → 地表温度 → 重症化风险(同一张图)。"""
    st.caption("在地图上画一个地块,系统显示该地块 LST 模型自变量的现状值;拖动滑块设定改造目标"
               "(绿地占比 / 建筑密度 / 容积率),经上海 100m 地表温度模型算 ΔLST(含空间外溢),"
               "再按重症模型 LST 系数(每 +1°C 约 OR 1.12)换算重症化概率变化,结果叠加在同一张图上。")

    SLV = [("greenfrac", "绿地占比", 0.0, 1.0, 0.02, "%.2f"),
           ("dw_built", "建筑密度", 0.0, 1.0, 0.02, "%.2f"),
           ("FAR_proxy", "容积率代理", 0.0, 15.0, 0.2, "%.1f")]
    colmap, colctl = st.columns([1.5, 1], gap="large")

    res = st.session_state.get("heat_chain")
    cp = st.session_state.get("heat_chain_poly")
    with colmap:
        rm = folium.Map(location=[31.17, 121.45], zoom_start=10, tiles=None, control_scale=True)
        _add_basemap(rm, "浅色地图")
        Draw(draw_options={"polyline": False, "circle": False, "marker": False,
                           "circlemarker": False, "rectangle": True, "polygon": True},
             edit_options={"edit": False}, export=False).add_to(rm)
        if res is not None and res.get("n_cells", 0) > 0:
            add_drisk_grid(rm, res["lat"], res["lon"], res["drisk"])
        if cp:
            folium.Polygon(locations=[[p[1], p[0]] for p in cp], color="#1B6B3A",
                           weight=2.5, fill=False, dash_array="5,4").add_to(rm)
            rm.fit_bounds([[min(p[1] for p in cp), min(p[0] for p in cp)],
                           [max(p[1] for p in cp), max(p[0] for p in cp)]], padding=(60, 60))
        dout = st_folium(rm, key="heat_chain_map", width=None, height=520,
                         returned_objects=["last_active_drawing"])
        st.caption("🟦 重症化概率下降 → 🟥 上升。画新多边形可重新分析。")

    drw = dout.get("last_active_drawing") if dout else None
    poly = None
    if drw and drw.get("geometry", {}).get("type") == "Polygon":
        poly = [[float(x), float(y)] for x, y in drw["geometry"]["coordinates"][0]]
    pkey = tuple(tuple(round(c, 6) for c in p) for p in poly) if poly else None
    if pkey and pkey != st.session_state.get("heat_chain_pkey"):
        st.session_state["heat_chain_pkey"] = pkey
        st.session_state["heat_chain_poly"] = poly
        st.session_state.pop("heat_chain", None)
        st.rerun()

    with colctl:
        if not cp:
            st.info("👈 先在地图上画一个地块(矩形/多边形)。")
        else:
            means = _poly_means_cached(tuple(tuple(p) for p in cp))
            st.markdown("**地块现状**(LST 模型自变量)")
            st.caption("地表温度 **%.1f°C** · 夜间灯光 %.0f · 建筑高度 %.0fm · 高程 %.1fm(以上不在调控范围)· %d 个100m网格"
                       % (means["lst_now"], means["ntl"], means["bldg_height"], means["elevation"], means["n_cells"]))
            ph = abs(hash(st.session_state.get("heat_chain_pkey")))
            targets = {}
            for key, label, lo, hi, step, fmt in SLV:
                cur = float(means[key])
                val = st.slider(f"{label}(现状 {fmt % cur})", lo, float(max(hi, cur)), cur, step,
                                key=f"sl_{key}_{ph}")
                if abs(val - cur) > 1e-9:          # 仅"被改动"的指标进入 targets
                    targets[key] = val
            if st.button("应用改造 · 计算风险变化", type="primary", use_container_width=True):
                if not targets:
                    st.session_state["heat_chain"] = {"n_cells": 0, "note": "未调整任何指标,请先拖动滑块。"}
                else:
                    st.session_state["heat_chain"] = _chain_cached(
                        tuple(tuple(p) for p in cp),
                        tuple(sorted((k, round(v, 4)) for k, v in targets.items())))
                st.rerun()
            if res is not None and res.get("n_cells", 0) > 0:
                st.markdown("**改造效果**")
                st.metric("地块内 ΔLST", f"{res['dlst_mean_inside']:+.2f} °C",
                          help=f"范围 {res['dlst_min']:+.2f} ~ {res['dlst_max']:+.2f} °C")
                st.metric("重症化概率 · 平均变化", f"{res['mean_drisk']*100:+.2f} 个百分点",
                          help="对一次老年中暑而言, 发展为重症的概率变化; 负=下降")
                st.metric("重症化概率 · 最大降幅 / 影响面积",
                          f"{res['min_drisk']*100:+.2f} 个百分点 · {res['area_down_ha']:.0f} ha")
            elif res is not None:
                st.warning(res.get("note", "该地块无有效数据,请换一处。"))


def page_health_risk():
    """健康风险维度 · 热相关重症风险诊断(局部建成环境→LST→重症化风险)。"""
    mi = heat_risk.model_info()
    page_header(
        "健康风险 · 热相关重症风险诊断与规划调控",
        "基于 287 例 60 岁以上中暑病例的 logistic 重症模型(重症 vs 轻症),显著变量为当天地表温度"
        "(p&lt;0.01)与到最近急救站距离。关联性模型,非交叉验证预测,用于规划辅助研判。")
    _heat_diag()
    with st.expander("模型与显著变量(logistic 重症模型)", expanded=False):
        b = mi["beta"]; pv = mi.get("pval", {})
        rows = [{"变量": VAR_ZH_HEAT.get(v, v), "OR/标准差": f"{np.exp(b[v]):.2f}",
                 "p 值": f"{pv.get(v, float('nan')):.3f}", "方向": VAR_DIR_HEAT.get(v, "")}
                for v in mi["vars"]]
        st.table(rows)
        st.markdown(
            "- 样本:287 例 60+ 中暑病例(167 重症/120 轻症),2023–2025 夏季。\n"
            "- 模型**只保留 当天地表温度(p<0.01)+ 到最近急救站距离**;建成密度/容积率/绿地**不直接入模**,"
            "而是经上方「局部改造模拟」通过影响 LST 间接作用。纳凉站点距离/密度经检验不显著(p≈0.2),未纳入。\n"
            "- McFadden R²≈%.2f;in-sample AUC≈%.2f,空间分块 CV AUC≈0.59(弱但显著)。\n"
            "- 显著的热信号是「当天高温」(时间维);本图为**关联性风险图**,非交叉验证预测,辅助研判而非精确定点。\n"
            "- LST 每 +1°C 约使重症 OR×1.12(局部改造据此把 ΔLST 换算为风险变化)。\n"
            "- 个体因素(基础病、送医及时性)主导重症,未纳入。" % (mi["mcfadden_r2"], mi.get("auc_insample", 0.62)))
