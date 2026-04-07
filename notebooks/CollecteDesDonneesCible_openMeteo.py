"""
=============================================================
INDABAX CAMEROON 2026 — Semaine 1
Étape 3 : Open-Meteo Air Quality — PM2.5 + O3 + NO2
- Gratuit, sans compte, sans licence
- Source : CAMS Global reanalysis
- Résolution : ~11 km, horaire → agrégé en journalier
=============================================================
Prérequis :
    pip install requests pandas numpy tqdm
=============================================================
"""

import time
import requests
import numpy as np
import pandas as pd
from pathlib import Path
from tqdm import tqdm

# ════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════

DATASET_CLEAN_PATH = "dataset_clean.csv"
OUTPUT_POL_PATH    = "polluants_openmeteo.csv"
OUTPUT_FINAL_PATH  = "dataset_avec_polluants_openmeteo.csv"

DATE_DEBUT = "2020-01-01"
DATE_FIN   = "2025-12-20"

BASE_URL   = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Polluants à récupérer depuis Open-Meteo
# Clé = nom paramètre API  |  Valeur = préfixe colonne de sortie
POLLUANTS = {
    "pm2_5":          "pm25",   # PM2.5  µg/m³
    "ozone":          "o3",     # Ozone  µg/m³
    "nitrogen_dioxide": "no2",  # NO2    µg/m³
}

# Seuils OMS journaliers (µg/m³) pour classification
SEUILS_OMS = {
    "pm25": [0, 15, 35, 55, 110, float("inf")],
    "o3":   [0, 50, 100, 150, 200, float("inf")],
    "no2":  [0, 25,  50, 100, 200, float("inf")],
}
LABELS_OMS = ["Bonne", "Modérée", "Mauvaise", "Très mauvaise", "Dangereuse"]


# ════════════════════════════════════════════════════════════
# TÉLÉCHARGEMENT OPEN-METEO (une ville à la fois)
# ════════════════════════════════════════════════════════════

def telecharger_openmeteo_multipolluants(villes_df: pd.DataFrame) -> pd.DataFrame:
    """
    Récupère PM2.5, O3 et NO2 horaires pour les 42 villes
    puis agrège en journalier (mean, max, min, p95).
    """

    resultats = []
    erreurs   = []

    print(f"Open-Meteo Air Quality — {len(villes_df)} villes")
    print(f"Polluants  : {', '.join(POLLUANTS.values())}")
    print(f"Période    : {DATE_DEBUT} → {DATE_FIN}\n")

    for _, ville in tqdm(villes_df.iterrows(),
                         total=len(villes_df),
                         desc="Villes"):

        params = {
            "latitude":   round(ville["latitude"],  4),
            "longitude":  round(ville["longitude"], 4),
            "hourly":     ",".join(POLLUANTS.keys()),
            "start_date": DATE_DEBUT,
            "end_date":   DATE_FIN,
            "timezone":   "Africa/Douala",
        }

        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if "hourly" not in data:
                erreurs.append(ville["city"])
                continue

            # Construction du DataFrame horaire
            df_h = pd.DataFrame({"time": pd.to_datetime(data["hourly"]["time"])})
            for api_key, prefixe in POLLUANTS.items():
                if api_key in data["hourly"]:
                    df_h[prefixe] = data["hourly"][api_key]
                else:
                    df_h[prefixe] = np.nan

            # Agrégation horaire → journalier
            df_h["date"] = df_h["time"].dt.date
            agg_dict = {}
            for prefixe in POLLUANTS.values():
                agg_dict[f"{prefixe}_mean"] = (prefixe, "mean")
                agg_dict[f"{prefixe}_max"]  = (prefixe, "max")
                agg_dict[f"{prefixe}_min"]  = (prefixe, "min")
                agg_dict[f"{prefixe}_p95"]  = (
                    prefixe, lambda x: x.quantile(0.95)
                )

            df_jour = df_h.groupby("date").agg(
                pm25_mean=("pm25", "mean"),
                pm25_max =("pm25", "max"),
                pm25_min =("pm25", "min"),
                pm25_p95 =("pm25", lambda x: x.quantile(0.95)),
                o3_mean  =("o3",   "mean"),
                o3_max   =("o3",   "max"),
                o3_min   =("o3",   "min"),
                o3_p95   =("o3",   lambda x: x.quantile(0.95)),
                no2_mean =("no2",  "mean"),
                no2_max  =("no2",  "max"),
                no2_min  =("no2",  "min"),
                no2_p95  =("no2",  lambda x: x.quantile(0.95)),
            ).reset_index()

            df_jour["time"] = pd.to_datetime(df_jour["date"])
            df_jour = df_jour.drop(columns=["date"])
            df_jour["city"] = ville["city"]

            # Arrondi
            cols_val = [c for c in df_jour.columns
                        if c not in ["time", "city"]]
            df_jour[cols_val] = df_jour[cols_val].round(3)

            resultats.append(df_jour)
            time.sleep(0.3)   # respecter les limites API

        except requests.exceptions.RequestException as e:
            print(f"\n  ERREUR {ville['city']} : {e}")
            erreurs.append(ville["city"])
            time.sleep(2)

    if erreurs:
        print(f"\nVilles en erreur ({len(erreurs)}) : {erreurs}")
        print("Relancez le script — les villes en cache seront skippées.")

    if not resultats:
        raise ValueError("Aucune donnée récupérée. Vérifiez votre connexion.")

    df_pol = pd.concat(resultats, ignore_index=True)

    # Réorganiser colonnes : city, time en premier
    cols = ["city", "time"] + [c for c in df_pol.columns
                                if c not in ["city", "time"]]
    df_pol = df_pol[cols]

    print(f"\nDonnées récupérées : {len(df_pol):,} observations")
    print(f"Villes couvertes   : {df_pol['city'].nunique()} / {len(villes_df)}")
    print(f"Période            : {df_pol['time'].min()} → {df_pol['time'].max()}")
    print(f"\nStatistiques :")
    cols_mean = ["pm25_mean", "o3_mean", "no2_mean"]
    print(df_pol[cols_mean].describe().round(2).to_string())

    return df_pol


# ════════════════════════════════════════════════════════════
# JOINTURE + CLASSIFICATION OMS
# ════════════════════════════════════════════════════════════

def joindre_et_classifier(df_meteo: pd.DataFrame,
                           df_pol: pd.DataFrame) -> pd.DataFrame:

    print("\n" + "=" * 60)
    print("JOINTURE MÉTÉO + POLLUANTS")
    print("=" * 60)

    df_meteo["time"] = pd.to_datetime(df_meteo["time"])
    df_pol["time"]   = pd.to_datetime(df_pol["time"])

    n      = len(df_meteo)
    df     = df_meteo.merge(df_pol, on=["city", "time"], how="left")
    assert len(df) == n, "Erreur jointure : nombre de lignes modifié !"

    # Classification OMS pour chaque polluant
    for pol, bins in SEUILS_OMS.items():
        col_mean = f"{pol}_mean"
        if col_mean not in df.columns:
            continue
        taux = df[col_mean].notna().sum() / n * 100
        df[f"qualite_{pol}"] = pd.cut(
            df[col_mean], bins=bins, labels=LABELS_OMS
        )
        df[f"alerte_{pol}"] = df[col_mean] > bins[2]
        print(f"  {pol.upper():5s} : {taux:.1f}% couverts")

    # Indice global = pire des 3 polluants
    ordre = {l: i for i, l in enumerate(LABELS_OMS)}
    cols_qualite = [f"qualite_{p}" for p in SEUILS_OMS if f"qualite_{p}" in df.columns]

    def pire_qualite(row):
        vals = [str(row[c]) for c in cols_qualite if pd.notna(row[c])]
        if not vals:
            return np.nan
        return max(vals, key=lambda x: ordre.get(x, -1))

    df["indice_global"] = df.apply(pire_qualite, axis=1)

    print(f"\n  Lignes météo       : {n:,}")
    print(f"\nDistribution indice global :")
    print(df["indice_global"].value_counts(dropna=False).to_string())

    return df


# ════════════════════════════════════════════════════════════
# RAPPORT PAR RÉGION
# ════════════════════════════════════════════════════════════

def rapport_polluants(df: pd.DataFrame):

    print("\n" + "=" * 60)
    print("RAPPORT POLLUANTS PAR RÉGION")
    print("=" * 60)
    print("Seuils OMS (µg/m³) : PM2.5 ≤15 | O3 ≤100 | NO2 ≤25\n")

    for pol in SEUILS_OMS:
        col = f"{pol}_mean"
        if col not in df.columns:
            continue
        print(f"--- {pol.upper()} (µg/m³) ---")
        stats = (
            df.groupby("region")[col]
            .agg(["mean", "max", "std"])
            .round(2)
            .sort_values("mean", ascending=False)
        )
        stats.columns = ["Moyenne", "Max", "Std"]
        print(stats.to_string())
        print()

    print("Top 10 jours — PM2.5 le plus élevé :")
    cols_top = ["time", "city", "region", "pm25_mean", "o3_mean", "no2_mean"]
    cols_top = [c for c in cols_top if c in df.columns]
    top10 = (
        df[cols_top].dropna(subset=["pm25_mean"])
        .nlargest(10, "pm25_mean")
        .reset_index(drop=True)
    )
    print(top10.to_string(index=False))


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # Chargement dataset nettoyé
    print("Chargement du dataset nettoyé...")
    df_meteo = pd.read_csv(DATASET_CLEAN_PATH, parse_dates=["time"])
    df_meteo = df_meteo.dropna(subset=["city", "latitude", "longitude"])
    df_meteo["city"] = df_meteo["city"].str.strip().str.title()
    print(f"  {df_meteo.shape[0]:,} lignes chargées.")

    # Extraction des 42 villes
    villes_df = (
        df_meteo[["city", "region", "latitude", "longitude"]]
        .drop_duplicates("city")
        .reset_index(drop=True)
    )
    print(f"  {len(villes_df)} villes identifiées.\n")

    # Récupération polluants (avec cache)
    cache = Path(OUTPUT_POL_PATH)
    if cache.exists():
        print(f"Cache trouvé : {OUTPUT_POL_PATH} — chargement direct.")
        df_pol = pd.read_csv(cache, parse_dates=["time"])
    else:
        df_pol = telecharger_openmeteo_multipolluants(villes_df)
        df_pol.to_csv(OUTPUT_POL_PATH, index=False)
        print(f"Polluants sauvegardés : {OUTPUT_POL_PATH}")

    # Jointure + classification
    df_final = joindre_et_classifier(df_meteo, df_pol)

    # Rapport
    rapport_polluants(df_final)

    # Sauvegarde
    df_final.to_csv(OUTPUT_FINAL_PATH, index=False)
    print(f"\nDataset final sauvegardé : {OUTPUT_FINAL_PATH}")
    print(f"Shape : {df_final.shape}")
    print("\nPrêt pour l'étape 4 : Feature Engineering !")