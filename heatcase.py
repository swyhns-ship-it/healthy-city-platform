# -*- coding: utf-8 -*-
"""中暑病例风险地图 — 运行时数据引擎(轻量:仅加载 + 筛选 + 街道聚合)。

数据 heatcase_points.npz 由 analysis/build_heatcase_data.py 离线生成
(2013–2025 上海高温中暑病例,5,349 例)。被 views/heatcase_map.py 调用。
不依赖 openpyxl/shapely(那些只在离线脚本用)。
"""
import os

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
_S = None

# 年龄分组:(下限, 上限含, 标签)
AGE_GROUPS = [(0, 17, "0–17"), (18, 44, "18–44"), (45, 59, "45–59"),
              (60, 74, "60–74"), (75, 200, "75+")]


def _state():
    global _S
    if _S is None:
        d = np.load(os.path.join(_DIR, "heatcase_points.npz"), allow_pickle=True)
        _S = {k: d[k] for k in d.files}
        for k in ("occ_labels", "subtype_labels", "jd_names"):
            _S[k] = [str(x) for x in d[k]]
    return _S


def meta():
    s = _state()
    yr = s["year"][s["year"] > 0]
    return {
        "n": int(len(s["lon"])),
        "year_min": int(yr.min()), "year_max": int(yr.max()),
        "n_onset": int(np.isfinite(s["olon"].astype(float)).sum()),
        "occ_labels": s["occ_labels"], "jd_names": s["jd_names"],
        "n_severe": int(s["severe"].sum()), "n_death": int(s["death"].sum()),
        "n_precise": int(s["precise"].sum()),
        "n_precise_onset": int((s["oprecise"] == 1).sum()),
    }


def filter_cases(years=None, severe=(0, 1), sexes=(0, 1),
                 age_groups=None, occs=None, death_only=False):
    """只按**非空间**条件(年份/严重度/性别/年龄/职业/死亡)筛选,返回全部匹配病例。

    地理编码精度过滤不在这里做 —— 病例的严重度/年龄/死亡等与定位精度无关,
    统计/街道聚合应基于全部匹配病例。空间显示(热力图/病例点)再用 map_points()
    按精度/坐标基准取子集。返回含 home/onset 两套坐标 + precise/oprecise 标记。"""
    s = _state()
    m = np.ones(len(s["lon"]), bool)
    if years:
        m &= (s["year"] >= years[0]) & (s["year"] <= years[1])
    if severe is not None:
        m &= np.isin(s["severe"], list(severe))
    if sexes is not None:
        m &= np.isin(s["sex"], list(sexes))
    if occs is not None:
        m &= np.isin(s["occ"], list(occs))
    if age_groups:
        am = np.zeros(len(m), bool)
        for lo, hi in age_groups:
            am |= (s["age"] >= lo) & (s["age"] <= hi)
        m &= am
    if death_only:
        m &= (s["death"] == 1)
    return {
        "lon": s["lon"][m].astype(float), "lat": s["lat"][m].astype(float),
        "olon": s["olon"][m].astype(float), "olat": s["olat"][m].astype(float),
        "precise": s["precise"][m], "oprecise": s["oprecise"][m],
        "severe": s["severe"][m], "death": s["death"][m], "jd": s["jd"][m],
        "age": s["age"][m], "occ": s["occ"][m], "subtype": s["subtype"][m],
        "sex": s["sex"][m], "year": s["year"][m], "n": int(m.sum()),
    }


def map_points(f, basis="home", precise_only=True):
    """从 filter_cases 结果里取**用于上图**的子集(按坐标基准 + 地理编码精度)。
    返回 (lon, lat, sel):sel 为相对 f 各数组的布尔掩码,供取色/tooltip 用同一子集。"""
    if basis == "onset":
        lon, lat = f["olon"], f["olat"]
        valid = np.isfinite(lon) & np.isfinite(lat)
        pm = f["oprecise"] == 1
    else:
        lon, lat = f["lon"], f["lat"]
        valid = np.ones(len(lon), bool)
        pm = f["precise"] == 1
    sel = valid & (pm if precise_only else np.ones(len(lon), bool))
    return lon[sel], lat[sel], sel


def jiedao_agg(jd_arr, severe_arr):
    """各街道:病例数、重症数。返回 (cnt[n_jd], sev[n_jd])。"""
    s = _state()
    n = len(s["jd_names"])
    cnt = np.zeros(n, int); sev = np.zeros(n, int)
    for j, sv in zip(jd_arr, severe_arr):
        if j >= 0:
            cnt[j] += 1; sev[j] += int(sv)
    return cnt, sev
