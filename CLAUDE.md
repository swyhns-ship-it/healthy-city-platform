# 健康城市规划与智能评估平台 — 项目说明(给 Claude Code)

> 本文件随仓库提交,任何机器克隆后 Claude Code 自动读取,作为跨机器的项目上下文。
> 用户:孙文尧(同济 CAUP · 王兰团队 · 健康城市方向)。Python 熟,前端不熟。中文回复、简明、给可执行下一步。

## 是什么
Streamlit 多页平台:基于上海 100m 实测栅格 + 机器学习,做城市热环境健康影响评估与调控。
已部署 Streamlit Community Cloud(repo: github.com/swyhns-ship-it/healthy-city-platform,main 文件 `app.py`,**Python 3.11**)。
顶部标题「健康城市规划与智能评估平台」。

## 运行
```bash
pip install -r requirements.txt   # 锁定版本;scikit-learn==1.3.2 必须(否则加载不了 model_v2.joblib)
streamlit run app.py
```
本机(家里)是 Anaconda 建的 venv + run.ps1(处理 OpenSSL DLL);**别的机器用干净的 Python 3.11 + venv 即可,无需那套 DLL 折腾**。

## 架构(app.py,st.navigation 多页,按研究维度分组)
- 平台首页(page_home:概览 + 四维度卡片)
- **健康风险** → page_health_risk:热相关重症风险诊断;_heat_diag() 局部建成环境(绿地/建筑密度/容积率)→ΔLST→重症化概率,同图对比
- **健康资源** → page_health_resource:_heat_ems() 急救站布局模拟(客户端 Leaflet 组件,实时落站/拖站)
- **健康行为** → page_behavior:占位(待数据)
- **健康影响评估** → page_hia_cases(绿地干预示范案例)/ render_custom_mode(自定义地块 HIA)
- **方法与关于** → render_methodology / page_about

计算核心(纯函数,被页面调用):`green_lst.py`(LST 随机森林 + 干预 ΔLST,含邻域外溢)、`heat_risk.py`(中暑重症 logistic + ΔLST→Δ风险链路)、`hia_engine.py`(逐格 HIA)、`cases.py`、`report_docx.py`。
新增分析的范式:加一个引擎 + 在对应维度加一页。

## 运行时数据文件(在仓库内,勿删)
model_v2.joblib(29MB,LST RF,已 compress)、baseline_v2.npz、feature_grids_dense.npz(21MB)、heat_risk_grid.npz、heat_risk_model.json、heat_cases.npz、heat_ems_points.npz、heat_facility_grids.npz。

## 关键模型决策与坑(别重复踩)
- **LST 模型**:greenfrac(非NDVI,对应"画多边形改绿地")+ 邻域绿地(300/900m)+ 到最近绿地距离 + 建成/灯光/高程。空间分块 CV **R²≈0.74**。瘦身到 120树/深16/叶50+compress,精度不变。
- **中暑重症 logistic**:287 例 60+ 病例,只保留**当天地表温度(p<0.01)+ 到最近急救站距离**(建成/绿地经 LST 间接影响,不直接入模)。in-sample AUC≈0.62,空间 CV≈0.59,**关联性模型非预测**,页面已标注。RF 在 n=287 上过拟合,故用 logistic。
- **空气污染(CHAP PM2.5/NO2)**:试过"绿地→污染"模型,空间分块 CV 全为负(城内污染由区域背景/排放主导),**做不成,已弃**;若重启走"暴露+健康负担层"。
- **数据陷阱**:早期单期 LST CSV 有无效像元(裸相关方向都反);现用多年合成 `SH_HIA_100m_multiyear.csv`,有效 LST 100%。

## 原始建模数据(不在仓库,只在家里这台机器)
H:\heat_facility\(急救站/纳凉点 shp)、C:\Users\...\Downloads\(CHAP nc、greenfrac tif、病例 xlsx、SH_HIA_100m_multiyear.csv)。
**只有重跑 `analysis/` 里的离线建模脚本才需要这些;改/跑 app 不需要**(运行时 npz/joblib 已在仓库)。如需在办公室也做重建模,把这些原始数据放网盘/OneDrive。

## 跨机器工作流(重要)
两台电脑都通过 GitHub 同步:
- **开工前**:`git pull`
- **收工前**:`git add -A && git commit -m "..." && git push`
- 切忌两边都留未提交的改动 → 冲突。国内 push 大文件若被重置:`git config http.postBuffer 1048576000; git config http.version HTTP/1.1`。

## 待办/方向
首页做实(亮点/数据概览/案例缩略图);代码进一步分层(engines/ 包、pages/);健康资源扩展(纳凉点/绿地/医疗可达性);长期:静态门户站(Hugo Academic/al-folio)做成果展示 + 链接本平台。
