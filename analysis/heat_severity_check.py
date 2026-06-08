# -*- coding: utf-8 -*-
"""(Anaconda)检验纯ML重症模型可行性:重症 vs 轻症,空间分块CV AUC。
比较 仅可上图栅格协变量 / +当天气象情景 / +全部 三种特征集。"""
import numpy as np, pandas as pd
from pyproj import Transformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

XLSX = r"C:\Users\Administrator\Downloads\MODIS_LST_Heatstroke_Cases_v3 (1).xlsx"
FG = r"E:\projects\hia_demo\feature_grids_dense.npz"
df = pd.read_excel(XLSX)
y = (df["中暑诊断"] == "重症中暑").astype(int).values

# 映射到全市栅格,提取可上图协变量
G = np.load(FG, allow_pickle=True); gt = G["gt"]; NY, NX = G["greenfrac"].shape
tr = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
ux, uy = tr.transform(df["lon"].values, df["lat"].values)
col = ((ux-gt[0])/gt[1]).astype(int); row = ((uy-gt[3])/gt[5]).astype(int)
inb = (col >= 0) & (col < NX) & (row >= 0) & (row < NY)
RAS = ["lst_filled", "greenfrac", "dw_built", "FAR_proxy", "ntl", "elevation"]
ras = {}
for k in RAS:
    v = np.full(len(df), np.nan)
    v[inb] = G[k][row[inb], col[inb]]
    ras[k] = v
dfr = pd.DataFrame(ras)
dfr["T_max"] = df["T_max"].values; dfr["T_mean"] = df["T_mean"].values
dfr["RH_mean"] = df["RH_mean"].values; dfr["MODIS_LST"] = df["MODIS_LST"].values
dfr["age"] = df["年龄"].values
lon = df["lon"].values; lat = df["lat"].values

SETS = {
 "A 仅可上图栅格": RAS,
 "B 栅格+当天气象(情景)": RAS + ["T_max", "RH_mean"],
 "C +MODIS当天LST+年龄": RAS + ["T_max", "RH_mean", "MODIS_LST", "age"],
}

def spatial_cv_auc(X, y, lon, lat, nb=4):
    bx = pd.qcut(lon, nb, labels=False, duplicates="drop")
    by = pd.qcut(lat, nb, labels=False, duplicates="drop")
    blk = bx.astype(int)*10 + by.astype(int)
    order = sorted(np.unique(blk)); folds = [order[i::4] for i in range(4)]
    oof = np.full(len(y), np.nan)
    for tb in folds:
        te = np.isin(blk, tb)
        if te.sum() == 0 or len(np.unique(y[~te])) < 2: continue
        m = RandomForestClassifier(n_estimators=400, max_depth=8, min_samples_leaf=8,
                                   n_jobs=-1, random_state=0).fit(X[~te], y[~te])
        oof[te] = m.predict_proba(X[te])[:, 1]
    ok = ~np.isnan(oof)
    return roc_auc_score(y[ok], oof[ok]), ok.sum()

print("重症占比 %.1f%% (n=%d)\n" % (100*y.mean(), len(y)))
for name, feats in SETS.items():
    sub = dfr[feats].copy()
    mask = sub.notna().all(axis=1).values
    X = sub[mask].values; yy = y[mask]
    auc, n = spatial_cv_auc(X, yy, lon[mask], lat[mask])
    print("%-22s 空间CV AUC=%.3f (n=%d, %d特征)" % (name, auc, n, len(feats)))

# 全特征集 B 的重要性
sub = dfr[SETS["B 栅格+当天气象(情景)"]]; mask = sub.notna().all(axis=1).values
rf = RandomForestClassifier(n_estimators=500, max_depth=8, min_samples_leaf=8,
                            n_jobs=-1, random_state=0).fit(sub[mask].values, y[mask])
print("\n特征集B 重要性:")
for f, i in sorted(zip(SETS["B 栅格+当天气象(情景)"], rf.feature_importances_), key=lambda t:-t[1]):
    print("  %-12s %.3f" % (f, i))
