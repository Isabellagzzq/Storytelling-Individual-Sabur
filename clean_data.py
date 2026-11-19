# clean_data.py
# Loads the INEGI RAIAVL monthly sales files (2016-2026), cleans them and saves
# two clean files that the Streamlit app reads.
#
# How to run (from the project folder):  python clean_data.py

from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------
# 1. Paths
# ---------------------------------------------------------------
BASE = Path(__file__).parent
RAW_DIR = BASE / "data" / "raw"      # original INEGI files (not edited by hand)
CLEAN_DIR = BASE / "data" / "clean"  # where the clean files are saved
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------
# 2. Load the raw files
# ---------------------------------------------------------------
# One CSV per year. We read all of them and stack them in one table.
files = sorted(RAW_DIR.glob("raiavl_venta_mensual_tr_cifra_*.csv"))
raw = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

# Country catalog (ID -> country name)
countries = pd.read_csv(RAW_DIR / "tc_pais_origen.csv")

print(f"Files loaded: {len(files)} | Raw rows: {len(raw):,} | Raw units: {raw['UNI_VEH'].sum():,}")

# ---------------------------------------------------------------
# 3. Rename columns to English names that are easier to use
# ---------------------------------------------------------------
df = raw.rename(
    columns={
        "ANIO": "year",
        "ID_MES": "month",
        "MARCA": "brand_original",
        "MODELO": "model",
        "TIPO": "vehicle_type",
        "SEGMENTO": "segment",
        "ORIGEN": "origin",
        "ID_PAIS_ORIGEN": "country_id",
        "UNI_VEH": "units",
        "ESTATUS": "status",
    }
)

# Columns that are the same in every row (project name, coverage) are not needed
df = df.drop(columns=["PROD_EST", "COBERTURA"])

# ---------------------------------------------------------------
# 4. Build a proper monthly date (first day of each month)
# ---------------------------------------------------------------
df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"].astype(int), day=1))

# ---------------------------------------------------------------
# 5. Status of the figures (definitive, revised or preliminary)
# ---------------------------------------------------------------
# We translate the INEGI labels so the app can show them in English
status_map = {
    "Cifras Definitivas": "Definitive",
    "Cifras Revisadas": "Revised",
    "Cifras Preliminares": "Preliminary",
}
df["status"] = df["status"].map(status_map)

# ---------------------------------------------------------------
# 6. Harmonize brands
# ---------------------------------------------------------------
# Some brand names change over time or belong to the same group.
# - Chrysler and Fiat are reported separately but both are Stellantis
#   (the Chrysler rows contain Jeep, RAM and Dodge models).
# - JETOUR (until Feb 2025) and Jetour Soueast (from Mar 2025) are the same brand
#   renamed (same models, for example Dashing and T2, appear under both names).
# - The others only fix capital letters or the "Motor" suffix.
brand_map = {
    "Chrysler": "Stellantis",
    "Fiat": "Stellantis",
    "JETOUR": "Jetour",
    "Jetour Soueast": "Jetour",
    "Ford Motor": "Ford",
    "MG Motor": "MG",
    "KIA": "Kia",
    "Mini": "MINI",
    "Isuzu": "ISUZU",
}
df["brand"] = df["brand_original"].str.strip().replace(brand_map)

# Model names: remove extra spaces and use capital letters (the file mixes both)
df["model"] = df["model"].str.strip().str.upper()

# ---------------------------------------------------------------
# 7. Add the country name of the vehicle origin
# ---------------------------------------------------------------
# For NACIONAL vehicles the country is always Mexico (id 1).
df = df.merge(
    countries.rename(columns={"DESC_PAIS_ORIGEN": "origin_country"}),
    left_on="country_id",
    right_on="ID_PAIS_ORIGEN",
    how="left",
).drop(columns=["ID_PAIS_ORIGEN"])

# Spanish labels to English
df["origin"] = df["origin"].map({"NACIONAL": "Made in Mexico", "IMPORTADO": "Imported"})
df["vehicle_type"] = df["vehicle_type"].map({"Automóviles": "Cars", "Camiones ligeros": "Light trucks"})
df["segment"] = df["segment"].replace(
    {
        "Compactos": "Compacts",
        "De Lujo": "Luxury",
        "Deportivos": "Sports",
        "Minivans": "Minivans",
        "Pick Ups": "Pick-ups",
        "SUV's": "SUVs",
        "Subcompactos": "Subcompacts",
    }
)
# Country names to English (only the countries that appear in the data)
df["origin_country"] = df["origin_country"].replace(
    {
        "Estados Unidos": "United States",
        "Japón": "Japan",
        "Alemania": "Germany",
        "Corea del Sur": "South Korea",
        "Brasil": "Brazil",
        "Tailandia": "Thailand",
        "España": "Spain",
        "Canadá": "Canada",
        "México": "Mexico",
        "Reino Unido": "United Kingdom",
        "Bélgica": "Belgium",
        "Eslovaquia": "Slovakia",
        "Francia": "France",
        "Hungría": "Hungary",
        "Italia": "Italy",
        "No Especificado": "Not specified",
        "Países Bajos": "Netherlands",
        "Polonia": "Poland",
        "República Checa": "Czech Republic",
        "Suecia": "Sweden",
        "Turquía": "Turkey",
    }
)

# ---------------------------------------------------------------
# 8. Brand coverage table (which months each brand appears in the registry)
# ---------------------------------------------------------------
# The registry is built from what the companies report, so brands enter and leave.
# This table is used in the app to warn the user about coverage.
reported = df[df["units"] > 0]

coverage = (
    reported.groupby("brand")
    .agg(
        first_month=("date", "min"),
        last_month=("date", "max"),
        months_reported=("date", "nunique"),
        total_units=("units", "sum"),
    )
    .reset_index()
)
# A brand is "stable" if it is in the registry from the first to the last month
# of the period (it never entered or left). Used to compare the market without
# the effect of brands that joined or left the registry.
coverage["stable_brand"] = (coverage["first_month"] == df["date"].min()) & (
    coverage["last_month"] == df["date"].max()
)

# Add the stable flag to the main table too
df = df.merge(coverage[["brand", "stable_brand"]], on="brand", how="left")

# ---------------------------------------------------------------
# 9. Rows with zero units and negative values
# ---------------------------------------------------------------
# Zero rows add no information (they do not change any total), so we drop them.
# Negative values (24 rows) are corrections reported by the companies; we KEEP them
# because they are part of the net sales.
zero_rows = (df["units"] == 0).sum()
df = df[df["units"] != 0]
print(f"Zero-unit rows dropped: {zero_rows:,} | Negative rows kept: {(df['units'] < 0).sum()}")

# ---------------------------------------------------------------
# 10. Checks: cleaning should not change the total number of units
# ---------------------------------------------------------------
assert df["units"].sum() == raw["UNI_VEH"].sum(), "Total units changed after cleaning!"
assert df["origin_country"].notna().all(), "Some country ids were not found in the catalog"
assert df["status"].notna().all(), "Unknown status label"

# ---------------------------------------------------------------
# 11. Save the clean files
# ---------------------------------------------------------------
columns = [
    "date", "year", "month", "brand", "brand_original", "model", "vehicle_type",
    "segment", "origin", "origin_country", "units", "status", "stable_brand",
]
df = df[columns].sort_values(["date", "brand", "model"]).reset_index(drop=True)

df.to_csv(CLEAN_DIR / "sales_clean.csv", index=False)
coverage.sort_values("first_month").to_csv(CLEAN_DIR / "brand_coverage.csv", index=False)

print(f"Clean rows: {len(df):,} | Clean units: {df['units'].sum():,}")
print(f"Period: {df['date'].min():%b %Y} to {df['date'].max():%b %Y}")
print("Saved: data/clean/sales_clean.csv and data/clean/brand_coverage.csv")
