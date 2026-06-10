# 健康城市智能规划与评估平台 — 项目说明(给 Claude Code)

> 本文件随仓库提交,任何机器克隆后 Claude Code 自动读取,作为跨机器的项目上下文。
> 用户:孙文尧(同济 CAUP · 王兰团队 · 健康城市方向)。Python 熟,前端不熟。中文回复、简明、给可执行下一步。

## 是什么
Streamlit 多页平台:基于上海 100m 实测栅格 + 机器学习,做城市热环境健康影响评估与调控。
已部署 Streamlit Community Cloud(repo: github.com/swyhns-ship-it/healthy-city-platform,main 文件 `app.py`,**Python 3.11**)。
顶部标题「健康城市智能规划与评估平台」。

## 运行
```bash
pip install -r requirements.txt   # 锁定版本;scikit-learn==1.3.2 必须(否则加载不了 model_v2.joblib)
streamlit run app.py              # 或本机用 .\run.ps1
```
**环境(2026-06-10 起):两台机器都用干净的 python.org CPython 3.11**(家里这台已从 Anaconda venv 迁过来,`import ssl` 原生可用,不再需要那套 Anaconda DLL/PATH 折腾)。`run.ps1` 已改**路径自适应(`$PSScriptRoot`)+ ssl 自愈**(若某机器 venv 缺 ssl 会自动探测 Anaconda 补 DLL),两机通用。`requirements.txt` 新增:`pulp==3.1.1`(MCLP 选址;注意 PyPI 无 3.3.2)、`shapely==2.1.2`(运行时缓冲区几何)。`geopandas/rasterio/pyproj/openpyxl/pyshp` 只在 `analysis/` 离线脚本用,**不入 requirements**。PowerShell 跑脚本若被"禁止运行脚本"拦,一次性 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`。

## 密钥 / 运行时配置(**不随 git 同步,每台机器/云端各配一次**)
`.streamlit/secrets.toml`(已 gitignore;云端在 Streamlit Cloud → Settings → Secrets 填同样内容):
```toml
baidu_ak = "你的AK"            # 百度路线/地址搜索
deepseek_api_key = "sk-..."    # 智能助手 + AI辅助HIA
app_password = "..."           # 平台访问口令门(auth.py;未配则不拦)
admin_password = "..."         # 模块管理面板口令(?admin 进入;未配则本地放行——云端务必配)
```
- **百度地图 AK**:凉爽路径规划的「全市·百度路线」模式 + 地址搜索 需要。
  该文件已被 .gitignore(**换机器不会同步,要重配**);云端在 Streamlit Cloud → App → Settings → Secrets 填同样内容。
  AK 须**放开服务端调用**(IP 白名单设 `0.0.0.0/0` 或用 SN 签名),否则云端/服务端调不通。也可在页面密码框临时输入(仅当次会话)。
  「中心城区·绿荫路网」模式 + 地图点选 **不需要 AK**。

## 架构(分层:入口 / 共享层 / 页面 / 引擎,st.navigation 多页,按研究维度分组)
**代码分层**(2026-06 由 1546 行的单体 app.py 拆分):
- `app.py`(~40 行):瘦身入口 —— set_page_config + 注入主题 + banner + st.navigation 注册页面。
- `theme.py`:健康绿主题色常量、全局 CSS(inject_css)、品牌条(render_banner)、统一页头(page_header)、`md_bold()`(HTML 文本里 **→<b>)。
- `auth.py`:访问口令门(require_login)+ 会话级限流(rate_limit)。`module_config.py`:板块可见性/数据打码配置(读写 module_config.json,被 app.py 导航过滤与 admin 面板用)。
- `geo.py`:坐标变换(WGS84↔GCJ-02)+ folium 地图/栅格渲染工具(_add_basemap、dlst/risk 栅格、build_draw_map、面积/范围校验),纯绘图工具、无页面逻辑。
- `views/`:按维度一页(组)一模块 —— static_pages(首页/行为/关于)、assistant、health_risk、heatcase_map、heatroute、health_resource、ems_response、cooling、bike、hia、hia_calc、hia_screen、methodology、friends、admin。页面只做 UI,调用 engines + geo + theme。
- 拆分原则:engines 与数据文件保持根目录不动(避免改路径/踩部署坑)。改动详见 git。

页面(在 views/ 下;**导航名 2026-06-10 重排+改名**,函数名/url_path 不变):
- 平台首页(page_home:概览 + 四维度卡片;**已去掉数字胶囊条**)。banner 副标题改「AI 辅助 · 健康风险-资源-行为规划调控 · 演示系统」。
- **🤖 智能助手(顶部独立入口)** → page_assistant:见本会话新增。
- **健康风险**(顺序:中暑风险地图→热相关重症风险诊断与规划调控→清凉路径规划):
  - page_heatcase_map「中暑风险地图」(原"中暑病例风险地图",**排第一**;2013–2025 上海 5349 例实测,热力图/病例点/街道重症比例 + 多维筛选,引擎 heatcase.py)
  - page_health_risk「热相关重症风险诊断与规划调控」(_heat_diag() 局部建成环境→ΔLST→重症化概率,同图对比)
  - page_heatroute「清凉路径规划」(原"凉爽路径规划";一页两模式①全市·百度路线 directionlite+沿路 LST 热暴露,需 AK;②中心城区·绿荫路网 scipy Dijkstra,引擎 heatroute.py/roadnet.py)
- **健康资源**(顺序:急救反应时间预测→急救站布局模拟→设施配置优化):
  - page_ems_response「急救反应时间预测」(**本会话新增**)
  - page_health_resource「急救站布局模拟」(_heat_ems() 客户端 Leaflet 落站/拖站 what-if,偏热环境)
  - page_facility_layout「设施配置优化」(**原 page_cooling_layout,本会话改为两选项卡:纳凉 cooling_mclp / EMS急救 ems_facility,统一 MCLP+街道公平性**)
- **健康行为** → page_bike「骑行潜力与建成环境优化」(**本会话新增**,原占位 page_behavior 弃用)
- **健康影响评估** → render_custom_mode「绿地规划健康影响评估」(原"自定义地块评估")/ page_hia_calc「规划方案 HIA 计算器」(专利 5D 法,**本会话完善+城市死亡率库**)。注:「绿地干预·示范案例」page_hia_cases 与「建模方法说明」render_methodology 已从导航**隐去**(代码保留)。AI 辅助 HIA 初筛 page_hia_screen/hia_screen.py 当前未挂导航。
- **友情链接** → page_friends(**本会话新增**:嵌合作学者工具);**关于** → page_about(**本会话改为仅免责声明+版权声明**)。模块管理 views/admin.page_admin(?admin)。

计算引擎(根目录,纯函数,被 views 调用):`green_lst.py`(LST 随机森林 + 干预 ΔLST,含邻域外溢)、`heat_risk.py`(中暑重症 logistic + ΔLST→Δ风险链路)、`hia_engine.py`(逐格 HIA)、`cooling_mclp.py`(纳凉设施 MCLP 选址优化,scipy+pulp,**不依赖 geopandas**)、`heatcase.py`(中暑病例风险地图:加载/筛选/街道聚合,轻量)、`heatroute.py`(凉爽路径规划:百度 directionlite 路线 + geocoding 地址解析 + LST 的 cKDTree 采样 + 沿路热暴露 + 凉爽途经点绕行强造备选,LST 面取自 green_lst,无新数据文件)、`roadnet.py`(绿荫凉爽路径:街景路网图 + scipy Dijkstra 多目标最短路,边权=长度×(1+w_热·LST归一+w_荫·(1−S_veget)))、`hia_screen.py`(AI 辅助 HIA 因果路径流水线 + docx)、`hia_evidence.py`(WHO 证据卡片库)、`hia_calc.py`(规划方案 HIA 专利法,纯公式 + 内置 5D 弹性表/ERF/城市死亡率)、`ems_response.py`(急救反应时间:最近站 cKDTree + 百度 v2 驾车多候选 + 缓冲区算 5 变量 + RF 预测,运行时用 shapely)、`ems_facility.py`(EMS 急救设施 MCLP,达标由 ART 定义)、`bike_ride.py`(共享单车骑行量 HGB 预测 + 圈范围反向优化建成环境杠杆)、`llm_agent.py`(智能助手 DeepSeek 引擎)、`platform_manual.py`(助手知识底座)、`cases.py`、`report_docx.py`。
新增分析的范式:加一个引擎(根目录)+ 在 `views/` 加一页 + 在 app.py 的 st.navigation 注册。MCLP 是最新一例:离线 `analysis/build_cooling_data.py`(pyshp+shapely+pyproj 读 shp)瘦身成 npz/geojson,运行时只用 numpy/scipy/pulp 现场求解。

## 运行时数据文件(在仓库内,勿删)
model_v2.joblib(29MB,LST RF,已 compress)、baseline_v2.npz、feature_grids_dense.npz(21MB)、heat_risk_grid.npz、heat_risk_model.json、heat_cases.npz、heat_ems_points.npz、heat_facility_grids.npz、cooling_mclp.npz(0.49MB,纳凉/小区/街道坐标+属性)、cooling_jiedao.geojson(0.65MB,简化街道边界,纳凉/病例 choropleth 共用)、heatcase_points.npz(0.05MB,2013–2025 上海中暑病例 5349 例:坐标/严重度/死亡/年龄/性别/职业/街道归属 + 地理编码质量 conf/precise;**坐标已脱敏:精确点抖动 ~300m,带 anonymized 标记;精确真源仅本机 heatcase_points_precise.local.npz**)、module_config.json(板块可见性/打码配置)、roadnet.npz(2.4MB,中心城区街景路网最大连通分量:74157 节点/95514 边,每边含 length/S_veget 绿视率/采样 LST/折线几何,绿荫凉爽路径用)。
**本会话(2026-06-10)新增运行时数据**:ems_layers.npz(4.5MB,EMS 反应时间:人口/FAR 栅格+支路坐标+医疗POI+POPDEN/FAR 校准系数+投影中心)、ems_model.joblib(10MB,reg+clf 双 RF)、ems_facility.npz(0.2MB,外环内 14625 需求格:人口/老年/ART/街道 + 202 站 + 街道质心)、bike_grid.npz(5.9MB,298249 格逐格 13 变量+工作日/周末骑行量)、bike_model.joblib(1.1MB,HGB wk/we + 杠杆上限)、city_mortality.csv(316 城全因死亡率,HIA 计算器内置)、assets/avatar_1~3.jpg(助手拟人化头像)、friends/nyc_crime_light.html(友情链接嵌入的合作者 Mapbox 仪表盘)。

## 关键模型决策与坑(别重复踩)
- **LST 模型**:greenfrac(非NDVI,对应"画多边形改绿地")+ 邻域绿地(300/900m)+ 到最近绿地距离 + 建成/灯光/高程。空间分块 CV **R²≈0.74**。瘦身到 120树/深16/叶50+compress,精度不变。
- **中暑重症 logistic**:287 例 60+ 病例,只保留**当天地表温度(p<0.01)+ 到最近急救站距离**(建成/绿地经 LST 间接影响,不直接入模)。in-sample AUC≈0.62,空间 CV≈0.59,**关联性模型非预测**,页面已标注。RF 在 n=287 上过拟合,故用 logistic。
- **空气污染(CHAP PM2.5/NO2)**:试过"绿地→污染"模型,空间分块 CV 全为负(城内污染由区域背景/排放主导),**做不成,已弃**;若重启走"暴露+健康负担层"。
- **数据陷阱**:早期单期 LST CSV 有无效像元(裸相关方向都反);现用多年合成 `SH_HIA_100m_multiyear.csv`,有效 LST 100%。
- **中暑病例地理编码陷阱**:5349 例里 52% 的地址只编码到"乡镇/区县"级,被吸附到中心点(单坐标最多叠 192 例)→ 假热点。按 `现住_level` 标 `precise`(非乡镇/区县/城市/NoClass),病例风险地图**默认仅用精确定位 1454 例**(可切"全部")。

## 原始建模数据(不在仓库,只在家里这台机器)
H:\heat_facility\(急救站/纳凉点 shp)、C:\Users\...\Downloads\(CHAP nc、greenfrac tif、病例 xlsx、SH_HIA_100m_multiyear.csv)。
MCLP 选址原始数据(cool/residence1/jiedao shp,UTM 51N):来自 `MCLP.zip`,办公室机器解压在 `D:\projects\_mclp_raw\`(仓库外);residence1 含 Pop/LST/Health 字段、jiedao 名字段为 `F`。重跑 `analysis/build_cooling_data.py` 才需要。
中暑病例风险地图原始数据:`2023-2025年高温中暑病例监测数据-经纬度.xlsx`(实际跨 2013–2025,29 列含现住/中暑发生地 WGS84 经纬度、中暑诊断[重症/轻症]、是否死亡、年龄/性别/职业)。重跑 `analysis/build_heatcase_data.py`(需 openpyxl+shapely,仅 venv 本地)才需要。
绿荫路径原始数据:`link_SVI_补充空值_type.shp`(98334 路段街景路网,WGS84,from_node/to_node/length/dir + 街景语义分割 S_* 含 `S_veget` 绿视率;来自骑行研究),解压在 `D:\projects\_svi_raw\`(仓库外)。**坑:拖到 Temp 时 ArcGIS 锁着会导致 .dbf/.shp 残缺**(.dbf 仅 5 字节)——务必关 ArcGIS 后整套(.shp/.shx/.dbf/.prj)打包。重跑 `analysis/build_roadnet_data.py`(pyshp+scipy)才需要。
**只有重跑 `analysis/` 里的离线建模脚本才需要这些;改/跑 app 不需要**(运行时 npz/joblib 已在仓库)。如需在办公室也做重建模,把这些原始数据放网盘/OneDrive。

## 跨机器工作流(重要)
两台电脑都通过 GitHub 同步:
- **开工前**:`git pull`
- **收工前**:`git add -A && git commit -m "..." && git push`
- 切忌两边都留未提交的改动 → 冲突。
- **⚠️ 一次性(2026-06 重写过历史)**:为病例坐标脱敏 force-push 过一次,改写了历史。**另一台机器若还是改写前的旧历史,不要 pull,直接删掉项目文件夹重新 `git clone`**(否则 divergent 冲突);clone 一次后即恢复正常 pull/push。
- **新机器/重新 clone 后**:① `pip install -r requirements.txt`(含 `pypdf`,AI 辅助 HIA 解析 PDF 用);② 重配 `.streamlit/secrets.toml`(见下)。
- **国内 push 大文件被重置(OpenSSL errno 10053)** → 仓库本地配:`git config http.postBuffer 1048576000; git config http.version HTTP/1.1; git config http.lowSpeedLimit 0; git config http.lowSpeedTime 999999`,再多试几次 / 挂代理(`git config --global http.proxy http://127.0.0.1:端口`)。这些是本地 `.git/config`,**不随仓库同步,每台机器要各设一次**。
- 新机器首次 push 需配 git 身份:`git config user.name swyhns; git config user.email 64192494+swyhns@users.noreply.github.com`;凭据走 GCM(manager-core),首次会弹 GitHub 登录窗。

## 本会话新增(2026-06-10,security / admin / AI 辅助 HIA)
- **AI 辅助 HIA(定性初筛)** `views/hia_screen.py` + 引擎 `hia_screen.py`:对标《健康影响评估初筛表》。3 段 DeepSeek 流水线 `行动抽取 → 多视角因果路径展开(沿健康决定因素,深度2–3)→ 完整性批判` → 代码确定性聚合到 10 题(强/中且非假设→是;仅推测→不知道;无路径→否)。`st.graphviz_chart` 画可编辑因果路径图(注:**不能用 use_container_width=True**,会把超宽 SVG 压成 0;且页面注入 CSS 让 SVG 自然尺寸+滚动)。PDF 用 `pypdf`(新依赖)、Word 用 python-docx。导出填好的初筛表 docx。
- **证据库** `hia_evidence.py`:56 张 WHO 官网卡片(带真实 URL,q="Q#"/note/sources/status),`match()` 按题号+关键词双向命中(只在决定因素段、剔除末端结果词防误配)+ `map_evidence()` LLM 语义匹配提召回。`docs/who_evidence_worklist.md` 是取证清单。
- **访问安全** `auth.py`:口令门 `require_login()`(app_password)+ `rate_limit()` 会话级限流(DeepSeek/百度防刷)。`theme.py` 注 noindex。病例坐标已脱敏(`analysis/anonymize_heatcase.py` 抖动 ~300m;精确真源 `heatcase_points_precise.local.npz` 仅本机 gitignore;**git 历史已 force-push 重写**)。
- **板块管理** `module_config.py` + `views/admin.py`:`?admin` 进入(会话标志)+ admin_password。单一全局开关隐藏功能页(`module_config.json` 的 disabled)+ 数据打码演示模式(blurred,目前 heatcase 注入 CSS 模糊地图/指标/图表)。app.py 导航按配置过滤。⚠ 云端文件系统临时,面板改动需"导出配置"提交才持久。
- **杂项**:平台改名「健康城市智能规划与评估平台」;`theme.md_bold()` 把 HTML 文本里的 `**` 转 `<b>`(page_header/首页卡片接入,清字面星号);关于页改标签页 + 延伸阅读(4 篇论文 + 王兰 2023 导读 + 空间干预梯度模型 SVG 自绘图)。

## 本会话新增(2026-06-10 第二段,家里机器一整天)
- **环境迁移**:Anaconda venv → 干净 python.org 3.11(SSL DLL 折腾消失);run.ps1 路径自适应+ssl自愈;修 `pulp==3.3.2`(不存在)→3.1.1;升级 venv pip。
- **急救反应时间预测** `ems_response.py`+`views/ems_response.py`+`analysis/build_ems_data.py`:地图点选事发点→最近现状急救站(直线最近邻)→百度 `direction/v2/driving` alternatives 多候选→沿轨迹缓冲区算 5 变量(距离/支路长/POPDEN/FAR/医疗POI密度)→RF 预测到场秒数+4档分级,标记模型预测最短路线。**坑**:原始人口/FAR 栅格量纲与训练对不上→用"分布校准"(线性映射对齐训练分布,系数存 npz)。需百度 AK。
- **EMS 急救设施配置**:并入「设施配置优化」两选项卡(纳凉/EMS),引擎 `ems_facility.py`。**达标由 ART 急救反应时间定义**(非到站距离);25.6万栋建筑 ART 聚合到 ~200m 格(14625),权重 总人口/老年(**70+**)/均等。
- **骑行潜力与建成环境优化** `bike_ride.py`+`views/bike.py`+`analysis/build_bike_data.py`:HGB 预测骑行量(R²≈0.37);圈范围→反向优化正向杠杆(商业POI/FAR/密度/路网)升向 p90 上限,三模式(强度/重点N格/预算约束)。绘制图与结果图左右对齐(session 记忆多边形+缩放对齐)。
- **规划方案 HIA 计算器** `hia_calc.py`+`views/hia_calc.py`:实现专利 8 步法(5D弹性表1→出行→暴露→ERF表2→RR→PAF→全因死亡)。**坑**:专利表1「到公交站距离」弹性符号与表3工作案例矛盾,按案例(物理合理)取 car=+0.05/walk=−0.15,改后精确复现案例(心血管−5.25%)。城市死亡率按 city_mortality.csv 选城自动取;PM2.5 内嵌全国均值30可改;小汽车贡献/通勤步行固定;仅评估全因死亡。
- **🤖 智能助手** `llm_agent.py`+`platform_manual.py`+`views/assistant.py`:DeepSeek(OpenAI兼容,公网可达云端能调)对话引导→结构化「reply+options+action」。options→按钮;need_map→内嵌 folium 点选/圈选;navigate→预填 session_state(白名单)+地图几何→`st.switch_page`(app.py 建 `st.session_state["_nav_pages"]` 注册表)。**混合模式**:急救反应时间在对话里直接出结果(内联卡片+小地图);其余引导跳转。**拟人化头像**按当前功能切换(avatar_1猫=急救/急救站/骑行,avatar_2=其余,avatar_3=未分配)。**大坑(已根治)**:DeepSeek json_object 模式对固定输入**确定性地只吐一串空白**(解析空→助手卡死),升温没用,**改输入(加一句扰动提示)重试才能打破**——chat() 三次尝试 0.3→(加扰动)0.8→1.2 + 稳健 `_extract_json`。别改纯文本模式(模型反更不稳)。
- **友情链接** `views/friends.py`+`friends/*.html`:`components.html` 内嵌合作学者自包含工具(首个:rxy 纽约犯罪×夜间照明 Mapbox 仪表盘)。扩展只需往 `FRIENDS` 列表加项(embed/url)。**坑**:嵌入 HTML 里有 Mapbox `pk.` token→GitHub 推送保护拦截,需在网页点 "Allow secret" 放行(公开发布型 token,部署页本就会暴露)。
- **导航/文案**:多处改名+重排(见上页面段);隐去建模方法说明/示范案例;首页去数字胶囊条;关于页改免责+版权声明。

## 待办/方向
- **云端 Secrets 必配**:`deepseek_api_key`(智能助手)、`baidu_ak`(急救反应时间/清凉路径),否则线上这几页用不了。建议把对话里出现过的 DeepSeek/Mapbox token 轮换。
- ✅ 已完成(2026-06):代码分层(theme/geo/views)、视觉打磨(page_header/卡片)、纳凉 MCLP、中暑风险地图、清凉路径规划、EMS 反应时间+设施配置、骑行潜力优化、规划方案 HIA 计算器、智能助手、友情链接。
- 首页可再做实(案例缩略图/成果亮点);健康行为维度待数据(手机信令/问卷/可穿戴)。
- 路径规划:绕行/绿荫备选可加"经某公园/绿廊"标注;绿荫路网范围外可自动回落百度。
- 长期:静态门户站(Hugo Academic/al-folio)做成果展示 + 链接本平台。
