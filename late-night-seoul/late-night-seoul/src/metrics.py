"""
비교 기준 — 대시보드(app.py)와 발표용 그림(figures.py)이 같은 함수를 쓴다.
복합 지수·가중치 점수는 만들지 않는다. 원본 수치와 그 비율만 비교한다.

  심야 생활인구   : 01~04시(01·02·03시대) 평균 생활인구
  심야 버스 승차  : 01~04시 버스 승차 인원 합계 (한 달 합계 ÷ 30일 = 일평균)
  이용 비율       : 심야 버스 승차 ÷ 심야 생활인구 × 10,000  (생활인구 1만 명당 승차 인원)
  심야 승차 정류장: 01~04시 승차가 한 번이라도 기록된 정류장

  최소 Limit 미달 : ① 이용 비율 ≤ 서울 행정동 하위 10% 값   또는   ② 심야 승차 정류장 0개
  사각지대        : 최소 Limit 미달  AND  심야 생활인구 ≥ 서울 행정동 중앙값
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

GROUP_BLIND = "사각지대 (생활인구 중앙값 이상 · 최소 Limit 미달)"
GROUP_LOW = "최소 Limit 미달 (생활인구 중앙값 미만)"
GROUP_OK = "최소 Limit 충족"
GROUPS = [GROUP_BLIND, GROUP_LOW, GROUP_OK]

# 비교용 번화가 (강남·홍대·종로)
HOTSPOTS = {"11680640": "강남구 역삼1동", "11440660": "마포구 서교동", "11110615": "종로구 종로1·2·3·4가동"}


@dataclass
class Rule:
    pct: float = 10.0                 # 하한선 백분위
    use_zero_stop: bool = True        # ② 심야 승차 정류장 0개 기준 사용
    custom_limit: float | None = None # 사용자 지정 하한선(1만 명당 승차 인원)


def limit_value(s: pd.DataFrame, rule: Rule) -> float:
    if rule.custom_limit is not None:
        return float(rule.custom_limit)
    return float(np.percentile(s["service10k"].dropna(), rule.pct))


def classify(s: pd.DataFrame, rule: Rule = Rule()) -> tuple[pd.DataFrame, dict]:
    d = s.copy()
    lim = limit_value(d, rule)
    d["zero_stop"] = d["night_stops"] == 0
    d["below_line"] = d["service10k"] <= lim
    d["below"] = d["below_line"] | (d["zero_stop"] if rule.use_zero_stop else False)
    x_cut = float(d["night_pop"].median())
    d["high_demand"] = d["night_pop"] >= x_cut
    d["group"] = np.select([d["below"] & d["high_demand"], d["below"]], [GROUP_BLIND, GROUP_LOW], GROUP_OK)
    info = {"limit": lim, "x_cut": x_cut, "n": int(len(d)),
            "n_blind": int((d.group == GROUP_BLIND).sum()), "n_low": int((d.group == GROUP_LOW).sum()),
            "n_ok": int((d.group == GROUP_OK).sum()), "n_below": int(d["below"].sum()),
            "n_zero_stop": int(d["zero_stop"].sum()), "n_zero_ratio": int((d["service10k"] == 0).sum()),
            "pop_blind": float(d.loc[d.group == GROUP_BLIND, "night_pop"].sum()),
            "pop_below": float(d.loc[d["below"], "night_pop"].sum()),
            "pop_total": float(d["night_pop"].sum())}
    return d, info


HOURS_18_05 = list(range(18, 24)) + list(range(0, 6))


def cliff_groups(h: pd.DataFrame, d: pd.DataFrame, hours=None) -> pd.DataFrame:
    """시간대별 대중교통 이용 비율: 사각지대 행정동 / 서울 전체 / 번화가.
    이용 비율 = 그룹 합계(버스+지하철 승차) ÷ 그룹 합계 생활인구 × 10,000."""
    hours = hours or HOURS_18_05
    grp = {"사각지대 행정동": d.loc[d.group == GROUP_BLIND, "code8"],
           "서울 전체": d["code8"],
           "번화가 (역삼1동·서교동·종로1~4가동)": pd.Series([c for c in HOTSPOTS if c in set(d.code8)])}
    rows = []
    for name, codes in grp.items():
        if len(codes) == 0:
            continue
        g = h[h.code8.isin(codes) & h.hour.isin(hours)].groupby("hour")[["board", "bus", "subway", "pop"]].sum()
        for hr in hours:
            r = g.loc[hr]
            rows.append({"group": name, "hour": hr, "rate10k": r.board / r["pop"] * 1e4,
                         "bus10k": r.bus / r["pop"] * 1e4, "sub10k": r.subway / r["pop"] * 1e4,
                         "board": r.board, "pop": r["pop"], "n": len(codes)})
    out = pd.DataFrame(rows)
    out["order"] = out["hour"].map({hr: i for i, hr in enumerate(hours)})
    out["label"] = out["hour"].map(lambda x: f"{x:02d}시")
    return out.sort_values(["group", "order"])
