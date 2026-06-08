# -*- coding: utf-8 -*-
"""(Anaconda)重症 logistic:去 greenfrac,加纳凉站点 dis_cool/den_cool,后向剔除选显著变量。"""
import numpy as np, pandas as pd
import statsmodels.api as sm
from pyproj import Transformer
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression

CASE = r"C:\Users\Administrator\Downloads\MODIS_LST_Heatstroke_Cases_v3 (1).xlsx"
COOL = r"H:\heat_facility\上海纳凉站点信息（党群服务站、居委等）.xlsx"
df = pd.read_excel(CASE); y = (df["中暑诊断"] == "重症中暑").astype(int).values
cool = pd.read_excel(COOL)
clon = cool["wgs84Lng"].values; clat = cool["wgs84Lat"].values
ok = np.isfinite(clon) & np.isfinite(clat); clon, clat = clon[ok], clat[ok]
print("纳凉站点 %d" % len(clon))

tr = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
cx, cy = tr.transform(clon, clat)               # 纳凉点 UTM
px, py = tr.transform(df["lon"].values, df["lat"].values)  # 病例 UTM
# 病例到最近纳凉点距离(m) + 1km内数量
dis_cool = np.empty(len(df)); den_cool = np.empty(len(df))
for i in range(len(df)):
    d = np.hypot(cx - px[i], cy - py[i])
    dis_cool[i] = d.min(); den_cool[i] = (d <= 1000).sum()

G = np.load(r"E:\projects\hia_demo\feature_grids_dense.npz", allow_pickle=True)
F = np.load(r"E:\projects\hia_demo\heat_facility_grids.npz", allow_pickle=True)
gt = G["gt"]; NY, NX = G["greenfrac"].shape
ux, uy = px, py
col = ((ux-gt[0])/gt[1]).astype(int); row = ((uy-gt[3])/gt[5]).astype(int)
inb = (col >= 0) & (col < NX) & (row >= 0) & (row < NY)
def at(a):
    v = np.full(len(df), np.nan); v[inb] = a[row[inb], col[inb]]; return v

feat = pd.DataFrame({
    "MODIS_LST": df["MODIS_LST"].values, "dw_built": at(G["dw_built"]),
    "FAR_proxy": at(G["FAR_proxy"]), "ntl": at(G["ntl"]), "elevation": at(G["elevation"]),
    "dis_ems": at(F["dis_ems"]), "den_bus": at(F["den_bus"]),
    "location": df["location"].values.astype(float),
    "dis_cool": dis_cool, "den_cool": den_cool,
})
m = feat.notna().all(axis=1).values
X = feat[m]; yy = y[m]; lon = df["lon"].values[m]; lat = df["lat"].values[m]
Z = (X - X.mean()) / X.std()

def fit(cols): return sm.Logit(yy, sm.add_constant(Z[cols])).fit(disp=0)
cols = list(Z.columns)
while True:
    r = fit(cols); pv = r.pvalues.drop("const"); worst = pv.idxmax()
    if pv[worst] <= 0.05 or len(cols) <= 1: break
    cols.remove(worst)
r = fit(cols)
print("\n=== 去greenfrac+纳凉 后,后向剔除最终模型 ===")
print("McFadden R2=%.3f  in-sample AUC=%.3f  (n=%d)" %
      (r.prsquared, roc_auc_score(yy, r.predict(sm.add_constant(Z[cols]))), len(yy)))
for c in cols:
    print("  %-12s β=%+.3f OR/SD=%.2f p=%.3f" % (c, r.params[c], np.exp(r.params[c]), r.pvalues[c]))

# 纳凉两指标单独的显著性(放进全模型看)
rf_all = fit(list(Z.columns))
print("\n纳凉指标在全模型中: dis_cool p=%.3f  den_cool p=%.3f" %
      (rf_all.pvalues["dis_cool"], rf_all.pvalues["den_cool"]))

def spcv(cols):
    a=[]
    for sd in range(6):
        bx=pd.qcut(lon,4,labels=False,duplicates="drop");by=pd.qcut(lat,4,labels=False,duplicates="drop")
        blk=bx.astype(int)*10+by.astype(int);order=sorted(np.unique(blk))
        rng=np.random.RandomState(sd);rng.shuffle(order);folds=[order[i::4] for i in range(4)]
        oof=np.full(len(yy),np.nan)
        for tb in folds:
            te=np.isin(blk,tb)
            if te.sum()==0 or len(np.unique(yy[~te]))<2: continue
            lr=LogisticRegression(max_iter=1000).fit(Z[cols].values[~te],yy[~te])
            oof[te]=lr.predict_proba(Z[cols].values[te])[:,1]
        o=~np.isnan(oof);a.append(roc_auc_score(yy[o],oof[o]))
    return np.mean(a),np.std(a)
auc,sd=spcv(cols)
print("最终模型 空间CV AUC=%.3f±%.3f" % (auc,sd))
