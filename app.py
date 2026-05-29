import streamlit as st
import pandas as pd
import json
import folium
from streamlit_folium import st_folium

# ---------------------------------------------------------
# 1. DATA INLADEN
# ---------------------------------------------------------

@st.cache_data
def load_data():
    # CSV inladen (meestal ; gescheiden vanuit Excel/CBS)
    df = pd.read_csv("screening.csv", sep=";")

    # Kolomnamen normaliseren
    df.columns = [c.strip() for c in df.columns]

    # Percentage naar float
    df["Percentage"] = (
        df["Percentage"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    # Gemeentenaam als string
    df["Gemeente"] = df["Gemeente"].astype(str).str.strip()

    # Risico-classificatie op basis van percentage
    def classify_risk(p):
        if p < 60:
            return "Hoog"
        elif p < 70:
            return "Midden"
        else:
            return "Laag"

    df["Risico"] = df["Percentage"].apply(classify_risk)

    return df


@st.cache_data
def load_geo():
    # Lokaal, vereenvoudigd GeoJSON-bestand
    with open("gemeenten_geo.json", "r", encoding="utf-8") as f:
        gemeenten_geo = json.load(f)
    return gemeenten_geo


df = load_data()
gemeenten_geo = load_geo()

# ---------------------------------------------------------
# 2. STREAMLIT LAYOUT
# ---------------------------------------------------------

st.title("📊 Borstkanker Risico Monitor")
st.write("Interactieve kaart van Nederland met screeningspercentages per gemeente.")

st.sidebar.header("Filters")

risico_filter = st.sidebar.selectbox(
    "Selecteer risico (op basis van screeningspercentage):",
    ["Laag", "Midden", "Hoog"]
)

df_filtered = df[df["Risico"] == risico_filter]

st.sidebar.write(f"Aantal gemeenten in selectie: **{len(df_filtered)}**")

# ---------------------------------------------------------
# 3. KAART MAKEN MET FOLIUM
# ---------------------------------------------------------

# Startpositie Nederland
m = folium.Map(location=[52.1, 5.3], zoom_start=7, tiles="cartodbpositron")

def kleur(percent):
    if percent < 60:
        return "red"
    elif percent < 70:
        return "orange"
    else:
        return "green"

def get_percentage(gemeente_naam: str):
    row = df_filtered.loc[df_filtered["Gemeente"] == gemeente_naam]
    if row.empty:
        return None
    return float(row["Percentage"].iloc[0])

def style_function(feature):
    naam = feature["properties"].get("GM_NAAM") or feature["properties"].get("name")
    if naam is None:
        return {
            "fillColor": "lightgray",
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.3,
        }

    perc = get_percentage(naam)
    if perc is None:
        return {
            "fillColor": "lightgray",
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.3,
        }

    return {
        "fillColor": kleur(perc),
        "color": "black",
        "weight": 0.5,
        "fillOpacity": 0.7,
    }

folium.GeoJson(
    gemeenten_geo,
    name="Gemeenten",
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(
        fields=["GM_NAAM"],
        aliases=["Gemeente:"],
        localize=True
    )
).add_to(m)

# ---------------------------------------------------------
# 4. KAART EN TABEL WEERGEVEN
# ---------------------------------------------------------

st.subheader("🗺️ Kaart")
st_folium(m, width=900, height=600)

st.subheader("📋 Gegevens per gemeente")
st.dataframe(
    df_filtered[["Gemeente", "Percentage", "Risico"]]
    .sort_values("Percentage", ascending=True)
    .reset_index(drop=True)
)
