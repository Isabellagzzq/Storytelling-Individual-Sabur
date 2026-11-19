# Is Mexico worth entering in 2027? Light-vehicle market dashboard

Individual assignment: "The Emerging Stories of Mexico's Automotive Industry".

## Role, stakeholder and decision
- **Role:** market-entry analyst on the strategy team of a brand that does not sell in Mexico yet.
- **Stakeholder:** the team deciding whether to launch in Mexico in 2027.
- **Decision:** go or no-go, which vehicle to lead with, and how fast to expect to grow.

## Data
INEGI, *Registro Administrativo de la Industria Automotriz de Vehículos Ligeros* (RAIAVL), **monthly retail sales**, January 2016 to
October 2026 (revised figures; file modified 2026-11-09). https://www.inegi.org.mx/datosprimarios/iavl/

Only the sales table is used. The period starts in 2016 to have four years before COVID-19 as a baseline, plus the 2020 shock,
the 2021-2022 chip shortage and the arrival of new brands.

## Project structure
```
app.py                  Streamlit dashboard (one page: timeline, 3 acts, decision)
clean_data.py           Loads the raw INEGI files and writes the clean data
requirements.txt
.streamlit/config.toml  Theme (the navy background and white cards are set in app.py)
data/raw/               Original INEGI files (not edited by hand)
data/clean/             Output of clean_data.py (read by the app)
```

## Run it
```
pip install -r requirements.txt
python clean_data.py        # optional: the clean files are already in data/clean/
streamlit run app.py
```

## What clean_data.py does
- Loads the 11 yearly CSV files and the country catalog.
- Builds a monthly date from year and month; keeps the status of each figure (definitive / revised).
- Harmonizes brands: Chrysler and Fiat into Stellantis; JETOUR and Jetour Soueast as one brand (same models, renamed in Mar 2025).
- Drops 12,858 rows with zero units (no effect on totals); keeps 24 negative rows (corrections reported by the companies).
- Merges model-name variants into one name (model_family): for example BEAT and BEAT 4 PTAS., or AVEO-, AVEO and AVEO HB.
- Writes a brand coverage table (first and last month each brand appears in the registry).
- Checks that total units are the same before and after cleaning (14,638,243).

## Data limits (also shown in the dashboard)
- BYD does not report to INEGI; newcomer volumes are a lower bound.
- Chirey and Omoda stop appearing after Mar 2025; MOTORNATION after Jun 2026; Geely, GAC and Foton appear from Jan 2024.
- Figures from Nov 2023 are "revised" and can change.
- Brand nationality is not in the data; the Chinese-brand classification in the app is our own.
- No prices, margins, dealer or state data.
- Event dates on the charts (COVID-19, chip shortage, January 2026 tariffs) come from press and trade reports listed in the app, not from the official gazette.

## Deploy (Streamlit Community Cloud)
Push this folder to a public GitHub repository, then create the app at https://share.streamlit.io with `app.py` as the main file.

## Story structure
Three periods, compared January to October of each year (2026 has ten months): 2016-2019 (shrinking market), 2019-2023 (COVID-19 shock and recovery),
2023-2026 (new brands and growth). Each act has the same layout: a big number, who gained and lost share, and the best-selling cars colored by where they were built.
The last block is the decision: which vehicle, how fast, and three recommendations. Filters (years, vehicle group, origin) change the charts;
titles and the decision block always describe the whole market. Vehicle groups: Cars = subcompact + compact; Other = luxury, sports, minivans.
