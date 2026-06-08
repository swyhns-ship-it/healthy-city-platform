# -*- coding: utf-8 -*-
"""
LST 空间插值补洞:中心城区 LST 合成有成片无效像元(云/条带空洞),
用有效 LST 观测对'有特征可预测'的网格做空间插值,生成连续'现状 LST'底图。

linear(Delaunay)插值为主,凸包外用 nearest 兜底,结果裁剪到 [20,60]。
把 obs_lst_filled 写回 green_lst_grid.npz。
"""
import numpy as np
from scipy.interpolate import griddata

NPZ = r"E:\projects\hia_demo\green_lst_grid.npz"
g = dict(np.load(NPZ, allow_pickle=True))

obs = g["obs_lst"].astype(np.float32)         # (NY,NX) 观测,坏值为 <20 或 NaN
pred0 = g["pred_anchor"][0]                    # 有特征的格此处非 NaN
NY, NX = obs.shape

predictable = ~np.isnan(pred0)
valid = predictable & (obs >= 20) & (obs <= 60)
target = predictable & ~valid                 # 要补的格(有特征但 LST 无效)

print("可预测格 %d, 有效LST %d (%.1f%%), 待补 %d" %
      (predictable.sum(), valid.sum(), 100*valid.sum()/predictable.sum(), target.sum()))

vr, vc = np.where(valid)
tr, tc = np.where(target)
src_pts = np.column_stack([vr, vc]).astype(np.float32)
src_val = obs[vr, vc]
tgt_pts = np.column_stack([tr, tc]).astype(np.float32)

print("插值中(源 %d 点 -> 目标 %d 点)..." % (len(src_val), len(tgt_pts)))
fill_lin = griddata(src_pts, src_val, tgt_pts, method="linear")
nan_mask = np.isnan(fill_lin)
if nan_mask.any():
    fill_lin[nan_mask] = griddata(src_pts, src_val, tgt_pts[nan_mask], method="nearest")
fill_lin = np.clip(fill_lin, 20, 60)

filled = obs.copy()
filled[tr, tc] = fill_lin.astype(np.float32)

# 校验:案例1徐汇中心附近补洞后应为合理城市高温
g["obs_lst_filled"] = filled
np.savez_compressed(NPZ, **g)

print("补洞后 filled: 中位 %.2f, 均值 %.2f, 范围 %.1f~%.1f" %
      (np.nanmedian(filled), np.nanmean(filled), np.nanmin(filled), np.nanmax(filled)))
# 抽查徐汇 grid(751,502)
print("徐汇(751,502) 补洞前 %.1f -> 补洞后 %.1f" % (obs[751,502], filled[751,502]))
print("已写回", NPZ)
