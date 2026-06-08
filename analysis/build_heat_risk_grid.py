# -*- coding: utf-8 -*-
"""(venv)把中暑风险模型协变量聚合到 ~500m 经纬度网格,供运行时算风险面+what-if。"""
import numpy as np
G = np.load(r"E:\projects\hia_demo\feature_grids_dense.npz", allow_pickle=True)
F = np.load(r"E:\projects\hia_demo\heat_facility_grids.npz", allow_pickle=True)
lon = G["lon"].ravel(); lat = G["lat"].ravel()
gf = G["greenfrac"].ravel(); built = G["dw_built"].ravel(); dems = F["dis_ems"].ravel()
pop = np.nan_to_num(G["pop"].ravel())
m = np.isfinite(gf) & np.isfinite(built) & np.isfinite(dems)
lon, lat, gf, built, dems, pop = lon[m], lat[m], gf[m], built[m], dems[m], pop[m]

RES = 0.005  # ~500m
lon0, lat0 = 120.85, 30.67; lon1, lat1 = 122.05, 31.92
NX = int((lon1-lon0)/RES)+1; NY = int((lat1-lat0)/RES)+1
ix = ((lon-lon0)/RES).astype(int); iy = ((lat-lat0)/RES).astype(int)
ok = (ix >= 0) & (ix < NX) & (iy >= 0) & (iy < NY)
ix, iy = ix[ok], iy[ok]

def agg(v):
    s = np.zeros((NY, NX)); c = np.zeros((NY, NX))
    np.add.at(s, (iy, ix), v[ok]); np.add.at(c, (iy, ix), 1.0)
    return np.where(c > 0, s/np.maximum(c, 1), np.nan)

def agg_sum(v):
    s = np.zeros((NY, NX)); np.add.at(s, (iy, ix), v[ok]); return s
grid = dict(greenfrac=agg(gf).astype(np.float32), dw_built=agg(built).astype(np.float32),
            dis_ems=agg(dems).astype(np.float32), pop=agg_sum(pop).astype(np.float32),
            lon0=lon0, lat0=lat0, res=RES, nx=NX, ny=NY)
# 每格中心经纬度
cx = lon0 + (np.arange(NX)+0.5)*RES; cy = lat0 + (np.arange(NY)+0.5)*RES
gx, gy = np.meshgrid(cx, cy)
grid["clon"] = gx.astype(np.float32); grid["clat"] = gy.astype(np.float32)
np.savez_compressed(r"E:\projects\hia_demo\heat_risk_grid.npz", **grid)
import os
print("已存 heat_risk_grid.npz  网格 %dx%d  有效格 %d  (%.2f MB)" %
      (NY, NX, int(np.isfinite(grid["greenfrac"]).sum()),
       os.path.getsize(r"E:\projects\hia_demo\heat_risk_grid.npz")/1e6))
