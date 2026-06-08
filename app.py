# -*- coding: utf-8 -*-
"""
上海市城市规划项目健康影响评估 (HIA) — Streamlit 演示应用
Phase 1 · 第一步:标题 + 案例选择 + 参数显示
"""

import math

import numpy as np
import pandas as pd
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium

from cases import CASES
from hia_engine import compute_hia, compute_hia_gridded
from report_docx import build_report_docx
import green_lst
import heat_risk

# ----- 健康绿主色 -----
HEALTH_GREEN = "#2E9E5B"      # 主强调色
GREEN_DEEP = "#1B6B3A"        # 深绿(标题)
TONGJI_RED = "#A6192E"        # 同济红(仅作品牌点缀,保留备用)

# 100m 网格在经纬度下的半格尺寸(用于绘制网格方块)
HALF_LON, HALF_LAT = 0.00053, 0.00045

# ---- WGS84 -> GCJ-02(火星坐标)转换:高德/国内卫星瓦片为 GCJ-02,需转换叠加层才对齐 ----
_GCJ_A = 6378245.0
_GCJ_EE = 0.00669342162296594323


def _gcj_tf_lat(x, y):
    r = (-100 + 2*x + 3*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
         + (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi)) * 2/3
         + (20*math.sin(y*math.pi) + 40*math.sin(y/3*math.pi)) * 2/3
         + (160*math.sin(y/12*math.pi) + 320*math.sin(y*math.pi/30)) * 2/3)
    return r


def _gcj_tf_lng(x, y):
    r = (300 + x + 2*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
         + (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi)) * 2/3
         + (20*math.sin(x*math.pi) + 40*math.sin(x/3*math.pi)) * 2/3
         + (150*math.sin(x/12*math.pi) + 300*math.sin(x/30*math.pi)) * 2/3)
    return r


def wgs2gcj(lng, lat):
    """WGS84 经纬度 -> GCJ-02。中国境外原样返回。"""
    if not (73.66 < lng < 135.05 and 3.86 < lat < 53.55):
        return lng, lat
    dlat = _gcj_tf_lat(lng - 105.0, lat - 35.0)
    dlng = _gcj_tf_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat); magic = 1 - _GCJ_EE * magic * magic
    sm = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_GCJ_A * (1 - _GCJ_EE)) / (magic * sm) * math.pi)
    dlng = (dlng * 180.0) / (_GCJ_A / sm * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


def gcj2wgs(lng, lat):
    """GCJ-02 -> WGS84(镜像近似,误差 <5m,足够 100m 网格用)。"""
    glng, glat = wgs2gcj(lng, lat)
    return lng * 2 - glng, lat * 2 - glat


def _identity(lng, lat):
    return lng, lat


def get_field(case):
    """对案例多边形调用 v2 模型,得到含外溢的逐格 ΔLST 场(结果在进程内缓存)。"""
    mode = "add" if case["intervention_type"] == "greenspace_add" else "remove"
    return green_lst.compute_field(case["polygon"], mode=mode,
                                   target_greenfrac=case.get("greenfrac_after"))


def _lerp_hex(c1, c2, t):
    a = tuple(int(c1[i:i+2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i+2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % tuple(int(a[i] + (b[i]-a[i]) * t) for i in range(3))


def dlst_color(d, vmax):
    """ΔLST 配色:降温=由浅到深的青蓝,升温=由浅到深的橙红。"""
    t = min(abs(d) / vmax, 1.0) if vmax > 0 else 0.0
    if d <= 0:
        return _lerp_hex("#E8F6FF", "#0B5394", t)   # 蓝:降温
    return _lerp_hex("#FFF0E6", "#B22222", t)        # 红:升温


def add_dlst_grid(m, field, tx=_identity):
    """把逐格 ΔLST 场以彩色 100m 方块叠加到地图(含空间外溢)。tx 为坐标变换。"""
    if not field or field.get("n_cells", 0) == 0:
        return
    dl = field["dlst"]; vmax = max(abs(min(dl)), abs(max(dl)), 0.5)
    for lat_c, lon_c, d in zip(field["lat"], field["lon"], dl):
        col = dlst_color(d, vmax)
        lo1, la1 = tx(lon_c - HALF_LON, lat_c - HALF_LAT)
        lo2, la2 = tx(lon_c + HALF_LON, lat_c + HALF_LAT)
        folium.Rectangle(
            bounds=[[la1, lo1], [la2, lo2]],
            color=col, weight=0, fill=True, fill_color=col, fill_opacity=0.72,
            tooltip=f"ΔLST {d:+.1f} °C",
        ).add_to(m)


def add_dlst_raster(m, field, upscale=8, tx=_identity):
    """把 ΔLST 场渲染成平滑高分辨率栅格(PIL 上采样 + ImageOverlay),
    分辨率与绿地大小在图上自然匹配,不受 100m 方块限制。"""
    import io, base64
    from scipy.ndimage import zoom
    from PIL import Image
    f2 = field.get("field2d") if field else None
    if not f2:
        return
    D = f2["d"]; lat2 = f2["lat"]; lon2 = f2["lon"]
    mask = np.isfinite(D)
    if mask.sum() == 0:
        return
    D0 = np.where(mask, D, 0.0).astype(float)
    Dz = zoom(D0, upscale, order=1)
    Mz = zoom(mask.astype(float), upscale, order=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        Dz = np.where(Mz > 0.05, Dz / np.maximum(Mz, 1e-6), 0.0)
    vmax = max(abs(float(np.nanmin(D))), abs(float(np.nanmax(D))), 0.5)
    t = np.clip(np.abs(Dz) / vmax, 0, 1)[..., None]
    cool = (Dz <= 0)[..., None]

    def ramp(c0, c1):
        a = np.array([int(c0[i:i+2], 16) for i in (1, 3, 5)], float)
        b = np.array([int(c1[i:i+2], 16) for i in (1, 3, 5)], float)
        return a + (b - a) * t
    rgb = np.where(cool, ramp("#E8F6FF", "#0B5394"), ramp("#FFF0E6", "#B22222"))
    alpha = (np.clip(Mz, 0, 1) * 205)[..., None]
    rgba = np.concatenate([rgb, alpha], axis=2).astype(np.uint8)
    buf = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    sw = tx(float(lon2.min()) - HALF_LON, float(lat2.min()) - HALF_LAT)
    ne = tx(float(lon2.max()) + HALF_LON, float(lat2.max()) + HALF_LAT)
    bounds = [[sw[1], sw[0]], [ne[1], ne[0]]]
    folium.raster_layers.ImageOverlay(image=uri, bounds=bounds, opacity=0.8).add_to(m)


def _add_basemap(m, basemap):
    """加专业底图。卫星影像(高德, GCJ-02)/ 街道地图(CartoDB Voyager)/ 浅色(Positron)。"""
    if basemap == "卫星影像":
        # 高德卫星(国内可达, GCJ-02 坐标系;叠加层已做 WGS84->GCJ 变换对齐)
        folium.TileLayer(
            "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
            attr="高德地图 AutoNavi", name="卫星影像", control=False,
            subdomains="1234", max_zoom=18).add_to(m)
        # 高德路网+地名注记(同为 GCJ-02)
        folium.TileLayer(
            "https://webst0{s}.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}",
            attr="高德地图 AutoNavi", name="路网注记", overlay=True, control=False,
            subdomains="1234", max_zoom=18).add_to(m)
    elif basemap == "街道地图":
        folium.TileLayer(
            "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
            attr="© OpenStreetMap contributors © CARTO", name="街道地图",
            control=False, max_zoom=20).add_to(m)
    else:  # 浅色
        folium.TileLayer("CartoDB positron", control=False).add_to(m)


def build_case_map(case, field=None, viz_mode="平滑栅格", basemap="卫星影像"):
    """聚焦案例地块的地图:专业底图 + ΔLST 场(含外溢)+ 干预多边形描边,自动适配范围。
    viz_mode: '平滑栅格'(高分辨率连续) 或 '网格方块'(100m 原始格)。"""
    poly = case["polygon"]  # [[lng, lat], ...]
    is_loss = case["intervention_type"] == "greenspace_remove"
    edge = "#C62828" if is_loss else HEALTH_GREEN

    # 卫星底图为 GCJ-02,需把所有叠加坐标 WGS84->GCJ 才能与地面对齐
    tx = wgs2gcj if basemap == "卫星影像" else _identity
    c_lng, c_lat = tx(case["center_lng"], case["center_lat"])
    m = folium.Map(
        location=[c_lat, c_lng],
        zoom_start=15,
        tiles=None,
        control_scale=True,
    )
    _add_basemap(m, basemap)

    # ΔLST 可视化(降温蓝 / 升温红)
    if viz_mode.startswith("网格"):
        add_dlst_grid(m, field, tx)
    else:
        add_dlst_raster(m, field, tx=tx)

    # 干预地块只描边(填充让位给 ΔLST 网格)
    poly_tx = [tx(lng, lat) for lng, lat in poly]
    folium.Polygon(
        locations=[[la, lo] for lo, la in poly_tx],
        color=edge, weight=2.5, fill=False, dash_array="5,4",
        tooltip=f"{case['project_name']}({case['size_ha']} 公顷)",
    ).add_to(m)

    # 缩放到受影响范围(含外溢)而非仅多边形(坐标同步变换)
    if field and field.get("n_cells", 0) > 0:
        pts = [tx(lo, la) for lo, la in zip(field["lon"], field["lat"])]
    else:
        pts = poly_tx
    lats = [p[1] for p in pts]; lngs = [p[0] for p in pts]
    m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], padding=(30, 30))
    return m


def render_report(case, result):
    """在页面上渲染 HIA 评估报告(对应 v0.9 工作流 7 章节结构,屏幕精简版)。"""
    years = case["evaluation_years"]
    mname = result["metric_name"]          # 可避免病例数 / 额外病例数
    cooling = result["direction"] == "cooling"
    cvd = result["cvd_primary"]
    ac = result["ac_primary"]
    sens = result["cvd_sensitivity"]

    tone = HEALTH_GREEN if cooling else "#C62828"
    verb = "健康效益(降温)" if cooling else "健康风险(升温)"

    # —— 结论横幅:大字突出核心数字 ——
    st.markdown(
        f"""
        <div style="background:linear-gradient(90deg,{tone}14 0%,#FFFFFF 90%);
                    border-left:6px solid {tone}; border-radius:8px;
                    padding:1rem 1.4rem; margin:0.6rem 0 1.2rem 0;">
          <div style="color:{tone}; font-size:0.95rem; font-weight:600;">评估结论 · {verb}</div>
          <div style="font-size:1.05rem; color:#333; margin-top:0.2rem;">
            该项目在 <b>{years} 年</b>评估期内,预计带来心血管疾病
            <span style="color:{tone}; font-size:1.9rem; font-weight:800;">
              {abs(cvd['total_point']):.1f}</span> 例
            <b>{mname}</b>(全因 {abs(ac['total_point']):.1f} 例)。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # —— 关键指标卡 ——
    k1, k2, k3 = st.columns(3)
    k1.metric(f"心血管 · {mname}(累计)", f"{abs(cvd['total_point']):.1f} 例",
              help=f"95% CI:{abs(cvd['total_low']):.1f} – {abs(cvd['total_high']):.1f} 例")
    k2.metric(f"全因 · {mname}(累计)", f"{abs(ac['total_point']):.1f} 例",
              help=f"95% CI:{abs(ac['total_low']):.1f} – {abs(ac['total_high']):.1f} 例")
    k3.metric("心血管 · 每年", f"{abs(cvd['per_year_point']):.2f} 例/年",
              help=f"95% CI:{abs(cvd['per_year_low']):.2f} – {abs(cvd['per_year_high']):.2f}")

    # —— 量化结果表(双 ERF 并行)——
    def ci(lo, hi):
        return f"{abs(lo):.1f} – {abs(hi):.1f}"

    rows = [
        {"指标 / ERF": "心血管(主分析 · Liu 2022)",
         f"每年{mname}": f"{abs(cvd['per_year_point']):.2f}",
         f"累计 {years} 年": f"{abs(cvd['total_point']):.1f}",
         "95% CI(累计)": ci(cvd['total_low'], cvd['total_high'])},
        {"指标 / ERF": "全因(主分析 · Liu 2022)",
         f"每年{mname}": f"{abs(ac['per_year_point']):.2f}",
         f"累计 {years} 年": f"{abs(ac['total_point']):.1f}",
         "95% CI(累计)": ci(ac['total_low'], ac['total_high'])},
        {"指标 / ERF": "心血管(敏感性 · Lingyan 2017)",
         f"每年{mname}": f"{abs(sens['per_year_point']):.2f}",
         f"累计 {years} 年": f"{abs(sens['total_point']):.1f}",
         "95% CI(累计)": ci(sens['total_low'], sens['total_high'])},
    ]
    st.markdown("##### 健康影响量化结果(双 ERF 并行)")
    st.table(rows)

    # —— 方法、敏感性、局限、建议 ——
    with st.expander("方法与关键假设", expanded=False):
        ep_cvd = result["erf_primary_cvd"]
        ep_ac = result["erf_primary_allcause"]
        es = result["erf_sensitivity_cvd"]
        st.markdown(
            f"""
- **主分析 ERF**:{ep_cvd['label']},心血管 RR={ep_cvd['rr_point']}、全因 RR={ep_ac['rr_point']}({ep_cvd['unit']})。
- **敏感性 ERF**:{es['label']},RR={es['rr_point']}({es['unit']})。
- **城市基线死亡率**:全因 {result['baseline_allcause_per_1000']}‰、心血管 {result['baseline_cvd_per_1000']}‰(上海市卫健委统计公报)。
- **热归因比例**:取夏季热相关死亡占比 {result['heat_fraction']:.0%}。
- **计算式**:可避免/额外病例 = 热相关基线病例 × (1 − RR<sup>ΔT</sup>) × 评估年数,ΔT_air = {case['delta_air_temp_C']:+.2f} °C。
            """,
            unsafe_allow_html=True,
        )

    with st.expander("敏感性分析的意义"):
        ratio = result["sensitivity_ratio"]
        ratio_txt = f"约为主分析的 {ratio:.1f} 倍" if ratio else "—"
        st.write(
            f"采用更陡峭的 Lingyan 2017 暴露-反应关系作为上界情景,其估计{ratio_txt},"
            "用于刻画 ERF 选择带来的不确定性区间。真实影响大概率落在主分析与敏感性分析之间。"
        )

    with st.expander("局限性"):
        st.markdown(
            """
- ERF 来自人群流行病学 meta 分析,迁移到本地存在不确定性;
- 仅量化热暴露的死亡终点,未含发病、住院、心理与社会效益;
- ΔLST→ΔT_air 的转换与降温幅度基于经验系数,未做精细微气候模拟;
- 人口为周边估算常住口径,未细分昼夜流动与脆弱人群空间分布;
- 未考虑适应行为(空调、行为调整)对暴露的削减;
- 评估期内人口与基线死亡率假定恒定;
- 多边形与部分参数为演示用途的合理估计,非实测地块;
- 结果用于规划决策辅助,不替代正式环境健康风险评估。
            """
        )

    with st.expander("规划建议", expanded=True):
        if cooling:
            st.markdown(
                """
1. **优先实施并尽量提质**:量化结果显示明确的健康效益,建议保障绿地规模与乔木覆盖以稳定降温。
2. **面向脆弱人群布局**:在老年人、户外劳动者集中处增设遮荫与饮水等避暑设施,放大健康收益。
3. **建立监测**:对地表温度与就诊数据做前后对比,为后续项目积累本地化 ERF 证据。
                """
            )
        else:
            st.markdown(
                """
1. **审慎评估与缓解**:拆除将带来可量化的健康风险,建议核算是否可避免或缩小拆除范围。
2. **同步补偿降温**:就近新增绿地、增加遮荫与喷雾等措施,抵消热岛加剧的短期影响。
3. **错峰与告知**:将施工与拆除安排避开盛夏高温,并对周边脆弱人群做高温健康提示。
                """
            )

    st.caption("报告生成:HIA 智能体(Phase 3.P1+P2+P3+P4)· 本结果由本地计算核心生成,用于演示")


def render_case_flow(case, show_map=True, field=None):
    """通用评估流程:参数 +(可选)区位地图 + 开始评估 + 报告 + Word 下载。
    示范案例与自定义评估共用此函数。field 为 v2 模型逐格 ΔLST 场。"""
    cid = case["id"]
    if field is None:
        field = get_field(case)
    has_field = bool(field) and field.get("n_cells", 0) > 0

    def _params_block():
        st.markdown("##### 项目参数")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("干预类型", case["intervention_type_zh"])
            st.metric("地块内降温 ΔLST", f"{case['delta_lst_C']:+.1f} °C",
                      help="多边形内逐格预测的地表温度变化均值")
            pop = field["pop_affected"] if has_field else case["population"]
            st.metric("受影响人口", f"{int(pop):,} 人", help="含空间外溢, 100m 人口栅格求和")
        with c2:
            st.metric("规模", f"{case['size_ha']} 公顷")
            st.metric("气温变化 ΔT_air", f"{case['delta_air_temp_C']:+.2f} °C")
            st.metric("评估期", f"{case['evaluation_years']} 年")
        if has_field:
            st.caption(
                f"模型(空间分块CV R²={field['cv_r2']:.2f}, MAE={field['cv_mae']:.1f}°C)"
                f"预测:干预影响 {field['n_inside']} 格、含外溢共 {field['n_cells']} 格,"
                f"最强降温 {field['dlst_min']:+.1f}°C。"
            )
        st.caption(f"人口口径:{case['population_brief']}")
        with st.expander("更多参数(基线死亡率 / 年龄结构 / 气候)"):
            st.write(f"**全因死亡率基线**:{case['baseline_mortality_per_1000']} ‰")
            st.write(f"**心血管死亡率基线**:{case['baseline_cvd_mortality_per_1000']} ‰")
            st.write(f"**夏季地表温度基线**:{case['summer_lst_baseline_C']} °C")
            age = case["age_distribution"]
            st.write(
                f"**年龄结构**:0–14 岁 {age['0_14']:.0%} · "
                f"15–64 岁 {age['15_64']:.0%} · 65 岁以上 {age['65plus']:.0%}"
            )

    if show_map:
        col_info, col_map = st.columns([1, 1.05], gap="large")
        with col_info:
            _params_block()
        with col_map:
            st.markdown("##### 降温影响 · 逐格预测")
            cm1, cm2 = st.columns([1, 1])
            with cm1:
                basemap = st.selectbox(
                    "底图", ["卫星影像", "街道地图", "浅色地图"],
                    key=f"base_{cid}", label_visibility="collapsed")
            with cm2:
                viz_mode = st.radio(
                    "可视化方式", ["平滑栅格", "网格方块(100m)"],
                    horizontal=True, key=f"viz_{cid}", label_visibility="collapsed")
            st_folium(build_case_map(case, field, viz_mode, basemap), key=f"map_{cid}",
                      width=None, height=400, returned_objects=[])
            st.caption("🟦 降温　🟥 升温　颜色越深变化越大;含绿地对周边的空间外溢。"
                       "「平滑栅格」分辨率随地块自适应,「网格方块」为 100m 原始格。")
    else:
        _params_block()

    st.markdown("---")

    # 开始评估(逐格 HIA:100m 人口 × 逐格 ΔLST)
    eval_key = f"eval_{cid}"
    if st.button("开始评估", type="primary", use_container_width=True, key=f"btn_{cid}"):
        if has_field:
            st.session_state[eval_key] = compute_hia_gridded(case, field)
        else:
            st.session_state[eval_key] = compute_hia(case)

    result = st.session_state.get(eval_key)
    if result:
        st.markdown(f"## {case['project_name']} · 健康影响评估报告")
        render_report(case, result)
        docx_buf = build_report_docx(case, result)
        st.download_button(
            "📄 下载 Word 报告",
            data=docx_buf,
            file_name=f"HIA评估报告_{case['district']}_{case['subdistrict']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            key=f"dl_{cid}",
        )
    else:
        st.info("点击上方「开始评估」,系统将调用本地 HIA 计算核心生成评估报告。")


# ===== Phase 4:自定义画多边形 =====
# 上海市大致外包矩形 (lng_min, lat_min, lng_max, lat_max),用于挡掉范围外绘制
SHANGHAI_BBOX = (120.85, 30.67, 122.05, 31.90)


def polygon_area_ha(poly_latlng):
    """用等积平面近似计算多边形面积(公顷)。poly_latlng: [[lat, lng], ...]。"""
    if len(poly_latlng) < 3:
        return 0.0
    lat0 = sum(p[0] for p in poly_latlng) / len(poly_latlng)
    m_lat = 111320.0
    m_lng = 111320.0 * math.cos(math.radians(lat0))
    pts = [(lng * m_lng, lat * m_lat) for lat, lng in poly_latlng]
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0 / 10000.0  # m² → 公顷


def in_shanghai(lng, lat):
    a, b, c, d = SHANGHAI_BBOX
    return a <= lng <= c and b <= lat <= d


def build_draw_map(basemap="卫星影像"):
    """带绘制工具的上海地图(专业底图),只允许画多边形/矩形。
    卫星底图为 GCJ-02,地图中心也转到 GCJ;返回的绘制坐标在 render 处再转回 WGS84。"""
    if basemap == "卫星影像":
        clng, clat = wgs2gcj(121.47, 31.23)
    else:
        clng, clat = 121.47, 31.23
    m = folium.Map(location=[clat, clng], zoom_start=11, tiles=None, control_scale=True)
    _add_basemap(m, basemap)
    Draw(
        draw_options={
            "polyline": False, "circle": False, "marker": False,
            "circlemarker": False, "rectangle": True, "polygon": True,
        },
        edit_options={"edit": False},
        export=False,
    ).add_to(m)
    return m


def build_custom_case(poly_latlng, direction, years, project_name, field):
    """把用户绘制的多边形 + v2 模型逐格场组装成与示范案例同构的 case 字典。
    ΔLST、受影响人口、现状地温均由模型/数据给出,不再手填。"""
    poly_lnglat = [[lng, lat] for lat, lng in poly_latlng]
    lat_c = sum(p[0] for p in poly_latlng) / len(poly_latlng)
    lng_c = sum(p[1] for p in poly_latlng) / len(poly_latlng)
    area = polygon_area_ha(poly_latlng)
    cooling = direction == "新增绿地"
    dlst_in = field["dlst_mean_inside"]
    return {
        "id": "custom",
        "label": "自定义评估",
        "tag": "新增绿地" if cooling else "绿地损失",
        "tag_color": "#2E7D32" if cooling else "#C62828",
        "project_name": project_name or "自定义城市绿地评估项目",
        "city": "上海市",
        "district": "自定义地块",
        "subdistrict": "用户绘制",
        "center_lng": lng_c,
        "center_lat": lat_c,
        "polygon": poly_lnglat,
        "intervention_type": "greenspace_add" if cooling else "greenspace_remove",
        "intervention_type_zh": "新增城市绿地" if cooling else "拆除既有绿地",
        "size_ha": round(area, 2),
        "delta_lst_C": round(dlst_in, 2),
        "delta_air_temp_C": round(dlst_in * 0.7, 2),
        "population": int(field["pop_affected"]),
        "population_brief": "模型预测降温影响范围内常住居民(含外溢, 100m 人口栅格求和)",
        "age_distribution": {"0_14": 0.11, "15_64": 0.65, "65plus": 0.24},
        "baseline_mortality_per_1000": 6.28,
        "baseline_cvd_mortality_per_1000": 2.70,
        "climate_zone": "hot_summer_cold_winter",
        "summer_lst_baseline_C": field["obs_lst_inside"],
        "evaluation_years": int(years),
        "background": (
            f"用户在地图上自定义绘制的地块,面积约 {area:.2f} 公顷,"
            f"拟进行{'新增城市绿地' if cooling else '拆除既有绿地'}干预。"
            "以下为基于上海 100m 实测数据训练的地表温度模型(含绿地空间外溢)"
            "与逐格健康影响量化的评估结果。"
        ),
    }


def render_custom_mode():
    """自定义模式:绘制多边形 → 模型预测逐格 ΔLST(含外溢)→ 逐格评估。"""
    st.markdown("## 自定义评估 · 在地图上绘制地块")
    st.caption("用地图左上角绘制工具(多边形 / 矩形)画出目标地块,系统调用上海 100m 地温模型"
               "自动预测降温幅度、空间外溢范围与受影响人口。仅支持上海市范围。")

    col_map, col_form = st.columns([1.2, 1], gap="large")
    with col_map:
        draw_basemap = st.selectbox(
            "底图", ["卫星影像", "街道地图", "浅色地图"],
            key="draw_base", label_visibility="collapsed")
        out = st_folium(build_draw_map(draw_basemap), key=f"draw_map_{draw_basemap}",
                        width=None, height=460, returned_objects=["last_active_drawing"])

    # 解析最近一次绘制的多边形;卫星底图为 GCJ-02,需把绘制坐标转回 WGS84
    poly_latlng = None
    drawing = out.get("last_active_drawing") if out else None
    if drawing and drawing.get("geometry", {}).get("type") == "Polygon":
        coords = drawing["geometry"]["coordinates"][0]  # [[lng, lat], ...](地图CRS)
        if draw_basemap == "卫星影像":
            coords = [gcj2wgs(x, y) for x, y in coords]
        poly_latlng = [[lat, lng] for lng, lat in coords]

    with col_form:
        st.markdown("##### 评估参数")
        project_name = st.text_input("项目名称", value="自定义城市绿地评估项目")
        direction = st.radio("干预方向", ["新增绿地", "拆除绿地"], horizontal=True)
        years = st.number_input("评估期 (年)", min_value=1, max_value=30, value=10, step=1)
        if poly_latlng:
            st.metric("已绘制地块面积", f"{polygon_area_ha(poly_latlng):.2f} 公顷")
        else:
            st.info("👈 请先在地图上绘制一个地块")

    if not poly_latlng:
        return

    # 上海范围校验
    lat_c = sum(p[0] for p in poly_latlng) / len(poly_latlng)
    lng_c = sum(p[1] for p in poly_latlng) / len(poly_latlng)
    if not in_shanghai(lng_c, lat_c):
        st.warning("当前演示仅支持上海市范围内的地块,请在上海范围内重新绘制。")
        return

    # 调模型算逐格 ΔLST 场
    poly_lnglat = [[lng, lat] for lat, lng in poly_latlng]
    mode = "add" if direction == "新增绿地" else "remove"
    field = green_lst.compute_field(poly_lnglat, mode=mode)
    if field.get("n_cells", 0) == 0:
        st.warning(field.get("note", "该地块无有效栅格数据,请换一处或画大一些。"))
        return

    case = build_custom_case(poly_latlng, direction, years, project_name, field)
    st.markdown("---")
    render_case_flow(case, show_map=True, field=field)


FEAT_ZH = {
    "bldg_height": "建筑高度 (GHSL)", "ntl": "夜间灯光 (VIIRS·人为热代理)",
    "dw_built": "建成概率 (Dynamic World)", "FAR_proxy": "容积率代理",
    "elevation": "高程", "slope": "坡度",
    "greenfrac": "本格绿地占比", "g300": "300m 邻域绿地占比",
    "g900": "900m 邻域绿地占比", "dist_green_m": "到最近绿地距离",
}


@st.cache_data(show_spinner=False)
def _feature_importance():
    rf = green_lst._state()["rf"]
    feats = green_lst.OWN + green_lst.GREEN_FEATS
    s = pd.Series(rf.feature_importances_, index=[FEAT_ZH[f] for f in feats])
    return s.sort_values(ascending=False)


@st.cache_data(show_spinner=False)
def _dose_response():
    """代表性建成背景下,周边绿地占比 0→1 的预测地表温度(剂量–反应曲线)。"""
    S = green_lst._state()
    own = S["own"]; gf = S["gf"]; wc = S["wc"]
    built = np.isfinite(own[0]) & (own[0] > 0.4) & (wc != 80) & (wc != 90)
    bg = [float(np.nanmedian(own[i][built])) for i in range(len(green_lst.OWN))]
    levels = np.round(np.arange(0, 1.001, 0.1), 2)
    rows = []
    for g in levels:
        dist = 0.0 if g >= green_lst.GREEN_THRESH else 300.0
        rows.append(bg + [g, g, g, dist])   # greenfrac, g300, g900, dist_green_m
    pred = S["rf"].predict(np.array(rows, dtype=float))
    d = pred - pred[0]
    return pd.DataFrame({"绿地占比": levels, "预测地表温度变化 ΔLST (°C)": np.round(d, 2)}
                        ).set_index("绿地占比")


def render_methodology():
    """LST 变化建模方法的专门说明页。"""
    S = green_lst._state()
    st.markdown("## 地表温度变化建模方法 · 技术说明")
    st.caption("本页说明 demo 中「绿地干预 → 地表温度(LST)变化」的数据、模型、验证与预测流程,"
               "供方法学审阅。")

    st.markdown("### 1　总体思路")
    st.markdown(
        "在地图上绘制一块新增/拆除绿地的多边形后,系统用一个基于上海全市 100m 实测数据训练的"
        "**机器学习地表温度模型**,预测该地块**及其周边**逐格的夏季地表温度变化 ΔLST(含空间外溢),"
        "再据此做逐格健康影响评估(HIA)。核心特征里包含**邻域绿地占比与到最近绿地的距离**,"
        "因此「绿地对周边的降温外溢」是由模型内生预测的,而非人为叠加的衰减假设。")

    st.markdown("### 2　数据源")
    st.markdown(
        "- **训练数据**:上海全市 100m 网格(EPSG:32651 / UTM 51N),约 **60.7 万**个有效网格,"
        "GEE 多年夏季(6–9 月)中位合成,有效 LST 覆盖率 ~100%(每格含 `LST_count` 有效影像数,中位 16)。\n"
        "- **地表温度 LST**:Landsat 8/9 热红外反演,多年合成以抑制云污染与单期噪声。\n"
        "- **绿地**:ESA WorldCover / Dynamic World 衍生的 100m 绿地占比(greenfrac)与二值绿地。\n"
        "- **协变量**:建筑高度/体积(GHSL)、建成概率(Dynamic World)、容积率代理、"
        "夜间灯光(VIIRS,人为热代理)、高程与坡度(Copernicus DEM)、人口(WorldPop 2020)。")

    st.markdown("### 3　自变量(特征)")
    st.markdown("分两类:**绿地相关特征**(干预会改变)与**建成/地形背景特征**(干预时保持不变)。")
    feat_rows = [
        {"类别": "绿地(可干预)", "特征": "本格绿地占比 greenfrac", "说明": "100m 网格内绿地面积比例,干预直接改变"},
        {"类别": "绿地(可干预)", "特征": "300m / 900m 邻域绿地占比", "说明": "周边窗口内绿地均值——绿地降温外溢的关键通道"},
        {"类别": "绿地(可干预)", "特征": "到最近绿地距离", "说明": "离最近成片绿地的距离,刻画可达性"},
        {"类别": "建成/地形(背景)", "特征": "建筑高度、建成概率、容积率代理", "说明": "城市形态——热岛主要驱动"},
        {"类别": "建成/地形(背景)", "特征": "夜间灯光", "说明": "人为热排放代理"},
        {"类别": "建成/地形(背景)", "特征": "高程、坡度", "说明": "地形背景"},
    ]
    st.table(feat_rows)
    st.caption("注:经纬度未直接入模,以免地理坐标吸收绿地效应;空间趋势由邻域绿地与建成形态承载。")

    st.markdown("### 4　模型与精度验证")
    c1, c2, c3 = st.columns(3)
    c1.metric("模型", "随机森林")
    c2.metric("空间分块 CV · R²", f"{S['cv_r2']:.2f}")
    c3.metric("空间分块 CV · MAE", f"{S['cv_mae']:.1f} °C")
    st.markdown(
        "- 采用**随机森林回归**(300 棵树)。\n"
        "- 因地表温度存在强**空间自相关**,普通随机交叉验证会高估精度;故用 **6×6 空间分块"
        "交叉验证**(整块留出、5 折),给出诚实的泛化精度:**R²≈{:.2f}、MAE≈{:.1f}°C**。\n"
        "- 下图为特征重要性:城市形态(建筑高度、夜间灯光、建成概率)主导地表温度水平,"
        "绿地类特征是**次级调节项**——这与城市热岛物理一致;绿地的价值体现在"
        "「相对降温幅度」与「空间外溢」上。".format(S["cv_r2"], S["cv_mae"]))
    st.bar_chart(_feature_importance(), height=300)

    st.markdown("### 5　绿地降温的剂量–反应关系")
    st.markdown("固定典型建成区背景,把(本格及邻域)绿地占比从 0 提到 1,模型预测的地表温度变化:")
    st.line_chart(_dose_response(), height=300)
    st.caption("曲线为说明性剂量–反应:绿地占比越高、降温越强,且呈现边际递减。"
               "实际每个地块的降温幅度还取决于其建筑高度、人为热等背景。")

    st.markdown("### 6　绘制多边形后的预测流程")
    st.markdown(
        "1. **设定干预**:多边形内网格的绿地占比设为目标值(新增→0.9,拆除→0.05)。\n"
        "2. **重算绿地特征**:在影响范围内重新计算邻域绿地占比(300m/900m)与到最近绿地距离"
        "——这使周边网格的特征也随之改变,从而预测出**外溢降温**。\n"
        "3. **逐格预测**:用模型预测干预后地表温度,ΔLST = 干预后预测 − 现状基线预测。\n"
        "4. **单调约束**:新增绿地只计降温、拆除只计升温,抑制模型在个别格上的反向噪声。\n"
        "5. **空间平滑**:对 ΔLST 场做掩膜感知高斯平滑(等效热扩散),消除随机森林阶梯差值的斑驳,"
        "得到连续降温场。\n"
        "6. **影响半径自适应**:影响范围随地块大小缩放(等效半径 √(N/π)+余量,约 200–900m),"
        "小地块小范围、大公园大范围,符合公园冷岛(PCI)尺度规律。")

    st.markdown("### 7　从地表温度到健康影响")
    st.markdown(
        "- **ΔLST → 近地气温 ΔT_air**:按经验系数 0.7 折减(地表温度变化大于气温变化)。\n"
        "- **逐格 HIA**:对每个 100m 网格,用其**自身的 ΔT_air × 该格 100m 人口 × 城市基线死亡率 × "
        "热归因比例 ×(1 − RR^ΔT)** 计算可避免/额外病例,再全场求和——而非"
        "「单一温度 × 总人口」的粗略口径。ERF 采用 Liu 2022(主分析)与 Lingyan 2017(敏感性)。")

    st.markdown("### 8　局限与说明")
    st.markdown(
        "- 模型为**观测数据的统计关系**(相关性),非因果实验;迁移到具体新建项目存在不确定性。\n"
        "- 绿地类特征重要性偏低,绝对降温幅度对绿地的敏感度有限;大尺度公园的区域性降温可能被低估。\n"
        "- 「平滑栅格」为展示层的空间插值,使热力图连续;底层 HIA 计算仍用真实 100m 逐格 ΔLST。\n"
        "- 数据为 100m 分辨率,**最小可分辨干预为 1 格(1 公顷)**;更小地块按 1 格处理。\n"
        "- 卫星底图(高德)为 GCJ-02 坐标系,叠加层已做坐标变换对齐;ΔLST→气温、热归因比例等为经验设定。\n"
        "- 本系统用于规划阶段的健康影响**辅助研判**,不替代正式环境健康风险评估。")
    st.caption(f"模型:随机森林 · 空间分块CV R²={S['cv_r2']:.2f} / MAE={S['cv_mae']:.1f}°C · "
               "训练数据:上海 100m 多年夏季合成(约 60.7 万网格)")


def _risk_color(t):
    """风险 0→1 配色:蓝(低)→黄→红(高)。t 为 (H,W) 0-1。返回 (H,W,3)。"""
    def lerp(c0, c1, tt):
        a = np.array([int(c0[i:i+2], 16) for i in (1, 3, 5)], float)
        b = np.array([int(c1[i:i+2], 16) for i in (1, 3, 5)], float)
        return a + (b - a) * tt[..., None]
    t = np.clip(t, 0, 1)
    lo = lerp("#2C7BB6", "#FFFFBF", np.clip(t/0.5, 0, 1))
    hi = lerp("#FFFFBF", "#D7191C", np.clip((t-0.5)/0.5, 0, 1))
    return np.where((t < 0.5)[..., None], lo, hi)


def add_risk_raster(m, prob, bounds, opacity=0.72):
    """把重症风险概率栅格作平滑图层叠加(蓝低→红高)。"""
    import io, base64
    from PIL import Image
    p = prob[::-1]  # 行0=南 → 翻成北上
    mask = np.isfinite(p)
    rgb = _risk_color(np.where(mask, p, 0))
    alpha = (mask * opacity * 255)
    rgba = np.dstack([rgb, alpha[..., None]]).astype(np.uint8)
    buf = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    folium.raster_layers.ImageOverlay(image=uri, bounds=bounds, opacity=opacity).add_to(m)


def add_delta_raster(m, delta, bounds, opacity=0.78):
    """风险变化 Δ 栅格:蓝=风险下降,红=风险上升。"""
    import io, base64
    from PIL import Image
    p = delta[::-1]
    mask = np.isfinite(p)
    vmax = max(float(np.nanmax(np.abs(p))), 0.02)
    t = np.clip(np.abs(np.where(mask, p, 0)) / vmax, 0, 1)[..., None]
    cool = (np.where(mask, p, 0) <= 0)[..., None]

    def ramp(c0, c1):
        a = np.array([int(c0[i:i+2], 16) for i in (1, 3, 5)], float)
        b = np.array([int(c1[i:i+2], 16) for i in (1, 3, 5)], float)
        return a + (b - a) * t
    rgb = np.where(cool, ramp("#F7F7F7", "#2C7BB6"), ramp("#F7F7F7", "#D7191C"))
    alpha = (mask * (0.25 + 0.73 * t[..., 0]) * 255)
    rgba = np.dstack([rgb, alpha[..., None]]).astype(np.uint8)
    buf = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    folium.raster_layers.ImageOverlay(image=uri, bounds=bounds, opacity=opacity).add_to(m)


def add_drisk_grid(m, lats, lons, drisk):
    """把逐格 Δ重症风险以彩色方块叠加(蓝=风险下降/红=上升)。"""
    if len(drisk) == 0:
        return
    vmax = max(float(np.max(np.abs(drisk))), 0.01)
    for la, lo, d in zip(lats, lons, drisk):
        col = dlst_color(float(d), vmax)   # 负→蓝, 正→红
        folium.Rectangle(bounds=[[la-HALF_LAT, lo-HALF_LON], [la+HALF_LAT, lo+HALF_LON]],
                         color=col, weight=0, fill=True, fill_color=col, fill_opacity=0.75,
                         tooltip=f"Δ重症风险 {d:+.3f}").add_to(m)


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


@st.cache_data(show_spinner=False)
def _risk_cached(modis_lst, ems_extra, built_scale):
    prob, bounds, meta = heat_risk.risk_latlon(
        modis_lst=modis_lst, ems_extra=list(ems_extra) if ems_extra else None,
        built_scale=built_scale)
    return prob, bounds, heat_risk.city_stats(prob)


VAR_ZH_HEAT = {"MODIS_LST": "当天地表温度", "dw_built": "建成密度",
               "dis_ems": "到最近急救站距离"}
VAR_DIR_HEAT = {"MODIS_LST": "越热→越重", "dw_built": "越密→越重",
                "dis_ems": "越远→越重"}


@st.cache_data(show_spinner=False)
def _heat_component_data():
    """打包中暑风险组件所需数据(网格有效格 + 模型 + 病例点),供前端 JS 实时算图。"""
    import os
    g = heat_risk._state()["g"]; mdl = heat_risk.model_info()
    built = g["dw_built"].astype(float); dems = g["dis_ems"].astype(float)
    pop = np.nan_to_num(g["pop"].astype(float)) if "pop" in g else np.zeros_like(built)
    mask = np.isfinite(built) & np.isfinite(dems)
    iy, ix = np.where(mask)
    cells = {
        "ix": ix.astype(int).tolist(), "iy": iy.astype(int).tolist(),
        "built": np.round(built[mask] * 1000).astype(int).tolist(),   # 0-1000
        "dems": np.round(dems[mask]).astype(int).tolist(),            # 米
        "pop": np.round(pop[mask]).astype(int).tolist(),              # 每格人口
    }
    meta = {"lon0": float(g["lon0"]), "lat0": float(g["lat0"]), "res": float(g["res"]),
            "nx": int(g["nx"]), "ny": int(g["ny"])}
    cp = heat_risk.cases_points()
    cases = {"lon": [round(float(x), 5) for x in cp["lon"]],
             "lat": [round(float(x), 5) for x in cp["lat"]],
             "sev": [int(s) for s in cp["severe"]]} if cp is not None else {"lon": [], "lat": [], "sev": []}
    ems = {"lon": [], "lat": []}
    try:
        E = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "heat_ems_points.npz"), allow_pickle=True)
        ems = {"lon": [round(float(x), 5) for x in E["lon"]],
               "lat": [round(float(x), 5) for x in E["lat"]]}
    except Exception:
        pass
    return {"cells": cells, "meta": meta, "model": mdl, "cases": cases, "ems": ems}


def _heat_component_html(basemap):
    import json
    d = _heat_component_data()
    if basemap == "浅色地图":
        turl = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
    else:
        turl = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
    payload = json.dumps({**d, "turl": turl}, separators=(",", ":"))
    tmpl = _HEAT_HTML_TMPL.replace("/*__DATA__*/null", payload)
    return tmpl


_HEAT_HTML_TMPL = r"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 body{margin:0;font-family:'Noto Sans SC','Microsoft YaHei',sans-serif;}
 #map{height:560px;width:100%;border-radius:10px;}
 .panel{background:#F6FCF8;border:1px solid #DCEEE3;border-radius:10px;padding:10px 14px;margin-bottom:8px;
   display:flex;flex-wrap:wrap;gap:18px;align-items:center;}
 .ctl{display:flex;flex-direction:column;font-size:13px;color:#33574a;min-width:150px;}
 .ctl b{color:#1B6B3A;font-size:13px;}
 input[type=range]{width:170px;accent-color:#2E9E5B;}
 .seg button{border:1px solid #2E9E5B;background:#fff;color:#1B6B3A;padding:3px 10px;cursor:pointer;font-size:12px;}
 .seg button.on{background:#2E9E5B;color:#fff;}
 .seg button:first-child{border-radius:6px 0 0 6px;} .seg button:last-child{border-radius:0 6px 6px 0;}
 .btn{border:1px solid #2E9E5B;background:#fff;color:#1B6B3A;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;}
 .stat{font-size:13px;color:#33574a;} .stat b{font-size:18px;color:#1B6B3A;}
 .legend{position:absolute;z-index:500;bottom:14px;right:10px;background:rgba(255,255,255,.9);
   padding:6px 9px;border-radius:6px;font-size:11px;color:#444;box-shadow:0 1px 3px rgba(0,0,0,.2);}
 .lgbar{height:9px;width:120px;border-radius:3px;margin:3px 0;}
</style></head><body>
<div class="panel">
  <div class="ctl"><b>当天地表温度 <span id="vlst"></span>°C</b><input id="lst" type="range" step="0.5"></div>
  <div class="ctl"><b>地图显示</b><div class="seg"><button id="vr" class="on">风险水平</button><button id="vd">相对基线 Δ</button><button id="ve">急救站效果</button></div></div>
  <div class="ctl"><b>急救站 what-if</b>
    <div><label style="font-size:12px"><input type="checkbox" id="addems"> 点击地图落站</label>
    <button class="btn" id="clr">清除</button> <span id="nems" style="font-size:12px"></span></div></div>
  <div class="ctl"><label style="font-size:12px"><input type="checkbox" id="exems" checked> 现状急救站</label>
    <label style="font-size:12px"><input type="checkbox" id="cases"> 叠加病例点</label></div>
  <div class="stat">平均重症风险 <b id="smean">–</b> &nbsp; 高风险面积 <b id="shigh">–</b> &nbsp; <span id="emsbox" style="display:none">急救站效果:<b id="sems">–</b></span></div>
</div>
<div style="position:relative"><div id="map"></div>
  <div class="legend"><div id="lgttl">重症风险</div><div class="lgbar" id="lgbar"></div>
   <div style="display:flex;justify-content:space-between"><span id="lglo"></span><span id="lghi"></span></div></div>
</div>
<script>
var D = /*__DATA__*/null;
var M=D.meta, MO=D.model, C=D.cells;
var b=MO.beta, mu=MO.mean, sd=MO.std;
var N=C.ix.length;
// 预存每格 lon/lat
var clon=new Float64Array(N), clat=new Float64Array(N);
for(var i=0;i<N;i++){clon[i]=M.lon0+(C.ix[i]+0.5)*M.res; clat[i]=M.lat0+(C.iy[i]+0.5)*M.res;}
var south=M.lat0, west=M.lon0, north=M.lat0+M.ny*M.res, east=M.lon0+M.nx*M.res;
var bounds=[[south,west],[north,east]];

var map=L.map('map',{center:[31.17,121.45],zoom:9});
L.tileLayer(D.turl,{subdomains:'abcd',maxZoom:19,attribution:'© OpenStreetMap © CARTO'}).addTo(map);
map.fitBounds(bounds);
// 组件在隐藏标签里初始化时容器高度为0,Leaflet取不到尺寸→会退回全球视野。
// 等容器获得真实尺寸(切到本标签)时刷新尺寸并定位到上海,仅首次自动 fitBounds。
var _fitted=false;
function _fixmap(){ var el=document.getElementById('map');
  if(el && el.clientWidth>50 && el.clientHeight>50){ map.invalidateSize();
    if(!_fitted){ map.fitBounds(bounds); _fitted=true; } } }
setTimeout(_fixmap,300); setTimeout(_fixmap,1200);
try{ new ResizeObserver(_fixmap).observe(document.getElementById('map')); }catch(e){}

var cv=document.createElement('canvas'); cv.width=M.nx; cv.height=M.ny;
var ctx=cv.getContext('2d'); var imgd=ctx.createImageData(M.nx,M.ny);
var overlay=L.imageOverlay(cv.toDataURL(),bounds,{opacity:0.72}).addTo(map);

var emsPts=[], emsMarkers=[], caseLayer=null, addMode=false, view='risk';
var baseProb=null;
// 现状急救站(202个,灰色)
var exLayer=L.layerGroup();
for(var i=0;i<D.ems.lon.length;i++){
  L.circleMarker([D.ems.lat[i],D.ems.lon[i]],{radius:3,weight:1,color:'#444',
    fillColor:'#999',fillOpacity:0.85}).bindTooltip('现状急救站').addTo(exLayer);}
exLayer.addTo(map);
document.getElementById('exems').onchange=function(){ if(this.checked)exLayer.addTo(map); else map.removeLayer(exLayer); };

function sig(z){return 1/(1+Math.exp(-z));}
function computeProb(lst,ems){
  var p=new Float64Array(N);
  var zc=MO.const + b.MODIS_LST*(lst-mu.MODIS_LST)/sd.MODIS_LST;
  for(var i=0;i<N;i++){
    var dem=C.dems[i];
    for(var k=0;k<ems.length;k++){
      var dx=(clon[i]-ems[k][0])*111000*Math.cos(clat[i]*Math.PI/180);
      var dy=(clat[i]-ems[k][1])*111000; var dd=Math.sqrt(dx*dx+dy*dy);
      if(dd<dem)dem=dd;
    }
    var z=zc + b.dis_ems*(dem-mu.dis_ems)/sd.dis_ems;
    p[i]=sig(z);
  }
  return p;
}
function lerp(a,c,t){return [a[0]+(c[0]-a[0])*t,a[1]+(c[1]-a[1])*t,a[2]+(c[2]-a[2])*t];}
function riskColor(v){ // 0..1 蓝→黄→红
  if(v<0.5)return lerp([44,123,182],[255,255,191],v/0.5);
  return lerp([255,255,191],[215,25,28],(v-0.5)/0.5);
}
function deltaColor(v,vmax){ // 蓝(降)白(0)红(升)
  var t=Math.min(Math.abs(v)/vmax,1);
  if(v<=0)return lerp([247,247,247],[44,123,182],t);
  return lerp([247,247,247],[215,25,28],t);
}
function draw(){
  var lst=+document.getElementById('lst').value;
  var prob=computeProb(lst,emsPts);
  var arr=prob, vmax=0.3, emsmsg='–';
  if(view==='delta'){ arr=new Float64Array(N); var mx=1e-6;
    for(var i=0;i<N;i++){arr[i]=prob[i]-baseProb[i]; if(Math.abs(arr[i])>mx)mx=Math.abs(arr[i]);} vmax=mx; }
  else if(view==='ems'){ // 加站 vs 不加站(同情景),隔离急救站效果
    var noems=computeProb(lst,[]); arr=new Float64Array(N); var mx2=1e-4, ben=0, sumd=0, mind=0, popben=0;
    for(var i=0;i<N;i++){ arr[i]=prob[i]-noems[i];
      if(Math.abs(arr[i])>mx2)mx2=Math.abs(arr[i]);
      if(arr[i]<-0.002){ben++; sumd+=arr[i]; if(arr[i]<mind)mind=arr[i]; popben+=C.pop[i];} }
    vmax=mx2;
    emsmsg = emsPts.length? ('受益面积 '+(ben*0.25).toFixed(1)+' km²,覆盖人口 '
             +Math.round(popben).toLocaleString()+';重症化概率平均降 '
             +(ben?(-sumd/ben*100).toFixed(2):'0')+' 个百分点,最大降 '+(-mind*100).toFixed(2)+' 个百分点')
             : '勾选「点击地图落站」后点图落站(站点可拖动)';
  }
  var dat=imgd.data; for(var j=0;j<dat.length;j++)dat[j]=0;
  var sum=0,high=0;
  for(var i=0;i<N;i++){
    var col, al;
    if(view==='risk'){ col=riskColor(prob[i]); al=185; }
    else if(view==='delta'){ col=deltaColor(arr[i],vmax); al=185; }
    else { col=deltaColor(arr[i],vmax); al=30+210*Math.min(Math.abs(arr[i])/vmax,1); } // ems:按降幅放大对比
    var px=C.ix[i], py=M.ny-1-C.iy[i]; var o=(py*M.nx+px)*4;
    dat[o]=col[0];dat[o+1]=col[1];dat[o+2]=col[2];dat[o+3]=al;
    sum+=prob[i]; if(prob[i]>=0.7)high++;
  }
  ctx.putImageData(imgd,0,0); overlay.setUrl(cv.toDataURL());
  document.getElementById('vlst').textContent=lst.toFixed(1);
  document.getElementById('smean').textContent=(sum/N).toFixed(2);
  document.getElementById('shigh').textContent=(100*high/N).toFixed(0)+'%';
  document.getElementById('emsbox').style.display = (view==='ems')?'inline':'none';
  document.getElementById('sems').textContent = emsmsg;
  updLegend(vmax);
}
function updLegend(vmax){
  var bar=document.getElementById('lgbar');
  if(view==='delta'||view==='ems'){
    document.getElementById('lgttl').textContent = view==='ems'?'急救站效果(风险下降)':'风险变化 Δ';
    bar.style.background='linear-gradient(90deg,#2C7BB6,#F7F7F7,#D7191C)';
    document.getElementById('lglo').textContent='降 −'+vmax.toFixed(3);
    document.getElementById('lghi').textContent='升 +'+vmax.toFixed(3);}
  else{document.getElementById('lgttl').textContent='重症风险';
    bar.style.background='linear-gradient(90deg,#2C7BB6,#FFFFBF,#D7191C)';
    document.getElementById('lglo').textContent='低';document.getElementById('lghi').textContent='高';}
}
// 初始化滑块范围
var sl=document.getElementById('lst');
sl.min=MO.modis_lst_p10; sl.max=(MO.modis_lst_p90+2); sl.value=MO.modis_lst_ref;
baseProb=computeProb(MO.modis_lst_ref,[]);
sl.addEventListener('input',draw);
function setView(v){view=v;['vr','vd','ve'].forEach(function(id){document.getElementById(id).classList.remove('on');});
  document.getElementById({risk:'vr',delta:'vd',ems:'ve'}[v]).classList.add('on');draw();}
document.getElementById('vr').onclick=function(){setView('risk');};
document.getElementById('vd').onclick=function(){setView('delta');};
document.getElementById('ve').onclick=function(){setView('ems');};
document.getElementById('addems').onchange=function(){addMode=this.checked;};
document.getElementById('clr').onclick=function(){emsPts=[];emsMarkers.forEach(function(m){map.removeLayer(m);});emsMarkers=[];document.getElementById('nems').textContent='';draw();};
document.getElementById('cases').onchange=function(){
  if(this.checked){caseLayer=L.layerGroup();for(var i=0;i<D.cases.lon.length;i++){
    L.circleMarker([D.cases.lat[i],D.cases.lon[i]],{radius:2.5,weight:0,
      fillColor:D.cases.sev[i]?'#C62828':'#1f6feb',fillOpacity:0.7}).addTo(caseLayer);}
    caseLayer.addTo(map);} else if(caseLayer){map.removeLayer(caseLayer);}};
map.on('click',function(e){ if(!addMode)return;
  var idx=emsPts.length;
  emsPts.push([e.latlng.lng,e.latlng.lat]);
  var mk=L.marker([e.latlng.lat,e.latlng.lng],{draggable:true});
  mk.bindTooltip('新增急救站(可拖动)');
  mk.on('drag',function(ev){ var ll=ev.target.getLatLng(); emsPts[idx]=[ll.lng,ll.lat];
    if(view!=='ems'){view='ems';['vr','vd','ve'].forEach(function(id){document.getElementById(id).classList.remove('on');});document.getElementById('ve').classList.add('on');}
    draw(); });
  mk.addTo(map); emsMarkers.push(mk);
  document.getElementById('nems').textContent='已加'+emsPts.length+'个'; setView('ems');});
draw();
</script></body></html>
"""


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


def _heat_ems():
    """② 急救站布局模拟(客户端实时组件:现状站点 + 落站/拖站 what-if)。"""
    import streamlit.components.v1 as components
    st.caption("灰点为现状 202 个急救站,底图为重症风险预测。拖动「当天地表温度」看高温日风险;"
               "勾选「点击地图落站」后点图新增急救站(可拖动),实时显示重症化概率下降、受益面积与覆盖人口。")
    basemap = st.selectbox("底图", ["街道地图", "浅色地图"], index=0, key="heat_base")
    components.html(_heat_component_html(basemap), height=660, scrolling=False)


def render_heat_risk():
    """热相关健康风险诊断与调控:① 风险诊断 ② 急救站布局模拟(两个标签板块)。"""
    mi = heat_risk.model_info()
    st.markdown("## 热相关健康风险诊断与调控")
    st.caption("基于 287 例 60 岁以上中暑病例的 logistic 重症模型(重症 vs 轻症),显著变量为当天地表温度"
               "(p<0.01)与到最近急救站距离。关联性模型,非交叉验证预测,用于规划辅助研判。")
    tab1, tab2 = st.tabs(["① 风险诊断:建成环境→地表温度→重症化风险", "② 急救站布局模拟"])
    with tab1:
        _heat_diag()
    with tab2:
        _heat_ems()

    with st.expander("模型与显著变量(logistic 重症模型)", expanded=False):
        b = mi["beta"]; pv = mi.get("pval", {})
        rows = [{"变量": VAR_ZH_HEAT.get(v, v), "OR/标准差": f"{np.exp(b[v]):.2f}",
                 "p 值": f"{pv.get(v, float('nan')):.3f}", "方向": VAR_DIR_HEAT.get(v, "")}
                for v in mi["vars"]]
        st.table(rows)
        st.markdown(
            "- 样本:287 例 60+ 中暑病例(167 重症/120 轻症),2023–2025 夏季。\n"
            "- 模型**只保留 当天地表温度(p<0.01)+ 到最近急救站距离**;建成密度/容积率/绿地**不直接入模**,"
            "而是经「② 局部改造连锁」通过影响 LST 间接作用。纳凉站点距离/密度经检验不显著(p≈0.2),未纳入。\n"
            "- McFadden R²≈%.2f;in-sample AUC≈%.2f,空间分块 CV AUC≈0.59(弱但显著)。\n"
            "- 显著的热信号是「当天高温」(时间维);本图为**关联性风险图**,非交叉验证预测,辅助研判而非精确定点。\n"
            "- LST 每 +1°C 约使重症 OR×1.12(连锁分析据此把 ΔLST 换算为风险变化)。\n"
            "- 个体因素(基础病、送医及时性)主导重症,未纳入。" % (mi["mcfadden_r2"], mi.get("auc_insample", 0.62)))


st.set_page_config(
    page_title="健康城市规划与智能评估平台",
    page_icon="🌳",
    layout="wide",
)

# ===== 全局视觉打磨 (Phase 3) =====
# Noto Serif SC(标题)/ Noto Sans SC(正文),健康绿主题,卡片化,大字数字。
# 字体走 Google Fonts CDN,失败则回退系统宋体/黑体,不影响功能。
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@500;600;700&display=swap');

    html, body, [class*="css"], .stMarkdown, .stMetric {{
        font-family: 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
    }}
    h1, h2, h3, h4, h5 {{
        font-family: 'Noto Serif SC', 'SimSun', serif !important;
        color: {GREEN_DEEP};
        letter-spacing: 0.5px;
    }}
    /* 主区留白更舒展 */
    .block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1200px; }}

    /* 指标卡:浅绿底 + 绿色左边线,数字大而醒目 */
    div[data-testid="stMetric"] {{
        background: #F6FCF8;
        border: 1px solid #DCEEE3;
        border-left: 4px solid {HEALTH_GREEN};
        padding: 0.7rem 0.95rem;
        border-radius: 10px;
        box-shadow: 0 1px 2px rgba(27,107,58,0.05);
    }}
    div[data-testid="stMetricValue"] {{
        font-size: 1.9rem; font-weight: 700; color: {GREEN_DEEP};
    }}
    div[data-testid="stMetricLabel"] p {{ color: #5a7a66; font-weight: 500; }}

    /* 按钮:健康绿、圆角、加粗 */
    .stButton > button, .stDownloadButton > button {{
        border-radius: 9px; font-weight: 600; border: 1px solid {HEALTH_GREEN};
    }}
    .stButton > button[kind="primary"] {{
        background: {HEALTH_GREEN}; border-color: {HEALTH_GREEN};
    }}
    .stButton > button[kind="primary"]:hover {{
        background: {GREEN_DEEP}; border-color: {GREEN_DEEP};
    }}

    /* 侧栏:浅绿底 + 右侧细分隔 */
    section[data-testid="stSidebar"] {{
        background: #EAF7EF; border-right: 1px solid #DCEEE3;
    }}

    /* 结果表:表头浅绿、行距舒适 */
    .stTable thead tr th {{
        background: #EAF7EF !important; color: {GREEN_DEEP} !important; font-weight: 600;
    }}
    .stTable td, .stTable th {{ padding: 0.55rem 0.7rem !important; }}

    /* 隐藏顶部菜单与页脚,演示更干净 */
    #MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ===== 顶部标题 =====
st.markdown(
    f"""
    <div style="background:linear-gradient(90deg,#EAF7EF 0%,#F6FCF8 100%);
                border-left:6px solid {HEALTH_GREEN};
                border-radius:8px; padding:0.9rem 1.2rem; margin-bottom:1.2rem;">
      <div style="color:{HEALTH_GREEN}; font-size:0.95rem; letter-spacing:2px; font-weight:600;">
        同济大学建筑与城市规划学院 · 健康城市实验室
      </div>
      <div style="font-family:'Noto Serif SC','SimSun',serif; font-size:1.9rem;
                  font-weight:700; color:{GREEN_DEEP}; letter-spacing:1px;">
        健康城市规划与智能评估平台
      </div>
      <div style="color:#5a7a66; font-size:0.9rem;">
        AI 辅助 · 热暴露—健康影响量化 (HIA) 演示系统
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ===== 左侧栏:模式 + 案例选择 =====
with st.sidebar:
    st.markdown("### 评估模式")
    mode = st.radio(
        "模式",
        ["示范案例", "自定义评估", "热相关健康风险诊断与调控", "建模方法说明"],
        label_visibility="collapsed",
    )
    selected_id = None
    if mode == "示范案例":
        st.markdown("---")
        st.markdown("### 示范案例")
        selected_id = st.radio(
            "请选择一个示范案例",
            options=list(CASES.keys()),
            format_func=lambda cid: CASES[cid]["label"],
            label_visibility="collapsed",
        )

# ===== 主区 =====
if mode == "示范案例":
    case = CASES[selected_id]
    # 案例标签 + 标题 + 背景
    st.markdown(
        f"""
        <span style="background:{case['tag_color']}; color:white; padding:2px 10px;
                     border-radius:10px; font-size:0.85rem;">{case['tag']}</span>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(f"## {case['project_name']}")
    st.caption(f"{case['city']} · {case['district']} · {case['subdistrict']}")
    st.write(case["background"])
    st.markdown("---")
    render_case_flow(case, show_map=True)
elif mode == "自定义评估":
    render_custom_mode()
elif mode == "热相关健康风险诊断与调控":
    render_heat_risk()
else:
    render_methodology()
