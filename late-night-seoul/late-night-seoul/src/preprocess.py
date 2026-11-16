"""
전처리 파이프라인 — 원천 6종 → 행정동 단위 분석 테이블
=====================================================
실행:  python src/preprocess.py
  · data/raw/ 에 실제 파일 6종이 모두 있으면 → 실제 데이터로 처리
  · 하나라도 없으면 → data/synthetic/ 의 가상 데이터로 처리 (없으면 자동 생성)

출력 (data/processed/)
  dong_hourly.csv     행정동 × 시간(0~23) : 평균 생활인구, 버스/지하철 일평균 승차
  dong_summary.csv    행정동별 심야 지표 (수요·서비스 수준·심야 운행 정류장 수 등)
  night_stops.csv     심야 운행 정류장 좌표 (지도용)
  seoul_dong.geojson  서울 행정동 경계 (code8 속성 추가)
  meta.json           데이터 출처(real/synthetic), 기준월, 매칭률 등 품질 기록

핵심 처리 원칙
  1) 공간 단위 통일: 정류장·역 좌표를 행정동 경계에 '점-다각형 포함' 판정으로 붙인다.
  2) 월 합계 → 일평균: 버스·지하철은 월 누적값이므로 해당 월 일수로 나눈다.
  3) 0값 보존: 심야 승차가 없는 동은 결측(NaN)이 아니라 0으로 남긴다. 이 0이 분석의 핵심이다.
"""
from __future__ import annotations

import calendar
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.path import Path as MPath

ROOT = Path(__file__).resolve().parents[1]
RAW, SYN, OUT = ROOT / "data" / "raw", ROOT / "data" / "synthetic", ROOT / "data" / "processed"

# 판정 구간: 01:00~03:59 (시간대 1·2·3). 00시대는 일반버스 막차, 04시대는 첫차가 섞여
# '심야 대중교통'의 순수한 공급을 흐리기 때문에 핵심 판정에서 제외한다.
NIGHT_HOURS = [1, 2, 3]
# 심야 운행 정류장: 판정 구간 일평균 승차가 1명 이상 발생한 정류장
NIGHT_STOP_MIN = 1e-9

PATTERNS = {
    "pop": "LOCAL_PEOPLE_DONG_*.*",
    "bus": "*버스노선별_정류장별_시간대별_승하차*.csv",
    "stop": "*버스정류소위치정보*.xlsx",
    "sub": "*지하철*시간대별*.csv",
    "station": "*역사마스터*.csv",
    "geo": "*.geojson",
}


# --------------------------------------------------------------------------- 공통 유틸
def _find(folder: Path) -> dict[str, Path] | None:
    found = {}
    for k, pat in PATTERNS.items():
        hits = sorted(folder.glob(pat))
        if not hits:
            return None
        found[k] = hits[-1]  # 같은 종류가 여럿이면 이름순 마지막(최신)
    return found


def _read_csv(src, **kw) -> pd.DataFrame:
    """서울 열린데이터광장 CSV는 cp949 / utf-8-sig 가 섞여 있다."""
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            if isinstance(src, bytes):
                return pd.read_csv(io.BytesIO(src), encoding=enc, low_memory=False, **kw)
            return pd.read_csv(src, encoding=enc, low_memory=False, **kw)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 판별하지 못했습니다: {src}")


def _col(df: pd.DataFrame, *keys: str) -> str:
    for c in df.columns:
        cc = str(c).replace(" ", "").replace("﻿", "").replace('"', "")
        if any(k in cc for k in keys):
            return c
    raise KeyError(f"{keys} 를 포함하는 컬럼이 없습니다: {list(df.columns)[:12]}")


def _norm_station(name: str) -> str:
    s = re.sub(r"\(.*?\)", "", str(name)).strip()
    return s[:-1] if s.endswith("역") and len(s) > 2 else s


# --------------------------------------------------------------------------- ⑥ 경계
def load_boundary(path: Path):
    gj = json.loads(path.read_text(encoding="utf-8"))
    feats = []
    for f in gj["features"]:
        p = f["properties"]
        nm = p.get("adm_nm", "")
        if not (str(p.get("sido", "")) == "11" or nm.startswith("서울특별시")):
            continue
        code8 = str(p.get("adm_cd2", ""))[:8]
        p["code8"] = code8
        parts = nm.split()
        p["gu"] = parts[1] if len(parts) > 1 else ""
        p["dong"] = " ".join(parts[2:]) if len(parts) > 2 else nm
        feats.append(f)
    gj["features"] = feats
    # 판정용 다각형 목록
    shapes = []
    for f in feats:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            ring = np.asarray(poly[0])
            shapes.append((f["properties"]["code8"], MPath(ring),
                           ring[:, 0].min(), ring[:, 0].max(), ring[:, 1].min(), ring[:, 1].max()))
    master = pd.DataFrame([{k: f["properties"][k] for k in ("code8", "gu", "dong", "adm_nm")} for f in feats])
    cent = []
    for f in feats:
        g = f["geometry"]
        ring = np.asarray((g["coordinates"][0][0] if g["type"] == "MultiPolygon" else g["coordinates"][0]))
        cent.append((ring[:, 1].mean(), ring[:, 0].mean()))
    master["lat"], master["lon"] = zip(*cent)
    return gj, shapes, master.drop_duplicates("code8")


def assign_dong(lon: np.ndarray, lat: np.ndarray, shapes) -> np.ndarray:
    out = np.full(len(lon), None, dtype=object)
    pts = np.column_stack([lon, lat])
    for code8, path, x0, x1, y0, y1 in shapes:
        cand = np.where((lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1) & (out == None))[0]  # noqa: E711
        if len(cand):
            hit = path.contains_points(pts[cand])
            out[cand[hit]] = code8
    return out


# --------------------------------------------------------------------------- ① 생활인구
def load_population(path: Path) -> tuple[pd.DataFrame, int]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
            raw = _read_csv(z.read(name), dtype=str, index_col=False)
    else:
        # 실제 파일은 각 행 끝에 빈 칸이 하나 더 있어(헤더 32개, 값 33개) index_col=False가 필요
        raw = _read_csv(path, dtype=str, index_col=False)
    try:
        c_day, c_h, c_code, c_tot = (_col(raw, "기준일"), _col(raw, "시간대"),
                                     _col(raw, "행정동코드"), _col(raw, "총생활인구"))
        df = raw[[c_day, c_h, c_code, c_tot]].copy()
    except KeyError:  # 일부 파일의 헤더 밀림 대비: 위치 기반
        df = raw.iloc[:, :4].copy()
    df.columns = ["day", "hour", "code8", "pop"]
    df["hour"] = pd.to_numeric(df["hour"], errors="coerce").astype("Int64")
    df["pop"] = pd.to_numeric(df["pop"].str.replace(",", ""), errors="coerce")
    df["code8"] = df["code8"].str.strip().str[:8]
    n_days = df["day"].nunique()
    hourly = df.groupby(["code8", "hour"], as_index=False)["pop"].mean()
    hourly["hour"] = hourly["hour"].astype(int)
    return hourly, n_days


# --------------------------------------------------------------------------- ②③ 버스
def load_bus(bus_path: Path, stop_path: Path, shapes, n_days: int):
    bus = _read_csv(bus_path, dtype=str)
    c_ars = _col(bus, "ARS")
    c_type = None
    try:
        c_type = _col(bus, "교통수단타입명")
    except KeyError:
        pass
    hour_cols = {}
    for c in bus.columns:
        m = re.match(r"^\s*(\d+)시\s*승차", str(c))
        if m:
            hour_cols[int(m.group(1))] = c
    board = bus[list(hour_cols.values())].apply(lambda s: pd.to_numeric(s.str.replace(",", ""), errors="coerce")).fillna(0)
    board.columns = list(hour_cols.keys())
    board["ARS"] = bus[c_ars].astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(5)
    board["is_owl"] = bus[c_type].astype(str).str.contains("심야") if c_type else False
    stop_hour = board.groupby("ARS")[list(hour_cols.keys())].sum() / n_days  # 일평균

    st = pd.read_excel(stop_path, dtype=str)
    c_sars, c_x, c_y = _col(st, "ARS"), _col(st, "X좌표", "경도", "X"), _col(st, "Y좌표", "위도", "Y")
    st = pd.DataFrame({"ARS": st[c_sars].str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(5),
                       "lon": pd.to_numeric(st[c_x], errors="coerce"),
                       "lat": pd.to_numeric(st[c_y], errors="coerce")}).dropna().drop_duplicates("ARS")
    st["code8"] = assign_dong(st.lon.values, st.lat.values, shapes)

    joined = stop_hour.join(st.set_index("ARS"), how="left")
    quality = {"bus_stop_rows": int(len(stop_hour)),
               "bus_stop_matched_coord": int(joined["lon"].notna().sum()),
               "bus_stop_matched_dong": int(joined["code8"].notna().sum()),
               "bus_board_total_daily": float(stop_hour.values.sum()),
               "bus_board_matched_share": float(stop_hour[joined["code8"].notna().values].values.sum()
                                                / max(stop_hour.values.sum(), 1))}
    joined = joined[joined["code8"].notna()]
    hours = list(range(24))
    joined[hours] = joined.reindex(columns=hours, fill_value=0)[hours]
    dong_hour = (joined.groupby("code8")[hours].sum().stack().rename("bus").reset_index()
                 .rename(columns={"level_1": "hour"}))
    joined["night_board"] = joined[NIGHT_HOURS].sum(axis=1)
    night_stops = joined[joined["night_board"] >= NIGHT_STOP_MIN].reset_index()[
        ["ARS", "lat", "lon", "code8", "night_board"]]
    owl_ars = set(board.loc[board["is_owl"], "ARS"])
    night_stops["owl_route_stop"] = night_stops["ARS"].isin(owl_ars)
    return dong_hour, night_stops, quality


# --------------------------------------------------------------------------- ④⑤ 지하철
def load_subway(sub_path: Path, station_path: Path, shapes, n_days: int, month: str | None = None):
    sub = _read_csv(sub_path, dtype=str)
    c_name = _col(sub, "지하철역", "역명")
    try:
        c_month = _col(sub, "사용월")
        months = sub[c_month].dropna().astype(str).str.strip().unique()
        pick = month if month in months else sorted(months)[-1]  # 생활인구와 같은 달
        sub = sub[sub[c_month].astype(str).str.strip() == pick]
        sub = sub.drop_duplicates()
    except KeyError:
        pass
    hour_cols = {}
    for c in sub.columns:
        m = re.match(r"^\s*(\d+)시\s*-\s*\d+시\s*승차", str(c))
        if m:
            hour_cols[int(m.group(1))] = c
    board = sub[list(hour_cols.values())].apply(lambda s: pd.to_numeric(s.str.replace(",", ""), errors="coerce")).fillna(0)
    board.columns = list(hour_cols.keys())
    board["key"] = sub[c_name].map(_norm_station)
    st_hour = board.groupby("key").sum() / n_days

    ms = _read_csv(station_path, dtype=str)
    ms = pd.DataFrame({"key": ms[_col(ms, "역사명", "역명")].map(_norm_station),
                       "lat": pd.to_numeric(ms[_col(ms, "위도")], errors="coerce"),
                       "lon": pd.to_numeric(ms[_col(ms, "경도")], errors="coerce")}).dropna()
    ms = ms.groupby("key", as_index=False)[["lat", "lon"]].mean()  # 환승역은 좌표 평균
    ms["code8"] = assign_dong(ms.lon.values, ms.lat.values, shapes)
    joined = st_hour.join(ms.set_index("key"), how="left")
    quality = {"subway_station_rows": int(len(st_hour)),
               "subway_station_matched": int(joined["code8"].notna().sum()),
               "subway_unmatched_names": sorted(joined.index[joined["code8"].isna()].tolist())[:30]}
    joined = joined[joined["code8"].notna()]
    hours = list(range(24))
    joined = joined.reindex(columns=hours + ["code8"], fill_value=0)
    dong_hour = (joined.groupby("code8")[hours].sum().stack().rename("subway").reset_index()
                 .rename(columns={"level_1": "hour"}))
    return dong_hour, quality


# --------------------------------------------------------------------------- 결합·지표
def build(force_synthetic: bool = False) -> dict:
    files = None if force_synthetic else _find(RAW)
    source = "real"
    if files is None:
        source = "synthetic"
        files = _find(SYN)
        if files is None:
            from make_synthetic import build as make
            make()
            files = _find(SYN)
    print(f"[데이터 출처] {source}  ← {files['pop'].parent}")

    gj, shapes, master = load_boundary(files["geo"])
    pop, n_days = load_population(files["pop"])
    month = re.search(r"(\d{6})", files["pop"].name).group(1)
    cal_days = calendar.monthrange(int(month[:4]), int(month[4:]))[1]  # 버스·지하철 월계 → 일평균
    bus_h, night_stops, q_bus = load_bus(files["bus"], files["stop"], shapes, cal_days)
    sub_h, q_sub = load_subway(files["sub"], files["station"], shapes, cal_days, month)

    grid = pd.MultiIndex.from_product([master.code8, range(24)], names=["code8", "hour"]).to_frame(index=False)
    h = (grid.merge(pop, how="left").merge(bus_h, how="left").merge(sub_h, how="left"))
    h[["bus", "subway"]] = h[["bus", "subway"]].fillna(0)  # ★ 0값 보존: 운행 0건은 0
    h["board"] = h["bus"] + h["subway"]
    h["rate10k"] = np.where(h["pop"] > 0, h["board"] / h["pop"] * 1e4, np.nan)
    h = h.merge(master[["code8", "gu", "dong"]], how="left")

    # 행정동별 심야 지표
    piv_pop = h.pivot(index="code8", columns="hour", values="pop")
    piv_bus = h.pivot(index="code8", columns="hour", values="bus")
    s = master.set_index("code8")[["gu", "dong", "adm_nm", "lat", "lon"]].copy()
    s["night_pop"] = piv_pop[NIGHT_HOURS].mean(axis=1)                       # 수요(체류)
    s["night_activity"] = piv_pop[[0, 1, 2, 3, 4]].diff(axis=1).abs().iloc[:, 1:].mean(axis=1)  # 수요(이동 변동)
    s["day_pop"] = piv_pop[list(range(9, 18))].mean(axis=1)
    s["night_bus"] = piv_bus[NIGHT_HOURS].sum(axis=1)                         # 판정 구간 일평균 승차
    s["service10k"] = np.where(s["night_pop"] > 0, s["night_bus"] / s["night_pop"] * 1e4, np.nan)
    s["night_stops"] = night_stops.groupby("code8").size().reindex(s.index).fillna(0).astype(int)
    # 도보 접근성: 행정동 중심점 → 가장 가까운 심야 운행 정류장 거리(km).
    # 동 안에 정류장이 없어도 바로 옆 동 정류장을 걸어서 이용할 수 있는 경우를 구분하기 위함.
    if len(night_stops):
        dlat = (s["lat"].values[:, None] - night_stops["lat"].values[None, :]) * 111.0
        dlon = (s["lon"].values[:, None] - night_stops["lon"].values[None, :]) * 88.2
        s["nearest_stop_km"] = np.sqrt(dlat ** 2 + dlon ** 2).min(axis=1)
    else:
        s["nearest_stop_km"] = np.inf
    s["evening_rate10k"] =h[h.hour.isin([21, 22])].groupby("code8")["rate10k"].mean()
    s["day_rate10k"] = h[h.hour.isin(range(9, 18))].groupby("code8")["rate10k"].mean()
    s = s.reset_index()
    pop_missing = int(s["night_pop"].isna().sum())
    s = s[s["night_pop"].notna()]

    OUT.mkdir(parents=True, exist_ok=True)
    h.to_csv(OUT / "dong_hourly.csv", index=False, encoding="utf-8-sig")
    s.to_csv(OUT / "dong_summary.csv", index=False, encoding="utf-8-sig")
    night_stops.to_csv(OUT / "night_stops.csv", index=False, encoding="utf-8-sig")
    (OUT / "seoul_dong.geojson").write_text(json.dumps(gj, ensure_ascii=False), encoding="utf-8")
    meta = {"source": source, "month": re.search(r"(\d{6})", files["pop"].name).group(1),
            "n_days": n_days, "cal_days": cal_days, "night_hours": NIGHT_HOURS, "night_stop_min": NIGHT_STOP_MIN,
            "n_dong": int(len(s)), "dong_without_population": pop_missing,
            "files": {k: v.name for k, v in files.items()}, **q_bus, **q_sub}
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items() if k != "subway_unmatched_names"}, ensure_ascii=False, indent=1))
    return meta


if __name__ == "__main__":
    import sys
    build(force_synthetic="--synthetic" in sys.argv)
