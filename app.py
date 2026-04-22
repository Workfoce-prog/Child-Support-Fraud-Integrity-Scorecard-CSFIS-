
import json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"
CSS_PATH = ASSETS_DIR / "style.css"
FAVICON_PATH = ASSETS_DIR / "favicon.ico"

st.set_page_config(
    page_title="Child Support Fraud & Integrity Scorecard",
    page_icon=str(FAVICON_PATH) if FAVICON_PATH.exists() else "⚖️",
    layout="wide",
)

POSSIBLE_DATA_PATHS = [
    BASE_DIR / "data" / "mock_child_support_cases.csv",
    Path.cwd() / "data" / "mock_child_support_cases.csv",
    BASE_DIR / "mock_child_support_cases.csv",
    Path.cwd() / "mock_child_support_cases.csv",
]
POSSIBLE_ZIP_PATHS = [
    BASE_DIR / "data" / "zip_reference.csv",
    Path.cwd() / "data" / "zip_reference.csv",
    BASE_DIR / "zip_reference.csv",
    Path.cwd() / "zip_reference.csv",
]
POSSIBLE_OVERRIDE_PATHS = [
    BASE_DIR / "county_overrides_template.json",
    Path.cwd() / "county_overrides_template.json",
]

RAG_COLORS = {
    "Low": "#22c55e",
    "Moderate": "#eab308",
    "High": "#f97316",
    "Critical": "#ef4444",
}


def first_existing_path(paths):
    for path in paths:
        if path.exists():
            return path
    return None


@st.cache_data
def load_data(uploaded_file=None):
    if uploaded_file is not None:
        return pd.read_csv(uploaded_file)
    data_path = first_existing_path(POSSIBLE_DATA_PATHS)
    if data_path is None:
        raise FileNotFoundError(
            "Could not find mock_child_support_cases.csv. Expected it in a data/ folder beside app.py or in the working directory. "
            "Upload a CSV in the sidebar or make sure the repo includes data/mock_child_support_cases.csv."
        )
    return pd.read_csv(data_path)


@st.cache_data
def load_zip_reference():
    zip_path = first_existing_path(POSSIBLE_ZIP_PATHS)
    if zip_path is None:
        return pd.DataFrame()
    return pd.read_csv(zip_path)


@st.cache_data
def load_overrides():
    override_path = first_existing_path(POSSIBLE_OVERRIDE_PATHS)
    if override_path is None:
        return {
            "default_thresholds": {"low_max": 29, "moderate_max": 59, "high_max": 79},
            "county_overrides": {},
        }
    with open(override_path, "r", encoding="utf-8") as f:
        return json.load(f)


def rag_label(score, thresholds):
    if score <= thresholds["low_max"]:
        return "Low"
    if score <= thresholds["moderate_max"]:
        return "Moderate"
    if score <= thresholds["high_max"]:
        return "High"
    return "Critical"


def distance_bucket(x):
    if x < 25:
        return "<25"
    if x < 100:
        return "25-99"
    if x < 300:
        return "100-299"
    if x < 1000:
        return "300-999"
    return "1000+"


def compute_distance_score(distance):
    conditions = [
        distance < 25,
        (distance >= 25) & (distance < 100),
        (distance >= 100) & (distance < 300),
        (distance >= 300) & (distance < 1000),
        distance >= 1000,
    ]
    values = [10, 30, 60, 80, 100]
    return np.select(conditions, values, default=30)


def recompute_scores(df):
    out = df.copy()
    out["distance_score"] = compute_distance_score(out["distance_miles"])
    income_level = np.clip(out["monthly_income_ncp"] / 100, 10, 100)
    out["travel_cost_index"] = np.clip(out["distance_miles"] / 12, 0, 100)
    out["distance_burden"] = np.clip(out["distance_score"] * (out["travel_cost_index"] / income_level), 0, 100)

    out["ncp_risk"] = (
        0.20 * out["payment_irregularity"]
        + 0.15 * out["income_volatility"]
        + 0.20 * out["employment_mismatch"]
        + 0.15 * out["arrears_growth"]
        + 0.15 * out["distance_score"]
        + 0.15 * out["mobility_risk"]
    )

    out["cp_risk"] = (
        0.25 * out["benefit_overlap"]
        + 0.20 * out["household_mismatch"]
        + 0.15 * out["income_discrepancy"]
        + 0.20 * out["custody_reporting_flag"]
        + 0.10 * out["distance_score"]
        + 0.10 * out["interstate_complexity"]
    )

    out["system_risk"] = (
        0.25 * out["data_lag"]
        + 0.25 * out["order_accuracy_gap"]
        + 0.20 * out["enforcement_fit"]
        + 0.15 * out["interstate_delay"]
        + 0.15 * out["distance_burden"]
    )

    out["total_risk"] = 0.40 * out["ncp_risk"] + 0.30 * out["cp_risk"] + 0.30 * out["system_risk"]
    return out


if CSS_PATH.exists():
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

head1, head2 = st.columns([0.18, 0.82])
with head1:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), use_container_width=True)
with head2:
    st.markdown("<div class='main-title'>Child Support Fraud &amp; Integrity Scorecard</div>", unsafe_allow_html=True)
    st.markdown("<div class='subtle-caption'>Distance-adjusted framework for CP risk, NCP risk, and structural/system integrity in child support cases.</div>", unsafe_allow_html=True)

with st.sidebar:
    st.header("Controls")
    uploaded_file = st.file_uploader("Upload a CSV to test your own cases", type=["csv"])
    overrides = load_overrides()

try:
    source_df = load_data(uploaded_file)
except FileNotFoundError as e:
    st.error(str(e))
    st.info("Fix: confirm the repo includes data/mock_child_support_cases.csv, or upload a CSV from the sidebar.")
    st.stop()

with st.sidebar:
    selected_county = st.selectbox("County threshold profile", ["Default"] + sorted(source_df["county"].dropna().unique().tolist()))
    thresholds = overrides["default_thresholds"].copy()
    if selected_county != "Default":
        thresholds.update(overrides.get("county_overrides", {}).get(selected_county, {}))

    counties = sorted(source_df["county"].dropna().unique().tolist())
    regions = sorted(source_df["region"].dropna().unique().tolist())
    selected_counties = st.multiselect("Filter counties", counties, default=counties)
    selected_regions = st.multiselect("Filter regions", regions, default=regions)

    st.markdown("**Current thresholds**")
    st.json(thresholds)

df = recompute_scores(source_df)
df["distance_bucket"] = df["distance_miles"].apply(distance_bucket)
df["rag_status"] = df["total_risk"].apply(lambda x: rag_label(x, thresholds))
df["true_fraud_signal"] = np.where(
    (df["employment_mismatch"] > 65) & (df["payment_irregularity"] > 60) & (df["monthly_income_ncp"] > 3500),
    "Likely true fraud",
    "Not primary signal",
)
df["structural_signal"] = np.where(
    (df["distance_miles"] > 300) & (df["monthly_income_ncp"] < 3000) & (df["arrears_growth"] > 55),
    "Likely structural barrier",
    "Not primary signal",
)

filtered = df[df["county"].isin(selected_counties) & df["region"].isin(selected_regions)].copy()

if filtered.empty:
    st.warning("No records match your filters.")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Cases", f"{len(filtered):,}")
k2.metric("Avg Total Risk", f"{filtered['total_risk'].mean():.1f}")
k3.metric("Critical Cases", f"{(filtered['rag_status'] == 'Critical').sum():,}")
k4.metric("Avg Distance", f"{filtered['distance_miles'].mean():.1f} mi")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Executive View", "NCP Risk", "CP Risk", "System & Distance", "Case Explorer"]
)

with tab1:
    col1, col2 = st.columns([1.15, 1])
    with col1:
        rag_counts = (
            filtered["rag_status"]
            .value_counts()
            .rename_axis("rag_status")
            .reset_index(name="cases")
        )
        rag_counts["color"] = rag_counts["rag_status"].map(RAG_COLORS)
        chart = alt.Chart(rag_counts).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
            x=alt.X("rag_status:N", sort=["Low", "Moderate", "High", "Critical"], title="Risk band"),
            y=alt.Y("cases:Q", title="Cases"),
            color=alt.Color("rag_status:N", scale=None),
            tooltip=["rag_status", "cases"],
        ).properties(height=350)
        st.altair_chart(chart, use_container_width=True)

    with col2:
        summary = filtered.groupby("county", as_index=False)[["ncp_risk", "cp_risk", "system_risk", "total_risk"]].mean()
        melt = summary.melt(id_vars="county", var_name="score_type", value_name="avg_score")
        heatmap = alt.Chart(melt).mark_rect().encode(
            x=alt.X("score_type:N", title="Score Type"),
            y=alt.Y("county:N", sort="-x", title="County"),
            color=alt.Color("avg_score:Q", title="Avg Score"),
            tooltip=["county", "score_type", alt.Tooltip("avg_score:Q", format=".1f")],
        ).properties(height=350)
        st.altair_chart(heatmap, use_container_width=True)

    st.markdown("### Signal interpretation")
    left, right = st.columns(2)
    left.info(
        "**True fraud** tends to show up with high employment mismatch, high payment irregularity, and stable or higher income."
    )
    right.info(
        "**Structural burden** tends to show up with long distance, lower income, and rising arrears even when evidence points to access or travel barriers."
    )

with tab2:
    st.subheader("NCP fraud & compliance risk")
    scatter = alt.Chart(filtered).mark_circle(size=85).encode(
        x=alt.X("distance_miles:Q", title="Distance (miles)"),
        y=alt.Y("payment_irregularity:Q", title="Payment irregularity"),
        color=alt.Color("rag_status:N", scale=None),
        size=alt.Size("monthly_income_ncp:Q", title="Monthly income"),
        tooltip=["case_id", "county", "distance_miles", "payment_irregularity", "monthly_income_ncp", "ncp_risk", "true_fraud_signal"],
    ).properties(height=400)
    st.altair_chart(scatter, use_container_width=True)

    top_ncp = filtered.sort_values("ncp_risk", ascending=False)[
        ["case_id", "county", "distance_miles", "monthly_income_ncp", "payment_irregularity", "employment_mismatch", "arrears_growth", "ncp_risk", "true_fraud_signal"]
    ].head(25)
    st.dataframe(top_ncp, use_container_width=True)

with tab3:
    st.subheader("CP integrity & reporting risk")
    cp_chart = alt.Chart(filtered).mark_circle(size=85).encode(
        x=alt.X("distance_miles:Q", title="Distance (miles)"),
        y=alt.Y("custody_reporting_flag:Q", title="Custody reporting flag"),
        color=alt.Color("rag_status:N", scale=None),
        size=alt.Size("benefit_overlap:Q", title="Benefit overlap"),
        tooltip=["case_id", "county", "distance_miles", "custody_reporting_flag", "benefit_overlap", "cp_risk", "custody_type"],
    ).properties(height=400)
    st.altair_chart(cp_chart, use_container_width=True)

    top_cp = filtered.sort_values("cp_risk", ascending=False)[
        ["case_id", "county", "distance_miles", "benefit_overlap", "household_mismatch", "custody_reporting_flag", "interstate_complexity", "cp_risk"]
    ].head(25)
    st.dataframe(top_cp, use_container_width=True)

with tab4:
    st.subheader("System + distance burden")
    colm1, colm2 = st.columns([1, 1.1])
    with colm1:
        dist_summary = filtered.groupby("distance_bucket", as_index=False)[["distance_burden", "system_risk", "total_risk"]].mean()
        line = alt.Chart(dist_summary).mark_line(point=True).encode(
            x=alt.X("distance_bucket:N", sort=["<25", "25-99", "100-299", "300-999", "1000+"], title="Distance band"),
            y=alt.Y("system_risk:Q", title="Avg system risk"),
            tooltip=["distance_bucket", alt.Tooltip("system_risk:Q", format=".1f"), alt.Tooltip("distance_burden:Q", format=".1f"), alt.Tooltip("total_risk:Q", format=".1f")],
        ).properties(height=350)
        st.altair_chart(line, use_container_width=True)
    with colm2:
        zips = load_zip_reference()
        cp_map = filtered.merge(zips.add_prefix("cp_"), left_on="cp_zip", right_on="cp_zip", how="left")
        cp_map["color"] = cp_map["rag_status"].map({
            "Low": [34, 197, 94, 180],
            "Moderate": [234, 179, 8, 180],
            "High": [249, 115, 22, 180],
            "Critical": [239, 68, 68, 180],
        })
        cp_map = cp_map.rename(columns={"cp_lat": "lat", "cp_lon": "lon"})
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=cp_map,
            get_position="[lon, lat]",
            get_radius=12000,
            get_fill_color="color",
            pickable=True,
        )
        view_state = pdk.ViewState(latitude=46.0, longitude=-94.5, zoom=5.6, pitch=0)
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"text": "{case_id}\n{county}\nRisk: {rag_status}\nDistance: {distance_miles}"}))

    structural = filtered[filtered["structural_signal"] == "Likely structural barrier"][
        ["case_id", "county", "distance_miles", "monthly_income_ncp", "arrears_growth", "distance_burden", "system_risk", "structural_signal"]
    ].sort_values("system_risk", ascending=False)
    st.markdown("#### Cases likely driven by structural burden")
    st.dataframe(structural.head(25), use_container_width=True)

with tab5:
    st.subheader("Case explorer")
    selected_case = st.selectbox("Select case", filtered["case_id"].tolist())
    case = filtered.loc[filtered["case_id"] == selected_case].iloc[0]

    a, b, c, d = st.columns(4)
    a.metric("Total risk", f"{case['total_risk']:.1f}", case["rag_status"])
    b.metric("NCP risk", f"{case['ncp_risk']:.1f}")
    c.metric("CP risk", f"{case['cp_risk']:.1f}")
    d.metric("System risk", f"{case['system_risk']:.1f}")

    st.markdown("### Case narrative")
    st.write(
        f"""
        **{case['case_id']}** in **{case['county']} County** shows a CP-NCP living distance of **{case['distance_miles']:.1f} miles**.
        The distance score is **{case['distance_score']:.1f}**, which feeds into both fraud/integrity risk and the system burden layer.
        Current classification: **{case['rag_status']}**.
        """
    )

    radar_df = pd.DataFrame({
        "metric": ["Payment irregularity", "Income volatility", "Employment mismatch", "Arrears growth", "Distance burden", "Custody flag", "Benefit overlap", "Data lag"],
        "value": [
            case["payment_irregularity"],
            case["income_volatility"],
            case["employment_mismatch"],
            case["arrears_growth"],
            case["distance_burden"],
            case["custody_reporting_flag"],
            case["benefit_overlap"],
            case["data_lag"],
        ],
    })
    radar_chart = alt.Chart(radar_df).mark_bar().encode(
        x=alt.X("metric:N", sort=None),
        y=alt.Y("value:Q", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("value:Q", scale=alt.Scale(scheme="redyellowgreen", reverse=True), legend=None),
        tooltip=["metric", alt.Tooltip("value:Q", format=".1f")],
    ).properties(height=360)
    st.altair_chart(radar_chart, use_container_width=True)

    export_cols = [
        "case_id", "county", "region", "distance_miles", "distance_score", "ncp_risk",
        "cp_risk", "system_risk", "total_risk", "rag_status", "true_fraud_signal", "structural_signal"
    ]
    st.download_button(
        "Download filtered summary CSV",
        data=filtered[export_cols].to_csv(index=False).encode("utf-8"),
        file_name="child_support_fraud_integrity_filtered.csv",
        mime="text/csv",
    )

st.markdown("---")
st.markdown(
    """
    **Model logic**
    - **NCP risk** blends payment irregularity, income volatility, employment mismatch, arrears growth, distance score, and mobility risk.
    - **CP risk** blends benefit overlap, household mismatch, income discrepancy, custody reporting flag, distance score, and interstate complexity.
    - **System risk** blends data lag, order accuracy gap, enforcement fit, interstate delay, and distance burden.
    """
)
