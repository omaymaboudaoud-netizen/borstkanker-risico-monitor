import streamlit as st
import pandas as pd
import json
import folium
import unicodedata
import requests
from streamlit_folium import st_folium

# ---------------------------------------------------------
# 1. Normalisatie
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
# 2. Data inladen (screening + gemeenten)
# ---------------------------------------------------------

@st.cache_data
def load_data():
    df = pd.read_csv("screening.csv", sep=";")
    df.columns = [c.strip() for c in df.columns]

    df = df[df["Screening"].str.contains("Borstkanker", case=False)]

    df["Percentage"] = (
        df["Percentage"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    df["Gemeente"] = df["Gemeente"].astype(str).str.strip()
    df["Gemeente_norm"] = df["Gemeente"].apply(normalize)

    naam_mapping = {
        "s gravenhage": "'s gravenhage",
        "s hertogenbosch": "'s hertogenbosch",
        "noardeast frysla¢n": "noardeast fryslan",
        "saodwest frysla¢n": "sudwest fryslan",
    }

    df["Gemeente_norm"] = df["Gemeente_norm"].replace(naam_mapping)

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
        return json.load(f)


# ---------------------------------------------------------
# 3. Live mammobussen / onderzoekscentra inladen
# ---------------------------------------------------------

@st.cache_data
def load_mammobussen():
    url = "https://www.bevolkingsonderzoeknederland.nl/umbraco/Bevolkingsonderzoek/MapApi/GetborstkankerLocations?1780150115"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    return pd.DataFrame(data)


df = load_data()
geo = load_geo()
bussen = load_mammobussen()


# ---------------------------------------------------------
# 4. Naamveld detectie in GeoJSON
# ---------------------------------------------------------

mogelijke_naamvelden = ["statnaam", "naam", "GM_NAAM", "NAAM", "label", "LABEL"]
properties = geo["features"][0]["properties"]

naamveld = next((v for v in mogelijke_naamvelden if v in properties), None)
if naamveld is None:
    st.error("Geen gemeentenaam-veld gevonden in GeoJSON.")
    st.stop()


# ---------------------------------------------------------
# 5. Normalisatie toevoegen aan GeoJSON
# ---------------------------------------------------------

for f in geo["features"]:
    naam_norm = normalize(f["properties"][naamveld])
    f["properties"]["naam_norm"] = naam_norm


# ---------------------------------------------------------
# 6. Lookup-tabel uit screening-data
# ---------------------------------------------------------

lookup = (
    df
    .drop_duplicates(subset="Gemeente_norm")
    .set_index("Gemeente_norm")[["Percentage", "Risico", "Gemeente"]]
    .to_dict(orient="index")
)


# ---------------------------------------------------------
# 7. Risico + percentage toevoegen aan GeoJSON
# ---------------------------------------------------------

for f in geo["features"]:
    naam_norm = f["properties"]["naam_norm"]
    if naam_norm in lookup:
        f["properties"]["Risico"] = lookup[naam_norm]["Risico"]
        f["properties"]["Percentage"] = lookup[naam_norm]["Percentage"]
    else:
        f["properties"]["Risico"] = None
        f["properties"]["Percentage"] = None


# ---------------------------------------------------------
# 8. Centroid-functie (zonder shapely)
# ---------------------------------------------------------

def polygon_centroid(coords):
    """Bereken centroid van Polygon of MultiPolygon."""
    # MultiPolygon: [[[[]]]], Polygon: [[[]]]
    if isinstance(coords[0][0][0], list):
        coords = coords[0]

    xs = [p[0] for p in coords[0]]
    ys = [p[1] for p in coords[0]]
    return sum(ys) / len(ys), sum(xs) / len(xs)


# ---------------------------------------------------------
# 9. Streamlit UI + datumfilter
# ---------------------------------------------------------

st.title("📊 Borstkanker-risico & screeningslocaties in Nederland")

st.subheader("📅 Filter mammobussen op datum")

datum_filter = st.radio(
    "Toon mammobussen voor:",
    [
        "Alle locaties",
        "Vandaag actief",
        "Komende 7 dagen",
        "Komende 30 dagen"
    ],
    horizontal=True
)

vandaag = pd.Timestamp.today().normalize()

def filter_bussen(df_bussen, keuze):
    df_b = df_bussen.copy()
    df_b["dateDate"] = pd.to_datetime(df_b["dateDate"], errors="coerce")

    if keuze == "Vandaag actief":
        return df_b[df_b["dateDate"] == vandaag]

    elif keuze == "Komende 7 dagen":
        return df_b[(df_b["dateDate"] >= vandaag) &
                    (df_b["dateDate"] <= vandaag + pd.Timedelta(days=7))]

    elif keuze == "Komende 30 dagen":
        return df_b[(df_b["dateDate"] >= vandaag) &
                    (df_b["dateDate"] <= vandaag + pd.Timedelta(days=30))]

    else:
        return df_b

bussen_filtered = filter_bussen(bussen, datum_filter)

risico_filter = st.sidebar.selectbox("Filter op risico:", ["Laag", "Midden", "Hoog"])
df_filtered = df[df["Risico"] == risico_filter]

alle_gemeenten = sorted([f["properties"][naamveld] for f in geo["features"]])
gekozen_gemeente = st.sidebar.selectbox("Zoom naar gemeente:", ["(geen)"] + alle_gemeenten)


# ---------------------------------------------------------
# 10. Kaart center & zoom
# ---------------------------------------------------------

center = [52.1, 5.3]
zoom = 7

if gekozen_gemeente != "(geen)":
    for f in geo["features"]:
        if f["properties"][naamveld] == gekozen_gemeente:
            cy, cx = polygon_centroid(f["geometry"]["coordinates"])
            center = [cy, cx]
            zoom = 10
            break

m = folium.Map(location=center, zoom_start=zoom, tiles="cartodbpositron")


# ---------------------------------------------------------
# 11. Kleurfunctie + stijl
# ---------------------------------------------------------

def get_color(risico):
    if risico == "Hoog":
        return "red"
    elif risico == "Midden":
        return "orange"
    elif risico == "Laag":
        return "green"
    else:
        return "lightgrey"


def style_function(feature):
    risico = feature["properties"].get("Risico")
    return {
        "fillColor": get_color(risico),
        "color": "black",
        "weight": 0.5,
        "fillOpacity": 0.8,
    }


tooltip = folium.GeoJsonTooltip(
    fields=[naamveld, "Risico", "Percentage"],
    aliases=["Gemeente:", "Risico:", "Opkomst (%):"],
    localize=True
)

folium.GeoJson(
    geo,
    name="Gemeenten",
    style_function=style_function,
    tooltip=tooltip,
    overlay=True,
    control=True,
    show=True
).add_to(m)


# ---------------------------------------------------------
# 12. Mammobussen / centra toevoegen (gefilterd)
# ---------------------------------------------------------

for _, row in bussen_filtered.iterrows():
    name = row.get("name", "")
    intro = row.get("intro", "")
    full_address = row.get("fullAddress", "")
    date = row.get("date", "")
    url_path = row.get("url", "")

    popup_html = f"""
    <b>{name}</b><br>
    {intro}<br><br>
    <b>Adres:</b> {full_address}<br>
    <b>Datum:</b> {date}<br><br>
    <a href='https://www.bevolkingsonderzoeknederland.nl{url_path}' target='_blank'>Meer info</a>
    """

    folium.Marker(
        location=[row["lat"], row["lng"]],
        popup=popup_html,
        tooltip=name,
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(m)


folium.LayerControl().add_to(m)


# ---------------------------------------------------------
# 13. Legenda
# ---------------------------------------------------------

legend_html = """
<div style="
position: fixed; 
bottom: 50px; left: 50px; width: 190px; height: 180px; 
background-color: white; z-index:9999; 
border:2px solid grey; border-radius:8px; padding:10px;">
<b>Legenda</b><br>
<i style="background:red; width:20px; height:20px; float:left; margin-right:8px;"></i> Hoog risico<br>
<i style="background:orange; width:20px; height:20px; float:left; margin-right:8px;"></i> Midden risico<br>
<i style="background:green; width:20px; height:20px; float:left; margin-right:8px;"></i> Laag risico<br>
<i style="background:lightgrey; width:20px; height:20px; float:left; margin-right:8px;"></i> Geen data<br>
<i style="background:blue; width:20px; height:20px; float:left; margin-right:8px;"></i> Mammobus / centrum<br>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))


# ---------------------------------------------------------
# 14. Weergave kaart + tabel
# ---------------------------------------------------------

st_folium(m, width=900, height=600)

st.subheader(f"Gemeenten met risico: {risico_filter}")
st.dataframe(
    df_filtered[["Gemeente", "Percentage", "Risico"]]
    .sort_values("Percentage")
    .reset_index(drop=True)
)


# ---------------------------------------------------------
# 15. Analyse: gemeenten die NU / BINNEN 30 DAGEN aandacht nodig hebben
# ---------------------------------------------------------

st.subheader("🔎 Gemeenten die NU of BINNENKORT aandacht nodig hebben (risico: Hoog + Midden)")

df_risico = df[df["Risico"].isin(["Hoog", "Midden"])].copy()
df_risico["Gemeente_norm"] = df_risico["Gemeente"].apply(normalize)

bussen["city_norm"] = bussen["city"].apply(normalize)
bussen["dateDate"] = pd.to_datetime(bussen["dateDate"], errors="coerce")

# NU aandacht: bus staat er vandaag
nu_actief = bussen[bussen["dateDate"] == vandaag]
gemeenten_nu = df_risico[df_risico["Gemeente_norm"].isin(nu_actief["city_norm"])]

# Binnen 30 dagen aandacht
binnenkort = bussen[
    (bussen["dateDate"] > vandaag) &
    (bussen["dateDate"] <= vandaag + pd.Timedelta(days=30))
]
gemeenten_binnenkort = df_risico[df_risico["Gemeente_norm"].isin(binnenkort["city_norm"])]

st.markdown("### 🟢 Gemeenten die **NU** aandacht nodig hebben")
if len(gemeenten_nu) == 0:
    st.write("Geen gemeenten met actieve mammobus vandaag (voor risico Hoog + Midden).")
else:
    st.dataframe(
        gemeenten_nu[["Gemeente", "Percentage", "Risico"]]
        .sort_values("Percentage")
        .reset_index(drop=True)
    )

st.markdown("### 🟡 Gemeenten die **binnen 30 dagen** aandacht nodig hebben")
if len(gemeenten_binnenkort) == 0:
    st.write("Geen gemeenten met geplande mammobus binnen 30 dagen (voor risico Hoog + Midden).")
else:
    st.dataframe(
        gemeenten_binnenkort[["Gemeente", "Percentage", "Risico"]]
        .sort_values("Percentage")
        .reset_index(drop=True)
    )
