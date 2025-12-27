import streamlit as st
import pandas as pd
from pulp import *

# --- 網頁介面設定 ---
st.set_page_config(page_title="美鄰診所排班系統", layout="wide")
st.title("🏥 專業診所排班系統 (互動版)")

# --- 側邊欄：設定參數 ---
st.sidebar.header("⚙️ 排班設定")

# 1. 護理師名單輸入
nurse_input = st.sidebar.text_area("護理師名單 (用逗號隔開)", "昀, 家, 琳, 護理4, 護理5, 護理6, 護理7, 護理8")
nurse_names = [n.strip() for n in nurse_input.split(",")]

# 2. 班數限制
max_shifts = st.sidebar.slider("每人每週總班數上限", 5, 15, 10)

# 3. 請假管理 (簡單示範)
st.sidebar.subheader("📅 請假設定")
off_nurse = st.sidebar.selectbox("選擇請假人員", nurse_names, index=1) # 預設選 "家"
off_days = st.sidebar.multiselect("選擇請假日期", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"], default=["週五", "週六"])

# --- 排班核心邏輯 (內部函數) ---
def run_pulp_scheduler(nurses, max_s, off_n, off_d):
    clinics = ["榮清", "美鄰", "仁友", "鴻林"]
    days = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    shifts = ["早班", "午班", "晚班"]

    # 營業時間表
    active_map = {(c, d, s): False for c in clinics for d in days for s in shifts}
    for d in days:
        if d in ["週一", "週二", "週三", "週四", "週五"]:
            for c in ["榮清", "美鄰", "仁友"]: 
                for s in shifts: active_map[(c, d, s)] = True
            for s in ["早班", "午班"]: active_map[("鴻林", d, s)] = True
        if d == "週四": active_map[("鴻林", d, "晚班")] = True
        if d == "週六":
            for s in ["早班", "午班"]: active_map[("榮清", d, s)] = True
            active_map[("美鄰", d, "早班")] = True
            for s in ["早班", "午班"]: active_map[("仁友", d, s)] = True
        if d == "週日":
            active_map[("榮清", d, "早班")] = True
            active_map[("美鄰", d, "早班")] = True
            for s in ["早班", "午班"]: active_map[("仁友", d, s)] = True
            active_map[("鴻林", d, "早班")] = True

    prob = LpProblem("Clinic_Scheduling", LpMaximize)
    choices = LpVariable.dicts("Choice", (nurses, clinics, days, shifts), 0, 1, LpBinary)

    # 約束：診所需求
    for c in clinics:
        for d in days:
            for s in shifts:
                if not active_map[(c, d, s)]:
                    for n in nurses: prob += choices[n][c][d][s] == 0
                else:
                    prob += lpSum([choices[n][c][d][s] for n in nurses]) == 1

    # 約束：個人時間
    for n in nurses:
        # 總班數上限
        prob += lpSum([choices[n][c][d][s] for c in clinics for d in days for s in shifts]) <= max_s
        for d in days:
            # 同時段只能在一處
            prob += lpSum([choices[n][c][d][s] for c in clinics for s in shifts]) <= 2 # 每天最多2班
            for s in shifts:
                prob += lpSum([choices[n][c][d][s] for c in clinics]) <= 1
            
            # 避免花班 (早晚中間無午)
            m = lpSum([choices[n][c][d]["早班"] for c in clinics])
            a = lpSum([choices[n][c][d]["午班"] for c in clinics])
            e = lpSum([choices[n][c][d]["晚班"] for c in clinics])
            prob += m + e - a <= 1

    # 處理請假 (側邊欄設定)
    if off_n in nurses:
        for d in off_d:
            for c in clinics:
                for s in shifts:
                    prob += choices[off_n][c][d][s] == 0

    # 優先權得分 (保留原本逻辑)
    scores = []
    if "昀" in nurses:
        for d in days:
            for c in clinics: prob += choices["昀"][c][d]["晚班"] == 0
            if d in ["週一", "週三", "週五"] and "榮清" in clinics:
                scores.append(choices["昀"]["榮清"][d]["早班"] * 10)
    
    prob += lpSum(scores)
    prob.solve(PULP_CBC_CMD(msg=0))

    if LpStatus[prob.status] == 'Optimal':
        rows = []
        for d in days:
            day_res = {"日期": d}
            for c in clinics:
                for s in shifts:
                    assigned = [n for n in nurses if value(choices[n][c][d][s]) == 1]
                    day_res[f"{c}-{s}"] = assigned[0] if assigned else "---"
            rows.append(day_res)
        return pd.DataFrame(rows)
    return None

# --- 網頁主畫面 ---
if st.button("🚀 依照設定生成排班表"):
    res_df = run_pulp_scheduler(nurse_names, max_shifts, off_nurse, off_days)
    if res_df is not None:
        st.success("🎉 排班表已更新！")
        # 讓表格更漂亮
        st.dataframe(res_df.style.highlight_max(axis=0, color='#e6f3ff'), use_container_width=True)
        st.download_button("📥 下載此份排班表", res_df.to_csv(index=False).encode('utf-8-sig'), "new_schedule.csv")
    else:
        st.error("❌ 條件太嚴苛（可能大家都在請假），請調整參數再試一次。")