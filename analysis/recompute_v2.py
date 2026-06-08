# -*- coding: utf-8 -*-
"""(venv)用 v2 场重算 3 案例聚合标量,并验证逐格 HIA。输出可直接填回 cases.py。"""
import sys
sys.path.insert(0, r"E:\projects\hia_demo")
from cases import CASES
from green_lst import compute_field
from hia_engine import compute_hia_gridded

mm = {"greenspace_add": "add", "greenspace_remove": "remove"}
for cid, c in CASES.items():
    f = compute_field(c["polygon"], mode=mm[c["intervention_type"]])
    r = compute_hia_gridded(c, f)
    dlst_in = f["dlst_mean_inside"]; air = round(dlst_in * 0.7, 2)
    print("\n[%s] %s" % (cid, c["label_short"]))
    print("  填回 cases.py:  delta_lst_C=%.2f  delta_air_temp_C=%.2f  population=%d  summer_lst_baseline_C=%.1f"
          % (dlst_in, air, int(f["pop_affected"]), f["obs_lst_inside"]))
    print("  场: 内%d格/含外溢%d格  内ΔLST %.2f  人口加权ΔT_air %.2f"
          % (f["n_inside"], f["n_cells"], dlst_in, r["delta_air_temp_pop_weighted"]))
    print("  逐格HIA: %s CVD %.2f [%.2f,%.2f] | 全因 %.2f | 敏感性 %.2f (%d年)"
          % (r["metric_name"], r["cvd_primary"]["total_point"],
             r["cvd_primary"]["total_low"], r["cvd_primary"]["total_high"],
             r["ac_primary"]["total_point"], r["cvd_sensitivity"]["total_point"],
             c["evaluation_years"]))
