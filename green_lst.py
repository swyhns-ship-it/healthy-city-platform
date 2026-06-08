# -*- coding: utf-8 -*-
"""
绿地 -> 地表温度(ΔLST) 逐格预测 —— demo 运行时模块(v2,含空间外溢)。

模型(model_v2.joblib)以"邻域绿地均值 + 到最近绿地距离"为特征,因此画下一个
绿地多边形后,不仅多边形内、其周边一定范围内网格的 LST 变化也由模型预测出来。

依赖:numpy / scipy / scikit-learn / joblib(已装入 .venv)。
静态网格:feature_grids.npz;基线预测:baseline_v2.npz;模型:model_v2.joblib。
"""
import os
import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
OWN = ["dw_built", "bldg_height", "FAR_proxy", "ntl", "elevation", "slope"]
GREEN_FEATS = ["greenfrac", "g300", "g900", "dist_green_m"]
SCALES = [3, 9]
GREEN_THRESH = 0.5

_S = None  # 缓存


def _state():
    global _S
    if _S is None:
        import joblib
        G = np.load(os.path.join(_DIR, "feature_grids_dense.npz"), allow_pickle=True)
        B = np.load(os.path.join(_DIR, "baseline_v2.npz"), allow_pickle=True)
        rf = joblib.load(os.path.join(_DIR, "model_v2.joblib"))
        own = np.stack([G[k].astype(np.float32) for k in OWN], axis=0)  # (6,NY,NX)
        _S = dict(
            rf=rf, own=own,
            gf=G["greenfrac"].astype(np.float32),
            lon=G["lon"], lat=G["lat"], pop=G["pop"],
            wc=G["worldcover"], lst=G["lst_filled"],
            base=B["base_pred"], cv_r2=float(B["cv_r2"]), cv_mae=float(B["cv_mae"]),
        )
    return _S


# ---------- 邻域 / 距离特征(与训练一致) ----------
def _neigh_mean(gf, size):
    from scipy.ndimage import uniform_filter
    valid = np.isfinite(gf).astype(np.float32)
    gf0 = np.where(np.isfinite(gf), gf, 0).astype(np.float32)
    s = uniform_filter(gf0, size=size, mode="constant") * (size * size)
    c = uniform_filter(valid, size=size, mode="constant") * (size * size)
    out = np.full_like(gf0, np.nan); nz = c > 0; out[nz] = s[nz] / c[nz]
    return out


def _dist_green(gf):
    from scipy.ndimage import distance_transform_edt
    green = np.isfinite(gf) & (gf >= GREEN_THRESH)
    if green.sum() == 0:
        return np.full(gf.shape, 9999, np.float32)
    return (distance_transform_edt(~green) * 100.0).astype(np.float32)


def _green_stack(gf):
    return {"greenfrac": gf, "g300": _neigh_mean(gf, SCALES[0]),
            "g900": _neigh_mean(gf, SCALES[1]), "dist_green_m": _dist_green(gf)}


def _point_in_poly(lon, lat, poly):
    px = np.asarray([p[0] for p in poly], float); py = np.asarray([p[1] for p in poly], float)
    n = len(px); inside = np.zeros(len(lon), bool); j = n - 1
    for i in range(n):
        cond = (py[i] > lat) != (py[j] > lat)
        denom = np.where((py[j]-py[i]) == 0, 1e-12, py[j]-py[i])
        xint = (px[j]-px[i]) * (lat-py[i]) / denom + px[i]
        inside ^= cond & (lon < xint); j = i
    return inside


def compute_field(polygon, mode="add", target_greenfrac=None, buffer_cells=None):
    """
    画一个多边形(经纬度环)-> 逐格 ΔLST 场(含外溢)。
    返回 dict:rows/cols/lat/lon/dlst/pop(影响范围内逐格), inside(是否多边形内),
              以及汇总统计。ΔLST<0 为降温,>0 升温。
    """
    S = _state()
    lon = S["lon"]; lat = S["lat"]; NY, NX = lon.shape
    gf = S["gf"]; base = S["base"]; wc = S["wc"]; own = S["own"]; pop = S["pop"]
    if target_greenfrac is None:
        target_greenfrac = 0.9 if mode == "add" else 0.02

    # 1) 多边形内网格
    lons = [p[0] for p in polygon]; lats = [p[1] for p in polygon]
    bb = (lon >= min(lons)) & (lon <= max(lons)) & (lat >= min(lats)) & (lat <= max(lats))
    rb, cb = np.where(bb)
    pr = pc = np.array([], dtype=int)
    if len(rb) > 0:
        ins = _point_in_poly(lon[rb, cb], lat[rb, cb], polygon)
        pr, pc = rb[ins], cb[ins]
    if len(pr) == 0:
        # 多边形小于一个 100m 网格(未覆盖任何格中心):回退到离形心最近的有效格
        clon = sum(lons) / len(lons); clat = sum(lats) / len(lats)
        dist = (lon - clon) ** 2 + (lat - clat) ** 2
        dist = np.where(np.isfinite(base) & (wc != 80) & (wc != 90), dist, np.inf)
        ri, ci = np.unravel_index(np.argmin(dist), dist.shape)
        if not np.isfinite(dist[ri, ci]):
            return {"n_cells": 0, "note": "该地块周边缺少有效栅格数据,无法预测"}
        pr, pc = np.array([ri]), np.array([ci])

    # 2) 干预后 greenfrac 网格
    gf2 = gf.copy()
    gf2[pr, pc] = target_greenfrac

    # 影响半径随地块大小自适应(物理上小公园影响范围小、大公园才大):
    # 等效半径 sqrt(N/π) + 小余量,夹在 [2,9] 格(200–900m)。
    if buffer_cells is None:
        import math
        r_eq = math.sqrt(len(pr) / math.pi)
        buffer_cells = int(min(max(2, round(r_eq + 1.5)), 9))

    # 3) 影响范围 = 多边形膨胀 buffer_cells 格
    from scipy.ndimage import binary_dilation
    polymask = np.zeros((NY, NX), bool); polymask[pr, pc] = True
    region = binary_dilation(polymask, iterations=buffer_cells)
    predmask = region & np.isfinite(base) & (wc != 80) & (wc != 90)
    rr, cc = np.where(predmask)
    if len(rr) == 0:
        return {"n_cells": 0, "note": "该地块周边缺少有效栅格数据(数据覆盖空洞),无法预测"}

    # 4) 仅在影响范围重算绿地特征并预测(局部裁剪以省算力)
    r0, r1 = max(0, rr.min()-SCALES[1]), min(NY, rr.max()+SCALES[1]+1)
    c0, c1 = max(0, cc.min()-SCALES[1]), min(NX, cc.max()+SCALES[1]+1)
    sub = (slice(r0, r1), slice(c0, c1))
    gsub = _green_stack(gf2[sub])
    feat = []
    for i, _ in enumerate(OWN):
        feat.append(own[i][sub][rr-r0, cc-c0])
    for k in GREEN_FEATS:
        feat.append(gsub[k][rr-r0, cc-c0])
    X = np.column_stack(feat)
    ok = np.isfinite(X).all(axis=1)
    rr, cc = rr[ok], cc[ok]; X = X[ok]
    pred_new = S["rf"].predict(X).astype(np.float32)
    dlst = pred_new - base[rr, cc]

    # 5) 单调约束:新增绿地只降温,拆除只升温(抑制 RF 反向噪声)
    if mode == "add":
        dlst = np.minimum(dlst, 0.0)
    else:
        dlst = np.maximum(dlst, 0.0)

    # 6) 掩膜感知空间平滑(等效热扩散):消除 RF 阶梯差值造成的斑驳/留白,
    #    让降温场连续。仅在可预测格上平滑,不外扩到无数据区。
    from scipy.ndimage import gaussian_filter
    rr_l, cc_l = rr - r0, cc - c0
    H, W = (r1 - r0), (c1 - c0)
    D = np.zeros((H, W), np.float32); M = np.zeros((H, W), np.float32)
    D[rr_l, cc_l] = dlst; M[rr_l, cc_l] = 1.0
    sig = 1.1
    num = gaussian_filter(D, sigma=sig, mode="constant")
    den = gaussian_filter(M, sigma=sig, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        Ds = np.where(den > 1e-6, num / den, 0.0)
    dlst = Ds[rr_l, cc_l]
    # 多边形内保留原始(更强的)直接降温,避免被周边稀释
    inside = polymask[rr, cc]
    dlst = np.where(inside, np.where(mode == "add", np.minimum(dlst, D[rr_l, cc_l]),
                                     np.maximum(dlst, D[rr_l, cc_l])), dlst)
    if mode == "add":
        dlst = np.minimum(dlst, 0.0)
    else:
        dlst = np.maximum(dlst, 0.0)

    cell_pop = np.nan_to_num(pop[rr, cc])
    # 展示:保留所有有变化的格(多边形内 或 |ΔLST|>=0.03),呈现连续降温梯度
    keep = inside | (np.abs(dlst) >= 0.03)
    rr, cc, dlst, cell_pop, inside = rr[keep], cc[keep], dlst[keep], cell_pop[keep], inside[keep]

    # "受影响人口" 只计有实质降温(多边形内 或 |ΔLST|>=0.2°C)的格,避免微弱外溢虚高
    signif = inside | (np.abs(dlst) >= 0.2)
    pop_affected = float(cell_pop[signif].sum())
    pw = float(np.sum(dlst*cell_pop)/np.sum(cell_pop)) if cell_pop.sum() > 0 else float("nan")

    # 供"平滑栅格"可视化:影响范围内的 2D ΔLST 场 + 逐格经纬度(裁剪区坐标)
    Dviz = np.full((H, W), np.nan, np.float32)
    Dviz[rr - r0, cc - c0] = dlst
    field2d = {"d": Dviz, "lat": lat[r0:r1, c0:c1].astype(float),
               "lon": lon[r0:r1, c0:c1].astype(float)}
    return {
        "field2d": field2d,
        "rows": rr, "cols": cc,
        "lat": lat[rr, cc].astype(float), "lon": lon[rr, cc].astype(float),
        "dlst": dlst.astype(float), "pop": cell_pop.astype(float),
        "inside": inside,
        "n_cells": int(len(rr)),
        "n_inside": int(inside.sum()),
        "area_ha": round(float(inside.sum()) * 1.0, 1),       # 多边形内面积
        "affected_area_ha": round(float(len(rr)) * 1.0, 1),   # 含外溢
        "mode": mode, "target_greenfrac": round(float(target_greenfrac), 3),
        "greenfrac_cur_inside": round(float(np.nanmean(gf[pr, pc])), 3),
        "dlst_mean_inside": round(float(dlst[inside].mean()), 3) if inside.any() else 0.0,
        "dlst_min": round(float(dlst.min()), 3),
        "pop_affected": round(pop_affected, 1),
        "dlst_pop_weighted": round(pw, 3),
        "obs_lst_inside": round(float(np.nanmean(S["lst"][pr, pc])), 2),
        "cv_r2": round(S["cv_r2"], 3), "cv_mae": round(S["cv_mae"], 2),
    }


def polygon_means(polygon):
    """多边形内各 LST 自变量(可调的逐格输入)的当前均值 + 现状地表温度。"""
    S = _state(); lon = S["lon"]; lat = S["lat"]; own = S["own"]; gf = S["gf"]; base = S["base"]
    lons = [p[0] for p in polygon]; lats = [p[1] for p in polygon]
    bb = (lon >= min(lons)) & (lon <= max(lons)) & (lat >= min(lats)) & (lat <= max(lats))
    rb, cb = np.where(bb); pr = pc = np.array([], int)
    if len(rb):
        ins = _point_in_poly(lon[rb, cb], lat[rb, cb], polygon); pr, pc = rb[ins], cb[ins]
    if len(pr) == 0:
        clon = sum(lons)/len(lons); clat = sum(lats)/len(lats)
        d = np.where(np.isfinite(base), (lon-clon)**2+(lat-clat)**2, np.inf)
        ri, ci = np.unravel_index(np.argmin(d), d.shape); pr, pc = np.array([ri]), np.array([ci])
    res = {name: float(np.nanmean(own[i][pr, pc])) for i, name in enumerate(OWN)}
    res["greenfrac"] = float(np.nanmean(gf[pr, pc]))
    res["lst_now"] = float(np.nanmean(S["lst"][pr, pc]))
    res["n_cells"] = int(len(pr))
    return res


def compute_lst_delta(polygon, targets=None):
    """
    局部建成环境改造 -> ΔLST(含绿地空间外溢)。用于"建成环境→LST→重症风险"链路。
    targets: dict,可含 greenfrac/dw_built/bldg_height/FAR_proxy/ntl/elevation/slope 的
    目标绝对值(只对多边形内网格生效;未给的保持现状)。返回逐格 ΔLST(100m 网格)。
    """
    targets = targets or {}
    import math
    from scipy.ndimage import binary_dilation, gaussian_filter
    S = _state(); lon = S["lon"]; lat = S["lat"]; NY, NX = lon.shape
    gf = S["gf"]; base = S["base"]; wc = S["wc"]; own = S["own"]; rf = S["rf"]
    lons = [p[0] for p in polygon]; lats = [p[1] for p in polygon]
    bb = (lon >= min(lons)) & (lon <= max(lons)) & (lat >= min(lats)) & (lat <= max(lats))
    rb, cb = np.where(bb); pr = pc = np.array([], int)
    if len(rb):
        ins = _point_in_poly(lon[rb, cb], lat[rb, cb], polygon); pr, pc = rb[ins], cb[ins]
    if len(pr) == 0:
        clon = sum(lons)/len(lons); clat = sum(lats)/len(lats)
        d = np.where(np.isfinite(base), (lon-clon)**2+(lat-clat)**2, np.inf)
        ri, ci = np.unravel_index(np.argmin(d), d.shape)
        if not np.isfinite(d[ri, ci]):
            return {"n_cells": 0, "note": "无有效栅格数据"}
        pr, pc = np.array([ri]), np.array([ci])
    buf = int(min(max(2, round(math.sqrt(len(pr)/math.pi)+1.5)), 9))
    polymask = np.zeros((NY, NX), bool); polymask[pr, pc] = True
    region = binary_dilation(polymask, iterations=buf) & np.isfinite(base) & (wc != 80) & (wc != 90)
    rr, cc = np.where(region)
    if len(rr) == 0:
        return {"n_cells": 0, "note": "无有效栅格数据"}
    gf2 = gf.copy()
    if "greenfrac" in targets and targets["greenfrac"] is not None:
        gf2[pr, pc] = float(targets["greenfrac"])
    own_mod = [own[i].copy() for i in range(len(OWN))]
    for i, name in enumerate(OWN):
        if name in targets and targets[name] is not None:
            own_mod[i][pr, pc] = float(targets[name])
    r0, r1 = max(0, rr.min()-SCALES[1]), min(NY, rr.max()+SCALES[1]+1)
    c0, c1 = max(0, cc.min()-SCALES[1]), min(NX, cc.max()+SCALES[1]+1)
    sub = (slice(r0, r1), slice(c0, c1))
    # 基线与情景在同一裁剪区重算特征并预测,二者之差消除裁剪边缘伪差:
    # 未改动任何指标时 X_base==X_new → ΔLST 恒为 0。
    gsub_b = _green_stack(gf[sub]); gsub_n = _green_stack(gf2[sub])
    featb = [own[i][sub][rr-r0, cc-c0] for i in range(len(OWN))]
    featn = [own_mod[i][sub][rr-r0, cc-c0] for i in range(len(OWN))]
    for k in GREEN_FEATS:
        featb.append(gsub_b[k][rr-r0, cc-c0]); featn.append(gsub_n[k][rr-r0, cc-c0])
    Xb = np.column_stack(featb); Xn = np.column_stack(featn)
    ok = np.isfinite(Xb).all(axis=1) & np.isfinite(Xn).all(axis=1)
    rr, cc = rr[ok], cc[ok]; Xb = Xb[ok]; Xn = Xn[ok]
    dlst = (rf.predict(Xn) - rf.predict(Xb)).astype(np.float32)
    # 轻度平滑保持连续
    H, W = (r1-r0), (c1-c0); D = np.zeros((H, W), np.float32); Mk = np.zeros((H, W), np.float32)
    D[rr-r0, cc-c0] = dlst; Mk[rr-r0, cc-c0] = 1.0
    with np.errstate(invalid="ignore", divide="ignore"):
        den = gaussian_filter(Mk, 1.0)
        Ds = np.where(den > 1e-6, gaussian_filter(D, 1.0)/np.maximum(den, 1e-6), 0.0)
    dlst = Ds[rr-r0, cc-c0]
    inside = polymask[rr, cc]
    keep = inside | (np.abs(dlst) >= 0.05)
    rr, cc, dlst, inside = rr[keep], cc[keep], dlst[keep], inside[keep]
    return {"rows": rr, "cols": cc, "lat": lat[rr, cc].astype(float),
            "lon": lon[rr, cc].astype(float), "dlst": dlst.astype(float),
            "inside": inside, "n_cells": int(len(rr)), "n_inside": int(inside.sum()),
            "dlst_mean_inside": round(float(dlst[inside].mean()), 3) if inside.any() else 0.0,
            "dlst_min": round(float(dlst.min()), 3), "dlst_max": round(float(dlst.max()), 3)}


# 兼容旧接口:返回汇总
def predict_delta_lst(polygon, mode="add", target_greenfrac=None):
    f = compute_field(polygon, mode=mode, target_greenfrac=target_greenfrac)
    if f.get("n_cells", 0) == 0:
        return f
    return {k: v for k, v in f.items()
            if k not in ("rows", "cols", "lat", "lon", "dlst", "pop", "inside", "field2d")}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, _DIR)
    from cases import CASES
    mm = {"greenspace_add": "add", "greenspace_remove": "remove"}
    for cid, c in CASES.items():
        f = compute_field(c["polygon"], mode=mm[c["intervention_type"]])
        print("\n[%s] %s" % (cid, c["label_short"]))
        print("  内 %d 格 / 含外溢 %d 格;内 ΔLST 均值 %.2f, 全场最强 %.2f" %
              (f["n_inside"], f["n_cells"], f["dlst_mean_inside"], f["dlst_min"]))
        print("  受影响人口 %.0f, 人口加权 ΔLST %.2f°C (CV R2=%.2f MAE=%.2f)" %
              (f["pop_affected"], f["dlst_pop_weighted"], f["cv_r2"], f["cv_mae"]))
