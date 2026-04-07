"""
=============================================================
INDABAX CAMEROON 2026 — Calcul IQA standard (méthode EPA)
Formule : interpolation linéaire par plage de concentration
IQA = max(I_O3, I_PM25, I_NO2, ...)  — polluant directeur
=============================================================
"""

import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════
# GRILLES DE BREAKPOINTS PAR POLLUANT
# Chaque ligne : (C_low, C_high, I_low, I_high, label)
# ════════════════════════════════════════════════════════════

BREAKPOINTS = {

    # PM2.5 µg/m³ — moyenne 24h (EPA + OMS 2021)
    "pm25": [
        (0.0,   9.0,    0,  50,  "Bonne"),
        (9.1,  35.4,   51, 100,  "Modérée"),
        (35.5,  55.4,  101, 150,  "Mauvaise"),
        (55.5, 125.4,  151, 200,  "Très mauvaise"),
        (125.5, 225.4, 201, 300,  "Dangereuse"),
        (225.5, 500.0, 301, 500,  "Très dangereuse"),
    ],

    # O3 µg/m³ — moyenne 8h  (1 ppb ≈ 2.0 µg/m³)
    "o3": [
        (0,    54,    0,  50,  "Bonne"),
        (55,  124,   51, 100,  "Modérée"),
        (125, 164,  101, 150,  "Mauvaise"),
        (165, 204,  151, 200,  "Très mauvaise"),
        (205, 404,  201, 300,  "Dangereuse"),
        (405, 604,  301, 500,  "Très dangereuse"),
    ],

    # NO2 µg/m³ — moyenne 1h  (1 ppb ≈ 1.88 µg/m³)
    "no2": [
        (0,    53,    0,  50,  "Bonne"),
        (54,  100,   51, 100,  "Modérée"),
        (101, 360,  101, 150,  "Mauvaise"),
        (361, 649,  151, 200,  "Très mauvaise"),
        (650, 1249, 201, 300,  "Dangereuse"),
        (1250, 2049, 301, 500, "Très dangereuse"),
    ],
}

# Correspondance IQA → label officiel
IQA_LABELS = [
    (0,   50,  "Bonne"),
    (51,  100, "Modérée"),
    (101, 150, "Mauvaise"),
    (151, 200, "Très mauvaise"),
    (201, 300, "Dangereuse"),
    (301, 500, "Très dangereuse"),
]


# ════════════════════════════════════════════════════════════
# CALCUL SOUS-INDICE — interpolation linéaire
# ════════════════════════════════════════════════════════════

def sous_indice(concentration: float, polluant: str) -> float:
    """
    Calcule le sous-indice I_p pour un polluant donné.
    Formule :
        I_p = (I_high - I_low) / (C_high - C_low) * (C_p - C_low) + I_low

    Retourne NaN si concentration hors plage ou manquante.
    """
    if pd.isna(concentration) or concentration < 0:
        return np.nan

    grille = BREAKPOINTS.get(polluant)
    if grille is None:
        return np.nan

    for c_low, c_high, i_low, i_high, _ in grille:
        if c_low <= concentration <= c_high:
            # Interpolation linéaire
            ip = (i_high - i_low) / (c_high - c_low) * \
                 (concentration - c_low) + i_low
            return round(ip, 1)

    # Concentration au-dessus de la dernière borne → valeur max
    return 500.0


def label_iqa(iqa: float) -> str:
    """Retourne le label qualitatif pour un score IQA donné."""
    if pd.isna(iqa):
        return np.nan
    for i_low, i_high, label in IQA_LABELS:
        if i_low <= iqa <= i_high:
            return label
    return "Très dangereuse"


# ════════════════════════════════════════════════════════════
# APPLICATION SUR UN DATAFRAME
# ════════════════════════════════════════════════════════════

def calculer_iqa(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute les colonnes IQA au DataFrame :
      - iqa_pm25, iqa_o3, iqa_no2       : sous-indices (0-500)
      - iqa_global                        : max des sous-indices
      - iqa_label                         : label qualitatif
      - polluant_directeur                : polluant qui détermine l'IQA
    """
    df = df.copy()

    polluants_dispo = [p for p in BREAKPOINTS if f"{p}_mean" in df.columns]

    if not polluants_dispo:
        raise ValueError(
            "Aucune colonne de polluant trouvée. "
            "Attendu : pm25_mean, o3_mean, no2_mean"
        )

    print(f"Polluants détectés : {polluants_dispo}")

    # ── Calcul des sous-indices ──────────────────────────────
    for pol in polluants_dispo:
        col_conc  = f"{pol}_mean"
        col_iqa   = f"iqa_{pol}"
        df[col_iqa] = df[col_conc].apply(
            lambda c: sous_indice(c, pol)
        )
        n_ok = df[col_iqa].notna().sum()
        print(f"  iqa_{pol:5s} : {n_ok:,} valeurs calculées "
              f"| moyenne = {df[col_iqa].mean():.1f}")

    # ── IQA global = max des sous-indices ───────────────────
    cols_iqa = [f"iqa_{p}" for p in polluants_dispo]
    df["iqa_global"] = df[cols_iqa].max(axis=1, skipna=True)

    # ── Polluant directeur ───────────────────────────────────
    def trouver_directeur(row):
        vals = {p: row[f"iqa_{p}"] for p in polluants_dispo
                if not pd.isna(row[f"iqa_{p}"])}
        if not vals:
            return np.nan
        return max(vals, key=vals.get)

    df["polluant_directeur"] = df.apply(trouver_directeur, axis=1)

    # ── Label qualitatif ─────────────────────────────────────
    df["iqa_label"] = df["iqa_global"].apply(label_iqa)

    # ── Alerte binaire ───────────────────────────────────────
    df["alerte_iqa"] = df["iqa_global"] > 100   # > Modéré = alerte

    # ── Rapport ─────────────────────────────────────────────
    print(f"\nIQA global — statistiques :")
    print(df["iqa_global"].describe().round(1).to_string())

    print(f"\nDistribution IQA (labels) :")
    print(df["iqa_label"].value_counts(dropna=False).to_string())

    print(f"\nPolluant directeur (fréquence) :")
    print(df["polluant_directeur"].value_counts(dropna=False).to_string())

    if "region" in df.columns:
        print(f"\nIQA moyen par région :")
        print(
            df.groupby("region")["iqa_global"]
            .mean().round(1)
            .sort_values(ascending=False)
            .to_string()
        )

    return df


# ════════════════════════════════════════════════════════════
# MAIN — intégration dans le pipeline
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    INPUT_PATH  = "dataset_avec_polluants_openmeteo.csv"
    OUTPUT_PATH = "dataset_final_iqa.csv"

    print("Chargement...")
    df = pd.read_csv(INPUT_PATH, parse_dates=["time"])
    print(f"Shape : {df.shape}")

    print("\nCalcul IQA standard (méthode EPA)...")
    df = calculer_iqa(df)

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSauvegardé : {OUTPUT_PATH}")
    print(f"Shape final : {df.shape}")

    # Aperçu
    cols_affich = ["city", "time", "pm25_mean", "o3_mean", "no2_mean",
                   "iqa_pm25", "iqa_o3", "iqa_no2",
                   "iqa_global", "iqa_label", "polluant_directeur"]
    cols_affich = [c for c in cols_affich if c in df.columns]
    print(f"\nAperçu (5 lignes) :")
    print(df[cols_affich].dropna(subset=["iqa_global"]).head(5).to_string(index=False))