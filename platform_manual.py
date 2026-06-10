# -*- coding: utf-8 -*-
"""平台模块说明书 —— 智能助手的知识底座。

结构化描述平台各功能(用途/适用场景/参数及取值/是否需要地图或百度AK/可预填项/跳转目标),
既喂给 DeepSeek 系统提示(manual_text),也驱动"预填+跳转"动作(MODULES 按 goto 查)。
被 llm_agent.py 与 views/assistant.py 调用。
"""

# 每个模块:
#   key     稳定标识(=页面函数 url_path,用于跳转)
#   dim     所属维度
#   title   导航/页面标题
#   purpose 一句话用途
#   when    适用场景(用户问题命中时推荐它)
#   params  关键参数 [{name, options/range, note}]
#   needs   {"map": None|"draw"|"click"|"view", "baidu": bool}
#   prefill 可由助手预填的 session_state 键(键→含义);跳转前写入
MODULES = [
    {
        "key": "page_heatcase_map", "dim": "健康风险", "title": "中暑风险地图",
        "purpose": "2013–2025 上海中暑病例(5349例)实测空间分布可视化。**纯浏览/筛选功能,不需要在地图上点选**,直接 navigate 即可,所有筛选(年份/严重程度/可视化方式)在功能页内完成。",
        "when": "想看中暑病例分布在哪、哪些街道高发、哪些人群/职业易中暑。直接 navigate 带用户进页面,不要用 need_map。",
        "params": [
            {"name": "年份范围", "range": "2013–2025", "note": "筛选病例年份"},
            {"name": "严重程度", "options": ["全部", "重症", "轻症"], "note": "按中暑诊断筛选"},
            {"name": "定位精度", "options": ["仅精确(1454例)", "全部(5349例)"], "note": "默认仅精确,避免乡镇级地址假热点"},
            {"name": "可视化方式", "options": ["热力图", "病例点", "街道重症比例"], "note": ""},
        ],
        "needs": {"map": "view", "baidu": False}, "prefill": {},
    },
    {
        "key": "page_health_risk", "dim": "健康风险", "title": "热相关重症风险诊断与规划调控",
        "purpose": "局部建成环境(绿地/建筑密度/容积率)改造 → 地表温度变化 → 中暑重症化概率,可对比模拟。",
        "when": "想评估某地块绿地/密度/容积率改造能否降低中暑重症风险、做规划调控 what-if。",
        "params": [
            {"name": "绿地率调整", "range": "提高/降低", "note": "改造后绿地覆盖"},
            {"name": "建筑密度/容积率", "range": "—", "note": "建成环境强度"},
        ],
        "needs": {"map": "view", "baidu": False}, "prefill": {},
    },
    {
        "key": "page_heatroute", "dim": "健康风险", "title": "清凉路径规划",
        "purpose": "给定起终点,规划并对比凉爽出行路线(沿路实测地表温度热暴露 / 绿荫路网)。",
        "when": "想找一条更凉快的步行/骑行/驾车路线、对比不同路线的热暴露。",
        "params": [
            {"name": "规划模式", "options": ["全市·百度路线(热暴露)", "中心城区·绿荫路网(热+绿荫)"], "note": "百度模式需AK"},
            {"name": "出行方式", "options": ["步行", "骑行", "驾车"], "note": ""},
            {"name": "起点/终点", "range": "地图点选或地址搜索", "note": "需在上海范围"},
        ],
        "needs": {"map": "click", "baidu": True},
        "prefill": {"hr_o": "起点(lng,lat)", "hr_d": "终点(lng,lat)"},
    },
    {
        "key": "page_ems_response", "dim": "健康资源", "title": "急救反应时间预测",
        "purpose": "选事发点 → 匹配最近急救站 → 预测到场时间与分级。**用户在对话里点一个点即可直接得到结果**(无需跳转),想看多候选详细路线再进功能页。",
        "when": "想评估某地点的急救可达性、救护车大概多久到。请用 need_map(click)让用户点一个点,结果会在对话里直接算出。",
        "params": [
            {"name": "事发点", "range": "地图点选(上海范围)", "note": "必填"},
        ],
        "needs": {"map": "click", "baidu": True},
        "prefill": {"ems_incident": "事发点(lng,lat)"},
    },
    {
        "key": "page_health_resource", "dim": "健康资源", "title": "急救站布局模拟",
        "purpose": "以中暑重症风险为底图,落站/拖站模拟新增急救站对风险的改善(what-if)。",
        "when": "想试新增急救站放哪里能降低中暑重症风险、看受益面积与覆盖人口(偏热环境)。",
        "params": [
            {"name": "当天地表温度", "range": "滑块", "note": "高温情景"},
            {"name": "显示模式", "options": ["风险水平", "相对基线Δ", "急救站效果"], "note": ""},
            {"name": "落站", "range": "点击地图新增(可拖动)", "note": ""},
        ],
        "needs": {"map": "click", "baidu": False}, "prefill": {},
    },
    {
        "key": "page_facility_layout", "dim": "健康资源", "title": "设施配置优化",
        "purpose": "纳凉设施 / EMS急救设施 的最优新增选址(MCLP 最大覆盖 + 街道公平性),两个选项卡。",
        "when": "想为纳凉点或急救站做'新增几个、放哪里最优'的选址优化、看覆盖率提升与公平性。",
        "params": [
            {"name": "设施类型", "options": ["❄️纳凉设施", "🚑EMS急救设施"], "note": "选项卡"},
            {"name": "覆盖半径(米)", "range": "纳凉300–1000 / EMS500–3000", "note": ""},
            {"name": "需求权重", "options": ["纳凉:健康/人口/温度/均等", "EMS:总人口/老年70+/均等"], "note": ""},
            {"name": "新增数量 K", "range": "1–50", "note": ""},
            {"name": "街道公平性 α", "range": "0–1", "note": "越大越向最弱街道倾斜"},
            {"name": "(EMS)达标ART阈值", "options": ["≤4分", "≤8分", "≤12分"], "note": "由ART定义欠服务"},
        ],
        "needs": {"map": "view", "baidu": False}, "prefill": {},
    },
    {
        "key": "page_bike", "dim": "健康行为", "title": "骑行潜力与建成环境优化",
        "purpose": "圈定范围 → 机器学习预测共享单车骑行量 → 反向优化建成环境杠杆,估算骑行(体力活动)提升潜力。",
        "when": "想评估某片区骑行潜力、看怎么改建成环境(商业POI/容积率/密度/路网)能促进骑行。",
        "params": [
            {"name": "时段", "options": ["工作日", "周末"], "note": ""},
            {"name": "优化模式", "options": ["升至上限(强度)", "重点改造N格", "预算约束(系数)"], "note": ""},
            {"name": "可调杠杆", "options": ["商业POI", "容积率", "建筑密度", "路网密度等"], "note": "正向变量"},
            {"name": "圈定范围", "range": "地图画多边形/矩形", "note": "必需"},
        ],
        "needs": {"map": "draw", "baidu": False},
        "prefill": {"bk_poly": "圈定范围多边形[(lng,lat),...]", "bk_day": "工作日/周末"},
    },
    {
        "key": "render_custom_mode", "dim": "健康影响评估", "title": "绿地规划健康影响评估",
        "purpose": "地图画地块 → 绿地干预(新增/拆除)→ 逐格地表温度变化 + 健康影响评估 + 受影响人口,可导出报告。",
        "when": "想评估某地块新增/拆除绿地的降温效果与健康影响、出一份 HIA 报告。",
        "params": [
            {"name": "地块", "range": "地图绘制多边形/矩形(上海范围)", "note": "必需"},
            {"name": "干预方向", "options": ["新增绿地", "拆除绿地"], "note": ""},
            {"name": "评估期(年)", "range": "1–30", "note": ""},
        ],
        "needs": {"map": "draw", "baidu": False},
        "prefill": {},
    },
    {
        "key": "page_hia_calc", "dim": "健康影响评估", "title": "规划方案 HIA 计算器",
        "purpose": "输入城市 + 现状/规划 5D 指标 → 出行变化 → 暴露差值 → 全因死亡变化(专利方法)。",
        "when": "有规划方案的 5D 指标(密度/混合度/路网/可达性等),想定量算它带来的健康(全因死亡)变化。",
        "params": [
            {"name": "城市", "range": "省份+城市(内置316城死亡率库)", "note": "自动取现状全因死亡率"},
            {"name": "5D指标(现状/规划)", "range": "人口/就业密度、商业容积率、用地混合度、路网密度、四向交叉口、公交可达性、到商店/公交距离", "note": ""},
            {"name": "现状PM2.5", "range": "默认全国均值30,可改", "note": ""},
        ],
        "needs": {"map": None, "baidu": False},
        "prefill": {"hc_prov": "省份", "hc_city": "城市"},
    },
]

_DIM_ORDER = ["健康风险", "健康资源", "健康行为", "健康影响评估"]


def get_module(key):
    for m in MODULES:
        if m["key"] == key:
            return m
    return None


def manual_text():
    """把说明书渲染成中文文本,供系统提示使用。"""
    lines = []
    for dim in _DIM_ORDER:
        lines.append(f"\n【{dim}】")
        for m in MODULES:
            if m["dim"] != dim:
                continue
            tags = []
            nm = m["needs"]["map"]
            if nm in ("draw", "click"):
                tags.append("需在地图" + ("圈选" if nm == "draw" else "点选"))
            if m["needs"]["baidu"]:
                tags.append("需百度AK")
            tag = f"({'、'.join(tags)})" if tags else ""
            lines.append(f"- 〔{m['title']}〕key={m['key']} {tag}")
            lines.append(f"    用途:{m['purpose']}")
            lines.append(f"    适用:{m['when']}")
            ps = "；".join(
                f"{p['name']}[{p.get('options') and '/'.join(p['options']) or p.get('range', '')}]"
                for p in m["params"])
            if ps:
                lines.append(f"    参数:{ps}")
    return "\n".join(lines)


# 选项卡内详细参数过多的模块,助手只引导到页面即可;以上 params 用于解释与推荐。
