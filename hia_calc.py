# -*- coding: utf-8 -*-
"""规划方案 HIA 计算器引擎 —— 实现专利《一种面向规划方案的健康结果模拟预测方法》。

路径:城市规划方案(5D 指标变化)→ 出行方式变化 → 风险暴露变化(交通 PM2.5 / 体力活动)
      → 暴露-响应函数(ERF)→ 相对风险 RR → 人群归因分数 PAF → 健康结果变化。
纯公式 + 内置参数(专利表1弹性量、表2 ERF),无需数据文件/模型。被 views/hia_calc.py 调用。
"""
import os
import math

_DIR = os.path.dirname(os.path.abspath(__file__))
NATIONAL_PM25 = 30.0   # 全国地级及以上城市 PM2.5 年均(2023《中国生态环境状况公报》,339 城市)


def load_cities():
    """读取内置城市全因死亡率库(316 城,来自各地统计年鉴/公报)。"""
    import pandas as pd
    return pd.read_csv(os.path.join(_DIR, "city_mortality.csv"))

# 表1:5D 指标对 小汽车/步行 出行量的弹性量(指标变化% × 弹性 = 出行变化%)。None=该指标不适用。
ELASTICITY = {
    "pop_density":  {"zh": "人口密度", "unit": "人/km²", "car": -0.04, "walk": 0.07},
    "job_density":  {"zh": "就业密度", "unit": "人/km²", "car": 0.00, "walk": 0.04},
    "comm_far":     {"zh": "商业容积率", "unit": "", "car": None, "walk": 0.07},
    "land_mix":     {"zh": "用地混合度(SHDI)", "unit": "", "car": -0.09, "walk": 0.15},
    "road_density": {"zh": "路网密度", "unit": "km/km²", "car": -0.12, "walk": 0.39},
    "intersection": {"zh": "四向交叉口百分比", "unit": "%", "car": -0.12, "walk": -0.06},
    "job_transit":  {"zh": "工作地公交可达性", "unit": "%", "car": -0.05, "walk": None},
    "dist_shop":    {"zh": "到商店距离", "unit": "m", "car": None, "walk": -0.25},
    # 注:专利表1印为 car=-0.05/walk=0.15,但与表3工作案例(距离-40%→步行+6.00/小汽车-2.00)矛盾;
    #     按案例的物理合理方向(距离↓→步行↑、小汽车↓)取 car=+0.05/walk=-0.15。
    "dist_transit": {"zh": "到最近公交站距离", "unit": "m", "car": 0.05, "walk": -0.15},
}
IND_ORDER = list(ELASTICITY.keys())

# 表2:暴露-响应函数。pm25:每 10 ug/m³ 的 RR(>1,污染升风险升);pa:(RR, 单位 MET·min/week)(<1,体力活动保护)
OUTCOMES = {
    "全因死亡":     {"pm25": 1.08, "pa": (0.81, 660)},
    "心血管疾病":   {"pm25": 1.11, "pa": (0.909, 600)},
    "缺血性心脏病": {"pm25": 1.16},
    "中风":         {"pm25": 1.11, "pa": (0.910, 600)},
    "呼吸系统疾病": {"pm25": 1.10},
    "慢阻肺":       {"pm25": 1.11},
    "肺癌":         {"pm25": 1.12},
    "二型糖尿病":   {"pa": (0.980, 600)},
    "结直肠癌":     {"pa": (0.978, 600)},
    "乳腺癌":       {"pa": (0.987, 600)},
    "痴呆":         {"pa": (0.72, 1980)},
}

# 顾村案例默认值(专利表3),用于演示与校验
CASE_5D = {
    "pop_density":  (13060, 17858), "job_density": (4101, 4745), "comm_far": (1.80, 2.54),
    "land_mix": (0.08, 0.15), "road_density": (4.46, 6.00), "intersection": (61.83, 64.07),
    "job_transit": (10.33, 22.58), "dist_shop": (390, 322), "dist_transit": (2300, 1380),
}
CASE_PM25, CASE_CAR_FRAC, CASE_WALK_MIN = 35.0, 26.0, 17.38   # PM2.5总浓度, 小汽车贡献%, 通勤步行 min/日
WALK_MET = 4.0   # 通勤步行代谢当量(MET)


def travel_change(cur_planned):
    """cur_planned: {ind: (current, planned)} → 出行方式变化。
    返回 总小汽车变化%、总步行变化%、逐指标贡献。"""
    rows = []
    car_tot = walk_tot = 0.0
    for ind in IND_ORDER:
        if ind not in cur_planned:
            continue
        cur, plan = cur_planned[ind]
        if cur in (None, 0):
            pct = 0.0
        else:
            pct = (plan - cur) / cur * 100.0
        e = ELASTICITY[ind]
        car_c = pct * e["car"] if e["car"] is not None else None
        walk_c = pct * e["walk"] if e["walk"] is not None else None
        car_tot += car_c or 0.0
        walk_tot += walk_c or 0.0
        rows.append({"ind": ind, "zh": e["zh"], "cur": cur, "plan": plan,
                     "pct": pct, "car": car_c, "walk": walk_c})
    return {"car_pct": car_tot, "walk_pct": walk_tot, "rows": rows}


def exposure_diff(car_pct, walk_pct, pm25_total, car_frac_pct, walk_min_day):
    """出行变化% + 现状暴露 → 暴露差值。
    交通PM2.5 = 总PM2.5 × 小汽车贡献%;PM差值 = 小汽车变化% × 交通PM2.5。
    现状体力活动MET = 步行min/日 × 7 × MET;PA差值 = 步行变化% × 现状MET。"""
    traffic_pm = pm25_total * car_frac_pct / 100.0
    pm_diff = car_pct / 100.0 * traffic_pm                 # 一般为负(污染下降)
    pa_cur = walk_min_day * 7.0 * WALK_MET
    pa_diff = walk_pct / 100.0 * pa_cur                    # 一般为正(体力活动增加)
    return {"traffic_pm": traffic_pm, "pm_diff": pm_diff,
            "pa_cur": pa_cur, "pa_diff": pa_diff}


def _rr_diff(rr_unit_val, unit, diff):
    """RR_diff = exp( ln(RR)/unit × 暴露差值 )。"""
    return math.exp(math.log(rr_unit_val) / unit * diff)


def health_results(pm_diff, pa_diff, outcomes=None, current_rates=None):
    """对每个健康结果,综合 PM2.5 与体力活动两条路径,计算综合RR、PAF、变化%。
    current_rates: {outcome: 现状发病/死亡率} 可选,给出则算优化后水平。"""
    outcomes = outcomes or list(OUTCOMES.keys())
    current_rates = current_rates or {}
    out = []
    for oc in outcomes:
        spec = OUTCOMES.get(oc, {})
        rr_pm = _rr_diff(spec["pm25"], 10.0, pm_diff) if "pm25" in spec else 1.0
        if "pa" in spec:
            rr_val, unit = spec["pa"]
            rr_pa = _rr_diff(rr_val, unit, pa_diff)
        else:
            rr_pa = 1.0
        rr_c = rr_pm * rr_pa
        paf = (rr_c - 1.0) / rr_c if rr_c != 0 else 0.0      # <0 表示发病降低
        change_pct = (rr_c - 1.0) * 100.0                    # <0 表示下降
        row = {"outcome": oc, "rr_pm": rr_pm, "rr_pa": rr_pa, "rr_c": rr_c,
               "paf": paf, "change_pct": change_pct,
               "has_pm": "pm25" in spec, "has_pa": "pa" in spec}
        if oc in current_rates and current_rates[oc] is not None:
            row["rate_cur"] = current_rates[oc]
            row["rate_new"] = current_rates[oc] * rr_c
        out.append(row)
    return out


def full_assess(cur_planned, pm25_total, car_frac_pct, walk_min_day,
                outcomes=None, current_rates=None):
    """完整流程:5D → 出行 → 暴露 → 健康结果。返回各步骤结果。"""
    tc = travel_change(cur_planned)
    ed = exposure_diff(tc["car_pct"], tc["walk_pct"], pm25_total, car_frac_pct, walk_min_day)
    hr = health_results(ed["pm_diff"], ed["pa_diff"], outcomes, current_rates)
    return {"travel": tc, "exposure": ed, "health": hr}
