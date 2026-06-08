# -*- coding: utf-8 -*-
"""(Anaconda)重症风险 logistic:全模型 + 后向剔除选显著变量;标注可上图者。"""
import numpy as np, pandas as pd
import statsmodels.api as sm
from pyproj import Transformer
from sklearn.metrics import roc_auc_score

df = pd.read_excel(r"C:\Users\Administrator\Downloads\MODIS_LST_Heatstroke_Cases_v3 (1).xlsx")
y = (df["中暑诊断"] == "重症中暑").astype(int).values
lon = df["lon"].values; lat = df["lat"].values
G = np.load(r"E:\projects\hia_demo\feature_grids_dense.npz", allow_pickle=True)
F = np.load(r"E:\projects\hia_demo\heat_facility_grids.npz", allow_pickle=True)
gt = G["gt"]; NY, NX = G["greenfrac"].shape
tr = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
ux, uy = tr.transform(lon, lat); col = ((ux-gt[0])/gt[1]).astype(int); row = ((uy-gt[3])/gt[5]).astype(int)
inb = (col >= 0) & (col < NX) & (row >= 0) & (row < NY)
def at(arr):
    v = np.full(len(df), np.nan); v[inb] = arr[row[inb], col[inb]]; return v

# 候选变量(标注是否可上图 MAP)
feat = pd.DataFrame({
    "MODIS_LST": df["MODIS_LST"].values,        # 当天热(情景/时间维)
    "clim_LST": at(G["lst_filled"]),            # MAP 气候态地温
    "greenfrac": at(G["greenfrac"]),            # MAP
    "dw_built": at(G["dw_built"]),              # MAP
    "FAR_proxy": at(G["FAR_proxy"]),            # MAP
    "ntl": at(G["ntl"]),                        # MAP
    "elevation": at(G["elevation"]),            # MAP
    "dis_ems": at(F["dis_ems"]),                # MAP(新建)
    "den_bus": at(F["den_bus"]),                # MAP(新建)
    "location": df["location"].values.astype(float),  # MAP(城郊)
    "age": df["年龄"].values.astype(float),     # 个体(地图取参考值)
    "T_max": df["T_max"].values,                # 情景气象
    "RH_mean": df["RH_mean"].values,            # 情景气象
})
MAPPABLE = {"clim_LST","greenfrac","dw_built","FAR_proxy","ntl","elevation","dis_ems","den_bus","location"}
m = feat.notna().all(axis=1).values
X = feat[m].copy(); yy = y[m]
# 标准化连续变量
Z = (X - X.mean()) / X.std()

def fit(cols):
    Xc = sm.add_constant(Z[cols])
    return sm.Logit(yy, Xc).fit(disp=0)

cols = list(Z.columns)
print("全模型 n=%d, 重症 %d\n" % (len(yy), yy.sum()))
# 后向剔除:每次去掉 p 最大且 >0.05 的项
while True:
    r = fit(cols); pv = r.pvalues.drop("const")
    worst = pv.idxmax()
    if pv[worst] <= 0.05 or len(cols) <= 1: break
    cols.remove(worst)

r = fit(cols)
print("=== 后向剔除后(p<=0.05)最终模型 ===")
print("McFadden R2=%.3f, in-sample AUC=%.3f" %
      (r.prsquared, roc_auc_score(yy, r.predict(sm.add_constant(Z[cols])))))
print("%-12s %8s %8s %8s  %s" % ("变量", "β", "OR/SD", "p", "可上图"))
for c in cols:
    print("%-12s %+8.3f %8.2f %8.3f  %s" %
          (c, r.params[c], np.exp(r.params[c]), r.pvalues[c], "是" if c in MAPPABLE else "否(情景/个体)"))

# 空间CV AUC(最终模型)
from sklearn.linear_model import LogisticRegression
def spcv(cols):
    a = []
    for sd in range(6):
        bx = pd.qcut(lon[m],4,labels=False,duplicates="drop"); by=pd.qcut(lat[m],4,labels=False,duplicates="drop")
        blk=bx.astype(int)*10+by.astype(int); order=sorted(np.unique(blk))
        rng=np.random.RandomState(sd); rng.shuffle(order); folds=[order[i::4] for i in range(4)]
        oof=np.full(len(yy),np.nan)
        for tb in folds:
            te=np.isin(blk,tb)
            if te.sum()==0 or len(np.unique(yy[~te]))<2: continue
            lr=LogisticRegression(max_iter=1000).fit(Z[cols].values[~te],yy[~te])
            oof[te]=lr.predict_proba(Z[cols].values[te])[:,1]
        ok=~np.isnan(oof); a.append(roc_auc_score(yy[ok],oof[ok]))
    return np.mean(a),np.std(a)
auc,sd=spcv(cols)
print("\n最终模型 空间CV AUC=%.3f±%.3f" % (auc,sd))
print("可上图的显著变量:", [c for c in cols if c in MAPPABLE])
