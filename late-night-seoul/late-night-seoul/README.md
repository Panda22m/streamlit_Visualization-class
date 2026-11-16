# 막차 이후의 서울 — 심야 교통 사각지대 시각화

평균이 아니라 **최저선(최소 Limit)** 관점으로, 사람은 있는데 심야 대중교통이 끊긴 서울 행정동을 찾는 프로젝트입니다.

## 폴더 구조

```
late-night-seoul/
├─ app.py                  Streamlit 대시보드
├─ requirements.txt
├─ src/
│  ├─ preprocess.py        원천 6종 → 행정동 지표 (실제 데이터 우선, 없으면 가상)
│  ├─ metrics.py           최소 Limit·사각지대·우선순위 판정 규칙 (대시보드와 PPT 공용)
│  ├─ figures.py           발표용 그림 3장 + numbers.json
│  └─ make_synthetic.py    실제 파일과 같은 구조의 가상 데이터 생성기
├─ data/
│  ├─ raw/                 ← 실제 파일 6종을 여기에 넣는다
│  ├─ synthetic/           가상 데이터
│  └─ processed/           전처리 결과 (대시보드가 읽는 파일)
└─ figures/                fig1_cliff.png, fig2_scatter.png, fig3_map.png, numbers.json
```

## 1. 설치

```bash
pip install -r requirements.txt
```

## 2. 실제 데이터 넣기 (기준월 2026년 6월)

`data/raw/` 폴더에 아래 6개 파일을 **이름을 바꾸지 말고** 그대로 넣습니다.

| 파일 | 출처 |
|---|---|
| `LOCAL_PEOPLE_DONG_202606.zip` 또는 `.csv` | 서울 열린데이터광장 OA-14991 (행정동 단위 서울 생활인구, 내국인) |
| `2026년_버스노선별_정류장별_시간대별_승하차_인원_정보(06월).csv` | OA-12913 |
| `서울시버스정류소위치정보(20260701).xlsx` | OA-15067 |
| 지하철 시간대별 CSV (파일명에 `지하철`·`시간대별` 포함) | OA-12252 |
| 역사마스터 CSV (파일명에 `역사마스터` 포함) | 서울시 역사마스터 정보 |
| 행정동 경계 `.geojson` | GitHub `vuski/admdongkor` 의 `ver20260701` 폴더 |

> 6개가 **모두** 있어야 실제 데이터로 처리합니다. 하나라도 없으면 가상 데이터로 처리하고 화면 상단에 노란 안내가 뜹니다.

## 3. 실행 순서

```bash
python src/preprocess.py     # 전처리 → data/processed/
python src/figures.py        # 발표용 그림 3장 → figures/
streamlit run app.py         # 대시보드 → http://localhost:8501
```

`python src/preprocess.py --synthetic` 으로 실제 파일이 있어도 가상 데이터로 돌려볼 수 있습니다.

## 4. 웹 링크로 제출하기 (Streamlit Community Cloud, 무료)

1. 이 폴더를 GitHub 저장소로 올립니다. (`data/processed/` 포함)
2. https://share.streamlit.io 에서 GitHub 로그인 → **Create app** → 저장소 선택, Main file = `app.py`
3. 배포가 끝나면 나오는 `https://….streamlit.app` 주소를 PPT 제출 안내 슬라이드에 적습니다.

## 비교 기준 (metrics.py) — 복합 지수 없음, 원본 수치의 비율만 사용

| 항목 | 정의 |
|---|---|
| 판정 시간 | 01:00~04:00 (01·02·03시대). 00시대는 일반버스 막차 승차 88.5% 포함으로 제외 |
| 심야 생활인구 | 01·02·03시대 평균 생활인구 |
| 이용 비율 | 01~04시 버스 승차(일평균) ÷ 심야 생활인구 × 10,000 |
| 최소 Limit 미달 | 이용 비율 ≤ 서울 행정동 하위 10% 값, 또는 01~04시 승차 정류장 0개 |
| 사각지대 | 최소 Limit 미달 AND 심야 생활인구 ≥ 서울 중앙값 |

## 실제 데이터 결과 (2026년 6월)

- 분석 행정동 415개 (경계·생활인구 코드 불일치 12개 제외)
- 하한선 1만 명당 0.02명 · 최소 Limit 미달 42개 동 · 사각지대 11개 동 (모두 01~04시 버스 승차 0명)
