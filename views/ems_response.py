# -*- coding: utf-8 -*-
"""健康资源:急救反应时间预测。

地图点选事发点 → 自动匹配最近现状急救站 → 百度驾车路径规划得到行驶轨迹 →
沿轨迹缓冲区算 5 个空间自变量 → 随机森林预测到场秒数 + 4 档分级。
引擎 ems_response.py(空间计算+模型)、heatroute.py(百度路线)、geo.py(坐标/底图)。
"""
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

import ems_response
import heatroute
from geo import _add_basemap, in_shanghai
from theme import page_header

_GRADE_DESC = {"4min": ("4 分钟内", "#1B7F4B"), "8min": ("4–8 分钟", "#7FB800"),
               "12min": ("8–12 分钟", "#F5A623"), "Delay": ("延误(>12 分钟)", "#D7191C")}


def _get_ak():
    try:
        return st.secrets.get("baidu_ak", "") or ""
    except Exception:
        return ""


def _pick_map(incident):
    """点选地图:画出 202 个现状急救站 + 已选事发点。"""
    m = folium.Map(location=[31.23, 121.47], zoom_start=11, tiles=None, control_scale=True)
    _add_basemap(m, "浅色地图")
    slon, slat = ems_response.stations()
    glayer = folium.FeatureGroup(name="现状急救站")
    for lo, la in zip(slon, slat):
        folium.CircleMarker([la, lo], radius=2.5, weight=1, color="#444",
                            fill_color="#999", fill_opacity=0.85,
                            tooltip="现状急救站").add_to(glayer)
    glayer.add_to(m)
    if incident:
        folium.Marker([incident[1], incident[0]], tooltip="事发点",
                      icon=folium.Icon(color="red", icon="plus-sign")).add_to(m)
    return m


def _result_map(station, incident, path):
    m = folium.Map(location=[31.23, 121.47], zoom_start=13, tiles=None, control_scale=True)
    _add_basemap(m, "浅色地图")
    folium.PolyLine([(p[1], p[0]) for p in path], color="#D7191C", weight=5,
                    opacity=0.85, tooltip="救护车行驶轨迹").add_to(m)
    folium.Marker([station[1], station[0]], tooltip="最近急救站(起点)",
                  icon=folium.Icon(color="green", icon="plus", prefix="fa")).add_to(m)
    folium.Marker([incident[1], incident[0]], tooltip="事发点(终点)",
                  icon=folium.Icon(color="red", icon="plus-sign")).add_to(m)
    lats = [p[1] for p in path]; lngs = [p[0] for p in path]
    m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], padding=(40, 40))
    return m


def page_ems_response():
    page_header(
        "健康资源 · 急救反应时间预测",
        "在地图上点选**事发点**,系统匹配最近现状急救站、用百度驾车路径规划得到行驶轨迹,"
        "再沿轨迹缓冲区自动计算 5 个建成环境变量,预测**急救反应时间**与分级。")

    ak = _get_ak()
    if not ak:
        ak = st.text_input("百度地图 AK(驾车路径规划需要)", type="password",
                           help="写入 .streamlit/secrets.toml 的 baidu_ak;云端在 Secrets 配置。"
                                "AK 需放开服务端调用(IP 白名单)。")

    if st.button("🗑 清除"):
        for k in ("ems_incident", "ems_result"):
            st.session_state.pop(k, None)
        st.rerun()

    incident = st.session_state.get("ems_incident")
    tip = "点击地图选**事发点**" if not incident else f"事发点 {incident[1]:.4f}, {incident[0]:.4f}"
    st.caption(f"📍 {tip}")

    out = st_folium(_pick_map(incident), key="ems_pick", width=None, height=380,
                    returned_objects=["last_clicked"])
    lc = out.get("last_clicked") if out else None
    if lc:
        p = (round(lc["lng"], 6), round(lc["lat"], 6))
        if st.session_state.get("ems_incident") != p:
            if not in_shanghai(p[0], p[1]):
                st.warning("事发点需在上海范围内,请重新点选。")
            else:
                st.session_state["ems_incident"] = p
                st.session_state.pop("ems_result", None)
                st.rerun()

    if st.button("⏱ 预测到场时间", type="primary",
                 disabled=not (incident and ak)):
        try:
            with st.spinner("匹配最近急救站 + 百度驾车路径规划 + 计算建成环境变量…"):
                slon, slat, sdist = ems_response.nearest_station(*incident)
                station = (slon, slat)
                routes = heatroute.plan_routes(station, incident, mode_zh="驾车", ak=ak)
                if not routes:
                    st.warning("百度未返回可用驾车路线,请换事发点。")
                else:
                    path = routes[0]["path"]
                    feat = ems_response.compute_features(path)
                    pred = ems_response.predict(feat)
                    st.session_state["ems_result"] = {
                        "station": station, "sdist": sdist, "path": path,
                        "baidu_dist": routes[0].get("distance"),
                        "baidu_dur": routes[0].get("duration"),
                        "feat": feat, "pred": pred}
        except Exception as e:
            st.error(f"预测失败:{e}\n\n请检查 AK 是否有效、是否放开服务端调用(IP 白名单)。")

    res = st.session_state.get("ems_result")
    if not res:
        return

    pred = res["pred"]; feat = res["feat"]
    sec = pred["seconds"]
    grade = pred["sec_bin"]          # 头部分级用回归秒数切档,与展示的分钟数一致
    clf_grade = pred["class"]        # 分类模型的判档(单独呈现概率)
    gdesc, gcol = _GRADE_DESC.get(grade, (grade, "#666"))

    colmap, colres = st.columns([1.4, 1], gap="large")
    with colmap:
        st_folium(_result_map(res["station"], incident, res["path"]),
                  key="ems_result_map", width=None, height=440, returned_objects=[])
        st.caption(f"🟢 最近急救站(直线 {res['sdist']/1000:.1f}km)→ 🔴 事发点;"
                   f"红线为百度驾车轨迹,全程 {(res['baidu_dist'] or 0)/1000:.1f}km / "
                   f"百度估时 {(res['baidu_dur'] or 0)//60:.0f} 分。")
    with colres:
        st.markdown(
            f"<div style='background:{gcol}1A;border:1px solid {gcol};border-radius:10px;"
            f"padding:12px 16px;margin-bottom:8px'>"
            f"<div style='font-size:13px;color:#555'>模型预测到场时间</div>"
            f"<div style='font-size:30px;font-weight:800;color:{gcol}'>{sec/60:.1f} 分</div>"
            f"<div style='font-size:14px;color:{gcol};font-weight:600'>分级:{gdesc}</div></div>",
            unsafe_allow_html=True)
        # 各档概率
        pr = pred["proba"]; order = ["4min", "8min", "12min", "Delay"]
        dfp = pd.DataFrame({"档": [_GRADE_DESC[c][0] for c in order if c in pr],
                            "概率": [pr.get(c, 0) for c in order if c in pr]}).set_index("档")
        st.markdown("**分类模型各档概率**")
        st.bar_chart(dfp, height=160)
        if clf_grade != grade:
            st.caption(f"注:回归模型按秒数判为「{gdesc}」,分类模型最可能为"
                       f"「{_GRADE_DESC.get(clf_grade, (clf_grade,))[0]}」——边界附近两模型可不一致。")

    st.markdown("**沿轨迹计算的 5 个建成环境变量**")
    rows = []
    name_zh = {"Distance_m": "行驶距离(m)", "Road4_Length_m": "途径支路长度(m)",
               "POPDEN_phm2": "人口密度(人/公顷)", "FAR": "容积率",
               "MediPOIDen_nhm2": "医疗POI密度(个/公顷)"}
    for f in pred["feats"]:
        lo, hi = pred["feat_ranges"][f]
        rows.append({"变量": name_zh.get(f, f), "计算值": round(feat[f], 2),
                     "训练范围": f"[{lo:.0f}, {hi:.0f}]" if f != "FAR" else f"[{lo:.2f}, {hi:.2f}]",
                     "": "⚠超范围" if pred["oob"][f] else "✓"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(
        "**方法**:最近急救站取直线最近邻;轨迹来自百度驾车路径规划;支路长度=20m 缓冲区内支路线段长,"
        "人口密度/容积率=200m 缓冲区均值(已校准到训练分布),医疗POI密度=200m 缓冲区内点数/面积。"
        f"模型为随机森林(回归到场秒数={sec:.0f}s,分类直接判档={grade};二者一致性供参考)。"
        "样本为上海 120 急救出车记录(n=2267),为**关联性模型**,精度有限(4 分类约 56%、相邻档容忍约 96%),"
        "结果仅作规划研究参考。")
