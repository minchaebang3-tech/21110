


import re
from io import BytesIO

import requests
import pandas as pd
import streamlit as st
import plotly.express as px

# -----------------------------------
# 1. 기본 설정
# -----------------------------------
st.set_page_config(
    page_title="인구 피라미드 탐험기",
    page_icon="👥",
    layout="wide"
)

st.title("👥 인구 피라미드 탐험기")
st.caption("연도와 지역을 선택해 남녀별 연령 인구 구조를 살펴보세요.")

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"


# -----------------------------------
# 2. 데이터 불러오기
# -----------------------------------
@st.cache_data(show_spinner="인구 데이터를 불러오는 중입니다...")
def load_population():
    response = requests.get(POP_URL, timeout=60)
    response.raise_for_status()

    # 코드 열은 앞자리 0이 사라지지 않도록 문자로 읽습니다.
    return pd.read_csv(
        BytesIO(response.content),
        compression="gzip",
        dtype={"코드": str}
    )


@st.cache_data(show_spinner="지도 경계를 불러오는 중입니다...")
def load_geojson():
    response = requests.get(GEO_URL, timeout=30)
    response.raise_for_status()
    return response.json()


# -----------------------------------
# 3. 나이 추출 함수
# -----------------------------------
def age_of(column):
    # 예: 남_65세 -> 65
    match = re.match(r"(?:남|여|계)_(\d+)세", column)
    return int(match.group(1)) if match else None


# -----------------------------------
# 4. 데이터 불러오기
# -----------------------------------
try:
    df = load_population()
    geojson = load_geojson()
except Exception as error:
    st.error(f"데이터를 불러오지 못했습니다: {error}")
    st.stop()

df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
df["코드"] = df["코드"].astype("string").str.strip()
df["시군구코드"] = df["코드"].str[:5]


# -----------------------------------
# 5. 연도와 지역 목록 만들기
# -----------------------------------
years = sorted(
    df["연도"].dropna().astype(int).unique().tolist()
)

regions = pd.DataFrame([
    {
        "시군구코드": str(f["properties"]["코드"]).zfill(5),
        "시군구": str(f["properties"]["시군구"]),
        "시도": str(f["properties"]["시도"])
    }
    for f in geojson["features"]
]).drop_duplicates("시군구코드")

regions["표시이름"] = regions["시도"] + " " + regions["시군구"]


# -----------------------------------
# 6. 사용자 선택
# -----------------------------------
st.sidebar.header("🔎 탐험 설정")

latest_year = max(years)

selected_year = st.sidebar.selectbox(
    "연도",
    options=years,
    index=years.index(latest_year)
)

province_options = ["전국"] + sorted(
    regions["시도"].unique().tolist()
)

selected_province = st.sidebar.selectbox(
    "시도",
    options=province_options
)

if selected_province == "전국":
    available_regions = regions.copy()
else:
    available_regions = regions[
        regions["시도"] == selected_province
    ].copy()

region_options = ["전국"] + sorted(
    available_regions["표시이름"].tolist()
)

selected_region = st.sidebar.selectbox(
    "시군구",
    options=region_options
)


# -----------------------------------
# 7. 선택한 지역의 인구 데이터 추출
# -----------------------------------
year_df = df[df["연도"] == selected_year].copy()

if selected_region == "전국":
    selected_codes = available_regions["시군구코드"].tolist()

    selected_df = year_df[
        year_df["시군구코드"].isin(selected_codes)
    ].copy()

    region_title = (
        selected_province
        if selected_province != "전국"
        else "전국"
    )

else:
    chosen = available_regions[
        available_regions["표시이름"] == selected_region
    ].iloc[0]

    selected_df = year_df[
        year_df["시군구코드"] == chosen["시군구코드"]
    ].copy()

    region_title = selected_region


# -----------------------------------
# 8. 남녀별 연령 인구 열 찾기
# -----------------------------------
male_cols = [
    c for c in selected_df.columns
    if c.startswith("남_") and age_of(c) is not None
]

female_cols = [
    c for c in selected_df.columns
    if c.startswith("여_") and age_of(c) is not None
]

# 100세 이상 열은 나이 추출 정규식에 걸리지 않으므로 따로 추가합니다.
if "남_100세 이상" in selected_df.columns:
    male_cols.append("남_100세 이상")

if "여_100세 이상" in selected_df.columns:
    female_cols.append("여_100세 이상")

male_cols = list(dict.fromkeys(male_cols))
female_cols = list(dict.fromkeys(female_cols))

if not male_cols or not female_cols:
    st.error("남녀별 연령 인구 열을 찾지 못했습니다.")
    st.stop()


# -----------------------------------
# 9. 인구 합산
# -----------------------------------
for col in male_cols + female_cols:
    selected_df[col] = pd.to_numeric(
        selected_df[col],
        errors="coerce"
    ).fillna(0)

male_sum = selected_df[male_cols].sum()
female_sum = selected_df[female_cols].sum()

age_rows = []

for col in male_cols:
    age = age_of(col)

    if age is not None:
        age_rows.append({
            "나이": age,
            "연령대": f"{age}세",
            "남성": float(male_sum[col]),
            "여성": 0.0
        })

for col in female_cols:
    age = age_of(col)

    if age is not None:
        age_rows.append({
            "나이": age,
            "연령대": f"{age}세",
            "남성": 0.0,
            "여성": float(female_sum[col])
        })

# 100세 이상은 별도 연령대로 추가합니다.
for sex, col, values in [
    ("남성", "남_100세 이상", male_sum),
    ("여성", "여_100세 이상", female_sum)
]:
    if col in selected_df.columns:
        age_rows.append({
            "나이": 100,
            "연령대": "100세 이상",
            "남성": float(values[col]) if sex == "남성" else 0.0,
            "여성": float(values[col]) if sex == "여성" else 0.0
        })

age_df = pd.DataFrame(age_rows)

age_df = (
    age_df.groupby(["나이", "연령대"], as_index=False)[
        ["남성", "여성"]
    ]
    .sum()
    .sort_values("나이")
)


# -----------------------------------
# 10. 요약 통계
# -----------------------------------
male_total = age_df["남성"].sum()
female_total = age_df["여성"].sum()
all_total = male_total + female_total

elderly_total = age_df.loc[
    age_df["나이"] >= 65,
    ["남성", "여성"]
].sum().sum()

elderly_rate = (
    elderly_total / all_total * 100
    if all_total > 0
    else 0
)

c1, c2, c3, c4 = st.columns(4)

c1.metric("기준 연도", f"{selected_year}년")
c2.metric("전체 인구", f"{all_total:,.0f}명")
c3.metric("남성 인구", f"{male_total:,.0f}명")
c4.metric("65세 이상 비율", f"{elderly_rate:.2f}%")


# -----------------------------------
# 11. 인구 피라미드 그래프
# -----------------------------------
st.divider()

st.subheader(
    f"📊 {region_title} 인구 피라미드 ({selected_year}년)"
)

st.write(
    "왼쪽은 남성, 오른쪽은 여성입니다. "
    "막대 길이로 연령별 인구 규모를 비교할 수 있습니다."
)

plot_df = age_df.copy()

# 남성 인구를 음수로 바꾸면 그래프 왼쪽에 표시됩니다.
plot_df["남성"] = -plot_df["남성"]

fig = px.bar(
    plot_df.sort_values("나이", ascending=True),
    x=["남성", "여성"],
    y="연령대",
    orientation="h",
    barmode="relative",
    labels={
        "value": "인구 수(명)",
        "연령대": "연령대",
        "variable": "성별"
    },
    color_discrete_map={
        "남성": "#6BAED6",
        "여성": "#F28EAD"
    }
)

# x축의 음수 눈금도 양수 인구로 표시합니다.
max_population = max(
    plot_df["남성"].abs().max(),
    plot_df["여성"].max()
)

tick_values = [
    -max_population,
    -max_population / 2,
    0,
    max_population / 2,
    max_population
]

tick_text = [
    f"{abs(value):,.0f}"
    for value in tick_values
]

fig.update_xaxes(
    tickvals=tick_values,
    ticktext=tick_text,
    title="인구 수(명)",
    zeroline=True
)

fig.update_layout(
    height=850,
    yaxis_title="연령대",
    legend_title="성별",
    margin=dict(l=20, r=20, t=30, b=20),
    bargap=0.08
)

st.plotly_chart(
    fig,
    use_container_width=True
)


# -----------------------------------
# 12. 연령별 인구 표
# -----------------------------------
st.subheader("📋 연령별 인구")

table_df = age_df[
    ["연령대", "남성", "여성"]
].copy()

table_df["남성"] = table_df["남성"].map(
    lambda x: f"{x:,.0f}명"
)

table_df["여성"] = table_df["여성"].map(
    lambda x: f"{x:,.0f}명"
)

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True
)


# -----------------------------------
# 13. 그래프 읽는 방법
# -----------------------------------
with st.expander("💡 인구 피라미드 읽는 방법"):
    st.markdown(
        """
        - **가로축:** 해당 연령대의 인구 수입니다.
        - **세로축:** 나이 구간입니다.
        - **왼쪽 막대:** 남성 인구입니다.
        - **오른쪽 막대:** 여성 인구입니다.
        - **아래쪽이 넓으면:** 상대적으로 어린 연령대 인구가 많은 구조입니다.
        - **위쪽이 넓으면:** 상대적으로 고령층 인구가 많은 구조입니다.
        - 이 그래프는 선택한 연도의 인구 현황이며,
          미래 인구를 예측한 결과는 아닙니다.
        """
    )
    
