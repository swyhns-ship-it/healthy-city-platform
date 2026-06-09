# -*- coding: utf-8 -*-
"""离线预处理:2013–2025 高温中暑病例监测数据(xlsx)→ 运行时紧凑 npz。

产物 heatcase_points.npz(提交进仓库,供「健康风险 · 中暑病例风险地图」页用):
  经纬度(现住地 + 中暑发生地)、严重程度、重症亚型、是否死亡、年份/月、年龄、
  性别、职业分组、所属街道索引(归到现有 cooling_jiedao.geojson 的 230 街道)。

只在有原始 xlsx 的机器上跑一次。运行时不依赖 openpyxl/shapely。
用法(venv):
  .venv/Scripts/python.exe analysis/build_heatcase_data.py
"""
import json
import os

import numpy as np
import pandas as pd
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

SRC = r"D:/xwechat_files/wxid_m7dpdt527k1j21_88e6/msg/file/2026-06/2023-2025年高温中暑病例监测数据-经纬度.xlsx"
ROOT = r"D:/projects/healthy-city-platform"
BBOX = (120.8, 30.6, 122.1, 31.95)   # 上海(略放宽),挡掉地理编码异常值

SUBTYPE_LABELS = ["无/轻症", "热射病", "热痉挛", "热衰竭", "混合型"]
OCC_LABELS = ["未填/不详", "建筑工人", "农民", "离退人员", "学生", "物流/运输", "其他"]


def occ_group(s):
    if pd.isna(s) or str(s).strip() in ("", "不详", "其他（备注）", "其他(备注)"):
        return 0
    s = str(s).strip()
    return {"建筑工人": 1, "农民": 2, "离退人员": 3, "学生": 4,
            "物流人员": 5, "生产运输设备操作人员": 5}.get(s, 6)


def sex_code(s):
    s = str(s)
    if s.startswith("男"):
        return 0
    if s.startswith("女"):
        return 1
    return -1


print("▶ 读取 xlsx ...")
df = pd.read_excel(SRC, sheet_name=0)
print(f"  原始记录:{len(df):,}")

# —— 字段解析 ——
lon = pd.to_numeric(df["现住_经度WGS84"], errors="coerce")
lat = pd.to_numeric(df["现住_纬度WGS84"], errors="coerce")
olon = pd.to_numeric(df["中暑_经度WGS84"], errors="coerce")
olat = pd.to_numeric(df["中暑_纬度WGS84"], errors="coerce")
dt = pd.to_datetime(df["中暑日期"], errors="coerce")
severe = (df["中暑诊断"].astype(str).str.strip() == "重症中暑").astype(np.int8)
death = (df["是否死亡"].astype(str).str.strip() == "是").astype(np.int8)
subtype = df["重症中暑"].map({"热射病": 1, "热痉挛": 2, "热衰竭": 3, "混合型": 4}).fillna(0).astype(np.int8)
age_unit = df["年龄单位"].astype(str)
age = pd.to_numeric(df["年龄"], errors="coerce")
age = np.where(age_unit.str.contains("月"), 0, age)          # “月”单位婴儿 → 0 岁
age = pd.Series(age).fillna(-1).astype(np.int16)
sex = df["性别"].map(sex_code).fillna(-1).astype(np.int8)
occ = df["职业"].map(occ_group).astype(np.int8)
year = dt.dt.year.fillna(0).astype(np.int16)
month = dt.dt.month.fillna(0).astype(np.int8)

# —— 地理编码质量:level 粗到“乡镇/区县/城市/NoClass”会被吸附到中心点(虚假聚集),标为不精确 ——
COARSE_LEVELS = {"乡镇", "区县", "城市", "NoClass"}
conf = pd.to_numeric(df["现住_confidence"], errors="coerce").fillna(0).astype(np.int16)
oconf = pd.to_numeric(df["中暑_confidence"], errors="coerce").fillna(0).astype(np.int16)
hlev, olev = df["现住_level"], df["中暑_level"]
precise = (hlev.notna() & ~hlev.isin(COARSE_LEVELS)).astype(np.int8)   # 1=精确定位点
oprecise = (olev.notna() & ~olev.isin(COARSE_LEVELS)).astype(np.int8)

# —— 上海范围过滤(按现住地)——
a, b, c, d = BBOX
in_sh = (lon >= a) & (lon <= c) & (lat >= b) & (lat <= d)
keep = in_sh & lon.notna() & lat.notna()
print(f"  落在上海范围内(现住地):{int(keep.sum()):,} / {len(df):,}")

idx = np.where(keep.values)[0]
lon, lat = lon.values[idx], lat.values[idx]
olon, olat = olon.values[idx], olat.values[idx]
severe, death, subtype = severe.values[idx], death.values[idx], subtype.values[idx]
age, sex, occ = age.values[idx], sex.values[idx], occ.values[idx]
year, month = year.values[idx], month.values[idx]
conf, oconf = conf.values[idx], oconf.values[idx]
precise, oprecise = precise.values[idx], oprecise.values[idx]

# —— 归到现有 230 街道(point-in-polygon,复用 cooling_jiedao.geojson)——
print("▶ 归街道(复用 cooling_jiedao.geojson)...")
gj = json.load(open(os.path.join(ROOT, "cooling_jiedao.geojson"), encoding="utf-8"))
polys, names = [], []
for f in sorted(gj["features"], key=lambda x: x["properties"]["idx"]):
    polys.append(shape(f["geometry"]))
    names.append(f["properties"]["NAME"])
tree = STRtree(polys)
jd = np.full(len(lon), -1, np.int16)
for i in range(len(lon)):
    p = Point(float(lon[i]), float(lat[i]))
    for j in tree.query(p):
        if polys[int(j)].contains(p):
            jd[i] = int(j)
            break
print(f"  已归街道:{int((jd >= 0).sum()):,} | 未落入(水域等):{int((jd < 0).sum()):,}")

out = os.path.join(ROOT, "heatcase_points.npz")
np.savez_compressed(
    out,
    lon=lon.astype(np.float32), lat=lat.astype(np.float32),
    olon=olon.astype(np.float32), olat=olat.astype(np.float32),
    severe=severe, death=death, subtype=subtype,
    age=age, sex=sex, occ=occ, year=year, month=month, jd=jd,
    conf=conf, oconf=oconf, precise=precise, oprecise=oprecise,
    jd_names=np.array(names, dtype="<U40"),
    occ_labels=np.array(OCC_LABELS, dtype="<U20"),
    subtype_labels=np.array(SUBTYPE_LABELS, dtype="<U20"),
)
print(f"  ✓ 写出 {out}  ({os.path.getsize(out)/1e6:.2f} MB)")

n = len(lon)
print(f"\n== 汇总 ==")
print(f"  上海病例:{n:,} | 重症 {int(severe.sum()):,}({severe.mean()*100:.1f}%)"
      f" | 死亡 {int(death.sum()):,}({death.mean()*100:.1f}%)")
print(f"  精确定位(现住地):{int(precise.sum()):,}({precise.mean()*100:.1f}%)"
      f" | 粗定位(街镇/区县中心点,地图默认剔除):{int((precise == 0).sum()):,}")
print(f"  年份:{int(year[year>0].min())}–{int(year.max())} | 有中暑发生地坐标:{int(np.isfinite(olon).sum()):,}")
print(f"  年龄中位:{int(np.median(age[age>=0]))} | 男 {int((sex==0).sum()):,} 女 {int((sex==1).sum()):,}")
print("\n✅ 完成。运行时数据:heatcase_points.npz")
