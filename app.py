import streamlit as st
import pandas as pd
from pulp import *
import calendar
from datetime import date

# --- 1. 網頁基礎設定 ---
st.set_page_config(page_title="Nursing Scheduler Pro", layout="wide")
st.title("🏥 護理排班系統")

# --- 2. 護理師資料維護 ---
st.header("👥 1. 護理人員名單與月班數設定")
st.info("💡 預設：同、琳、恩、羽 不排美鄰。王、同上限為 20，其餘人員為 50。")

all_clinics_options = ["榮清", "美鄰", "仁友", "鴻林"]

# 根據要求設定預設名單與排除邏輯
default_nurses = [
    {"姓名": "昀", "月班數上限": 50, "不排美鄰": False},
    {"姓名": "琳", "月班數上限": 50, "不排美鄰": True},
    {"姓名": "羽", "月班數上限": 50, "不排美鄰": True},
    {"姓名": "榛", "月班數上限": 50, "不排美鄰": False},
    {"姓名": "映", "月班數上限": 50, "不排美鄰": False},
    {"姓名": "王", "月班數上限": 20, "不排美鄰": False},
    {"姓名": "恩", "月班數上限": 50, "不排美鄰": True},
    {"姓名": "同", "月班數上限": 20, "不排美鄰": True},
]

df_nurses = st.data_editor(
    pd.DataFrame(default_nurses), 
    num_rows="dynamic", 
    use_container_width=True, 
    key="nurse_editor",
    column_config={
        "不排美鄰": st.column_config.CheckboxColumn("不排美鄰", help="預設不前往美鄰院區"),
        "月班數上限": st.column_config.NumberColumn("上限", min_value=0, max_value=100)
    }
)
nurse_names = df_nurses["姓名"].tolist()

# --- 3. 院所固定需求設定 ---
st.header("🏪 2. 院所每週固定人力需求")
weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
clinic_rules = [
    {"診所": "榮清", "週一": "早2/午1/晚1", "週二": "早1/午1/晚1", "週三": "早2/午1/晚1", "週四": "早1/午1/晚1", "週五": "早2/午1/晚1", "週六": "早1/午1/晚0", "週日": "早1/午0/晚0"},
    {"診所": "美鄰", "週一": "早1/午1/晚1", "週二": "早1/午1/晚1", "週三": "早1/午1/晚1", "週四": "早1/午1/晚1", "週五": "早1/午1/晚1", "週六": "早1/午0/晚0", "週日": "早1/午0/晚0"},
    {"診所": "仁友", "週一": "早1/午2/晚2", "週二": "早1/午2/晚2", "週三": "早1/午2/晚2", "週四": "早1/午2/晚2", "週五": "早1/午2/晚2", "週六": "早1/午1/晚0", "週日": "早2/午1/晚0"},
    {"診所": "鴻林", "週一": "早1/午1/晚0", "週二": "早1/午1/晚0", "週三": "早1/午1/晚0", "週四": "早1/午1/晚1", "週五": "早1/午1/晚0", "週六": "早0/午0/晚0", "週日": "早1/午0/晚0"},
]
df_rules = st.data_editor(pd.DataFrame(clinic_rules), use_container_width=True, key="rule_editor")

# --- 4. 側邊欄：月份與個人偏好 ---
st.sidebar.header("🗓️ 3. 排班月份與偏好")
selected_year = st.sidebar.selectbox("年份", [2025, 2026, 2027], index=1)
selected_month = st.sidebar.slider("月份", 1, 12, 1)
_, num_days = calendar.monthrange(selected_year, selected_month)
days_list = [f"{i:02d}" for i in range(1, num_days + 1)]

# 各分院獨立休診
clinic_holidays = {}
with st.sidebar.expander("🏥 各院所休診日期"):
    for c in all_clinics_options:
        clinic_holidays[c] = st.multiselect(f"【{c}】休診日期", days_list, key=f"h_{c}")

is_sat_alt = st.sidebar.checkbox("榮清週六隔週 2 人邏輯", value=True)

# 護理師習慣與志願序 (連動主畫面表格的預設值)
nurse_configs = {}
with st.sidebar.expander("👤 4. 護理人員習慣設定"):
    for _, row in df_nurses.iterrows():
        name = row["姓名"]
        st.write(f"**--- {name} ---**")
        
        # 這裡會自動讀取表格中的「不排美鄰」布林值
        no_meilin = st.checkbox(f"{name} 不排美鄰", value=row["不排美鄰"], key=f"no_m_{name}")
        p1 = st.selectbox(f"{name}：優先志願", ["無"] + all_clinics_options, key=f"p1_{name}")
        no_night = st.checkbox("不排晚班", key=f"n_{name}")
        fixed_off = st.multiselect("每週固定休", weekday_names, key=f"f_{name}")
        temp_off = st.multiselect("特定日期請假", days_list, key=f"t_{name}")
        
        nurse_configs[name] = {
            "no_meilin": no_meilin, "pref_c": p1,
            "no_night": no_night, "fixed_off": fixed_off, "temp_off": temp_off
        }

run_button = st.sidebar.button("🚀 生成全月護理排班表", use_container_width=True)

# --- 5. 需求微調與禁止限制 ---
st.header("✏️ 5. 特定日期需求【微調】與【禁止】")
col1, col2 = st.columns(2)
with col1:
    df_overrides = st.data_editor(
        pd.DataFrame(columns=["診所", "日期", "時段", "需求人數"]),
        num_rows="dynamic", use_container_width=True, key="override_editor",
        column_config={
            "診所": st.column_config.SelectboxColumn("診所", options=all_clinics_options),
            "日期": st.column_config.SelectboxColumn("日期", options=days_list),
            "時段": st.column_config.SelectboxColumn("時段", options=["早班", "午班", "晚班"])
        }
    )
with col2:
    df_prohibitions = st.data_editor(
        pd.DataFrame(columns=["護理師", "日期", "診所", "時段"]),
        num_rows="dynamic", use_container_width=True, key="prohibition_editor",
        column_config={
            "護理師": st.column_config.SelectboxColumn("護理師", options=nurse_names),
            "日期": st.column_config.SelectboxColumn("日期", options=days_list),
            "診所": st.column_config.SelectboxColumn("診所", options=all_clinics_options)
        }
    )

# --- 內部工具函數 ---
def parse_need(rule_str, shift):
    try:
        parts = rule_str.split("/")
        for p in parts:
            if shift[0] in p: return int(p[1:])
    except: return 0
    return 0

def style_schedule(val):
    if val == "休診": return 'background-color: #F0F0F0; color: #999999;'
    if "缺" in val: return 'background-color: #FFCCCC; color: #CC0000; font-weight: bold;'
    return 'background-color: #E6F3FF; color: #003366;'

# --- 6. 排班引擎 ---
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
        for c in all_clinics_options:
            rule_row = df_rules[df_rules["診所"] == c].iloc[0]
            day_rule_str = rule_row[weekday_names[wd_idx]]
            for s in shifts:
                if f"{i:02d}" in clinic_holidays.get(c, []):
                    need_map[(c, lbl, s)] = 0
                else:
                    base_need = parse_need(day_rule_str, s)
                    if c == "榮清" and wd_idx == 5 and s == "早班" and is_sat_alt:
                        base_need = 1 if sat_count % 2 != 0 else 2
                    final_need = base_need
                    for _, ov in df_overrides.iterrows():
                        if ov["診所"] == c and ov["日期"] == f"{i:02d}" and ov["時段"] == s:
                            if pd.notnull(ov["需求人數"]): final_need = int(ov["需求人數"])
                    need_map[(c, lbl, s)] = final_need

    prob = LpProblem("Nursing_Default_Exclusion", LpMaximize)
    choices = LpVariable.dicts("Choice", (nurse_names, all_clinics_options, day_labels, shifts), 0, 1, LpBinary)

    fulfillment = lpSum([choices[n][c][lbl][s] for n in nurse_names for c in all_clinics_options for lbl in day_labels for s in shifts])
    
    # 志願優先加分
    pref_score = []
    for n in nurse_names:
        cp = nurse_configs[n]["pref_c"]
        if cp != "無":
            pref_score.append(lpSum([choices[n][cp][lbl][s] for lbl in day_labels for s in shifts]) * 0.1)
    
    prob += fulfillment + lpSum(pref_score)

    for lbl in day_labels:
        for c in all_clinics_options:
            for s in shifts:
                prob += lpSum([choices[n][c][lbl][s] for n in nurse_names]) <= need_map[(c, lbl, s)]

    for _, row in df_nurses.iterrows():
        n = row["姓名"]
        conf = nurse_configs[n]
        prob += lpSum([choices[n][c][lbl][s] for c in all_clinics_options for lbl in day_labels for s in shifts]) <= row["月班數上限"]
        
        # 處理不排美鄰
        if conf["no_meilin"]:
            for lbl in day_labels:
                for s in shifts: prob += choices[n]["美鄰"][lbl][s] == 0

        for lbl in day_labels:
            d_idx = date(selected_year, selected_month, int(lbl[:2])).weekday()
            if conf["no_night"]:
                for c in all_clinics_options: prob += choices[n][c][lbl]["晚班"] == 0
            if weekday_names[d_idx] in conf["fixed_off"]:
                for c in all_clinics_options:
                    for s in shifts: prob += choices[n][c][lbl][s] == 0
            if lbl[:2] in conf["temp_off"]:
                for c in all_clinics_options:
                    for s in shifts: prob += choices[n][c][lbl][s] == 0
            
            for _, ban in df_prohibitions.iterrows():
                if ban["護理師"] == n and ban["日期"] == lbl[:2] and ban["診所"] == c and ban["時段"] == s:
                    prob += choices[n][c][lbl][s] == 0

            for s in shifts: prob += lpSum([choices[n][c][lbl][s] for c in all_clinics_options]) <= 1
            m = lpSum([choices[n][c][lbl]["早班"] for c in all_clinics_options]); a = lpSum([choices[n][c][lbl]["午班"] for c in all_clinics_options]); e = lpSum([choices[n][c][lbl]["晚班"] for c in all_clinics_options])
            prob += m + e - a <= 1

    prob.solve(PULP_CBC_CMD(msg=0, timeLimit=20))
    
    final_rows = []
    vacancy_list = []
    for lbl in day_labels:
        res_row = {"日期": lbl}
        for c in all_clinics_options:
            for s in shifts:
                assigned = [n for n in nurse_names if value(choices[n][c][lbl][s]) == 1]
                needed = need_map[(c, lbl, s)]
