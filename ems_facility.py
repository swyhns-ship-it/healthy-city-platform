# -*- coding: utf-8 -*-
"""EMS 急救设施新增选址优化引擎 —— MCLP(最大覆盖)+ 街道公平性,与纳凉设施同一套算法。

与纳凉的唯一区别:"是否已达标"由 **ART 急救反应时间预测** 定义(而非到现状设施的距离)——
当前 ART 较差(楼面加权均值 ≥ 阈值)的需求格视为欠服务,新增急救站在 cover_dist 内可改善。

运行时从 ems_facility.npz 读紧凑数据(需求格 坐标/人口/老年/ART/街道 + 202 现状站 + 街道质心),
scipy(cKDTree)建覆盖关系、pulp/CBC 求解整数规划。不依赖 geopandas。
离线数据由 analysis/build_ems_facility_data.py 生成。被 views/cooling.py(EMS 选项卡)调用。
"""
import os

import numpy as np
from scipy.spatial import cKDTree

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE = None

WEIGHT_SCHEMES = {"pop": "总人口", "elderly": "老年人口(70+)", "equal": "均等"}
DEDUP_DIST = 200.0
# 达标 ART 阈值(楼面加权均值;ART 序数 4min=0/8min=1/12min=2/延误=3)
ART_THR = {"≤4分钟": 0.5, "≤8分钟": 1.5, "≤12分钟": 2.5}


def _state():
    global _STATE
    if _STATE is None:
        d = np.load(os.path.join(_DIR, "ems_facility.npz"), allow_pickle=True)
        _STATE = {
            "dem_xy": d["dem_xy"].astype(float), "dem_ll": d["dem_ll"].astype(float),
            "pop": d["pop"].astype(float), "elderly": d["elderly"].astype(float),
            "art": d["art"].astype(float), "dem_jd": d["dem_jd"].astype(int),
            "ems_xy": d["ems_xy"].astype(float), "ems_ll": d["ems_ll"].astype(float),
            "jd_xy": d["jd_xy"].astype(float), "jd_ll": d["jd_ll"].astype(float),
            "jd_names": [str(x) for x in d["jd_names"]],
        }
    return _STATE


def data_summary():
    s = _state()
    return {"n_dem": len(s["dem_xy"]), "n_ems": len(s["ems_xy"]),
            "n_jiedao": len(s["jd_names"]), "pop_total": float(s["pop"].sum()),
            "elderly_total": float(s["elderly"].sum())}


def weights_for(scheme):
    """需求格权重(归一化到和为 1)。"""
    s = _state()
    if scheme == "equal":
        w = np.ones(len(s["dem_xy"]), float)
    elif scheme == "elderly":
        w = np.clip(s["elderly"], 0, None) + 1e-6
    else:  # pop(默认)
        w = np.clip(s["pop"], 0, None) + 1e-6
    return w / w.sum()


def baseline_mask(art_thr):
    """现状已达标(不算欠服务):ART 楼面加权均值 < 阈值。"""
    s = _state()
    return s["art"] < art_thr


def _gini(arr):
    arr = np.sort(np.asarray(arr, float))
    n = len(arr)
    if n == 0 or arr.mean() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * np.sum(idx * arr) / (n * arr.sum())) - (n + 1) / n)


def _street_coverage(cover_mask, weights):
    s = _state()
    res_jd = s["dem_jd"]
    out = {}
    for d, name in enumerate(s["jd_names"]):
        idx = np.where(res_jd == d)[0]
        tw = float(weights[idx].sum())
        out[name] = float(weights[idx][cover_mask[idx]].sum()) / tw if tw > 0 else np.nan
    return out


def candidates(art_thr):
    """候选选址点:欠服务格质心 + 街道质心,DEDUP_DIST 去重。
    返回 (xy[米], ll[经纬度], jd_idx[所属街道])。"""
    s = _state()
    covered = baseline_mask(art_thr)
    unc = ~covered
    a_xy, a_ll, a_jd = s["dem_xy"][unc], s["dem_ll"][unc], s["dem_jd"][unc]
    b_xy, b_ll, b_jd = s["jd_xy"], s["jd_ll"], np.arange(len(s["jd_xy"]))
    xy = np.vstack([a_xy, b_xy]); ll = np.vstack([a_ll, b_ll])
    jdi = np.concatenate([a_jd, b_jd])
    pairs = cKDTree(xy).query_pairs(DEDUP_DIST)
    drop = {max(i, j) for i, j in pairs}
    keep = np.array([k for k in range(len(xy)) if k not in drop], int)
    return xy[keep], ll[keep], jdi[keep]


def base_stats(art_thr=1.5, scheme="pop"):
    """现状(不新增)指标:已达标加权比例 / 欠服务格数 / 街道公平性。"""
    w = weights_for(scheme)
    covered = baseline_mask(art_thr)
    sc = _street_coverage(covered, w)
    vals = np.array([v for v in sc.values() if not np.isnan(v)])
    return {
        "coverage": float(w[covered].sum()),
        "count_coverage": float(covered.mean()),
        "n_covered": int(covered.sum()), "n_dem": int(len(covered)),
        "n_underserved": int((~covered).sum()),
        "gini": _gini(vals), "street_coverage": sc,
    }


def solve(cover_dist=1500.0, art_thr=1.5, scheme="pop", K=10, alpha=0.0, time_limit=60):
    """求解 MCLP:在欠服务格中,用 K 个新增急救站(cover_dist 内)最大化加权改善。"""
    from pulp import (LpProblem, LpMaximize, LpVariable, lpSum,
                      LpBinary, LpStatus, PULP_CBC_CMD, value)
    s = _state()
    dem_xy, dem_jd = s["dem_xy"], s["dem_jd"]
    w = weights_for(scheme)
    covered = baseline_mask(art_thr)
    cand_xy, cand_ll, cand_jd = candidates(art_thr)
    n_cand = len(cand_xy)

    tree = cKDTree(cand_xy)
    unc_idx = np.where(~covered)[0]
    reach = tree.query_ball_point(dem_xy[unc_idx], cover_dist)
    dem_to_cand = {int(i): c for i, c in zip(unc_idx, reach) if c}

    prob = LpProblem("EMS_MCLP", LpMaximize)
    x = [LpVariable(f"x_{j}", cat=LpBinary) for j in range(n_cand)]
    y = {i: LpVariable(f"y_{i}", cat=LpBinary) for i in dem_to_cand}
    prob += lpSum(x) == int(K)
    for i, cj in dem_to_cand.items():
        prob += y[i] <= lpSum(x[j] for j in cj)

    base_cov = float(w[covered].sum())
    new_cov = lpSum(float(w[i]) * y[i] for i in y)

    if alpha <= 0:
        prob += new_cov
    else:
        mc = LpVariable("min_cov", lowBound=0, upBound=1)
        for d in range(len(s["jd_names"])):
            idx = np.where(dem_jd == d)[0]
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
        "status": status, "K": int(K), "cover_dist": cover_dist, "art_thr": art_thr,
        "scheme": scheme, "alpha": alpha,
        "sel_ll": cand_ll[sel], "sel_jd": [s["jd_names"][cand_jd[j]] for j in sel],
        "coverage_before": base_cov, "coverage_after": float(w[cover_after].sum()),
        "count_before": int(covered.sum()), "count_after": int(cover_after.sum()),
        "gini_before": _gini(vb), "gini_after": _gini(va),
        "n_newly": len(newly), "newly_idx": np.array(newly, int),
        "cover_after_mask": cover_after, "cover_before_mask": covered,
        "street_before": sc_before, "street_after": sc_after,
    }


def sweep(cover_dist=1500.0, art_thr=1.5, scheme="pop",
          k_list=(5, 10, 15, 20, 25, 30, 35, 40, 45), alpha=0.0):
    rows = []
    for K in k_list:
        r = solve(cover_dist, art_thr, scheme, K, alpha)
        rows.append({"K": int(K), "coverage": r["coverage_after"], "gini": r["gini_after"]})
    df = []
    prev = None
    base = base_stats(art_thr, scheme)["coverage"]
    for row in rows:
        marg = row["coverage"] - (prev if prev is not None else base)
        df.append({**row, "marginal": marg})
        prev = row["coverage"]
    return df


def elbow_k(sweep_rows):
    if not sweep_rows:
        return None
    margs = [r["marginal"] for r in sweep_rows]
    mmax = max(margs) if margs else 0
    for r in sweep_rows:
        if r["marginal"] < mmax * 0.5:
            return r["K"]
    return sweep_rows[-1]["K"]
