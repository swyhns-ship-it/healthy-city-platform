# -*- coding: utf-8 -*-
"""
(Anaconda)把特征网格补密,解决 CSV 覆盖空洞导致的"网格稀疏/不均匀"。
- greenfrac / green_bin:用完整 tif(本就稠密)
- 建成/地形/人口/LST:只在 CSV 点上有 -> 最近邻填补到"真实数据 buffer 格内"
- 超出 buffer(默认 3 格=300m)的真空洞仍留空(不凭空造数)
输出 feature_grids_dense.npz(纯 numpy)。
"""
import numpy as np
from osgeo import gdal
from scipy.ndimage import binary_dilation, distance_transform_edt

FG = r"E:\projects\hia_demo\feature_grids.npz"
TIF_FRAC = r"C:\Users\Administrator\Downloads\SH_greenfrac_100m.tif"
TIF_BIN = r"C:\Users\Administrator\Downloads\SH_green_100m.tif"
OUT = r"E:\projects\hia_demo\feature_grids_dense.npz"
BUFFER = 2  # 最近邻填补半径(格);新数据已稠密,仅填网格对齐小缝

G = dict(np.load(FG, allow_pickle=True))
NY, NX = G["greenfrac"].shape

# 完整 greenfrac / green_bin
gf_full = gdal.Open(TIF_FRAC).ReadAsArray().astype(np.float32)
gb_full = gdal.Open(TIF_BIN).ReadAsArray().astype(np.float32)
assert gf_full.shape == (NY, NX)

# CSV 数据掩膜(以 dw_built 是否有值为准)
valid = np.isfinite(G["dw_built"])
extent = binary_dilation(valid, iterations=BUFFER)
print("CSV有效格 %d -> buffer%d格后extent %d (%.1f%%覆盖率提升)" %
      (valid.sum(), BUFFER, extent.sum(), 100*extent.sum()/max(valid.sum(),1)))

# 最近邻索引(从最近的 valid 格取值)
idx = distance_transform_edt(~valid, return_indices=True)[1]
def nearest_fill(arr, fillmask, nodata=np.nan):
    out = arr[tuple(idx)]                     # 每格取最近 valid 值
    res = np.where(fillmask, out, nodata)
    return res

dense = {}
for k in ["dw_built", "bldg_height", "FAR_proxy", "ntl", "elevation", "slope", "pop", "lst_filled"]:
    dense[k] = nearest_fill(G[k].astype(np.float32), extent).astype(np.float32)
# worldcover 最近邻(用于水体掩膜)
wc_fill = G["worldcover"][tuple(idx)]
dense["worldcover"] = np.where(extent, wc_fill, -1).astype(np.int16)
# greenfrac/green_bin 用完整 tif,但限制在 extent 内(extent 外不预测)
dense["greenfrac"] = np.where(extent, gf_full, np.nan).astype(np.float32)
dense["green_bin"] = np.where(extent, gb_full, np.nan).astype(np.float32)
dense["lon"] = G["lon"]; dense["lat"] = G["lat"]; dense["gt"] = G["gt"]
dense["lst_obs"] = G["lst_obs"]

np.savez_compressed(OUT, **dense)
import os
print("已存 %s (%.1f MB)" % (OUT, os.path.getsize(OUT)/1e6))

# 抽查徐汇 30x30 覆盖率
lon = G["lon"]; lat = G["lat"]
d = (lon-121.4182)**2 + (lat-31.1895)**2
r, c = np.unravel_index(np.nanargmin(d), d.shape)
def cov_at(clon, clat, name):
    dd = (lon-clon)**2 + (lat-clat)**2
    rr, ccc = np.unravel_index(np.nanargmin(dd), dd.shape)
    before = np.isfinite(G["greenfrac"])[rr-15:rr+15, ccc-15:ccc+15].mean()
    after = np.isfinite(dense["greenfrac"])[rr-15:rr+15, ccc-15:ccc+15].mean()
    print("%s 30x30 覆盖率: 补密前 %.2f -> 补密后 %.2f" % (name, before, after))
cov_at(121.4182, 31.1895, "徐汇")
cov_at(121.4400, 31.2800, "静安")
cov_at(121.5000, 31.2300, "陆家嘴")
