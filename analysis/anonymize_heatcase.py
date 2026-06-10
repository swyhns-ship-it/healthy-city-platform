# -*- coding: utf-8 -*-
"""病例坐标脱敏 —— 把提交进仓库/部署到云端的 heatcase_points.npz 做成脱敏版。

背景:heatcase_points.npz 含个体级中暑病例(居住地精确经纬度 + 年龄/性别/职业/
是否死亡),属敏感个人信息。仓库公开后任何人可直接下载原始 npz,绕过页面上的
精度/聚合处理 → 个人可被定位。本脚本对**精确定位点**做圆盘内随机抖动(默认 R≈300m):
- 个人无法被精确定位;
- 街道级 choropleth 用的是预存 `jd`(建库时按原始坐标归街道),不受抖动影响;
- 热力图/病例点的空间格局(街区尺度)基本保留。

设计(幂等 + 防误伤):
- 唯一真源 = 精确原始备份 heatcase_points_precise.local.npz(已 gitignore,只在本机)。
  首次运行时,若该备份不存在且当前 npz 是精确版(无 anonymized 标记),则先备份。
- 每次都从精确备份重新抖动 → 覆盖 heatcase_points.npz,并写入 anonymized=1 标记。
- 固定随机种子 → 可复现。
- 若当前 npz 已带 anonymized 标记且无精确备份,则拒绝运行(避免把脱敏版当真源)。

用法(venv,只在持有精确原始数据的本机跑一次,产物提交进仓库):
  .venv/Scripts/python.exe analysis/anonymize_heatcase.py
"""
import os

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_DIR)
NPZ = os.path.join(ROOT, "heatcase_points.npz")
PRECISE_BAK = os.path.join(ROOT, "heatcase_points_precise.local.npz")  # gitignore

JITTER_M = 300.0   # 抖动半径(米):圆盘内均匀;精确点位移 0–300m
SEED = 20260610    # 固定种子,可复现


def _load(path):
    d = np.load(path, allow_pickle=True)
    return {k: d[k] for k in d.files}


def _save(path, s):
    np.savez_compressed(path, **s)


def _jitter(lon, lat, mask, rng, radius_m):
    """对 mask 为 True 的点做圆盘内(半径 radius_m)均匀随机位移。原地返回新数组。"""
    lon = lon.astype(np.float64).copy()
    lat = lat.astype(np.float64).copy()
    idx = np.where(mask & np.isfinite(lon) & np.isfinite(lat))[0]
    n = len(idx)
    if n == 0:
        return lon.astype(np.float32), lat.astype(np.float32)
    r = radius_m * np.sqrt(rng.random(n))         # 圆盘内均匀 → r ∝ sqrt(u)
    th = 2.0 * np.pi * rng.random(n)
    dnorth = r * np.cos(th)                        # 米
    deast = r * np.sin(th)
    dlat = dnorth / 111320.0
    dlon = deast / (111320.0 * np.cos(np.radians(lat[idx])))
    lat[idx] += dlat
    lon[idx] += dlon
    return lon.astype(np.float32), lat.astype(np.float32)


def main():
    cur = _load(NPZ)
    already = "anonymized" in cur and int(np.ravel(cur["anonymized"])[0]) == 1

    # —— 确定精确真源 ——
    if os.path.exists(PRECISE_BAK):
        src = _load(PRECISE_BAK)
        print(f"▶ 使用已有精确备份:{os.path.basename(PRECISE_BAK)}")
    else:
        if already:
            raise SystemExit(
                "✗ 当前 heatcase_points.npz 已是脱敏版,且找不到精确备份 "
                f"{os.path.basename(PRECISE_BAK)}。\n"
                "  本机没有精确真源,无法脱敏。请在持有原始数据的机器上运行,"
                "或先用 analysis/build_heatcase_data.py 从 xlsx 重建精确 npz。")
        src = cur
        _save(PRECISE_BAK, src)
        print(f"▶ 首次运行:已把当前精确 npz 备份为 {os.path.basename(PRECISE_BAK)}(本机保留,勿提交)")

    rng = np.random.default_rng(SEED)
    out = {k: v for k, v in src.items()}

    # 现住地精确点 + 中暑发生地精确点,各自抖动
    n_home = int((src["precise"] == 1).sum())
    n_onset = int((src["oprecise"] == 1).sum())
    out["lon"], out["lat"] = _jitter(src["lon"], src["lat"], src["precise"] == 1, rng, JITTER_M)
    out["olon"], out["olat"] = _jitter(src["olon"], src["olat"], src["oprecise"] == 1, rng, JITTER_M)
    out["anonymized"] = np.array([1], np.int8)

    _save(NPZ, out)
    sz = os.path.getsize(NPZ) / 1e6
    print(f"  ✓ 已抖动现住精确点 {n_home:,} + 发生地精确点 {n_onset:,}(R≈{JITTER_M:.0f}m 圆盘内均匀)")
    print(f"  ✓ 写出脱敏版 {os.path.basename(NPZ)}({sz:.2f} MB,带 anonymized 标记)")
    print(f"  · 街道 choropleth 用预存 jd,不受影响;粗定位点(街镇/区县中心)未动。")
    print(f"\n✅ 完成。提交此 {os.path.basename(NPZ)};精确版仅留本机 {os.path.basename(PRECISE_BAK)}。")
    print("   残留提示:坐标已不可精确定位,但年龄/职业/死亡/日期等属性仍在;"
          "若对外公开发布,建议进一步做 k-匿名或粗化属性。")


if __name__ == "__main__":
    main()
