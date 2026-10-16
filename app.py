import streamlit as st
import pandas as pd
import json
import os
from dotenv import load_dotenv

load_dotenv()

from queries import (
    get_all_wards,
    get_all_issue_types,
    get_incidents,
    get_incident_details,
    trend_for_ward,
    top_rising_issues,
    trace_root_cause,
    what_if_delay,
    get_all_work_orders,
    graph_for_incident,
    CITYWIDE_H1_PCT_CHANGE,
    BASELINE_WEEKLY_EXCL_SPIKE,
    SPIKE_MULTIPLIER
)
from agent import run_agent_turn, ask_city
from pyvis.network import Network
import streamlit.components.v1 as components

# Streamlit Page Config
st.set_page_config(
    page_title="CivicGraph | Bangalore Municipal Intelligence",
    page_icon="🏙️",
    layout="wide"
)

# Custom Styling with guaranteed light and dark mode text visibility
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    /* Top Hero Banner */
    .hero-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 60%, #2563eb 100%);
        border-radius: 12px;
        padding: 24px 28px;
        color: #ffffff !important;
        margin-bottom: 16px;
        box-shadow: 0 4px 18px rgba(15, 23, 42, 0.22);
    }
    .hero-title {
        color: #ffffff !important;
        font-size: 2.1rem;
        font-weight: 700;
        margin: 0 0 6px 0;
        letter-spacing: -0.5px;
    }
    .hero-subtitle {
        color: #cbd5e1 !important;
        font-size: 1.0rem;
        margin: 0 0 14px 0;
        line-height: 1.5;
        font-weight: 400;
    }
    .badge-pill {
        display: inline-block;
        padding: 5px 13px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 8px;
        margin-bottom: 6px;
        background: rgba(255, 255, 255, 0.14);
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.28);
        backdrop-filter: blur(4px);
    }
    
    /* Theme-Adaptive Legend Box (Crystal-clear contrast in light AND dark mode) */
    .legend-box {
        background: rgba(37, 99, 235, 0.08);
        border: 1px solid rgba(37, 99, 235, 0.32);
        border-left: 5px solid #2563eb;
        border-radius: 10px;
        padding: 16px 20px;
        font-size: 0.92rem;
        line-height: 1.6;
        margin-bottom: 16px;
    }
    .legend-title {
        font-weight: 700;
        font-size: 0.96rem;
        margin-bottom: 6px;
        color: inherit;
    }
    
    /* Modern Metric Cards */
    [data-testid="stMetric"] {
        background: rgba(148, 163, 184, 0.08);
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 10px;
        padding: 14px 16px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    [data-testid="stMetric"]:hover {
        border-color: rgba(59, 130, 246, 0.45);
        box-shadow: 0 4px 10px rgba(0,0,0,0.06);
    }
    
    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 600;
        font-size: 0.95rem;
        padding: 10px 18px;
        border-radius: 8px 8px 0 0;
    }
    
    .status-open { color: #ef4444; font-weight: bold; }
    .status-resolved { color: #10b981; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Render Hero Banner
st.markdown("""
<div class="hero-banner">
    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
        <div>
            <div class="hero-title">🏙️ CivicGraph</div>
            <div class="hero-subtitle">Bangalore Municipal Grievance Intelligence & Graph-Native Root Cause Redressal Engine</div>
        </div>
        <div>
            <span class="badge-pill">🏛️ BBMP Sahaaya Open Data</span>
            <span class="badge-pill">🌐 Bilingual EN / ಕನ್ನಡ</span>
            <span class="badge-pill">⚡ Neo4j Graph Aura</span>
            <span class="badge-pill">📅 H1 2024 vs H1 2025</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Global UI Legend with guaranteed visibility across all themes
st.markdown("""
<div class="legend-box">
    <div class="legend-title">📋 Data Provenance & Modeling Legend</div>
    <div>
        • <strong>Real Data (BBMP Sahaaya Open Data):</strong> 198 canonical ward boundaries, grievance records (ID, date, category, status), and year-over-year volume aggregations.<br>
        • <strong>Synthetic Modeling:</strong> Individual complaint text descriptions (including 20% Kannada texts flagged <code>kn</code>), municipal infrastructure models, work orders, and contractors ending in <em>(modeled)</em>.
    </div>
</div>
""", unsafe_allow_html=True)

# Data Notes Expander
with st.expander("ℹ️ Data Notes & Reporting Methodology", expanded=False):
    st.markdown(f"""
    - **Reporting Growth**: Grievance volumes reflect **registered complaints**, which may include growth in citizen reporting channels (e.g., BBMP WhatsApp Chatbot and Sahaaya 2.0 rollout).
    - **Like-for-Like Timeframe**: All year-over-year trends compare **Jan 1 – Jun 19, 2024 vs Jan 1 – Jun 19, 2025** labeled `"H1 2024 vs H1 2025 (Jan 1-Jun 19)"`. Full-year 2024 figures are provided purely as supplementary context.
    - **Citywide Benchmark**: Registered complaints across all 198 BBMP wards grew by **+{CITYWIDE_H1_PCT_CHANGE}%** year-over-year.
    - **Complaint Status**: Unresolved complaints include `Registered`, `ReOpen`, and `In Progress`. Resolved complaints are marked `Closed`.
    - **Causality Disclaimer**: Modeled work orders and infrastructure chains represent synthetic simulations. **Association is not causation.**
    """)

# Sidebar: Interactive Assistant
with st.sidebar:
    st.header("🤖 CivicGraph Agent")
    st.caption("Municipal intelligence assistant with live graph tool execution.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "Hello! I can analyze registered civic grievances across Bangalore, investigate root cause correlations, and simulate what-if work order delays. Try asking about **Thanisandra solid waste** or **citywide trends**."}
        ]

    # Quick prompt shortcuts
    st.markdown("**Quick Inquiries:**")
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        if st.button("🚨 Thanisandra Surge", use_container_width=True):
            st.session_state.pending_prompt = "What factors contribute to the recent volume surge in solid waste complaints in Thanisandra above the citywide pattern?"
    with col_q2:
        if st.button("📈 Rising Issues", use_container_width=True):
            st.session_state.pending_prompt = "Show me the top rising registered complaints across Bangalore wards."

    if st.button("⏱️ Simulate WO-101 Delay", use_container_width=True):
        st.session_state.pending_prompt = "Simulate the downstream impact if work order WO-101 is delayed."

    # Display conversation
    chat_container = st.container(height=420)
    for msg in st.session_state.chat_history:
        with chat_container.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Ask about wards, trends, or root causes...")
    if "pending_prompt" in st.session_state and st.session_state.pending_prompt:
        user_input = st.session_state.pending_prompt
        del st.session_state.pending_prompt

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with chat_container.chat_message("user"):
            st.markdown(user_input)

        with chat_container.chat_message("assistant"):
            with st.spinner("Analyzing graph relationships..."):
                response = run_agent_turn(st.session_state.chat_history)
                st.markdown(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})

# ---------------------------------------------------------
# VISIBLE "ASK THE CITY" PANEL
# ---------------------------------------------------------
with st.container():
    st.subheader("🤖 Ask the City: Municipal Intelligence Engine")
    st.caption("Ask natural language civic questions in English or Kannada (ಕನ್ನಡ) about wards, trends, root causes, or work orders.")

    col_inp, col_btn = st.columns([5, 1])
    with col_inp:
        main_q = st.text_input("Enter inquiry:", value="", placeholder="e.g., Why is Thanisandra's garbage problem rising? or ಥಣಿಸಂದ್ರದಲ್ಲಿ ಕಸದ ಸಮಸ್ಯೆ ಏಕೆ ಹೆಚ್ಚುತ್ತಿದೆ?", key="main_inquiry_input")
    with col_btn:
        st.write("")
        run_btn = st.button("🚀 Ask", type="primary", use_container_width=True)

    # Prompt Pills
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("Thanisandra Garbage (EN)", key="pill1", use_container_width=True):
            st.session_state.main_query_to_run = "Why is Thanisandra's garbage problem rising?"
    with c2:
        if st.button("ಥಣಿಸಂದ್ರ ಕಸದ ಸಮಸ್ಯೆ (KN)", key="pill2", use_container_width=True):
            st.session_state.main_query_to_run = "ಥಣಿಸಂದ್ರದಲ್ಲಿ ಕಸದ ಸಮಸ್ಯೆ ಏಕೆ ಹೆಚ್ಚುತ್ತಿದೆ?"
    with c3:
        if st.button("ವಿಳಂಬಿತ ಕೆಲಸದ ಆದೇಶಗಳು (KN)", key="pill3", use_container_width=True):
            st.session_state.main_query_to_run = "ಯಾವ ಕೆಲಸದ ಆದೇಶಗಳು ವಿಳಂಬವಾಗಿವೆ?"
    with c4:
        if st.button("Highest Complaints (EN)", key="pill4", use_container_width=True):
            st.session_state.main_query_to_run = "Which ward in Bengaluru has received the most complaints?"

    target_query = None
    if run_btn and main_q.strip():
        target_query = main_q.strip()
    elif "main_query_to_run" in st.session_state and st.session_state.main_query_to_run:
        target_query = st.session_state.main_query_to_run
        del st.session_state.main_query_to_run

    if target_query:
        with st.spinner("Analyzing graph and executing queries..."):
            agent_result = ask_city(target_query)
        st.markdown(f"**Inquiry:** `{target_query}`")
        if agent_result.get("english_translation"):
            st.caption(f"**English Translation:** {agent_result['english_translation']}")
        st.markdown(agent_result["answer"])

        with st.expander("🛠️ Tools Called & Execution Trace", expanded=True):
            if agent_result.get("tools_called"):
                for t in agent_result["tools_called"]:
                    st.markdown(f"- **Tool**: `{t['tool']}`")
                    st.json(t["args"])
            else:
                st.info("No external tools called.")
    st.markdown("---")

# 5 Main Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 City Overview",
    "⚠️ Active Incidents",
    "🔍 Root Cause Tracing",
    "⚡ What-If Analysis",
    "📈 Year-Over-Year Trends"
])

# ---------------------------------------------------------
# TAB 1: City Overview
# ---------------------------------------------------------
with tab1:
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); border-radius: 10px; padding: 18px 24px; color: #ffffff !important; margin-bottom: 20px; box-shadow: 0 4px 14px rgba(30, 58, 138, 0.2);">
        <div style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; color: #93c5fd !important; margin-bottom: 4px;">⚡ Key Narrative Anchor</div>
        <div style="font-size: 1.25rem; font-weight: 700; line-height: 1.4; color: #ffffff !important;">Thanisandra: 3.83x own baseline vs citywide 2.58x — about 1.5x relative (1.48x on the 24-week baseline, about 1.4x on the 4-week one)</div>
        <div style="font-size: 0.88rem; color: #e0e7ff !important; margin-top: 6px;">141 registered complaints in Week 24 vs 36.8/wk baseline (excluding peak week) | Citywide Solid Waste rose 2.58x (from 1,436.6/wk to 3,702)</div>
    </div>
    """, unsafe_allow_html=True)
    st.subheader("Bangalore Citywide Redressal Pulse")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="Citywide Registered Complaints Growth",
            value=f"+{CITYWIDE_H1_PCT_CHANGE}%",
            delta="H1 2024 vs H1 2025"
        )
    with col2:
        st.metric(
            label="Top Surge Above Citywide Pattern",
            value="Thanisandra",
            delta=f"{SPIKE_MULTIPLIER}x vs baseline (above citywide pattern)"
        )
    with col3:
        st.metric(
            label="Recent Real Complaints Loaded",
            value="2,487",
            help="Real BBMP complaints from the 14-day window (Jun 6–Jun 19, 2025) across the top 8 wards (no sampling cap)."
        )
    with col4:
        st.metric(
            label="Formed Incidents",
            value="57",
            help="Ward + Issue clusters with at least 5 registered complaints in the window."
        )

    st.markdown("---")
    st.subheader("Top 8 Wards by Registered Grievance Volume")
    st.caption("Comparison period: Jan 1 – Jun 19, 2024 vs Jan 1 – Jun 19, 2025. Full-year 2024 provided as supplementary context.")

    top8_data = [
        {"Rank": 1, "Ward Name": "Horamavu", "H1 2024": 1580, "H1 2025": 3128, "% Change": "+97.97%", "vs Citywide": "+33.98%", "Full-Year 2024": 4349},
        {"Rank": 2, "Ward Name": "Jnanabharathi Ward", "H1 2024": 1995, "H1 2025": 2842, "% Change": "+42.46%", "vs Citywide": "-21.53%", "Full-Year 2024": 4987},
        {"Rank": 3, "Ward Name": "Thanisandra", "H1 2024": 1417, "H1 2025": 2480, "% Change": "+75.02%", "vs Citywide": "+11.03%", "Full-Year 2024": 3723},
        {"Rank": 4, "Ward Name": "Hemmigepura", "H1 2024": 1470, "H1 2025": 2415, "% Change": "+64.29%", "vs Citywide": "+0.30%", "Full-Year 2024": 3940},
        {"Rank": 5, "Ward Name": "Jakkur", "H1 2024": 1398, "H1 2025": 2408, "% Change": "+72.25%", "vs Citywide": "+8.26%", "Full-Year 2024": 3978},
        {"Rank": 6, "Ward Name": "Rajarajeshwari Nagar", "H1 2024": 1529, "H1 2025": 2401, "% Change": "+57.03%", "vs Citywide": "-6.96%", "Full-Year 2024": 3912},
        {"Rank": 7, "Ward Name": "Begur", "H1 2024": 1515, "H1 2025": 2338, "% Change": "+54.32%", "vs Citywide": "-9.67%", "Full-Year 2024": 3755},
        {"Rank": 8, "Ward Name": "Bellandur", "H1 2024": 1123, "H1 2025": 2257, "% Change": "+100.98%", "vs Citywide": "+36.99%", "Full-Year 2024": 3679},
    ]
    st.dataframe(pd.DataFrame(top8_data), hide_index=True, use_container_width=True)

# ---------------------------------------------------------
# TAB 2: Active Incidents
# ---------------------------------------------------------
with tab2:
    st.subheader("Active Incidents in the Loaded 14-Day Window")
    st.caption("Status as of data export; recent complaints are more likely still open.")

    all_wards = ["All"] + get_all_wards()
    all_issues = ["All"] + get_all_issue_types()

    col_w, col_i = st.columns(2)
    with col_w:
        sel_w = st.selectbox("Filter by Ward", all_wards, index=all_wards.index("Thanisandra") if "Thanisandra" in all_wards else 0)
    with col_i:
        sel_i = st.selectbox("Filter by Issue Type", all_issues, index=0)

    ward_param = None if sel_w == "All" else sel_w
    issue_param = None if sel_i == "All" else sel_i

    incidents_list = get_incidents(ward_param, issue_param)

    if incidents_list:
        df_inc = pd.DataFrame(incidents_list)[['incident_id', 'ward', 'issue_type', 'complaint_count', 'open_count', 'resolved_count', 'source']]
        df_inc['open_share'] = (df_inc['open_count'] / df_inc['complaint_count']).map(lambda x: f"{x:.1%}")
        df_inc = df_inc.rename(columns={
            'incident_id': 'Incident ID',
            'ward': 'Ward',
            'issue_type': 'Issue Type',
            'complaint_count': 'Total Complaints',
            'open_count': 'Open Count',
            'resolved_count': 'Resolved Count',
            'open_share': 'Open Share',
            'source': 'Source'
        })[['Incident ID', 'Ward', 'Issue Type', 'Total Complaints', 'Open Count', 'Resolved Count', 'Open Share', 'Source']]
        st.dataframe(df_inc, hide_index=True, use_container_width=True)
        st.caption("Status as of data export; recent complaints are more likely still open.")

        # Weekly registered solid-waste complaints line chart (weeks 15-24 indexed to baseline = 1.0)
        st.markdown("---")
        st.subheader("Weekly Solid Waste Grievances: Thanisandra vs Citywide (Indexed to Baseline = 1.0)")
        st.caption("Weekly registered solid waste complaints indexed to baseline = 1.0 (weeks 15–24). Week 25 is partial (Jun 16–19) and excluded from the indexed comparison. Thanisandra baseline (excl. peak week) = 36.8/wk; Citywide baseline = 1,436.6/wk. In Week 24, Thanisandra rose to 3.83x above the citywide pattern (2.58x).")
        
        indexed_weekly_data = [
            {"Week": "Week 15", "Thanisandra (Solid Waste)": 0.81, "Citywide (Solid Waste)": 1.06},
            {"Week": "Week 16", "Thanisandra (Solid Waste)": 0.76, "Citywide (Solid Waste)": 0.95},
            {"Week": "Week 17", "Thanisandra (Solid Waste)": 0.76, "Citywide (Solid Waste)": 1.20},
            {"Week": "Week 18", "Thanisandra (Solid Waste)": 0.95, "Citywide (Solid Waste)": 0.95},
            {"Week": "Week 19", "Thanisandra (Solid Waste)": 1.49, "Citywide (Solid Waste)": 0.81},
            {"Week": "Week 20", "Thanisandra (Solid Waste)": 1.03, "Citywide (Solid Waste)": 0.92},
            {"Week": "Week 21", "Thanisandra (Solid Waste)": 1.52, "Citywide (Solid Waste)": 1.46},
            {"Week": "Week 22", "Thanisandra (Solid Waste)": 1.38, "Citywide (Solid Waste)": 1.20},
            {"Week": "Week 23", "Thanisandra (Solid Waste)": 1.38, "Citywide (Solid Waste)": 1.39},
            {"Week": "Week 24", "Thanisandra (Solid Waste)": 3.83, "Citywide (Solid Waste)": 2.58},
        ]
        df_weekly_chart = pd.DataFrame(indexed_weekly_data).set_index("Week")
        st.line_chart(df_weekly_chart)

        st.markdown("---")
        st.subheader("Incident Complaint Inspector")
        inc_ids = [r['incident_id'] for r in incidents_list]
        selected_inc = st.selectbox("Select Incident to inspect complaints", inc_ids, index=0)

        details = get_incident_details(selected_inc)
        if details:
            st.markdown(f"**Incident {details['incident_id']}**: {details['ward']} — {details['issue_type']} ({details['complaint_count']} total registered complaints)")
            st.markdown(f"**Resolution Status**: :red[{details['open_count']} Open] | :green[{details['resolved_count']} Resolved]")
            st.caption(details.get('status_note', 'Status as of data export; recent complaints are more likely still open.'))

            st.write("Recent Individual Grievance Records:")
            st.caption("Individual grievance text descriptions are synthetic text modeled from real sub-category records.")
            complaints_table = []
            for c in details.get("complaints", [])[:15]:
                complaints_table.append({
                    "Complaint ID": c["id"],
                    "Date Logged": c["created_at"],
                    "Sub-Category": c["sub_category"],
                    "Status": c["status"],
                    "Language": "Kannada" if c["language"] == "kn" else "English",
                    "Grievance Text (synthetic text)": c["text"],
                    "Text Source": "synthetic text"
                })
            st.dataframe(pd.DataFrame(complaints_table), hide_index=True, use_container_width=True)
    else:
        st.info("No incidents found matching the selected filters.")

# ---------------------------------------------------------
# TAB 3: Root Cause Tracing
# ---------------------------------------------------------
with tab3:
    st.subheader("Root Cause Correlation & Evidence Scoring")
    st.caption("Associates real incident clusters with modeled infrastructure dependencies and delayed work orders.")

    incidents_all = get_incidents()
    inc_options = [f"{r['incident_id']} - {r['ward']} ({r['issue_type']})" for r in incidents_all]
    
    # Default to INC-001 (Thanisandra)
    default_idx = 0
    for idx, opt in enumerate(inc_options):
        if "Thanisandra" in opt and "Solid Waste" in opt:
            default_idx = idx
            break

    chosen_opt = st.selectbox("Select Incident to Trace", inc_options, index=default_idx)
    target_inc_id = chosen_opt.split(" ")[0]

    if st.button("🔍 Execute Root Cause Trace", type="primary"):
        with st.spinner("Traversing dependency chains..."):
            trace_res = trace_root_cause(target_inc_id)

        if "error" in trace_res:
            st.error(trace_res["error"])
        else:
            st.success(f"Analysis complete for {trace_res['incident_id']} ({trace_res['ward']} - {trace_res['issue_type']})")

            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("Total Incident Volume", f"{trace_res['complaint_count']} complaints", f"{trace_res['open_count']} open / {trace_res['resolved_count']} resolved")
            with col_m2:
                st.metric("YoY Trend for Issue", f"{trace_res['pct_change']:+.1f}%", f"vs Citywide: {trace_res['vs_citywide']:+}%")
            with col_m3:
                tot_score = trace_res.get("evidence_score", 0)
                rd_score = trace_res.get("real_data_score", 0)
                md_score = trace_res.get("modeled_link_score", 0)
                st.metric("Evidence Score", f"{tot_score} / 95", f"Real: {rd_score}/40 | Model: {md_score}/55")

            st.caption(f"ℹ️ {trace_res['baseline_note']}")
            st.caption(f"📌 {trace_res['status_caption']}")

            # Baseline Sensitivity Analysis
            bs = trace_res.get("baseline_sensitivity", {})
            if bs:
                st.markdown("#### Baseline Sensitivity Analysis")
                st.caption("Evaluating peak week volume against dual baselines: 24-week average (excluding peak week) vs previous 4-week average.")
                bs_data = [
                    {
                        "Benchmark": f"{trace_res['ward']} ({trace_res['issue_type']})",
                        "Peak Week Volume": f"{bs.get('ward_peak_count', 0)} complaints",
                        "24-Wk Baseline (excl. peak)": f"{bs.get('ward_24wk_baseline_excl_peak', 0.0):.1f}/wk",
                        "Ratio vs 24-Wk Baseline": f"{bs.get('ward_24wk_ratio', 1.0):.2f}x",
                        "Previous 4-Wk Average": f"{bs.get('ward_prev_4wk_avg', 0.0):.1f}/wk",
                        "Ratio vs Prev 4-Wk Avg": f"{bs.get('ward_prev_4wk_ratio', 1.0):.2f}x"
                    },
                    {
                        "Benchmark": f"Citywide ({trace_res['issue_type']})",
                        "Peak Week Volume": f"{bs.get('citywide_peak_count', 0)} complaints",
                        "24-Wk Baseline (excl. peak)": f"{bs.get('citywide_24wk_baseline_excl_peak', 0.0):.1f}/wk",
                        "Ratio vs 24-Wk Baseline": f"{bs.get('citywide_24wk_ratio', 1.0):.2f}x",
                        "Previous 4-Wk Average": f"{bs.get('citywide_prev_4wk_avg', 0.0):.1f}/wk",
                        "Ratio vs Prev 4-Wk Avg": f"{bs.get('citywide_prev_4wk_ratio', 1.0):.2f}x"
                    }
                ]
                st.dataframe(pd.DataFrame(bs_data), hide_index=True, use_container_width=True)
                st.info("Citywide same-category registrations also rose that week.")

            st.markdown("---")
            top_cand = trace_res.get("top_candidate")
            if top_cand:
                st.subheader("Primary Modeled Contributing Factor")
                st.markdown(f"""
                - **Work Order**: `{top_cand['work_order_id']}` — **{top_cand['work_order_name']}**
                - **Status**: :red[**{top_cand['status']}**] ({top_cand['delay_days']} days overdue)
                - **Target Infrastructure**: **{top_cand['affected_infrastructure']}** ({top_cand['infrastructure_type']})
                - **Assigned Contractor**: {top_cand['contractor']}
                - **Project**: {top_cand['project']}
                """)

                st.markdown(f"#### Split Evidence Score: `{tot_score} / 95`")
                st.markdown(f"- **Real-Data Evidence**: `{rd_score} / 40 pts` (complaint count, spike vs baseline, trend vs citywide)")
                st.markdown(f"- **Modeled-Link Evidence**: `{md_score} / 55 pts` (work order, contributes-to, dependency chain)")

                st.markdown("##### Detailed Fired Rules:")
                for rule in trace_res.get("rules_fired", []):
                    cat = rule.get("category", "")
                    st.markdown(f"- **+{rule['points']} pts** `[{cat}]` (`{rule['rule']}`): {rule['description']}")

                st.warning(f"⚠️ **Evidence Rule Note**: {trace_res['evidence_rule_note']}")
            else:
                st.info("No active work orders mapped to this issue type.")

            st.markdown("---")
            st.subheader("Interactive Incident Dependency Subgraph")
            st.caption("Visualizing Incident, Ward, Issue, Work Orders, and Infrastructure dependencies (pyvis graph).")
            graph_data = graph_for_incident(target_inc_id)
            if graph_data.get("nodes"):
                net = Network(height="460px", width="100%", bgcolor="#ffffff", font_color="#2c3e50", directed=True)
                for n in graph_data["nodes"]:
                    net.add_node(
                        n["id"],
                        label=n["label"],
                        title=n["label"],
                        color=n["color"],
                        shape="box" if n.get("group") in ("Incident", "WorkOrder") else "ellipse",
                        borderWidth=2
                    )
                for e in graph_data["edges"]:
                    net.add_edge(
                        e["from"],
                        e["to"],
                        label=e.get("label", ""),
                        title=e.get("label", ""),
                        arrows="to",
                        color="#7f8c8d"
                    )
                net.set_options("""
                var options = {
                  "physics": {
                    "barnesHut": {
                      "gravitationalConstant": -3500,
                      "centralGravity": 0.25,
                      "springLength": 100,
                      "springConstant": 0.04
                    },
                    "minVelocity": 0.75
                  }
                }
                """)
                html = net.generate_html()
                components.html(html, height=480, scrolling=True)

# ---------------------------------------------------------
# TAB 4: What-If Analysis
# ---------------------------------------------------------
with tab4:
    st.subheader("What-If Simulation: Downstream Work Order Delay Impact")
    st.caption("Walks DEPENDS_ON*1..3 infrastructure dependencies and tallies real grievances in the connected catchment area.")

    work_orders = get_all_work_orders()
    wo_options = [f"{wo['id']} - {wo['name']} [{wo['status']}]" for wo in work_orders]
    selected_wo_opt = st.selectbox("Select Work Order to Simulate", wo_options, index=0)
    target_wo_id = selected_wo_opt.split(" ")[0]

    if st.button("⚡ Simulate Downstream Delay Impact", type="primary"):
        sim_res = what_if_delay(target_wo_id)
        if "error" in sim_res:
            st.error(sim_res["error"])
        else:
            st.markdown(f"### Simulation Results for `{sim_res['work_order_id']}`")
            st.markdown(f"**Target Facility**: {sim_res['target_infrastructure']} | **Status**: {sim_res['status']} ({sim_res['delay_days']} days delay)")

            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Real Complaints in Catchment", sim_res["total_real_complaints_impacted"])
            with c2:
                st.metric("Open Complaints", sim_res["total_open_complaints"])
            with c3:
                st.metric("Resolved Complaints", sim_res["total_resolved_complaints"])

            st.caption(f"📌 {sim_res['status_caption']}")
            st.caption(f"⚠️ {sim_res['evidence_note']}")

            st.markdown("#### Connected Dependent Infrastructure Chain (DEPENDS_ON*1..3):")
            dep_infras = sim_res.get("dependent_infrastructure", [])
            if dep_infras:
                st.dataframe(pd.DataFrame(dep_infras), hide_index=True, use_container_width=True)

            st.markdown("#### Real Grievance Catchment by Ward:")
            st.dataframe(pd.DataFrame(sim_res.get("ward_breakdown", [])), hide_index=True, use_container_width=True)

# ---------------------------------------------------------
# TAB 5: Year-Over-Year Trends
# ---------------------------------------------------------
with tab5:
    st.subheader("Year-Over-Year Trends: H1 2024 vs H1 2025")
    st.caption("Comparison timeframe: Jan 1 – Jun 19, 2024 vs Jan 1 – Jun 19, 2025. All metrics reflect registered complaints.")

    all_wards_clean = get_all_wards()
    def_idx = all_wards_clean.index("Thanisandra") if "Thanisandra" in all_wards_clean else 0
    chosen_trend_ward = st.selectbox("Select Ward to view Trends", all_wards_clean, index=def_idx)

    trends_data = trend_for_ward(chosen_trend_ward)
    if trends_data:
        df_trends = pd.DataFrame(trends_data)

        # Bar chart comparison
        chart_df = df_trends.melt(
            id_vars=['issue_type'],
            value_vars=['h1_2024_registered_complaints', 'h1_2025_registered_complaints'],
            var_name='Period',
            value_name='Registered Complaints'
        )
        chart_df['Period'] = chart_df['Period'].replace({
            'h1_2024_registered_complaints': 'H1 2024 (Jan 1-Jun 19)',
            'h1_2025_registered_complaints': 'H1 2025 (Jan 1-Jun 19)'
        })

        st.bar_chart(
            chart_df,
            x='issue_type',
            y='Registered Complaints',
            color='Period',
            use_container_width=True
        )

        st.markdown(f"#### Detailed Issue Breakdown for {chosen_trend_ward}:")
        display_trends = df_trends[[
            'issue_type',
            'h1_2024_registered_complaints',
            'h1_2025_registered_complaints',
            'ward_pct_change',
            'citywide_pct_change',
            'vs_citywide',
            'full_year_2024_context'
        ]].rename(columns={
            'issue_type': 'Issue Type',
            'h1_2024_registered_complaints': 'H1 2024 Registered Complaints',
            'h1_2025_registered_complaints': 'H1 2025 Registered Complaints',
            'ward_pct_change': 'Ward % Change',
            'citywide_pct_change': 'Citywide Same-Issue % Change',
            'vs_citywide': 'Percentage Points vs Citywide',
            'full_year_2024_context': 'Full Year 2024 Total'
        })
        st.dataframe(display_trends, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.subheader("Top Rising Registered Complaints Across All Bangalore Wards")
        st.caption(f"Ward + Issue pairs with largest percentage growth in registered complaints (Citywide benchmark: +{CITYWIDE_H1_PCT_CHANGE}%).")
        top_rising = top_rising_issues(10)
        df_rising = pd.DataFrame(top_rising).rename(columns={
            'ward': 'Ward',
            'issue_type': 'Issue Type',
            'h1_2024_registered_complaints': 'H1 2024 Registered Complaints',
            'h1_2025_registered_complaints': 'H1 2025 Registered Complaints',
            'ward_pct_change': 'Ward % Change',
            'citywide_pct_change': 'Citywide Same-Issue % Change',
            'vs_citywide': 'Percentage Points vs Citywide',
            'absolute_increase': 'Absolute Volume Increase'
        })[['Ward', 'Issue Type', 'H1 2024 Registered Complaints', 'H1 2025 Registered Complaints', 'Ward % Change', 'Citywide Same-Issue % Change', 'Percentage Points vs Citywide', 'Absolute Volume Increase']]
        st.dataframe(df_rising, hide_index=True, use_container_width=True)

