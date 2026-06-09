# -*- coding: utf-8 -*-
"""共享单车骑行量预测 + 反向优化 —— 离线数据/建模脚本(只在有原始数据的机器跑一次)。

输入:上海2018汇总/xandy上海2018.shp(298,249 个 100m 格网,UTM 51N,
      建成环境变量 + bk_str_wk/bk_str_we 工作日/周末骑行量)。
输出(进仓库,运行时用):
  - bike_grid.npz   逐格 经纬度 + 13 自变量 + 工作日/周末骑行量 + 可调变量上限
  - bike_model.joblib  HistGradientBoosting 回归(工作日 + 周末)+ 元数据

被 bike_ride.py(预测 + 反向优化引擎)调用。
"""
import os
import numpy as np
import geopandas as gpd
import joblib

RAW = os.environ.get("BIKE_RAW", r"E:\projects\_bike_raw\上海2018汇总")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHP = os.path.join(RAW, "xandy上海2018.shp")

FEATS = ["MajorRoad_", "MinorRoad", "POI_commer", "MajorRoad", "Minor_1", "Minor_2",
         "BuiDen", "BuiHight", "FAR", "SUM_per_gr", "per_water", "lst_day_c", "light_dnb"]
# 可规划调整的杠杆(其余 light_dnb/lst_day_c/per_water 视为城市化背景,固定不动)
ACTIONABLE = ["POI_commer", "FAR", "BuiDen", "BuiHight",
              "MinorRoad", "MajorRoad_", "Minor_1", "Minor_2", "MajorRoad", "SUM_per_gr"]
TARGETS = {"wk": "bk_str_wk", "we": "bk_str_we"}


def main():
    print("[1/4] 读取单车格网…")
    g = gpd.read_file(SHP)
    print(f"      {len(g)} 格,CRS {g.crs}")
    cen = g.geometry.centroid
    cen_wgs = gpd.GeoSeries(cen, crs=g.crs).to_crs(4326)
    lon = cen_wgs.x.values.astype("float32"); lat = cen_wgs.y.values.astype("float32")

    X = g[FEATS].fillna(0).values.astype("float32")
    bk_wk = g["bk_str_wk"].fillna(0).values.astype("float32")
    bk_we = g["bk_str_we"].fillna(0).values.astype("float32")

    # 建模子集:有建成环境痕迹的格(避开全空边缘)
    bd = g["BuiDen"].fillna(0).values; far = g["FAR"].fillna(0).values
    light = g["light_dnb"].fillna(0).values
    road = g[["MajorRoad_", "MinorRoad"]].fillna(0).sum(axis=1).values
    train_m = (bd > 0) | (far > 0) | (light > 0) | (road > 0)
    print(f"[2/4] 建模子集 {int(train_m.sum())}/{len(g)}")

    # 可调变量现实上限(全市 p90,作反向优化的天花板)
    ceilings = {}
    for f in ACTIONABLE:
        v = g[f].fillna(0).values
        ceilings[f] = float(np.percentile(v[v > 0], 90)) if (v > 0).any() else float(np.percentile(v, 90))

    print("[3/4] 训练 HistGradientBoosting…")
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.model_selection import cross_val_predict, KFold
    from sklearn.metrics import r2_score, mean_absolute_error
    cv = KFold(5, shuffle=True, random_state=42)
    models = {}
    Xtr = X[train_m]
    for tag, col in TARGETS.items():
        y = (bk_wk if tag == "wk" else bk_we)[train_m]
        m = HistGradientBoostingRegressor(max_iter=400, max_depth=None, learning_rate=0.08,
                                          min_samples_leaf=40, l2_regularization=1.0,
                                          random_state=42)
        pred = cross_val_predict(m, Xtr, y, cv=cv, n_jobs=-1)
        print(f"      {col}: CV R²={r2_score(y, pred):.3f} MAE={mean_absolute_error(y, pred):.2f}")
        m.fit(Xtr, y)
        models[tag] = m

    print("[4/4] 存盘…")
    np.savez_compressed(os.path.join(ROOT, "bike_grid.npz"),
                        lon=lon, lat=lat, X=X, bk_wk=bk_wk, bk_we=bk_we,
                        feats=np.array(FEATS, dtype=object))
    joblib.dump({"wk": models["wk"], "we": models["we"], "feats": FEATS,
                 "actionable": ACTIONABLE, "ceilings": ceilings,
                 "fixed": [f for f in FEATS if f not in ACTIONABLE]},
                os.path.join(ROOT, "bike_model.joblib"), compress=3)
    sz1 = os.path.getsize(os.path.join(ROOT, "bike_grid.npz")) / 1e6
    sz2 = os.path.getsize(os.path.join(ROOT, "bike_model.joblib")) / 1e6
    print(f"[done] bike_grid.npz {sz1:.1f}MB | bike_model.joblib {sz2:.1f}MB")


if __name__ == "__main__":
    main()
