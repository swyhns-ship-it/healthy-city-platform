# -*- coding: utf-8 -*-
"""健康城市规划与智能评估平台 — Streamlit 多页入口。

按研究维度分组导航。页面在 views/、共享样式在 theme.py、地图/坐标工具在 geo.py、
计算引擎为根目录各 *.py(green_lst / heat_risk / cooling_mclp / hia_engine / cases / report_docx)。
详见 CLAUDE.md。
"""
import streamlit as st

st.set_page_config(
    page_title="健康城市规划与智能评估平台",
    page_icon="🌳",
    layout="wide",
)

from theme import inject_css, render_banner
from views.static_pages import page_home, page_behavior, page_about
from views.health_risk import page_health_risk
from views.heatcase_map import page_heatcase_map
from views.heatroute import page_heatroute
from views.health_resource import page_health_resource
from views.ems_response import page_ems_response
from views.cooling import page_facility_layout
from views.bike import page_bike
from views.hia import page_hia_cases, render_custom_mode
from views.hia_calc import page_hia_calc
from views.hia_screen import page_hia_screen
from views.methodology import render_methodology
from views.assistant import page_assistant
from views.friends import page_friends

inject_css()
render_banner()

from auth import require_login
require_login()   # 未通过口令则在此 st.stop();本地无 app_password secret 时不拦

import module_config as mc

# key → 页面函数(标题/图标/分组/顺序见 module_config.PAGES)
_FUNCS = {
    "home": page_home, "assistant": page_assistant, "heatcase": page_heatcase_map,
    "health_risk": page_health_risk, "heatroute": page_heatroute, "ems": page_ems_response,
    "resource": page_health_resource, "facility": page_facility_layout, "bike": page_bike,
    "hia_custom": render_custom_mode, "hia_calc": page_hia_calc, "hia_screen": page_hia_screen,
    "friends": page_friends, "about": page_about,
}

# 按配置过滤:disabled 列表里的板块对访客隐藏(首页等 locked 始终保留)
disabled = mc.load_disabled()
pages = {}
for p in mc.PAGES:
    if not p.get("locked") and p["key"] in disabled:
        continue
    func = _FUNCS.get(p["key"])
    if func is None:
        continue
    pages.setdefault(p["group"], []).append(
        st.Page(func, title=p["title"], icon=p["icon"], default=(p["key"] == "home")))

# 管理面板:带 ?admin 访问一次即在本会话内开启(用会话标志,避免导航后 query 参数丢失);
# 客户从不带 ?admin → 看不到此页。内部再用管理员口令把关。
if "admin" in st.query_params:
    st.session_state["_admin_mode"] = True
if st.session_state.get("_admin_mode"):
    from views.admin import page_admin
    pages["管理"] = [st.Page(page_admin, title="模块管理", icon="⚙️")]

nav = st.navigation(pages)
# 页面注册表(url_path → Page),供智能助手"预填+跳转"用
st.session_state["_nav_pages"] = {p.url_path: p for grp in pages.values() for p in grp}
nav.run()
