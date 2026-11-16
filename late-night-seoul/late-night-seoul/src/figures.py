"""
발표용 그림 3종 (PNG) — metrics.py의 비교 기준 그대로 그린다.
실행: python src/figures.py → figures/fig1_scatter.png, fig2_cliff.png, fig3_map.png, numbers.json
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, ticker
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from metrics import GROUP_BLIND, GROUP_LOW, GROUP_OK, HOTSPOTS, Rule, classify, cliff_groups

ROOT = Path(__file__).resolve().parents[1]
P, F = ROOT / "data" / "processed", ROOT / "figures"
F.mkdir(exist_ok=True)

for name in ("Noto Sans CJK KR", "NanumGothic", "Malgun Gothic", "AppleGothic"):
    if any(name in f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = name
        break

INK, INK2, MUTED, GRID, SURF = "#1E293B", "#475569", "#64748B", "#E2E8F0", "#FFFFFF"
BLUE, GREEN, CORAL, CORAL_T, SLATE = "#34607F", "#5E9483", "#F97316", "#FDBA74", "#CBD5E1"
plt.rcParams.update({"axes.unicode_minus": False, "savefig.dpi": 200, "font.size": 17,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#94A3B8",
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.titlesize": 19, "legend.fontsize": 16})
GROUP_COLOR = {GROUP_BLIND: CORAL, GROUP_LOW: CORAL_T, GROUP_OK: SLATE}
LINE_COLOR = {"번화가 (역삼1동·서교동·종로1~4가동)": BLUE, "서울 전체": GREEN, "사각지대 행정동": CORAL}


def load():
    s = pd.read_csv(P / "dong_summary.csv", dtype={"code8": str})
    h = pd.read_csv(P / "dong_hourly.csv", dtype={"code8": str})
    gj = json.loads((P / "seoul_dong.geojson").read_text(encoding="utf-8"))
    meta = json.loads((P / "meta.json").read_text(encoding="utf-8"))
    stops = pd.read_csv(P / "night_stops.csv", dtype={"code8": str, "ARS": str})
    return s, h, gj, meta, stops


def _src(fig, meta):
    src = "서울 열린데이터광장" if meta["source"] == "real" else "가상 데이터"
    fig.text(0.01, 0.01, f"자료: {src} · {meta['month'][:4]}년 {int(meta['month'][4:])}월 일평균",
             fontsize=13, color=MUTED, ha="left", va="bottom")


# ------------------------------------------------------------------ 시각화 1: 사분면 산점도
def fig_scatter(d, info, meta):
    ZERO_Y = 0.006
    fig, ax = plt.subplots(figsize=(13, 7.4), facecolor=SURF)
    ax.set_facecolor(SURF)
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    y = d["service10k"].where(d["service10k"] > 0, ZERO_Y)
    for g in [GROUP_OK, GROUP_LOW, GROUP_BLIND]:
        m = d.group == g
        ax.scatter(d.loc[m, "night_pop"], y[m], s=58 if g == GROUP_BLIND else 40, color=GROUP_COLOR[g],
                   edgecolor=SURF, lw=1, zorder=3 if g != GROUP_OK else 2, label=f"{g} · {int(m.sum())}개 동")
    ax.set_yscale("log")
    ax.set_ylim(0.004, 1500)
    ax.axhspan(0.004, 0.009, color="#FFF7ED", zorder=0)
    ax.axhline(info["limit"], color=BLUE, lw=2, ls=(0, (6, 3)))
    ax.axvline(info["x_cut"], color=MUTED, lw=1.4, ls=(0, (2, 3)))
    xmax = d["night_pop"].max() * 1.05
    ax.set_xlim(0, xmax)
    ax.text(xmax, (info["limit"] * 0.009) ** 0.5, f"▲ 최소 Limit 선: 하위 10% = 1만 명당 {info['limit']:.2f}명 ",
            ha="right", va="center", fontsize=14, color=BLUE)
    ax.text(xmax, ZERO_Y, "01~04시 버스 승차 0명 ", fontsize=14, color=CORAL, va="center", ha="right")
    ax.text(info["x_cut"] * 1.01, 900, f" 생활인구 중앙값 {info['x_cut']:,.0f}명", fontsize=14, color=MUTED, va="top")
    ax.set_yticks([0.01, 0.1, 1, 10, 100, 1000])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: {0.01: "", 0.1: "0.1"}.get(v, f"{v:g}")))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1e4:.0f}만" if v else "0"))
    ax.set_xlabel("심야(01~04시) 평균 생활인구 (명)")
    ax.set_ylabel("생활인구 1만 명당 심야 버스 승차 (명, 로그)")
    top = d[d.group == GROUP_BLIND].sort_values("night_pop", ascending=False).head(3)
    for i, (_, r) in enumerate(top.iterrows()):
        ax.annotate(f"{r.gu} {r.dong} {r.night_pop:,.0f}명", (r.night_pop, ZERO_Y), xytext=(61000, [0.55, 0.22, 0.09][i]),
                    textcoords="data", ha="left", va="center", fontsize=14, color=INK,
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.legend(frameon=False, loc="upper right", fontsize=15, markerscale=1.3)
    fig.suptitle(f"시각화 1 · 사분면 산점도: {info['n']}개 행정동 중 사각지대 {info['n_blind']}개 동",
                 x=0.01, ha="left", fontsize=21, fontweight="bold", color=INK)
    _src(fig, meta)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(F / "fig1_scatter.png", facecolor=SURF)
    plt.close(fig)


# ------------------------------------------------------------------ 시각화 2: 막차 절벽
def fig_cliff(h, d, meta):
    c = cliff_groups(h, d)
    labels = [f"{x:02d}시" for x in list(range(18, 24)) + list(range(0, 6))]
    fig, (ax, az) = plt.subplots(1, 2, figsize=(14, 6.6), gridspec_kw={"width_ratios": [1.5, 1]}, facecolor=SURF)
    for a in (ax, az):
        a.set_facecolor(SURF)
        a.grid(axis="y", color=GRID, lw=0.8)
        a.set_axisbelow(True)
    for g, col in LINE_COLOR.items():
        dd = c[c.group == g]
        ax.plot(dd["order"], dd["rate10k"], color=col, lw=3, marker="o", ms=6, label=g, zorder=3)
    ax.axvspan(6.5, 9.5, color=CORAL, alpha=0.07, lw=0)
    ax.text(8, ax.get_ylim()[1] * 0.55, "01~04시", ha="center", fontsize=15, color=CORAL)
    ax.set_xticks(range(12), labels, fontsize=14)
    ax.set_ylabel("생활인구 1만 명당 시간당 승차 (버스+지하철)")
    ax.set_title("18시 → 다음날 05시", loc="left", color=INK, pad=12)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(frameon=False, loc="upper right", fontsize=15)
    zh = [0, 1, 2, 3, 4]
    for g, col in LINE_COLOR.items():
        dd = c[(c.group == g) & c.hour.isin(zh)].sort_values("order")
        az.plot(range(5), dd["rate10k"], color=col, lw=3, marker="o", ms=7, zorder=3)
        v = float(dd.iloc[2]["rate10k"])
        off, ha = {"서울 전체": ((-12, 10), "right"), "사각지대 행정동": ((12, 6), "left")}.get(g, ((0, 10), "center"))
        az.annotate(f"{v:.1f}", (2, v), textcoords="offset points", xytext=off, ha=ha, fontsize=15, color=INK)
    az.set_xticks(range(5), [f"{x:02d}시" for x in zh], fontsize=14)
    az.set_ylim(0, 110)
    az.set_title("확대: 00~04시 (Y축 0~110)", loc="left", color=INK, pad=12)
    fig.suptitle("시각화 2 · 시간대별 선 그래프(막차 절벽): 사각지대 행정동은 01~04시 이용 비율 0",
                 x=0.01, ha="left", fontsize=21, fontweight="bold", color=INK)
    _src(fig, meta)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(F / "fig2_cliff.png", facecolor=SURF)
    plt.close(fig)
    piv = c.pivot(index="hour", columns="group", values="rate10k")
    return {"rate10k": piv.round(2).to_dict(),
            "bus10k": c.pivot(index="hour", columns="group", values="bus10k").round(2).to_dict(),
            "sub10k": c.pivot(index="hour", columns="group", values="sub10k").round(2).to_dict()}


# ------------------------------------------------------------------ 시각화 3: 지도
def fig_map(d, gj, stops, meta, info):
    dd = d.set_index("code8")
    blind = d[d.group == GROUP_BLIND].sort_values("night_pop", ascending=False).reset_index(drop=True)
    num = {c: i + 1 for i, c in enumerate(blind.code8)}
    fig = plt.figure(figsize=(15, 9.4), facecolor=SURF)
    ax = fig.add_axes([0.0, 0.04, 0.66, 0.88])
    ax.set_facecolor(SURF)
    polys, faces = [], []
    for f in gj["features"]:
        code = f["properties"]["code8"]
        g = f["geometry"]
        rings = [p[0] for p in g["coordinates"]] if g["type"] == "MultiPolygon" else [g["coordinates"][0]]
        if code in dd.index:
            grp = dd.loc[code, "group"]
            col = CORAL if grp == GROUP_BLIND else (CORAL_T if grp == GROUP_LOW else "#F1F5F9")
        else:
            col = "#E2E8F0"
        for ring in rings:
            polys.append(np.asarray(ring)); faces.append(col)
    ax.add_collection(PolyCollection(polys, facecolors=faces, edgecolors="white", linewidths=0.5))
    ax.scatter(stops.lon, stops.lat, s=3, color=BLUE, alpha=0.55, lw=0, zorder=3)
    for _, r in blind.iterrows():
        ax.text(r.lon, r.lat, str(num[r.code8]), ha="center", va="center", fontsize=12, color="white",
                fontweight="bold", zorder=5, bbox=dict(boxstyle="circle,pad=0.25", fc=INK, ec="none"))
    ax.autoscale_view()
    ax.set_aspect(1 / np.cos(np.radians(37.55)))
    ax.axis("off")
    handles = [Patch(color=CORAL, label=f"사각지대 {info['n_blind']}개 동"),
               Patch(color=CORAL_T, label=f"최소 Limit 미달 · 생활인구 중앙값 미만 {info['n_low']}개 동"),
               Patch(color="#F1F5F9", label="최소 Limit 충족"),
               Patch(color="#E2E8F0", label="경계·코드 불일치로 제외"),
               Line2D([], [], marker="o", ls="", color=BLUE, ms=5, label="01~04시 승차 기록 정류장")]
    ax.legend(handles=handles, frameon=True, facecolor=SURF, edgecolor=GRID, loc="lower left", fontsize=13)
    side = fig.add_axes([0.67, 0.08, 0.32, 0.82]); side.axis("off")
    side.text(0, 1, "사각지대 행정동\n(심야 생활인구 순)", fontsize=17, fontweight="bold", color=INK, va="top")
    for i, r in blind.iterrows():
        side.text(0, 0.88 - i * 0.072, f"{i+1:>2}. {r.gu} {r.dong}", fontsize=15, color=INK, va="top")
        side.text(1, 0.88 - i * 0.072, f"{r.night_pop:,.0f}명", fontsize=15, color=INK2, va="top", ha="right")
    fig.suptitle("시각화 3 · 행정동 지도: 최소 Limit 미달 행정동 분포", x=0.01, ha="left",
                 fontsize=21, fontweight="bold", color=INK)
    _src(fig, meta)
    fig.savefig(F / "fig3_map.png", facecolor=SURF)
    plt.close(fig)
    return blind[["gu", "dong", "night_pop", "service10k", "night_stops"]].round(2).to_dict("records")


def main():
    s, h, gj, meta, stops = load()
    d, info = classify(s, Rule())
    nums = {"meta": {k: v for k, v in meta.items() if k != "subway_unmatched_names"}, "rule": info}
    fig_scatter(d, info, meta)
    nums["cliff"] = fig_cliff(h, d, meta)
    nums["blind"] = fig_map(d, gj, stops, meta, info)
    low = d[d.group == GROUP_LOW].sort_values("night_pop", ascending=False)
    nums["low"] = low[["gu", "dong", "night_pop", "service10k", "night_stops"]].round(2).to_dict("records")
    nums["by_gu_below"] = d[d.below].groupby("gu").size().sort_values(ascending=False).to_dict()
    hh = h.groupby("hour")[["bus", "subway", "pop"]].sum()
    nums["seoul_hourly"] = hh.round(0).to_dict()
    nums["hotspots"] = d[d.code8.isin(HOTSPOTS)][["gu", "dong", "night_pop", "service10k", "night_stops"]].round(2).to_dict("records")
    nums["ratio_quantiles"] = d["service10k"].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).round(2).to_dict()
    for p in (5, 20):
        _, i2 = classify(s, Rule(pct=p))
        nums[f"rule_p{p}"] = {k: i2[k] for k in ("limit", "n_below", "n_blind")}
    _, i3 = classify(s, Rule(use_zero_stop=False))
    nums["rule_no_zero_stop"] = {k: i3[k] for k in ("limit", "n_below", "n_blind")}
    (F / "numbers.json").write_text(json.dumps(nums, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: nums[k] for k in ("rule", "by_gu_below", "hotspots", "ratio_quantiles", "rule_p5", "rule_p20",
                                           "rule_no_zero_stop")}, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
