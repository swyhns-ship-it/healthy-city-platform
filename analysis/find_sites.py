# -*- coding: utf-8 -*-
"""
为 3 个案例在真实栅格里找"有有效数据 + 符合叙事"的地块。
输出每个案例:建议多边形(经纬度环)、中心、地块统计、用引擎口径预测的 ΔLST。
"""
import numpy as np

NPZ = r"E:\projects\hia_demo\green_lst_grid.npz"
g = np.load(NPZ, allow_pickle=True)
lon = g["lon_grid"]; lat = g["lat_grid"]
gf = g["greenfrac_cur"]; wc = g["worldcover"]
filled = g["obs_lst_filled"]; pop = g["pop"]
pred = g["pred_anchor"]; anchors = g["anchors"].astype(float)
NY, NX = gf.shape
HALF_LON, HALF_LAT = 0.00055, 0.00045   # ~半格(100m)经纬度

def interp(av, x):  # av (n,k), x (n,)
    step = anchors[1]-anchors[0]; k=len(anchors)
    xa=np.clip(x,anchors[0],anchors[-1]); idx=np.clip(((xa-anchors[0])/step).astype(int),0,k-2)
    g0=anchors[0]+idx*step; fr=(xa-g0)/step; r=np.arange(len(x))
    return av[r,idx]+fr*(av[r,idx+1]-av[r,idx])

def dlst_for_cells(rows, cols, target):
    cur = gf[rows, cols]
    av = pred[:, rows, cols].T
    d = interp(av, np.full(len(cur), target)) - interp(av, cur)
    cp = np.nan_to_num(pop[rows, cols])
    pw = np.sum(d*cp)/np.sum(cp) if cp.sum()>0 else np.nan
    return d, cur, cp, pw

def poly_from_cells(rows, cols):
    los = lon[rows, cols]; las = lat[rows, cols]
    a,b,c,d = los.min()-HALF_LON, los.max()+HALF_LON, las.min()-HALF_LAT, las.max()+HALF_LAT
    return [[a,c],[b,c],[b,d],[a,d],[a,c]]

def window(clon, clat, rkm):
    rdeg = rkm/111.0
    return (np.abs(lon-clon) < rdeg) & (np.abs(lat-clat) < rdeg*1.15)

def grow(seed, elig, n):
    """从 seed 出发,沿 8 邻接在 elig 内 BFS 生长,最多 n 格(连续地块)。"""
    from collections import deque
    R,C = elig.shape
    q = deque([seed]); seen={seed}; out=[]
    while q and len(out)<n:
        r,c = q.popleft()
        if not elig[r,c]: continue
        out.append((r,c))
        for dr in (-1,0,1):
            for dc in (-1,0,1):
                nr,nc=r+dr,c+dc
                if 0<=nr<R and 0<=nc<C and (nr,nc) not in seen and elig[nr,nc]:
                    seen.add((nr,nc)); q.append((nr,nc))
    rows=np.array([p[0] for p in out]); cols=np.array([p[1] for p in out])
    return rows, cols

def report(name, rows, cols, target, mode):
    d, cur, cp, pw = dlst_for_cells(rows, cols, target)
    poly = poly_from_cells(rows, cols)
    cc_lon = lon[rows,cols].mean(); cc_lat = lat[rows,cols].mean()
    print("\n=== %s ===" % name)
    print(" 命中 %d 格(%.0f ha) 中心(%.4f,%.4f)" % (len(rows), len(rows), cc_lon, cc_lat))
    print(" 现状 greenfrac 均值 %.2f, 目标 %.2f" % (cur.mean(), target))
    print(" 现状(补洞)LST 均值 %.1f°C, 人口 %.0f" % (filled[rows,cols].mean(), cp.sum()))
    print(" ΔLST: 面积均值 %+.2f°C, 人口加权 %+.2f°C (范围 %+.2f~%+.2f)" %
          (d.mean(), pw, d.min(), d.max()))
    print(" 建议多边形:", [[round(x,5),round(y,5)] for x,y in poly])
    return poly

# ---- 案例1:徐汇漕河泾,建成低绿高温,选有人口的连续小块(~3ha)----
w = window(121.4042, 31.1731, 2.5)
cand = w & (wc==50) & (gf<0.08) & (filled>=20) & (filled<=60)
popn = np.nan_to_num(pop); popn[~cand] = -1
# 在合格格里选周边人口较高的热点为种子,生长 3 格
rr,cc = np.where(cand)
# 综合评分:热 + 有人口
sc = filled[rr,cc] + 0.05*np.nan_to_num(pop[rr,cc])
seed = (rr[np.argmax(sc)], cc[np.argmax(sc)])
r1,c1 = grow(seed, cand, 3)
report("案例1 徐汇·停车场→社区公园(新增, gf→0.9)", r1, c1, 0.9, "add")

# ---- 案例2:浦东花木,现状绿地且周边有居民,连续绿块(~3ha)----
w = window(121.5520, 31.2050, 3.5)
cand = w & (np.isin(wc,[10,30])) & (gf>0.5) & (filled>=20) & (filled<=60)
rr,cc = np.where(cand)
# 选"周边 5x5 人口最高"的绿格为种子(拆绿影响的是周边居民)
from scipy.ndimage import uniform_filter
popdens = uniform_filter(np.nan_to_num(pop), size=5, mode="constant")
seed = (rr[np.argmax(popdens[rr,cc])], cc[np.argmax(popdens[rr,cc])])
r2,c2 = grow(seed, cand, 3)
report("案例2 浦东·拆除社区绿地建地铁口(损失, gf→0.05)", r2, c2, 0.05, "remove")

# ---- 案例3:缺绿郊区(农田/建成)大片连续高温块,~85ha,移动窗口找 ----
print("\n[案例3 搜索:农田/建成、低绿、高温、连续大块]")
elig = (np.isin(wc,[40,50])) & (gf<0.2) & (filled>=33) & (filled<=60)
# 排除中心城区(粗略:离市中心>15km),偏郊区
citylon, citylat = 121.47, 31.23
far = (np.abs(lon-citylon) > 0.13) | (np.abs(lat-citylat) > 0.13)
elig = elig & far
# 9x9 窗口求和找最密集块
from scipy.ndimage import uniform_filter
score = uniform_filter(elig.astype(float), size=9, mode="constant")
ci = np.unravel_index(np.argmax(score), score.shape)
print(" 最优块中心 grid", ci, "经纬", round(float(lon[ci]),4), round(float(lat[ci]),4),
      " 9x9内合格率 %.2f" % score[ci])
# 取该块 9x9 内的合格格作为公园范围
r0,c0 = ci
sl_r = slice(max(0,r0-4), r0+5); sl_c = slice(max(0,c0-4), c0+5)
sub = np.zeros_like(elig); sub[sl_r,sl_c] = elig[sl_r,sl_c]
r3,c3 = np.where(sub)
report("案例3 郊区·新建大型郊野公园(新增, gf→0.9)", r3, c3, 0.9, "add")
