# -*- coding: utf-8 -*-
"""
(Anaconda)构建 1km(0.01°)空气污染建模网格:
- 目标:PM2.5/NO2 的 2024 年均与 12 月(冬季),裁到上海。
- 协变量:把 100m 的 feature_grids_dense 聚合到 1km(绿地/建成/灯光等取均值,人口取和)。
输出 pollution_grids.npz(纯 numpy)。
"""
import numpy as np, h5py, os

SH = (120.85, 122.05, 30.67, 31.90)  # lon_min,lon_max,lat_min,lat_max
FILES = {
 "pm25_y": r"C:\Users\Administrator\Downloads\CHAP_PM2.5_Y1K_2024_V4.nc",
 "pm25_w": r"C:\Users\Administrator\Downloads\CHAP_PM2.5_M1K_202412_V4.nc",
 "no2_y":  r"C:\Users\Administrator\Downloads\CHAP_NO2_Y1K_2024_V2.nc",
 "no2_w":  r"C:\Users\Administrator\AppData\Local\Temp\CHAP_NO2_M1K_202412_V2.nc",
}
FG = r"E:\projects\hia_demo\feature_grids_dense.npz"
OUT = r"E:\projects\hia_demo\pollution_grids.npz"


def read_chap(fp):
    h = h5py.File(fp, "r")
    var = [k for k in h.keys() if k not in ("lat", "lon")][0]
    lat = h["lat"][:].astype(float); lon = h["lon"][:].astype(float)
    d = h[var]
    sf = float(np.array(d.attrs.get("scale_factor", [1.0])).ravel()[0])
    off = float(np.array(d.attrs.get("add_offset", [0.0])).ravel()[0])
    fv = np.array(d.attrs.get("_FillValue", [None])).ravel()[0]
    ri = np.where((lat >= SH[2]) & (lat <= SH[3]))[0]
    ci = np.where((lon >= SH[0]) & (lon <= SH[1]))[0]
    sub = d[ri.min():ri.max()+1, ci.min():ci.max()+1].astype(float)
    sub = np.where(sub == fv, np.nan, sub*sf + off)
    return sub, lat[ri.min():ri.max()+1], lon[ci.min():ci.max()+1]


# 以 PM2.5 年的裁块为基准网格
pm25_y, clat, clon = read_chap(FILES["pm25_y"])
NYg, NXg = pm25_y.shape
targets = {"pm25_y": pm25_y}
for k in ["pm25_w", "no2_y", "no2_w"]:
    arr, la, lo = read_chap(FILES[k])
    assert arr.shape == (NYg, NXg), (k, arr.shape)
    targets[k] = arr
print("CHAP 上海网格:", NYg, "x", NXg, " lon", clon.min(), clon.max(), " lat", clat.min(), clat.max())

# ---- 聚合 100m 协变量到 1km ----
G = np.load(FG, allow_pickle=True)
lon100 = G["lon"].ravel(); lat100 = G["lat"].ravel()
dlon = clon[1]-clon[0]; dlat = clat[1]-clat[0]
ci = np.round((lon100 - clon[0]) / dlon).astype(int)
ri = np.round((lat100 - clat[0]) / dlat).astype(int)
ok = (ci >= 0) & (ci < NXg) & (ri >= 0) & (ri < NYg)

COV_MEAN = ["greenfrac", "dw_built", "bldg_height", "FAR_proxy", "ntl", "elevation"]
agg = {}
for name in COV_MEAN:
    v = G[name].ravel()
    m = ok & np.isfinite(v)
    s = np.zeros((NYg, NXg)); c = np.zeros((NYg, NXg))
    np.add.at(s, (ri[m], ci[m]), v[m]); np.add.at(c, (ri[m], ci[m]), 1.0)
    agg[name] = np.where(c > 0, s / c, np.nan)
# 人口取和
v = G["pop"].ravel(); m = ok & np.isfinite(v)
popg = np.zeros((NYg, NXg)); np.add.at(popg, (ri[m], ci[m]), v[m])
agg["pop"] = popg

glon, glat = np.meshgrid(clon, clat)
out = dict(lon=glon.astype(np.float32), lat=glat.astype(np.float32),
           clon=clon.astype(np.float32), clat=clat.astype(np.float32))
out.update({k: v.astype(np.float32) for k, v in targets.items()})
out.update({k: v.astype(np.float32) for k, v in agg.items()})
np.savez_compressed(OUT, **out)
print("已存", OUT, "%.2f MB" % (os.path.getsize(OUT)/1e6))
print("协变量覆盖(greenfrac非空格):", int(np.isfinite(agg["greenfrac"]).sum()), "/", NYg*NXg)
for k in targets: print("  %s 上海均值 %.1f" % (k, np.nanmean(targets[k])))
