# -*- coding: utf-8 -*-
"""健康行为:共享单车骑行潜力与建成环境反向优化。

在地图圈定范围 → 选中范围内 100m 格网 → 反向优化:把可调正向杠杆(商业POI/容积率/
建筑密度/路网密度等)按"改造强度"升向现实上限,预测骑行量提升并按杠杆分解,辅助
"如何通过建成环境改造提升骑行(体力活动)"的规划研判。
引擎 bike_ride.py(HistGradientBoosting 预测 + 反向优化)、geo.py(绘制地图/坐标)。
"""
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

import bike_ride
from geo import gcj2wgs, wgs2gcj, _identity, _add_basemap, build_draw_map, in_shanghai, _lerp_hex
from theme import HEALTH_GREEN, GREEN_DEEP, page_header


def _disp_tx(basemap):
    """显示坐标变换:卫星底图为 GCJ-02,需把 WGS84 转 GCJ 对齐;其余底图原样。"""
    return wgs2gcj if basemap == "卫星影像" else _identity


def _bbox_disp(poly_lnglat, basemap):
    """多边形(WGS84 lng,lat)→ 显示坐标下的 [[s,w],[n,e]] 边界。"""
    tx = _disp_tx(basemap)
    pts = [tx(x, y) for x, y in poly_lnglat]
    lons = [p[0] for p in pts]; lats = [p[1] for p in pts]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def _uplift_map(idx, base, opt, basemap="街道地图", bbox=None):
    """选中格按骑行量提升着色(浅→深绿)。格多则抽样显示。bbox=[[s,w],[n,e]] 对齐绘制图。"""
    lon, lat = bike_ride.cells_lonlat(idx)
    up = np.clip(opt - base, 0, None)
    vmax = max(float(np.percentile(up, 95)) if len(up) else 1.0, 1e-6)
    tx = _disp_tx(basemap)
    m = folium.Map(location=[float(lat.mean()), float(lon.mean())], zoom_start=14,
                   tiles=None, control_scale=True)
    _add_basemap(m, basemap)
    step = max(1, len(idx) // 2500)
    for k in range(0, len(idx), step):
        t = min(up[k] / vmax, 1.0)
        col = _lerp_hex("#EAF7EF", GREEN_DEEP, t)
        dlon, dlat = tx(float(lon[k]), float(lat[k]))
        folium.Rectangle(
            bounds=[[dlat - 0.00045, dlon - 0.00053], [dlat + 0.00045, dlon + 0.00053]],
            color=col, weight=0, fill=True, fill_color=col, fill_opacity=0.7,
            tooltip=f"+{up[k]:.0f} 次/日").add_to(m)
    if bbox is None:
        dpts = [tx(float(lon[k]), float(lat[k])) for k in range(0, len(idx), step)]
        bbox = [[min(p[1] for p in dpts), min(p[0] for p in dpts)],
                [max(p[1] for p in dpts), max(p[0] for p in dpts)]]
    m.fit_bounds(bbox)
    return m


_MODES = {"升至上限(强度)": "strength", "重点改造 N 格": "topN", "预算约束(系数)": "budget"}


def page_bike():
    page_header(
        "健康行为 · 共享单车骑行潜力与建成环境优化",
        "基于上海 2018 年 100m 格网共享单车通行量与建成环境数据,用机器学习预测骑行量,"
        "并在地图圈定范围后**反向求解**:把可调建成环境杠杆(商业POI/容积率/密度/路网)"
        "升向现实上限,估算骑行量(体力活动)提升潜力与各杠杆贡献,支持多种优化模式。")

    # ── 控件(顶部紧凑排布,避免空白)──
    r1c1, r1c2, r1c3 = st.columns([1, 1.4, 1.6])
    with r1c1:
        day = st.radio("时段", ["工作日", "周末"], key="bk_day")
    day_key = "wk" if day == "工作日" else "we"
    with r1c2:
        mode_label = st.radio("优化模式", list(_MODES.keys()), key="bk_mode")
    mode = _MODES[mode_label]
    with r1c3:
        if mode == "strength":
            strength = st.slider("改造强度 %", 0, 100, 100, 10, key="bk_strength",
                                 help="100%=各杠杆达现实上限(理论最优);调低看渐进方案") / 100.0
            top_n, budget_coef = None, 0.3
        elif mode == "topN":
            top_n = st.number_input("重点改造格数 N", 1, 5000, 20, 5, key="bk_topn",
                                    help="选提升潜力最大的 N 格,其所选杠杆全部升到现实上限(p90),其余格不动")
            strength, budget_coef = 1.0, 0.3
        else:
            budget_coef = st.slider("改造预算(占全面改造 %)", 5, 100, 30, 5, key="bk_budget",
                                    help="预算 = 把范围内所有格都升到现实上限所需投入的百分之几;"
                                         "系统按'每格提升÷改造成本'从高到低分配,优先改最划算的格") / 100.0
            strength, top_n = 1.0, None

    lever_opts = bike_ride.levers_available()
    sel = st.multiselect("可调杠杆(规划可改变的正向变量,升向全市 p90 上限)",
                         [k for k, _ in lever_opts], default=["POI_commer", "FAR", "BuiDen", "MinorRoad"],
                         format_func=lambda k: dict(lever_opts)[k], key="bk_levers")

    if mode == "budget":
        st.caption("💡 **预算约束 = 性价比优先**:把「所有格都升到上限」的投入记作 100%。你只花其中一部分预算,"
                   "系统按「每分投入换来的骑行量」从高到低改造——用有限投入拿最大提升。")

    # 底图 + 清除(放在两图之上,使左右地图顶部对齐)
    tb1, tb2, _tb3 = st.columns([2, 1, 4])
    draw_basemap = tb1.selectbox("底图", ["街道地图", "浅色地图", "卫星影像"],
                                 key="bk_base", label_visibility="collapsed")
    if tb2.button("🗑 清除范围", key="bk_clear", use_container_width=True):
        st.session_state.pop("bk_poly", None); st.rerun()

    # ── 左:圈定范围  右:优化结果(同高标题 + 同尺寸地图,左右对齐)──
    col_l, col_r = st.columns(2, gap="medium")
    with col_l:
        st.markdown("**① 圈定范围**")
        prev = st.session_state.get("bk_poly")
        dm = build_draw_map(draw_basemap)
        if prev:                                   # 已圈定:画出轮廓 + 缩放对齐
            tx = _disp_tx(draw_basemap)
            outline = [[tx(x, y)[1], tx(x, y)[0]] for x, y in prev]
            folium.Polygon(outline, color="#E8731F", weight=2, fill=True,
                           fill_opacity=0.05).add_to(dm)
            dm.fit_bounds(_bbox_disp(prev, draw_basemap))
        out = st_folium(dm, key=f"bk_draw_{draw_basemap}", width=None, height=360,
                        returned_objects=["last_active_drawing"])
        st.caption("用多边形/矩形工具圈定范围;「清除范围」可重画。")

    # 解析新绘制(转 WGS84),变化则存入 session 并 rerun(以便缩放对齐)
    drawing = out.get("last_active_drawing") if out else None
    if drawing and drawing.get("geometry", {}).get("type") == "Polygon":
        coords = drawing["geometry"]["coordinates"][0]
        if draw_basemap == "卫星影像":
            coords = [gcj2wgs(x, y) for x, y in coords]
        new_poly = [(x, y) for x, y in coords]
        if new_poly != st.session_state.get("bk_poly"):
            st.session_state["bk_poly"] = new_poly
            st.rerun()
    poly_lnglat = st.session_state.get("bk_poly")

    # 计算结果或提示信息(在渲染右列前确定)
    res, hint = None, None
    if poly_lnglat is None:
        hint = "👈 在左侧圈定一个范围,这里显示优化后的逐格骑行量提升。"
    elif not in_shanghai(sum(p[0] for p in poly_lnglat) / len(poly_lnglat),
                         sum(p[1] for p in poly_lnglat) / len(poly_lnglat)):
        hint = "当前数据仅覆盖上海市范围,请在上海范围内绘制。"
    elif not sel:
        hint = "请至少选择一个可调杠杆。"
    else:
        idx = bike_ride.select_in_polygon(poly_lnglat)
        if len(idx) < 3:
            hint = "圈定范围内有效格网过少,请画大一些。"
        else:
            res = bike_ride.optimize(idx, sel, day=day_key, mode=mode,
                                     strength=strength, top_n=top_n, budget_coef=budget_coef)

    with col_r:
        st.markdown("**② 优化结果**")
        if res is not None:
            st_folium(_uplift_map(res["cell_idx"], res["cell_base"], res["cell_opt"], draw_basemap,
                                  bbox=_bbox_disp(poly_lnglat, draw_basemap)),
                      key="bk_uplift", width=None, height=360, returned_objects=[])
            st.caption("格网按**预测骑行量提升**着色(越绿越大);未改造格接近无色。与左图同范围。")
        else:
            st.info(hint)

    if res is None:
        return

    # ── 指标 + 模式说明(全宽)──
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("范围内格网", f"{res['n_cells']:,}", help=f"实际改造 {res['n_changed']:,} 格")
    m2.metric(f"{day}骑行量·模型基线", f"{res['base_total']:,.0f} 次/日")
    m3.metric("优化后(模型)", f"{res['opt_total']:,.0f} 次/日", delta=f"+{res['uplift']:,.0f}")
    m4.metric("提升幅度", f"+{res['uplift_pct']:.0f}%")
    st.caption(f"对照:该范围**实测**{day}骑行量约 {res['obs_total']:,.0f} 次/日;"
               f"「基线/优化后」均为**模型预测**,口径一致可比。")
    if mode == "strength":
        st.caption(f"📌 **升至上限(强度{strength*100:.0f}%)**:全部 {res['n_cells']:,} 格的所选杠杆,"
                   f"各自从现状向现实上限(p90)提升 {strength*100:.0f}%。强度100%=理论最优。")
    elif mode == "topN":
        st.caption(f"📌 **重点改造 {res['n_changed']:,} 格**:选潜力最大的这些格,所选杠杆**全部升到上限(p90)**,"
                   f"其余 {res['n_cells']-res['n_changed']:,} 格不动。")
    else:
        eff = res["uplift"] / (res["full_total"] - res["base_total"]) * 100 if res["full_total"] > res["base_total"] else 0
        st.caption(f"📌 **预算约束 {budget_coef*100:.0f}%(性价比优先)**:在「全面改造投入」的 {budget_coef*100:.0f}% 预算内,"
                   f"优先改最划算的 **{res['n_changed']:,}/{res['n_cells']:,}** 格 → 骑行量 **+{res['uplift_pct']:.0f}%**"
                   f"(全面改造可 +{res['full_uplift_pct']:.0f}%)。即用 {budget_coef*100:.0f}% 投入拿到全部潜力的 **{eff:.0f}%**。")

    # ── 杠杆贡献 + 前后均值(全宽两列)──
    cc1, cc2 = st.columns(2, gap="large")
    contrib = res["contrib"]
    with cc1:
        st.markdown("**各杠杆对提升的贡献(次/日)**")
        dfc = pd.DataFrame({"杠杆": [bike_ride.LEVER_ZH[k] for k in contrib],
                            "贡献(次/日)": [contrib[k] for k in contrib]}).set_index("杠杆")
        st.bar_chart(dfc.sort_values("贡献(次/日)", ascending=False), height=220)
    with cc2:
        st.markdown("**被改造格 · 杠杆 现状均值 → 优化后均值**")
        rows = [{"杠杆": bike_ride.LEVER_ZH[k], "现状": round(res["cur_avg"][k], 3),
                 "优化后": round(res["opt_avg"][k], 3), "上限p90": round(res["ceilings"][k], 3),
                 "贡献(次/日)": round(contrib[k])} for k in sel]
        st.dataframe(pd.DataFrame(rows).sort_values("贡献(次/日)", ascending=False),
                     hide_index=True, use_container_width=True)
        st.caption("「现状/优化后」为**被改造格**的均值;升至上限模式按强度部分提升,N格/预算模式被改造格升到 p90。")

    with st.expander("模型与方法(骑行量预测 + 反向优化)", expanded=False):
        st.markdown(
            "- **数据**:上海 2018 年 100m 格网(298,249 格)共享单车工作日/周末通行量 + 建成环境变量。\n"
            "- **预测模型**:HistGradientBoosting 回归,5 折 CV **R²≈0.37**(骑行量约 1/3 可由建成环境解释,"
            "其余受天气/时段/车辆投放等影响,数据未含)。\n"
            "- **反向优化**:固定城市化背景(夜光/地表温度/水体),把所选正向杠杆(商业POI/容积率/建筑密度/"
            "建筑高度/路网密度)按强度升向**全市 p90 现实上限**(只升不降),预测骑行量提升并按单杠杆分解。\n"
            "- **解读**:模型对杠杆近似单调,故 100% 强度即 box 约束下理论最优;绿地率与骑行量负相关、默认不作上调。\n"
            "- 属规划探索性**辅助研判**(关联非因果),非真实建设承诺。")


def page_behavior_placeholder():
    page_header("健康行为", "体力活动 / 绿地使用 / 出行暴露 / 高温避险(更多功能建设中)。")
    st.info("本维度首个功能:共享单车骑行潜力与建成环境优化(见左侧)。")
