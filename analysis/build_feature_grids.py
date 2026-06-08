# -*- coding: utf-8 -*-
"""
(Anaconda)从新版多年合成 CSV + 绿地栅格,产出纯 numpy 特征网格 feature_grids.npz。
新 CSV(SH_HIA_100m_multiyear.csv, 60.7万行)有效 LST 100%、中心城区全覆盖,
不再需要 LST 补洞。greenfrac/green_bin 由 tif 采样到 CSV 点。
"""
import numpy as np
import pandas as pd
from osgeo import gdal
from pyproj import Transformer

CSV = r"C:\Users\Administrator\Downloads\SH_HIA_100m_multiyear.csv"
TIF_FRAC = r"C:\Users\Administrator\Downloads\SH_greenfrac_100m.tif"
TIF_BIN = r"C:\Users\Administrator\Downloads\SH_green_100m.tif"
OUT = r"E:\projects\hia_demo\feature_grids.npz"

dsf = gdal.Open(TIF_FRAC); GT = dsf.GetGeoTransform()
NX, NY = dsf.RasterXSize, dsf.RasterYSize
arr_f = dsf.ReadAsArray().astype(np.float32)
arr_b = gdal.Open(TIF_BIN).ReadAsArray().astype(np.float32)

df = pd.read_csv(CSV)
tr = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
x, y = tr.transform(df["lon"].values, df["lat"].values)
col = ((x - GT[0]) / GT[1]).astype(int)
row = ((y - GT[3]) / GT[5]).astype(int)
inb = (col >= 0) & (col < NX) & (row >= 0) & (row < NY)
r, c = row[inb], col[inb]
print("CSV %d 行, 落入网格 %d, 唯一格 %d" %
      (len(df), inb.sum(), len({(int(a), int(b)) for a, b in zip(r, c)})))

def grid(name, dtype=np.float32, fill=np.nan):
    g = np.full((NY, NX), fill, dtype=dtype)
    g[r, c] = df.loc[inb, name].values.astype(dtype)
    return g

# greenfrac/green_bin:用 CSV 点处的 tif 采样值(与其它特征同网格)
gf = np.full((NY, NX), np.nan, np.float32); gf[r, c] = arr_f[r, c]
gb = np.full((NY, NX), np.nan, np.float32); gb[r, c] = arr_b[r, c]

lst = grid("LST")  # 新数据 100% 有效
arrs = dict(
    dw_built=grid("dw_built"), bldg_height=grid("bldg_height"),
    FAR_proxy=grid("FAR_proxy"), ntl=grid("ntl"),
    elevation=grid("elevation"), slope=grid("slope"),
    greenfrac=gf, green_bin=gb,
    worldcover=grid("worldcover", np.int16, -1),
    pop=grid("pop"),
    lst_obs=lst, lst_filled=lst,           # 新数据有效,obs 与 filled 相同
    lst_count=grid("LST_count"),
    lon=np.full((NY, NX), np.nan, np.float32),
    lat=np.full((NY, NX), np.nan, np.float32),
    gt=np.array(GT, dtype=np.float64),
)
# 全网格每格中心经纬度(运行时点-多边形判断免投影)
cc = (np.arange(NX) + 0.5) * GT[1] + GT[0]
cr = (np.arange(NY) + 0.5) * GT[5] + GT[3]
gx, gy = np.meshgrid(cc, cr)
inv = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)
glon, glat = inv.transform(gx.ravel(), gy.ravel())
arrs["lon"] = np.asarray(glon, np.float32).reshape(NY, NX)
arrs["lat"] = np.asarray(glat, np.float32).reshape(NY, NX)

np.savez_compressed(OUT, **arrs)
import os
vmask = np.isfinite(lst) & (lst >= 20) & (lst <= 60)
print("已存 %s (%.1f MB)" % (OUT, os.path.getsize(OUT)/1e6))
print("有效LST格 %d, LST中位 %.1f" % (vmask.sum(), np.nanmedian(lst[vmask])))
