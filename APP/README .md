title: TREEDEVS ISMD
emoji: 🐨
colorFrom: purple
colorTo: yellow
sdk: docker
pinned: false
license: apache-2.0



# TREEDEVS-ISDM  — Plateforme IA Pollution
> **Hackathon IndabaX Cameroun** · Prédiction de la Qualité de l'Air par RandomForest

---

## 📁 Structure du projet

```
pollution-platform/
├── frontend/
│   └── index.html                          ← Dashboard complet (HTML/CSS/JS)
├── backend/
│   ├── app.py                              ← API Flask production
│   ├── requirements.txt
│   ├── models/                             ← ⚠️ Placez vos fichiers .pkl ici
│   │   ├── Random Forest_best_model.pkl
│   │   ├── Random Forest_features_list.pkl
│   │   ├── Random Forest_encoder_city.pkl
│   │   ├── Random Forest_encoder_region.pkl
│   │   └── Random Forest_encoder_saison.pkl
│   └── data/                               ← ⚠️ Placez votre CSV ici
│       └── data.csv
└── README.md
```

---

## 🚀 Démarrage rapide

### 1. Préparer les fichiers

```bash
# Copiez votre modèle et encodeurs
cp Random\ Forest_best_model.pkl       backend/models/
cp Random\ Forest_features_list.pkl    backend/models/
cp Random\ Forest_encoder_city.pkl     backend/models/
cp Random\ Forest_encoder_region.pkl   backend/models/
cp Random\ Forest_encoder_saison.pkl   backend/models/

# Renommez votre CSV en data.csv
cp votre_fichier.csv backend/data/data.csv
```

### 2. Installer les dépendances

```bash
cd backend
pip install -r requirements.txt
```

### 3. Lancer le backend Flask

```bash
python app.py
```

Au démarrage, vous verrez :

```
═══════════════════════════════════════════════════════
  🌍  TREEDEVS-ISDM  API — Production  v2.0
═══════════════════════════════════════════════════════
  Modèle   : ✅ chargé
  Données  : ✅ 87240 lignes
  Villes   : Bafoussam, Bamenda, Bertoua, Douala, Ebolowa...
  Features : 40
───────────────────────────────────────────────────────
  GET  /predict?city=Douala
  GET  /risk-score
  GET  /alerts
  GET  /timeseries?city=Douala&days=90&predicted=true
  GET  /dashboard
  POST /reload-data
═══════════════════════════════════════════════════════
```

### 4. Ouvrir le dashboard

Ouvrez `localhost:5004/` dans votre navigateur.

> Le dashboard détecte automatiquement si l'API Flask est active.
> Un indicateur vert/rouge dans la sidebar confirme la connexion.

---

## 📊 Colonnes du CSV utilisées

| Colonne | Rôle |
|---------|------|
| `time` | Date (parse_dates) |
| `city` | Nom de la ville → encodé via `encoder_city.pkl` |
| `region` | Région → encodé via `encoder_region.pkl` |
| `saison` | Saison camerounaise → encodé via `encoder_saison.pkl` |
| `iqa_global` | **Target** · utilisée pour calculer les lags et rolling |
| `pm25_mean`, `o3_mean`, `no2_mean` | Polluants affichés sur le dashboard |
| `latitude`, `longitude` | Coordonnées pour la carte |
| `day_of_year`, `week_of_year`, `year` | Base des features cycliques |
| Toutes les colonnes météo | Passées directement au modèle |

> ⚠️ Les colonnes `alerte_*` du CSV sont **ignorées**.
> Les alertes sont **recalculées** selon les seuils OMS/OMM (voir ci-dessous).

---

## ⚙️ Features calculées automatiquement par l'API

Le backend recalcule à la volée toutes les features dérivées à partir du CSV brut :

| Feature | Calcul |
|---------|--------|
| `city_enc` | `encoder_city.pkl.transform(city)` |
| `region_enc` | `encoder_region.pkl.transform(region)` |
| `saison_enc` | `encoder_saison.pkl.transform(saison)` |
| `doy_sin / doy_cos` | `sin/cos(2π × day_of_year / 365)` |
| `woy_sin / woy_cos` | `sin/cos(2π × week_of_year / 52)` |
| `iqa_global_lag_1/2/3/7/14/30` | `.shift(n)` par ville |
| `iqa_global_roll_7` | `.rolling(7).mean()` par ville |
| `iqa_global_roll_30` | `.rolling(30).mean()` par ville |
| `iqa_global_roll_std7` | `.rolling(7).std()` par ville |

---

## 🚨 Seuils d'alerte OMS/OMM

Les alertes sont recalculées en temps réel. Les colonnes `alerte_*` du CSV sont ignorées.

| Polluant | MODÉRÉE | ÉLEVÉE | CRITIQUE |
|----------|---------|--------|----------|
| **PM2.5** (µg/m³) | > 15 | > 45 | > 75 |
| **O₃** (µg/m³) | > 100 | > 120 | > 180 |
| **NO₂** (µg/m³) | > 25 | > 40 | > 200 |

| IQA global | Niveau |
|------------|--------|
| 0 – 50 | 🟢 Bonne |
| 51 – 100 | 🟡 Modérée |
| 101 – 150 | 🟠 Mauvaise (groupes sensibles) |
| 151 – 200 | 🔴 Mauvaise |
| 201 – 300 | 🟣 Très mauvaise |
| > 300 | ⚫ Dangereuse |

---

## 🌐 API Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/` | Statut de l'API, liste des villes, endpoints |
| `GET` | `/predict?city=Douala` | Prédiction RF pour une ville |
| `GET` | `/predict?city=Douala&date=2024-06-15` | Prédiction à une date précise |
| `POST` | `/predict` | Prédiction avec surcharge de features météo |
| `GET` | `/risk-score` | Score risque (0–100) pour toutes les villes |
| `GET` | `/alerts` | Alertes actives (seuils OMS recalculés) |
| `GET` | `/cities` | Liste des villes + métadonnées CSV |
| `GET` | `/timeseries?city=Douala&days=90` | Série temporelle réelle |
| `GET` | `/timeseries?city=Douala&days=90&predicted=true` | + prédiction RF point par point |
| `GET` | `/dashboard` | Tout : summary, prédictions, feature importances, métriques |
| `POST` | `/reload-data` | Recharge le CSV sans redémarrer Flask |

### Exemple de réponse `/predict`

```json
{
  "city": "Douala",
  "date": "2024-06-15",
  "region": "Littoral",
  "iqa_global": 87.4,
  "pm25": 36.7,
  "o3": 54.2,
  "no2": 18.1,
  "risk_score": 29.1,
  "level": "Modérée",
  "color": "#ffd32a",
  "recommendation": "✅ Qualité d'air acceptable...",
  "alerts": {
    "pm25": { "niveau": "MODÉRÉE", "valeur": 36.7, "seuil": 15, "msg": "PM2.5 légèrement élevé" }
  },
  "feature_contributions": {
    "iqa_global_lag_1": 0.284,
    "iqa_global_roll_7": 0.182,
    "wind_speed_10m_max": 0.141
  },
  "source": "csv",
  "model": "RandomForest"
}
```

---

## 🧠 Modules du Dashboard

| Module | Source des données |
|--------|--------------------|
| 🗺️ **Carte Interactive** | `/risk-score` → marqueurs colorés par IQA réel |
| 📈 **Analyse Temporelle** | `/timeseries?predicted=true` → IQA réel + courbe RF |
| 🔁 **Distribution saisonnière** | `/timeseries?days=365` → groupé par colonne `saison` |
| 🆚 **Comparaison villes** | `/risk-score` → barres IQA actuelles |
| 🧠 **Feature Importance** | `/dashboard` → `feature_importances_` du RandomForest |
| 📉 **Scatter réel/prédit** | `/timeseries?predicted=true` → points vrais vs RF |
| ⚡ **SHAP par ville** | `/predict` → `feature_contributions` normalisées |
| ⚡ **Prédiction** | `POST /predict` → RandomForest avec features exactes |
| 🚨 **Alertes** | `/alerts` → seuils OMS/OMM recalculés + détail polluants |

---

## 🤖 Modèle RandomForest

- **Fichier** : `Random Forest_best_model.pkl`
- **Features** : 39 variables (météo + temporelles + lags + encodages)
- **Target** : `iqa_global`
- **Métriques** : RMSE = 12.4 · MAE = 9.1 · R² = 0.87
- **Chargement** : `joblib.load()`

### Features du modèle (ordre exact)

```python
['weather_code', 'temperature_2m_max', 'temperature_2m_min', 'temperature_2m_mean',
 'apparent_temperature_max', 'apparent_temperature_min', 'apparent_temperature_mean',
 'daylight_duration', 'sunshine_duration', 'precipitation_sum', 'rain_sum', 'snowfall_sum',
 'precipitation_hours', 'wind_speed_10m_max', 'wind_gusts_10m_max',
 'wind_direction_10m_dominant', 'shortwave_radiation_sum', 'et0_fao_evapotranspiration',
 'latitude', 'longitude', 'year', 'day_of_year', 'week_of_year',
 'city_enc', 'region_enc', 'saison_enc',
 'doy_sin', 'doy_cos', 'woy_sin', 'woy_cos',
 'iqa_global_lag_1', 'iqa_global_lag_2', 'iqa_global_lag_3',
 'iqa_global_lag_7', 'iqa_global_lag_14', 'iqa_global_lag_30',
 'iqa_global_roll_7', 'iqa_global_roll_30', 'iqa_global_roll_std7']
```

---

## 🎯 Cas d'usage

| Utilisateur | Usage |
|-------------|-------|
| 🏥 **Ministère de la Santé** | Identifier les zones critiques · Déclencher des alertes sanitaires |
| 🌍 **ONG Environnementales** | Suivre les tendances · Produire des rapports basés sur des données réelles |
| 🏙️ **Collectivités locales** | Planifier des interventions ciblées par ville et par saison |
| 👨‍👩‍👧 **Population** | Recevoir des recommandations simples et compréhensibles |

---

## 🔧 Dépannage

| Problème | Solution |
|----------|----------|
| `❌ Modèle absent` | Vérifiez que les `.pkl` sont dans `backend/models/` avec les noms exacts |
| `❌ CSV absent` | Vérifiez que votre fichier est renommé `data.csv` dans `backend/data/` |
| Dashboard affiche `API hors ligne` | Lancez `python app.py` et vérifiez le port 5000 |
| Encodeur échoue au démarrage | Vérifiez que les valeurs du CSV correspondent aux valeurs vues à l'entraînement |
| Recharger le CSV sans redémarrer | `POST http://localhost:5000/reload-data` |

---

*TREEDEVS-ISDM · Hackathon IndabaX Cameroun*
