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

# ❗ Alleen borstkanker selecteren (anders dubbele gemeenten)
df = df[df["Screening"].str.contains("Borstkanker", case=False)]

    # Percentage naar float
    df["Percentage"] = (
        df["Percentage"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    # Gemeentenaam normaliseren
    df["Gemeente"] = df["Gemeente"].astype(str).str.strip()
    df["Gemeente_norm"] = df["Gemeente"].apply(normalize)

    # Risicoklasse
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
# 4. NORMALISATIE + MAPPING TUSSEN CSV EN GEOJSON
# ---------------------------------------------------------

# Voeg genormaliseerde naam toe aan GeoJSON
for f in gemeenten_geo["features"]:
    naam = f["properties"].get(naamveld, "")
    f["properties"]["naam_norm"] = normalize(naam)

# Maak een mapping van gemeente_norm -> (Percentage, Risico, originele naam)
# (we nemen aan dat elke gemeente maar één keer voorkomt in de CSV)
csv_map = (
    df
    .set_index("Gemeente_norm")[["Percentage", "Risico", "Gemeente"]]
    .to_dict(orient="index")
)

# Voor debug: welke CSV-gemeenten matchen niet met GeoJSON?
geo_norms = {f["properties"]["naam_norm"] for f in gemeenten_geo["features"]}
csv_norms = set(csv_map.keys())
niet_in_geo = sorted(csv_norms - geo_norms)
niet_in_csv = sorted(geo_norms - csv_norms)

with st.sidebar.expander("🔍 Matching-diagnostiek", expanded=False):
    st.write("Aantal gemeenten in CSV:", len(csv_norms))
    st.write("Aantal gemeenten in GeoJSON:", len(geo_norms))
    st.write("CSV-gemeenten die niet in GeoJSON voorkomen (genormaliseerd):")
    st.write(niet_in_geo[:50])  # eerste 50 tonen
    st.write("GeoJSON-gemeenten die geen match in CSV hebben (genormaliseerd):")
    st.write(niet_in_csv[:50])

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

# Voor de kaart gebruiken we de volledige csv_map,
# maar de tabel onderaan filteren we op risico.

# ---------------------------------------------------------
# 6. KAART MAKEN
# ---------------------------------------------------------

m = folium.Map(location=[52.1, 5.3], zoom_start=7, tiles="cartodbpositron")

def style_function(feature):
    naam_norm = feature["properties"].get("naam_norm")

    if not naam_norm:
        return {
            "fillColor": "lightgray",
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.3,
        }

    info = csv_map.get(naam_norm)
    if info is None:
        # Geen data voor deze gemeente
        return {
            "fillColor": "lightgray",
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.3,
        }

    perc = float(info["Percentage"])

    if perc < 60:
        kleur = "red"
    elif perc < 70:
        kleur = "orange"
    else:
        kleur = "green"

    # Alleen inkleuren als deze gemeente in de gekozen risicoklasse valt
    if info["Risico"] != risico_filter:
        # lichtgrijs tonen als hij niet in de huidige filter valt
        return {
            "fillColor": "lightgray",
            "color": "black",
            "weight": 0.3,
            "fillOpacity": 0.2,
        }

    return {
        "fillColor": kleur,
        "color": "black",
        "weight": 0.5,
        "fillOpacity": 0.7,
    }


def tooltip_function(feature):
    naam = feature["properties"].get(naamveld, "Onbekend")
    naam_norm = feature["properties"].get("naam_norm")
    info = csv_map.get(naam_norm)

    if info is None:
        return f"{naam} – geen data"

    return f"{naam} – {info['Percentage']:.1f}% ({info['Risico']})"


folium.GeoJson(
    gemeenten_geo,
    name="Gemeenten",
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(
        fields=[],
        aliases=[],
        labels=False,
        sticky=True,
        toLocaleString=False,
        localize=False,
        style=(
            "background-color: white; "
            "border: 1px solid black; "
            "border-radius: 3px; "
            "padding: 3px;"
        ),
        # custom tooltip via lambda
        # (folium zelf ondersteunt geen directe lambda, dus we gebruiken 'fields' leeg
        #  en zetten de tekst via 'tooltip_function' in 'GeoJson' zelf)
    ),
    highlight_function=lambda x: {"weight": 2, "color": "black"},
).add_to(m)

# Workaround om custom tooltip-tekst te zetten:
for feature in gemeenten_geo["features"]:
    gj = folium.GeoJson(
        feature,
        style_function=style_function,
        tooltip=tooltip_function(feature),
    )
    gj.add_to(m)

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
