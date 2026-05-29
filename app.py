import streamlit as st
import pandas as pd
import json
import folium
from streamlit_folium import st_folium

# ---------------------------------------------------------
# 1. DATA INLADEN
# ---------------------------------------------------------

# CSV met screening percentages
df = pd.read_csv("screening.csv", sep=";")

# GeoJSON met gemeentegrenzen
import codecs

with codecs.open("gemeenten_geo.json", "r", encoding="utf-8", errors="ignore") as f:
    gemeenten_geo = json.load(f)

# ---------------------------------------------------------
# 2. STREAMLIT LAYOUT
# ---------------------------------------------------------

st.title("📊 Borstkanker Risico Monitor")
st.write("Interactieve kaart van Nederland met screeningspercentages per gemeente.")

# Filters
st.sidebar.header("Filters")
risico_filter = st.sidebar.selectbox("Selecteer risico:", ["Laag", "Midden", "Hoog"])
ses_filter = st.sidebar.selectbox("Selecteer SES-klasse:", ["Laag", "Midden", "Hoog"])

# Filter toepassen
df_filtered = df[
    (df["Risico"] == risico_filter) &
    (df["SES"] == ses_filter)
]

# ---------------------------------------------------------
# 3. KAART MAKEN MET FOLIUM
# ---------------------------------------------------------

# Startpositie Nederland
m = folium.Map(location=[52.1, 5.3], zoom_start=7, tiles="cartodbpositron")

# Kleurfunctie op basis van percentage
def kleur(percent):
    if percent < 50:
        return "red"
    elif percent < 70:
        return "orange"
    else:
        return "green"

# GeoJSON toevoegen
folium.GeoJson(
    gemeenten_geo,
    name="Gemeenten",
    style_function=lambda feature: {
        "fillColor": kleur(
            df_filtered.loc[
                df_filtered["Gemeente"] == feature["properties"]["name"],
                "Percentage"
            ].values[0]
        ) if feature["properties"]["name"] in df_filtered["Gemeente"].values else "gray",
        "color": "black",
        "weight": 0.5,
        "fillOpacity": 0.6,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=["name"],
        aliases=["Gemeente:"],
        localize=True
    )
).add_to(m)

# ---------------------------------------------------------
# 4. KAART WEERGEVEN
# ---------------------------------------------------------

st_folium(m, width=800, height=600)
