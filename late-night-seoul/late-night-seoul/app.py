"""
막차 이후의 서울 — 심야 교통 사각지대 대시보드
실행:  streamlit run app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from metrics import GROUP_BLIND, GROUP_LOW, GROUP_OK, GROUPS, Rule, classify, cliff_groups  # noqa: E402

P = ROOT / "data" / "processed"
INK, INK2, MUTED, GRID = "#1E293B", "#475569", "#64748B", "#E2E8F0"
BLUE, GREEN, CORAL, CORAL_T, SLATE = "#34607F", "#5E9483", "#F97316", "#FDBA74", "#CBD5E1"
GROUP_COLOR = {GROUP_BLIND: CORAL, GROUP_LOW: CORAL_T, GROUP_OK: SLATE}
LINE_COLOR = {"번화가 (역삼1동·서교동·종로1~4가동)": BLUE, "서울 전체": GREEN, "사각지대 행정동": CORAL}
FONT = "Pretendard, 'Noto Sans KR', 'Malgun Gothic', sans-serif"

st.set_page_config(page_title="막차 이후의 서울", page_icon="🌙", layout="wide")
st.markdown(f"""<style>
html, body, [class*="css"] {{ font-family: {FONT}; color: {INK}; }}
.block-container {{ padding-top: 1.4rem; max-width: 1280px; }}
.claim {{ border-left: 5px solid {BLUE}; background: #F8FAFC; padding: 12px 16px; border-radius: 6px;
          font-size: 17px; margin-bottom: 12px; }}
.why {{ background: #F8FAFC; border: 1px solid {GRID}; border-radius: 8px; padding: 12px 16px; font-size: 15px; color: {INK2}; }}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner="데이터 불러오는 중")
def load():
    if not (P / "dong_summary.csv").exists():
        from preprocess import build
        build()
    s = pd.read_csv(P / "dong_summary.csv", dtype={"code8": str})
    h = pd.read_csv(P / "dong_hourly.csv", dtype={"code8": str})
    stops = pd.read_csv(P / "night_stops.csv", dtype={"code8": str, "ARS": str})
    gj = json.loads((P / "seoul_dong.geojson").read_text(encoding="utf-8"))
    meta = json.loads((P / "meta.json").read_text(encoding="utf-8"))
    return s, h, stops, gj, meta


s, h, stops, gj, meta = load()
s["label"] = s["gu"] + " " + s["dong"]

with st.sidebar:
    st.markdown("### 비교 기준 설정")
    mode = st.radio("최소 Limit 하한선", ["하위 백분위", "사용자 지정 값"])
    pct, custom = 10.0, None
    if mode == "하위 백분위":
        pct = float(st.slider("하위 백분위 (%)", 5, 30, 10, step=5))
    else:
        custom = st.number_input("생활인구 1만 명당 심야 버스 승차 (명)", 0.0, 50.0, 1.0, step=0.5)
    zero = st.checkbox("심야 승차 정류장 0개 동 포함", value=True)
    picks = st.multiselect("비교 행정동 선택", s["label"].sort_values().tolist())
    st.caption(f"기준월 {meta['month'][:4]}.{meta['month'][4:]} · 판정 시간 01:00~04:00 · 행정동 {meta['n_dong']}개")

d, info = classify(s, Rule(pct=pct, use_zero_stop=zero, custom_limit=custom))
pick_codes = set(d.loc[d["label"].isin(picks), "code8"])

st.markdown("## 막차 이후의 서울 — 심야 교통 사각지대")
k1, k2, k3, k4 = st.columns(4)
k1.metric("최소 Limit 하한선", f"{info['limit']:.2f}명", "생활인구 1만 명당 심야 버스 승차", delta_color="off")
k2.metric("최소 Limit 미달", f"{info['n_below']}개 동", f"전체 {info['n']}개 동", delta_color="off")
k3.metric("사각지대", f"{info['n_blind']}개 동", f"심야 생활인구 {info['pop_blind']:,.0f}명", delta_color="off")
k4.metric("01~04시 승차 0명", f"{info['n_zero_ratio']}개 동", "심야 승차 정류장 0개", delta_color="off")

tabs = st.tabs(["작품 소개", "시각화 1 · 사분면 산점도", "시각화 2 · 막차 절벽", "시각화 3 · 행정동 지도", "행정동 목록"])


def layout(fig, height=560):
    fig.update_layout(height=height, font=dict(family=FONT, size=14, color=INK2), plot_bgcolor="white",
                      paper_bgcolor="white", margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.08, x=0))
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


with tabs[0]:
    st.markdown("""
- **주제**: 심야(01~04시) 생활인구 대비 대중교통 공급이 부족한 행정동 도출
- **관점**: 평균 개선·격차 축소가 아닌 **최소 Limit(최저선)** 기준
- **최소 Limit 미달**: 생활인구 1만 명당 심야 버스 승차가 서울 하위 10% 이하, 또는 심야 승차 정류장 0개
- **사각지대**: 최소 Limit 미달이면서 심야 생활인구가 서울 중앙값 이상인 행정동
- **데이터**: 서울 열린데이터광장 — 생활인구(OA-14991), 버스 승하차(OA-12913), 지하철 승하차(OA-12252), 버스정류소 위치(OA-15067), 역사마스터, 행정동 경계
""")

with tabs[1]:
    st.markdown(f'<div class="claim">{info["n"]}개 행정동 중 {info["n_blind"]}개 동: 심야 생활인구 중앙값 이상, 01~04시 버스 승차 하한선 이하</div>',
                unsafe_allow_html=True)
    fig = go.Figure()
    y = d["service10k"].where(d["service10k"] > 0, 0.006)
    for g in [GROUP_OK, GROUP_LOW, GROUP_BLIND]:
        m = d.group == g
        dd = d[m]
        fig.add_trace(go.Scatter(x=dd.night_pop, y=y[m], mode="markers", name=f"{g} · {int(m.sum())}개",
                                 marker=dict(size=9, color=GROUP_COLOR[g], line=dict(color="white", width=1)),
                                 customdata=np.c_[dd.label, dd.service10k, dd.night_stops],
                                 hovertemplate="<b>%{customdata[0]}</b><br>생활인구 %{x:,.0f}명<br>1만 명당 승차 %{customdata[1]:.2f}명"
                                               "<br>심야 승차 정류장 %{customdata[2]}개<extra></extra>"))
    if pick_codes:
        dd = d[d.code8.isin(pick_codes)]
        fig.add_trace(go.Scatter(x=dd.night_pop, y=dd.service10k.where(dd.service10k > 0, 0.006), mode="markers+text",
                                 text=dd.label, textposition="top center", name="선택 행정동",
                                 marker=dict(size=15, color="rgba(0,0,0,0)", line=dict(color=INK, width=2))))
    fig.add_hline(y=max(info["limit"], 0.007), line=dict(color=BLUE, width=2, dash="dash"),
                  annotation_text=f"최소 Limit {info['limit']:.2f}명", annotation_font_color=BLUE)
    fig.add_vline(x=info["x_cut"], line=dict(color=MUTED, width=1, dash="dot"),
                  annotation_text="생활인구 중앙값", annotation_font_color=MUTED)
    fig.update_yaxes(type="log", title="생활인구 1만 명당 심야 버스 승차 (로그, 0은 맨 아래)")
    fig.update_xaxes(title="심야(01~04시) 평균 생활인구 (명)")
    st.plotly_chart(layout(fig, 620), use_container_width=True)

with tabs[2]:
    st.markdown('<div class="claim">사각지대 행정동: 01~04시 생활인구 1만 명당 승차 0명 · 서울 전체 5~9명 · 번화가 52~92명</div>',
                unsafe_allow_html=True)
    c = cliff_groups(h, d)
    zoom = st.toggle("00~05시 확대", value=False)
    fig = go.Figure()
    for g, col in LINE_COLOR.items():
        dd = c[c.group == g]
        if dd.empty:
            continue
        fig.add_trace(go.Scatter(x=dd.label, y=dd.rate10k, name=g, mode="lines+markers",
                                 line=dict(color=col, width=3), marker=dict(size=7),
                                 customdata=np.c_[dd.bus10k, dd.sub10k],
                                 hovertemplate="%{x} %{y:.1f}명<br>버스 %{customdata[0]:.1f} · 지하철 %{customdata[1]:.1f}<extra></extra>"))
    hp = h.merge(d[["code8", "label"]])
    for lab in picks:
        dd = hp[hp.label == lab].set_index("hour").reindex(c.hour.unique())
        fig.add_trace(go.Scatter(x=[f"{x:02d}시" for x in dd.index], y=dd.rate10k, name=lab, mode="lines",
                                 line=dict(width=2, dash="dot")))
    fig.update_yaxes(title="생활인구 1만 명당 시간당 승차 (버스+지하철)")
    if zoom:
        fig.update_xaxes(range=[5.5, 11.5]); fig.update_yaxes(range=[0, 120])
    st.plotly_chart(layout(fig), use_container_width=True)

with tabs[3]:
    st.markdown(f'<div class="claim">최소 Limit 미달 {info["n_below"]}개 동 분포 · 사각지대 {info["n_blind"]}개 동 강조</div>',
                unsafe_allow_html=True)
    z = d.group.map({GROUP_OK: 0, GROUP_LOW: 1, GROUP_BLIND: 2})
    fig = go.Figure(go.Choroplethmap(
        geojson=gj, featureidkey="properties.code8", locations=d.code8, z=z, zmin=0, zmax=2, showscale=False,
        colorscale=[[0, "#F1F5F9"], [0.33, "#F1F5F9"], [0.34, CORAL_T], [0.66, CORAL_T], [0.67, CORAL], [1, CORAL]],
        marker=dict(line=dict(color="white", width=0.6), opacity=0.9),
        customdata=np.c_[d.label, d.group, d.night_pop, d.service10k],
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>생활인구 %{customdata[2]:,.0f}명"
                      "<br>1만 명당 승차 %{customdata[3]:.2f}명<extra></extra>"))
    fig.add_trace(go.Scattermap(lat=stops.lat, lon=stops.lon, mode="markers", name="01~04시 승차 정류장",
                                marker=dict(size=3, color=BLUE, opacity=0.6), hoverinfo="skip"))
    fig.update_layout(map=dict(style="carto-positron", center=dict(lat=37.563, lon=126.99), zoom=10.1),
                      height=640, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, use_container_width=True)

with tabs[4]:
    t = d[d.below].sort_values(["group", "night_pop"], ascending=[True, False])[
        ["group", "gu", "dong", "night_pop", "night_bus", "service10k", "night_stops"]]
    t.columns = ["구분", "자치구", "행정동", "심야 생활인구", "심야 버스 승차(일평균)", "1만 명당 승차", "심야 승차 정류장"]
    st.dataframe(t.style.format({"심야 생활인구": "{:,.0f}", "심야 버스 승차(일평균)": "{:.1f}", "1만 명당 승차": "{:.2f}"}),
                 use_container_width=True, hide_index=True, height=520)
    st.download_button("CSV 내려받기", t.to_csv(index=False).encode("utf-8-sig"), "최소Limit_미달_행정동.csv", "text/csv")
