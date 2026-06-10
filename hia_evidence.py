# -*- coding: utf-8 -*-
"""
hia_evidence.py
HIA 机制路径支撑证据卡片（WHO 官方来源）

字段说明：
  keys    : 该"决定因素 → 健康结果"机制链的中文关键词
  q       : 初筛题号（Q1~Q10）
  note    : 支撑要点（概括，非 WHO 原文逐字摘录；逐字结论请打开 URL 自取）
  sources : ["标题(年份). WHO. URL", ...]，同一来源可被多条路径复用
  status  : "done" = WHO 官网已取证；"todo" = WHO 官网确无/待核实，转系统综述/meta 补

注：所有 URL 均经实际打开核实域名(who.int / iris.who.int)、年份与主题。

app 接口（被 hia_screen.py / views 调用）：match(pathway) / annotate(pathways) / gaps(pathways)。
匹配按"题号一致 + 关键词双向命中因果链"；status='todo' 的卡片仍挂来源,显示端标"待补强"。
"""

CARDS = [
    # ===================== Q1 传染病与感染性疾病 =====================
    {
        "keys": ["饮用水水质", "供水安全", "介水传染病"],
        "q": "Q1",
        "note": "以 60 余年证据为基础，确立基于健康的目标、流域到龙头水安全计划与独立监测，"
                "作为各国水质标准的权威依据，核心目标是控制介水病原体风险。",
        "sources": [
            "Guidelines for drinking-water quality: 4th edition incorporating the 1st and 2nd addenda (2022). WHO. https://www.who.int/publications/i/item/9789240045064",
        ],
        "status": "done",
    },
    {
        "keys": ["环境卫生", "卫生设施", "污水处理不足", "粪口途径传染病"],
        "q": "Q1",
        "note": "安全环境卫生对预防感染至关重要；指南汇总卫生设施与健康（含粪口途径传染病）"
                "的证据并给出循证建议。",
        "sources": [
            "Guidelines on sanitation and health (2018). WHO. https://www.who.int/publications/i/item/9789241514705",
            "Sanitation (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/sanitation",
        ],
        "status": "done",
    },
    {
        "keys": ["人口聚集", "居住拥挤", "呼吸道传染病传播"],
        "q": "Q1",
        "note": "住房与健康指南专门评估居住拥挤的健康风险（含呼吸道传染病传播）并给出针对拥挤的建议。",
        "sources": [
            "WHO Housing and health guidelines (2018). WHO. https://www.who.int/publications/i/item/9789241550376",
        ],
        "status": "done",
    },
    {
        "keys": ["病媒孳生", "积水", "绿化与水体管理", "媒介传播疾病", "登革热"],
        "q": "Q1",
        "note": "提出强化病媒控制以降低登革热等媒介传播疾病负担的全球对策框架。",
        "sources": [
            "Global vector control response 2017–2030. WHO. https://www.who.int/publications/i/item/9789241512978",
            "Vector-borne diseases (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/vector-borne-diseases",
        ],
        "status": "done",
    },
    {
        "keys": ["食品安全不足", "食源性感染"],
        "q": "Q1",
        "note": "首次全球估计食源性疾病负担，量化不安全食品导致的感染与死亡。",
        "sources": [
            "WHO estimates of the global burden of foodborne diseases: FERG 2007–2015 (2015). WHO. https://www.who.int/publications/i/item/9789241565165",
            "Food safety (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/food-safety",
        ],
        "status": "done",
    },
    {
        "keys": ["人员流动", "交通枢纽", "传染病输入与扩散"],
        "q": "Q1",
        "note": "IHR 为防止疾病跨境输入与扩散提供国际法律框架与口岸/旅行公共卫生措施。",
        "sources": [
            "International Health Regulations (IHR) (health topic). WHO. https://www.who.int/health-topics/international-health-regulations",
        ],
        "status": "done",
    },
    {
        "keys": ["医疗废物", "危险废物处置不当", "感染风险"],
        "q": "Q1",
        "note": "医疗废物管理不当会带来感染等健康风险，需安全处置。",
        "sources": [
            "Health-care waste (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/health-care-waste",
        ],
        "status": "done",
    },

    # ===================== Q2 重点慢性病 =====================
    {
        "keys": ["空气污染", "PM2.5", "NO2", "心血管与呼吸系统疾病", "过早死亡"],
        "q": "Q2",
        "note": "更低浓度即可见健康损害；空气污染被认定为缺血性心脏病、卒中、COPD、哮喘、癌症等"
                "的危险因素，每年造成数百万死亡。",
        "sources": [
            "WHO global air quality guidelines: PM, O3, NO2, SO2 and CO (2021). WHO. https://www.who.int/publications/i/item/9789240034228",
            "Ambient (outdoor) air quality and health (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/ambient-(outdoor)-air-quality-and-health",
        ],
        "status": "done",
    },
    {
        "keys": ["家用固体燃料", "替代燃料燃烧", "室内空气污染", "呼吸系统疾病"],
        "q": "Q2",
        "note": "家用燃料燃烧导致室内空气污染并损害呼吸系统健康，提出排放与燃料相关建议。",
        "sources": [
            "WHO guidelines for indoor air quality: household fuel combustion (2014). WHO. https://www.who.int/publications/i/item/9789241548885",
        ],
        "status": "done",
    },
    {
        "keys": ["环境噪声", "高血压", "心血管疾病"],
        "q": "Q2",
        "note": "环境噪声对健康有负面影响（含心血管效应），给出各类噪声源的暴露限值建议。",
        "sources": [
            "Environmental noise guidelines for the European Region (2018). WHO Regional Office for Europe. https://www.who.int/europe/publications/i/item/9789289053563",
        ],
        "status": "done",
    },
    {
        "keys": ["高温", "城市热岛", "热相关疾病", "过早死亡"],
        "q": "Q2",
        "note": "高温暴露加重心血管等疾病并增加过早死亡，需热健康行动计划应对。",
        "sources": [
            "Heat and health (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health",
        ],
        "status": "done",
    },
    {
        "keys": ["取暖不足", "室内低温", "能源贫困", "心血管与呼吸系统疾病"],
        "q": "Q2",
        "note": "指南就室内最低温度提出建议，指出室内低温与心血管/呼吸系统疾病风险相关。",
        "sources": [
            "WHO Housing and health guidelines (2018). WHO. https://www.who.int/publications/i/item/9789241550376",
        ],
        "status": "done",
    },
    {
        "keys": ["体力活动不足", "步行性", "绿地可达", "心血管", "糖尿病", "肥胖"],
        "q": "Q2",
        "note": "身体活动不足与久坐增加心血管病、糖尿病、肥胖等风险，给出各人群活动量建议。",
        "sources": [
            "WHO guidelines on physical activity and sedentary behaviour (2020). WHO. https://www.who.int/publications/i/item/9789240015128",
        ],
        "status": "done",
    },
    {
        "keys": ["城市绿地可达", "体力活动", "减压", "慢病改善", "健康效益"],
        "q": "Q2",
        "note": "城市绿地通过促进体力活动、减压等带来健康效益，可改善慢性病结局。",
        "sources": [
            "Urban green spaces: a brief for action (2017). WHO Regional Office for Europe. https://www.who.int/europe/publications/i/item/9789289052498",
        ],
        "status": "done",
    },
    {
        "keys": ["膳食", "食物环境", "营养不足", "重点慢性病"],
        "q": "Q2",
        "note": "系统评估膳食与营养因素对主要慢性病的影响，并提出人群层面预防建议。",
        "sources": [
            "Diet, nutrition and the prevention of chronic diseases: report of a joint WHO/FAO expert consultation (TRS 916, 2003). WHO. https://www.who.int/publications/i/item/924120916X",
        ],
        "status": "done",
    },
    {
        "keys": ["住房潮湿", "霉变", "哮喘", "呼吸系统疾病"],
        "q": "Q2",
        "note": "室内潮湿与霉菌与哮喘等呼吸系统疾病相关，建议控制潮湿与霉菌暴露。",
        "sources": [
            "WHO guidelines for indoor air quality: dampness and mould (2009). WHO Regional Office for Europe. https://www.who.int/europe/publications/i/item/9789289041683",
        ],
        "status": "done",
    },
    {
        "keys": ["烟草", "酒精可得性环境", "慢性病"],
        "q": "Q2",
        "note": "烟草、有害饮酒是慢性病主要可改变危险因素，FCTC 与控酒战略提出环境/政策层面干预。",
        "sources": [
            "Tobacco (health topic, 含 WHO FCTC 入口). WHO. https://www.who.int/health-topics/tobacco",
            "Alcohol (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/alcohol",
        ],
        "status": "todo",  # TODO: FCTC 正式条约文本专属稳定 URL（fctc.who.int / IRIS）待单独核实
    },

    # ===================== Q3 中毒与伤害 =====================
    {
        "keys": ["道路交通", "重型货运", "交通伤害", "交通死亡"],
        "q": "Q3",
        "note": "全球道路交通伤害负担与风险因素的权威统计与对策。",
        "sources": [
            "Global status report on road safety 2018. WHO. https://www.who.int/publications/i/item/9789241565684",
        ],
        "status": "done",
    },
    {
        "keys": ["危险化学品暴露", "泄漏", "急性中毒", "伤害"],
        "q": "Q3",
        "note": "化学品暴露可致急性中毒与伤害，WHO/IPCS 提供风险评估与管理框架。",
        "sources": [
            "Chemical safety (health topic, IPCS). WHO. https://www.who.int/health-topics/chemical-safety",
        ],
        "status": "done",
    },
    {
        "keys": ["职业暴露", "工作环境暴露", "职业中毒", "工伤"],
        "q": "Q3",
        "note": "量化职业暴露导致的疾病与工伤负担。",
        "sources": [
            "WHO/ILO joint estimates of the work-related burden of disease and injury, 2000–2016 (2021). WHO. https://www.who.int/publications/i/item/9789240034945",
        ],
        "status": "done",
    },
    {
        "keys": ["室内燃烧", "通风不足", "一氧化碳中毒"],
        "q": "Q3",
        "note": "家用燃料不完全燃烧/通风不足产生 CO 等污染物，构成室内空气健康风险。",
        "sources": [
            "WHO guidelines for indoor air quality: household fuel combustion (2014). WHO. https://www.who.int/publications/i/item/9789241548885",
        ],
        "status": "done",
    },
    {
        "keys": ["农药", "化学品可及", "中毒", "自伤"],
        "q": "Q3",
        "note": "限制高危农药等手段可得性是有效的自杀/中毒预防措施。",
        "sources": [
            "Suicide (fact sheet, 含限制手段可得性). WHO. https://www.who.int/news-room/fact-sheets/detail/suicide",
            "Chemical safety (health topic). WHO. https://www.who.int/health-topics/chemical-safety",
        ],
        "status": "done",
    },
    {
        "keys": ["公共空间", "道路设计", "适老化不足", "跌倒", "伤害"],
        "q": "Q3",
        "note": "跌倒是重要伤害原因，环境与适老化设计是关键可改变因素。",
        "sources": [
            "Falls (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/falls",
            "Age-friendly environments (team page). WHO. https://www.who.int/teams/social-determinants-of-health/demographic-change-and-healthy-ageing/age-friendly-environments",
        ],
        "status": "done",
    },

    # ===================== Q4 其他突发公共卫生事件 =====================
    {
        "keys": ["危化品事故", "泄漏", "群体急性暴露事件"],
        "q": "Q4",
        "note": "WHO/IPCS 提供化学事件公共卫生准备与应对框架。",
        "sources": [
            "Chemical safety (health topic, IPCS). WHO. https://www.who.int/health-topics/chemical-safety",
        ],
        "status": "done",
    },
    {
        "keys": ["食品安全事件", "食源性疾病暴发"],
        "q": "Q4",
        "note": "不安全食品可引发食源性疾病暴发，需食品安全体系防控。",
        "sources": [
            "Food safety (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/food-safety",
        ],
        "status": "done",
    },
    {
        "keys": ["饮用水污染事件", "介水疾病暴发"],
        "q": "Q4",
        "note": "水安全计划通过逐步风险管理预防饮用水污染导致的介水疾病暴发。",
        "sources": [
            "Water safety plan manual (WSP manual, 1st ed.). WHO. https://www.who.int/publications/i/item/9789241562638",
        ],
        "status": "done",
    },
    {
        "keys": ["极端高温", "气候事件", "群体性健康事件"],
        "q": "Q4",
        "note": "极端高温可造成群体性超额发病与死亡，需热健康预警系统。",
        "sources": [
            "Heat and health (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health",
        ],
        "status": "done",
    },
    {
        "keys": ["大型人群聚集", "突发公共卫生风险"],
        "q": "Q4",
        "note": "大型集会带来传染病及环境健康等多重公共卫生风险，需专门规划与准备。",
        "sources": [
            "Public health for mass gatherings: key considerations (2015). WHO. https://www.who.int/publications/i/item/public-health-for-mass-gatherings-key-considerations",
        ],
        "status": "done",
    },

    # ===================== Q5 人口高质量发展 =====================
    {
        "keys": ["空气暴露", "化学品暴露", "不良出生结局", "生殖健康"],
        "q": "Q5",
        "note": "空气污染与不良出生结局及儿童健康损害相关。",
        "sources": [
            "Air pollution and child health: prescribing clean air (2018). WHO. https://www.who.int/publications/i/item/air-pollution-and-child-health",
        ],
        "status": "done",
    },
    {
        "keys": ["环境条件", "居住条件", "儿童早期发展", "儿童健康"],
        "q": "Q5",
        "note": "环境与居住条件影响儿童早期发展与健康。",
        "sources": [
            "Children's environmental health (health topic). WHO. https://www.who.int/health-topics/children-environmental-health",
        ],
        "status": "done",
    },
    {
        "keys": ["教育", "社会决定因素", "长期健康", "健康素养"],
        "q": "Q5",
        "note": "教育等社会决定因素塑造健康差异与长期健康结局。",
        "sources": [
            "Closing the gap in a generation: health equity through action on the social determinants of health — CSDH final report (2008). WHO. https://www.who.int/publications/i/item/WHO-IER-CSDH-08.1",
        ],
        "status": "done",
    },
    {
        "keys": ["就业", "收入", "社会经济地位", "人口健康", "健康公平"],
        "q": "Q5",
        "note": "就业与收入等社会经济条件是人群健康与健康公平的根本决定因素。",
        "sources": [
            "Closing the gap in a generation — CSDH final report (2008). WHO. https://www.who.int/publications/i/item/WHO-IER-CSDH-08.1",
            "Health equity (health topic). WHO. https://www.who.int/health-topics/health-equity",
        ],
        "status": "done",
    },
    {
        "keys": ["适老环境", "适老设施", "老年健康", "健康老龄化"],
        "q": "Q5",
        "note": "适老环境与设施支持健康老龄化和老年功能发挥。",
        "sources": [
            "Ageing and health (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/ageing-and-health",
            "Age-friendly environments (team page). WHO. https://www.who.int/teams/social-determinants-of-health/demographic-change-and-healthy-ageing/age-friendly-environments",
        ],
        "status": "done",
    },

    # ===================== Q6 健康环境 =====================
    {
        "keys": ["大气质量改变", "环境健康"],
        "q": "Q6",
        "note": "空气质量改变直接影响环境健康，2021 版指南给出污染物暴露限值。",
        "sources": [
            "WHO global air quality guidelines (2021). WHO. https://www.who.int/publications/i/item/9789240034228",
        ],
        "status": "done",
    },
    {
        "keys": ["饮用水水质", "环境健康"],
        "q": "Q6",
        "note": "饮用水水质是环境健康核心要素，指南提供水质安全管理框架。",
        "sources": [
            "Guidelines for drinking-water quality (2022). WHO. https://www.who.int/publications/i/item/9789240045064",
        ],
        "status": "done",
    },
    {
        "keys": ["食品安全", "环境健康"],
        "q": "Q6",
        "note": "食品安全是环境健康组成部分，不安全食品造成可观疾病负担。",
        "sources": [
            "Food safety (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/food-safety",
        ],
        "status": "done",
    },
    {
        "keys": ["环境噪声", "环境健康", "生活质量"],
        "q": "Q6",
        "note": "环境噪声影响健康与生活质量，给出各噪声源暴露限值建议。",
        "sources": [
            "Environmental noise guidelines for the European Region (2018). WHO Regional Office for Europe. https://www.who.int/europe/publications/i/item/9789289053563",
        ],
        "status": "done",
    },
    {
        "keys": ["土壤污染", "重金属污染", "铅暴露", "环境健康"],
        "q": "Q6",
        "note": "铅等重金属暴露无安全阈值，损害神经发育等健康；化学品安全提供管理框架。",
        "sources": [
            "Lead poisoning (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/lead-poisoning-and-health",
            "Chemical safety (health topic). WHO. https://www.who.int/health-topics/chemical-safety",
        ],
        "status": "done",
    },
    {
        "keys": ["固体废物", "危废处置", "环境卫生"],
        "q": "Q6",
        "note": "危险/医疗废物处置不当带来环境与健康风险；城市生活固废与健康 WHO 无独立旗舰文档。",
        "sources": [
            "Health-care waste (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/health-care-waste",
        ],
        "status": "todo",  # TODO: 城市生活固废与健康 WHO 官网无独立文档，待系统综述/meta 补
    },

    # ===================== Q7 健康生活方式与社会心理健康 =====================
    {
        "keys": ["绿地", "开放空间", "体力活动", "减压", "心理健康"],
        "q": "Q7",
        "note": "城市绿地通过促进体力活动与减压改善身心健康。",
        "sources": [
            "Urban green spaces: a brief for action (2017). WHO Regional Office for Europe. https://www.who.int/europe/publications/i/item/9789289052498",
        ],
        "status": "done",
    },
    {
        "keys": ["步行性", "街道设计", "公共空间设计", "主动出行", "活动方式"],
        "q": "Q7",
        "note": "支持步行/骑行的环境与设计促进主动出行和身体活动。",
        "sources": [
            "WHO guidelines on physical activity and sedentary behaviour (2020). WHO. https://www.who.int/publications/i/item/9789240015128",
        ],
        "status": "done",
    },
    {
        "keys": ["环境噪声", "睡眠干扰", "烦扰", "心理健康", "主观健康"],
        "q": "Q7",
        "note": "环境噪声导致睡眠干扰与烦扰，影响心理与主观健康。",
        "sources": [
            "Environmental noise guidelines for the European Region (2018). WHO Regional Office for Europe. https://www.who.int/europe/publications/i/item/9789289053563",
        ],
        "status": "done",
    },
    {
        "keys": ["社会隔离", "社区凝聚力下降", "心理健康", "幸福感"],
        "q": "Q7",
        "note": "社会因素影响心理健康；CSDH 可部分支撑，WHO 较新 Social connection 委员会报告待核实。",
        "sources": [
            "Closing the gap in a generation — CSDH final report (2008). WHO. https://www.who.int/publications/i/item/WHO-IER-CSDH-08.1",
        ],
        "status": "todo",  # TODO: 核实 WHO 'Social isolation and loneliness / Social connection' 主题页稳定 URL（知识截止后发布）
    },
    {
        "keys": ["拆迁", "人口置换", "社区网络破坏", "心理压力"],
        "q": "Q7",
        "note": "居住环境变动与社区网络破坏构成心理压力源；住房与健康、SDH 提供证据基础。",
        "sources": [
            "WHO Housing and health guidelines (2018). WHO. https://www.who.int/publications/i/item/9789241550376",
            "Closing the gap in a generation — CSDH final report (2008). WHO. https://www.who.int/publications/i/item/WHO-IER-CSDH-08.1",
        ],
        "status": "done",
    },
    {
        "keys": ["经济困难", "可负担性下降", "心理压力", "行为风险"],
        "q": "Q7",
        "note": "经济困难与可负担性下降是心理压力与不良行为风险的社会决定因素。",
        "sources": [
            "Closing the gap in a generation — CSDH final report (2008). WHO. https://www.who.int/publications/i/item/WHO-IER-CSDH-08.1",
        ],
        "status": "done",
    },

    # ===================== Q8 卫生健康投入保障与医疗保险 =====================
    {
        "keys": ["卫生筹资", "投入安排", "公共卫生服务能力", "医疗服务能力"],
        "q": "Q8",
        "note": "卫生筹资安排决定公共卫生与医疗服务的供给能力。",
        "sources": [
            "Health financing (health topic). WHO. https://www.who.int/health-topics/health-financing",
        ],
        "status": "done",
    },
    {
        "keys": ["自付负担", "保障水平", "因病致贫", "服务利用"],
        "q": "Q8",
        "note": "高自付与低保障导致灾难性卫生支出、因病致贫并抑制服务利用。",
        "sources": [
            "Universal health coverage (UHC) (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/universal-health-coverage-(uhc)",
        ],
        "status": "done",
    },
    {
        "keys": ["经济结构", "就业", "参保能力", "缴费能力"],
        "q": "Q8",
        "note": "经济结构与就业状况影响参保与缴费能力，是 UHC 与健康公平的相关因素。",
        "sources": [
            "Closing the gap in a generation — CSDH final report (2008). WHO. https://www.who.int/publications/i/item/WHO-IER-CSDH-08.1",
            "Universal health coverage (UHC) (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/universal-health-coverage-(uhc)",
        ],
        "status": "done",
    },

    # ===================== Q9 优质医疗资源合理配置与利用 =====================
    {
        "keys": ["设施布局", "规划", "医疗资源地理可达性"],
        "q": "Q9",
        "note": "设施布局与规划决定医疗资源地理可及性，是 UHC 服务可及维度的内容。",
        "sources": [
            "Universal health coverage (UHC) (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/universal-health-coverage-(uhc)",
        ],
        "status": "done",
    },
    {
        "keys": ["区域发展不均", "资源配置公平性"],
        "q": "Q9",
        "note": "区域发展不均带来卫生人力与资源配置的公平性问题。",
        "sources": [
            "Health workforce (health topic). WHO. https://www.who.int/health-topics/health-workforce",
            "Health equity (health topic). WHO. https://www.who.int/health-topics/health-equity",
        ],
        "status": "done",
    },
    {
        "keys": ["急救网络", "转诊网络", "资源利用效率", "时效"],
        "q": "Q9",
        "note": "急诊与院前急救/转诊系统影响资源利用效率与救治时效。",
        "sources": [
            "Emergency care (health topic). WHO. https://www.who.int/health-topics/emergency-care",
        ],
        "status": "done",
    },

    # ===================== Q10 医疗卫生服务质量、利用、公平与可及性 =====================
    {
        "keys": ["设施空间布局", "交通可达", "就医地理可及性"],
        "q": "Q10",
        "note": "设施布局与交通可达性决定就医地理可及性，是 UHC 服务覆盖的核心维度。",
        "sources": [
            "Universal health coverage (UHC) (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/universal-health-coverage-(uhc)",
        ],
        "status": "done",
    },
    {
        "keys": ["经济可负担性", "服务利用", "放弃就医"],
        "q": "Q10",
        "note": "经济可负担性低导致灾难性卫生支出与放弃就医，抑制服务利用。",
        "sources": [
            "Universal health coverage (UHC) (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/universal-health-coverage-(uhc)",
        ],
        "status": "done",
    },
    {
        "keys": ["弱势群体", "健康公平", "服务利用差距"],
        "q": "Q10",
        "note": "弱势群体面临服务利用差距，健康公平与社会决定因素提供分析框架。",
        "sources": [
            "Health equity (health topic). WHO. https://www.who.int/health-topics/health-equity",
            "Closing the gap in a generation — CSDH final report (2008). WHO. https://www.who.int/publications/i/item/WHO-IER-CSDH-08.1",
        ],
        "status": "done",
    },
    {
        "keys": ["急救可达", "反应时间", "救治时效", "结局"],
        "q": "Q10",
        "note": "急诊与院前急救系统的反应时间影响救治时效与健康结局。",
        "sources": [
            "Emergency care (health topic). WHO. https://www.who.int/health-topics/emergency-care",
        ],
        "status": "done",
    },
    {
        "keys": ["服务质量", "患者安全", "健康结果"],
        "q": "Q10",
        "note": "医疗服务质量与患者安全直接影响健康结果。",
        "sources": [
            "Quality health services (fact sheet). WHO. https://www.who.int/news-room/fact-sheets/detail/quality-health-services",
        ],
        "status": "done",
    },
]  # ← CARDS 列表结束


# ----------------------- 辅助函数 -----------------------

def cards_by_q(q):
    """按题号筛选卡片，如 cards_by_q('Q2')。"""
    return [c for c in CARDS if c["q"] == q]


def todo_cards():
    """返回所有 WHO 官网确无/待核实（status='todo'）的卡片。"""
    return [c for c in CARDS if c["status"] == "todo"]


def all_sources():
    """去重后的所有来源 URL 列表（便于核对引用）。"""
    seen, out = set(), []
    for c in CARDS:
        for s in c["sources"]:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


# ----------------------- app 匹配接口 -----------------------

def match(pathway):
    """为一条因果路径匹配证据卡片(同题号 + 关键词双向命中因果链)。最多 2 张。
    返回 [{note, sources, status}, ...];匹配不到 → []（显示端标'待专家补证')。"""
    chain = pathway.get("chain") or []
    det = chain[:-1] if len(chain) > 1 else chain      # 去掉末端健康结果(≈题目),只在决定因素段匹配
    text = " ".join(det)                               # 否则"心血管病"等结果词会误中同题各卡
    nodes = [n for n in det if len(n) >= 2]            # 链节点做反向子串匹配(术语比 key 短时)
    qs = f"Q{pathway.get('outcome_q')}"
    out = []
    for c in CARDS:
        if c["q"] != qs:
            continue
        hit = False
        for k in c["keys"]:
            if k in text:                              # 正向:关键词出现在链里
                hit = True
                break
            for n in nodes:                            # 反向:链节点是关键词子串(术语更短时)
                if n in k:
                    hit = True
                    break
            if hit:
                break
        if hit:
            out.append({"note": c.get("note", ""), "sources": c["sources"],
                        "status": c.get("status", "done")})
        if len(out) >= 2:
            break
    return out


def annotate(pathways):
    """给每条路径加 cards 字段(可能为空 → 显示端标'机制推断·待专家补证')。"""
    for p in pathways:
        p["cards"] = match(p)
    return pathways


def catalog_lines():
    """供 LLM 语义匹配的卡片目录(编号 + 题号 + 决定因素关键词)。"""
    return [f"C{i} [{c['q']}] {'/'.join(c['keys'])}" for i, c in enumerate(CARDS)]


def card_ref(i):
    """按目录编号取卡片的显示信息(note/sources/status),供匹配后挂到路径上。"""
    c = CARDS[i]
    return {"note": c.get("note", ""), "sources": c["sources"],
            "status": c.get("status", "done"), "q": c["q"]}


def gaps(pathways):
    """汇总当前匹配不到证据卡片的(机制链 → 题号)去重清单,供专家批量补卡。
    按"题号 + 终末两级链路"去重(一张卡片大致对应一条终末机制链)。"""
    seen, out = set(), []
    for p in pathways:
        if p.get("cards"):
            continue
        chain, q = p.get("chain") or [], p.get("outcome_q")
        if not chain or not q:
            continue
        sig = (q, "→".join(chain[-2:]))
        if sig in seen:
            continue
        seen.add(sig)
        out.append({"q": q, "chain": list(chain)})
    out.sort(key=lambda g: g["q"])
    return out


if __name__ == "__main__":
    print(f"卡片总数: {len(CARDS)}")
    print(f"已取证(done): {sum(1 for c in CARDS if c['status']=='done')}")
    print(f"待补(todo)  : {sum(1 for c in CARDS if c['status']=='todo')}")
    for c in todo_cards():
        print(f"  [todo] {c['q']} - {'/'.join(c['keys'])}")
