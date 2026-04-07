"""
=============================================================
INDABAX CAMEROON 2026 — Semaine 1
Étapes 1 & 2 : Audit + Nettoyage du dataset météo
=============================================================
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
DATA_PATH = "../data/Dataset_complet_Meteo.xlsx"   # ← adapter au chemin réel
OUTPUT_PATH = "../data/dataset_clean.csv"

pd.set_option("display.max_columns", None)
pd.set_option("display.float_format", "{:.3f}".format)


# ═════════════════════════════════════════════
# ÉTAPE 1 — AUDIT INITIAL
# ═════════════════════════════════════════════

def audit_dataset(df: pd.DataFrame) -> dict:
    """Rapport d'audit complet du dataset brut."""
    print("=" * 60)
    print("AUDIT DU DATASET")
    print("=" * 60)

    rapport = {}

    # 1.1 Dimensions
    print(f"\n[1] Dimensions : {df.shape[0]:,} lignes × {df.shape[1]} colonnes")
    rapport["shape"] = df.shape

    # 1.2 Types de données
    print("\n[2] Types de données :")
    print(df.dtypes.to_string())

    # 1.3 Valeurs manquantes
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2)
    missing_df = pd.DataFrame({
        "manquants": missing,
        "pourcent": missing_pct
    }).query("manquants > 0").sort_values("pourcent", ascending=False)

    print(f"\n[3] Valeurs manquantes ({len(missing_df)} colonnes affectées) :")
    if len(missing_df) > 0:
        print(missing_df.to_string())
    else:
        print("  Aucune valeur manquante détectée.")
    rapport["missing"] = missing_df

    # 1.4 Doublons
    n_dup = df.duplicated().sum()
    n_dup_key = df.duplicated(subset=["time", "city"]).sum()
    print(f"\n[4] Doublons :")
    print(f"  Lignes dupliquées (toutes colonnes) : {n_dup}")
    print(f"  Doublons (time, city) : {n_dup_key}  ← clé métier")
    rapport["doublons"] = {"total": n_dup, "cle_metier": n_dup_key}

    # 1.5 Couverture temporelle
    print(f"\n[5] Couverture temporelle :")
    print(f"  Début  : {df['time'].min()}")
    print(f"  Fin    : {df['time'].max()}")
    n_jours = (df["time"].max() - df["time"].min()).days + 1
    n_villes = df["city"].nunique()
    attendu = n_jours * n_villes
    print(f"  Jours couverts : {n_jours} | Villes : {n_villes}")
    print(f"  Observations attendues : {attendu:,} | Réelles : {len(df):,}")
    manquantes_obs = attendu - len(df)
    if manquantes_obs > 0:
        print(f"  ATTENTION : {manquantes_obs:,} observations manquantes !")
    rapport["temporel"] = {"jours": n_jours, "villes": n_villes, "manquantes": manquantes_obs}

    # 1.6 Cohérence géographique
    print(f"\n[6] Villes & régions :")
    ville_region = df.groupby("city")["region"].nunique()
    incoherents = ville_region[ville_region > 1]
    if len(incoherents) > 0:
        print(f"  PROBLÈME : {len(incoherents)} ville(s) avec plusieurs régions !")
        print(incoherents)
    else:
        print(f"  OK — {n_villes} villes, chacune dans une seule région.")

    # 1.7 Statistiques descriptives — variables numériques
    print("\n[7] Statistiques descriptives (variables clés) :")
    cols_cles = [
        "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
        "precipitation_sum", "wind_speed_10m_max", "wind_gusts_10m_max",
        "shortwave_radiation_sum", "et0_fao_evapotranspiration"
    ]
    cols_cles = [c for c in cols_cles if c in df.columns]
    print(df[cols_cles].describe().round(2).to_string())

    # 1.8 Vérifications logiques
    print("\n[8] Vérifications logiques :")
    issues = []

    if "temperature_2m_max" in df.columns and "temperature_2m_min" in df.columns:
        inv_temp = (df["temperature_2m_max"] < df["temperature_2m_min"]).sum()
        print(f"  Tmax < Tmin : {inv_temp} cas")
        if inv_temp > 0:
            issues.append(f"temperature inversée ({inv_temp} cas)")

    if "precipitation_sum" in df.columns:
        neg_precip = (df["precipitation_sum"] < 0).sum()
        print(f"  Précipitations négatives : {neg_precip} cas")
        if neg_precip > 0:
            issues.append(f"précipitations négatives ({neg_precip} cas)")

    if "wind_speed_10m_max" in df.columns:
        neg_vent = (df["wind_speed_10m_max"] < 0).sum()
        high_vent = (df["wind_speed_10m_max"] > 200).sum()
        print(f"  Vent négatif : {neg_vent} cas | Vent > 200 km/h : {high_vent} cas")

    if "snowfall_sum" in df.columns:
        snow = (df["snowfall_sum"] > 0).sum()
        print(f"  Neige > 0 (doit être 0) : {snow} cas")
        if snow > 0:
            issues.append(f"neige non nulle ({snow} cas)")

    rapport["issues"] = issues
    print(f"\n  Résumé : {len(issues)} problème(s) logique(s) détecté(s)")

    return rapport


# ═════════════════════════════════════════════
# ÉTAPE 2 — NETTOYAGE
# ═════════════════════════════════════════════

def nettoyer_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoyage complet et traçable du dataset."""
    print("\n" + "=" * 60)
    print("NETTOYAGE DU DATASET")
    print("=" * 60)

    df = df.copy()
    n_init = len(df)

    # ── 2.1 Typage des colonnes ──────────────────────────────────
    print("\n[2.1] Conversion des types...")

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["city"] = df["city"].str.strip().str.title()
    df["region"] = df["region"].str.strip().str.title()

    # Colonnes numériques attendues
    cols_num = [
        "latitude", "longitude",
        "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
        "apparent_temperature_max", "apparent_temperature_min", "apparent_temperature_mean",
        "weather_code", "precipitation_sum", "rain_sum", "snowfall_sum",
        "precipitation_hours", "wind_speed_10m_max", "wind_gusts_10m_max",
        "wind_direction_10m_dominant", "daylight_duration", "sunshine_duration",
        "shortwave_radiation_sum", "et0_fao_evapotranspiration"
    ]
    for col in cols_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    print(f"  OK — types convertis.")

    # ── 2.2 Suppression des doublons ─────────────────────────────
    print("\n[2.2] Suppression des doublons...")
    n_avant = len(df)
    df = df.drop_duplicates(subset=["time", "city"], keep="first")
    n_suppr = n_avant - len(df)
    print(f"  {n_suppr} doublon(s) supprimé(s) sur clé (time, city).")

    # ── 2.3 Dates invalides ──────────────────────────────────────
    print("\n[2.3] Suppression des dates invalides...")
    n_avant = len(df)
    df = df.dropna(subset=["time", "city"])
    n_suppr = n_avant - len(df)
    print(f"  {n_suppr} ligne(s) supprimée(s) (date ou ville nulle).")

    # ── 2.4 Complétion du calendrier (dates manquantes par ville) ─
    print("\n[2.4] Reconstruction du calendrier complet...")
    date_min = df["time"].min()
    date_max = df["time"].max()
    calendrier = pd.date_range(date_min, date_max, freq="D")

    villes_meta = df[["city", "region", "latitude", "longitude"]].drop_duplicates("city")
    idx_complet = pd.MultiIndex.from_product(
        [villes_meta["city"].values, calendrier],
        names=["city", "time"]
    )
    df_complet = pd.DataFrame(index=idx_complet).reset_index()
    df = df_complet.merge(df, on=["city", "time"], how="left")

    # Ré-attacher les métadonnées statiques
    df = df.drop(columns=["region", "latitude", "longitude"], errors="ignore")
    df = df.merge(villes_meta, on="city", how="left")

    n_nouvelles = len(df) - (n_init - n_suppr)
    print(f"  {max(0, n_nouvelles)} date(s) recréée(s) avec NaN — seront imputées.")

    # ── 2.5 Gestion des valeurs aberrantes (outliers) ────────────
    print("\n[2.5] Correction des valeurs aberrantes...")

    corrections = {
        "precipitation_sum": (0, None),      # pas de précipitation négative
        "rain_sum": (0, None),
        "snowfall_sum": (0, 0),              # toujours 0 au Cameroun
        "wind_speed_10m_max": (0, 200),      # 0-200 km/h
        "wind_gusts_10m_max": (0, 250),
        "wind_direction_10m_dominant": (0, 360),
        "daylight_duration": (0, 86400),     # en secondes
        "sunshine_duration": (0, 86400),
        "shortwave_radiation_sum": (0, None),
        "et0_fao_evapotranspiration": (0, None),
        "precipitation_hours": (0, 24),
    }

    for col, (vmin, vmax) in corrections.items():
        if col not in df.columns:
            continue
        n_avant = df[col].notna().sum()
        if vmin is not None:
            df.loc[df[col] < vmin, col] = np.nan
        if vmax is not None:
            df.loc[df[col] > vmax, col] = np.nan
        n_apres = df[col].notna().sum()
        if n_avant != n_apres:
            print(f"  {col} : {n_avant - n_apres} valeur(s) aberrante(s) → NaN")

    # Cohérence Tmax >= Tmin
    if "temperature_2m_max" in df.columns and "temperature_2m_min" in df.columns:
        masque_inv = df["temperature_2m_max"] < df["temperature_2m_min"]
        n_inv = masque_inv.sum()
        if n_inv > 0:
            df.loc[masque_inv, ["temperature_2m_max", "temperature_2m_min"]] = np.nan
            print(f"  temperature_2m : {n_inv} inversion(s) Tmax<Tmin → NaN")

    # Sunshine ne peut pas dépasser daylight
    if "sunshine_duration" in df.columns and "daylight_duration" in df.columns:
        masque = df["sunshine_duration"] > df["daylight_duration"]
        df.loc[masque, "sunshine_duration"] = df.loc[masque, "daylight_duration"]
        print(f"  sunshine_duration > daylight : {masque.sum()} cas corrigés.")

    # ── 2.6 Imputation des valeurs manquantes ────────────────────
    print("\n[2.6] Imputation des valeurs manquantes...")

    cols_num_imputer = [c for c in cols_num if c in df.columns and c not in
                        ["weather_code", "wind_direction_10m_dominant"]]

    # Interpolation temporelle par ville (méthode linéaire, max 3 jours consécutifs)
    df = df.sort_values(["city", "time"])
    for col in cols_num_imputer:
        avant = df[col].isna().sum()
        df[col] = (
            df.groupby("city")[col]
            .transform(lambda x: x.interpolate(method="linear", limit=3, limit_direction="both"))
        )
        apres = df[col].isna().sum()
        if avant > 0:
            print(f"  {col} : {avant} NaN → {apres} restants après interpolation")

    # Pour les NaN restants (>3j consécutifs) : médiane par ville × mois
    df["month"] = df["time"].dt.month
    for col in cols_num_imputer:
        if df[col].isna().sum() == 0:
            continue
        mediane_ville_mois = (
            df.groupby(["city", "month"])[col].transform("median")
        )
        df[col] = df[col].fillna(mediane_ville_mois)

        # Ultime fallback : médiane globale de la colonne
        df[col] = df[col].fillna(df[col].median())

    # Weather code : mode par ville × mois
    if "weather_code" in df.columns:
        df["weather_code"] = df["weather_code"].fillna(
            df.groupby(["city", "month"])["weather_code"]
            .transform(lambda x: x.mode()[0] if not x.mode().empty else 0)
        ).astype(int)

    # ── 2.7 Ajout de colonnes temporelles utiles ─────────────────
    print("\n[2.7] Ajout de colonnes temporelles...")
    df["year"] = df["time"].dt.year
    df["month"] = df["time"].dt.month
    df["day_of_year"] = df["time"].dt.dayofyear
    df["week_of_year"] = df["time"].dt.isocalendar().week.astype(int)
    df["saison"] = df["month"].map({
        12: "Harmattan", 1: "Harmattan", 2: "Harmattan",
        3: "Transition", 4: "Transition",
        5: "Saison_pluies", 6: "Saison_pluies", 7: "Saison_pluies",
        8: "Saison_pluies", 9: "Saison_pluies", 10: "Saison_pluies",
        11: "Transition"
    })

    # ── 2.8 Rapport final ────────────────────────────────────────
    df = df.drop(columns=["month"], errors="ignore")  # était temporaire
    df = df.sort_values(["city", "time"]).reset_index(drop=True)

    missing_final = df.isnull().sum().sum()
    print(f"\n{'='*60}")
    print(f"NETTOYAGE TERMINÉ")
    print(f"  Lignes finales   : {len(df):,}")
    print(f"  Colonnes         : {df.shape[1]}")
    print(f"  NaN restants     : {missing_final}")
    print(f"{'='*60}")

    return df


# ═════════════════════════════════════════════
# VISUALISATIONS D'AUDIT
# ═════════════════════════════════════════════

def visualiser_qualite(df_brut: pd.DataFrame, df_clean: pd.DataFrame):
    """Graphiques de contrôle qualité avant/après nettoyage."""

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Contrôle qualité — Avant / Après nettoyage", fontsize=14, fontweight="bold")

    # 1. Heatmap des valeurs manquantes (avant)
    ax = axes[0, 0]
    cols_check = [c for c in df_brut.columns if df_brut[c].isnull().sum() > 0]
    if cols_check:
        missing_par_ville = df_brut.groupby("city")[cols_check].apply(
            lambda x: x.isnull().mean() * 100
        ).T
        sns.heatmap(missing_par_ville, ax=ax, cmap="YlOrRd", cbar_kws={"label": "% manquant"},
                    linewidths=0.3, fmt=".0f")
        ax.set_title("% valeurs manquantes par ville (brut)")
        ax.tick_params(axis="x", rotation=90, labelsize=6)
    else:
        ax.text(0.5, 0.5, "Aucune valeur manquante", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Valeurs manquantes (brut)")

    # 2. Distribution température (avant vs après)
    ax = axes[0, 1]
    col_t = "temperature_2m_mean"
    if col_t in df_brut.columns:
        ax.hist(df_brut[col_t].dropna(), bins=50, alpha=0.5, label="Brut", color="#E24B4A")
        ax.hist(df_clean[col_t].dropna(), bins=50, alpha=0.5, label="Nettoyé", color="#1D9E75")
        ax.set_title("Distribution Température moyenne (°C)")
        ax.set_xlabel("°C")
        ax.legend()

    # 3. Précipitations par région (après nettoyage)
    ax = axes[1, 0]
    if "precipitation_sum" in df_clean.columns and "region" in df_clean.columns:
        df_clean.groupby("region")["precipitation_sum"].mean().sort_values().plot(
            kind="barh", ax=ax, color="#378ADD"
        )
        ax.set_title("Précipitation moyenne par région (mm/j) — nettoyé")
        ax.set_xlabel("mm/jour")

    # 4. Observations par ville (complétude)
    ax = axes[1, 1]
    obs_par_ville = df_clean.groupby("city").size().sort_values()
    n_attendu = df_clean["time"].nunique()
    (obs_par_ville / n_attendu * 100).plot(kind="bar", ax=ax, color="#639922")
    ax.axhline(100, color="red", linestyle="--", linewidth=1, label="100% attendu")
    ax.set_title("Complétude par ville (% des jours couverts)")
    ax.set_ylabel("%")
    ax.tick_params(axis="x", rotation=90, labelsize=6)
    ax.legend()

    plt.tight_layout()
    plt.savefig("qualite_nettoyage.png", dpi=150, bbox_inches="tight")
    print("\nGraphique sauvegardé : qualite_nettoyage.png")
    plt.show()


# ═════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════

if __name__ == "__main__":

    print("Chargement du dataset...")
    df_brut = pd.read_csv(DATA_PATH, parse_dates=["time"])
    print(f"Dataset chargé : {df_brut.shape}")

    # Étape 1 — Audit
    rapport = audit_dataset(df_brut)

    # Étape 2 — Nettoyage
    df_clean = nettoyer_dataset(df_brut)

    # Visualisations
    visualiser_qualite(df_brut, df_clean)

    # Sauvegarde
    df_clean.to_csv(OUTPUT_PATH, index=False)
    print(f"\nDataset nettoyé sauvegardé : {OUTPUT_PATH}")
    print(f"Prêt pour l'étape 3 : récupération CAMS Copernicus !")