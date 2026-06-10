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
streamlit run app.py
```
本机(家里)是 Anaconda 建的 venv + run.ps1(处理 OpenSSL DLL);**别的机器用干净的 Python 3.11 + venv 即可,无需那套 DLL 折腾**。

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
- `theme.py`:健康绿主题色常量、全局 CSS(inject_css)、品牌条(render_banner)、统一页头(page_header)。
- `geo.py`:坐标变换(WGS84↔GCJ-02)+ folium 地图/栅格渲染工具(_add_basemap、dlst/risk 栅格、build_draw_map、面积/范围校验),纯绘图工具、无页面逻辑。
- `views/`:按维度一页(组)一模块 —— static_pages(首页/行为/关于)、health_risk、heatcase_map、health_resource、cooling、hia、methodology。页面只做 UI,调用 engines + geo + theme。
- 拆分原则:engines 与数据文件保持根目录不动(避免改路径/踩部署坑)。改动详见 git。

页面(在 views/ 下):
- 平台首页(page_home:概览 + 数据胶囊条 + 四维度卡片)
- **健康风险** → page_health_risk:热相关重症风险诊断;_heat_diag() 局部建成环境(绿地/建筑密度/容积率)→ΔLST→重症化概率,同图对比。page_heatcase_map:中暑病例风险地图(2013–2025 上海 5349 例实测,热力图/病例点/街道重症比例 choropleth + 多维筛选,引擎 heatcase.py)。page_heatroute:凉爽路径规划(**统一一页两模式**,共享起终点[地图点选/地址搜索]):①全市·百度路线(directionlite + 凉爽途经点绕行 → 沿路 100m LST 热暴露,引擎 heatroute.py,需百度 AK);②中心城区·绿荫路网(街景路网多目标最短路:距离+LST+绿视率 S_veget 加权,scipy Dijkstra,引擎 roadnet.py,仅路网范围内)
- **健康资源** → page_health_resource:_heat_ems() 急救站布局模拟(客户端 Leaflet 组件,实时落站/拖站);page_cooling_layout:纳凉设施布局优化(MCLP 最大覆盖选址 + 街道公平性软约束,pulp/CBC 现场求解)
- **健康行为** → page_behavior:占位(待数据)
- **健康影响评估** → page_hia_cases(绿地干预示范案例)/ render_custom_mode(自定义地块 HIA)
- **方法与关于** → render_methodology / page_about

计算引擎(根目录,纯函数,被 views 调用):`green_lst.py`(LST 随机森林 + 干预 ΔLST,含邻域外溢)、`heat_risk.py`(中暑重症 logistic + ΔLST→Δ风险链路)、`hia_engine.py`(逐格 HIA)、`cooling_mclp.py`(纳凉设施 MCLP 选址优化,scipy+pulp,**不依赖 geopandas**)、`heatcase.py`(中暑病例风险地图:加载/筛选/街道聚合,轻量)、`heatroute.py`(凉爽路径规划:百度 directionlite 路线 + geocoding 地址解析 + LST 的 cKDTree 采样 + 沿路热暴露 + 凉爽途经点绕行强造备选,LST 面取自 green_lst,无新数据文件)、`roadnet.py`(绿荫凉爽路径:街景路网图 + scipy Dijkstra 多目标最短路,边权=长度×(1+w_热·LST归一+w_荫·(1−S_veget)))、`cases.py`、`report_docx.py`。
新增分析的范式:加一个引擎(根目录)+ 在 `views/` 加一页 + 在 app.py 的 st.navigation 注册。MCLP 是最新一例:离线 `analysis/build_cooling_data.py`(pyshp+shapely+pyproj 读 shp)瘦身成 npz/geojson,运行时只用 numpy/scipy/pulp 现场求解。

## 运行时数据文件(在仓库内,勿删)
model_v2.joblib(29MB,LST RF,已 compress)、baseline_v2.npz、feature_grids_dense.npz(21MB)、heat_risk_grid.npz、heat_risk_model.json、heat_cases.npz、heat_ems_points.npz、heat_facility_grids.npz、cooling_mclp.npz(0.49MB,纳凉/小区/街道坐标+属性)、cooling_jiedao.geojson(0.65MB,简化街道边界,纳凉/病例 choropleth 共用)、heatcase_points.npz(0.05MB,2013–2025 上海中暑病例 5349 例:坐标/严重度/死亡/年龄/性别/职业/街道归属 + 地理编码质量 conf/precise)、roadnet.npz(2.4MB,中心城区街景路网最大连通分量:74157 节点/95514 边,每边含 length/S_veget 绿视率/采样 LST/折线几何,绿荫凉爽路径用)。

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

## 待办/方向
- ✅ 已完成(2026-06):代码分层(theme/geo/views)、视觉打磨(page_header/胶囊条/卡片)、纳凉 MCLP、中暑病例风险地图、凉爽路径规划(百度+绿荫路网双模式)。
- 首页可再做实(案例缩略图/成果亮点);健康行为维度待数据(手机信令/问卷/可穿戴)。
- 路径规划:绕行/绿荫备选可加"经某公园/绿廊"标注;绿荫路网范围外可自动回落百度。
- 长期:静态门户站(Hugo Academic/al-folio)做成果展示 + 链接本平台。
