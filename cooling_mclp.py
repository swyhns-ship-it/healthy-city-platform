# -*- coding: utf-8 -*-
"""纳凉设施新增选址优化引擎 —— MCLP(最大覆盖选址)+ 街道公平性软约束。

运行时从 cooling_mclp.npz 读紧凑数据(坐标 + Pop/LST/Health + 街道归属),
用 scipy(cKDTree)构建覆盖关系、pulp/CBC 现场求解整数规划。不依赖 geopandas。

被 app.py 的「健康资源 · 纳凉设施布局优化」页调用。离线数据由
analysis/build_cooling_data.py 生成。

模型(与原 Colab notebook 一致,略作工程优化):
  目标 max (1-α)·Σ_i w_i·y_i  +  α·min_d { Σ_{i∈d} w_i y_i / W_d }
  约束 Σ_j x_j = K ;  y_i ≤ Σ_{j∈N_i} x_j(新增覆盖) ;  已被现状覆盖的 y_i = 1
其中 i=小区(需求点)、j=候选点、d=街道;w 为需求权重。
"""
import os

import numpy as np
from scipy.spatial import cKDTree

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE = None

WEIGHT_SCHEMES = {
    "health": "健康脆弱度(Health)",
    "pop": "人口(Pop)",
    "lst": "地表温度(LST)",
    "equal": "均等",
}
DEDUP_DIST = 200.0   # 候选点去重距离(米),与 notebook 一致


def _state():
    """懒加载 npz(进程内缓存)。"""
    global _STATE
    if _STATE is None:
        d = np.load(os.path.join(_DIR, "cooling_mclp.npz"), allow_pickle=True)
        _STATE = {
            "cool_xy": d["cool_xy"].astype(float), "cool_ll": d["cool_ll"].astype(float),
            "res_xy": d["res_xy"].astype(float), "res_ll": d["res_ll"].astype(float),
            "pop": d["pop"].astype(float), "lst": d["lst"].astype(float),
            "health": d["health"].astype(float), "res_jd": d["res_jd"].astype(int),
            "jd_xy": d["jd_xy"].astype(float), "jd_ll": d["jd_ll"].astype(float),
            "jd_names": [str(x) for x in d["jd_names"]],
        }
    return _STATE


def data_summary():
    s = _state()
    return {"n_cool": len(s["cool_xy"]), "n_res": len(s["res_xy"]),
            "n_jiedao": len(s["jd_names"])}


def weights_for(scheme):
    """需求点权重(归一化到和为 1)。"""
    s = _state()
    if scheme == "equal":
        w = np.ones(len(s["res_xy"]), float)
    elif scheme == "pop":
        w = np.clip(s["pop"], 0, None)
    elif scheme == "lst":
        raw = s["lst"].astype(float)
        raw = np.where(raw < -100, np.nan, raw)        # 清掉无效 LST
        med = np.nanmedian(raw)
        raw = np.where(np.isnan(raw), med, raw)
        w = (raw - raw.min()) / (raw.max() - raw.min() + 1e-9) + 0.1
    else:  # health(默认)
        h = s["health"].astype(float)
        w = np.clip(h, 0, None) + h.mean() * 0.05
    return w / w.sum()


def baseline_mask(cover_dist):
    """现状(不新增)下,每个小区是否已被某纳凉点覆盖。"""
    s = _state()
    d, _ = cKDTree(s["cool_xy"]).query(s["res_xy"])
    return d <= cover_dist


def _gini(arr):
    arr = np.sort(np.asarray(arr, float))
    n = len(arr)
    if n == 0 or arr.mean() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * np.sum(idx * arr) / (n * arr.sum())) - (n + 1) / n)


def _street_coverage(cover_mask, weights):
    """各街道加权覆盖率 {街道名: 覆盖率},以及对应数组(去掉空街道)。"""
    s = _state()
    res_jd = s["res_jd"]
    out = {}
    for d, name in enumerate(s["jd_names"]):
        idx = np.where(res_jd == d)[0]
        tw = float(weights[idx].sum())
        out[name] = float(weights[idx][cover_mask[idx]].sum()) / tw if tw > 0 else np.nan
    return out


def candidates(cover_dist):
    """候选选址点:未覆盖小区质心 + 街道质心,DEDUP_DIST 去重。
    返回 (xy[米], ll[经纬度], jd_idx[所属街道])。"""
    s = _state()
    covered = baseline_mask(cover_dist)
    unc = ~covered
    a_xy, a_ll, a_jd = s["res_xy"][unc], s["res_ll"][unc], s["res_jd"][unc]
    b_xy, b_ll, b_jd = s["jd_xy"], s["jd_ll"], np.arange(len(s["jd_xy"]))
    xy = np.vstack([a_xy, b_xy]); ll = np.vstack([a_ll, b_ll])
    jdi = np.concatenate([a_jd, b_jd])
    pairs = cKDTree(xy).query_pairs(DEDUP_DIST)
    drop = {max(i, j) for i, j in pairs}
    keep = np.array([k for k in range(len(xy)) if k not in drop], int)
    return xy[keep], ll[keep], jdi[keep]


def base_stats(cover_dist=500.0, scheme="health"):
    """不新增时的现状指标(快,无求解)。"""
    w = weights_for(scheme)
    covered = baseline_mask(cover_dist)
    sc = _street_coverage(covered, w)
    vals = np.array([v for v in sc.values() if not np.isnan(v)])
    return {
        "coverage": float(w[covered].sum()),
        "count_coverage": float(covered.mean()),
        "n_covered": int(covered.sum()), "n_res": int(len(covered)),
        "gini": _gini(vals), "street_coverage": sc,
    }


def solve(cover_dist=500.0, scheme="health", K=10, alpha=0.0, time_limit=60):
    """求解 MCLP,返回选址方案 + 前后指标。"""
    from pulp import (LpProblem, LpMaximize, LpVariable, lpSum,
                      LpBinary, LpStatus, PULP_CBC_CMD, value)
    s = _state()
    res_xy, res_jd = s["res_xy"], s["res_jd"]
    w = weights_for(scheme)
    covered = baseline_mask(cover_dist)
    cand_xy, cand_ll, cand_jd = candidates(cover_dist)
    n_cand = len(cand_xy)

    # 每个未覆盖小区:可达(<=cover_dist)的候选点
    tree = cKDTree(cand_xy)
    unc_idx = np.where(~covered)[0]
    reach = tree.query_ball_point(res_xy[unc_idx], cover_dist)
    dem_to_cand = {int(i): c for i, c in zip(unc_idx, reach) if c}

    prob = LpProblem("MCLP", LpMaximize)
    x = [LpVariable(f"x_{j}", cat=LpBinary) for j in range(n_cand)]
    y = {i: LpVariable(f"y_{i}", cat=LpBinary) for i in dem_to_cand}
    prob += lpSum(x) == int(K)
    for i, cj in dem_to_cand.items():
        prob += y[i] <= lpSum(x[j] for j in cj)

    base_cov = float(w[covered].sum())                       # 现状已覆盖(常数)
    new_cov = lpSum(float(w[i]) * y[i] for i in y)           # 新增覆盖

    if alpha <= 0:
        prob += new_cov
    else:
        mc = LpVariable("min_cov", lowBound=0, upBound=1)
        for d in range(len(s["jd_names"])):
            idx = np.where(res_jd == d)[0]
            tw = float(w[idx].sum())
            if tw <= 0:
                continue
            base_d = float(w[idx][covered[idx]].sum())
            terms = [float(w[i]) * y[i] for i in idx if i in y]
            prob += (base_d + lpSum(terms)) / tw >= mc
        prob += (1 - alpha) * new_cov + alpha * mc

    prob.solve(PULP_CBC_CMD(msg=0, timeLimit=time_limit))
    status = LpStatus[prob.status]

    sel = [j for j in range(n_cand) if (value(x[j]) or 0) > 0.5]
    cover_after = covered.copy()
    newly = []
    for i in y:
        if (value(y[i]) or 0) > 0.5:
            cover_after[i] = True
            newly.append(i)

    sc_before = _street_coverage(covered, w)
    sc_after = _street_coverage(cover_after, w)
    vb = np.array([v for v in sc_before.values() if not np.isnan(v)])
    va = np.array([v for v in sc_after.values() if not np.isnan(v)])

    return {
        "status": status, "K": int(K), "cover_dist": cover_dist, "scheme": scheme, "alpha": alpha,
        "sel_ll": cand_ll[sel], "sel_jd": [s["jd_names"][cand_jd[j]] for j in sel],
        "coverage_before": base_cov, "coverage_after": float(w[cover_after].sum()),
        "count_before": int(covered.sum()), "count_after": int(cover_after.sum()),
        "gini_before": _gini(vb), "gini_after": _gini(va),
        "n_newly": len(newly), "newly_idx": np.array(newly, int),
        "cover_after_mask": cover_after, "cover_before_mask": covered,
        "street_before": sc_before, "street_after": sc_after,
    }


def sweep(cover_dist=500.0, scheme="health", k_list=(5, 10, 15, 20, 25, 30, 35, 40, 45), alpha=0.0):
    """多 K 值批量求解,用于边际效益 / 拐点分析。返回每个 K 的覆盖率与 Gini。"""
    rows = []
    for K in k_list:
        r = solve(cover_dist, scheme, K, alpha)
        rows.append({"K": int(K), "coverage": r["coverage_after"], "gini": r["gini_after"]})
    df = []
    prev = None
    for row in rows:
        marg = row["coverage"] - (prev if prev is not None else base_stats(cover_dist, scheme)["coverage"])
        df.append({**row, "marginal": marg})
        prev = row["coverage"]
    return df


def elbow_k(sweep_rows):
    """边际增量首次跌破最大边际 50% 的 K(拐点)。"""
    if not sweep_rows:
        return None
    margs = [r["marginal"] for r in sweep_rows]
    mmax = max(margs)
    for r in sweep_rows:
        if r["marginal"] < mmax * 0.5:
            return r["K"]
    return sweep_rows[-1]["K"]
