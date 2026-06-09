# -*- coding: utf-8 -*-
"""健康影响评估(HIA):绿地干预示范案例 + 自定义地块评估。"""
import streamlit as st
import folium
from streamlit_folium import st_folium

from cases import CASES
from hia_engine import compute_hia, compute_hia_gridded
from report_docx import build_report_docx
import green_lst
from geo import (wgs2gcj, gcj2wgs, _identity, _add_basemap,
                 add_dlst_grid, add_dlst_raster, build_draw_map,
                 polygon_area_ha, in_shanghai)
from theme import HEALTH_GREEN, page_header


def get_field(case):
    """对案例多边形调用 v2 模型,得到含外溢的逐格 ΔLST 场(结果在进程内缓存)。"""
    mode = "add" if case["intervention_type"] == "greenspace_add" else "remove"
    return green_lst.compute_field(case["polygon"], mode=mode,
                                   target_greenfrac=case.get("greenfrac_after"))


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
    page_header(
        "绿地规划健康影响评估 · 在地图上绘制地块",
        "用地图左上角绘制工具(多边形 / 矩形)画出目标地块,系统调用上海 100m 地温模型"
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


def page_hia_cases():
    page_header("健康影响评估 · 绿地干预示范案例")
    cid = st.selectbox("选择示范案例", list(CASES.keys()),
                       format_func=lambda c: CASES[c]["label"])
    case = CASES[cid]
    st.markdown(
        f"<span style='background:{case['tag_color']};color:white;padding:2px 10px;"
        f"border-radius:10px;font-size:0.85rem;'>{case['tag']}</span>", unsafe_allow_html=True)
    st.markdown(f"### {case['project_name']}")
    st.caption(f"{case['city']} · {case['district']} · {case['subdistrict']}")
    st.write(case["background"])
    st.markdown("---")
    render_case_flow(case, show_map=True)
