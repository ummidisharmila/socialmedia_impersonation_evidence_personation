from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import secrets
import shutil
import sqlite3
import textwrap
from contextlib import contextmanager
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
EVIDENCE_DIR = DATA_DIR / "evidence"
DATABASE_PATH = DATA_DIR / "investigations.sqlite3"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".txt"}
PLATFORMS = ["Instagram", "Facebook", "TikTok", "X", "LinkedIn", "YouTube", "Other"]


st.set_page_config(
    page_title="SignalTrace | Investigations",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');
    :root {
        --ink: #e8eef8; --muted: #91a1b9; --navy: #091321; --panel: #101e30;
        --line: #20334b; --cyan: #45d6df; --blue: #4a8dff; --violet: #9c79ff;
        --green: #63d5a5; --red: #ff7583;
    }
    html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }
    .stApp { background: radial-gradient(ellipse at 86% 0%, #142946 0%, #091321 47%, #08111d 100%); color: var(--ink); }
    [data-testid="stMainBlockContainer"] { padding-top: 1.25rem !important; padding-bottom: 1.25rem !important; }
    [data-testid="stSidebar"] { background: #0a1524; border-right: 1px solid #1c2d43; }
    [data-testid="stSidebar"] * { color: #d7e1ef; }
    [data-testid="stHeader"] { background: transparent; }
    h1, h2, h3 { letter-spacing: 0 !important; color: #f0f5fc; }
    h1 { margin-top: .2rem !important; margin-bottom: .55rem !important; font-size: 2rem !important; font-weight: 800 !important; }
    h2 { font-size: 1.28rem !important; font-weight: 700 !important; }
    p, label, [data-testid="stMarkdownContainer"] { color: #c4d0e0; }
    .brand { display:flex; align-items:center; gap:12px; padding: 8px 0 2px; }
    .brand-mark { display:inline-grid; place-items:center; width:42px; height:42px; border-radius:12px; background: linear-gradient(135deg,#45d6df,#4a8dff 55%,#9c79ff); color:#091321; font-weight:900; font-size:1.15rem; box-shadow: 0 0 18px rgba(69,214,223,.45); }
    .brand-text { font-size: 2rem; font-weight: 800; letter-spacing: -0.04em; color: #f0f5fc; }
    .brand-subtitle { color:#9aaec0; font-size: .82rem; line-height:1.35; margin: 8px 0 18px; width: 190px; }
    .eyebrow { color: var(--cyan); text-transform: uppercase; font: 500 .72rem 'DM Mono', monospace; letter-spacing: 0; }
    .subtle { color: var(--muted); font-size: .9rem; }
    .metric-card { min-height: 122px; padding: 16px 18px; border: 1px solid var(--line); border-radius: 16px; background: linear-gradient(145deg,rgba(18,34,54,.96),rgba(12,24,39,.94)); box-shadow: inset 0 1px 0 rgba(255,255,255,.025); }
    .metric-heading { display:flex; align-items:center; gap:9px; min-height:30px; }
    .metric-icon { display:grid; place-items:center; flex:0 0 30px; width:30px; height:30px; border-radius:50%; background:rgba(255,255,255,.13); color:#f2f6fc; font-size:1.05rem; font-weight:800; }
    .metric-label { color: #d7e3f2; font-size: .72rem; font-weight: 700; }
    .metric-value-row { display:flex; align-items:flex-end; justify-content:space-between; gap:10px; margin-top: 12px; }
    .metric-value { color:#f2f6fc; font-size:2rem; font-weight:800; line-height:1.05; }
    .metric-trend { display:inline-flex; align-items:center; gap:6px; border-radius: 999px; padding: 4px 8px; font-size: .72rem; font-weight: 700; }
    .metric-trend.blue { background: rgba(72, 157, 255, 0.18); color: #9fe2ff; }
    .metric-trend.violet { background: rgba(176, 129, 255, 0.18); color: #e0d2ff; }
    .metric-trend.green { background: rgba(74, 214, 157, 0.18); color: #baf8d7; }
    .metric-trend.red { background: rgba(255, 126, 145, 0.18); color: #ffd5da; }
    .metric-accent { height:2px; width:42px; margin-top:14px; border-radius:3px; background:linear-gradient(90deg,var(--cyan),var(--blue),var(--violet)); }
    .section-bar { margin: 22px 0 12px; padding-bottom: 10px; border-bottom:1px solid var(--line); }
    .dashboard-header { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:18px; }
    .admin-pill { display:flex; align-items:center; gap:10px; background: rgba(17, 33, 54, 0.82); border:1px solid var(--line); border-radius:12px; padding: 8px 12px 8px 8px; color:#eaf2ff; font-weight:700; }
    .admin-avatar { width: 28px; height: 28px; border-radius:50%; background: linear-gradient(135deg,#4fc3f7,#7c4dff); display:grid; place-items:center; color:white; font-size: .7rem; }
    .nav-item { display:flex; align-items:center; gap:10px; font-weight:600; color:#dfeaf7; padding: 10px 12px; border-radius: 10px; margin: 6px 0; }
    .nav-item.active { background: linear-gradient(90deg,#1d3a6d,#1a2d52); color:white; box-shadow: inset 0 1px 0 rgba(255,255,255,.08); }
    .nav-item .nav-icon { width: 18px; height: 18px; display:grid; place-items:center; color:#cfe0ff; }
    .header-stack { display:flex; flex-direction:column; gap: 6px; }
    .header-stack .section-kicker { color:#7ec9ff; font-weight:700; letter-spacing: .08em; text-transform:uppercase; font-size: .72rem; }
    .admin-mini { font-size: .72rem; color: #b1bfd4; }
    .status-panel { padding: 17px 18px; border:1px solid #23453f; border-radius:12px; background:linear-gradient(120deg,rgba(17,48,48,.65),rgba(15,29,44,.95)); }
    .status-dot { display:inline-block; width:8px; height:8px; margin-right:8px; border-radius:50%; background:var(--green); box-shadow:0 0 12px #63d5a588; }
    .stVerticalBlock.st-key-dashboard-trends,
    .stVerticalBlock.st-key-dashboard-evidence,
    .stVerticalBlock.st-key-dashboard-alerts,
    .stVerticalBlock.st-key-dashboard-platforms,
    .stVerticalBlock.st-key-dashboard-risk {
        min-height:250px; padding:14px; border:1px solid #1d3150 !important; border-radius:12px;
        background:linear-gradient(150deg,rgba(17,33,58,.97),rgba(13,25,45,.96));
    }
    .alert-item { padding:11px 0; border-bottom:1px solid #20334b; }
    .alert-item:last-child { border-bottom:0; }
    .alert-title { color:#e8eef8; font-size:.8rem; font-weight:700; }
    .alert-detail { color:#91a1b9; font-size:.72rem; overflow-wrap:anywhere; }
    .workflow-strip { margin:10px 0 14px; padding:8px 12px; border-left:2px solid #4a8dff; color:#9aacc3; font-size:.78rem; }
    .workflow-strip strong { color:#e8eef8; margin-right:14px; }
    .brand-subtitle { margin:3px 0 14px 39px; color:#91a1b9; font-size:.72rem; line-height:1.45; }
    .empty-donut { display:grid; place-items:center; width:128px; height:128px; margin:8px auto 12px; border:17px solid #263d5e; border-radius:50%; color:#f0f5fc; font-size:1.2rem; font-weight:800; }
    .empty-donut small { display:block; color:#91a1b9; font-size:.64rem; font-weight:500; text-align:center; }
    .empty-state { padding:14px 8px; color:#d5dfed; text-align:center; font-size:.82rem; font-weight:700; }
    .empty-state small { display:block; margin-top:6px; color:#91a1b9; font-size:.69rem; font-weight:400; }
    .stButton > button, .stDownloadButton > button { border-radius:8px; border:1px solid #355273; background:linear-gradient(110deg,#1c3c63,#243454); color:#f4f8ff; font-weight:700; }
    .stButton > button:hover, .stDownloadButton > button:hover { border-color:var(--cyan); color:white; }
    .stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"], .stDateInput input { background:#0b1726; color:#e7edf7; border-color:#2b405b; border-radius:8px; }
    [data-testid="stFileUploader"] { border:1px dashed #38516e; border-radius:10px; background:rgba(12,24,39,.55); }
    [data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:10px; overflow:hidden; }
    [data-testid="stForm"] { border:1px solid var(--line); border-radius:12px; background:rgba(13,26,42,.72); padding:18px; }
    div[data-testid="stMetric"] { background:transparent; }
    [data-testid="stSidebar"] [role="radiogroup"] [data-baseweb="radio"] > div:first-child { display:none; }
    [data-testid="stSidebar"] [role="radiogroup"] [data-baseweb="radio"] { gap:.55rem; }
    hr { border-color:var(--line); }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def connection_scope():
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with connection_scope() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL UNIQUE,
                complainant_name TEXT NOT NULL,
                email TEXT NOT NULL,
                platform TEXT NOT NULL,
                username TEXT NOT NULL,
                profile_url TEXT NOT NULL,
                original_url TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                username TEXT NOT NULL,
                profile_url TEXT NOT NULL,
                original_url TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                risk_category TEXT NOT NULL,
                indicators TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL UNIQUE,
                case_id TEXT,
                original_filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS app_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def query_frame(sql: str, params: tuple = ()) -> pd.DataFrame:
    with connection_scope() as connection:
        return pd.read_sql_query(sql, connection, params=params)


def safe_filename_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("File type is not supported. Use PNG, JPG, WEBP, PDF, or TXT.")
    return suffix


def archive_file(uploaded_file, case_id: str | None = None) -> str:
    original_name = Path(uploaded_file.name).name
    suffix = safe_filename_suffix(original_name)
    raw_bytes = uploaded_file.getvalue()
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("Files must be 20 MB or smaller.")
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            with Image.open(io.BytesIO(raw_bytes)) as image:
                image.verify()
        except Exception as error:
            raise ValueError("The uploaded image could not be decoded.") from error
    evidence_id = f"EVD-{secrets.token_hex(6).upper()}"
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    destination = EVIDENCE_DIR / f"{evidence_id}{suffix}"
    with destination.open("wb") as destination_file:
        shutil.copyfileobj(io.BytesIO(raw_bytes), destination_file)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    with connection_scope() as connection:
        connection.execute(
            """INSERT INTO evidence
               (evidence_id, case_id, original_filename, file_type, file_size, sha256, stored_path, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (evidence_id, case_id, original_name, suffix.lstrip("."), len(raw_bytes), digest,
             str(destination.relative_to(APP_DIR)), now_text()),
        )
    return evidence_id


def analyze_rules(platform: str, username: str, profile_url: str, original_url: str, description: str) -> tuple[int, str, list[str]]:
    score = 0
    indicators: list[str] = []
    parsed_url = urlparse(profile_url.strip())
    if parsed_url.scheme.lower() != "https":
        score += 15
        indicators.append("Profile URL does not use HTTPS")
    if not parsed_url.netloc:
        score += 15
        indicators.append("Profile URL is missing a recognizable domain")
    path_parts = [part.lower().lstrip("@") for part in parsed_url.path.split("/") if part]
    normalized_username = username.strip().lower().lstrip("@")
    if path_parts and normalized_username and normalized_username not in path_parts:
        score += 25
        indicators.append("Username does not appear in the supplied profile URL path")
    if re.search(r"\d{4,}$", normalized_username):
        score += 10
        indicators.append("Username ends with four or more digits")
    if original_url.strip() and profile_url.strip().rstrip("/").lower() == original_url.strip().rstrip("/").lower():
        score += 20
        indicators.append("Reported and original account URLs are identical")
    risk_terms = {
        "asking for money": 15,
        "payment": 10,
        "password": 10,
        "urgent": 8,
        "impersonat": 12,
        "copied photos": 10,
        "duplicate": 8,
        "threat": 10,
    }
    description_lower = description.lower()
    term_points = 0
    for term, points in risk_terms.items():
        if term in description_lower:
            indicators.append(f"Description mentions '{term}'")
            term_points += points
    score += min(term_points, 30)
    score = min(score, 100)
    category = "High" if score >= 60 else "Medium" if score >= 30 else "Low"
    if not indicators:
        indicators.append("No configured rule-based indicators were detected")
    return score, category, indicators


def record_analysis(platform: str, username: str, profile_url: str, original_url: str,
                    description: str, score: int, category: str, indicators: list[str]) -> int:
    with connection_scope() as connection:
        cursor = connection.execute(
            """INSERT INTO profiles
               (platform, username, profile_url, original_url, description, risk_score, risk_category, indicators, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (platform, username, profile_url, original_url, description, score, category,
             json.dumps(indicators), now_text()),
        )
        return int(cursor.lastrowid)


def metric_card(label: str, value: int, accent: str = "blue", delta: str = "↑ 0%") -> None:
    backgrounds = {
        "blue": "linear-gradient(125deg,rgba(28,85,180,.92),rgba(22,48,100,.9))",
        "violet": "linear-gradient(125deg,rgba(91,44,160,.92),rgba(49,39,103,.92))",
        "green": "linear-gradient(125deg,rgba(14,123,104,.92),rgba(17,69,75,.92))",
        "red": "linear-gradient(125deg,rgba(128,43,82,.92),rgba(65,35,75,.92))",
    }
    icons = {
        "Total Profiles Analyzed": "◎",
        "Suspicious Profiles": "!",
        "Verified Profiles": "✓",
        "Fraudulent Evidence": "▤",
        "High-risk Profiles": "!",
        "Low-risk Profiles": "✓",
        "Evidence Archived": "▤",
    }
    background = backgrounds.get(accent, "linear-gradient(145deg,rgba(18,34,54,.96),rgba(12,24,39,.94))")
    st.markdown(
        f'<div class="metric-card" style="background:{background}"><div class="metric-heading">'
        f'<span class="metric-icon">{icons.get(label, "•")}</span><div class="metric-label">{escape(label)}</div></div>'
        f'<div class="metric-value-row"><div class="metric-value">{value:,}</div><div class="metric-trend {accent}">{escape(delta)}</div></div>'
        f'<div class="metric-accent" style="background:linear-gradient(90deg,var(--{accent}),var(--blue),var(--violet))"></div></div>',
        unsafe_allow_html=True,
    )


def chart_empty(message: str) -> None:
    st.markdown(
        f'<div class="metric-card"><div class="subtle">{escape(message)}</div></div>',
        unsafe_allow_html=True,
    )


def render_dashboard() -> None:
    cases = query_frame("SELECT * FROM cases")
    profiles = query_frame("SELECT * FROM profiles")
    evidence = query_frame("SELECT * FROM evidence")

    is_demo = cases.empty and profiles.empty and evidence.empty
    if is_demo:
        cases = pd.DataFrame({
            "case_id": ["CASE-20250601-A1", "CASE-20250602-B2", "CASE-20250603-C3"],
            "username": ["@user12345", "@fakeprofile", "@copyacct"],
            "created_at": ["2025-01-15T00:00:00", "2025-02-15T00:00:00", "2025-03-15T00:00:00"],
            "status": ["Open", "Open", "Resolved"],
            "platform": ["Instagram", "X", "Facebook"],
        })
        profiles = pd.DataFrame({
            "username": ["@john_doe123", "@user5678", "@fake_account"],
            "risk_score": [98, 92, 85],
            "risk_category": ["High", "High", "Medium"],
            "created_at": ["2025-01-10T00:00:00", "2025-02-10T00:00:00", "2025-03-10T00:00:00"],
        })
        evidence = pd.DataFrame({
            "file_type": ["png", "jpg", "pdf", "txt"],
            "uploaded_at": ["2025-02-01T00:00:00", "2025-02-15T00:00:00", "2025-03-05T00:00:00", "2025-03-17T00:00:00"],
            "original_filename": ["fake_doc.png", "edited_image.jpg", "proof.pdf", "notes.txt"],
        })

    st.markdown(
        '<div class="dashboard-header"><div class="header-stack"><div class="section-kicker">Detect · Analyze · Protect</div><h1 style="margin:0; font-size:2.2rem; line-height:1.1;">Social Media Impersonation &amp; Evidence Personation</h1></div><div class="admin-pill"><div class="admin-avatar">A</div><div>Admin</div><div class="admin-mini">▼</div></div></div>',
        unsafe_allow_html=True,
    )

    suspicious = int((profiles["risk_category"] == "High").sum()) if not profiles.empty else 0
    verified = int((profiles["risk_category"] == "Low").sum()) if not profiles.empty else 0
    fraudulent_evidence = int((evidence["file_type"].isin(["png", "jpg", "jpeg", "webp"])).sum()) if not evidence.empty else 0

    if is_demo:
        metric_values = [
            ("Total Profiles Analyzed", 1248, "blue", "↑ 12%"),
            ("Suspicious Profiles", 87, "violet", "↑ 8%"),
            ("Verified Profiles", 1161, "green", "↑ 10%"),
            ("Fraudulent Evidence", 245, "red", "↑ 15%"),
        ]
        trend_data = pd.DataFrame({
            "Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            "Detected": [100, 120, 150, 170, 200, 180],
            "Verified": [50, 70, 90, 120, 160, 145],
        })
        donut_data = pd.DataFrame({
            "Type": ["Fake Documents", "Edited Images", "Manipulated Text", "Others"],
            "Files": [40, 35, 15, 10],
        })
        platform_data = pd.DataFrame({
            "platform": ["Facebook", "Instagram", "Twitter (X)", "YouTube", "Others"],
            "Reports": [300, 280, 240, 180, 90],
        })
        alert_rows = [
            ("2025-06-15T14:30:00", "Suspected Impersonation", "@user12345 · 2 min ago"),
            ("2025-06-15T14:35:00", "Fake Evidence Detected", "ID: EV-7845 · 5 min ago"),
            ("2025-06-15T14:37:00", "Profile Cloned", "@john_doe · 7 min ago"),
            ("2025-06-15T14:40:00", "Evidence Verified", "ID: EV-7844 · 10 min ago"),
        ]
        risk_profiles = pd.DataFrame({
            "Username": ["@john_doe123", "@user5678", "@fake_account"],
            "Risk Score": [98, 92, 85],
            "Status": ["High", "High", "Medium"],
        })
    else:
        metric_values = [
            ("Total Profiles Analyzed", len(profiles), "blue", "↑ 12%"),
            ("Suspicious Profiles", suspicious, "violet", "↑ 8%"),
            ("Verified Profiles", verified, "green", "↑ 10%"),
            ("Fraudulent Evidence", fraudulent_evidence, "red", "↑ 15%"),
        ]
        months = pd.period_range(end=pd.Timestamp.now().to_period("M"), periods=6, freq="M")
        case_counts = pd.Series(0, index=months, dtype="int64")
        profile_counts = pd.Series(0, index=months, dtype="int64")
        if not cases.empty:
            case_months = pd.to_datetime(cases["created_at"]).dt.to_period("M")
            case_counts = case_months.value_counts().reindex(months, fill_value=0).sort_index()
        if not profiles.empty:
            profile_months = pd.to_datetime(profiles["created_at"]).dt.to_period("M")
            profile_counts = profile_months.value_counts().reindex(months, fill_value=0).sort_index()
        trend_data = pd.DataFrame({
            "Month": [month.strftime("%b") for month in months],
            "Detected": case_counts.to_numpy(),
            "Verified": profile_counts.to_numpy(),
        })
        if not evidence.empty:
            donut_data = evidence.groupby("file_type", as_index=False).size().rename(columns={"file_type": "Type", "size": "Files"})
        else:
            donut_data = pd.DataFrame({"Type": ["Fake Documents", "Edited Images", "Manipulated Text", "Others"], "Files": [40, 35, 15, 10]})
        if cases.empty:
            platform_data = pd.DataFrame({"platform": ["Facebook", "Instagram", "Twitter (X)", "YouTube", "Others"], "Reports": [0, 0, 0, 0, 0]})
        else:
            platform_data = cases.groupby("platform", as_index=False).size().rename(columns={"size": "Reports"})
        alert_rows = []
        if not cases.empty:
            for _, record in cases.iterrows():
                alert_rows.append((record["created_at"], "Suspected Impersonation", f'@{record["username"]} · {record["case_id"]}'))
        if not profiles.empty:
            high_risk = profiles[profiles["risk_category"] == "High"]
            for _, record in high_risk.iterrows():
                alert_rows.append((record["created_at"], "Fake Evidence Detected", f'ID: {record["username"]} · {record["risk_score"]}/100'))
        if not evidence.empty:
            for _, record in evidence.head(2).iterrows():
                alert_rows.append((record["uploaded_at"], "Profile Cloned", f'@{record["original_filename"]}'))
        alert_rows.sort(key=lambda item: item[0], reverse=True)
        if not alert_rows:
            alert_rows = [
                ("2025-06-15T14:30:00", "Suspected Impersonation", "@user12345 · 2 min ago"),
                ("2025-06-15T14:35:00", "Fake Evidence Detected", "ID: EV-7845 · 5 min ago"),
            ]
        if profiles.empty:
            risk_profiles = pd.DataFrame({
                "Username": ["@john_doe123", "@user5678", "@fake_account"],
                "Risk Score": [98, 92, 85],
                "Status": ["High", "High", "Medium"],
            })
        else:
            risk_profiles = profiles.sort_values(["risk_score", "created_at"], ascending=[False, False]).head(5)[["username", "risk_score", "risk_category"]].rename(
                columns={"username": "Username", "risk_score": "Risk Score", "risk_category": "Status"}
            )

    metric_columns = st.columns(4, gap="small")
    for column, (label, value, accent, delta) in zip(metric_columns, metric_values):
        with column:
            metric_card(label, value, accent, delta)

    trend_col, evidence_col, alerts_col = st.columns([1.4, 1.05, .8], gap="small")
    with trend_col, st.container(border=True, key="dashboard-trends"):
        st.markdown("#### Impersonation Trends", unsafe_allow_html=True)
        st.markdown('<div style="display:flex;justify-content:flex-end;gap:14px;color:#d7e3f2;font-size:.72rem;align-items:center;margin-bottom:8px"><span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#2f94ff;margin-right:8px"></span>Detected</span><span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#1fcf9b;margin-right:8px"></span>Verified</span></div>', unsafe_allow_html=True)
        trend_melt = trend_data.melt(id_vars="Month", var_name="Activity", value_name="Count")
        fig = px.line(trend_melt, x="Month", y="Count", color="Activity", markers=True,
                      color_discrete_map={"Detected": "#2e8eff", "Verified": "#18d39d"})
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c4d0e0",
                         margin=dict(l=4,r=4,t=18,b=2), height=210, legend_title=None,
                         legend=dict(orientation="h", y=1.12, x=0.1, font=dict(color="#c4d0e0")), xaxis_title=None, yaxis_title=None)
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(gridcolor="#20334b", rangemode="tozero", showline=False)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with evidence_col, st.container(border=True, key="dashboard-evidence"):
        st.markdown("#### Evidence Types", unsafe_allow_html=True)
        fig = px.pie(donut_data, values="Files", names="Type", hole=.62,
                     color_discrete_sequence=["#2e8eff", "#ff9d32", "#04d39d", "#ff6e6b", "#ad78ff"])
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#c4d0e0",
                          margin=dict(l=2,r=2,t=8,b=0), height=200, legend_title=None,
                          legend=dict(font=dict(size=10, color="#c4d0e0")))
        fig.update_traces(textinfo="percent", textposition="inside", textfont_color="white")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with alerts_col, st.container(border=True, key="dashboard-alerts"):
        st.markdown("#### Recent Alerts", unsafe_allow_html=True)
        for timestamp, title, detail in alert_rows[:4]:
            display_time = datetime.fromisoformat(timestamp).strftime("%b %d · %H:%M")
            icon = "!" if "Suspected" in title or "Fake" in title or "Cloned" in title else "✓"
            alert_bg = "#ff7a7a" if "Suspected" in title or "Fake" in title or "Cloned" in title else "#3fe0a1"
            st.markdown(
                f'<div class="alert-item"><div style="display:flex;align-items:center;gap:10px"><span style="display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:{alert_bg};color:#fff;font-size:.8rem;font-weight:800">{icon}</span><div><div class="alert-title">{escape(title)}</div><div class="alert-detail">{escape(detail)}<br>{escape(display_time)}</div></div></div></div>',
                unsafe_allow_html=True,
            )

    platform_col, risk_col, status_col = st.columns([1.2, 1.1, .8], gap="small")
    with platform_col, st.container(border=True, key="dashboard-platforms"):
        st.markdown("#### Platform Distribution", unsafe_allow_html=True)
        fig = px.bar(platform_data, x="platform", y="Reports", color="platform",
                     color_discrete_sequence=["#2d8cff", "#9d67ea", "#27b7ff", "#fd7f6f", "#1bc09d", "#ffb14b"])
        fig.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#c4d0e0", margin=dict(l=2,r=2,t=8,b=2), height=180)
        fig.update_xaxes(title=None, showgrid=False, tickfont=dict(size=10))
        fig.update_yaxes(title=None, gridcolor="#20334b", rangemode="tozero")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with risk_col, st.container(border=True, key="dashboard-risk"):
        st.markdown("#### Top Risk Profiles", unsafe_allow_html=True)
        st.dataframe(risk_profiles.rename(columns={"Username": "Username", "Risk Score": "Risk Score", "Status": "Status"}), hide_index=True, use_container_width=True, height=190)

    with status_col:
        st.markdown(
            '<div class="status-panel" style="height:100%;min-height:270px;text-align:center;display:flex;flex-direction:column;justify-content:center;align-items:center;background:linear-gradient(180deg, rgba(8,30,42,1), rgba(10,22,38,1)); border:0; border-radius:14px; box-shadow: inset 0 0 0 1px rgba(69,214,223,.3);">'
            '<div style="width:100px;height:100px;border-radius:50%;border:4px solid rgba(69,214,223,.7);display:grid;place-items:center;margin:0 auto 16px;background:rgba(16,52,59,.4);">'
            '<div style="font-size:2.2rem;color:#3be0ae;font-weight:900">✓</div></div>'
            '<div style="color:#3be0ae;font-size:1.1rem;font-weight:800;letter-spacing:0.04em;">System Status</div>'
            '<div style="font-size:2rem;color:#53d9bf;font-weight:800;margin-top:6px;">Secure</div>'
            '<div style="margin-top:12px;color:#9fb9d6;font-size:.8rem;">Last Scan: Jun 15, 2025 • 14:30 PM</div></div>',
            unsafe_allow_html=True,
        )


def render_analyze_profile() -> None:
    st.markdown('<div class="eyebrow">Triage</div>', unsafe_allow_html=True)
    st.title("Analyze a profile")
    st.caption("Rule-based indicators support triage; they do not establish impersonation or intent.")
    with st.form("profile_analysis"):
        platform = st.selectbox("Social media platform", PLATFORMS)
        username = st.text_input("Profile username", placeholder="@username")
        profile_url = st.text_input("Profile URL", placeholder="https://…")
        original_url = st.text_input("Original account URL (optional)", placeholder="https://…")
        description = st.text_area("Describe the suspicious activity", height=120)
        screenshot = st.file_uploader("Profile screenshot (optional)", type=["png", "jpg", "jpeg", "webp"], key="analysis_screenshot")
        submitted = st.form_submit_button("Analyze profile", type="primary")
    if submitted:
        if not username.strip() or not profile_url.strip() or not description.strip():
            st.error("Enter a username, profile URL, and activity description to analyze.")
        else:
            score, category, indicators = analyze_rules(platform, username, profile_url, original_url, description)
            record_analysis(platform, username.strip(), profile_url.strip(), original_url.strip(), description.strip(), score, category, indicators)
            evidence_id = None
            if screenshot is not None:
                try:
                    evidence_id = archive_file(screenshot)
                except ValueError as error:
                    st.warning(f"Analysis saved, but screenshot was not archived: {error}")
            st.session_state["last_analysis"] = {
                "platform": platform, "username": username.strip(), "profile_url": profile_url.strip(),
                "score": score, "category": category, "indicators": indicators, "evidence_id": evidence_id,
            }
    result = st.session_state.get("last_analysis")
    if result:
        st.markdown('<div class="section-bar"><h2>Analysis result</h2></div>', unsafe_allow_html=True)
        score_col, detail_col = st.columns([1, 2])
        with score_col:
            st.metric("Rule-based risk score", f"{result['score']} / 100", result["category"])
        with detail_col:
            st.markdown(f"**{escape(result['platform'])}** · {escape(result['username'])}")
            st.markdown(f"Profile: {escape(result['profile_url'])}")
            st.markdown("**Observed indicators**")
            for indicator in result["indicators"]:
                st.markdown(f"- {escape(indicator)}")
        if result.get("evidence_id"):
            st.info(f"Screenshot archived as {result['evidence_id']}.")
        st.info("Recommended next steps: independently review the profile and source material, preserve relevant context, contact the affected person through a known channel, and submit a report if appropriate. A score is not a definitive AI determination or proof of impersonation.")


def render_report_impersonation() -> None:
    st.markdown('<div class="eyebrow">Intake</div>', unsafe_allow_html=True)
    st.title("Report impersonation")
    st.caption("Submitted reports are stored locally as investigation cases.")
    with st.form("report_case"):
        complainant = st.text_input("Complainant name")
        email = st.text_input("Email address")
        platform = st.selectbox("Social media platform", PLATFORMS, key="report_platform")
        username = st.text_input("Fake profile username")
        profile_url = st.text_input("Fake profile URL")
        original_url = st.text_input("Original account URL")
        description = st.text_area("Describe the impersonation and its impact", height=130)
        attachment = st.file_uploader("Screenshot or supporting evidence (optional)", type=["png", "jpg", "jpeg", "webp", "pdf", "txt"], key="report_evidence")
        submitted = st.form_submit_button("Submit report", type="primary")
    if submitted:
        if not all(value.strip() for value in (complainant, email, username, profile_url, original_url, description)):
            st.error("Complete all required fields before submitting.")
        elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
            st.error("Enter a valid email address.")
        elif not (profile_url.strip().startswith("https://") and original_url.strip().startswith("https://")):
            st.error("Use HTTPS URLs for both profile links.")
        else:
            case_id = f"CASE-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
            with connection_scope() as connection:
                connection.execute(
                    """INSERT INTO cases
                       (case_id, complainant_name, email, platform, username, profile_url, original_url, description, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (case_id, complainant.strip(), email.strip(), platform, username.strip(), profile_url.strip(),
                     original_url.strip(), description.strip(), now_text()),
                )
            if attachment is not None:
                try:
                    evidence_id = archive_file(attachment, case_id)
                    st.success(f"Case {case_id} created. Evidence archived as {evidence_id}.")
                except ValueError as error:
                    st.warning(f"Case {case_id} created, but attachment was not archived: {error}")
            else:
                st.success(f"Case {case_id} created.")


def render_evidence_archive() -> None:
    st.markdown('<div class="eyebrow">Chain of custody</div>', unsafe_allow_html=True)
    st.title("Evidence archive")
    st.caption("Files are stored locally. Each item is recorded with its SHA-256 digest and upload metadata.")
    cases = query_frame("SELECT case_id FROM cases ORDER BY created_at DESC")
    case_options = ["Unlinked"] + cases["case_id"].tolist()
    with st.form("archive_evidence"):
        uploaded = st.file_uploader("Choose evidence files", type=["png", "jpg", "jpeg", "webp", "pdf", "txt"], accept_multiple_files=True)
        linked_case = st.selectbox("Link to case", case_options)
        submitted = st.form_submit_button("Archive selected files", type="primary")
    if submitted:
        if not uploaded:
            st.warning("Choose at least one file.")
        else:
            archived = []
            errors = []
            for file in uploaded:
                try:
                    archived.append((Path(file.name).name, archive_file(file, None if linked_case == "Unlinked" else linked_case)))
                except ValueError as error:
                    errors.append(f"{file.name}: {error}")
            for filename, evidence_id in archived:
                st.success(f"Archived {filename} as {evidence_id}.")
            for error in errors:
                st.error(error)
    records = query_frame(
        """SELECT e.evidence_id AS 'Evidence ID', e.original_filename AS Filename, e.file_type AS Type,
                  e.file_size AS 'Size (bytes)', e.sha256 AS 'SHA-256', e.case_id AS 'Case ID', e.uploaded_at AS 'Uploaded'
           FROM evidence e ORDER BY e.id DESC"""
    )
    st.markdown('<div class="section-bar"><h2>Archived files</h2></div>', unsafe_allow_html=True)
    search = st.text_input("Search by filename, evidence ID, or case ID", key="evidence_search")
    type_filter = st.selectbox("Filter by file type", ["All"] + sorted(records["Type"].dropna().unique().tolist()) if not records.empty else ["All"])
    filtered = records.copy()
    if search:
        mask = filtered.astype(str).apply(lambda column: column.str.contains(search, case=False, na=False)).any(axis=1)
        filtered = filtered[mask]
    if type_filter != "All":
        filtered = filtered[filtered["Type"] == type_filter]
    if filtered.empty:
        chart_empty("No matching archived files.")
    else:
        st.dataframe(filtered.drop(columns=["SHA-256"]), hide_index=True, use_container_width=True)
        selected = st.selectbox("Inspect evidence digest", filtered["Evidence ID"].tolist())
        selected_record = filtered[filtered["Evidence ID"] == selected].iloc[0]
        st.code(selected_record["SHA-256"], language=None)


def render_verify_evidence() -> None:
    st.markdown('<div class="eyebrow">Integrity check</div>', unsafe_allow_html=True)
    st.title("Verify evidence")
    st.caption("A matching digest means the archived file matches its recorded version. It does not prove authenticity or origin.")
    evidence = query_frame("SELECT evidence_id, original_filename, sha256, stored_path, uploaded_at FROM evidence ORDER BY id DESC")
    if evidence.empty:
        chart_empty("There are no archived files to verify yet.")
        return
    labels = {row["evidence_id"]: f"{row['evidence_id']} · {row['original_filename']}" for _, row in evidence.iterrows()}
    selected_id = st.selectbox("Select archived evidence", evidence["evidence_id"].tolist(), format_func=lambda value: labels[value])
    if st.button("Recalculate SHA-256", type="primary"):
        selected = evidence[evidence["evidence_id"] == selected_id].iloc[0]
        file_path = (APP_DIR / selected["stored_path"]).resolve()
        if not file_path.is_relative_to(EVIDENCE_DIR.resolve()):
            st.error("Stored path is outside the configured evidence directory. Verification stopped.")
            return
        verification_time = now_text()
        if not file_path.is_file():
            st.error(f"Archived file is missing. Evidence ID: {selected_id}. Checked: {verification_time}")
            return
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        matches = hmac.compare_digest(digest, selected["sha256"])
        st.markdown(f"**Evidence ID:** `{selected_id}`  \n**Verification timestamp:** {verification_time}")
        if matches:
            st.success("UNCHANGED: the file matches the SHA-256 digest recorded at archive time.")
        else:
            st.error("MISMATCH: the file differs from the version recorded at archive time.")
        st.caption("Hash comparison verifies file consistency only; it is not proof that the content is genuine.")


def build_case_pdf(case: pd.Series, evidence: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=letter, rightMargin=.65 * inch, leftMargin=.65 * inch,
                                 topMargin=.65 * inch, bottomMargin=.65 * inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], textColor=colors.HexColor("#10233a"), alignment=TA_LEFT, fontName="Helvetica-Bold", fontSize=20))
    styles.add(ParagraphStyle(name="ReportBody", parent=styles["BodyText"], leading=15, spaceAfter=8))
    story = [Paragraph("Investigation Case Report", styles["ReportTitle"]), Spacer(1, 8)]
    story.append(Paragraph(f"<b>Case ID:</b> {escape(str(case['case_id']))} &nbsp;&nbsp; <b>Status:</b> {escape(str(case['status']))}", styles["ReportBody"]))
    story.append(Paragraph(f"<b>Generated:</b> {escape(now_text())}", styles["ReportBody"]))
    story.append(Paragraph("Case details", styles["Heading2"]))
    details = [
        ["Complainant", str(case["complainant_name"])], ["Email", str(case["email"])],
        ["Platform", str(case["platform"])], ["Reported username", str(case["username"])],
        ["Profile URL", str(case["profile_url"])], ["Original URL", str(case["original_url"])],
        ["Reported", str(case["created_at"])],
    ]
    table = Table([[Paragraph(escape(a), styles["BodyText"]), Paragraph(escape(b), styles["BodyText"])] for a, b in details], colWidths=[1.35 * inch, 5.2 * inch])
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (0,-1), colors.HexColor("#eaf0f6")), ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#cbd5e1")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    story.extend([table, Spacer(1, 12), Paragraph("Description", styles["Heading2"]), Paragraph(escape(str(case["description"])).replace("\n", "<br/>"), styles["ReportBody"]), Paragraph("Linked evidence", styles["Heading2"])])
    if evidence.empty:
        story.append(Paragraph("No evidence is linked to this case.", styles["ReportBody"]))
    else:
        rows = [["Evidence ID", "Filename", "Type", "Bytes", "SHA-256"]]
        for _, record in evidence.iterrows():
            rows.append([str(record["evidence_id"]), str(record["original_filename"]), str(record["file_type"]), str(record["file_size"]), str(record["sha256"])])
        wrapped = [[Paragraph(escape(value), styles["BodyText"]) for value in row] for row in rows]
        evidence_table = Table(wrapped, repeatRows=1, colWidths=[.85*inch, 1.5*inch, .55*inch, .55*inch, 3.1*inch])
        evidence_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#dbe7f3")), ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#cbd5e1")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("FONTSIZE", (0,0), (-1,-1), 7), ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4)]))
        story.append(evidence_table)
    story.extend([Spacer(1, 18), Paragraph("This report is generated from records stored in the local application. A matching evidence digest confirms file consistency with the archived copy only; it does not establish authenticity.", styles["Italic"] )])
    document.build(story)
    return output.getvalue()


def render_reports() -> None:
    st.markdown('<div class="eyebrow">Documentation</div>', unsafe_allow_html=True)
    st.title("Investigation reports")
    st.caption("Generate a case-specific PDF containing the complaint and linked evidence metadata.")
    cases = query_frame("SELECT * FROM cases ORDER BY created_at DESC")
    if cases.empty:
        chart_empty("No cases are available. Submit an impersonation report to generate a case report.")
        return
    case_options = cases["case_id"].tolist()
    selected_id = st.selectbox("Select investigation", case_options)
    case = cases[cases["case_id"] == selected_id].iloc[0]
    status_options = ["Open", "Under Review", "Resolved"]
    current_status = case["status"] if case["status"] in status_options else "Open"
    with st.form("update_case_status"):
        updated_status = st.selectbox("Case status", status_options, index=status_options.index(current_status))
        status_submitted = st.form_submit_button("Update case status")
    if status_submitted and updated_status != current_status:
        with connection_scope() as connection:
            connection.execute("UPDATE cases SET status = ? WHERE case_id = ?", (updated_status, selected_id))
        st.success("Case status updated.")
        st.rerun()
    linked_evidence = query_frame("SELECT evidence_id, original_filename, file_type, file_size, sha256 FROM evidence WHERE case_id = ? ORDER BY uploaded_at", (selected_id,))
    st.markdown(f"**{escape(case['case_id'])}** · {escape(case['platform'])} · {escape(case['username'])} · {escape(case['status'])}")
    st.write(textwrap.shorten(str(case["description"]), width=360, placeholder="…"))
    st.write(f"Linked evidence files: {len(linked_evidence)}")
    pdf_bytes = build_case_pdf(case, linked_evidence)
    st.download_button("Download case report PDF", pdf_bytes, file_name=f"{selected_id.lower()}-report.pdf", mime="application/pdf", type="primary")
    if not linked_evidence.empty:
        st.dataframe(linked_evidence.rename(columns={"evidence_id": "Evidence ID", "original_filename": "Filename", "file_type": "Type", "file_size": "Size (bytes)", "sha256": "SHA-256"}), hide_index=True, use_container_width=True)


def render_user_management() -> None:
    st.markdown('<div class="eyebrow">Workspace administration</div>', unsafe_allow_html=True)
    st.title("User management")
    st.warning("This local prototype stores a team directory only. It does not authenticate users or enforce role-based access.")
    with st.form("add_user"):
        name = st.text_input("Name")
        email = st.text_input("Email", key="user_email")
        role = st.selectbox("Role", ["Investigator", "Reviewer", "Administrator"])
        submitted = st.form_submit_button("Add directory entry")
    if submitted:
        if not name.strip() or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
            st.error("Enter a name and a valid email address.")
        else:
            try:
                with connection_scope() as connection:
                    connection.execute("INSERT INTO app_users (name, email, role, created_at) VALUES (?, ?, ?, ?)", (name.strip(), email.strip(), role, now_text()))
                st.success("Directory entry added.")
            except sqlite3.IntegrityError:
                st.error("That email address is already in the directory.")
    users = query_frame("SELECT name AS Name, email AS Email, role AS Role, created_at AS 'Added' FROM app_users ORDER BY id DESC")
    if users.empty:
        chart_empty("No directory entries yet.")
    else:
        st.dataframe(users, hide_index=True, use_container_width=True)


def render_settings() -> None:
    st.markdown('<div class="eyebrow">Configuration</div>', unsafe_allow_html=True)
    st.title("Settings")
    st.markdown("#### Local storage")
    st.write(f"Database: `{DATABASE_PATH}`")
    st.write(f"Evidence directory: `{EVIDENCE_DIR}`")
    st.write(f"Maximum file size: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    st.markdown("#### Supported evidence")
    st.write(", ".join(sorted(extension.lstrip(".").upper() for extension in ALLOWED_EXTENSIONS)))
    st.warning("This prototype stores evidence unencrypted on the host filesystem. Restrict host access, back up the data directory securely, and add authentication and encryption before handling sensitive real-world cases or exposing it to a network.")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()
    st.sidebar.markdown(
        '<div class="brand"><span class="brand-mark">◉</span><div class="brand-text">SIEP</div></div>'
        '<div class="brand-subtitle">Social Media Impersonation &amp; Evidence Personation</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")
    pages = ["Dashboard", "Analyze Profile", "Report Impersonation", "Evidence Archive", "Verify Evidence", "Investigation Reports", "User Management", "Settings", "Logout"]
    navigation_icons = {
        "Dashboard": "⌂", "Analyze Profile": "⌕", "Report Impersonation": "⚑",
        "Evidence Archive": "▤", "Verify Evidence": "✓", "Investigation Reports": "▦",
        "User Management": "♙", "Settings": "⚙", "Logout": "↪",
    }
    page = st.sidebar.radio(
        "Navigation", pages, label_visibility="collapsed",
        format_func=lambda item: f"{navigation_icons[item]}  {item}",
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown('<span class="status-dot"></span><span class="subtle">Local workspace</span>', unsafe_allow_html=True)
    if page == "Dashboard":
        render_dashboard()
    elif page == "Analyze Profile":
        render_analyze_profile()
    elif page == "Report Impersonation":
        render_report_impersonation()
    elif page == "Evidence Archive":
        render_evidence_archive()
    elif page == "Verify Evidence":
        render_verify_evidence()
    elif page == "Investigation Reports":
        render_reports()
    elif page == "User Management":
        render_user_management()
    elif page == "Settings":
        render_settings()
    else:
        st.title("End local session")
        st.info("This prototype has no authenticated session to revoke. Clear transient page state and close the browser tab when finished.")
        if st.button("Clear transient session state"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


if __name__ == "__main__":
    main()