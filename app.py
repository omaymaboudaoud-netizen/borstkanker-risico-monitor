import streamlit as st
import pandas as pd
import geopandas as gpd
import datetime as dt
import folium
from streamlit_folium import st_folium
import cbsodata

# ---------- 1. Datafuncties ----------

@st.cache_data
def load_screening(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";")
    df["Percentage"] = (
        df["Percentage"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )
    df_borst = df[df["Screening"].str.contains("Borstkanker", case=False)].copy()

    df_borst.rename(columns={
        "id": "gemeente_id",
        "Gemeente": "gemeente_naam"
    }, inplace=True)

    def classify_risk(p):
        if p < 60:
            return "Hoog risico"
        elif p < 70:
            return "Midden risico"
        else:
            return "Laag risico"

    df_borst["Risico"] = df_borst["Percentage"].apply(classify_risk)
    return df_borst

@st.cache_data
def load_ses() -> pd.DataFrame:
    ses = cbsodata.get_data("84799NED")
    ses_df = pd.DataFrame(ses)
    ses_df = ses_df[["Gemeentecode_1", "SESScore_1"]]
    ses_df.columns = ["gemeente_id", "SES_score"]
    ses_df["gemeente_id"] = ses_df["gemeente_id"].astype(int)

    def classify_ses(score):
        if score < -0.5:
            return "Laag SES"
        elif score <= 0.5:
            return "Midden SES"
        else:
            return "Hoog SES"

    ses_df["SES_klasse"] = ses_df["SES_score"].apply(classify_ses)
    return ses_df

@st.cache_data
def load_geo(path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if "GM_CODE" in gdf.columns:
        gdf["gemeente_id"] = gdf["GM_CODE"].str.replace("GM", "").astype(int)
    elif "statcode" in gdf.columns:
        gdf["gemeente_id"] = gdf["statcode"].str.replace("GM", "").astype(int)
    elif "id" in gdf.columns:
        gdf["gemeente_id"] = gdf["id"].astype(int)
    else:
        raise ValueError("Geen geschikte kolom gevonden voor gemeentecode in GeoJSON.")
    return gdf

# ---------- 2. Data laden ----------

screening = load_screening("screening.csv")
ses = load_ses()
geo = load_geo("gemeenten_geo.json")

df = screening.merge(ses, on="gemeente_id", how="left")
gdf = geo.merge(df, on="gemeente_id", how="left")

# ---------- 3. Streamlit UI ----------

st.set_page_config(page_title="Borstkanker Risico Monitor NL", layout="wide")
st.title("Borstkanker Risico Monitor NL")

st.sidebar.header("Filters")

risico_filter = st.sidebar.multiselect(
    "Risiconiveau",
    options=["Hoog risico", "Midden risico", "Laag risico"],
    default=["Hoog risico", "Midden risico", "Laag risico"]
)

ses_filter = st.sidebar.multiselect(
    "SES-klasse",
    options=["Laag SES", "Midden SES", "Hoog SES"],
    default=["Laag SES", "Midden SES", "Hoog SES"]
)

mask = gdf["Risico"].isin(risico_filter) & gdf["SES_klasse"].isin(ses_filter)
gdf_filtered = gdf[mask].copy()

st.subheader("Kaart van Nederland – risico per gemeente")

m = folium.Map(location=[52.1, 5.3], zoom_start=7)

def kleur(r):
    if r == "Hoog risico":
        return "red"
    elif r == "Midden risico":
        return "orange"
    else:
        return "green"

folium.GeoJson(
    gdf_filtered,
    style_function=lambda feature: {
        "fillColor": kleur(feature["properties"]["Risico"]),
        "color": "black",
        "weight": 0.5,
        "fillOpacity": 0.6,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=["gemeente_naam", "Percentage", "SES_klasse", "Risico"],
        aliases=["Gemeente", "Opkomst (%)", "SES", "Risico"],
        localize=True
    )
).add_to(m)

st_folium(m, width=1100, height=650)
