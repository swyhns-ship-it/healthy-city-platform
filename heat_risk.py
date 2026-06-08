# -*- coding: utf-8 -*-
"""
中暑重症风险(demo 运行时,纯 numpy)。

模型:对 287 例 60岁以上中暑病例做 logistic 回归(重症 vs 轻症),后向剔除保留显著变量
(p<=0.05):当天地表温度 MODIS_LST(+)、建成密度 dw_built(+)、到最近急救站 dis_ems(+)、
绿地占比 greenfrac(+,郊区脆弱性混杂)。在 ~500m 网格上算重症概率,得到风险地图。
属关联性模型(in-sample AUC≈0.64, 空间CV AUC≈0.59, McFadden R²≈0.05),非交叉验证预测。

what-if:高温日强度(MODIS_LST 情景滑块)、新增急救站(降低 dis_ems)等,任意显著变量可调。
"""
import os, json
import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
_S = None


def _state():
    global _S
    if _S is None:
        g = np.load(os.path.join(_DIR, "heat_risk_grid.npz"), allow_pickle=True)
        model = json.load(open(os.path.join(_DIR, "heat_risk_model.json"), encoding="utf-8"))
        cases = None
        cp = os.path.join(_DIR, "heat_cases.npz")
        if os.path.exists(cp):
            cases = np.load(cp, allow_pickle=True)
        _S = {"g": {k: g[k] for k in g.files}, "model": model, "cases": cases}
    return _S


def model_info():
    return _state()["model"]


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def risk_latlon(modis_lst=None, ems_extra=None, built_scale=1.0):
    """
    计算 ~500m 网格的重症风险概率。
    modis_lst: 当天地表温度情景(默认用病例均值 ref);ems_extra: [[lon,lat],...] 新增急救站;
    built_scale: 建成密度整体缩放(模拟开发/疏解,默认1)。
    返回 prob(NY,NX, 行0=南), bounds[[s,w],[n,e]], 以及网格 meta。
    """
    S = _state(); g = S["g"]; m = S["model"]
    if modis_lst is None:
        modis_lst = m["modis_lst_ref"]
    built = g["dw_built"].astype(float) * built_scale
    dems = g["dis_ems"].astype(float).copy()
    clon = g["clon"]; clat = g["clat"]
    if ems_extra:
        for lo, la in ems_extra:
            d = np.hypot((clon - lo) * 111000.0 * np.cos(np.radians(la)),
                         (clat - la) * 111000.0)
            dems = np.fmin(dems, d)
    # 各变量取值(MODIS_LST 为情景标量;其余为网格)
    src = {"MODIS_LST": modis_lst, "dw_built": built, "dis_ems": dems}
    if "greenfrac" in g:
        src["greenfrac"] = g["greenfrac"].astype(float)
    b = m["beta"]; mu = m["mean"]; sd = m["std"]
    z = m["const"]
    for v in m["vars"]:
        z = z + b[v] * (src[v] - mu[v]) / sd[v]
    prob = _sigmoid(z)
    prob = np.where(np.isfinite(g["dw_built"].astype(float)), prob, np.nan)
    res = float(g["res"]); lon0 = float(g["lon0"]); lat0 = float(g["lat0"])
    ny, nx = prob.shape
    bounds = [[lat0, lon0], [lat0 + ny*res, lon0 + nx*res]]
    return prob, bounds, {"res": res, "lon0": lon0, "lat0": lat0, "nx": nx, "ny": ny}


def city_stats(prob):
    v = prob[np.isfinite(prob)]
    return {"mean": round(float(v.mean()), 3), "p90": round(float(np.percentile(v, 90)), 3),
            "high_frac": round(float((v >= 0.7).mean()) * 100, 1), "n": int(v.size)}


_FAC = None


def severity_delta(rows, cols, dlst, modis_lst=None):
    """
    链路:ΔLST(局部建成/绿地改造,100m 网格)-> Δ重症风险。
    用重症模型的 LST 每度系数,把逐格 ΔLST 转成逐格重症概率变化(基线含该格急救距离)。
    返回 dict:逐格 drisk/risk0 + 汇总(平均/最强降幅、风险下降的格数)。
    """
    global _FAC
    if _FAC is None:
        _FAC = np.load(os.path.join(_DIR, "heat_facility_grids.npz"), allow_pickle=True)
    m = _state()["model"]
    if modis_lst is None:
        modis_lst = m["modis_lst_ref"]
    rows = np.asarray(rows); cols = np.asarray(cols); dlst = np.asarray(dlst, float)
    dems = _FAC["dis_ems"][rows, cols].astype(float)
    b = m["beta"]; mu = m["mean"]; sd = m["std"]
    z = m["const"] + b["MODIS_LST"] * (modis_lst - mu["MODIS_LST"]) / sd["MODIS_LST"]
    if "dis_ems" in b:
        z = z + b["dis_ems"] * (dems - mu["dis_ems"]) / sd["dis_ems"]
    lst_beta = m["lst_per_degree_beta"]
    risk0 = 1.0 / (1.0 + np.exp(-z))
    risk1 = 1.0 / (1.0 + np.exp(-(z + lst_beta * dlst)))
    drisk = risk1 - risk0
    down = drisk < -1e-4
    return {"drisk": drisk, "risk0": risk0,
            "mean_drisk": round(float(drisk.mean()), 4),
            "min_drisk": round(float(drisk.min()), 4),
            "n_down": int(down.sum()),
            "area_down_ha": round(float(down.sum()) * 1.0, 1)}


def cases_points():
    c = _state()["cases"]
    if c is None:
        return None
    return {"lon": c["lon"], "lat": c["lat"], "severe": c["severe"]}


if __name__ == "__main__":
    m = model_info()
    print("模型变量:", m["vars"], " McFadden R2=", m["mcfadden_r2"])
    for ml, name in [(m["modis_lst_p10"], "凉日P10"), (m["modis_lst_ref"], "均值"),
                     (m["modis_lst_p90"], "高温日P90")]:
        p, b, meta = risk_latlon(modis_lst=ml)
        s = city_stats(p)
        print("MODIS_LST=%.1f(%s): 平均重症风险 %.3f, P90 %.3f, 高风险(>=0.7)占 %.1f%%" %
              (ml, name, s["mean"], s["p90"], s["high_frac"]))
    # 新增急救站 what-if(在某高风险点加站)
    p0, _, _ = risk_latlon(m["modis_lst_p90"])
    p1, _, _ = risk_latlon(m["modis_lst_p90"], ems_extra=[[121.1, 31.0]])
    d = np.nanmean(p0) - np.nanmean(p1)
    print("加1个急救站(121.1,31.0): 全市平均风险变化 %.4f" % d)
