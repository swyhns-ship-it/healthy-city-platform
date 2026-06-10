# -*- coding: utf-8 -*-
"""板块可见性配置(单一全局开关)——控制哪些功能页对访客可见。

- 默认全部可见;`module_config.json` 的 disabled 列表里的页面 key 被隐藏。
- 由 views/admin.py 的管理面板在线勾选并写入(管理员口令保护)。
- ⚠ Streamlit 云端文件系统是临时的:面板改动对**当前运行实例即时生效**,实例重启/休眠后
  会恢复为仓库里提交的 module_config.json。要长期固定,请把改后的 json 提交进仓库
  (管理面板提供"导出配置")。

PAGES 仅为元数据(key/组/标题/图标/locked);key→页面函数 的映射在 app.py。
"""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "module_config.json")

# 顺序即导航顺序;key 唯一稳定(改 key 会让已存配置失效)。locked=True 的页不可关闭。
PAGES = [
    {"key": "home",        "group": "平台首页",     "title": "首页", "icon": "🏠", "locked": True},
    {"key": "assistant",   "group": "智能助手",     "title": "智能助手(对话引导)", "icon": "🤖"},
    {"key": "heatcase",    "group": "健康风险",     "title": "中暑风险地图", "icon": "🗺️"},
    {"key": "health_risk", "group": "健康风险",     "title": "热相关重症风险诊断与规划调控", "icon": "🌡️"},
    {"key": "heatroute",   "group": "健康风险",     "title": "清凉路径规划", "icon": "🧭"},
    {"key": "ems",         "group": "健康资源",     "title": "急救反应时间预测", "icon": "⏱️"},
    {"key": "resource",    "group": "健康资源",     "title": "急救站布局模拟", "icon": "🚑"},
    {"key": "facility",    "group": "健康资源",     "title": "设施配置优化", "icon": "📍"},
    {"key": "bike",        "group": "健康行为",     "title": "骑行潜力与建成环境优化", "icon": "🚲"},
    {"key": "hia_custom",  "group": "健康影响评估", "title": "绿地规划健康影响评估", "icon": "🌳"},
    {"key": "hia_calc",    "group": "健康影响评估", "title": "规划方案 HIA 计算器", "icon": "🧮"},
    {"key": "hia_screen",  "group": "健康影响评估", "title": "AI 辅助 HIA", "icon": "📝"},
    {"key": "friends",     "group": "友情链接",     "title": "合作学者工具", "icon": "🔗"},
    {"key": "about",       "group": "关于",         "title": "关于平台", "icon": "ℹ️"},
]

LOCKED = {p["key"] for p in PAGES if p.get("locked")}


def load_disabled():
    """返回被隐藏的页面 key 集合(读不到/出错则视为全部可见)。"""
    try:
        with open(_PATH, encoding="utf-8") as f:
            return set(json.load(f).get("disabled", []))
    except Exception:
        return set()


def save_disabled(keys):
    """写入隐藏列表(锁定页永不写入)。"""
    keys = sorted(k for k in keys if k not in LOCKED)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump({"disabled": keys}, f, ensure_ascii=False, indent=2)


def config_json(keys):
    """供导出的 JSON 文本。"""
    keys = sorted(k for k in keys if k not in LOCKED)
    return json.dumps({"disabled": keys}, ensure_ascii=False, indent=2)
