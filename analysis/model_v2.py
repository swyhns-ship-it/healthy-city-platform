# -*- coding: utf-8 -*-
"""
(venv 运行)重建模:加入邻域绿地 + 到最近绿地距离,使"画绿地→周边降温"可被模型预测。

特征:
  own 静态:dw_built, bldg_height, FAR_proxy, ntl, elevation, slope
  绿地相关(干预会改变):greenfrac(本格), g300/g900(300m/900m 邻域绿地均值), dist_green_m(到最近绿地距离)
空间分块交叉验证给诚实精度。保存 model_v2.joblib + 基线预测 LST 网格。
"""
import os, json
import numpy as np
from scipy.ndimage import uniform_filter, distance_transform_edt
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_absolute_error
import joblib

G = np.load(r"E:\projects\hia_demo\feature_grids_dense.npz", allow_pickle=True)
NY, NX = G["greenfrac"].shape
OWN = ["dw_built", "bldg_height", "FAR_proxy", "ntl", "elevation", "slope"]
SCALES = [3, 9]                 # 300m, 900m 邻域
GREEN_THRESH = 0.5             # 判定"绿地"的 greenfrac 阈值
FEATURES = OWN + ["greenfrac", "g300", "g900", "dist_green_m"]


def neigh_mean(gf, size):
    """对含 NaN 的 greenfrac 网格求 size×size 邻域均值(仅在有效格上平均)。"""
    valid = np.isfinite(gf).astype(np.float32)
    gf0 = np.where(np.isfinite(gf), gf, 0).astype(np.float32)
    s = uniform_filter(gf0, size=size, mode="constant") * (size * size)
    c = uniform_filter(valid, size=size, mode="constant") * (size * size)
    out = np.full_like(gf0, np.nan)
    nz = c > 0
    out[nz] = s[nz] / c[nz]
    return out


def dist_to_green_m(gf):
    """到最近绿地(greenfrac>=阈值)的距离,单位米(100m/格)。"""
    green = np.isfinite(gf) & (gf >= GREEN_THRESH)
    if green.sum() == 0:
        return np.full(gf.shape, 9999, np.float32)
    return (distance_transform_edt(~green) * 100.0).astype(np.float32)


def build_feature_grids(gf):
    """从(可被干预修改的)greenfrac 网格派生全部绿地相关特征网格。"""
    return {
        "greenfrac": gf,
        "g300": neigh_mean(gf, SCALES[0]),
        "g900": neigh_mean(gf, SCALES[1]),
        "dist_green_m": dist_to_green_m(gf),
    }


def stack_features(green_grids):
    cols = []
    for k in OWN:
        cols.append(G[k].ravel())
    for k in ["greenfrac", "g300", "g900", "dist_green_m"]:
        cols.append(green_grids[k].ravel())
    return np.column_stack(cols)


if __name__ == "__main__":
    gf = G["greenfrac"].astype(np.float32)
    gg = build_feature_grids(gf)
    X_all = stack_features(gg)                  # (NY*NX, nfeat)
    lst_obs = G["lst_obs"].ravel()              # 真实观测(训练标签,不用插值值)
    wc = G["worldcover"].ravel()
    lon = G["lon"].ravel(); lat = G["lat"].ravel()

    with np.errstate(invalid="ignore"):
        valid_lst = (lst_obs >= 20) & (lst_obs <= 60)
    land = np.isfinite(X_all).all(axis=1) & (wc != 80) & (wc != 90) & valid_lst
    Xtr = X_all[land]; ytr = lst_obs[land]
    lo = lon[land]; la = lat[land]
    print("训练样本(真实LST):", len(ytr), " 特征:", FEATURES)

    # 空间分块 CV(6x6 块, 5 折)
    import pandas as pd
    bx = pd.qcut(lo, 6, labels=False, duplicates="drop")
    by = pd.qcut(la, 6, labels=False, duplicates="drop")
    block = bx.astype(int) * 100 + by.astype(int)
    order = sorted(np.unique(block))
    folds = [order[i::5] for i in range(5)]
    r2s, maes = [], []
    for k, tb in enumerate(folds):
        te = np.isin(block, tb)
        m = RandomForestRegressor(n_estimators=80, max_depth=18, min_samples_leaf=20,
                                  n_jobs=-1, random_state=0)
        m.fit(Xtr[~te], ytr[~te]); p = m.predict(Xtr[te])
        r2s.append(r2_score(ytr[te], p)); maes.append(mean_absolute_error(ytr[te], p))
        print("  fold %d R2=%.3f MAE=%.2f (n=%d)" % (k, r2s[-1], maes[-1], te.sum()))
    print("空间CV: R2=%.3f±%.3f MAE=%.2f°C" % (np.mean(r2s), np.std(r2s), np.mean(maes)))

    # 全样本训练 + 基线预测网格
    rf = RandomForestRegressor(n_estimators=120, max_depth=16, min_samples_leaf=50,
                               n_jobs=-1, random_state=0)
    rf.fit(Xtr, ytr)
    imp = sorted(zip(FEATURES, rf.feature_importances_), key=lambda x: -x[1])
    print("全样本 R2=%.3f  特征重要性:" % rf.score(Xtr, ytr))
    for n, v in imp: print("  %-14s %.3f" % (n, v))

    # 基线预测 LST(对所有 land 格,用现状特征)
    base_pred = np.full(NY * NX, np.nan, np.float32)
    predmask = np.isfinite(X_all).all(axis=1) & (wc != 80) & (wc != 90)
    base_pred[predmask] = rf.predict(X_all[predmask]).astype(np.float32)
    base_pred = base_pred.reshape(NY, NX)

    joblib.dump(rf, r"E:\projects\hia_demo\model_v2.joblib", compress=3)
    np.savez_compressed(r"E:\projects\hia_demo\baseline_v2.npz",
                        base_pred=base_pred,
                        cv_r2=np.mean(r2s), cv_mae=np.mean(maes))
    json.dump({"features": FEATURES, "own": OWN, "scales": SCALES,
               "green_thresh": GREEN_THRESH,
               "cv_r2": round(float(np.mean(r2s)), 3),
               "cv_mae": round(float(np.mean(maes)), 3)},
              open(r"E:\projects\hia_demo\analysis\out\model_v2_meta.json", "w"),
              ensure_ascii=False, indent=2)
    print("已保存 model_v2.joblib + baseline_v2.npz")
