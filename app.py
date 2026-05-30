import streamlit as st
import pandas as pd
import json
import folium
import unicodedata
from streamlit_folium import st_folium

# ---------------------------------------------------------
# 1. NORMALISATIE
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


df = load_data()
geo = load_geo()

# ---------------------------------------------------------
# 3. NAAMVELD DETECTIE
# ---------------------------------------------------------

mogelijke_naamvelden = ["statnaam", "naam", "GM_NAAM", "NAAM", "label", "LABEL"]
properties = geo["features"][0]["properties"]

naamveld = next((v for v in mogelijke_naamvelden if v in properties), None)
if naamveld is None:
    st.error("Geen gemeentenaam-veld gevonden.")
    st.stop()

# ---------------------------------------------------------
# 4. NORMALISATIE TOEVOEGEN AAN GEOJSON
# ---------------------------------------------------------

for f in geo["features"]:
    naam_norm = normalize(f["properties"][naamveld])
    f["properties"]["naam_norm"] = naam_norm

# ---------------------------------------------------------
# 5. LOOKUP-TABEL
# ---------------------------------------------------------

lookup = (
    df
    .drop_duplicates(subset="Gemeente_norm")
    .set_index("Gemeente_norm")[["Percentage", "Risico", "Gemeente"]]
    .to_dict(orient="index")
)

# ---------------------------------------------------------
# 6. RISICO TOEVOEGEN AAN GEOJSON
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
# 7. CENTROID FUNCTIE (zonder shapely)
# ---------------------------------------------------------

def polygon_centroid(coords):
    """Bereken centroid van Polygon of MultiPolygon."""
    if isinstance(coords[0][0][0], list):  
        # MultiPolygon → neem eerste polygon
        coords = coords[0]

    xs = [p[0] for p in coords[0]]
    ys = [p[1] for p in coords[0]]
    return sum(ys)/len(ys), sum(xs)/len(xs)


# ---------------------------------------------------------
# 8. STREAMLIT UI
# ---------------------------------------------------------

st.title("📊 Borstkanker Risico Monitor")

risico_filter = st.sidebar.selectbox("Selecteer risico:", ["Laag", "Midden", "Hoog"])
df_filtered = df[df["Risico"] == risico_filter]

alle_gemeenten = sorted([f["properties"][naamveld] for f in geo["features"]])
gekozen_gemeente = st.sidebar.selectbox("Zoom naar gemeente:", ["(geen)"] + alle_gemeenten)

# ---------------------------------------------------------
# 9. KAART CENTER & ZOOM
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
# 10. KLEURFUNCTIE
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

folium.LayerControl().add_to(m)

# ---------------------------------------------------------
# 11. LEGENDA
# ---------------------------------------------------------

legend_html = """
<div style="
position: fixed; 
bottom: 50px; left: 50px; width: 160px; height: 150px; 
background-color: white; z-index:9999; 
border:2px solid grey; border-radius:8px; padding:10px;">
<b>Legenda</b><br>
<i style="background:red; width:20px; height:20px; float:left; margin-right:8px;"></i> Hoog risico<br>
<i style="background:orange; width:20px; height:20px; float:left; margin-right:8px;"></i> Midden risico<br>
<i style="background:green; width:20px; height:20px; float:left; margin-right:8px;"></i> Laag risico<br>
<i style="background:lightgrey; width:20px; height:20px; float:left; margin-right:8px;"></i> Geen data<br>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

# ---------------------------------------------------------
# 12. WEERGAVE
# ---------------------------------------------------------

st_folium(m, width=900, height=600)

st.dataframe(
    df_filtered[["Gemeente", "Percentage", "Risico"]]
    .sort_values("Percentage")
    .reset_index(drop=True)
)
