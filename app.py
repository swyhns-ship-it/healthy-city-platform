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

pages = {
    "平台首页": [st.Page(page_home, title="首页", icon="🏠", default=True)],
    "智能助手": [st.Page(page_assistant, title="智能助手(对话引导)", icon="🤖")],
    "健康风险": [st.Page(page_heatcase_map, title="中暑风险地图", icon="🗺️"),
             st.Page(page_health_risk, title="热相关重症风险诊断与规划调控", icon="🌡️"),
             st.Page(page_heatroute, title="清凉路径规划", icon="🧭")],
    "健康资源": [st.Page(page_ems_response, title="急救反应时间预测", icon="⏱️"),
             st.Page(page_health_resource, title="急救站布局模拟", icon="🚑"),
             st.Page(page_facility_layout, title="设施配置优化", icon="📍")],
    "健康行为": [st.Page(page_bike, title="骑行潜力与建成环境优化", icon="🚲")],
    "健康影响评估": [st.Page(render_custom_mode, title="绿地规划健康影响评估", icon="🌳"),
                 st.Page(page_hia_calc, title="规划方案 HIA 计算器", icon="🧮"),
                 st.Page(page_hia_screen, title="AI 辅助 HIA", icon="📝")],
    "友情链接": [st.Page(page_friends, title="合作学者工具", icon="🔗")],
    "关于": [st.Page(page_about, title="关于平台", icon="ℹ️")],
}
nav = st.navigation(pages)
# 页面注册表(url_path → Page),供智能助手"预填+跳转"用
st.session_state["_nav_pages"] = {p.url_path: p for grp in pages.values() for p in grp}
nav.run()
