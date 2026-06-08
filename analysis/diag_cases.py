# -*- coding: utf-8 -*-
"""诊断 3 个案例中心点周围 5x5 网格的现状:greenfrac、观测LST、worldcover、是否land。"""
import os, sys, numpy as np
sys.path.insert(0, r"E:\projects\hia_demo")
from cases import CASES

g = np.load(r"E:\projects\hia_demo\green_lst_grid.npz", allow_pickle=True)
lon = g["lon_grid"]; lat = g["lat_grid"]
gf = g["greenfrac_cur"]; obs = g["obs_lst"]; wc = g["worldcover"]; land = g["land_mask"]

def nearest_cell(clon, clat):
    d = (lon - clon) ** 2 + (lat - clat) ** 2
    r, c = np.unravel_index(np.nanargmin(d), d.shape)
    return r, c

for cid, c in CASES.items():
    r, col = nearest_cell(c["center_lng"], c["center_lat"])
    print("\n[%s] %s  中心(%.4f,%.4f) -> grid(%d,%d)" %
          (cid, c["label_short"], c["center_lng"], c["center_lat"], r, col))
    rr = slice(max(0, r-2), r+3); cc = slice(max(0, col-2), col+3)
    print("  greenfrac:\n", np.round(gf[rr, cc], 2))
    print("  obs_LST:\n", np.round(obs[rr, cc], 1))
    print("  worldcover:\n", wc[rr, cc])
    print("  land_mask:\n", land[rr, cc].astype(int))
