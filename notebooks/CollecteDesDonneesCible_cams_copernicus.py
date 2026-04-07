"""
=============================================================
INDABAX CAMEROON 2026 — Semaine 1
Étape 3 (v5) : CAMS Global — colonnes exactes demandées
Colonnes ajoutées :
  pm25_mean, pm25_max, pm25_min, pm25_p95,
  o3_mean,   o3_max,   o3_min,   o3_p95,
  no2_mean,  no2_max,  no2_min,  no2_p95,
  qualite_pm25, alerte_pm25,
  qualite_o3,   alerte_o3,
  qualite_no2,  alerte_no2,
  indice_global,
  iqa_pm25, iqa_o3, iqa_no2,
  iqa_global, polluant_directeur, iqa_label, alerte_iqa
=============================================================
"""

import cdsapi
import netCDF4
import zipfile
import numpy as np
import pandas as pd
from pathlib import Path
from tqdm import tqdm
import time
import warnings
warnings.filterwarnings("ignore")

# ════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════

DATASET_CLEAN_PATH = "dataset_clean.csv"
OUTPUT_POL_PATH    = "polluants_cams.csv"
OUTPUT_FINAL_PATH  = "dataset_avec_polluants.csv"

BBOX       = [13.5, 7.5, 1.0, 17.0]
ANNEES     = list(range(2020, 2026))
MOIS       = [f"{m:02d}" for m in range(1, 13)]
DOSSIER_NC = Path("cams_global_nc")
DOSSIER_NC.mkdir(exist_ok=True)

MAX_RETRIES     = 1
PAUSE_ENTRE_REQ = 3
PAUSE_RETRY     = 1

POLLUANTS = {
    "particulate_matter_2.5um": {
        "col":          "pm25",
        "nc_candidats": ["pm2p5", "pm2_5", "PM2p5", "pm2p5_conc"],
    },
    "total_column_ozone": {
        "col":          "o3",
        "nc_candidats": ["gtco3", "tco3", "go3", "o3", "O3"],
    },
    "total_column_nitrogen_dioxide": {
        "col":          "no2",
        "nc_candidats": ["tcno2", "tcno2_strat", "no2", "NO2", "no2_conc"],
    },
}

# Breakpoints IQA (méthode EPA, interpolation linéaire)
BREAKPOINTS = {
    "pm25": [(0.0,  9.0,   0,  50),
             (9.1,  35.4,  51, 100),
             (35.5, 55.4,  101,150),
             (55.5, 125.4, 151,200),
             (125.5,225.4, 201,300),
             (225.5,500.0, 301,500)],
    "o3":   [(0,   54,   0,  50),
             (55,  124,  51, 100),
             (125, 164,  101,150),
             (165, 204,  151,200),
             (205, 404,  201,300),
             (405, 604,  301,500)],
    "no2":  [(0,   53,   0,  50),
             (54,  100,  51, 100),
             (101, 360,  101,150),
             (361, 649,  151,200),
             (650, 1249, 201,300),
             (1250,2049, 301,500)],
}

# Seuils OMS pour qualite_ et alerte_  (µg/m³)
SEUILS_OMS = {
    "pm25": [0, 15, 35, 55, 110, float("inf")],
    "o3":   [0, 50, 100,150, 200, float("inf")],
    "no2":  [0, 25, 50, 100, 200, float("inf")],
}
LABELS_OMS = ["Bonne","Modérée","Mauvaise","Très mauvaise","Dangereuse"]

IQA_LABELS = [(0,  50,  "Bonne"),
              (51, 100, "Modérée"),
              (101,150, "Mauvaise"),
              (151,200, "Très mauvaise"),
              (201,300, "Dangereuse"),
              (301,500, "Très dangereuse")]

# Ordre du pire au meilleur (pour indice_global)
ORDRE_OMS = {l: i for i, l in enumerate(LABELS_OMS)}


# ════════════════════════════════════════════════════════════
# UTILITAIRE — décompression ZIP → .nc
# ════════════════════════════════════════════════════════════

def dezipper_si_zip(fichier: Path) -> Path:
    if fichier.suffix == ".nc":
        with open(fichier, "rb") as f:
            magic = f.read(4)
        if magic == b"PK\x03\x04":
            zip_path = fichier.with_suffix(".zip")
            fichier.rename(zip_path)
            fichier = zip_path

    if fichier.suffix == ".zip":
        with zipfile.ZipFile(fichier, "r") as z:
            nc_files = [f for f in z.namelist() if f.endswith(".nc")]
            if not nc_files:
                raise ValueError(f"Pas de .nc dans {fichier.name}")
            nc_name   = nc_files[0]
            nc_target = fichier.parent / (fichier.stem + ".nc")
            if not nc_target.exists():
                z.extract(nc_name, fichier.parent)
                (fichier.parent / nc_name).rename(nc_target)
            fichier.unlink()
            return nc_target

    return fichier


def reparer_fichiers_existants():
    fichiers = list(DOSSIER_NC.glob("*.nc")) + list(DOSSIER_NC.glob("*.zip"))
    print(f"Vérification de {len(fichiers)} fichiers existants...")
    repares = 0
    for fichier in fichiers:
        try:
            with open(fichier, "rb") as f:
                magic = f.read(4)
            if magic == b"PK\x03\x04":
                dezipper_si_zip(fichier)
                repares += 1
        except Exception as e:
            print(f"  Erreur sur {fichier.name} : {e}")
    print(f"  {repares} fichier(s) réparé(s).")


# ════════════════════════════════════════════════════════════
# TÉLÉCHARGEMENT
# ════════════════════════════════════════════════════════════

def telecharger_cams():
    c = cdsapi.Client(retry_max=1, sleep_max=10,
                      wait_until_complete=True, quiet=False)

    requetes   = [(pol, a, m) for pol in POLLUANTS
                  for a in ANNEES for m in MOIS]
    deja_faits = {f.stem for f in DOSSIER_NC.glob("*.nc")}
    a_faire    = [(pol, a, m) for pol, a, m in requetes
                  if f"{POLLUANTS[pol]['col']}_{a}_{m}" not in deja_faits]

    print(f"Total : {len(requetes)} | Faits : {len(deja_faits)} | "
          f"Restants : {len(a_faire)}\n")

    if not a_faire:
        print("Tous les fichiers sont déjà téléchargés !")
        return

    echecs = []
    for pol_api, annee, mois in tqdm(a_faire, desc="Téléchargement CAMS"):
        col     = POLLUANTS[pol_api]["col"]
        fichier = DOSSIER_NC / f"{col}_{annee}_{mois}.nc"
        succes  = False

        for tentative in range(1, MAX_RETRIES + 1):
            try:
                c.retrieve(
                    "cams-global-reanalysis-eac4",
                    {
                        "variable": pol_api,
                        "date":     f"{annee}-{mois}-01/{annee}-{mois}-31",
                        "time":     ["00:00","03:00","06:00","09:00",
                                     "12:00","15:00","18:00","21:00"],
                        "format":   "netcdf",
                        "area":     BBOX,
                    },
                    str(fichier)
                )
                fichier = dezipper_si_zip(fichier)
                succes  = True
                time.sleep(PAUSE_ENTRE_REQ)
                break

            except Exception as e:
                msg = str(e)
                if "500" in msg or "Internal Server Error" in msg:
                    print(f"\n  [{col} {annee}-{mois}] Erreur 500 — "
                          f"attente {PAUSE_RETRY}s "
                          f"(tentative {tentative}/{MAX_RETRIES})...")
                    if fichier.exists():
                        fichier.unlink()
                    time.sleep(PAUSE_RETRY)
                elif "400" in msg or "404" in msg:
                    print(f"\n  [{col} {annee}-{mois}] Erreur param : {msg}")
                    break
                else:
                    print(f"\n  [{col} {annee}-{mois}] Erreur : {msg[:80]}")
                    time.sleep(10)

        if not succes:
            echecs.append(f"{col}_{annee}-{mois}")

    nc_count = len(list(DOSSIER_NC.glob("*.nc")))
    print(f"\nFichiers .nc présents : {nc_count} / {len(requetes)}")
    if echecs:
        print(f"Échecs ({len(echecs)}) — relancez le script.")


# ════════════════════════════════════════════════════════════
# INSPECTION
# ════════════════════════════════════════════════════════════

def inspecter_nc(fichier: Path):
    print(f"\nInspection : {fichier.name}")
    ds = netCDF4.Dataset(str(fichier))
    print("  Dimensions :", dict(ds.dimensions))
    print("  Variables  :")
    for nom, var in ds.variables.items():
        units = getattr(var, "units", "—")
        print(f"    {nom:35s} shape={str(var.shape):25s} units={units}")
    ds.close()


# ════════════════════════════════════════════════════════════
# EXTRACTION
# ════════════════════════════════════════════════════════════

def extraire_polluant(pol_api: str, villes_df: pd.DataFrame) -> pd.DataFrame:
    info      = POLLUANTS[pol_api]
    col       = info["col"]
    candidats = info["nc_candidats"]

    fichiers = sorted(DOSSIER_NC.glob(f"{col}_*.nc"))
    if not fichiers:
        print(f"  Aucun fichier .nc pour {col} — skippé.")
        return pd.DataFrame()

    print(f"\n  {col.upper()} : {len(fichiers)} fichiers")
    records     = []
    fichiers_ok = fichiers_err = 0

    for fichier in tqdm(fichiers, desc=f"  Extraction {col.upper()}"):
        try:
            ds       = netCDF4.Dataset(str(fichier))
            dims     = list(ds.dimensions.keys())
            dim_time = next((d for d in dims if "time" in d.lower()), None)

            if dim_time is None:
                print(f"\n    {fichier.name} — dimension time introuvable")
                print(f"    Dimensions : {dims}")
                ds.close(); fichiers_err += 1; continue

            lats  = ds.variables["latitude"][:]
            lons  = ds.variables["longitude"][:]
            temps = netCDF4.num2date(
                ds.variables[dim_time][:],
                ds.variables[dim_time].units,
                only_use_cftime_datetimes=False,
                only_use_python_datetimes=True
            )

            var_nc = next((v for v in candidats if v in ds.variables), None)
            if var_nc is None:
                print(f"\n    {fichier.name} — variable {col} introuvable")
                print(f"    Variables dispo : {list(ds.variables.keys())}")
                ds.close(); fichiers_err += 1; continue

            data    = ds.variables[var_nc][:]
            units   = getattr(ds.variables[var_nc], "units", "")
            facteur = 1e9 if "kg" in str(units).lower() else 1.0

            for _, ville in villes_df.iterrows():
                idx_lat = int(np.argmin(np.abs(lats - ville["latitude"])))
                idx_lon = int(np.argmin(np.abs(lons - ville["longitude"])))

                for t_idx, t in enumerate(temps):
                    val = float(data[t_idx, idx_lat, idx_lon])
                    if val > 1e10 or val < 0:
                        val = np.nan
                    elif not np.isnan(val):
                        val = round(val * facteur, 4)

                    records.append({
                        "city": ville["city"],
                        "time": pd.Timestamp(t.year, t.month, t.day),
                        f"{col}_h": val
                    })

            ds.close()
            fichiers_ok += 1

        except Exception as e:
            print(f"\n    ERREUR {fichier.name} : {e}")
            fichiers_err += 1

    print(f"  {fichiers_ok} OK | {fichiers_err} erreurs | "
          f"{len(records):,} records")

    if not records:
        print(f"  Aucun record pour {col} !")
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df_jour = (
        df.groupby(["city", "time"])[f"{col}_h"]
        .agg(**{
            f"{col}_mean": "mean",
            f"{col}_max":  "max",
            f"{col}_min":  "min",
            f"{col}_p95":  lambda x: x.quantile(0.95),
        })
        .reset_index()
    )
    for c in [f"{col}_mean", f"{col}_max", f"{col}_min", f"{col}_p95"]:
        df_jour[c] = df_jour[c].round(3)

    return df_jour


def extraire_tous_polluants(villes_df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 60)
    print("EXTRACTION TOUS POLLUANTS")
    print("=" * 60)

    resultats = []
    for pol_api in POLLUANTS:
        df_pol = extraire_polluant(pol_api, villes_df)
        if not df_pol.empty:
            resultats.append(df_pol)

    if not resultats:
        raise ValueError(
            "Aucun polluant extrait.\n"
            "→ Vérifiez que les fichiers .nc ne sont pas des ZIP."
        )

    df = resultats[0]
    for df_pol in resultats[1:]:
        df = df.merge(df_pol, on=["city", "time"], how="outer")

    return df.sort_values(["city", "time"]).reset_index(drop=True)


# ════════════════════════════════════════════════════════════
# CALCUL IQA + QUALITÉ OMS + INDICE GLOBAL
# Produit exactement les colonnes demandées dans l'ordre exact
# ════════════════════════════════════════════════════════════

def sous_indice(c: float, pol: str) -> float:
    """Interpolation linéaire EPA → sous-indice 0-500."""
    if pd.isna(c) or c < 0:
        return np.nan
    for c_low, c_high, i_low, i_high in BREAKPOINTS.get(pol, []):
        if c_low <= c <= c_high:
            return round(
                (i_high - i_low) / (c_high - c_low) * (c - c_low) + i_low, 1
            )
    return 500.0


def label_iqa(v: float) -> str:
    if pd.isna(v):
        return np.nan
    for lo, hi, lbl in IQA_LABELS:
        if lo <= v <= hi:
            return lbl
    return "Très dangereuse"


def ajouter_colonnes_polluants(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute dans l'ordre EXACT demandé :
    pm25_mean … no2_p95             (déjà présentes depuis extraction)
    qualite_pm25, alerte_pm25       (classification OMS)
    qualite_o3,   alerte_o3
    qualite_no2,  alerte_no2
    indice_global                   (pire qualité OMS parmi les 3)
    iqa_pm25, iqa_o3, iqa_no2      (sous-indices EPA 0-500)
    iqa_global                      (max des sous-indices)
    polluant_directeur              (polluant qui détermine iqa_global)
    iqa_label                       (label qualitatif de iqa_global)
    alerte_iqa                      (iqa_global > 100)
    """
    pols_presents = [p for p in ["pm25", "o3", "no2"]
                     if f"{p}_mean" in df.columns]

    # ── qualite_ et alerte_ (OMS) ────────────────────────────
    for pol in pols_presents:
        col_mean = f"{pol}_mean"
        df[f"qualite_{pol}"] = pd.cut(
            df[col_mean],
            bins=SEUILS_OMS[pol],
            labels=LABELS_OMS,
            right=True
        )
        # seuil d'alerte = dépasse "Modérée" → > 3e borne
        seuil_alerte = SEUILS_OMS[pol][2]
        df[f"alerte_{pol}"] = df[col_mean] > seuil_alerte

    # ── indice_global = pire qualité OMS parmi les 3 ─────────
    cols_qualite = [f"qualite_{p}" for p in pols_presents]

    def pire_qualite(row):
        vals = [str(row[c]) for c in cols_qualite
                if pd.notna(row[c]) and str(row[c]) != "nan"]
        if not vals:
            return np.nan
        return max(vals, key=lambda x: ORDRE_OMS.get(x, -1))

    df["indice_global"] = df.apply(pire_qualite, axis=1)

    # ── iqa_ (sous-indices EPA, interpolation linéaire) ───────
    for pol in pols_presents:
        df[f"iqa_{pol}"] = df[f"{pol}_mean"].apply(
            lambda c: sous_indice(c, pol)
        )

    # ── iqa_global = max des sous-indices ────────────────────
    cols_iqa = [f"iqa_{p}" for p in pols_presents]
    df["iqa_global"] = df[cols_iqa].max(axis=1, skipna=True).round(1)

    # ── polluant_directeur ────────────────────────────────────
    def directeur(row):
        vals = {p: row[f"iqa_{p}"] for p in pols_presents
                if not pd.isna(row[f"iqa_{p}"])}
        if not vals:
            return np.nan
        return max(vals, key=vals.get)

    df["polluant_directeur"] = df.apply(directeur, axis=1)

    # ── iqa_label ─────────────────────────────────────────────
    df["iqa_label"] = df["iqa_global"].apply(label_iqa)

    # ── alerte_iqa ────────────────────────────────────────────
    df["alerte_iqa"] = df["iqa_global"] > 100

    return df


# ════════════════════════════════════════════════════════════
# JOINTURE + RÉORDONNANCEMENT DES COLONNES
# ════════════════════════════════════════════════════════════

def joindre_et_ordonner(df_meteo: pd.DataFrame,
                         df_pol: pd.DataFrame) -> pd.DataFrame:

    df_meteo["time"] = pd.to_datetime(df_meteo["time"])
    df_pol["time"]   = pd.to_datetime(df_pol["time"])

    n  = len(df_meteo)
    df = df_meteo.merge(df_pol, on=["city", "time"], how="left")
    assert len(df) == n, "Erreur jointure !"

    taux = df["pm25_mean"].notna().sum() / n * 100
    print(f"Jointure OK — {taux:.1f}% lignes avec PM2.5")

    # Colonnes de polluants dans l'ordre exact demandé
    cols_pol = [
        "pm25_mean", "pm25_max", "pm25_min", "pm25_p95",
        "o3_mean",   "o3_max",   "o3_min",   "o3_p95",
        "no2_mean",  "no2_max",  "no2_min",  "no2_p95",
        "qualite_pm25", "alerte_pm25",
        "qualite_o3",   "alerte_o3",
        "qualite_no2",  "alerte_no2",
        "indice_global",
        "iqa_pm25", "iqa_o3", "iqa_no2",
        "iqa_global", "polluant_directeur", "iqa_label", "alerte_iqa",
    ]

    # Colonnes de base (météo) + colonnes polluants dans l'ordre
    cols_base = [c for c in df.columns if c not in cols_pol]
    cols_pol_presentes = [c for c in cols_pol if c in df.columns]
    df = df[cols_base + cols_pol_presentes]

    print(f"\nColonnes polluants ajoutées ({len(cols_pol_presentes)}) :")
    print(cols_pol_presentes)

    return df


# ════════════════════════════════════════════════════════════
# RAPPORT FINAL
# ════════════════════════════════════════════════════════════

def rapport(df: pd.DataFrame):
    print("\n" + "=" * 60)
    print("RAPPORT POLLUANTS PAR RÉGION")
    print("=" * 60)

    for pol in ["pm25", "o3", "no2"]:
        col = f"{pol}_mean"
        if col not in df.columns:
            continue
        print(f"\n{pol.upper()} (µg/m³) :")
        print(
            df.groupby("region")[col]
            .mean().round(2)
            .sort_values(ascending=False)
            .to_string()
        )

    print(f"\nDistribution indice_global (OMS) :")
    print(df["indice_global"].value_counts(dropna=False).to_string())

    print(f"\nDistribution iqa_label (EPA) :")
    print(df["iqa_label"].value_counts(dropna=False).to_string())

    print(f"\nPolluant directeur (fréquence) :")
    print(df["polluant_directeur"].value_counts(dropna=False).to_string())


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("Chargement dataset nettoyé...")
    df_meteo = pd.read_csv(DATASET_CLEAN_PATH, parse_dates=["time"])
    df_meteo = df_meteo.dropna(subset=["city", "latitude", "longitude"])
    df_meteo["city"] = df_meteo["city"].str.strip().str.title()
    villes_df = (df_meteo[["city", "latitude", "longitude"]]
                 .drop_duplicates("city").reset_index(drop=True))
    print(f"{df_meteo.shape[0]:,} lignes | {len(villes_df)} villes\n")

    # Réparer les ZIP existants
    reparer_fichiers_existants()

    # Télécharger les fichiers manquants
    telecharger_cams()

    # Inspecter le premier fichier
    premiers = sorted(DOSSIER_NC.glob("*.nc"))
    if premiers:
        inspecter_nc(premiers[0])

    # Extraction (avec cache)
    cache = Path(OUTPUT_POL_PATH)
    if cache.exists():
        print(f"\nCache trouvé : {cache}")
        df_pol = pd.read_csv(cache, parse_dates=["time"])
    else:
        df_pol = extraire_tous_polluants(villes_df)
        df_pol.to_csv(cache, index=False)
        print(f"Polluants sauvegardés : {cache}")

    # Ajout de toutes les colonnes dans l'ordre exact
    print("\nCalcul des indicateurs (OMS + IQA EPA)...")
    df_pol = ajouter_colonnes_polluants(df_pol)

    # Jointure + réordonnancement
    df_final = joindre_et_ordonner(df_meteo, df_pol)

    # Rapport
    rapport(df_final)

    # Sauvegarde
    df_final.to_csv(OUTPUT_FINAL_PATH, index=False)
    print(f"\nDataset final : {OUTPUT_FINAL_PATH} — {df_final.shape}")
    print("Prêt pour l'étape 4 : Feature Engineering !")