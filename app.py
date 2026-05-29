import streamlit as st
import pandas as pd
import json
import folium
import unicodedata
from streamlit_folium import st_folium

# ---------------------------------------------------------
# 1. HULPFUNCTIE VOOR NAAM-NORMALISATIE
# ---------------------------------------------------------

def normalize(s):
    if not isinstance(s, str):
        s = str(s)

    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("-", " ").replace("’", "'").replace("`", "'")
    s = " ".join(s.split())
    return s


# ---------------------------------------------------------
# 2. DATA INLADEN
# ---------------------------------------------------------

@st.cache_data
def load_data():
    df = pd.read_csv("screening.csv", sep=";")
    df.columns = [c.strip() for c in df.columns]

    df["Percentage"] = (
        df["Percentage"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    df["Gemeente"] = df["Gemeente"].astype(str).str.strip()
    df["Gemeente_norm"] = df["Gemeente"].apply(normalize)

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
# 3. AUTOMATISCHE DETECTIE VAN GEMEENTENAAM-VELD
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
# 4. NORMALISATIE TOEVOEGEN AAN GEOJSON
# ---------------------------------------------------------

for f in gemeenten_geo["features"]:
    naam = f["properties"].get(naamveld, "")
    f["properties"]["naam_norm"] = normalize(naam)

# ---------------------------------------------------------
# 5. STREAMLIT UI
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
# 6. KAART MAKEN
# ---------------------------------------------------------

m = folium.Map(location=[52.1, 5.3], zoom_start=7, tiles="cartodbpositron")

def style_function(feature):
    naam_norm = feature["properties"].get("naam_norm")

    if naam_norm is None:
        return {"fillColor": "lightgray", "color": "black", "weight": 0.3, "fillOpacity": 0.3}

    row = df_filtered.loc[df_filtered["Gemeente_norm"] == naam_norm]

    if row.empty:
        return {"fillColor": "lightgray", "color": "black", "weight": 0.3, "fillOpacity": 0.3}

    perc = float(row["Percentage"].iloc[0])

    if perc < 60:
        kleur = "red"
    elif perc < 70:
        kleur = "orange"
    else:
        kleur = "green"

    return {"fillColor": kleur, "color": "black", "weight": 0.5, "fillOpacity": 0.7}


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
# 7. WEERGAVE
# ---------------------------------------------------------

st.subheader("🗺️ Kaart")
st_folium(m, width=900, height=600)

st.subheader("📋 Gegevens per gemeente")
st.dataframe(
    df_filtered[["Gemeente", "Percentage", "Risico"]]
    .sort_values("Percentage", ascending=True)
    .reset_index(drop=True)
)
