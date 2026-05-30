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

    # ❗ Alleen borstkanker (anders dubbele gemeenten)
    df = df[df["Screening"].str.contains("Borstkanker", case=False)]

    df["Percentage"] = (
        df["Percentage"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    df["Gemeente"] = df["Gemeente"].astype(str).str.strip()
    df["Gemeente_norm"] = df["Gemeente"].apply(normalize)

    # ❗ Mapping voor fout gecodeerde of afwijkende namen
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

mogelijke_naamvelden = ["naam", "GM_NAAM", "NAAM", "label", "LABEL"]
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
    naam_norm = naam_norm.replace("’", "'")  # apostrof fix
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
# 6. DEBUG (kan later uit)
# ---------------------------------------------------------

geo_norms = sorted({f["properties"]["naam_norm"] for f in geo["features"]})
csv_norms = sorted(set(df["Gemeente_norm"]))

st.sidebar.subheader("🔍 Matching analyse")
st.sidebar.write("Aantal gemeenten in GeoJSON:", len(geo_norms))
st.sidebar.write("Aantal gemeenten in CSV:", len(csv_norms))

st.sidebar.write("Niet in CSV (maar wel in GeoJSON):")
st.sidebar.write([g for g in geo_norms if g not in csv_norms][:30])

st.sidebar.write("Niet in GeoJSON (maar wel in CSV):")
st.sidebar.write([c for c in csv_norms if c not in geo_norms][:30])


# ---------------------------------------------------------
# 7. STREAMLIT UI
# ---------------------------------------------------------

st.title("📊 Borstkanker Risico Monitor")

risico_filter = st.sidebar.selectbox("Selecteer risico:", ["Laag", "Midden", "Hoog"])
df_filtered = df[df["Risico"] == risico_filter]


# ---------------------------------------------------------
# 8. KAART
# ---------------------------------------------------------

m = folium.Map(location=[52.1, 5.3], zoom_start=7, tiles="cartodbpositron")

def style_function(feature):
    return {
        "fillColor": "red",
        "color": "black",
        "weight": 0.5,
        "fillOpacity": 0.9,
    }


# ⭐ DE FIX: overlay=True + control=True + show=True
folium.GeoJson(
    geo,
    name="Gemeenten",
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(
        fields=[naamveld],
        aliases=["Gemeente:"],
        localize=True
    ),
    overlay=True,
    control=True,
    show=True
).add_to(m)

# ⭐ LayerControl zodat je kunt zien of de laag aan staat
folium.LayerControl().add_to(m)


# ---------------------------------------------------------
# 9. LEGENDA
# ---------------------------------------------------------

legend_html = """
<div style="
position: fixed; 
bottom: 50px; left: 50px; width: 160px; height: 130px; 
background-color: white; z-index:9999; 
border:2px solid grey; border-radius:8px; padding:10px;">
<b>Legenda</b><br>
<i style="background:red; width:20px; height:20px; float:left; margin-right:8px;"></i> Hoog risico<br>
<i style="background:orange; width:20px; height:20px; float:left; margin-right:8px;"></i> Midden risico<br>
<i style="background:green; width:20px; height:20px; float:left; margin-right:8px;"></i> Laag risico<br>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))


# ---------------------------------------------------------
# 10. WEERGAVE
# ---------------------------------------------------------

st_folium(m, width=900, height=600)

st.dataframe(
    df_filtered[["Gemeente", "Percentage", "Risico"]]
    .sort_values("Percentage")
    .reset_index(drop=True)
)
