# -*- coding: utf-8 -*-
"""(Anaconda)从 EMS急救分站 + 公交站点 shp,建全市 100m 栅格:
dis_ems(到最近急救站, m) 与 den_bus(1km 内公交站数)。对齐 feature_grids_dense 网格。"""
import numpy as np
from osgeo import ogr
from pyproj import Transformer
from scipy.ndimage import distance_transform_edt

EMS = r"H:\heat_facility\急救分站.shp"
BUS = r"H:\swy\上海\04-交通数据\公交车站\上海_公交站点.shp"
FG = r"E:\projects\hia_demo\feature_grids_dense.npz"
OUT = r"E:\projects\hia_demo\heat_facility_grids.npz"

def read_points(fp):
    ds = ogr.Open(fp); lyr = ds.GetLayer()
    xs, ys = [], []
    for feat in lyr:
        g = feat.GetGeometryRef()
        if g is None: continue
        xs.append(g.GetX()); ys.append(g.GetY())
    return np.array(xs), np.array(ys)

ex, ey = read_points(EMS); bx, by = read_points(BUS)
print("EMS 点 %d (lon %.3f~%.3f), 公交点 %d" % (len(ex), ex.min(), ex.max(), len(bx)))

G = np.load(FG, allow_pickle=True); gt = G["gt"]; NY, NX = G["greenfrac"].shape
tr = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)

def to_rc(x, y):
    ux, uy = tr.transform(x, y)
    c = ((ux - gt[0]) / gt[1]).astype(int); r = ((uy - gt[3]) / gt[5]).astype(int)
    ok = (c >= 0) & (c < NX) & (r >= 0) & (r < NY)
    return r[ok], c[ok]

# dis_ems:到最近急救站距离(米);用 EDT,100m/格
er, ec = to_rc(ex, ey)
ems_mask = np.zeros((NY, NX), bool); ems_mask[er, ec] = True
dis_ems = distance_transform_edt(~ems_mask) * 100.0  # 米

# den_bus:每格 1km(10格)半径内公交站数;用计数栅格 + 圆盘卷积
br, bc = to_rc(bx, by)
cnt = np.zeros((NY, NX), np.float32); np.add.at(cnt, (br, bc), 1.0)
from scipy.ndimage import uniform_filter
R = 10  # 10格≈1km
box = uniform_filter(cnt, size=2*R+1, mode="constant") * (2*R+1)**2  # 方窗计数
den_bus = box.astype(np.float32)

land = np.isfinite(G["greenfrac"])
dis_ems = np.where(land, dis_ems, np.nan).astype(np.float32)
den_bus = np.where(land, den_bus, np.nan).astype(np.float32)
np.savez_compressed(OUT, dis_ems=dis_ems, den_bus=den_bus)
import os
print("已存 %s (%.1f MB)" % (OUT, os.path.getsize(OUT)/1e6))
print("dis_ems 陆地: 中位%.0fm 范围%.0f~%.0f" %
      (np.nanmedian(dis_ems[land]), np.nanmin(dis_ems[land]), np.nanmax(dis_ems[land])))
print("den_bus 陆地: 中位%.0f 范围%.0f~%.0f" %
      (np.nanmedian(den_bus[land]), np.nanmin(den_bus[land]), np.nanmax(den_bus[land])))
