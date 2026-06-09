# -*- coding: utf-8 -*-
"""坐标变换(WGS84 ↔ GCJ-02)与 folium 地图/栅格渲染工具。

纯绘图/几何工具,不含页面逻辑;被各 views 页面共享。
"""
import math

import numpy as np
import folium
from folium.plugins import Draw


# 100m 网格在经纬度下的半格尺寸(用于绘制网格方块)
HALF_LON, HALF_LAT = 0.00053, 0.00045


# ---- WGS84 -> GCJ-02(火星坐标)转换:高德/国内卫星瓦片为 GCJ-02,需转换叠加层才对齐 ----
_GCJ_A = 6378245.0
_GCJ_EE = 0.00669342162296594323


def _gcj_tf_lat(x, y):
    r = (-100 + 2*x + 3*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
         + (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi)) * 2/3
         + (20*math.sin(y*math.pi) + 40*math.sin(y/3*math.pi)) * 2/3
         + (160*math.sin(y/12*math.pi) + 320*math.sin(y*math.pi/30)) * 2/3)
    return r


def _gcj_tf_lng(x, y):
    r = (300 + x + 2*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
         + (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi)) * 2/3
         + (20*math.sin(x*math.pi) + 40*math.sin(x/3*math.pi)) * 2/3
         + (150*math.sin(x/12*math.pi) + 300*math.sin(x/30*math.pi)) * 2/3)
    return r


def wgs2gcj(lng, lat):
    """WGS84 经纬度 -> GCJ-02。中国境外原样返回。"""
    if not (73.66 < lng < 135.05 and 3.86 < lat < 53.55):
        return lng, lat
    dlat = _gcj_tf_lat(lng - 105.0, lat - 35.0)
    dlng = _gcj_tf_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat); magic = 1 - _GCJ_EE * magic * magic
    sm = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_GCJ_A * (1 - _GCJ_EE)) / (magic * sm) * math.pi)
    dlng = (dlng * 180.0) / (_GCJ_A / sm * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


def gcj2wgs(lng, lat):
    """GCJ-02 -> WGS84(镜像近似,误差 <5m,足够 100m 网格用)。"""
    glng, glat = wgs2gcj(lng, lat)
    return lng * 2 - glng, lat * 2 - glat


def _identity(lng, lat):
    return lng, lat


# ---- BD09(百度坐标)↔ WGS84:百度 API 用 BD09,需与 WGS84 LST 网格对齐 ----
_X_PI = math.pi * 3000.0 / 180.0


def bd09_to_gcj02(lng, lat):
    x = lng - 0.0065; y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * _X_PI)
    return z * math.cos(theta), z * math.sin(theta)


def gcj02_to_bd09(lng, lat):
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * _X_PI)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * _X_PI)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd09_to_wgs(lng, lat):
    """BD09 -> WGS84(经 GCJ-02 中转)。"""
    g_lng, g_lat = bd09_to_gcj02(lng, lat)
    return gcj2wgs(g_lng, g_lat)


def wgs_to_bd09(lng, lat):
    """WGS84 -> BD09(经 GCJ-02 中转)。"""
    g_lng, g_lat = wgs2gcj(lng, lat)
    return gcj02_to_bd09(g_lng, g_lat)


def _lerp_hex(c1, c2, t):
    a = tuple(int(c1[i:i+2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i+2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % tuple(int(a[i] + (b[i]-a[i]) * t) for i in range(3))


def dlst_color(d, vmax):
    """ΔLST 配色:降温=由浅到深的青蓝,升温=由浅到深的橙红。"""
    t = min(abs(d) / vmax, 1.0) if vmax > 0 else 0.0
    if d <= 0:
        return _lerp_hex("#E8F6FF", "#0B5394", t)   # 蓝:降温
    return _lerp_hex("#FFF0E6", "#B22222", t)        # 红:升温


def add_dlst_grid(m, field, tx=_identity):
    """把逐格 ΔLST 场以彩色 100m 方块叠加到地图(含空间外溢)。tx 为坐标变换。"""
    if not field or field.get("n_cells", 0) == 0:
        return
    dl = field["dlst"]; vmax = max(abs(min(dl)), abs(max(dl)), 0.5)
    for lat_c, lon_c, d in zip(field["lat"], field["lon"], dl):
        col = dlst_color(d, vmax)
        lo1, la1 = tx(lon_c - HALF_LON, lat_c - HALF_LAT)
        lo2, la2 = tx(lon_c + HALF_LON, lat_c + HALF_LAT)
        folium.Rectangle(
            bounds=[[la1, lo1], [la2, lo2]],
            color=col, weight=0, fill=True, fill_color=col, fill_opacity=0.72,
            tooltip=f"ΔLST {d:+.1f} °C",
        ).add_to(m)


def add_dlst_raster(m, field, upscale=8, tx=_identity):
    """把 ΔLST 场渲染成平滑高分辨率栅格(PIL 上采样 + ImageOverlay),
    分辨率与绿地大小在图上自然匹配,不受 100m 方块限制。"""
    import io, base64
    from scipy.ndimage import zoom
    from PIL import Image
    f2 = field.get("field2d") if field else None
    if not f2:
        return
    D = f2["d"]; lat2 = f2["lat"]; lon2 = f2["lon"]
    mask = np.isfinite(D)
    if mask.sum() == 0:
        return
    D0 = np.where(mask, D, 0.0).astype(float)
    Dz = zoom(D0, upscale, order=1)
    Mz = zoom(mask.astype(float), upscale, order=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        Dz = np.where(Mz > 0.05, Dz / np.maximum(Mz, 1e-6), 0.0)
    vmax = max(abs(float(np.nanmin(D))), abs(float(np.nanmax(D))), 0.5)
    t = np.clip(np.abs(Dz) / vmax, 0, 1)[..., None]
    cool = (Dz <= 0)[..., None]

    def ramp(c0, c1):
        a = np.array([int(c0[i:i+2], 16) for i in (1, 3, 5)], float)
        b = np.array([int(c1[i:i+2], 16) for i in (1, 3, 5)], float)
        return a + (b - a) * t
    rgb = np.where(cool, ramp("#E8F6FF", "#0B5394"), ramp("#FFF0E6", "#B22222"))
    alpha = (np.clip(Mz, 0, 1) * 205)[..., None]
    rgba = np.concatenate([rgb, alpha], axis=2).astype(np.uint8)
    buf = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    sw = tx(float(lon2.min()) - HALF_LON, float(lat2.min()) - HALF_LAT)
    ne = tx(float(lon2.max()) + HALF_LON, float(lat2.max()) + HALF_LAT)
    bounds = [[sw[1], sw[0]], [ne[1], ne[0]]]
    folium.raster_layers.ImageOverlay(image=uri, bounds=bounds, opacity=0.8).add_to(m)


def _add_basemap(m, basemap):
    """加专业底图。卫星影像(高德, GCJ-02)/ 街道地图(CartoDB Voyager)/ 浅色(Positron)。"""
    if basemap == "卫星影像":
        # 高德卫星(国内可达, GCJ-02 坐标系;叠加层已做 WGS84->GCJ 变换对齐)
        folium.TileLayer(
            "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
            attr="高德地图 AutoNavi", name="卫星影像", control=False,
            subdomains="1234", max_zoom=18).add_to(m)
        # 高德路网+地名注记(同为 GCJ-02)
        folium.TileLayer(
            "https://webst0{s}.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}",
            attr="高德地图 AutoNavi", name="路网注记", overlay=True, control=False,
            subdomains="1234", max_zoom=18).add_to(m)
    elif basemap == "街道地图":
        folium.TileLayer(
            "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
            attr="© OpenStreetMap contributors © CARTO", name="街道地图",
            control=False, max_zoom=20).add_to(m)
    else:  # 浅色
        folium.TileLayer("CartoDB positron", control=False).add_to(m)


def add_drisk_grid(m, lats, lons, drisk):
    """把逐格 Δ重症风险以彩色方块叠加(蓝=风险下降/红=上升)。"""
    if len(drisk) == 0:
        return
    vmax = max(float(np.max(np.abs(drisk))), 0.01)
    for la, lo, d in zip(lats, lons, drisk):
        col = dlst_color(float(d), vmax)   # 负→蓝, 正→红
        folium.Rectangle(bounds=[[la-HALF_LAT, lo-HALF_LON], [la+HALF_LAT, lo+HALF_LON]],
                         color=col, weight=0, fill=True, fill_color=col, fill_opacity=0.75,
                         tooltip=f"Δ重症风险 {d:+.3f}").add_to(m)


# 上海市大致外包矩形 (lng_min, lat_min, lng_max, lat_max),用于挡掉范围外绘制
SHANGHAI_BBOX = (120.85, 30.67, 122.05, 31.90)


def polygon_area_ha(poly_latlng):
    """用等积平面近似计算多边形面积(公顷)。poly_latlng: [[lat, lng], ...]。"""
    if len(poly_latlng) < 3:
        return 0.0
    lat0 = sum(p[0] for p in poly_latlng) / len(poly_latlng)
    m_lat = 111320.0
    m_lng = 111320.0 * math.cos(math.radians(lat0))
    pts = [(lng * m_lng, lat * m_lat) for lat, lng in poly_latlng]
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0 / 10000.0  # m² → 公顷


def in_shanghai(lng, lat):
    a, b, c, d = SHANGHAI_BBOX
    return a <= lng <= c and b <= lat <= d


def build_draw_map(basemap="卫星影像"):
    """带绘制工具的上海地图(专业底图),只允许画多边形/矩形。
    卫星底图为 GCJ-02,地图中心也转到 GCJ;返回的绘制坐标在 render 处再转回 WGS84。"""
    if basemap == "卫星影像":
        clng, clat = wgs2gcj(121.47, 31.23)
    else:
        clng, clat = 121.47, 31.23
    m = folium.Map(location=[clat, clng], zoom_start=11, tiles=None, control_scale=True)
    _add_basemap(m, basemap)
    Draw(
        draw_options={
            "polyline": False, "circle": False, "marker": False,
            "circlemarker": False, "rectangle": True, "polygon": True,
        },
        edit_options={"edit": False},
        export=False,
    ).add_to(m)
    return m
