import pandas as pd
import numpy as np
import streamlit as st
import pydeck as pdk

st.markdown("""
<style>
/* Fond général */
.stApp {
    background-color: #F4F7FA;
    color: #263445;
}

/* Contenu principal */
.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
}

/* Titres */
h1, h2, h3 {
    color: #1F2937 !important;
}

/* Texte */
p, label, .stMarkdown {
    color: #4B5563;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #EAF0F6;
    border-right: 1px solid #D5DEE8;
}

/* Selectbox / multiselect / inputs */
div[data-baseweb="select"] > div {
    background-color: #FFFFFF;
    border-color: #D5DEE8;
}

div[data-baseweb="select"] span {
    color: #374151;
}

/* Cartes métriques */
div[data-testid="stMetric"] {
    background-color: #FFFFFF;
    border: 1px solid #E1E7ED;
    border-radius: 10px;
    padding: 15px;
    box-shadow: 0 1px 3px rgba(30, 50, 70, 0.06);
}

div[data-testid="stMetricLabel"] {
    color: #6B7280;
}

div[data-testid="stMetricValue"] {
    color: #1F2937;
}

/* Boutons */
.stButton > button {
    background-color: #FFFFFF;
    color: #374151;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
}

.stButton > button:hover {
    border-color: #4D9FFF;
    color: #2563EB;
}

/* Séparateurs */
hr {
    border-color: #DCE3EA;
}

/* Dataframes */
div[data-testid="stDataFrame"] {
    border: 1px solid #DCE3EA;
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# CHARGEMENT DES DONNÉES
# ============================================================

table = pd.read_html(
    "./data/ASHRAE_Service_Life_Data.xls",
    header=7
)[0]

table = table[table["System Type"] != "Heating Pump"].copy()

# Les 0 correspondent à des valeurs manquantes
table.loc[table["Removal Year"] == 0, "Removal Year"] = np.nan
table.loc[table["Install Year"] == 0, "Install Year"] = np.nan

# Dataset historique : dernière année observée = 2008
CURRENT_YEAR = 2008
CURRENT_MONTH = 12

# ============================================================
# DURÉE DE VIE OBSERVÉE
# ============================================================

table["life_duration"] = (
    (table["Removal Year"] - 1) * 12
    + table["Removal Month"]
    - (table["Install Year"] - 1) * 12
    - table["Install Month"]
)

# On élimine les durées incohérentes
table.loc[table["life_duration"] < 0, "life_duration"] = np.nan


# ============================================================
# ÂGE DES ÉQUIPEMENTS EN SERVICE
# ============================================================

table["Age"] = np.nan

mask_active = table["life_duration"].isna()

table.loc[mask_active, "Age"] = (
    (CURRENT_YEAR - 1) * 12
    + CURRENT_MONTH
    - (table.loc[mask_active, "Install Year"] - 1) * 12
    - table.loc[mask_active, "Install Month"]
)


# ============================================================
# DURÉE DE VIE DE RÉFÉRENCE
# ============================================================

stats_equipment = (
    table.groupby("Equipment Type")["life_duration"]
    .agg(["count", "median"])
    .dropna()
)

# On ne fait confiance à l'estimation par type
# qu'à partir de 10 observations
stats_equipment = stats_equipment[
    stats_equipment["count"] >= 10
]

dict_Equipment = stats_equipment["median"].to_dict()


stats_system = (
    table.groupby("System Type")["life_duration"]
    .agg(["count", "median"])
    .dropna()
)

stats_system = stats_system[
    stats_system["count"] >= 10
]

dict_System = stats_system["median"].to_dict()


# ============================================================
# ESTIMATION DU TEMPS RESTANT
# ============================================================

def calcul_temps_restant(row):

    if pd.isna(row["Age"]):
        return np.nan

    # Priorité au type d'équipement
    if row["Equipment Type"] in dict_Equipment:
        return dict_Equipment[row["Equipment Type"]] - row["Age"]

    # Sinon fallback sur le système
    elif row["System Type"] in dict_System:
        return dict_System[row["System Type"]] - row["Age"]

    return np.nan


table["Duree de vie"] = table.apply(
    calcul_temps_restant,
    axis=1
)


# ============================================================
# LOCALISATION DES BÂTIMENTS
# ============================================================

cities = {
    "Paris": (48.8566, 2.3522),
    "Lille": (50.6292, 3.0573),
    "Rouen": (49.4432, 1.0999),
    "Caen": (49.1829, -0.3707),
    "Rennes": (48.1173, -1.6778),
    "Nantes": (47.2184, -1.5536),
    "Bordeaux": (44.8378, -0.5792),
    "Toulouse": (43.6047, 1.4442),
    "Montpellier": (43.6108, 3.8767),
    "Marseille": (43.2965, 5.3698),
    "Nice": (43.7102, 7.2620),
    "Lyon": (45.7640, 4.8357),
    "Grenoble": (45.1885, 5.7245),
    "Clermont-Ferrand": (45.7772, 3.0870),
    "Dijon": (47.3220, 5.0415),
    "Strasbourg": (48.5734, 7.7521),
    "Metz": (49.1193, 6.1757),
    "Nancy": (48.6921, 6.1844),
    "Orléans": (47.9030, 1.9093),
    "Tours": (47.3941, 0.6848),
    "Limoges": (45.8336, 1.2611),
    "Poitiers": (46.5802, 0.3404),
    "La Rochelle": (46.1603, -1.1511),
    "Pau": (43.2951, -0.3708),
    "Bayonne": (43.4929, -1.4748),
    "Perpignan": (42.6887, 2.8948),
    "Avignon": (43.9493, 4.8055),
    "Annecy": (45.8992, 6.1294),
    "Besançon": (47.2378, 6.0241),
    "Le Mans": (48.0061, 0.1996),
}


# Une ville par Building ID
building_ids = table["Building ID"].dropna().unique()
city_names = list(cities.keys())

building_location = {}

for i, building_id in enumerate(building_ids):
    city = city_names[i % len(city_names)]

    building_location[building_id] = {
        "City": city,
        "Latitude": cities[city][0],
        "Longitude": cities[city][1]
    }


# On crée bien les colonnes Latitude / Longitude
table["City"] = table["Building ID"].map(
    lambda x: building_location.get(x, {}).get("City")
)

table["Latitude"] = table["Building ID"].map(
    lambda x: building_location.get(x, {}).get("Latitude")
)

table["Longitude"] = table["Building ID"].map(
    lambda x: building_location.get(x, {}).get("Longitude")
)


# ============================================================
# PETIT DÉCALAGE POUR ÉVITER QUE LES BÂTIMENTS SE SUPERPOSENT
# ============================================================

np.random.seed(42)

table["Latitude"] += np.random.uniform(
    -0.08, 0.08, len(table)
)

table["Longitude"] += np.random.uniform(
    -0.08, 0.08, len(table)
)



def get_gravity(remaining_months):

    if remaining_months < 0:
        return "Dépassement"

    elif remaining_months < 24:
        return "Prioritaire"

    elif remaining_months < 60:
        return "Surveillance"

    else:
        return "Faible"


table["Gravité"] = table["Duree de vie"].apply(get_gravity)







colors = {
    "Faible": [50, 180, 80],
    "Surveillance": [255, 180, 0],
    "Prioritaire": [240, 80, 60],
    "Dépassement": [100, 30, 30],
}

table["Color"] = table["Gravité"].map(colors)



st.set_page_config(
    page_title="Maintenance prédictive",
    page_icon="🏢",
    layout="wide"
)

st.title("Prototype de maintenance prédictive du parc immobilier")

st.caption(
    "Analyse de maturité des équipements et identification "
    "des bâtiments nécessitant une attention prioritaire."
)

st.info(
    "Les localisations sont simulées pour les besoins de la démonstration."
)


# ============================================================
# FILTRES
# ============================================================

col1, col2, col3 = st.columns(3)

with col1:

    equipment_filter = st.multiselect(
        "Type d'équipement",
        sorted(
            table["Equipment Type"]
            .dropna()
            .unique()
        )
    )

with col2:

    system_filter = st.multiselect(
        "Système",
        sorted(
            table["System Type"]
            .dropna()
            .unique()
        )
    )

with col3:

    gravity_filter = st.multiselect(
        "Niveau de priorité",
        [
            "Dépassement",
            "Prioritaire",
            "Surveillance",
            "Faible",
        ]
    )


# ============================================================
# APPLICATION DES FILTRES
# ============================================================

filtered = table.copy()

if equipment_filter:
    filtered = filtered[
        filtered["Equipment Type"].isin(equipment_filter)
    ]

if system_filter:
    filtered = filtered[
        filtered["System Type"].isin(system_filter)
    ]

if gravity_filter:
    filtered = filtered[
        filtered["Gravité"].isin(gravity_filter)
    ]


# ============================================================
# INDICATEURS
# ============================================================

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Bâtiments",
        filtered["Building ID"].nunique()
    )

with col2:
    st.metric(
        "Équipements",
        len(filtered)
    )

with col3:
    st.metric(
        "Prioritaires",
        (filtered["Gravité"] == "Prioritaire").sum()
    )

with col4:
    st.metric(
        "En dépassement",
        (filtered["Gravité"] == "Dépassement").sum()
    )


# ============================================================
# CARTE
# ============================================================

map_data = filtered.dropna(
    subset=["Latitude", "Longitude"]
).copy()

layer = pdk.Layer(
    "ScatterplotLayer",
    data=map_data,
    get_position="[Longitude, Latitude]",
    get_fill_color="Color",
    get_radius=5000,
    radius_min_pixels=3,
    radius_max_pixels=12,
    pickable=True,
    opacity=0.75,
)

tooltip = {
    "html": """
        <b>Bâtiment :</b> {Building ID}<br/>
        <b>Ville :</b> {City}<br/>
        <b>Système :</b> {System Type}<br/>
        <b>Équipement :</b> {Equipment Type}<br/>
        <b>Âge :</b> {Age} mois<br/>
        <b>Durée restante :</b> {Duree de vie} mois<br/>
        <b>Priorité :</b> {Gravité}
    """,
    "style": {
        "backgroundColor": "steelblue",
        "color": "white"
    }
}

view_state = pdk.ViewState(
    latitude=46.6,
    longitude=2.2,
    zoom=5,
    pitch=0
)

deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip=tooltip
)

st.pydeck_chart(
    deck,
    use_container_width=True
)

st.markdown("""### Données et limites

Les données utilisées dans ce prototype proviennent de la ASHRAE Service Life and Maintenance Cost Database**, une base publique regroupant des informations historiques sur la durée de vie de différents équipements HVAC et systèmes techniques des bâtiments.

Source : ASHRAE – HVAC Service Life Database - https://costdatabase.ashrae.org/service_life.asp

L'objectif de ce projet n'est pas de construire un modèle de prédiction de panne industriel ou directement exploitable en production. Les données disponibles étant principalement historiques et ne contenant pas l'ensemble des variables nécessaires à une prédiction fiable de défaillance, les estimations proposées constituent avant tout un indicateur simplifié de maturité des équipements et d'aide à la priorisation de la maintenance.

La durée de vie de référence est estimée à partir des durées de vie historiques observées pour les différents types d'équipements. Lorsque le nombre d'observations est insuffisant à ce niveau de détail, une estimation au niveau du système est utilisée. Les résultats doivent donc être interprétés comme des **ordres de grandeur, et non comme une date prévisionnelle de remplacement.

Les localisations des bâtiments présentées sur la carte sont également simulées afin de permettre la visualisation d'un parc immobilier en France ; elles ne correspondent pas aux localisations réelles des bâtiments présents dans la base ASHRAE.

Ce prototype a été réalisé dans une logique d'exploration : l'objectif était notamment de mettre en pratique le sujet de la maintenance prédictive appliquée à un parc immobilier, d'identifier les données nécessaires à ce type de problématique et de traduire les résultats en un outil simple d'aide à la décision. Il s'agit donc volontairement d'une **première esquisse**, destinée à illustrer une démarche et une compréhension du problème plutôt qu'à proposer une solution définitive.""")
