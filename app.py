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
    df = pd.read_csv("screening.csv", sep=";")
    df.columns = [c.strip() for c in df.columns]

    # Percentage naar float
    df["Percentage"] = (
        df["Percentage"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    # Gemeente opschonen (strip-fix)
    df["Gemeente"] = df["Gemeente"].astype(str).str.strip()

    # Risico-classificatie
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
    with open("gemeenten_geo.json", "r", encoding="utf-8") as f:
        geo = json.load(f)
    return geo


df = load_data()
gemeenten_geo = load_geo()

# ---------------------------------------------------------
# 2. AUTOMATISCHE DETECTIE VAN GEMEENTENAAM-VELD
# ---------------------------------------------------------

mogelijke_naamvelden = [
    "GM_NAAM", "naam", "NAAM", "Name", "Gemeentenaam",
    "gemeentenaam", "GEMEENTENAAM", "label", "LABEL"
]

properties = gemeenten_geo["features"][0]["properties"]

naamveld = None
for veld in mogelijke_naamvelden:
    if veld in properties:
        naamveld = veld
        break

if naamveld is None:
    st.error("Kon geen gemeentenaam-veld vinden in GeoJSON properties.")
    st.write("Beschikbare velden:", list(properties.keys()))
    st.stop()

st.sidebar.success(f"Gemeentenaam-veld gedetecteerd: **{naamveld}**")

# ---------------------------------------------------------
# 3. STREAMLIT LAYOUT
# ---------------------------------------------------------

st.title("📊 Borstkanker Risico Monitor")
st.write("Interactieve kaart van Nederland met screeningspercentages per gemeente.")

st.sidebar.header("Filters")
risico_filter = st.sidebar.selectbox(
    "Selecteer risico:",
    ["Laag", "Midden", "Hoog"]
)

df_filtered = df[df["Risico"] == risico_filter]

# ---------------------------------------------------------
# 4. KAART MAKEN
# ---------------------------------------------------------

m = folium.Map(location=[52.1, 5.3], zoom_start=7, tiles="cartodbpositron")

def style_function(feature):
    naam = feature["properties"].get(naamveld)

    if naam is None:
        return {
            "fillColor": "lightgray",
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.3,
        }

    row = df_filtered.loc[df_filtered["Gemeente"] == naam]

    if row.empty:
        return {
            "fillColor": "lightgray",
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.3,
        }

    perc = float(row["Percentage"].iloc[0])

    if perc < 60:
        kleur = "red"
    elif perc < 70:
        kleur = "orange"
    else:
        kleur = "green"

    return {
        "fillColor": kleur,
        "color": "black",
        "weight": 0.5,
        "fillOpacity": 0.7,
    }


folium.GeoJson(
    gemeenten_geo,
    name="Gemeenten",
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(
        fields=[naamveld],
        aliases=["Gemeente:"],
        localize=True
    )
).add_to(m)

# ---------------------------------------------------------
# 5. WEERGAVE
# ---------------------------------------------------------

st.subheader("🗺️ Kaart")
st_folium(m, width=900, height=600)

st.subheader("📋 Gegevens per gemeente")
st.dataframe(
    df_filtered[["Gemeente", "Percentage", "Risico"]]
    .sort_values("Percentage", ascending=True)
    .reset_index(drop=True)
)
