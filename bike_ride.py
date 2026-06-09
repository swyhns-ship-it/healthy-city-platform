# -*- coding: utf-8 -*-
"""共享单车骑行量预测 + 反向优化引擎(纯函数,被 views/bike.py 调用)。

- 预测:HistGradientBoosting 由建成环境 13 变量预测工作日/周末骑行量(bike_model.joblib)。
- 反向优化:在地图圈定范围内,把"可调正向杠杆"(商业POI/FAR/建筑密度/建筑高度/路网密度)
  按"改造强度"升向现实上限(全市 p90),预测骑行量提升,并按单杠杆分解贡献。
  (绿地/水体与骑行量负相关或无关,默认不作上调杠杆;夜光/地表温度为城市化背景,固定。)

数据 bike_grid.npz(逐格 经纬度 + 13 变量 + 现状骑行量),离线由 analysis/build_bike_data.py 生成。
坐标 WGS84;圈选用 shapely;不依赖 geopandas。
"""
import os

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE = None

# 默认可上调的正向杠杆(对骑行量正向、且可规划)
POSITIVE_LEVERS = ["POI_commer", "FAR", "BuiDen", "BuiHight",
                   "MinorRoad", "MajorRoad_", "Minor_1", "Minor_2", "MajorRoad"]
LEVER_ZH = {
    "POI_commer": "商业POI", "FAR": "容积率", "BuiDen": "建筑密度", "BuiHight": "建筑高度",
    "MinorRoad": "次干路密度", "MajorRoad_": "主干路密度", "Minor_1": "支路密度1",
    "Minor_2": "支路密度2", "MajorRoad": "主干路密度2", "SUM_per_gr": "绿地率",
}
DAY_COL = {"wk": "工作日", "we": "周末"}


def _state():
    global _STATE
    if _STATE is None:
        import joblib
        d = np.load(os.path.join(_DIR, "bike_grid.npz"), allow_pickle=True)
        bundle = joblib.load(os.path.join(_DIR, "bike_model.joblib"))
        _STATE = {
            "lon": d["lon"].astype(float), "lat": d["lat"].astype(float),
            "X": d["X"].astype(float), "bk_wk": d["bk_wk"].astype(float),
            "bk_we": d["bk_we"].astype(float),
            "feats": [str(x) for x in d["feats"]],
            "model": {"wk": bundle["wk"], "we": bundle["we"]},
            "ceilings": bundle["ceilings"], "actionable": bundle["actionable"],
        }
        _STATE["fi"] = {f: i for i, f in enumerate(_STATE["feats"])}
    return _STATE


def levers_available():
    """可选杠杆(中文名 + key),只给正向、可规划的。"""
    return [(k, LEVER_ZH.get(k, k)) for k in POSITIVE_LEVERS]


def select_in_polygon(poly_lonlat):
    """poly_lonlat: [(lon,lat),...] 多边形顶点(WGS84)-> 范围内格的索引。"""
    import shapely
    from shapely.geometry import Polygon
    s = _state()
    poly = Polygon(poly_lonlat)
    if not poly.is_valid or poly.area == 0:
        return np.array([], int)
    inb = shapely.contains_xy(poly, s["lon"], s["lat"])
    return np.where(inb)[0]


def select_in_circle(center_lonlat, radius_m):
    """圆心 (lon,lat) + 半径(米)-> 范围内格的索引。"""
    s = _state()
    clon, clat = center_lonlat
    kx = np.cos(np.radians(clat))
    dx = (s["lon"] - clon) * 111320.0 * kx
    dy = (s["lat"] - clat) * 110540.0
    return np.where(dx * dx + dy * dy <= radius_m * radius_m)[0]


def optimize(idx, levers, day="wk", mode="strength", strength=1.0, top_n=None, budget_coef=0.3):
    """对选中格反向优化骑行量,支持多种模式:
      mode="strength" 全域按 strength 升向现实上限(p90)。strength=1=box约束理论最优。
      mode="topN"     只改造提升潜力最大的 top_n 格(各自升至上限),其余不动。
      mode="budget"   预算约束:按 提升/改造成本 贪心选格,直到用满 budget_coef×全改造成本。
    成本=各杠杆相对增幅之和(升到上限算 1)。返回前后总量、单杠杆分解、被改造格掩码、逐格量。"""
    s = _state()
    m = s["model"][day]; ceil = s["ceilings"]; fi = s["fi"]
    if len(idx) == 0:
        return None
    idx = np.asarray(idx)
    X0 = s["X"][idx].copy()
    base = np.clip(m.predict(X0), 0, None)

    # 各格"升到上限"的目标配置 Xfull(只升不降),以及成本
    Xfull = X0.copy()
    cost = np.zeros(len(idx))
    for lev in levers:
        j = fi[lev]; c = ceil.get(lev, X0[:, j].max())
        inc = np.clip(c - X0[:, j], 0, None)
        Xfull[:, j] = X0[:, j] + inc
        cost += inc / (c + 1e-9)                      # 每杠杆相对增幅 0..1
    full_pred = np.clip(m.predict(Xfull), 0, None)
    gain_full = full_pred - base                      # 各格满改造潜在提升

    sel_mask = np.zeros(len(idx), bool)
    if mode == "topN":
        n = int(min(top_n or len(idx), len(idx)))
        chosen = np.argsort(-gain_full)[:n]
        Xo = X0.copy(); Xo[chosen] = Xfull[chosen]; sel_mask[chosen] = True
    elif mode == "budget":
        ratio = gain_full / (cost + 1e-9)
        order = np.argsort(-ratio)
        B = float(budget_coef) * float(cost.sum())
        Xo = X0.copy(); spent = 0.0
        for k in order:
            if cost[k] <= 1e-9 or gain_full[k] <= 0:
                continue
            if spent + cost[k] > B and spent > 0:
                break
            Xo[k] = Xfull[k]; sel_mask[k] = True; spent += cost[k]
    else:  # strength
        Xo = X0 + float(strength) * (Xfull - X0)
        sel_mask[:] = (cost > 0)
    opt = np.clip(m.predict(Xo), 0, None)

    base_tot = float(base.sum()); opt_tot = float(opt.sum())
    full_tot = float(full_pred.sum())                 # 全部格升到上限的潜力(全面改造)
    # 单杠杆分解:把该杠杆设为优化后取值、其余保持现状
    contrib = {}
    for lev in levers:
        Xl = X0.copy(); j = fi[lev]; Xl[:, j] = Xo[:, j]
        contrib[lev] = float(np.clip(m.predict(Xl), 0, None).sum() - base_tot)
    # 杠杆前后均值:在"被改造格"上(更能反映实际改了多少);无改造格则退回全体
    ch = sel_mask if sel_mask.any() else np.ones(len(idx), bool)
    cur_avg = {lev: float(X0[ch, fi[lev]].mean()) for lev in levers}
    opt_avg = {lev: float(Xo[ch, fi[lev]].mean()) for lev in levers}
    return {
        "n_cells": int(len(idx)), "day": day, "mode": mode, "levers": list(levers),
        "n_changed": int(sel_mask.sum()),
        "base_total": base_tot, "opt_total": opt_tot, "full_total": full_tot,
        "uplift": opt_tot - base_tot,
        "uplift_pct": (opt_tot - base_tot) / base_tot * 100 if base_tot > 0 else 0.0,
        "full_uplift_pct": (full_tot - base_tot) / base_tot * 100 if base_tot > 0 else 0.0,
        "contrib": contrib, "cur_avg": cur_avg, "opt_avg": opt_avg,
        "ceilings": {lev: float(ceil.get(lev, 0)) for lev in levers},
        "cell_idx": idx, "cell_base": base, "cell_opt": opt, "sel_mask": sel_mask,
        "obs_total": float((s["bk_wk"] if day == "wk" else s["bk_we"])[idx].sum()),
    }


def cells_lonlat(idx):
    s = _state()
    return s["lon"][idx], s["lat"][idx]
