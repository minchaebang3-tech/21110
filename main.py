

import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import plotly.express as px

# -----------------------------------------
# 1. 기본 설정
# -----------------------------------------
st.set_page_config(
    page_title="전국 고령화 지도",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ 전국 고령화 지도")
st.caption("시군구별 65세 이상 인구 비율을 한눈에 확인해 보세요.")

# 데이터 주소
POPULATION_URL = (
    "https://raw.githubusercontent.com/greatsong/"
    "modudata/main/data/population_yearly.csv.gz"
)

GEOJSON_URL = (
    "https://raw.githubusercontent.com/greatsong/"
    "modudata/main/data/boundaries/sigungu_kr.geojson"
)

# -----------------------------------------
# 2. 데이터 불러오기
# -----------------------------------------
@st.cache_data
def load_population():
    # 코드 열은 숫자가 아닌 문자로 읽어야 앞의 0이 사라지지 않음
    response = requests.get(POPULATION_URL, timeout=60)
    response.raise_for_status()

    from io import BytesIO

    df = pd.read_csv(
        BytesIO(response.content),
        compression="gzip",
        dtype={"코드": "string"}
    )

    # 코드 앞뒤 공백 제거
    df["코드"] = df["코드"].str.strip()

    # 코드 앞 5자리를 시군구 코드로 사용
    df["시군구코드"] = df["코드"].str[:5]

    # 연도는 숫자로 변환
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")

    return df


@st.cache_data
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=60)
    response.raise_for_status()
    return response.json()


# -----------------------------------------
# 3. 고령화율 계산
# -----------------------------------------
@st.cache_data
def calculate_aging_rate(df):
    # 데이터에서 가장 최신 연도를 자동으로 찾음
    latest_year = int(df["연도"].max())

    latest = df[df["연도"] == latest_year].copy()

    # 전체 인구 열
    total_col = "계_0세"

    # 65세 이상 인구 열 이름을 자동으로 찾음
    # 65세부터 100세 이상까지의 '계_' 열을 더함
    elderly_cols = [
        f"계_{age}세"
        for age in range(65, 100)
    ]
    elderly_cols.append("계_100세 이상")

    # 실제 데이터에 존재하는 열만 사용
    elderly_cols = [
        col for col in elderly_cols
        if col in latest.columns
    ]

    if total_col not in latest.columns:
        raise ValueError("전체 인구 열 '계_0세'를 찾을 수 없습니다.")

    if not elderly_cols:
        raise ValueError("65세 이상 인구 열을 찾을 수 없습니다.")

    # 인구 열을 숫자로 변환
    latest[total_col] = pd.to_numeric(
        latest[total_col], errors="coerce"
    ).fillna(0)

    for col in elderly_cols:
        latest[col] = pd.to_numeric(
            latest[col], errors="coerce"
        ).fillna(0)

    # 읍·면·동별 전체 인구와 65세 이상 인구 계산
    latest["65세이상인구"] = latest[elderly_cols].sum(axis=1)
    latest["전체인구"] = latest[total_col]

    # 시군구 코드별로 읍·면·동 인구를 합산
    sigungu = (
        latest.groupby("시군구코드", as_index=False)
        .agg(
            전체인구=("전체인구", "sum"),
            65세이상인구=("65세이상인구", "sum")
        )
    )

    # 고령화율(%) 계산
    sigungu["고령화율"] = np.where(
        sigungu["전체인구"] > 0,
        sigungu["65세이상인구"] / sigungu["전체인구"] * 100,
        np.nan
    )

    return latest_year, sigungu


# -----------------------------------------
# 4. 지도와 인구 데이터 연결
# -----------------------------------------
@st.cache_data
def prepare_map_data(population_df, geojson):
    latest_year, sigungu = calculate_aging_rate(population_df)

    # GeoJSON 경계 속성에서 시군구 코드 가져오기
    features = geojson["features"]

    boundary_rows = []

    for feature in features:
        properties = feature["properties"]

        boundary_rows.append({
            "코드": str(properties["코드"]).zfill(5),
            "시군구": properties["시군구"],
            "시도": properties["시도"]
        })

    boundary_df = pd.DataFrame(boundary_rows)

    # 이름이 아니라 코드로 연결
    map_df = boundary_df.merge(
        sigungu,
        left_on="코드",
        right_on="시군구코드",
        how="left"
    )

    # 지도에서 사용할 색상 구간
    bins = [-np.inf, 19, 23, 28, 38, np.inf]

    labels = [
        "19% 미만",
        "19% 이상 ~ 23% 미만",
        "23% 이상 ~ 28% 미만",
        "28% 이상 ~ 38% 미만",
        "38% 이상"
    ]

    map_df["고령화 단계"] = pd.cut(
        map_df["고령화율"],
        bins=bins,
        labels=labels,
        right=False
    )

    return latest_year, map_df


# -----------------------------------------
# 5. 데이터 실행
# -----------------------------------------
try:
    with st.spinner("인구 데이터와 지도 경계를 불러오는 중..."):
        population_df = load_population()
        geojson = load_geojson()

        latest_year, map_df = prepare_map_data(
            population_df,
            geojson
        )

except Exception as e:
    st.error(f"데이터를 불러오지 못했습니다: {e}")
    st.stop()


# -----------------------------------------
# 6. 데이터 확인
# -----------------------------------------
st.info(
    f"📅 기준 연도: {latest_year}년 | "
    f"지도 경계 수: {len(map_df)}개 시군구"
)

# 지도에 사용할 색상
color_map = {
    "19% 미만": "#fff7bc",
    "19% 이상 ~ 23% 미만": "#fec44f",
    "23% 이상 ~ 28% 미만": "#fe9929",
    "28% 이상 ~ 38% 미만": "#ec7014",
    "38% 이상": "#993404"
}

# -----------------------------------------
# 7. 단계구분도 그리기
# -----------------------------------------
st.subheader("전국 시군구별 고령화율")

# GeoJSON의 코드 속성과 데이터 코드가 일치하도록 설정
fig = px.choropleth(
    map_df,
    geojson=geojson,
    locations="코드",
    featureidkey="properties.코드",
    color="고령화 단계",
    color_discrete_map=color_map,
    category_orders={
        "고령화 단계": [
            "19% 미만",
            "19% 이상 ~ 23% 미만",
            "23% 이상 ~ 28% 미만",
            "28% 이상 ~ 38% 미만",
            "38% 이상"
        ]
    },
    hover_name="시군구",
    hover_data={
        "시도": True,
        "고령화율": ":.2f",
        "코드": False,
        "고령화 단계": False
    },
    labels={
        "시도": "시도",
        "고령화율": "고령화율(%)",
        "고령화 단계": "고령화 단계"
    }
)

# 배경 지도 타일 없이 경계선만 표시
fig.update_geos(
    fitbounds="locations",
    visible=False,
    showcountries=False,
    showcoastlines=False,
    showland=False,
    showocean=False,
    showlakes=False,
    showrivers=False
)

# 경계선 설정
fig.update_traces(
    marker_line_color="#555555",
    marker_line_width=0.5
)

# 지도 크기와 범례 설정
fig.update_layout(
    height=750,
    margin=dict(l=0, r=0, t=20, b=0),
    legend_title_text="고령화율 구간",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.08,
        xanchor="center",
        x=0.5
    ),
    paper_bgcolor="white",
    plot_bgcolor="white"
)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "displayModeBar": True,
        "scrollZoom": True
    }
)


# -----------------------------------------
# 8. 고령화율 높은 곳 / 낮은 곳 TOP 10
# -----------------------------------------
st.subheader("📊 고령화율 비교")

# 고령화율이 계산된 시군구만 사용
valid_df = map_df.dropna(subset=["고령화율"]).copy()

# 고령화율 높은 곳 10개
top10 = (
    valid_df.sort_values("고령화율", ascending=False)
    .head(10)
    .copy()
)

# 고령화율 낮은 곳 10개
bottom10 = (
    valid_df.sort_values("고령화율", ascending=True)
    .head(10)
    .copy()
)

# 표에 표시할 열과 이름 정리
display_columns = ["시도", "시군구", "고령화율"]

top10_display = top10[display_columns].copy()
bottom10_display = bottom10[display_columns].copy()

top10_display["고령화율"] = (
    top10_display["고령화율"].map(lambda x: f"{x:.2f}%")
)

bottom10_display["고령화율"] = (
    bottom10_display["고령화율"].map(lambda x: f"{x:.2f}%")
)

# 두 표를 나란히 배치
left, right = st.columns(2)

with left:
    st.markdown("### 🔴 고령화율 높은 곳 TOP 10")
    st.dataframe(
        top10_display.reset_index(drop=True),
        use_container_width=True,
        hide_index=True
    )

with right:
    st.markdown("### 🟡 고령화율 낮은 곳 TOP 10")
    st.dataframe(
        bottom10_display.reset_index(drop=True),
        use_container_width=True,
        hide_index=True
    )


# -----------------------------------------
# 9. 데이터 설명
# -----------------------------------------
with st.expander("📌 데이터 및 계산 방법"):
    st.markdown(
        """
        - **자료 출처:** 제공된 인구 CSV 및 시군구 GeoJSON
        - **기준 연도:** 인구 CSV에서 자동으로 찾은 최신 연도
        - **고령화율:** 65세 이상 인구 ÷ 전체 인구 × 100
        - **집계 방법:** 읍·면·동 인구를 시군구 코드 앞 5자리로 합산
        - **지도 연결:** 시군구 이름이 아닌 5자리 코드 사용
        - **색상 구간:** 19%, 23%, 28%, 38% 기준 5단계
        """
    )
