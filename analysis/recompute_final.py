# -*- coding: utf-8 -*-
"""用硬化后的 green_lst 引擎对 3 个最终多边形重算 ΔLST,并算 500m 集水人口。"""
import os, sys, json
import numpy as np
sys.path.insert(0, r"E:\projects\hia_demo")
from green_lst import predict_delta_lst

g = np.load(r"E:\projects\hia_demo\green_lst_grid.npz", allow_pickle=True)
lon = g["lon_grid"]; lat = g["lat_grid"]; pop = np.nan_to_num(g["pop"])
filled = g["obs_lst_filled"]

POLYS = {
 "case_1": dict(mode="add", poly=[[121.4173,31.18876],[121.41946,31.18876],
        [121.41946,31.19057],[121.4173,31.19057],[121.4173,31.18876]]),
 "case_2": dict(mode="remove", poly=[[121.5635,31.23739],[121.5646,31.23739],
        [121.5646,31.23829],[121.5635,31.23829],[121.5635,31.23739]]),
 "case_3": dict(mode="add", poly=[[121.10424,31.30541],[121.11388,31.30541],
        [121.11388,31.31365],[121.10424,31.31365],[121.10424,31.30541]]),
}

def catchment_pop(poly, rkm=0.5):
    los=[p[0] for p in poly]; las=[p[1] for p in poly]
    clo=sum(los)/len(los); cla=sum(las)/len(las); rd=rkm/111.0
    m=(np.abs(lon-clo)<rd)&(np.abs(lat-cla)<rd*1.15)
    return float(pop[m].sum()), clo, cla

out={}
for cid,info in POLYS.items():
    r=predict_delta_lst(info["poly"], mode=info["mode"])
    cpop,clo,cla=catchment_pop(info["poly"])
    dlst=r["delta_lst_mean"]; dair=round(dlst*0.7,2)
    out[cid]=dict(center=[round(clo,4),round(cla,4)], n_cells=r["n_cells"],
                  size_ha=round(r["area_ha"],1), greenfrac_cur=r["greenfrac_cur_mean"],
                  obs_lst_now=r["obs_lst_mean"], delta_lst_C=dlst,
                  delta_air_temp_C=dair, pop_500m=round(cpop))
    print("%s 中心(%.4f,%.4f) %d格/%.0fha gf现%.2f LST现%.1f ΔLST%+.2f ΔTair%+.2f 500m人口%.0f"%
          (cid,clo,cla,r["n_cells"],r["area_ha"],r["greenfrac_cur_mean"],
           r["obs_lst_mean"],dlst,dair,cpop))
json.dump(out, open(r"E:\projects\hia_demo\analysis\out\final_cases.json","w"),
          ensure_ascii=False, indent=2)
print("\n已存 final_cases.json")
