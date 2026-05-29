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

import requests
import json

url = "https://service.pdok.nl/kadaster/bestuurlijkegebieden/2022/wfs/v1_0?request=GetFeature&service=WFS&version=2.0.0&typeName=bestuurlijkegebieden:gemeente_gegeneraliseerd&outputFormat=application/json"

response = requests.get(url)

# Controleer of de server JSON teruggeeft
try:
    gemeenten_geo = response.json()
except ValueError:
    st.error("Kon GeoJSON niet laden. Server gaf geen geldig JSON terug.")
    st.stop()

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
