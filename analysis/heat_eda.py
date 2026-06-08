# -*- coding: utf-8 -*-
"""
(Anaconda)中暑病例可行性检验:病例点环境 vs 人口加权背景点环境是否有显著差异。
读 Excel 病例点 -> 映射到 100m 特征网格 -> 抽人口加权背景 -> 比较 LST/绿地/建成等。
同时保存 case_cells.npz(病例落点行列)供后续 venv 建模。
"""
import numpy as np, pandas as pd
from pyproj import Transformer

XLSX = r"C:\Users\Administrator\Documents\60岁以上中暑病例分布_TableToExcel.xlsx"
FG = r"E:\projects\hia_demo\feature_grids_dense.npz"

df = pd.read_excel(XLSX)
x = df["x"].values; y = df["y"].values   # WGS84 lon/lat
G = np.load(FG, allow_pickle=True)
gt = G["gt"]; NY, NX = G["greenfrac"].shape
tr = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
ux, uy = tr.transform(x, y)
col = ((ux - gt[0]) / gt[1]).astype(int)
row = ((uy - gt[3]) / gt[5]).astype(int)
inb = (col >= 0) & (col < NX) & (row >= 0) & (row < NY)
print("病例 %d 个, 落入网格 %d" % (len(df), inb.sum()))
cr, cc = row[inb], col[inb]

COVS = ["lst_filled", "greenfrac", "dw_built", "bldg_height", "ntl", "elevation", "pop"]
# 病例落点有效(有协变量)
valid = np.array([np.isfinite(G["greenfrac"][r, c]) for r, c in zip(cr, cc)])
cr, cc = cr[valid], cc[valid]
print("病例落在有效数据格 %d" % len(cr))

# 人口加权背景点:在有数据陆地格里按人口概率抽样
gf = G["greenfrac"]; pop = np.nan_to_num(G["pop"]); wc = G["worldcover"]
land = np.isfinite(gf) & (wc != 80) & (wc != 90) & np.isfinite(G["lst_filled"])
rr, ccc = np.where(land)
w = pop[rr, ccc]; w = np.where(w > 0, w, 0.01); w = w / w.sum()
rng = np.random.RandomState(0)
nbg = 5000
idx = rng.choice(len(rr), size=nbg, p=w)
br, bc = rr[idx], ccc[idx]

print("\n=== 病例点 vs 人口加权背景 协变量均值 ===")
print("%-12s %10s %10s %8s" % ("协变量", "病例(n=%d)" % len(cr), "背景(n=%d)" % nbg, "差异%"))
for cov in COVS:
    a = G[cov][cr, cc].astype(float); b = G[cov][br, bc].astype(float)
    ma, mb = np.nanmean(a), np.nanmean(b)
    diff = 100 * (ma - mb) / (abs(mb) + 1e-9)
    print("%-12s %10.3f %10.3f %+7.1f%%" % (cov, ma, mb, diff))

np.savez(r"E:\projects\hia_demo\analysis\out\case_cells.npz",
         rows=cr, cols=cc, lon=x[inb][valid], lat=y[inb][valid])
print("\n已存 case_cells.npz (病例落点)")
