"""
HIA 计算引擎。
沿用 v0.9 工作流的代码 01 核心算法,简化为纯函数。
"""

from typing import Dict, Any
import numpy as np
from cases import ERF_PRIMARY_CVD, ERF_PRIMARY_ALLCAUSE, ERF_SENSITIVITY_CVD


HEAT_FRACTION = 0.35
LST_TO_AIR = 0.7   # 地表温度 -> 近地气温 经验折减系数(与示范案例一致)


def compute_hia(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    对一个示范案例做完整的 HIA 计算。
    
    返回包含主分析 + 敏感性分析的结果字典。
    """
    pop = case["population"]
    years = case["evaluation_years"]
    delta_t = case["delta_air_temp_C"]
    baseline_allcause_per_1000 = case["baseline_mortality_per_1000"]
    baseline_cvd_per_1000 = case["baseline_cvd_mortality_per_1000"]
    
    # 方向判断
    if delta_t < 0:
        direction = "cooling"
        case_sign = 1.0
        metric_name = "可避免病例数"
    elif delta_t > 0:
        direction = "warming"
        case_sign = -1.0  # 反转符号显示为正的"额外"
        metric_name = "额外病例数"
    else:
        direction = "neutral"
        case_sign = 1.0
        metric_name = "净病例数"
    
    # 基线
    baseline_allcause_per_100k = baseline_allcause_per_1000 * 100
    baseline_cvd_per_100k = baseline_cvd_per_1000 * 100
    
    def calc(rr, rr_low, rr_high, baseline_rate):
        rr_new = rr ** delta_t
        rr_new_a = rr_low ** delta_t
        rr_new_b = rr_high ** delta_t
        
        baseline_cases = pop * (baseline_rate / 100000)
        heat_baseline = baseline_cases * HEAT_FRACTION
        
        avoided_raw = heat_baseline * (1 - rr_new)
        ci_a_raw = heat_baseline * (1 - rr_new_a)
        ci_b_raw = heat_baseline * (1 - rr_new_b)
        
        avoided = avoided_raw * case_sign
        ci_a = ci_a_raw * case_sign
        ci_b = ci_b_raw * case_sign
        ci_low = min(ci_a, ci_b)
        ci_high = max(ci_a, ci_b)
        
        return {
            "per_year_point": round(avoided, 3),
            "per_year_low": round(ci_low, 3),
            "per_year_high": round(ci_high, 3),
            "total_point": round(avoided * years, 2),
            "total_low": round(ci_low * years, 2),
            "total_high": round(ci_high * years, 2),
        }
    
    cvd_primary = calc(
        ERF_PRIMARY_CVD["rr_point"],
        ERF_PRIMARY_CVD["rr_low"],
        ERF_PRIMARY_CVD["rr_high"],
        baseline_cvd_per_100k,
    )
    ac_primary = calc(
        ERF_PRIMARY_ALLCAUSE["rr_point"],
        ERF_PRIMARY_ALLCAUSE["rr_low"],
        ERF_PRIMARY_ALLCAUSE["rr_high"],
        baseline_allcause_per_100k,
    )
    cvd_sensitivity = calc(
        ERF_SENSITIVITY_CVD["rr_point"],
        ERF_SENSITIVITY_CVD["rr_low"],
        ERF_SENSITIVITY_CVD["rr_high"],
        baseline_cvd_per_100k,
    )
    
    # 比值
    if cvd_primary["total_point"] != 0:
        sens_ratio = cvd_sensitivity["total_point"] / cvd_primary["total_point"]
    else:
        sens_ratio = None
    
    return {
        "direction": direction,
        "metric_name": metric_name,
        "case_sign": case_sign,
        "cvd_primary": cvd_primary,
        "cvd_sensitivity": cvd_sensitivity,
        "ac_primary": ac_primary,
        "sensitivity_ratio": sens_ratio,
        # 用于报告
        "erf_primary_cvd": ERF_PRIMARY_CVD,
        "erf_primary_allcause": ERF_PRIMARY_ALLCAUSE,
        "erf_sensitivity_cvd": ERF_SENSITIVITY_CVD,
        "heat_fraction": HEAT_FRACTION,
        "baseline_allcause_per_1000": baseline_allcause_per_1000,
        "baseline_cvd_per_1000": baseline_cvd_per_1000,
    }


def compute_hia_gridded(case: Dict[str, Any], field: Dict[str, Any]) -> Dict[str, Any]:
    """
    逐格 HIA:对 green_lst.compute_field 产出的 ΔLST 场,用每格 100m 人口和该格
    自己的 ΔLST(含外溢)逐格求和,而非单一 ΔT × 总人口。
    返回与 compute_hia 同结构的 dict,供 render_report / report_docx 直接复用。
    """
    years = case["evaluation_years"]
    baseline_allcause_per_100k = case["baseline_mortality_per_1000"] * 100
    baseline_cvd_per_100k = case["baseline_cvd_mortality_per_1000"] * 100

    dlst = np.asarray(field["dlst"], dtype=float)
    cell_pop = np.asarray(field["pop"], dtype=float)
    dT = dlst * LST_TO_AIR                      # 逐格近地气温变化

    cooling = field.get("mode", "add") == "add"
    if cooling:
        direction, case_sign, metric_name = "cooling", 1.0, "可避免病例数"
    else:
        direction, case_sign, metric_name = "warming", -1.0, "额外病例数"

    def calc(rr, rr_low, rr_high, baseline_rate):
        heat_baseline = cell_pop * (baseline_rate / 100000.0) * HEAT_FRACTION
        def total(rx):
            return float(np.sum(heat_baseline * (1.0 - rx ** dT)))
        a, lo, hi = total(rr) * case_sign, total(rr_low) * case_sign, total(rr_high) * case_sign
        ci_low, ci_high = min(lo, hi), max(lo, hi)
        return {
            "per_year_point": round(a, 3), "per_year_low": round(ci_low, 3),
            "per_year_high": round(ci_high, 3),
            "total_point": round(a * years, 2), "total_low": round(ci_low * years, 2),
            "total_high": round(ci_high * years, 2),
        }

    cvd_primary = calc(ERF_PRIMARY_CVD["rr_point"], ERF_PRIMARY_CVD["rr_low"],
                       ERF_PRIMARY_CVD["rr_high"], baseline_cvd_per_100k)
    ac_primary = calc(ERF_PRIMARY_ALLCAUSE["rr_point"], ERF_PRIMARY_ALLCAUSE["rr_low"],
                      ERF_PRIMARY_ALLCAUSE["rr_high"], baseline_allcause_per_100k)
    cvd_sensitivity = calc(ERF_SENSITIVITY_CVD["rr_point"], ERF_SENSITIVITY_CVD["rr_low"],
                           ERF_SENSITIVITY_CVD["rr_high"], baseline_cvd_per_100k)
    sens_ratio = (cvd_sensitivity["total_point"] / cvd_primary["total_point"]
                  if cvd_primary["total_point"] else None)

    pw_dT = float(np.sum(dT * cell_pop) / np.sum(cell_pop)) if cell_pop.sum() else 0.0
    return {
        "direction": direction, "metric_name": metric_name, "case_sign": case_sign,
        "cvd_primary": cvd_primary, "cvd_sensitivity": cvd_sensitivity,
        "ac_primary": ac_primary, "sensitivity_ratio": sens_ratio,
        "erf_primary_cvd": ERF_PRIMARY_CVD, "erf_primary_allcause": ERF_PRIMARY_ALLCAUSE,
        "erf_sensitivity_cvd": ERF_SENSITIVITY_CVD, "heat_fraction": HEAT_FRACTION,
        "baseline_allcause_per_1000": case["baseline_mortality_per_1000"],
        "baseline_cvd_per_1000": case["baseline_cvd_mortality_per_1000"],
        # 逐格特有的汇总(供报告/界面)
        "gridded": True,
        "pop_affected": round(float(cell_pop.sum()), 1),
        "delta_air_temp_pop_weighted": round(pw_dT, 3),
        "n_cells": int(len(dlst)), "n_inside": int(field.get("n_inside", 0)),
    }
