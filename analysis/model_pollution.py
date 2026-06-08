# -*- coding: utf-8 -*-
"""
(venv)空气污染 LUR 风格模型:PM2.5/NO2(年/冬)~ 绿地 + 建成/灯光/人口/地形。
加邻域绿地(3km/7km)+ 到最近绿地距离,空间分块 CV,特征重要性,绿地剂量-反应。
目的:先实测绿地对 1km 污染的可塑性(信号强弱),再决定 app 接入方式。
"""
import numpy as np, json, os
from scipy.ndimage import uniform_filter, distance_transform_edt
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_absolute_error
import joblib

G = np.load(r"E:\projects\hia_demo\pollution_grids.npz", allow_pickle=True)
NY, NX = G["pm25_y"].shape
OWN = ["dw_built", "bldg_height", "FAR_proxy", "ntl", "pop", "elevation"]
SCALES = [3, 7]; GTHRESH = 0.3
GREENF = ["greenfrac", "g3", "g7", "dist_green"]
FEATURES = OWN + GREENF
TARGETS = ["pm25_y", "pm25_w", "no2_y", "no2_w"]
TZH = {"pm25_y": "PM2.5 年均", "pm25_w": "PM2.5 冬季", "no2_y": "NO2 年均", "no2_w": "NO2 冬季"}


def neigh_mean(a, size):
    v = np.isfinite(a).astype(np.float32); a0 = np.where(np.isfinite(a), a, 0).astype(np.float32)
    s = uniform_filter(a0, size, mode="constant")*size*size
    c = uniform_filter(v, size, mode="constant")*size*size
    return np.where(c > 0, s/np.maximum(c, 1e-6), np.nan)


def green_feats(gf):
    green = np.isfinite(gf) & (gf >= GTHRESH)
    dist = distance_transform_edt(~green)*1.0 if green.any() else np.full(gf.shape, 99.0)
    return {"greenfrac": gf, "g3": neigh_mean(gf, SCALES[0]),
            "g7": neigh_mean(gf, SCALES[1]), "dist_green": dist.astype(np.float32)}


gf = G["greenfrac"]; gfe = green_feats(gf)
cols = [G[k].ravel() for k in OWN] + [gfe[k].ravel() for k in GREENF]
X_all = np.column_stack(cols)
lon = G["lon"].ravel(); lat = G["lat"].ravel()

import pandas as pd
results = {}
for tgt in TARGETS:
    y = G[tgt].ravel()
    m = np.isfinite(X_all).all(axis=1) & np.isfinite(y)
    Xtr, ytr = X_all[m], y[m]; lo, la = lon[m], lat[m]
    # 空间分块 CV(5x5 块, 5 折)
    bx = pd.qcut(lo, 5, labels=False, duplicates="drop")
    by = pd.qcut(la, 5, labels=False, duplicates="drop")
    blk = bx.astype(int)*10 + by.astype(int)
    order = sorted(np.unique(blk)); folds = [order[i::5] for i in range(5)]
    r2s, maes = [], []
    for tb in folds:
        te = np.isin(blk, tb)
        if te.sum() == 0 or (~te).sum() == 0: continue
        rf = RandomForestRegressor(n_estimators=200, max_depth=16, min_samples_leaf=5,
                                   n_jobs=-1, random_state=0)
        rf.fit(Xtr[~te], ytr[~te]); p = rf.predict(Xtr[te])
        r2s.append(r2_score(ytr[te], p)); maes.append(mean_absolute_error(ytr[te], p))
    rf = RandomForestRegressor(n_estimators=300, max_depth=18, min_samples_leaf=4,
                               n_jobs=-1, random_state=0).fit(Xtr, ytr)
    imp = dict(zip(FEATURES, rf.feature_importances_.round(3)))
    green_imp = sum(imp[k] for k in GREENF)
    # 绿地剂量-反应:典型建成背景,greenfrac 0->1
    built = np.isfinite(G["dw_built"].ravel()) & (G["dw_built"].ravel() > 0.4)
    bg = [np.nanmedian(G[k].ravel()[built]) for k in OWN]
    levels = np.round(np.arange(0, 1.01, 0.2), 2); dr = []
    for g in levels:
        dist = 0.0 if g >= GTHRESH else 5.0
        dr.append(float(rf.predict([bg + [g, g, g, dist]])[0]))
    dr_delta = round(dr[-1]-dr[0], 2)
    joblib.dump(rf, r"E:\projects\hia_demo\pollution_%s.joblib" % tgt)
    results[tgt] = dict(cv_r2=round(float(np.mean(r2s)), 3), cv_mae=round(float(np.mean(maes)), 2),
                        n=int(m.sum()), green_imp=round(green_imp, 3),
                        dose_full=dr_delta, imp=imp)
    print("\n=== %s (n=%d) ===" % (TZH[tgt], m.sum()))
    print("  空间CV R2=%.3f MAE=%.2f µg/m³" % (np.mean(r2s), np.mean(maes)))
    print("  绿地类特征重要性合计=%.3f" % green_imp)
    print("  剂量-反应(greenfrac 0->1, 建成背景): Δ=%.2f µg/m³" % dr_delta)
    top = sorted(imp.items(), key=lambda x: -x[1])[:5]
    print("  Top5 重要性:", ", ".join("%s=%.2f" % (k, v) for k, v in top))

json.dump(results, open(r"E:\projects\hia_demo\analysis\out\pollution_model_meta.json", "w"),
          ensure_ascii=False, indent=2)
print("\n已保存 4 个模型 + meta")
