"""
가상 원천 데이터 생성기
=======================
실제 서울 열린데이터광장 파일과 '같은 파일명 규칙 · 같은 컬럼명 · 같은 코드 체계'로
가상 데이터를 만든다. 실제 데이터를 내려받지 못했을 때 파이프라인 전체를 검증하고
대시보드·발표 자료를 미리 만들기 위한 용도다. (교수님 안내: "데이터는 만들어도 됨")

생성 파일 (data/synthetic/)
  ① LOCAL_PEOPLE_DONG_202606.zip                       행정동 생활인구(내국인)
  ② 2026년_버스노선별_정류장별_시간대별_승하차_인원_정보(06월).csv
  ③ 서울시버스정류소위치정보(20260701).xlsx
  ④ 서울시_지하철_호선별_역별_시간대별_승하차_인원_정보_202606.csv
  ⑤ 서울시_역사마스터_정보.csv
  ⑥ HangJeongDong_ver20260701.geojson                  행정동 경계

※ 행정동 이름은 '강남구 03동'처럼 가상 이름이다. 자치구(25개)·자치구 코드·대략적 위치,
  올빼미버스가 도심(종로·동대문·서울역·강남역)을 방사형으로 지나는 구조는 실제를 본떴다.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import ConvexHull, Voronoi

SEED = 20260616
YM = "202606"
DAYS = 30
OUT = Path(__file__).resolve().parents[1] / "data" / "synthetic"

# 자치구: (코드5, 이름, 중심 위도, 중심 경도, 행정동 수)
GU = [
    ("11110", "종로구", 37.594, 126.977, 17), ("11140", "중구", 37.560, 126.996, 15),
    ("11170", "용산구", 37.531, 126.980, 16), ("11200", "성동구", 37.551, 127.041, 17),
    ("11215", "광진구", 37.546, 127.086, 15), ("11230", "동대문구", 37.582, 127.055, 14),
    ("11260", "중랑구", 37.598, 127.093, 16), ("11290", "성북구", 37.606, 127.023, 20),
    ("11305", "강북구", 37.643, 127.011, 13), ("11320", "도봉구", 37.669, 127.032, 14),
    ("11350", "노원구", 37.652, 127.075, 19), ("11380", "은평구", 37.619, 126.927, 16),
    ("11410", "서대문구", 37.578, 126.939, 14), ("11440", "마포구", 37.559, 126.908, 16),
    ("11470", "양천구", 37.525, 126.856, 18), ("11500", "강서구", 37.561, 126.823, 20),
    ("11530", "구로구", 37.494, 126.856, 15), ("11545", "금천구", 37.461, 126.901, 10),
    ("11560", "영등포구", 37.522, 126.910, 18), ("11590", "동작구", 37.498, 126.951, 15),
    ("11620", "관악구", 37.467, 126.945, 21), ("11650", "서초구", 37.473, 127.031, 18),
    ("11680", "강남구", 37.497, 127.063, 22), ("11710", "송파구", 37.505, 127.115, 27),
    ("11740", "강동구", 37.550, 127.147, 19),
]

# 서울 외곽선(볼록 근사)
OUTLINE = np.array([
    (37.700, 127.050), (37.690, 127.100), (37.630, 127.120), (37.580, 127.180),
    (37.530, 127.180), (37.470, 127.140), (37.430, 127.070), (37.430, 126.980),
    (37.440, 126.900), (37.470, 126.830), (37.530, 126.765), (37.580, 126.790),
    (37.630, 126.880), (37.670, 126.950),
])

# 번화가(심야 유흥·환승 거점) / 업무지구 / 산업·물류(야간 근무) 앵커
NIGHTLIFE = [(37.498, 127.028), (37.505, 127.025), (37.557, 126.924), (37.570, 126.991),
             (37.534, 126.994), (37.484, 126.929), (37.540, 127.070), (37.516, 126.907),
             (37.571, 127.009)]
BUSINESS = [(37.566, 126.978), (37.521, 126.924), (37.503, 127.040), (37.575, 126.985)]
INDUSTRIAL = [(37.472, 126.885), (37.458, 126.897), (37.485, 126.901), (37.562, 126.830),
              (37.485, 127.122), (37.545, 127.056), (37.476, 127.143), (37.452, 126.905),
              (37.600, 127.098), (37.567, 126.812)]

# 올빼미버스(가상) 노선: 도심 방사형. (노선번호, [(위도, 경도), ...])
OWL = [
    ("N15", [(37.689, 127.046), (37.638, 127.025), (37.613, 127.030), (37.570, 126.991),
             (37.555, 126.972), (37.513, 126.942), (37.484, 126.929)]),
    ("N13", [(37.660, 127.073), (37.655, 127.062), (37.580, 127.047), (37.571, 127.009),
             (37.570, 126.991), (37.535, 127.006), (37.498, 127.028), (37.484, 127.034)]),
    ("N16", [(37.637, 126.919), (37.619, 126.921), (37.555, 126.937), (37.570, 126.991),
             (37.571, 127.009), (37.561, 127.037), (37.540, 127.070), (37.513, 127.100),
             (37.538, 127.124)]),
    ("N26", [(37.578, 126.812), (37.559, 126.838), (37.557, 126.924), (37.555, 126.937),
             (37.555, 126.972), (37.570, 126.991), (37.580, 127.047), (37.606, 127.093)]),
    ("N37", [(37.517, 126.866), (37.516, 126.907), (37.521, 126.924), (37.544, 126.946),
             (37.555, 126.972), (37.534, 126.994), (37.498, 127.028), (37.513, 127.100)]),
    ("N61", [(37.517, 126.866), (37.485, 126.901), (37.484, 126.929), (37.476, 126.981),
             (37.498, 127.028), (37.505, 127.060), (37.513, 127.100)]),
    ("N30", [(37.553, 127.153), (37.538, 127.124), (37.540, 127.070), (37.561, 127.037),
             (37.571, 127.009), (37.570, 126.991), (37.555, 126.972), (37.544, 126.946),
             (37.525, 126.870)]),
    ("N40", [(37.640, 126.915), (37.590, 126.935), (37.555, 126.972), (37.530, 126.965),
             (37.534, 126.994), (37.498, 127.028)]),
    ("N72", [(37.689, 127.046), (37.655, 127.062), (37.612, 127.078), (37.580, 127.047),
             (37.561, 127.037)]),
    ("N32", [(37.550, 126.860), (37.528, 126.875), (37.516, 126.907), (37.513, 126.942),
             (37.476, 126.981), (37.488, 127.000), (37.484, 127.034)]),
    ("N62", [(37.540, 127.070), (37.561, 127.037), (37.571, 127.009), (37.570, 126.991),
             (37.557, 126.924), (37.550, 126.905)]),
]

KM_LAT, KM_LON = 111.0, 88.2  # 서울 위도에서 1도당 km


def _inside_hull(pts, hull_pts):
    from matplotlib.path import Path as MPath
    return MPath(hull_pts).contains_points(pts)


def _clip(poly, clip):
    """Sutherland-Hodgman: 볼록 clip 다각형으로 poly를 자른다."""
    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0

    def inter(p1, p2, a, b):
        x1, y1 = p1; x2, y2 = p2; x3, y3 = a; x4, y4 = b
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-15:
            return p2
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    out = list(poly)
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        inp, out = out, []
        if not inp:
            break
        s = inp[-1]
        for e in inp:
            if inside(e, a, b):
                if not inside(s, a, b):
                    out.append(inter(s, e, a, b))
                out.append(e)
            elif inside(s, a, b):
                out.append(inter(s, e, a, b))
            s = e
    return out


def _dist_km(lat, lon, plat, plon):
    return np.hypot((lat - plat) * KM_LAT, (lon - plon) * KM_LON)


def _dist_to_polyline_km(lat, lon, line):
    best = np.full(np.shape(lat), np.inf)
    for (a_lat, a_lon), (b_lat, b_lon) in zip(line[:-1], line[1:]):
        ax, ay = a_lon * KM_LON, a_lat * KM_LAT
        bx, by = b_lon * KM_LON, b_lat * KM_LAT
        px, py = np.asarray(lon) * KM_LON, np.asarray(lat) * KM_LAT
        dx, dy = bx - ax, by - ay
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0, 1)
        best = np.minimum(best, np.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def build():
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- 행정동 배치
    hull = OUTLINE[ConvexHull(OUTLINE[:, ::-1]).vertices]  # (lat, lon) 반시계
    hull_xy = hull[:, ::-1]  # (lon, lat)
    rows = []
    for code5, gname, clat, clon, n in GU:
        k = 0
        while k < n:
            lat = clat + rng.normal(0, 0.012)
            lon = clon + rng.normal(0, 0.015)
            if not _inside_hull(np.array([[lon, lat]]), hull_xy)[0]:
                continue
            k += 1
            rows.append(dict(code5=code5, gu=gname, lat=lat, lon=lon,
                             code8=f"{code5}5{k:02d}", dong=f"{k:02d}동"))
    dong = pd.DataFrame(rows)
    # 동 이름: '강남구 03동' 형태(가상)
    dong["adm_nm"] = "서울특별시 " + dong["gu"] + " " + dong["dong"]

    # 유형: 번화가 / 업무 / 산업·물류 / 주거
    def near(anchors, r):
        d = np.min([_dist_km(dong.lat.values, dong.lon.values, a, b) for a, b in anchors], axis=0)
        return d < r
    dong["type"] = "주거"
    dong.loc[near(INDUSTRIAL, 1.6), "type"] = "산업·물류"
    dong.loc[near(BUSINESS, 1.2), "type"] = "업무"
    dong.loc[near(NIGHTLIFE, 1.1), "type"] = "번화가"

    # 경계: Voronoi + 서울 외곽 클리핑
    pts = dong[["lon", "lat"]].values
    far = np.array([[126.0, 36.8], [128.0, 36.8], [128.0, 38.4], [126.0, 38.4]])
    vor = Voronoi(np.vstack([pts, far]))
    polys = []
    for i in range(len(pts)):
        region = vor.regions[vor.point_region[i]]
        cell = [tuple(vor.vertices[v]) for v in region if v >= 0]
        polys.append(_clip(cell, [tuple(p) for p in hull_xy]))

    features = []
    for (_, r), poly in zip(dong.iterrows(), polys):
        ring = [[round(x, 6), round(y, 6)] for x, y in poly] + [[round(poly[0][0], 6), round(poly[0][1], 6)]]
        features.append({"type": "Feature", "properties": {
            "adm_nm": r.adm_nm, "adm_cd": r.code8[:7], "adm_cd2": r.code8 + "00",
            "sgg": r.code5, "sido": "11", "sidonm": "서울특별시", "sggnm": r.gu},
            "geometry": {"type": "Polygon", "coordinates": [ring]}})
    # 서울 밖 행정동 1개(필터링 검증용)
    features.append({"type": "Feature", "properties": {
        "adm_nm": "경기도 가상시 가상동", "adm_cd": "3101011", "adm_cd2": "4111051000",
        "sgg": "41110", "sido": "41", "sidonm": "경기도", "sggnm": "가상시"},
        "geometry": {"type": "Polygon", "coordinates": [[[127.3, 37.3], [127.35, 37.3], [127.35, 37.35], [127.3, 37.3]]]}})
    (OUT / "HangJeongDong_ver20260701.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")

    # ---------------------------------------------------------------- ① 생활인구
    resident = rng.lognormal(np.log(21500), 0.33, len(dong))
    # 시간대별 인구 배율 (0~23시)
    h = np.arange(24)
    prof = {
        "주거": np.select([(h >= 9) & (h <= 17), h == 22, h == 23, h == 0, h == 1, (h >= 2) & (h <= 6)],
                        [0.82, 0.97, 0.99, 1.01, 1.03, 1.04], 0.95),
        "업무": np.where((h >= 9) & (h <= 17), 2.6, np.where((h >= 22) | (h <= 6), 0.42, 1.3)),
        "번화가": np.select([(h >= 19) & (h <= 23), h == 0, h == 1, h == 2, h == 3, (h >= 4) & (h <= 6)],
                          [1.75, 1.62, 1.48, 1.33, 1.18, 1.05], 1.25),
        "산업·물류": np.select([(h >= 9) & (h <= 17), h == 22, h == 23, h == 0, h == 1, h == 2, (h >= 3) & (h <= 5)],
                            [1.55, 1.30, 1.22, 1.16, 1.12, 1.10, 1.08], 1.25),
    }
    lp_rows = []
    dates = pd.date_range(f"{YM[:4]}-{YM[4:]}-01", periods=DAYS)
    for di, d in enumerate(dates):
        wk = 1.10 if d.dayofweek in (4, 5) else 1.0  # 금·토 밤
        for i, r in dong.iterrows():
            base = resident[i] * prof[r.type] * rng.normal(1, 0.025)
            if r.type == "번화가":
                base = np.where((h <= 2) | (h >= 20), base * wk, base)
            lp_rows.append(pd.DataFrame({"기준일ID": d.strftime("%Y%m%d"), "시간대구분": h,
                                         "행정동코드": r.code8, "총생활인구수": np.round(base, 4)}))
    lp = pd.concat(lp_rows, ignore_index=True)
    lp["남자0세부터9세생활인구수"] = np.round(lp["총생활인구수"] * 0.041, 4)
    lp["여자0세부터9세생활인구수"] = np.round(lp["총생활인구수"] * 0.039, 4)
    lp["남자20세부터24세생활인구수"] = np.round(lp["총생활인구수"] * 0.031, 4)
    lp["여자20세부터24세생활인구수"] = np.round(lp["총생활인구수"] * 0.033, 4)
    buf = io.StringIO(); lp.to_csv(buf, index=False)
    with zipfile.ZipFile(OUT / f"LOCAL_PEOPLE_DONG_{YM}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"LOCAL_PEOPLE_DONG_{YM}.csv", buf.getvalue().encode("cp949"))
    night_pop = resident * np.array([prof[t][2] for t in dong.type])

    # ---------------------------------------------------------------- ③ 정류소 + ② 버스
    stops = []
    ars = 1000
    centrality = 1 / (1 + _dist_km(dong.lat.values, dong.lon.values, 37.555, 126.985) / 9)
    for i, r in dong.iterrows():
        n = max(6, rng.poisson(16 + 18 * centrality[i]))
        for _ in range(n):
            ars += rng.integers(1, 4)
            stops.append(dict(ARS_ID=ars, NODE_ID=100000000 + ars * 7,
                              lat=r.lat + rng.normal(0, 0.0028), lon=r.lon + rng.normal(0, 0.0035),
                              seed_dong=i, owl=None))
    # 올빼미 정류장: 노선을 따라 약 450m 간격 (기존 정류장 재사용 or 신설)
    owl_stop_routes: dict[int, list[str]] = {}
    for route, line in OWL:
        for (a_lat, a_lon), (b_lat, b_lon) in zip(line[:-1], line[1:]):
            seg_km = np.hypot((b_lat - a_lat) * KM_LAT, (b_lon - a_lon) * KM_LON)
            for t in np.linspace(0, 1, max(2, int(seg_km / 0.45)), endpoint=False):
                lat, lon = a_lat + t * (b_lat - a_lat), a_lon + t * (b_lon - a_lon)
                # 가장 가까운 동
                di = int(np.argmin(_dist_km(dong.lat.values, dong.lon.values, lat, lon)))
                ars += rng.integers(1, 4)
                stops.append(dict(ARS_ID=ars, NODE_ID=100000000 + ars * 7, lat=lat + rng.normal(0, 0.0004),
                                  lon=lon + rng.normal(0, 0.0005), seed_dong=di, owl=route))
                owl_stop_routes.setdefault(len(stops) - 1, []).append(route)
    st = pd.DataFrame(stops)
    st["정류소명"] = [f"{dong.gu[s]} {dong.dong[s]} 정류장{j % 9 + 1}" for j, s in enumerate(st.seed_dong)]

    # 시간대별 1인당 승차 프로파일 (일평균, 인구 1만 명당, 동 전체 기준)
    bus_rate = np.array([22, 1.2, 0.0, 0.0, 9, 55, 160, 330, 420, 270, 190, 175,
                         180, 175, 170, 175, 200, 255, 300, 215, 150, 125, 95, 62], dtype=float)
    dong_stops = st[st.owl.isna()].groupby("seed_dong").size()
    type_board = {"주거": 1.0, "업무": 1.5, "번화가": 1.35, "산업·물류": 1.1}
    owl_mult = {"주거": 1.0, "업무": 0.9, "번화가": 3.4, "산업·물류": 1.9}
    bus_rows = []
    routes_regular = [f"{rng.integers(100, 7800)}" for _ in range(420)]
    for si, s in st.iterrows():
        d = dong.iloc[s.seed_dong]
        board = np.zeros(24); alight = np.zeros(24)
        if pd.isna(s.owl):
            pop_day = resident[s.seed_dong] * prof[d.type]
            per_stop = pop_day / 1e4 * bus_rate * type_board[d.type] / dong_stops[s.seed_dong]
            per_stop *= rng.lognormal(0, 0.45)
            n_routes = int(rng.integers(2, 6))
            shares = rng.dirichlet(np.ones(n_routes))
            for k in range(n_routes):
                b = rng.poisson(per_stop * shares[k] * DAYS)
                a = rng.poisson(per_stop * shares[k] * DAYS * rng.uniform(0.8, 1.2))
                route = routes_regular[int(rng.integers(0, len(routes_regular)))]
                bus_rows.append((route, s, b, a, "131", "서울간선버스" if int(route) < 1000 else "서울지선버스"))
        else:
            # 올빼미: 23~04시만 운행, 동의 심야 인구·유형에 비례
            for route in owl_stop_routes.get(si, [s.owl]):
                base = 2.1 * night_pop[s.seed_dong] / 21500 * owl_mult[d.type] * rng.lognormal(0, 0.5)
                shape = np.zeros(24)
                shape[[23, 0, 1, 2, 3, 4]] = [0.55, 1.1, 1.0, 0.85, 0.55, 0.15]
                b = rng.poisson(base * shape * DAYS)
                a = rng.poisson(base * shape * DAYS * rng.uniform(0.8, 1.2))
                bus_rows.append((route, s, b, a, "131", "서울심야버스"))
    rec = []
    for route, s, b, a, tcode, tname in bus_rows:
        row = {"사용년월": YM, "노선번호": route, "노선명": f"{route}번(가상)",
               "표준버스정류장ID": s.NODE_ID, "버스정류장ARS번호": f"{s.ARS_ID:05d}", "역명": s.정류소명}
        for hh in range(24):
            lab = "00" if hh == 0 else str(hh)
            row[f"{lab}시승차총승객수"] = int(b[hh]); row[f"{lab}시하차총승객수"] = int(a[hh])
        row.update({"교통수단타입코드": tcode, "교통수단타입명": tname, "등록일자": "20260706"})
        rec.append(row)
    bus = pd.DataFrame(rec)
    bus.to_csv(OUT / "2026년_버스노선별_정류장별_시간대별_승하차_인원_정보(06월).csv",
               index=False, encoding="cp949")

    st_out = pd.DataFrame({"NODE_ID": st.NODE_ID, "ARS_ID": st.ARS_ID,  # ARS 앞자리 0 탈락 재현(정수)
                           "정류소명": st.정류소명, "X좌표": st.lon.round(7), "Y좌표": st.lat.round(7),
                           "정류소타입": np.where(st.owl.isna(), "가로변시간", "중앙차로")})
    st_out.to_excel(OUT / "서울시버스정류소위치정보(20260701).xlsx", index=False)

    # ---------------------------------------------------------------- ④⑤ 지하철
    weight = centrality ** 2 * np.where(dong.type.isin(["번화가", "업무"]), 3, 1)
    chosen = rng.choice(len(dong), size=230, replace=False, p=weight / weight.sum())
    lines = ["1호선", "2호선", "3호선", "4호선", "5호선", "6호선", "7호선", "8호선", "9호선"]
    sub_rate = np.array([30, 3, 0, 0, 0, 70, 260, 560, 690, 380, 260, 240,
                         250, 245, 245, 260, 300, 420, 520, 380, 300, 270, 230, 170], dtype=float)
    master, sub = [], []
    for j, di in enumerate(chosen):
        d = dong.iloc[di]
        name = f"{d.gu[:-1]}{d.dong[:-1]}"  # 예: 강남03
        line = lines[j % 9]
        lat, lon = d.lat + rng.normal(0, 0.002), d.lon + rng.normal(0, 0.0025)
        # 역사마스터 표기는 일부 '역' 접미사 포함(이름 정규화 검증용)
        master.append({"역사_ID": 1000 + j, "역사명": name + ("역" if j % 5 == 0 else ""),
                       "호선": line, "위도": round(lat, 6), "경도": round(lon, 6)})
        pop_day = resident[di] * prof[d.type]
        dayboard = pop_day / 1e4 * sub_rate * rng.lognormal(0, 0.4) * (1.6 if d.type == "번화가" else 1)
        row = {"사용월": YM, "호선명": line, "지하철역": name}
        order = list(range(4, 24)) + [0, 1, 2, 3]
        for hh in order:
            lab = f"{hh:02d}시-{(hh + 1) % 24:02d}시"
            row[f"{lab} 승차인원"] = int(rng.poisson(dayboard[hh] * DAYS))
            row[f"{lab} 하차인원"] = int(rng.poisson(dayboard[hh] * DAYS * 0.98))
        row["작업일자"] = "20260703"
        sub.append(row)
    pd.DataFrame(sub).to_csv(OUT / f"서울시_지하철_호선별_역별_시간대별_승하차_인원_정보_{YM}.csv",
                             index=False, encoding="cp949")
    pd.DataFrame(master).to_csv(OUT / "서울시_역사마스터_정보.csv", index=False, encoding="cp949")

    dong.assign(resident=resident.round(0)).to_csv(OUT / "_정답지_가상동_유형.csv", index=False, encoding="utf-8-sig")
    print(f"가상 데이터 생성 완료 → {OUT}  (행정동 {len(dong)}개, 정류장 {len(st)}개, 버스행 {len(bus)}개)")


if __name__ == "__main__":
    build()
