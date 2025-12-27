import streamlit as st
import pandas as pd
from pulp import *
import calendar
from datetime import date

# --- 1. 網頁基礎設定 ---
st.set_page_config(page_title="Nursing Scheduler Pro", layout="wide")
st.title("🏥 護理排班系統 (名單與美鄰優先優化版)")

# --- 2. 護理師資料維護 ---
st.header("👥 1. 護理人員名單與月班數設定")
st.info("💡 更新公告：已移除同仁【同】。新增【映、王】優先排美鄰。琳、羽、恩、同(已除) 維持不排美鄰。")

all_clinics = ["榮清", "美鄰", "仁友", "鴻林"]

# 設定預設名單、排除邏輯與優先志願
# 同已移除；映、王優先志願改為美鄰
default_nurses = [
    {"姓名": "昀", "月班數上限": 50, "不排美鄰": False, "優先志願": "無"},
    {"姓名": "琳", "月班數上限": 50, "不排美鄰": True, "優先志願": "榮清"},
    {"姓名": "羽", "月班數上限": 50, "不排美鄰": True, "優先志願": "仁友"},
    {"姓名": "榛", "月班數上限": 50, "不排美鄰": False, "優先志願": "鴻林"},
    {"姓名": "映", "月班數上限": 50, "不排美鄰": False, "優先志願": "美鄰"},
    {"姓名": "王", "月班數上限": 20, "不排美鄰": False, "優先志願": "美鄰"},
    {"姓名": "恩", "月班數上限": 50, "不排美鄰": True, "優先志願": "仁友"},
]

df_nurses = st.data_editor(
    pd.DataFrame(default_nurses), 
    num_rows="dynamic", 
    use_container_width=True, 
    key="nurse_editor",
    column_config={
        "不排美鄰": st.column_config.CheckboxColumn("不排美鄰"),
        "優先志願": st.column_config.SelectboxColumn("優先志願", options=["無"] + all_clinics),
        "月班數上限": st.column_config.NumberColumn("上限", min_value=0, max_value=100)
    }
)
nurse_names = df_nurses["姓名"].tolist()

# --- 3. 院所每週人力需求 ---
st.header("🏪 2. 院所每週固定人力需求")
weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
clinic_rules = [
    {"診所": "榮清", "週一": "早2/午1/晚1", "週二": "早1/午1/晚1", "週三": "早2/午1/晚1", "週四": "早1/午1/晚1", "週五": "早2/午1/晚1", "週六": "早1/午1/晚0", "週日": "早1/午0/晚0"},
    {"診所": "美鄰", "週一": "早1/午1/晚1", "週二": "早1/午1/晚1", "週三": "早1/午1/晚1", "週四": "早1/午1/晚1", "週五": "早1/午1/晚1", "週六": "早1/午0/晚0", "週日": "早1/午0/晚0"},
    {"診所": "仁友", "週一": "早1/午2/晚2", "週二": "早1/午2/晚2", "週三": "早1/午2/晚2", "週四": "早1/午2/晚2", "週五": "早1/午2/晚2", "週六": "早1/午1/晚0", "週日": "早2/午1/晚0"},
    {"診所": "鴻林", "週一": "早1/午1/晚0", "週二": "早1/午1/晚0", "週三": "早1/午1/晚0", "週四": "早1/午1/晚1", "週五": "早1/午1/晚0", "週六": "早0/午0/晚0", "週日": "早1/午0/晚0"},
]
df_rules = st.data_editor(pd.DataFrame(clinic_rules), use_container_width=True, key="rule_editor")

# --- 4. 側邊欄設定 ---
st.sidebar.header("🗓️ 3. 排班月份設定")
selected_year = st.sidebar.selectbox("年份", [2025, 2026, 2027], index=1)
selected_month = st.sidebar.slider("月份", 1, 12, 1)
_, num_days = calendar.monthrange(selected_year, selected_month)
days_list = [f"{i:02d}" for i in range(1, num_days + 1)]

clinic_holidays = {}
with st.sidebar.expander("🏥 各院所休診日期"):
    for c in all_clinics:
        clinic_holidays[c] = st.multiselect(f"【{c}】休診日期", days_list, key=f"h_{c}")

is_sat_alt = st.sidebar.checkbox("榮清週六隔週 2 人邏輯", value=True)

nurse_configs = {}
with st.sidebar.expander("👤 4. 護理人員習慣與志願"):
    for _, row in df_nurses.iterrows():
        name = row["姓名"]
        st.write(f"--- {name} ---")
        no_m = st.checkbox(f"{name} 不排美鄰", value=row["不排美鄰"], key=f"no_m_{name}")
        p_idx = (all_clinics.index(row["優先志願"]) + 1) if row["優先志願"] in all_clinics else 0
        p1 = st.selectbox(f"{name}：志願", ["無"] + all_clinics, index=p_idx, key=f"p1_{name}")
        no_night = st.checkbox("不排晚班", key=f"n_{name}")
        fixed_off = st.multiselect("每週固定休", weekday_names, key=f"f_{name}")
        temp_off = st.multiselect("特定日期請假", days_list, key=f"t_{name}")
        nurse_configs[name] = {"no_m": no_m, "p1": p1, "no_night": no_night, "fixed_off": fixed_off, "temp_off": temp_off}

run_button = st.sidebar.button("🚀 生成全月護理排班表", use_container_width=True)

# --- 5. 特定指派與微調 ---
st.header("✏️ 5. 特定指派與微調")
df_flex_assignments = st.data_editor(pd.DataFrame(columns=["護理師", "日期", "時段"]), num_rows="dynamic", use_container_width=True, key="flex_assign")
df_assignments = st.data_editor(pd.DataFrame(columns=["護理師", "日期", "診所", "時段"]), num_rows="dynamic", use_container_width=True, key="fix_assign")
df_overrides = st.data_editor(pd.DataFrame(columns=["診所", "日期", "時段", "需求人數"]), num_rows="dynamic", use_container_width=True, key="overrides")

# --- 6. 核心計算引擎 ---
def run_scheduler():
    shifts = ["早班", "午班", "晚班"]
    day_labels = []
    need_map = {}
    sat_count = 0
    
    for i in range(1, num_days + 1):
        d_obj = date(selected_year, selected_month, i)
        wd_idx = d_obj.weekday()
        if wd_idx == 5: sat_count += 1
        lbl = f"{i:02d} ({weekday_names[wd_idx]})"
        day_labels.append(lbl)
        for c in all_clinics:
            rule_row = df_rules[df_rules["診所"] == c].iloc[0]
            day_rule_str = rule_row[weekday_names[wd_idx]]
            for s in shifts:
                if f"{i:02d}" in clinic_holidays.get(c, []):
                    need_map[(c, lbl, s)] = 0
                else:
                    base_need = 1
                    try:
                        parts = day_rule_str.split("/")
                        for p in parts:
                            if s[0] in p: base_need = int(p[1:])
                    except: base_need = 1
                    if c == "榮清" and wd_idx == 5 and s == "早班" and is_sat_alt:
                        base_need = 1 if sat_count % 2 != 0 else 2
                    for _, ov in df_overrides.iterrows():
                        if ov["診所"] == c and ov["日期"] == f"{i:02d}" and ov["時段"] == s:
                            if pd.notnull(ov["需求人數"]): base_need = int(ov["需求人數"])
                    need_map[(c, lbl, s)] = base_need

    prob = LpProblem("Nursing_Final_Optimized", LpMaximize)
    choices = LpVariable.dicts("Choice", (nurse_names, all_clinics, day_labels, shifts), 0, 1, LpBinary)
    penalty_split = LpVariable.dicts("SplitShift", (nurse_names, day_labels), 0, 1, LpBinary)

    # 目標函數
    fulfillment = lpSum([choices[n][c][lbl][s] for n in nurse_names for c in all_clinics for lbl in day_labels for s in shifts])
    total_penalty = lpSum([penalty_split[n][lbl] for n in nurse_names for lbl in day_labels]) * 50
    pref_score = lpSum([choices[n][nurse_configs[n]["p1"]][lbl][s] for n in nurse_names for lbl in day_labels for s in shifts if nurse_configs[n]["p1"] != "無"]) * 0.1
    
    # 琳的黃金時段加權
    lin_bonus = []
    if "琳" in nurse_names:
        for lbl in day_labels:
            wd = date(selected_year, selected_month, int(lbl[:2])).weekday()
            if wd in [0, 2, 4]: lin_bonus.append(choices["琳"]["榮清"][lbl]["早班"] * 20)
            if wd == 3: lin_bonus.append(choices["琳"]["榮清"][lbl]["午班"] * 20)
            if wd == 1: lin_bonus.append(choices["琳"]["榮清"][lbl]["晚班"] * 20)
            if wd == 5 and need_map[("榮清", lbl, "早班")] == 2: lin_bonus.append(choices["琳"]["榮清"][lbl]["早班"] * 20)

    prob += (fulfillment * 100) - total_penalty + pref_score + lpSum(lin_bonus)

    for lbl in day_labels:
        for c in all_clinics:
            for s in shifts:
                prob += lpSum([choices[n][c][lbl][s] for n in nurse_names]) <= need_map[(c, lbl, s)]

    for _, row in df_nurses.iterrows():
        n = row["姓名"]
        conf = nurse_configs[n]
        prob += lpSum([choices[n][c][lbl][s] for c in all_clinics for lbl in day_labels for s in shifts]) <= row["月班數上限"]
        if conf["no_m"]:
            for lbl in day_labels:
                for s in shifts: prob += choices[n]["美鄰"][lbl][s] == 0

        for lbl in day_labels:
            has_M = lpSum([choices[n][c][lbl]["早班"] for c in all_clinics])
            has_A = lpSum([choices[n][c][lbl]["午班"] for c in all_clinics])
            has_N = lpSum([choices[n][c][lbl]["晚班"] for c in all_clinics])
            prob += penalty_split[n][lbl] >= has_M + has_N - has_A - 1
            # 地理限制
            prob += choices[n]["美鄰"][lbl]["午班"] + lpSum([choices[n][other][lbl]["晚班"] for other in ["榮清", "鴻林", "仁友"]]) <= 1
            prob += lpSum([choices[n][other][lbl]["午班"] for other in ["榮清", "鴻林", "仁友"]]) + choices[n]["美鄰"][lbl]["晚班"] <= 1

            if conf["no_night"]:
                for c in all_clinics: prob += choices[n][c][lbl]["晚班"] == 0
            if weekday_names[date(selected_year, selected_month, int(lbl[:2])).weekday()] in conf["fixed_off"]:
                for c in all_clinics:
                    for s in shifts: prob += choices[n][c][lbl][s] == 0
            for s in shifts: prob += lpSum([choices[n][c][lbl][s] for c in all_clinics]) <= 1

    prob.solve(PULP_CBC_CMD(msg=0, timeLimit=20))
    
    final_rows, vacancy_list, stats = [], [], {n: 0 for n in nurse_names}
    for lbl in day_labels:
        res_row = {"日期": lbl}
        for c in all_clinics:
            for s in shifts:
                assigned = [n for n in nurse_names if value(choices[n][c][lbl][s]) == 1]
                needed = need_map[(c, lbl, s)]
                for n in assigned: stats[n] += 1
                if needed == 0: res_row[f"{c}-{s}"] = "休診"
                else:
                    txt = ", ".join(assigned)
                    if len(assigned) < needed:
                        gap = needed - len(assigned)
                        txt = txt + (", " if txt else "") + "缺" * gap
                        vacancy_list.append({"日期": lbl, "診所": c, "班別": s, "缺額": gap})
                    res_row[f"{c}-{s}"] = txt
        final_rows.append(res_row)
    return pd.DataFrame(final_rows), pd.DataFrame(vacancy_list), stats

# --- 7. 結果顯示 ---
if run_button:
    with st.spinner("AI 正在根據新名單與志願優化班表..."):
        res_df, vac_df, nurse_stats = run_scheduler()
        st.success("🎉 排班完成！已移除同仁【同】，並優先安排映、王於美鄰。")
        st.dataframe(res_df.style.applymap(lambda v: 'background-color: #F0F0F0' if v == "休診" else ('background-color: #FFCCCC' if "缺" in v else 'background-color: #E6F3FF'), subset=res_df.columns[1:]), use_container_width=True, height=600)
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📊 人員總班數統計")
            st.table(pd.DataFrame(nurse_stats.items(), columns=["護理師", "本月總班數"]))
        with c2:
            st.subheader("📋 待補班清單")
            if not vac_df.empty:
                st.warning(f"偵測到 {vac_df['缺額'].sum()} 個護理空位。")
                st.table(vac_df)
            else:
                st.success("人力已全數補齊！")
        st.download_button("📥 下載班表 (CSV)", res_df.to_csv(index=False).encode('utf-8-sig'), "nursing_schedule.csv")