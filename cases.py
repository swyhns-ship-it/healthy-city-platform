"""
3 个示范案例的所有预设数据。
位置基于上海真实街道,但具体地块和数值为 demo 用途。
"""

CASES = {
    "case_1": {
        "id": "case_1",
        "label": "案例一 · 漕河泾街道停车场转绿地",
        "label_short": "徐汇 · 4 公顷新增",
        "tag": "新增绿地",
        "tag_color": "#2E7D32",
        # 项目描述
        "project_name": "徐汇区田林街道某高温建成地块改造社区公园",
        "city": "上海市",
        "district": "徐汇区",
        "subdistrict": "田林街道",  # 自动按经纬度推断,待孙老师校正
        # 地理 (站点由 100m 栅格数据驱动选定:建成、低绿、高温、有有效数据)
        "center_lng": 121.4182,
        "center_lat": 31.1895,
        # 多边形 (落入 4 个 100m 网格 ≈ 4 公顷的连续建成地块)
        "polygon": [
            [121.41730, 31.18876],
            [121.41946, 31.18876],
            [121.41946, 31.19057],
            [121.41730, 31.19057],
            [121.41730, 31.18876],
        ],
        # 干预参数 (delta_lst_C 由 greenfrac 0.06->0.9 经随机森林预测)
        "intervention_type": "greenspace_add",
        "intervention_type_zh": "新增城市绿地",
        "size_ha": 4.0,
        "greenfrac_before": 0.06,
        "greenfrac_after": 0.90,
        # ΔLST = 多边形内逐格预测降温均值;HIA 用整个 ΔLST 场(含外溢)逐格计算
        "delta_lst_C": -3.65,
        "delta_air_temp_C": -2.56,
        # 人口 = 实质降温(≥0.2°C, 含外溢)范围内 100m 栅格人口求和
        "population": 29216,
        "population_brief": "实质温度变化(≥0.2°C, 含空间外溢)范围内常住居民, 100m 人口栅格求和",
        "age_distribution": {
            "0_14": 0.12,
            "15_64": 0.66,
            "65plus": 0.22,
        },
        # 基线 (来自上海卫健委 2024 年统计公报)
        "baseline_mortality_per_1000": 6.28,
        "baseline_cvd_mortality_per_1000": 2.70,
        # 环境
        "climate_zone": "hot_summer_cold_winter",
        "summer_lst_baseline_C": 49.5,  # 该地块 100m 栅格多年夏季合成地表温度
        "evaluation_years": 10,
        # 描述文字
        "background": (
            "徐汇区田林街道一带为高密度商办与居住混合区,夏季热岛效应显著,"
            "现状夏季地表温度约 49.5℃、绿地占比不足 10%。"
            "拟将一处约 4 公顷的高温建成地块(地面停车与硬质场地)改造为社区公园,"
            "为周边约 3 万常住居民提供降温与休憩空间。"
        ),
    },

    "case_2": {
        "id": "case_2",
        "label": "案例二 · 花木街道绿地拆除建地铁出口",
        "label_short": "浦东 · 1 公顷拆除",
        "tag": "绿地损失",
        "tag_color": "#C62828",
        "project_name": "浦东新区金杨新村街道某社区绿地临时拆除",
        "city": "上海市",
        "district": "浦东新区",
        "subdistrict": "金杨新村街道",  # 自动按经纬度推断,待孙老师校正
        # 站点由栅格数据驱动选定:现状绿地、周边有居民、有有效数据
        "center_lng": 121.5639,
        "center_lat": 31.2377,
        # 多边形 (1 个 100m 网格 ≈ 1 公顷的现状绿地)
        "polygon": [
            [121.56350, 31.23739],
            [121.56460, 31.23739],
            [121.56460, 31.23829],
            [121.56350, 31.23829],
            [121.56350, 31.23739],
        ],
        "intervention_type": "greenspace_remove",
        "intervention_type_zh": "拆除既有绿地",
        "size_ha": 1.0,
        "greenfrac_before": 0.55,
        "greenfrac_after": 0.05,
        "delta_lst_C": 0.95,
        "delta_air_temp_C": 0.67,
        "population": 4489,
        "population_brief": "实质温度变化(≥0.2°C, 含空间外溢)范围内常住居民, 100m 人口栅格求和",
        "age_distribution": {
            "0_14": 0.10,
            "15_64": 0.68,
            "65plus": 0.22,
        },
        "baseline_mortality_per_1000": 6.28,
        "baseline_cvd_mortality_per_1000": 2.70,
        "climate_zone": "hot_summer_cold_winter",
        "summer_lst_baseline_C": 45.4,  # 该地块 100m 栅格多年夏季合成地表温度
        "evaluation_years": 3,
        "background": (
            "浦东新区金杨新村街道为高密度居住片区,因拟建轨道交通某出入口,"
            "需临时拆除一处约 1 公顷的既有社区绿地(现状绿地占比约 0.55)。"
            "该绿地承担了周边居民的微气候调节与休憩功能,"
            "拆除后预计将带来短期的热岛加剧与健康负面影响。"
        ),
    },

    "case_3": {
        "id": "case_3",
        "label": "案例三 · 青浦区大型郊野公园新建",
        "label_short": "青浦 · 81 公顷新增",
        "tag": "大型新增",
        "tag_color": "#2E7D32",
        "project_name": "青浦区白鹤镇某大型郊野公园新建",
        "city": "上海市",
        "district": "青浦区",
        "subdistrict": "白鹤镇",  # 自动按经纬度推断,待孙老师校正
        # 站点由栅格数据驱动选定:缺绿农田、连续大片、夏季高温、有有效数据
        "center_lng": 121.1081,
        "center_lat": 31.3087,
        # 多边形 (约 81 公顷的连续缺绿地块, 9×9 个 100m 网格)
        "polygon": [
            [121.10424, 31.30541],
            [121.11388, 31.30541],
            [121.11388, 31.31365],
            [121.10424, 31.31365],
            [121.10424, 31.30541],
        ],
        "intervention_type": "greenspace_add",
        "intervention_type_zh": "新增城市绿地",
        "size_ha": 81.0,
        "greenfrac_before": 0.02,
        "greenfrac_after": 0.90,
        "delta_lst_C": -5.55,
        "delta_air_temp_C": -3.89,
        "population": 6505,
        "population_brief": "实质温度变化(≥0.2°C, 含空间外溢)范围内常住居民, 100m 人口栅格求和",
        "age_distribution": {
            "0_14": 0.11,
            "15_64": 0.62,
            "65plus": 0.27,  # 郊区青壮年外流,老龄化亦突出
        },
        "baseline_mortality_per_1000": 6.28,
        "baseline_cvd_mortality_per_1000": 2.70,
        "climate_zone": "hot_summer_cold_winter",
        "summer_lst_baseline_C": 50.5,  # 该缺绿地块 100m 栅格多年夏季合成地表温度(裸/农田显著偏高)
        "evaluation_years": 20,
        "background": (
            "青浦区白鹤镇一带地处上海西郊,现状以农田与零散建设用地为主,"
            "绿地占比不足 5%、夏季地表温度高达 50℃ 左右,缺乏成规模的降温空间。"
            "拟统筹生态修复与游憩功能,新建一处约 81 公顷的大型郊野公园,"
            "形成区域性降温绿核、改善周边乡镇人居热环境。"
        ),
    },
}


# 硬编码 ERF (Phase 1 简化版,只用 Liu 2022 + Lingyan 2017)
ERF_PRIMARY_CVD = {
    "rr_point": 1.021,
    "rr_low": 1.020,
    "rr_high": 1.023,
    "source": "Liu Y, et al. 2022. Lancet Planetary Health",
    "label": "Liu 2022 (中国全国 meta 分析)",
    "unit": "per 1°C above MMT",
}
ERF_PRIMARY_ALLCAUSE = {
    "rr_point": 1.014,
    "rr_low": 1.012,
    "rr_high": 1.016,
    "source": "Liu Y, et al. 2022. Lancet Planetary Health",
    "label": "Liu 2022 (中国全国 meta 分析)",
    "unit": "per 1°C above MMT",
}
ERF_SENSITIVITY_CVD = {
    "rr_point": 1.0359,
    "rr_low": 1.0252,
    "rr_high": 1.0471,
    "source": "Lingyan Zhang, 2017. International Journal of Disaster Risk Science",
    "label": "Lingyan 2017 (东部中国 25 城市,外推自 P99)",
    "unit": "per 1°C (从 P99 vs MMT 线性外推)",
    "original_rr": 1.28,
    "original_ci": [1.19, 1.38],
    "delta_t_assumed": 7.0,
}
