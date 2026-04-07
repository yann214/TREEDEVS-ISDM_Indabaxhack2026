# 🌍 TREEDEVS-ISDM — Surveillance de la Qualité de l'Air au Cameroun
### IndabaX Cameroon 2026

> Système de prédiction et de visualisation de l'Indice de Qualité de l'Air (IQA)  
> basé sur un modèle Random Forest entraîné sur des données réelles.

---

## 📁 Architecture du projet

```
AirCam/
│
├── APP/                              # Application web (dashboard)
│   ├── static/                       # Fichiers statiques frontend
│   │   ├── css/                      #   Feuilles de style
│   │   └── js/                       #   Scripts JavaScript (main.js, charts…)
│   │
│   ├── templates/                    # Templates HTML Flask
│   │   └── index.html                #   Page principale du dashboard
│   │
│   ├── app.py                        # Backend Flask — API REST + prédictions RF
│   ├── Dockerfile                    # Image Docker pour le déploiement
│   └── requirements.txt             # Dépendances Python de l'application
│
├── notebooks/                        # Travail de recherche & modélisation
│   ├── images/                       # Graphiques et figures générés
│   │
│   ├── 02_Modelisation_IndabaX_Cam…  # Notebook principal de modélisation RF
│   ├── CollecteDesDonneesCible_cams… # Collecte des données cibles (capteurs Cameroun)
│   ├── CollecteDesDonneesCible_open… # Collecte météo via API Open-Meteo
│   ├── Nettoyage_VariableCible.ipynb # Nettoyage et préparation de la variable IQA
│   ├── calcule_iqa.py                # Script de calcul de l'IQA global (PM2.5, O₃, NO₂)
│   └── script_nettoyage.py          # Pipeline de nettoyage des données brutes
│
├── README.md                         # Ce fichier
└── requirements.txt                 # Dépendances globales du projet
```

---

## 🔄 Pipeline de données

```
Capteurs / Open-Meteo
        │
        ▼
CollecteDesDonneesCible_*.ipynb   ← Collecte brute (IQA + météo)
        │
        ▼
script_nettoyage.py               ← Nettoyage, alignement, fusion
        │
        ▼
Nettoyage_VariableCible.ipynb     ← Préparation de la variable cible iqa_global
        │
        ▼
calcule_iqa.py                    ← Calcul IQA depuis PM2.5 / O₃ / NO₂
        │
        ▼
02_Modelisation_IndabaX_Cam…      ← Entraînement Random Forest, sélection features
        │
        ▼
APP/model/                        ← Artefacts exportés (.pkl)
        │
        ▼
APP/app.py  ──►  Dashboard AirCam (localhost:5004)
```

---

## 🚀 Lancement rapide

### 1. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2. Lancer le backend Flask

```bash
cd APP
python app.py
```

> Le dashboard est accessible à l'adresse : **http://localhost:5004**

### 3. Ou via Docker

```bash
cd APP
docker build -t aircam .
docker run -p 5004:5004 aircam
```

---

## 🧠 Modèle ML

| Paramètre        | Valeur                          |
|------------------|---------------------------------|
| Algorithme       | Random Forest Regressor         |
| Variable cible   | `iqa_global`                    |
| Features         | Météo + temporelles + lags IQA  |
| Source météo     | Open-Meteo (fallback temps réel)|
| Format export    | `.pkl` via joblib               |

---

## 🌐 Endpoints API principaux

| Endpoint          | Description                              |
|-------------------|------------------------------------------|
| `GET /dashboard`  | KPIs + prédictions toutes villes         |
| `GET /predict`    | Prédiction IQA pour une ville/date       |
| `GET /timeseries` | Série temporelle IQA (90–365 jours)      |
| `GET /alerts`     | Villes en alerte (IQA > 120)             |
| `GET /top-cities` | Top 5 villes les plus / moins polluées   |
| `GET /weather`    | Données météo courantes par ville        |
| `GET /regions-iqa`| IQA moyen par région                     |
| `GET /monthly-iqa`| IQA mensuel par ville et par année       |

---

## 🗺️ Couverture géographique

Le système couvre les principales villes camerounaises réparties sur les dix régions, avec des données météorologiques et de qualité de l'air horodatées par jour.

---

## 👥 Contexte

Projet développé pour **IndabaX Cameroon 2026**, dans le cadre de la valorisation de la data science appliquée aux enjeux environnementaux et de santé publique.

---

## 📄 Licence

Ce projet est à usage académique et de recherche dans le cadre d'IndabaX Cameroon 2026.
