# 健康城市智能规划与评估平台

同济大学建筑与城市规划学院 · 健康城市实验室 — AI 辅助的城市热环境健康影响评估与调控演示系统。

## 功能模块

1. **示范案例** — 3 个上海绿地干预案例的热暴露健康影响评估(HIA)。
2. **自定义评估** — 在地图上绘制地块,模型预测 ΔLST(含空间外溢)与逐格健康影响。
3. **热相关健康风险诊断与调控**
   - ① 风险诊断:局部建成环境(绿地/建筑密度/容积率)→ 地表温度 → 中暑重症化风险(同一张图实时对比)。
   - ② 急救站布局模拟:现状急救站 + 重症风险底图,拖动落站/高温日滑块实时看受益面积、覆盖人口与风险下降。
4. **建模方法说明** — 数据、随机森林 + 空间分块交叉验证、特征重要性、剂量–反应、局限。

模型基于上海 100m 实测栅格(多年夏季合成 LST、绿地、建成、人口等)与 287 例 60+ 中暑病例训练。

## 本地运行(Windows)

```powershell
./run.ps1
```
浏览器打开 http://localhost:8501(同一局域网的同事可用 http://<本机IP>:8501)。

> 注:本机用 Anaconda 建的 venv,`run.ps1` 已处理 OpenSSL DLL 路径与局域网绑定。

通用方式:
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 云端发布(Streamlit Community Cloud)

1. 把本目录推到一个 GitHub 仓库(运行时数据文件已随仓库提交,约 51 MB,均 <100 MB)。
2. 登录 https://share.streamlit.io → New app → 选该仓库,Main file 填 `app.py`。
3. **Advanced settings 里把 Python 版本选 3.11**(`numpy==1.24.4` 无 3.12 轮子)。
4. Deploy。完成后得到一个公开网址,发给同事即可一起测试。

> 依赖见 `requirements.txt`(scikit-learn 锁定 1.3.2,否则无法加载 `model_v2.joblib`)。

## 运行时数据文件(随仓库提交,勿删)

| 文件 | 用途 |
|---|---|
| `model_v2.joblib` (29MB) | 地表温度随机森林模型 |
| `baseline_v2.npz` | 基线 LST 预测 |
| `feature_grids_dense.npz` (21MB) | 100m 协变量栅格 |
| `heat_risk_grid.npz` / `heat_risk_model.json` | 中暑重症风险网格 + logistic 系数 |
| `heat_cases.npz` / `heat_ems_points.npz` / `heat_facility_grids.npz` | 病例点 / 现状急救站 / EMS 距离栅格 |

`analysis/` 为离线建模脚本(依赖本地原始数据,部署不需要)。

## 说明与局限

- LST 模型空间分块 CV R²≈0.74;中暑重症 logistic 为关联性模型(in-sample AUC≈0.62,空间 CV≈0.59),用于规划辅助研判,非交叉验证预测。
- 用于演示与研究,不替代正式环境健康风险评估。
