# -*- coding: utf-8 -*-
"""(Anaconda)检验加入 dis_ems/den_bus 及其它丰富指标后,重症模型空间CV AUC 是否提升。
用病例文件已提取的列(无需 shp),先定 EMS/bus 是否值得做全市栅格。"""
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

df = pd.read_excel(r"C:\Users\Administrator\Downloads\MODIS_LST_Heatstroke_Cases_v3 (1).xlsx")
y = (df["中暑诊断"] == "重症中暑").astype(int).values
lon = df["lon"].values; lat = df["lat"].values

def spatial_cv_auc(X, y, lon, lat, nb=4, seeds=range(5)):
    aucs = []
    for sd in seeds:
        bx = pd.qcut(lon, nb, labels=False, duplicates="drop")
        by = pd.qcut(lat, nb, labels=False, duplicates="drop")
        blk = bx.astype(int)*10 + by.astype(int)
        order = sorted(np.unique(blk))
        rng = np.random.RandomState(sd); rng.shuffle(order)
        folds = [order[i::4] for i in range(4)]
        oof = np.full(len(y), np.nan)
        for tb in folds:
            te = np.isin(blk, tb)
            if te.sum() == 0 or len(np.unique(y[~te])) < 2: continue
            m = RandomForestClassifier(n_estimators=400, max_depth=6, min_samples_leaf=10,
                                       n_jobs=-1, random_state=0).fit(X[~te], y[~te])
            oof[te] = m.predict_proba(X[te])[:, 1]
        ok = ~np.isnan(oof)
        aucs.append(roc_auc_score(y[ok], oof[ok]))
    return np.mean(aucs), np.std(aucs)

SETS = {
 "A 可上图栅格(基线)": ["MODIS_LST", "NDVI", "FAR", "BC"],  # 近似我有全市栅格的
 "D A+EMS距离+公交密度": ["MODIS_LST", "NDVI", "FAR", "BC", "dis_ems", "den_bus"],
 "E +到公园/降温/地铁/路网": ["MODIS_LST", "NDVI", "FAR", "BC", "dis_ems", "den_bus",
                       "dis_park", "dis_cool", "n_cool", "dis_metro", "den_inter", "GVI"],
 "F 全部(含气象+年龄)": ["MODIS_LST", "T_max", "T_mean", "RH_mean", "Td_mean", "年龄",
                  "NDVI", "FAR", "BC", "dis_ems", "den_bus", "dis_park", "dis_cool",
                  "n_cool", "area_green", "dis_metro", "den_inter", "GVI", "location"],
}
print("重症占比 %.1f%% (n=%d), 空间块CV(4x4块,5随机种子)\n" % (100*y.mean(), len(y)))
for name, feats in SETS.items():
    sub = df[feats].apply(pd.to_numeric, errors="coerce")
    mask = sub.notna().all(axis=1).values
    auc, sd = spatial_cv_auc(sub[mask].values, y[mask], lon[mask], lat[mask])
    print("%-24s AUC=%.3f ± %.3f (n=%d, %d特征)" % (name, auc, sd, mask.sum(), len(feats)))

# 全特征重要性
sub = df[SETS["F 全部(含气象+年龄)"]].apply(pd.to_numeric, errors="coerce")
mask = sub.notna().all(axis=1).values
rf = RandomForestClassifier(n_estimators=600, max_depth=6, min_samples_leaf=10,
                            n_jobs=-1, random_state=0).fit(sub[mask].values, y[mask])
print("\n全特征重要性(前10):")
for f, i in sorted(zip(SETS["F 全部(含气象+年龄)"], rf.feature_importances_), key=lambda t:-t[1])[:10]:
    print("  %-12s %.3f" % (f, i))
