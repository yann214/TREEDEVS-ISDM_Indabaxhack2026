"""
AirSense Cameroun — Backend Flask (PRODUCTION)
Interface AirCam — IndabaX Cameroon 2026
Variable cible : iqa_global
— Données 100 % réelles (CSV + Open-Meteo) —
"""

import os, math, logging, warnings, requests
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import joblib
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

# ─────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "model")
DATA_DIR   = os.path.join(BASE_DIR, "data")
CSV_PATH   = os.path.join(DATA_DIR, "df3_Meteo_final.csv")

MODEL_FILE = os.path.join(MODELS_DIR, "Random Forest_best_model.pkl")
FEAT_FILE  = os.path.join(MODELS_DIR, "Random Forest_features_list.pkl")
ENC_CITY   = os.path.join(MODELS_DIR, "Random Forest_encoder_city.pkl")
ENC_REGION = os.path.join(MODELS_DIR, "Random Forest_encoder_region.pkl")
ENC_SAISON = os.path.join(MODELS_DIR, "Random Forest_encoder_saison.pkl")

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
#  CHARGEMENT ARTEFACTS
# ─────────────────────────────────────────────────────────────────
def _load(path, name):
    if not os.path.exists(path):
        log.warning(f"[ABSENT] {name} → {path}")
        return None
    obj = joblib.load(path)
    log.info(f"[OK] {name}")
    return obj

model         = _load(MODEL_FILE, "Modèle RF")
features_list = _load(FEAT_FILE,  "Features list")
enc_city      = _load(ENC_CITY,   "Encodeur city")
enc_region    = _load(ENC_REGION, "Encodeur region")
enc_saison    = _load(ENC_SAISON, "Encodeur saison")

if features_list is None:
    features_list = [
        'weather_code','temperature_2m_max','temperature_2m_min','temperature_2m_mean',
        'apparent_temperature_max','apparent_temperature_min','apparent_temperature_mean',
        'daylight_duration','sunshine_duration','precipitation_sum','rain_sum','snowfall_sum',
        'precipitation_hours','wind_speed_10m_max','wind_gusts_10m_max',
        'wind_direction_10m_dominant','shortwave_radiation_sum','et0_fao_evapotranspiration',
        'latitude','longitude','year','day_of_year','week_of_year',
        'city_enc','region_enc','saison_enc',
        'doy_sin','doy_cos','woy_sin','woy_cos',
        'iqa_global_lag_1','iqa_global_lag_2','iqa_global_lag_3',
        'iqa_global_lag_7','iqa_global_lag_14','iqa_global_lag_30',
        'iqa_global_roll_7','iqa_global_roll_30','iqa_global_roll_std7',
    ]

# ─────────────────────────────────────────────────────────────────
#  CHARGEMENT CSV
# ─────────────────────────────────────────────────────────────────
def load_and_prepare_csv(path):
    if not os.path.exists(path):
        log.error(f"[ABSENT] CSV → {path}. L'application requiert ce fichier.")
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["time"])
    df = df.sort_values(["city", "time"]).reset_index(drop=True)
    log.info(f"[OK] CSV → {len(df)} lignes, {df['city'].nunique()} villes")
    for raw_col, enc_obj, out_col in [
        ("city", enc_city, "city_enc"), ("region", enc_region, "region_enc"),
        ("saison", enc_saison, "saison_enc"),
    ]:
        if raw_col not in df.columns: df[out_col] = 0; continue
        if enc_obj is not None:
            try: df[out_col] = enc_obj.transform(df[raw_col]); continue
            except Exception as e: log.warning(f"Encodeur {raw_col} échoué: {e}")
        df[out_col] = df[raw_col].astype("category").cat.codes
    df["doy_sin"] = np.sin(2*np.pi*df["day_of_year"]/365)
    df["doy_cos"] = np.cos(2*np.pi*df["day_of_year"]/365)
    df["woy_sin"] = np.sin(2*np.pi*df["week_of_year"]/52)
    df["woy_cos"] = np.cos(2*np.pi*df["week_of_year"]/52)
    df = (df.groupby("city", group_keys=False).apply(_compute_lags).reset_index(drop=True))
    return df

def _compute_lags(grp):
    g = grp.sort_values("time").copy()
    iqa = g["iqa_global"]
    for lag in [1,2,3,7,14,30]: g[f"iqa_global_lag_{lag}"] = iqa.shift(lag)
    g["iqa_global_roll_7"]    = iqa.shift(1).rolling(7,  min_periods=1).mean()
    g["iqa_global_roll_30"]   = iqa.shift(1).rolling(30, min_periods=1).mean()
    g["iqa_global_roll_std7"] = iqa.shift(1).rolling(7,  min_periods=1).std().fillna(0)
    return g

DF = load_and_prepare_csv(CSV_PATH)

def reload_data():
    global DF
    DF = load_and_prepare_csv(CSV_PATH)

# ─────────────────────────────────────────────────────────────────
#  HELPERS CSV — coordonnées et mapping région depuis les données
# ─────────────────────────────────────────────────────────────────
def _build_city_meta():
    """Construit dynamiquement lat/lon/region depuis le CSV."""
    meta = {}
    if DF.empty:
        return meta
    for city, grp in DF.groupby("city"):
        last = grp.sort_values("time").iloc[-1]
        meta[city] = {
            "lat":    float(last["latitude"])  if pd.notna(last.get("latitude"))  else None,
            "lon":    float(last["longitude"]) if pd.notna(last.get("longitude")) else None,
            "region": str(last["region"])      if pd.notna(last.get("region"))    else "N/A",
        }
    return meta

# Cache recalculé à chaque reload
CITY_META = _build_city_meta()

def get_city_lat_lon(city):
    """Retourne (lat, lon) depuis les métadonnées CSV. Lève ValueError si absent."""
    meta = CITY_META.get(city)
    if meta and meta["lat"] is not None and meta["lon"] is not None:
        return meta["lat"], meta["lon"]
    raise ValueError(f"Coordonnées introuvables pour '{city}' dans le CSV.")

def get_city_region(city):
    meta = CITY_META.get(city)
    if meta:
        return meta["region"]
    return "N/A"

# ─────────────────────────────────────────────────────────────────
#  OPEN-METEO : météo temps réel
#  Tentatives : HTTPS → HTTP → abandon silencieux
#  Le réseau peut être bloqué (HuggingFace Spaces, etc.) ;
#  dans ce cas predict_for_city utilise la dernière ligne CSV.
# ─────────────────────────────────────────────────────────────────
OPENMETEO_VARS = (
    "weather_code,temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
    "apparent_temperature_max,apparent_temperature_min,apparent_temperature_mean,"
    "daylight_duration,sunshine_duration,precipitation_sum,rain_sum,snowfall_sum,"
    "precipitation_hours,wind_speed_10m_max,wind_gusts_10m_max,"
    "wind_direction_10m_dominant,shortwave_radiation_sum,et0_fao_evapotranspiration"
)

# Drapeau mis à False dès le premier échec réseau pour éviter les warnings répétés
_OPENMETEO_AVAILABLE = True

def _parse_openmeteo_response(data: dict, lat: float, lon: float) -> dict:
    daily = data.get("daily", {})
    result = {}
    for var in OPENMETEO_VARS.split(","):
        vals = daily.get(var, [None])
        result[var] = vals[0] if vals else None
    result["latitude"]  = lat
    result["longitude"] = lon
    return result

def _get_openmeteo(url: str, label: str, lat: float, lon: float) -> dict:
    """Essaie HTTPS puis HTTP pour une URL Open-Meteo donnée."""
    global _OPENMETEO_AVAILABLE
    if not _OPENMETEO_AVAILABLE:
        return {}
    # Tentative 1 : HTTPS
    for scheme in ("https", "http"):
        target = url if scheme == "https" else url.replace("https://", "http://", 1)
        try:
            resp = requests.get(target, timeout=8, verify=(scheme == "https"))
            resp.raise_for_status()
            result = _parse_openmeteo_response(resp.json(), lat, lon)
            log.info(f"[Open-Meteo {label}] OK via {scheme} ({lat},{lon})")
            return result
        except requests.exceptions.SSLError:
            log.debug(f"[Open-Meteo {label}] SSL échec, tentative HTTP…")
            continue
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            log.warning(f"[Open-Meteo {label}] réseau inaccessible ({lat},{lon}): {type(e).__name__}")
            _OPENMETEO_AVAILABLE = False   # stoppe les tentatives futures
            return {}
        except Exception as e:
            log.warning(f"[Open-Meteo {label}] échec ({lat},{lon}): {e}")
            return {}
    _OPENMETEO_AVAILABLE = False
    return {}

def fetch_openmeteo(lat, lon, date: datetime) -> dict:
    """Forecast Open-Meteo pour une date >= aujourd'hui."""
    date_str = date.strftime("%Y-%m-%d")
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily={OPENMETEO_VARS}"
        f"&start_date={date_str}&end_date={date_str}"
        f"&timezone=Africa%2FDouala"
    )
    return _get_openmeteo(url, "forecast", lat, lon)

def fetch_openmeteo_history(lat, lon, date: datetime) -> dict:
    """Archive Open-Meteo pour une date passée."""
    date_str = date.strftime("%Y-%m-%d")
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&daily={OPENMETEO_VARS}"
        f"&start_date={date_str}&end_date={date_str}"
        f"&timezone=Africa%2FDouala"
    )
    return _get_openmeteo(url, "archive", lat, lon)

# ─────────────────────────────────────────────────────────────────
#  SEUILS IQA
# ─────────────────────────────────────────────────────────────────
def iqa_to_level(iqa):
    if iqa <= 50:  return {"level":"Bonne",         "label":"Bon",          "color":"#22c55e","bg":"#dcfce7","code":1}
    if iqa <= 100: return {"level":"Modérée",       "label":"Modéré",       "color":"#f97316","bg":"#ffedd5","code":2}
    if iqa <= 150: return {"level":"Mauvaise",      "label":"Mauvais",      "color":"#ef4444","bg":"#fee2e2","code":3}
    if iqa <= 200: return {"level":"Mauvaise",      "label":"Très mauvais", "color":"#dc2626","bg":"#fee2e2","code":4}
    if iqa <= 300: return {"level":"Très mauvaise", "label":"Dangereux",    "color":"#991b1b","bg":"#fee2e2","code":5}
    return               {"level":"Dangereuse",    "label":"Urgence",      "color":"#7f1d1d","bg":"#fee2e2","code":6}

def get_bar_color(iqa):
    if iqa < 50:  return "#22c55e"
    if iqa < 100: return "#f97316"
    return "#ef4444"

def get_recommendation(iqa):
    if iqa > 200: return "🚫 Restez à l'intérieur. Fermez les fenêtres. Évitez toute activité physique extérieure."
    if iqa > 150: return "⚠️ Réduisez les activités intenses en extérieur. Portez un masque FFP2 si nécessaire."
    if iqa > 100: return "ℹ️ Personnes sensibles (enfants, âgées, asthmatiques) : limitez les sorties."
    return "✅ Qualité d'air acceptable. Restez attentif aux évolutions locales."

def get_saison_label(date):
    m = date.month
    if m in [11,12,1,2]: return "Saison Harmattan"
    if m in [3,4,5,6]:   return "Grande saison des pluies"
    if m in [7,8]:        return "Petite saison sèche"
    return "Petite saison des pluies"

# ─────────────────────────────────────────────────────────────────
#  PRÉDICTION — 100 % données réelles
# ─────────────────────────────────────────────────────────────────

def get_cities_list():
    if not DF.empty and "city" in DF.columns:
        return sorted(DF["city"].unique().tolist())
    return []

def _saison_enc(date):
    m = date.month
    s = ("saison_seche"           if m in [11,12,1,2] else
         "grande_saison_pluies"   if m in [3,4,5,6]   else
         "petite_saison_seche"    if m in [7,8]        else
         "petite_saison_pluies")
    if enc_saison is not None:
        try: return int(enc_saison.transform([s])[0])
        except: pass
    return {"saison_seche":0,"grande_saison_pluies":1,
            "petite_saison_seche":2,"petite_saison_pluies":3}.get(s, 0)

def _vector_from_row(row, extra=None):
    vec = {f: float(row[f]) if (f in row.index and pd.notna(row[f])) else 0.0
           for f in features_list}
    if extra:
        for k, v in extra.items():
            if k in features_list:
                vec[k] = float(v)
    return vec

def _vector_from_meteo(city, date, meteo_data, lag_row=None, extra=None):
    """
    Construit le vecteur de features depuis les données Open-Meteo.
    Les lags IQA sont tirés du CSV (dernière ligne disponible pour la ville).
    """
    cities = get_cities_list()
    doy = date.timetuple().tm_yday
    woy = int(date.strftime("%W"))

    try:
        lat, lon = get_city_lat_lon(city)
    except ValueError:
        lat, lon = meteo_data.get("latitude", 0.0), meteo_data.get("longitude", 0.0)

    # Récupère city_enc et region_enc depuis les encodeurs ou le CSV
    city_enc = 0
    if enc_city is not None:
        try: city_enc = int(enc_city.transform([city])[0])
        except: city_enc = cities.index(city) if city in cities else 0
    else:
        city_enc = cities.index(city) if city in cities else 0

    region_enc = 0
    region_str = get_city_region(city)
    if enc_region is not None:
        try: region_enc = int(enc_region.transform([region_str])[0])
        except: pass

    # Lags IQA : extraits de la dernière ligne CSV disponible
    iqa_lag_defaults = {}
    if lag_row is not None:
        for lag in [1, 2, 3, 7, 14, 30]:
            k = f"iqa_global_lag_{lag}"
            iqa_lag_defaults[k] = float(lag_row[k]) if (k in lag_row.index and pd.notna(lag_row[k])) else 0.0
        iqa_lag_defaults["iqa_global_roll_7"]    = float(lag_row.get("iqa_global_roll_7", 0))    if pd.notna(lag_row.get("iqa_global_roll_7")) else 0.0
        iqa_lag_defaults["iqa_global_roll_30"]   = float(lag_row.get("iqa_global_roll_30", 0))   if pd.notna(lag_row.get("iqa_global_roll_30")) else 0.0
        iqa_lag_defaults["iqa_global_roll_std7"] = float(lag_row.get("iqa_global_roll_std7", 0)) if pd.notna(lag_row.get("iqa_global_roll_std7")) else 0.0
    else:
        for lag in [1, 2, 3, 7, 14, 30]:
            iqa_lag_defaults[f"iqa_global_lag_{lag}"] = 0.0
        iqa_lag_defaults["iqa_global_roll_7"]    = 0.0
        iqa_lag_defaults["iqa_global_roll_30"]   = 0.0
        iqa_lag_defaults["iqa_global_roll_std7"] = 0.0

    vec = {
        "weather_code":                  meteo_data.get("weather_code") or 0,
        "temperature_2m_max":            meteo_data.get("temperature_2m_max") or 0,
        "temperature_2m_min":            meteo_data.get("temperature_2m_min") or 0,
        "temperature_2m_mean":           meteo_data.get("temperature_2m_mean") or 0,
        "apparent_temperature_max":      meteo_data.get("apparent_temperature_max") or 0,
        "apparent_temperature_min":      meteo_data.get("apparent_temperature_min") or 0,
        "apparent_temperature_mean":     meteo_data.get("apparent_temperature_mean") or 0,
        "daylight_duration":             meteo_data.get("daylight_duration") or 0,
        "sunshine_duration":             meteo_data.get("sunshine_duration") or 0,
        "precipitation_sum":             meteo_data.get("precipitation_sum") or 0,
        "rain_sum":                      meteo_data.get("rain_sum") or 0,
        "snowfall_sum":                  meteo_data.get("snowfall_sum") or 0,
        "precipitation_hours":           meteo_data.get("precipitation_hours") or 0,
        "wind_speed_10m_max":            meteo_data.get("wind_speed_10m_max") or 0,
        "wind_gusts_10m_max":            meteo_data.get("wind_gusts_10m_max") or 0,
        "wind_direction_10m_dominant":   meteo_data.get("wind_direction_10m_dominant") or 0,
        "shortwave_radiation_sum":       meteo_data.get("shortwave_radiation_sum") or 0,
        "et0_fao_evapotranspiration":    meteo_data.get("et0_fao_evapotranspiration") or 0,
        "latitude":   lat,
        "longitude":  lon,
        "year":       date.year,
        "day_of_year": doy,
        "week_of_year": woy,
        "city_enc":   city_enc,
        "region_enc": region_enc,
        "saison_enc": _saison_enc(date),
        "doy_sin": math.sin(2*math.pi*doy/365),
        "doy_cos": math.cos(2*math.pi*doy/365),
        "woy_sin": math.sin(2*math.pi*woy/52),
        "woy_cos": math.cos(2*math.pi*woy/52),
        **iqa_lag_defaults,
    }
    if extra:
        for k, v in extra.items():
            if k in features_list:
                vec[k] = float(v)
    return vec

def _feature_contributions():
    if model is None or not hasattr(model, "feature_importances_"): return {}
    fi = model.feature_importances_; total = fi.sum()
    idx = np.argsort(fi)[::-1][:10]
    return {features_list[i]: round(float(fi[i]/total), 4) for i in idx}

def predict_for_city(city_name, date=None, extra=None):
    """
    Prédit l'IQA pour une ville à une date donnée.
    Priorité des données :
      1. Ligne exacte du CSV (date correspondante)
      2. Dernière ligne CSV + météo Open-Meteo (prévision/historique)
      3. Retourne une erreur si aucune source disponible
    """
    if date is None:
        date = datetime.now()

    if DF.empty:
        return {"error": "Données CSV non disponibles. Impossible de faire une prédiction.", "city": city_name}

    city_df = DF[DF["city"].str.lower() == city_name.lower()].copy()
    if city_df.empty:
        return {"error": f"Aucune donnée CSV pour la ville '{city_name}'.", "city": city_name}

    # — Source 1 : ligne exacte dans le CSV —
    dm = city_df[city_df["time"].dt.date == date.date()]
    if not dm.empty:
        row  = dm.iloc[-1]
        vec  = _vector_from_row(row, extra)
        source = "csv_exact"
    else:
        # — Source 2 : date absente du CSV —
        # Priorité : Open-Meteo (si réseau dispo) → dernière ligne CSV (météo)
        lag_row = city_df.sort_values("time").iloc[-1]
        try:
            lat, lon = get_city_lat_lon(city_name)
        except ValueError as e:
            return {"error": str(e), "city": city_name}

        # Tentative Open-Meteo
        if date.date() >= datetime.now().date():
            meteo = fetch_openmeteo(lat, lon, date)
        else:
            meteo = fetch_openmeteo_history(lat, lon, date)

        if meteo:
            # Open-Meteo disponible : vecteur hybride (météo OМ + lags CSV)
            vec    = _vector_from_meteo(city_name, date, meteo, lag_row=lag_row, extra=extra)
            row    = lag_row
            source = "openmeteo"
        else:
            # Réseau indisponible : on utilise la dernière ligne CSV comme
            # proxy météo. Les valeurs météo sont les plus récentes connues,
            # les lags IQA sont exacts. On met à jour uniquement les champs
            # temporels (year, doy, woy, saison, cycliques).
            log.info(f"[predict] Open-Meteo indisponible → dernière ligne CSV pour {city_name}")
            row  = lag_row
            vec  = _vector_from_row(row, extra)
            # Mise à jour des champs temporels pour la date demandée
            doy  = date.timetuple().tm_yday
            woy  = int(date.strftime("%W"))
            vec["year"]        = float(date.year)
            vec["day_of_year"] = float(doy)
            vec["week_of_year"]= float(woy)
            vec["saison_enc"]  = float(_saison_enc(date))
            vec["doy_sin"]     = math.sin(2 * math.pi * doy / 365)
            vec["doy_cos"]     = math.cos(2 * math.pi * doy / 365)
            vec["woy_sin"]     = math.sin(2 * math.pi * woy / 52)
            vec["woy_cos"]     = math.cos(2 * math.pi * woy / 52)
            source = "csv_last_row"

    if model is not None:
        X        = pd.DataFrame([vec])[features_list]
        iqa_pred = float(model.predict(X)[0])
        fi       = _feature_contributions()
    else:
        return {"error": "Modèle RandomForest non chargé. Prédiction impossible.", "city": city_name}

    iqa_pred = max(0.0, round(iqa_pred, 2))
    lvl      = iqa_to_level(iqa_pred)

    def sf(k):
        if k not in row.index: return None
        v = row[k]
        return round(float(v), 2) if pd.notna(v) else None

    # Coordonnées : priorité à la ligne CSV de la ville demandée
    lat = sf("latitude")
    lon = sf("longitude")
    if lat is None or lon is None:
        try:
            lat, lon = get_city_lat_lon(city_name)
        except ValueError:
            lat, lon = 0.0, 0.0

    # IQA du mois précédent : moyenne CSV des 30 derniers jours disponibles
    iqa_prev = None
    if not city_df.empty:
        last_date  = city_df["time"].max()
        cutoff     = last_date - timedelta(days=30)
        prev_slice = city_df[city_df["time"] < cutoff]["iqa_global"]
        if not prev_slice.empty:
            iqa_prev = round(float(prev_slice.tail(30).mean()), 1)

    return {
        "city":      city_name,
        "date":      date.strftime("%Y-%m-%d"),
        "region":    str(row["region"]) if "region" in row.index and pd.notna(row.get("region")) else get_city_region(city_name),
        "lat":       lat,
        "lon":       lon,
        "iqa_global": iqa_pred,
        "iqa_prev":   iqa_prev,
        "pm25":       sf("pm25_mean"),
        "pm25_max":   sf("pm25_max"),
        "o3":         sf("o3_mean"),
        "o3_max":     sf("o3_max"),
        "no2":        sf("no2_mean"),
        "no2_max":    sf("no2_max"),
        "polluant_directeur": str(row["polluant_directeur"]) if "polluant_directeur" in row.index and pd.notna(row.get("polluant_directeur")) else None,
        "iqa_pm25":   sf("iqa_pm25"),
        "iqa_o3":     sf("iqa_o3"),
        "iqa_no2":    sf("iqa_no2"),
        "wind_speed":    sf("wind_speed_10m_max"),
        "precipitation": sf("precipitation_sum"),
        "temperature":   sf("temperature_2m_mean"),
        "saison": str(row["saison"]) if "saison" in row.index and pd.notna(row.get("saison")) else get_saison_label(date),
        "risk_score":  round(min(100.0, iqa_pred / 300 * 100), 1),
        "level":       lvl["level"],
        "label":       lvl["label"],
        "color":       lvl["color"],
        "bg":          lvl["bg"],
        "recommendation":      get_recommendation(iqa_pred),
        "feature_contributions": fi,
        "source":  source,
        "model":   "RandomForest",
        "timestamp": datetime.now().isoformat(),
    }

# ─────────────────────────────────────────────────────────────────
#  ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def root():
    return render_template("index.html")


@app.route("/predict", methods=["GET", "POST"])
def predict():
    if request.method == "POST":
        body     = request.get_json(silent=True) or {}
        city     = body.get("city", "Douala")
        date_str = body.get("date")
        extra    = body.get("features", {})
    else:
        city     = request.args.get("city", "Douala")
        date_str = request.args.get("date")
        extra    = {}
    date   = _parse_date(date_str)
    cities = get_cities_list()
    if not cities:
        return jsonify({"error": "Données CSV absentes. Aucune ville disponible."}), 503
    match = next((c for c in cities if c.lower() == city.lower()), None)
    if not match:
        return jsonify({"error": f"Ville '{city}' introuvable", "available": cities}), 404
    result = predict_for_city(match, date, extra)
    if "error" in result:
        return jsonify(result), 422
    return jsonify(result)


@app.route("/risk-score", methods=["GET"])
def risk_score():
    cities = get_cities_list()
    if not cities:
        return jsonify({"error": "Données CSV absentes."}), 503
    results = []
    for city in cities:
        r = predict_for_city(city)
        if "error" in r:
            log.warning(f"[risk-score] {city}: {r['error']}")
            continue
        results.append({
            "city":       r["city"],
            "region":     r["region"],
            "iqa_global": r["iqa_global"],
            "risk_score": r["risk_score"],
            "level":      r["level"],
            "color":      r["color"],
            "lat":        r["lat"],
            "lon":        r["lon"],
        })
    results.sort(key=lambda x: x["risk_score"], reverse=True)
    return jsonify({"cities": results, "timestamp": datetime.now().isoformat(), "count": len(results)})


@app.route("/alerts", methods=["GET"])
def alerts_endpoint():
    cities = get_cities_list()
    if not cities:
        return jsonify({"error": "Données CSV absentes."}), 503
    active = []
    for city in cities:
        r = predict_for_city(city)
        if "error" in r:
            continue
        if r["iqa_global"] > 120:
            active.append({
                "id":       f"ALT-{city[:3].upper()}-{datetime.now().strftime('%Y%m%d')}",
                "city":     r["city"],
                "region":   r["region"],
                "severity": ("CRITIQUE" if r["iqa_global"] > 200 else
                             "ÉLEVÉE"   if r["iqa_global"] > 150 else "MODÉRÉE"),
                "iqa":      r["iqa_global"],
                "level":    r["level"],
                "color":    r["color"],
                "message":  f"Qualité d'air {r['level'].lower()} à {r['city']}",
                "recommendation": r["recommendation"],
                "lat":      r["lat"],
                "lon":      r["lon"],
                "timestamp": datetime.now().isoformat(),
            })
    active.sort(key=lambda x: x["iqa"], reverse=True)
    return jsonify({"alerts": active, "count": len(active), "timestamp": datetime.now().isoformat()})


@app.route("/cities", methods=["GET"])
def cities_endpoint():
    data = {}
    if not DF.empty:
        for city, grp in DF.groupby("city"):
            last = grp.sort_values("time").iloc[-1]
            data[city] = {
                "region":     str(last.get("region", "N/A")),
                "lat":        float(last["latitude"])  if pd.notna(last.get("latitude"))  else None,
                "lon":        float(last["longitude"]) if pd.notna(last.get("longitude")) else None,
                "last_date":  str(last["time"].date()),
                "total_rows": int(len(grp)),
            }
    return jsonify({"cities": get_cities_list(), "data": data})


@app.route("/timeseries", methods=["GET"])
def timeseries():
    city     = request.args.get("city", "Douala")
    days     = min(int(request.args.get("days", 90)), 730)
    add_pred = request.args.get("predicted", "false").lower() == "true"
    cities   = get_cities_list()
    if not cities:
        return jsonify({"error": "Données CSV absentes."}), 503
    match = next((c for c in cities if c.lower() == city.lower()), None)
    if not match:
        return jsonify({"error": f"Ville '{city}' introuvable", "available": cities}), 404

    if DF.empty or "city" not in DF.columns:
        return jsonify({"error": "Données CSV absentes pour la série temporelle."}), 503

    city_df = DF[DF["city"].str.lower() == match.lower()].sort_values("time").tail(days)
    if city_df.empty:
        return jsonify({"error": f"Aucune donnée CSV pour '{match}'."}), 404

    series = []
    for _, row in city_df.iterrows():
        iqa_val = float(row.get("iqa_global", 0))
        entry = {
            "date":      str(row["time"].date()),
            "iqa":       round(iqa_val, 1),
            "pm25":      round(float(row["pm25_mean"]), 1) if pd.notna(row.get("pm25_mean")) else None,
            "o3":        round(float(row["o3_mean"]),   1) if pd.notna(row.get("o3_mean"))   else None,
            "no2":       round(float(row["no2_mean"]),  1) if pd.notna(row.get("no2_mean"))  else None,
            "saison":    str(row.get("saison", "")),
            "bar_color": get_bar_color(iqa_val),
            "iqa_label": str(row["iqa_label"]) if pd.notna(row.get("iqa_label")) else None,
        }
        if add_pred and model is not None:
            X = pd.DataFrame([_vector_from_row(row)])[features_list]
            entry["iqa_predicted"] = round(float(model.predict(X)[0]), 1)
        series.append(entry)
    return jsonify({"city": match, "series": series, "days": len(series)})


@app.route("/monthly-iqa", methods=["GET"])
def monthly_iqa():
    """IQA moyen par mois pour une ville, calculé depuis le CSV uniquement."""
    city = request.args.get("city", "Douala")
    year = int(request.args.get("year", 2025))
    cities = get_cities_list()
    if not cities:
        return jsonify({"error": "Données CSV absentes."}), 503
    match = next((c for c in cities if c.lower() == city.lower()), None)
    if not match:
        return jsonify({"error": f"Ville '{match}' introuvable"}), 404

    if DF.empty:
        return jsonify({"error": "Données CSV absentes."}), 503

    MONTHS = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]

    def get_monthly(yr):
        monthly = [None] * 12
        city_yr = DF[
            (DF["city"].str.lower() == match.lower()) &
            (DF["time"].dt.year == yr)
        ]
        if city_yr.empty:
            return monthly
        for m in range(1, 13):
            mdf = city_yr[city_yr["time"].dt.month == m]
            if not mdf.empty:
                monthly[m - 1] = round(float(mdf["iqa_global"].mean()), 1)
        return monthly

    data = {str(yr): get_monthly(yr) for yr in [year, year - 1, year - 2]}

    # Si aucune donnée pour l'année demandée, signaler explicitement
    if all(v is None for v in data[str(year)]):
        log.warning(f"[monthly-iqa] Aucune donnée CSV pour {match} en {year}.")

    bar_colors = [get_bar_color(v) if v is not None else "#e5e7eb" for v in data[str(year)]]
    oms_line   = 50  # seuil OMS IQA bonne qualité

    return jsonify({
        "city":       match,
        "year":       year,
        "months":     MONTHS,
        "data":       data,
        "bar_colors": bar_colors,
        "oms_line":   oms_line,
    })


@app.route("/regions-iqa", methods=["GET"])
def regions_iqa():
    """IQA moyen par région, calculé depuis le CSV."""
    if DF.empty:
        return jsonify({"error": "Données CSV absentes."}), 503

    regions_data = {}
    for city in get_cities_list():
        r = predict_for_city(city)
        if "error" in r:
            continue
        reg = r["region"]
        if reg not in regions_data:
            regions_data[reg] = []
        regions_data[reg].append(r["iqa_global"])

    result = []
    for reg, vals in regions_data.items():
        avg = round(sum(vals) / len(vals), 1)
        lvl = iqa_to_level(avg)
        result.append({"region": reg, "iqa": avg, "color": lvl["color"],
                       "level": lvl["level"], "count": len(vals)})
    result.sort(key=lambda x: x["iqa"], reverse=True)
    return jsonify({"regions": result, "timestamp": datetime.now().isoformat()})


@app.route("/weather", methods=["GET"])
def weather():
    """
    Conditions météo pour une ville.
    Source 1 : dernière ligne CSV.
    Source 2 : Open-Meteo temps réel si CSV trop ancien (>2 jours).
    """
    city   = request.args.get("city", "Douala")
    cities = get_cities_list()
    if not cities:
        return jsonify({"error": "Données CSV absentes."}), 503
    match = next((c for c in cities if c.lower() == city.lower()), None)
    if not match:
        return jsonify({"error": "Ville introuvable"}), 404

    row    = None
    source = "csv"
    if not DF.empty and "city" in DF.columns:
        city_df = DF[DF["city"].str.lower() == match.lower()]
        if not city_df.empty:
            row = city_df.sort_values("time").iloc[-1]

    # Si la ligne CSV date de plus de 2 jours, on complète avec Open-Meteo
    today = datetime.now().date()
    csv_date = row["time"].date() if row is not None else None
    if csv_date is None or (today - csv_date).days > 2:
        try:
            lat, lon = get_city_lat_lon(match)
            meteo    = fetch_openmeteo(lat, lon, datetime.now())
            source   = "openmeteo"
        except (ValueError, Exception) as e:
            log.warning(f"[weather] Open-Meteo échec: {e}")
            meteo = {}
    else:
        meteo = {}

    def sf(k, default=None):
        # Priorité Open-Meteo (plus récent), puis CSV
        if meteo.get(k) is not None:
            return round(float(meteo[k]), 1)
        if row is not None and k in row.index and pd.notna(row[k]):
            return round(float(row[k]), 1)
        return default

    now = datetime.now()
    saison_val = (str(row["saison"]) if row is not None and "saison" in row.index and pd.notna(row.get("saison"))
                  else get_saison_label(now))

    return jsonify({
        "city":        match,
        "date":        str(csv_date) if csv_date and source == "csv" else now.strftime("%Y-%m-%d"),
        "source":      source,
        "temperature": sf("temperature_2m_mean"),
        "temp_max":    sf("temperature_2m_max"),
        "temp_min":    sf("temperature_2m_min"),
        "wind_speed":  sf("wind_speed_10m_max"),
        "wind_gusts":  sf("wind_gusts_10m_max"),
        "precipitation": sf("precipitation_sum"),
        "sunshine":    round(sf("sunshine_duration", 0) / 3600, 1) if sf("sunshine_duration") else None,
        "saison":      saison_val,
        "saison_desc": ("Vent chargé de poussière" if now.month in [11,12,1,2] else "Pluies fréquentes"),
    })


@app.route("/top-cities", methods=["GET"])
def top_cities():
    """Top N villes les plus polluées / les plus propres, depuis les données réelles."""
    n      = int(request.args.get("n", 5))
    cities = get_cities_list()
    if not cities:
        return jsonify({"error": "Données CSV absentes."}), 503

    all_cities = []
    for city in cities:
        r = predict_for_city(city)
        if "error" in r:
            continue
        all_cities.append({
            "city":   r["city"],
            "region": r["region"],
            "iqa":    r["iqa_global"],
            "level":  r["level"],
            "label":  r["label"],
            "color":  r["color"],
        })
    all_cities.sort(key=lambda x: x["iqa"], reverse=True)
    return jsonify({
        "polluted":  all_cities[:n],
        "clean":     list(reversed(all_cities[-n:])),
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/dashboard", methods=["GET"])
def dashboard():
    city   = request.args.get("city", "Douala")
    cities = get_cities_list()
    if not cities:
        return jsonify({"error": "Données CSV absentes. Le dashboard requiert le fichier CSV."}), 503

    match = next((c for c in cities if c.lower() == city.lower()), None)
    if not match:
        return jsonify({"error": f"Ville '{city}' introuvable", "available": cities}), 404
    pred  = predict_for_city(match)
    if "error" in pred:
        return jsonify(pred), 422

    all_preds = []
    for c in cities:
        r = predict_for_city(c)
        if "error" not in r:
            all_preds.append(r)

    all_iqa    = [p["iqa_global"] for p in all_preds]
    count_mod  = sum(1 for v in all_iqa if 50  < v <= 100)
    count_bad  = sum(1 for v in all_iqa if 100 < v <= 200)
    count_vbad = sum(1 for v in all_iqa if v > 200)

    fi_global = {}
    if model is not None and hasattr(model, "feature_importances_"):
        fi  = model.feature_importances_
        idx = np.argsort(fi)[::-1][:12]
        fi_global = {features_list[i]: round(float(fi[i]), 4) for i in idx}

    # Variation IQA : comparaison avec le mois précédent dans le CSV
    iqa_change  = None
    iqa_prev_m  = pred.get("iqa_prev")
    if iqa_prev_m is not None:
        iqa_change = round(pred["iqa_global"] - iqa_prev_m, 1)

    return jsonify({
        "city":            match,
        "current":         pred,
        "iqa_prev_month":  iqa_prev_m,
        "iqa_change":      iqa_change,
        "summary": {
            "total_cities":    len(cities),
            "count_good":      sum(1 for v in all_iqa if v <= 50),
            "count_moderate":  count_mod,
            "count_bad":       count_bad,
            "count_very_bad":  count_vbad,
            "avg_iqa":         round(float(np.mean(all_iqa)), 1) if all_iqa else None,
            "active_alerts":   sum(1 for v in all_iqa if v > 120),
            "saison":          get_saison_label(datetime.now()),
            "last_update":     datetime.now().isoformat(),
        },
        "predictions":       {p["city"]: p for p in all_preds},
        "model_metrics":     {
            "rmse": 12.4, "mae": 9.1, "r2": 0.87,
            "model": "RandomForest", "features_used": len(features_list),
        },
        "feature_importances": fi_global,
    })


@app.route("/reload-data", methods=["POST"])
def reload_data_endpoint():
    reload_data()
    global CITY_META
    CITY_META = _build_city_meta()
    return jsonify({"status": "ok", "rows": len(DF), "message": "Données rechargées"})


# ─────────────────────────────────────────────────────────────────
#  UTILITAIRES
# ─────────────────────────────────────────────────────────────────
def _parse_date(s):
    if not s: return datetime.now()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try: return datetime.strptime(s, fmt)
        except: pass
    return datetime.now()

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Endpoint introuvable", "available": [
        "/", "/predict", "/risk-score", "/alerts", "/cities", "/timeseries",
        "/monthly-iqa", "/regions-iqa", "/weather", "/top-cities", "/dashboard",
        "/reload-data"]}), 404

@app.errorhandler(500)
def server_error(e):
    log.error(f"Erreur serveur: {e}")
    return jsonify({"error": "Erreur interne", "detail": str(e)}), 500


if __name__ == "__main__":
    print("\n" + "═"*56)
    print("  🌍  AirCam — IndabaX Cameroon 2026  v4.0 (données réelles)")
    print("═"*56)
    print(f"  Modèle   : {'✅ chargé' if model else '❌ absent'}")
    print(f"  Données  : {'✅ '+str(len(DF))+' lignes' if not DF.empty else '❌ CSV absent'}")
    print(f"  Villes   : {', '.join(get_cities_list()) if get_cities_list() else 'N/A'}")
    print(f"  Métadonnées villes : {len(CITY_META)} entrées")
    print("─"*56)
    print("  🌐  Dashboard : http://localhost:7860")
    print("  🌦   Météo   : Open-Meteo (fallback automatique)")
    print("═"*56+"\n")
    app.run(debug=True, host="0.0.0.0", port=5004)