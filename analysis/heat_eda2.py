# -*- coding: utf-8 -*-
"""(Anaconda)分析含发病当天温度的病例数据:严重程度信号 + 温度/环境差异。"""
import pandas as pd, numpy as np
fp = r"C:\Users\Administrator\Downloads\MODIS_LST_Heatstroke_Cases_v3 (1).xlsx"
df = pd.read_excel(fp)
print("总病例 %d, 日期 %s ~ %s" % (len(df), df.date.min(), df.date.max()))
print("严重程度:", df["中暑诊断"].value_counts().to_dict())
print("性别:", df["性别"].value_counts().to_dict(), " 年龄 %.0f~%.0f 均%.1f" %
      (df["年龄"].min(), df["年龄"].max(), df["年龄"].mean()))
print("location 取值:", df["location"].value_counts().to_dict())
print("data_source(时相):", df["data_source"].value_counts().to_dict())

sev = (df["中暑诊断"] == "重症中暑").astype(int)
print("\n重症占比 %.1f%% (n重=%d, n轻=%d)" % (100*sev.mean(), sev.sum(), (1-sev).sum()))

covs = ["MODIS_LST", "T_mean", "T_max", "RH_mean", "Td_mean", "年龄",
        "dis_park", "dis_cool", "dis_ems", "n_cool", "area_green", "NDVI",
        "GVI", "FAR", "BC", "den_bus", "dis_metro", "den_inter", "location"]
print("\n=== 重症 vs 轻症 各指标均值 ===")
print("%-12s %10s %10s %8s" % ("指标", "重症", "轻症", "差异%"))
for c in covs:
    a = df.loc[sev == 1, c].astype(float); b = df.loc[sev == 0, c].astype(float)
    ma, mb = a.mean(), b.mean()
    diff = 100*(ma-mb)/(abs(mb)+1e-9)
    print("%-12s %10.3f %10.3f %+7.1f%%" % (c, ma, mb, diff))

# 与重症的点二列相关
print("\n=== 各指标与'重症'的相关系数(|r|降序) ===")
cc = []
for c in covs:
    v = df[c].astype(float)
    m = v.notna()
    r = np.corrcoef(v[m], sev[m])[0, 1]
    cc.append((c, r))
for c, r in sorted(cc, key=lambda t: -abs(t[1])):
    print("  %-12s r=%+.3f" % (c, r))

print("\nMODIS_LST 病例分布: %.1f~%.1f 均%.1f (缺%d)" %
      (df.MODIS_LST.min(), df.MODIS_LST.max(), df.MODIS_LST.mean(), df.MODIS_LST.isna().sum()))
print("T_max 病例分布: %.1f~%.1f 均%.1f" % (df.T_max.min(), df.T_max.max(), df.T_max.mean()))
