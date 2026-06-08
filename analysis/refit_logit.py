# -*- coding: utf-8 -*-
"""(Anaconda)用【可上图栅格】协变量重拟合 logistic 重症模型,给系数(OR)+ 空间CV AUC。
heat 用气象情景(MODIS当天LST)与空间气候态LST两种口径对比。"""
import numpy as np, pandas as pd
from pyproj import Transformer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

df = pd.read_excel(r"C:\Users\Administrator\Downloads\MODIS_LST_Heatstroke_Cases_v3 (1).xlsx")
y = (df["中暑诊断"] == "重症中暑").astype(int).values
lon = df["lon"].values; lat = df["lat"].values

G = np.load(r"E:\projects\hia_demo\feature_grids_dense.npz", allow_pickle=True)
F = np.load(r"E:\projects\hia_demo\heat_facility_grids.npz", allow_pickle=True)
gt = G["gt"]; NY, NX = G["greenfrac"].shape
tr = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
ux, uy = tr.transform(lon, lat)
col = ((ux-gt[0])/gt[1]).astype(int); row = ((uy-gt[3])/gt[5]).astype(int)
inb = (col >= 0) & (col < NX) & (row >= 0) & (row < NY)

def at_pts(arr):
    v = np.full(len(df), np.nan); v[inb] = arr[row[inb], col[inb]]; return v

feat = pd.DataFrame({
    "clim_LST": at_pts(G["lst_filled"]), "greenfrac": at_pts(G["greenfrac"]),
    "dw_built": at_pts(G["dw_built"]), "FAR_proxy": at_pts(G["FAR_proxy"]),
    "ntl": at_pts(G["ntl"]), "elevation": at_pts(G["elevation"]),
    "dis_ems": at_pts(F["dis_ems"]), "den_bus": at_pts(F["den_bus"]),
    "MODIS_LST": df["MODIS_LST"].values, "location": df["location"].values,
})

def spatial_auc(X, y, lon, lat, nb=4, seeds=range(6)):
    a = []
    for sd in seeds:
        bx = pd.qcut(lon, nb, labels=False, duplicates="drop")
        by = pd.qcut(lat, nb, labels=False, duplicates="drop")
        blk = bx.astype(int)*10+by.astype(int); order = sorted(np.unique(blk))
        rng = np.random.RandomState(sd); rng.shuffle(order)
        folds = [order[i::4] for i in range(4)]; oof = np.full(len(y), np.nan)
        for tb in folds:
            te = np.isin(blk, tb)
            if te.sum() == 0 or len(np.unique(y[~te])) < 2: continue
            sc = StandardScaler().fit(X[~te])
            m = LogisticRegression(max_iter=1000, C=1.0).fit(sc.transform(X[~te]), y[~te])
            oof[te] = m.predict_proba(sc.transform(X[te]))[:, 1]
        ok = ~np.isnan(oof); a.append(roc_auc_score(y[ok], oof[ok]))
    return np.mean(a), np.std(a)

SETS = {
 "空间气候态LST+建成+绿地+EMS+公交+城郊":
   ["clim_LST", "dw_built", "FAR_proxy", "greenfrac", "ntl", "elevation", "dis_ems", "den_bus", "location"],
 "改用当天MODIS_LST(情景热)替气候态":
   ["MODIS_LST", "dw_built", "FAR_proxy", "greenfrac", "ntl", "elevation", "dis_ems", "den_bus", "location"],
}
print("重症占比 %.1f%% n=%d\n" % (100*y.mean(), len(y)))
for name, fs in SETS.items():
    sub = feat[fs]; m = sub.notna().all(axis=1).values
    auc, sd = spatial_auc(sub[m].values, y[m], lon[m], lat[m])
    print("%-34s 空间CV AUC=%.3f±%.3f (n=%d)" % (name, auc, sd, m.sum()))

# 全样本系数(标准化 -> 比较效应方向/强度)
fs = SETS["改用当天MODIS_LST(情景热)替气候态"]
sub = feat[fs]; m = sub.notna().all(axis=1).values
sc = StandardScaler().fit(sub[m].values)
lr = LogisticRegression(max_iter=1000).fit(sc.transform(sub[m].values), y[m])
print("\n标准化 logistic 系数(>0 增重症概率):")
for f, c in sorted(zip(fs, lr.coef_[0]), key=lambda t: -abs(t[1])):
    print("  %-12s β=%+.3f  OR/1SD=%.2f" % (f, c, np.exp(c)))
