# app.py
# Streamlit dashboard: Mexico's light-vehicle market 2016-2026 (INEGI RAIAVL, monthly sales).
# Built for an 8-minute talk: one page, three acts (2016-2019, 2019-2023, 2023-2026) and a decision.
# Role: market-entry analyst for a brand deciding whether to enter Mexico in 2027.
#
# Run with:  streamlit run app.py
# The clean data comes from clean_data.py (data/clean/*.csv).

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Should we enter Mexico in 2027?", layout="wide")

DATA_DIR = Path(__file__).parent / "data" / "clean"

# ---------------------------------------------------------------
# 1. Colors. The same color always means the same thing:
#    blue = what we want you to look at, orange = built in China / Chinese brand,
#    gray = everything else. Green appears only as the "target" highlight.
# ---------------------------------------------------------------
BLUE, ORANGE, GREEN = "#2a78d6", "#eb6834", "#1baf7a"
GRAY, LIGHT, DARK = "#9aa3af", "#d3d8e0", "#5b6573"
INK, INK2, MUTED = "#0b1b33", "#4a5568", "#8a93a3"
GRID, AXIS, RED = "#e6e9ef", "#c9ced8", "#d6453f"
SURFACE = "#ffffff"
TARGET_FILL = "rgba(27,175,122,0.16)"   # translucent green used to circle the target

# ---------------------------------------------------------------
# 2. Simple vehicle groups (the 7 INEGI segments are too many to explain in 8 minutes)
# ---------------------------------------------------------------
GROUP_OF = {
    "SUVs": "SUVs", "Pick-ups": "Pick-ups",
    "Subcompacts": "Cars", "Compacts": "Cars",
    "Luxury": "Other", "Sports": "Other", "Minivans": "Other",
}
GROUPS = ["SUVs", "Pick-ups", "Cars", "Other"]
GROUP_COLORS = {"SUVs": BLUE, "Cars": DARK, "Pick-ups": GRAY, "Other": "#c1c7d1"}

# The three periods of the story. Boundaries are October, because we compare January-October
# of every year (2026 only has ten months). Dates are used for the monthly chart.
ACTS = [(2016, 2019), (2019, 2023), (2023, 2026)]
ACT_BANDS = [("2016-01-01", "2019-10-01"), ("2019-10-01", "2023-10-01"), ("2023-10-01", "2026-10-01")]
BAND_FILL = ["rgba(42,120,214,0.06)", "rgba(42,120,214,0.15)", "rgba(42,120,214,0.06)"]
MILESTONES = [2016, 2019, 2023, 2026]

# Events (sources are press and trade reports; see "Sources and method" at the bottom)
COVID = ("COVID-19 shutdown", "2020-03-30", "2020-04-30")
CHIPS = ("Chip shortage (approx.)", "2021-07-01", "2022-12-31")
TARIFFS = ("Tariffs up to 50% (non-FTA)", "2026-01-01")

# Brand nationality is NOT in the INEGI data. This is our own classification by parent company.
CHINESE_BRANDS = {
    "MG", "JAC", "Chirey", "Omoda", "Jetour", "Great Wall Motor", "Geely", "GAC",
    "Changan", "Foton", "Zeekr", "Lynk&Co", "Leapmotor", "MOTORNATION",
}
SHORT_NAME = {"General Motors": "GM", "Great Wall Motor": "Great Wall", "Mercedes Benz": "Mercedes"}


# ---------------------------------------------------------------
# 3. Load the clean data
# ---------------------------------------------------------------
@st.cache_data
def load_data():
    sales = pd.read_csv(DATA_DIR / "sales_clean.csv", parse_dates=["date"])
    coverage = pd.read_csv(DATA_DIR / "brand_coverage.csv", parse_dates=["first_month", "last_month"])
    sales["group"] = sales["segment"].map(GROUP_OF)
    sales["chinese_brand"] = sales["brand"].isin(CHINESE_BRANDS)
    # Where was the vehicle built? Three buckets keep the story simple.
    sales["origin_group"] = np.where(
        sales["origin_country"] == "Mexico", "Made in Mexico",
        np.where(sales["origin_country"] == "China", "Built in China", "Other imports"),
    )
    return sales, coverage


sales, coverage = load_data()

LAST = sales["date"].max()                       # last month in the data (Oct 2026)
LAST_M, LAST_Y = LAST.month, LAST.year
ALL_MONTHS = pd.date_range(sales["date"].min(), LAST, freq="MS")
FIRST_REVISED = sales.loc[sales["status"] == "Revised", "date"].min()
ORIGIN_COLORS = {"Made in Mexico": BLUE, "Built in China": ORANGE, "Other imports": GRAY}


# ---------------------------------------------------------------
# 4. Small helper functions
# ---------------------------------------------------------------
def fmt(n):
    return f"{n:,.0f}"


def pct_change(new, old):
    """Percent change, or None when the old value is zero."""
    if old is None or old == 0:
        return None
    return (new / old - 1) * 100


def fmt_pct(p, digits=0):
    """Signed percent with a real minus sign (looks better in big numbers)."""
    return "n/a" if p is None else f"{p:+.{digits}f}%".replace("-", "−")


def millions(n):
    return f"{n / 1e6:.2f}M"


def ytd(frame, year):
    """Units from January to the last month of the data (Oct) in a given year.
    Using the same months every year makes years comparable."""
    return frame[(frame["year"] == year) & (frame["month"] <= LAST_M)]["units"].sum()


def monthly(frame):
    """Monthly units with no missing months."""
    return frame.groupby("date")["units"].sum().reindex(ALL_MONTHS, fill_value=0)


def bold_years(years):
    """Axis labels: milestone years in bold, the rest plain."""
    return [f"<b>{y}</b>" if y in MILESTONES else str(y) for y in years]


COUNTRY_SHORT = {"United States": "USA", "South Korea": "S. Korea", "United Kingdom": "UK", "Czech Republic": "Czechia"}
ACRONYMS = {"RAM", "GT", "MG", "SUV", "GLA", "GLB", "GLC", "GLE", "GLS", "CLA", "BMW"}


def model_label(brand, family):
    """Short readable car name: 'VERSA' -> 'Versa', 'CX-30' stays, and very short numeric names
    get the brand in front (Mazda 3, Kia K3)."""
    words = []
    for w in family.split():
        keep = any(c.isdigit() for c in w) or "-" in w or w in ACRONYMS
        words.append(w if keep else w.capitalize())
    name = " ".join(words)
    if len(family) <= 3 and any(c.isdigit() for c in family) and brand and not family.upper().startswith(brand.upper()):
        name = f"{SHORT_NAME.get(brand, brand)} {name}"
    return name


def style(fig, height, left=10, right=20, top=10, bottom=10):
    """Same look for every chart: white surface, light grid, big readable text (projector)."""
    fig.update_layout(
        height=height, margin=dict(l=left, r=right, t=top, b=bottom),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="sans-serif", size=15, color=INK2),
        hoverlabel=dict(bgcolor="white", font=dict(size=14, color=INK)),
        legend=dict(orientation="h", y=1.0, yanchor="bottom", xref="container", x=0.02, xanchor="left",
                    font=dict(size=14), traceorder="normal"),
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, ticks="outside", tickcolor=AXIS)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def draw(fig, key):
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


def card_title(text, sub=""):
    st.markdown(f'<div class="ctitle">{text}</div>' + (f'<div class="csub">{sub}</div>' if sub else ""),
                unsafe_allow_html=True)


# ---------------------------------------------------------------
# 5. Page style: navy background, white cards, big type
# ---------------------------------------------------------------
st.markdown(
    """
<style>
[data-testid="stApp"] {background: radial-gradient(1300px 700px at 8% -8%, #1a4a8a 0%, #0a1f44 52%, #061330 100%);}
[data-testid="stHeader"] {background: transparent;}
[data-testid="stMainBlockContainer"] {max-width: 1500px; padding-top: 1.6rem; padding-bottom: 3rem;}
[class*="st-key-card"] {background: #ffffff; border-radius: 14px; padding: 1rem 1.3rem 1.3rem 1.3rem;
                        box-shadow: 0 4px 18px rgba(0,0,0,0.28);}
.kicker {color: #8fbaff; letter-spacing: .16em; font-weight: 700; font-size: .95rem;}
.page-title {color: #fff; font-size: 2.8rem; font-weight: 800; line-height: 1.1; margin: .15rem 0 .35rem 0;}
.decision {color: #dbe8ff; font-size: 1.2rem; margin-bottom: 1.1rem;}
.act-tag {color: #8fbaff; letter-spacing: .16em; font-weight: 700; font-size: 1rem; margin-top: 2.4rem;}
.act-title {color: #fff; font-size: 2.15rem; font-weight: 800; line-height: 1.15; margin: .15rem 0 .3rem 0;}
.so-what {color: #dbe8ff; font-size: 1.2rem; margin-bottom: .9rem;}
.so-what b {color: #ffffff;}
.ctitle {font-size: 1.2rem; font-weight: 700; color: #0b1b33; margin-bottom: .1rem;}
.csub {font-size: .95rem; color: #6b7585; margin-bottom: .2rem;}
.hero-num {font-size: 4.6rem; font-weight: 800; line-height: 1; margin: .3rem 0 .2rem 0;}
.hero-lab {font-size: 1.1rem; font-weight: 600; color: #0b1b33;}
.hero-det {font-size: .95rem; color: #6b7585; margin-bottom: .4rem;}
.note {color: #6b7585; font-size: .85rem; margin: .1rem 0 .4rem 0;}
.rec-lead {font-size: 1.25rem; font-weight: 800; color: #0b1b33; margin-bottom: .25rem;}
.rec-body {font-size: 1.05rem; color: #333c4d; margin-bottom: .4rem;}
[class*="st-key-card_rec"] {min-height: 170px;}
.foot {color: #9db6e0; font-size: .85rem;}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------
# 6. Header: one line with the decision (no "who am I" box)
# ---------------------------------------------------------------
st.markdown(
    '<div class="kicker">MEXICO LIGHT-VEHICLE MARKET · 2016 – OCT 2026 · SOURCE: INEGI RAIAVL</div>'
    '<div class="page-title">Should we enter Mexico in 2027?</div>'
    '<div class="decision">Strategy team of a brand not yet in Mexico. '
    'We decide: <b>go or no-go, which vehicle first, and how fast we can grow.</b></div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------
# 7. Filter bar (one slim row; the filters apply to the timeline, brand and model charts)
# ---------------------------------------------------------------
with st.container(key="card_filters"):
    f1, f2, f3 = st.columns([1.3, 1.6, 1.3], gap="large")
    y_start, y_end = f1.select_slider(
        "Years on the top charts", options=list(range(2016, LAST_Y + 1)), value=(2016, LAST_Y),
    )
    groups = f2.pills("Vehicle group", GROUPS, selection_mode="multi", default=GROUPS,
                      help="Cars = subcompact + compact cars. Other = luxury, sports and minivans.")
    origins = f3.pills("Where it was built", ["Made in Mexico", "Imported"], selection_mode="multi",
                       default=["Made in Mexico", "Imported"])
    st.markdown('<div class="note">Filters change the timeline, brand and model charts. '
                'Titles and the decision block always describe the whole market.</div>', unsafe_allow_html=True)

if not groups or not origins:
    st.warning("Pick at least one vehicle group and one origin.")
    st.stop()

view = sales[sales["group"].isin(groups) & sales["origin"].isin(origins)]   # filtered data
if view.empty:
    st.warning("No data for this combination of filters.")
    st.stop()

# ---------------------------------------------------------------
# 8. Facts for titles and takeaways (always the whole market, no filters)
# ---------------------------------------------------------------
tot = {y: ytd(sales, y) for y in range(2016, LAST_Y + 1)}


def share_of(frame, year, mask_col, value):
    f = frame[(frame["year"] == year) & (frame["month"] <= LAST_M)]
    return f[f[mask_col] == value]["units"].sum() / f["units"].sum() * 100


def china_units(year):
    return ytd(sales[sales["origin_country"] == "China"], year)


imp = {y: share_of(sales, y, "origin", "Imported") for y in MILESTONES}
suv = {y: share_of(sales, y, "group", "SUVs") for y in MILESTONES}
cars_now = share_of(sales, LAST_Y, "group", "Cars")
roll_all = monthly(sales).rolling(12).sum().dropna()          # whole market, 12-month total
peak_m, trough_m, now_m = roll_all.max(), roll_all.min(), roll_all.iloc[-1]


# ===============================================================
# THE SPINE: the whole decade in one view, with the three periods marked
# ===============================================================
def fig_spine(frame):
    t0, t1 = pd.Timestamp(y_start, 1, 1), min(pd.Timestamp(y_end, 12, 1), LAST)
    roll = monthly(frame).rolling(12).sum().dropna()
    roll = roll[(roll.index >= t0) & (roll.index <= t1)]
    fig = go.Figure()

    # The three periods as shaded bands with a label on top
    for i, ((a, b), fill) in enumerate(zip(ACT_BANDS, BAND_FILL), start=1):
        a, b = max(pd.Timestamp(a), t0), min(pd.Timestamp(b), t1 + pd.offsets.MonthEnd(0))
        if a >= b:
            continue
        fig.add_shape(type="rect", xref="x", yref="paper", x0=a, x1=b, y0=0, y1=1, fillcolor=fill,
                      line_width=0, layer="below")
        fig.add_annotation(x=a + (b - a) / 2, y=1.0, yref="paper", yanchor="bottom", showarrow=False,
                           text=f"<b>ACT {i}</b>  {ACTS[i - 1][0]}–{ACTS[i - 1][1]}",
                           font=dict(size=15, color=INK))

    # The main line
    fig.add_trace(go.Scatter(x=roll.index, y=roll.values, mode="lines", line=dict(color=BLUE, width=3.5),
                             hovertemplate="12 months to %{x|%b %Y}: %{y:,.0f} units<extra></extra>", name="Units"))

    # Big labeled points: the first 12-month total and October of each period boundary
    marks = [d for d in [pd.Timestamp("2016-12-01"), pd.Timestamp("2019-10-01"),
                         pd.Timestamp("2023-10-01"), LAST] if d in roll.index]
    fig.add_trace(go.Scatter(
        x=marks, y=[roll[d] for d in marks], mode="markers+text", text=[millions(roll[d]) for d in marks],
        textposition=[{2016: "top right", 2019: "top right", 2023: "top left"}.get(d.year, "middle right") for d in marks],
        textfont=dict(size=19, color=INK), cliponaxis=False,
        marker=dict(size=13, color=INK, line=dict(color=SURFACE, width=2.5)),
        hovertemplate="12 months to %{x|%b %Y}: %{y:,.0f} units<extra></extra>", showlegend=False))

    # Events: COVID-19 and the chip shortage as bands, the tariffs as a line
    for (label, a, b), ypos, shade in [(COVID, 0.78, "rgba(11,27,51,0.25)"), (CHIPS, 0.92, "rgba(11,27,51,0.10)")]:
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        if a < t0 or a > t1:
            continue
        fig.add_shape(type="rect", xref="x", yref="paper", x0=a, x1=b, y0=0, y1=1, fillcolor=shade,
                      line_width=0, layer="below")
        fig.add_annotation(x=a, y=ypos, yref="paper", text=label, showarrow=False, xanchor="left", xshift=4,
                           font=dict(size=13, color=INK))
    ta = pd.Timestamp(TARIFFS[1])
    if t0 <= ta <= t1:
        fig.add_shape(type="line", xref="x", yref="paper", x0=ta, x1=ta, y0=0, y1=1,
                      line=dict(color=INK, width=1.5, dash="dot"))
        fig.add_annotation(x=ta, y=0.08, yref="paper", text=TARIFFS[0], showarrow=False, xanchor="right",
                           xshift=-5, font=dict(size=13, color=INK))

    lo, hi = roll.min(), roll.max()
    span = max(hi - lo, 1)
    style(fig, height=410, right=75, top=34)
    fig.update_layout(hovermode="x unified", showlegend=False)
    fig.update_yaxes(tickformat="~s", range=[lo - 0.18 * span, hi + 0.2 * span])
    fig.update_xaxes(tickformat="%Y", dtick="M12", tick0=f"{y_start}-01-01", range=[t0, t1 + pd.offsets.MonthEnd(0)])
    return fig


# ===============================================================
# What Mexicans buy: share of units by vehicle group (lines, not stacked bars)
# ===============================================================
def fig_mix(frame):
    years = list(range(y_start, y_end + 1))
    t = (frame[(frame["month"] <= LAST_M) & (frame["year"].isin(years))]
         .groupby(["year", "group"])["units"].sum().unstack(fill_value=0).reindex(years, fill_value=0))
    share = t.div(t.sum(axis=1).replace(0, np.nan), axis=0) * 100
    fig = go.Figure()

    for i, (a, b) in enumerate(ACTS):        # same three bands as the timeline
        a, b = max(a, y_start), min(b, y_end)
        if a < b:
            fig.add_shape(type="rect", xref="x", yref="paper", x0=a, x1=b, y0=0, y1=1, fillcolor=BAND_FILL[i],
                          line_width=0, layer="below")

    # Gray lines first, the highlighted SUV line last so it sits on top
    for g in ["Other", "Pick-ups", "Cars", "SUVs"]:
        if g not in share:
            continue
        hi = g == "SUVs"
        marks = [y for y in MILESTONES[:-1] if y in share.index]   # the last year gets its end label instead
        fig.add_trace(go.Scatter(
            x=share.index, y=share[g], mode="lines", name=g,
            line=dict(color=GROUP_COLORS[g], width=5 if hi else 2.5),
            customdata=t[g], hovertemplate=g + " %{x}: %{y:.1f}% (%{customdata:,.0f} units)<extra></extra>"))
        if g in ("SUVs", "Cars"):   # numbers at the milestone years
            fig.add_trace(go.Scatter(
                x=marks, y=[share.loc[y, g] for y in marks], mode="markers+text", showlegend=False,
                text=[f"{share.loc[y, g]:.0f}%" for y in marks],
                textposition="bottom center" if hi else "top center",
                textfont=dict(size=17 if hi else 14, color=BLUE if hi else DARK), cliponaxis=False,
                marker=dict(size=10 if hi else 7, color=GROUP_COLORS[g], line=dict(color=SURFACE, width=2)),
                hoverinfo="skip"))
    # Direct labels at the end of each line (SUVs and Cars are close, so push them apart)
    last = share.index[-1]
    shifts = {"SUVs": 11, "Cars": -11}
    for g in share.columns:
        fig.add_annotation(x=last, y=share.loc[last, g], text=f"<b>{g}</b> {share.loc[last, g]:.0f}%",
                           showarrow=False, xanchor="left", xshift=10, yshift=shifts.get(g, 0),
                           font=dict(size=15, color=BLUE if g == "SUVs" else INK2))

    style(fig, height=410, right=120, top=34)
    fig.update_layout(showlegend=False)
    fig.update_yaxes(ticksuffix="%", range=[0, max(70, share.max().max() + 8)])
    fig.update_xaxes(tickvals=years, ticktext=bold_years(years), range=[y_start - 0.25, y_end + 0.1])
    for i, (a, b) in enumerate(ACTS, start=1):
        a, b = max(a, y_start), min(b, y_end)
        if a < b:
            fig.add_annotation(x=(a + b) / 2, y=1.0, yref="paper", yanchor="bottom", showarrow=False,
                               text=f"<b>ACT {i}</b>", font=dict(size=15, color=INK))
    return fig


# ===============================================================
# One act = a big number + three comparable charts
# ===============================================================
def fig_mini(frame, y0, y1):
    """Jan-Oct units for each year of the act: first and last year highlighted, the rest gray."""
    years = list(range(y0, y1 + 1))
    vals = [ytd(frame, y) for y in years]
    colors = [GRAY if y == y0 else BLUE if y == y1 else LIGHT for y in years]
    ends = [y in (y0, y1) for y in years]
    fig = go.Figure(go.Bar(
        x=[str(y) for y in years], y=vals, marker_color=colors, marker_line_color=SURFACE, marker_line_width=2,
        text=[f"{v / 1000:,.0f}k" for v in vals], textposition="outside", cliponaxis=False,
        textfont=dict(size=[18 if e else 13 for e in ends], color=[INK if e else MUTED for e in ends]),
        hovertemplate="%{x}: %{y:,.0f} units<extra></extra>"))
    style(fig, height=290, top=30, bottom=5)
    fig.update_layout(showlegend=False, bargap=0.25)
    fig.update_xaxes(type="category", tickvals=[str(y) for y in years],
                     ticktext=[f"<b>{y}</b>" if y in (y0, y1) else str(y) for y in years])
    fig.update_yaxes(visible=False, range=[0, max(vals) * 1.25])
    return fig


def share_by_brand(frame, year):
    t = frame[(frame["year"] == year) & (frame["month"] <= LAST_M)].groupby("brand")["units"].sum()
    return t / t.sum() * 100 if t.sum() else t


def movers(frame, y0, y1):
    """Top 3 brands that gained share and top 3 that lost share between two years."""
    chg = pd.DataFrame({"old": share_by_brand(frame, y0), "new": share_by_brand(frame, y1)}).fillna(0)
    chg = chg[(chg["old"] >= 1) | (chg["new"] >= 1)]          # brands that matter in size
    chg["change"] = chg["new"] - chg["old"]
    chg = chg.sort_values("change")
    return pd.concat([chg.head(3)[chg.head(3)["change"] < 0], chg.tail(3)[chg.tail(3)["change"] > 0]])


def fig_movers(chg, y0, y1, limit):
    fig = go.Figure()
    names = [SHORT_NAME.get(b, b) for b in chg.index]
    colors = [ORANGE if b in CHINESE_BRANDS else (BLUE if c > 0 else GRAY) for b, c in zip(chg.index, chg["change"])]
    fig.add_trace(go.Bar(
        x=chg["change"], y=names, orientation="h", marker_color=colors, marker_line_color=SURFACE,
        marker_line_width=2, showlegend=False, text=[f"<b>{v:+.1f}</b>".replace("-", "−") for v in chg["change"]],
        textposition="outside", cliponaxis=False, textfont=dict(size=16, color=INK),
        customdata=chg[["old", "new"]].values,
        hovertemplate="%{y}: %{x:+.1f} pts<br>" + f"{y0}: " + "%{customdata[0]:.1f}% of units<br>"
                      + f"{y1}: " + "%{customdata[1]:.1f}% of units<extra></extra>"))
    for name, color in [("Chinese brand*", ORANGE), ("Gaining", BLUE), ("Losing", GRAY)]:
        fig.add_trace(go.Bar(x=[None], y=[None], name=name, marker_color=color))   # legend entries only
    fig.add_vline(x=0, line=dict(color=AXIS, width=1))
    style(fig, height=390, top=40, bottom=45, right=40)
    fig.update_xaxes(range=[-limit, limit], showgrid=False, showticklabels=False,
                     title=dict(text="Change in share of units (pts)", font=dict(size=13)))
    fig.update_yaxes(gridcolor=SURFACE, categoryorder="array", categoryarray=names, tickfont=dict(size=16, color=INK))
    return fig


def top_models(frame, year, n=8):
    """The n best-selling cars of a year, with the country where most of their units were built."""
    f = frame[(frame["year"] == year) & (frame["month"] <= LAST_M)]
    best = f.groupby(["brand", "model_family"])["units"].sum().sort_values(ascending=False).head(n)
    rows = []
    for (brand, family), units in best.items():
        sub = f[(f["brand"] == brand) & (f["model_family"] == family)]
        country = sub.groupby("origin_country")["units"].sum().idxmax()
        rows.append({"label": model_label(brand, family), "brand": brand, "units": units, "country": country,
                     "origin_group": "Made in Mexico" if country == "Mexico" else
                     "Built in China" if country == "China" else "Other imports"})
    return pd.DataFrame(rows)


def fig_models(tm):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=tm["units"], y=tm["label"], orientation="h", showlegend=False,
        marker_color=[ORIGIN_COLORS[o] for o in tm["origin_group"]], marker_line_color=SURFACE, marker_line_width=2,
        text=[f"<b>{u:,.0f}</b>  ·  {COUNTRY_SHORT.get(c, c)}" for u, c in zip(tm["units"], tm["country"])],
        textposition="outside", cliponaxis=False, textfont=dict(size=15, color=INK),
        customdata=tm[["brand", "country"]].values,
        hovertemplate="%{customdata[0]} %{y}: %{x:,.0f} units<br>Built in %{customdata[1]}<extra></extra>"))
    for name, color in ORIGIN_COLORS.items():
        fig.add_trace(go.Bar(x=[None], y=[None], name=name, marker_color=color))   # legend entries only
    style(fig, height=390, top=40, bottom=10)
    fig.update_xaxes(visible=False, range=[0, tm["units"].max() * 1.85])
    fig.update_yaxes(gridcolor=SURFACE, autorange="reversed", tickfont=dict(size=15, color=INK))   # best seller on top
    return fig


def act_block(i, y0, y1, title, so_what, key_prefix):
    """The same layout for every act: header, big number + mini bars, brands, models."""
    st.markdown(f'<div class="act-tag">ACT {i} · {y0} → {y1}</div>'
                f'<div class="act-title">{title}</div><div class="so-what">{so_what}</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.0, 1.25, 1.55], gap="medium")
    with c1:
        with st.container(key=f"card_hero{i}"):
            a, b = ytd(view, y0), ytd(view, y1)
            p = pct_change(b, a)
            st.markdown(
                f'<div class="hero-num" style="color:{RED if p is not None and p < 0 else BLUE}">{fmt_pct(p, 1 if p is not None and abs(p) < 10 else 0)}</div>'
                f'<div class="hero-lab">Jan–Oct sales, {y0} → {y1}</div>'
                f'<div class="hero-det">{fmt(a)} → {fmt(b)} units</div>', unsafe_allow_html=True)
            draw(fig_mini(view, y0, y1), f"{key_prefix}_mini")
    with c2:
        with st.container(key=f"card_brands{i}"):
            card_title("Who gained and lost share", f"Biggest 3 gainers and 3 losers, {y0} → {y1}")
            draw(fig_movers(MOVERS[i - 1], y0, y1, MOVER_LIMIT), f"{key_prefix}_movers")
    with c3:
        with st.container(key=f"card_models{i}"):
            card_title(f"Best-selling cars of {y1}", f"Units Jan–Oct, and the country where they were built")
            tm = top_models(view, y1)
            if tm.empty:
                st.info("No sales for these filters.")
            else:
                draw(fig_models(tm), f"{key_prefix}_models")


# ---------------------------------------------------------------
# 9. Page: the spine
# ---------------------------------------------------------------
sp1, sp2 = st.columns([1.7, 1.15], gap="medium")
with sp1:
    with st.container(key="card_spine"):
        card_title(f"Sales fell from {peak_m / 1e6:.2f}M to {trough_m / 1e6:.2f}M a year, and are now back at {now_m / 1e6:.2f}M",
                   "Units sold in the last 12 months. Labeled points: first full year (Dec 2016) and October of each period boundary")
        draw(fig_spine(view), "spine")
with sp2:
    with st.container(key="card_mix"):
        card_title(f"SUVs went from {suv[2016]:.0f}% to {suv[LAST_Y]:.0f}% of the vehicles sold",
                   "Share of Jan–Oct units, by vehicle group")
        draw(fig_mix(sales[sales["origin"].isin(origins)]), "mix")
st.markdown(
    '<div class="foot">Coverage: INEGI’s registry only lists brands that report. <b>BYD is not in it</b>; Chirey and Omoda '
    'stop appearing in Mar 2025; Geely, GAC and Foton appear from Jan 2024. Newcomer volumes are a lower bound. '
    f'Figures are definitive up to {(FIRST_REVISED - pd.DateOffset(months=1)):%b %Y} and revised afterwards.</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------
# 10. Page: the three acts (numbers are computed, not typed)
# ---------------------------------------------------------------
# Brand movers for the three acts share one x-axis scale so the acts can be compared at a glance
MOVERS = [movers(view, a, b) for a, b in ACTS]
MOVER_LIMIT = max([m["change"].abs().max() for m in MOVERS if len(m)] + [1]) * 1.75

(a1, b1), (a2, b2), (a3, b3) = ACTS
chg1, chg2, chg3 = (pct_change(tot[b], tot[a]) for a, b in ACTS)
trough = tot[2020]
movers_full = [movers(sales, a, b) for a, b in ACTS]          # whole market, for titles


def china_gainers(i):
    """Chinese brands among the top share gainers of act i (whole market), biggest first."""
    m = movers_full[i]
    return [SHORT_NAME.get(b, b) for b in m.index if b in CHINESE_BRANDS and m.loc[b, "change"] > 0][::-1]


def join_names(names):
    return " and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)


act_block(
    1, a1, b1,
    f"The market was already shrinking: {fmt_pct(chg1)} in three years",
    f"Before COVID-19, imports grew from <b>{imp[2016]:.0f}%</b> to <b>{imp[2019]:.0f}%</b> of sales "
    f"and SUVs from <b>{suv[2016]:.0f}%</b> to <b>{suv[2019]:.0f}%</b>.",
    "act1",
)
act_block(
    2, a2, b2,
    f"Sales fell {abs(pct_change(trough, tot[2019])):.0f}% in the COVID-19 year, and by 2023 they were back to 2019 ({fmt_pct(chg2, 1)})",
    f"SUVs grew from <b>{suv[2019]:.0f}% to {suv[2023]:.0f}%</b> of sales, vehicles built in China from "
    f"<b>{fmt(china_units(2019))} to {fmt(china_units(2023))}</b> units, and {join_names(china_gainers(1))} gained the most share.",
    "act2",
)
act_block(
    3, a3, b3,
    f"A new market: {fmt_pct(chg3)} in three years, with {join_names(china_gainers(2))} gaining share",
    f"Vehicles built in China reached <b>{fmt(china_units(2026))}</b> units in Jan–Oct {LAST_Y}, "
    f"up from <b>{fmt(china_units(2023))}</b> in {b2}.",
    "act3",
)
st.markdown('<div class="foot">*Chinese brand = our own classification by parent company (not an INEGI field). '
            'Model names are merged (for example “BEAT” and “BEAT 4 PTAS.”); a car can still be split under other names. '
            'Where a car was built is the country where most of its units were built.</div>', unsafe_allow_html=True)

# ===============================================================
# THE DECISION (always the whole market, no filters)
# ===============================================================
cut, cut2 = LAST - pd.DateOffset(months=12), LAST - pd.DateOffset(months=24)
last12, prev12 = sales[sales["date"] > cut], sales[(sales["date"] <= cut) & (sales["date"] > cut2)]


def growth_table(col):
    a, b = last12.groupby(col)["units"].sum(), prev12.groupby(col)["units"].sum()
    return pd.DataFrame({"last12": a, "prev12": b, "growth": (a / b - 1) * 100, "share": a / a.sum() * 100})


gg, sg = growth_table("group"), growth_table("segment")
detail = {   # growth of the segments inside each group, shown on hover
    g: ", ".join(f"{s} {sg.loc[s, 'growth']:+.1f}%".replace("-", "−")
                 for s in [k for k, v in GROUP_OF.items() if v == g]) for g in GROUPS
}


def top5_share(group):
    f = last12[last12["group"] == group].groupby(["brand", "model_family"])["units"].sum().sort_values(ascending=False)
    return f.head(5).sum() / f.sum() * 100, f.iloc[0] / f.sum() * 100, f.index[0]


openness = {g: top5_share(g) for g in GROUPS}


def target_box(fig, categories, target):
    """Translucent green rectangle around the target bar (what the audience should look at)."""
    pos = categories.index(target)
    fig.add_shape(type="rect", xref="paper", yref="y", x0=0, x1=1.0, y0=pos - 0.46, y1=pos + 0.46,
                  fillcolor=TARGET_FILL, line=dict(color=GREEN, width=2.5), layer="below")


def fig_growth():
    order = gg.sort_values("growth").index.tolist()            # biggest growth ends on top
    vals = [gg.loc[g, "growth"] for g in order]
    colors = [BLUE if g == "SUVs" else LIGHT for g in order]
    hover = [f"<b>{g}</b>: {gg.loc[g, 'growth']:+.1f}%<br>{gg.loc[g, 'share']:.0f}% of units<br>{detail[g]}"
             for g in order]
    kwargs = dict(y=order, orientation="h", marker_color=colors, marker_line_color=SURFACE, marker_line_width=2,
                  text=[f"<b>{v:+.1f}%</b>".replace("-", "−") for v in vals], textposition="outside",
                  cliponaxis=False, textfont=dict(size=18, color=INK), hovertext=hover, hoverinfo="text")
    fig = go.Figure(go.Bar(x=vals, **kwargs))
    # Animation: bars grow from zero when the button is pressed (the chart starts fully drawn)
    steps = np.linspace(0, 1, 14)
    fig.frames = [go.Frame(data=[go.Bar(x=[v * s for v in vals], **kwargs)]) for s in steps]
    fig.update_layout(updatemenus=[dict(
        type="buttons", showactive=False, x=1.0, xanchor="right", y=1.16, yanchor="top",
        buttons=[dict(label="Replay growth", method="animate",
                      args=[None, dict(frame=dict(duration=45, redraw=True), transition=dict(duration=0),
                                       fromcurrent=False, mode="immediate")])])])
    target_box(fig, order, "SUVs")
    fig.add_annotation(xref="paper", yref="y", x=0.995, y=order.index("SUVs") - 0.3, text="<b>TARGET</b>",
                       showarrow=False, xanchor="right", font=dict(size=13, color="#0f7a53"))
    fig.add_vline(x=0, line=dict(color=AXIS, width=1))
    style(fig, height=340, top=45, left=10, right=30)
    fig.update_xaxes(visible=False, range=[min(vals + [0]) - 1.8, max(vals) * 1.35])
    fig.update_yaxes(gridcolor=SURFACE, tickfont=dict(size=17, color=INK))
    return fig


def fig_open():
    order = sorted(GROUPS, key=lambda g: -openness[g][0])       # most open (lowest) ends on top
    vals = [openness[g][0] for g in order]
    fig = go.Figure(go.Bar(
        x=vals, y=order, orientation="h", marker_color=[BLUE if g == "SUVs" else LIGHT for g in order],
        marker_line_color=SURFACE, marker_line_width=2, text=[f"<b>{v:.0f}%</b>" for v in vals],
        textposition="outside", cliponaxis=False, textfont=dict(size=18, color=INK),
        hovertext=[f"<b>{g}</b>: top 5 models = {openness[g][0]:.0f}% of the group<br>"
                   f"Best seller: {model_label(*openness[g][2])} ({openness[g][1]:.0f}% of the group)"
                   for g in order], hoverinfo="text"))
    target_box(fig, order, "SUVs")
    fig.add_vline(x=0, line=dict(color=AXIS, width=1))
    style(fig, height=340, top=45, left=10, right=30)
    fig.update_xaxes(visible=False, range=[0, max(vals) * 1.3])
    fig.update_yaxes(gridcolor=SURFACE, tickfont=dict(size=17, color=INK))
    return fig


# Newcomers: brands first seen in 2017 or later with at least 20,000 units in the registry
ENTRANTS = coverage[(coverage["first_month"] >= "2017-01-01") & (coverage["total_units"] >= 20000)] \
    .sort_values("total_units", ascending=False)["brand"].tolist()


def brand_series(brand):
    """Monthly units of a brand from its first month in the registry
    (cut at its last month with sales if it stopped appearing)."""
    row = coverage[coverage["brand"] == brand].iloc[0]
    end_month = LAST if row["last_month"] >= LAST else row["last_month"]
    idx = pd.date_range(row["first_month"], end_month, freq="MS")
    return sales[sales["brand"] == brand].groupby("date")["units"].sum().reindex(idx, fill_value=0)


def months_to(series, threshold):
    """Months since first sale until the 3-month average reaches a monthly level."""
    reached = series.rolling(3).mean()
    hit = reached[reached >= threshold]
    return None if hit.empty else int(reached.index.get_loc(hit.index[0]))


entrants = []
for b in ENTRANTS:
    s = brand_series(b)
    rows = sales[sales["brand"] == b]
    entrants.append({
        "brand": b, "series": s, "m3k": months_to(s, 3000), "m1k": months_to(s, 1000),
        "year1": s.iloc[:12].sum() if len(s) >= 12 else None,
        "imported": rows[rows["origin"] == "Imported"]["units"].sum() / rows["units"].sum() * 100,
    })
winners = [e for e in entrants if e["m3k"] is not None]          # reached 3,000 units a month
winner_names = [e["brand"] for e in winners]
HORIZON = 36


def fig_cohort():
    fig = go.Figure()
    shown_other = False
    for e in entrants:                                           # gray lines first
        if e in winners:
            continue
        s = e["series"].rolling(3).mean().iloc[:HORIZON + 1]
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s.values, mode="lines", name="Other newcomers",
                                 legendgroup="other", showlegend=not shown_other, line=dict(color=LIGHT, width=2),
                                 hovertemplate=e["brand"] + ", month %{x}: %{y:,.0f} a month<extra></extra>"))
        shown_other = True
    for e in winners:                                            # highlighted brands on top
        s = e["series"].rolling(3).mean().iloc[:HORIZON + 1]
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s.values, mode="lines", name=e["brand"],
                                 line=dict(color=ORANGE, width=4.5, dash="solid" if e is winners[0] else "dot"),
                                 hovertemplate=e["brand"] + ", month %{x}: %{y:,.0f} a month<extra></extra>"))
        m = e["m3k"]
        if m is not None and m <= HORIZON:
            fig.add_trace(go.Scatter(x=[m], y=[s.iloc[m]], mode="markers+text", showlegend=False,
                                     text=[f"<b>{e['brand']}: {m} months</b>"],
                                     textposition="top left" if e is winners[0] else "bottom right",
                                     textfont=dict(size=15, color=INK), cliponaxis=False,
                                     marker=dict(size=13, color=ORANGE, line=dict(color=SURFACE, width=2.5)),
                                     hoverinfo="skip"))
    fig.add_hline(y=3000, line=dict(color=INK2, width=1.2, dash="dot"),
                  annotation_text="3,000 a month", annotation_position="top left",
                  annotation_font=dict(size=13, color=INK2))
    style(fig, height=380, top=45, right=20)
    fig.update_xaxes(title=dict(text="Months since the first month in the registry", font=dict(size=13)),
                     dtick=6, range=[0, HORIZON + 1], showgrid=False)
    fig.update_yaxes(title=dict(text="Units a month (3-month average)", font=dict(size=13)), tickformat=",.0f")
    return fig


def fig_year1():
    rows = sorted([e for e in entrants if e["year1"] is not None], key=lambda e: e["year1"])
    median = float(np.median([e["year1"] for e in rows]))
    fig = go.Figure(go.Bar(
        x=[e["year1"] for e in rows], y=[e["brand"] for e in rows], orientation="h",
        marker_color=[ORANGE if e["brand"] in winner_names else LIGHT for e in rows],
        marker_line_color=SURFACE, marker_line_width=2, text=[f"<b>{e['year1']:,.0f}</b>" for e in rows],
        textposition="outside", cliponaxis=False, textfont=dict(size=16, color=INK),
        hovertemplate="%{y}: %{x:,.0f} units in its first 12 months<extra></extra>"))
    fig.add_vline(x=median, line=dict(color=INK2, width=1.5, dash="dot"),
                  annotation_text=f"Median {median:,.0f}", annotation_position="bottom right",
                  annotation_font=dict(size=14, color=INK2))
    style(fig, height=380, top=45, right=20)
    fig.update_xaxes(visible=False, range=[0, max(e["year1"] for e in rows) * 1.25])
    fig.update_yaxes(gridcolor=SURFACE, tickfont=dict(size=16, color=INK))
    return fig, rows, median


# Numbers for the decision text
suv_g, suv_share = gg.loc["SUVs", "growth"], gg.loc["SUVs", "share"]
suv_top5, suv_top1, _ = openness["SUVs"]
others_top5 = [openness[g][0] for g in GROUPS if g != "SUVs"]
months_lo = min((e["m3k"] for e in winners), default=None)
months_hi = max((e["m3k"] for e in winners), default=None)
n_imported = sum(1 for e in entrants if e["imported"] >= 99)
cn_now, cn_prev = china_units(LAST_Y), china_units(LAST_Y - 1)

st.markdown(
    '<div class="act-tag">THE DECISION</div>'
    f'<div class="act-title">Enter with a SUV'
    + (f' and budget {months_lo}–{months_hi} months to reach 3,000 units a month' if winners else "")
    + '</div>'
    f'<div class="so-what">SUVs are now the biggest group (<b>{suv_share:.0f}%</b> of units vs <b>{cars_now:.0f}%</b> for cars), the fastest-growing '
    f'(<b>{fmt_pct(suv_g, 1)}</b>) and the most open: the top 5 models hold only <b>{suv_top5:.0f}%</b> of the group.</div>',
    unsafe_allow_html=True,
)

d1, d2 = st.columns(2, gap="medium")
with d1:
    with st.container(key="card_growth"):
        card_title("Which vehicle? Growth of each group", "Last 12 months vs the 12 months before. Hover for the detail inside each group")
        draw(fig_growth(), "growth")
        st.markdown(f'<div class="note">Inside Cars: {detail["Cars"]}.</div>', unsafe_allow_html=True)
with d2:
    with st.container(key="card_open"):
        card_title("Is there a clear leader? Share held by the group’s 5 best-selling cars",
                   "Last 12 months. Lower = more open to a newcomer")
        draw(fig_open(), "open")
        st.markdown(f'<div class="note">In SUVs the best-selling car has {suv_top1:.0f}% of the group; '
                    f'in the other groups the top 5 hold {min(others_top5):.0f}–{max(others_top5):.0f}%.</div>',
                    unsafe_allow_html=True)

st.markdown('<div class="act-tag" style="margin-top:1.6rem">HOW FAST?</div>'
            '<div class="act-title">What past newcomers achieved</div>', unsafe_allow_html=True)
d3, d4 = st.columns([1.3, 1], gap="medium")
with d3:
    with st.container(key="card_cohort"):
        card_title("Speed of the newcomers", "Monthly units since each brand’s first month in the registry")
        draw(fig_cohort(), "cohort")
with d4:
    with st.container(key="card_year1"):
        card_title("First 12 months", "Units sold in the first year (brands with 12 months of history)")
        fig_y1, y1_rows, y1_median = fig_year1()
        draw(fig_y1, "year1")
st.markdown(
    '<div class="foot">Month 0 is the first month a brand appears in the INEGI registry, which is not always its commercial launch '
    '(Geely, GAC and Foton appear in Jan 2024). These are observed results, not a forecast. BYD cannot be benchmarked: it does not report.</div>',
    unsafe_allow_html=True,
)

# Three one-line recommendations
st.markdown('<div class="act-tag" style="margin-top:1.6rem">WHAT WE RECOMMEND</div>', unsafe_allow_html=True)
r1, r2, r3 = st.columns(3, gap="medium")
with r1:
    with st.container(key="card_rec1"):
        st.markdown('<div class="rec-lead">1. Lead with a SUV</div>'
                    f'<div class="rec-body">{suv_share:.0f}% of units, {fmt_pct(suv_g, 1)} growth, and no car above '
                    f'{suv_top1:.0f}% of the group. Test a subcompact as a second model: it grew '
                    f'{fmt_pct(sg.loc["Subcompacts", "growth"], 1)}.</div>', unsafe_allow_html=True)
with r2:
    with st.container(key="card_rec2"):
        winners_txt = " and ".join(f"{e['brand']} {e['m3k']}" for e in winners)
        st.markdown(f'<div class="rec-lead">2. Plan for {months_lo}\u2013{months_hi} months to scale</div>'
                    f'<div class="rec-body">Months to reach 3,000 a month: {winners_txt}. '
                    f'The other {len(entrants) - len(winners)} newcomers did not get there. '
                    f'The median newcomer sold {y1_median:,.0f} units in year 1.</div>', unsafe_allow_html=True)
with r3:
    with st.container(key="card_rec3"):
        st.markdown('<div class="rec-lead">3. Stress-test the supply route</div>'
                    f'<div class="rec-body">{n_imported} of {len(entrants)} newcomers came 100% imported. Tariffs up to 50% on '
                    f'non-FTA cars began in Jan 2026, and vehicles built in China are still {fmt_pct(pct_change(cn_now, cn_prev))} '
                    f'in Jan–Oct. The registry has no prices, so model the tariff cost separately.</div>',
                    unsafe_allow_html=True)

# ---------------------------------------------------------------
# 11. Sources and method (collapsed: for questions, not for the talk)
# ---------------------------------------------------------------
with st.container(key="card_sources"), st.expander("Sources and method"):
    st.markdown(
        "**Data.** INEGI, Registro Administrativo de la Industria Automotriz de Vehículos Ligeros (RAIAVL), monthly sales 2016 to "
        "Oct 2026, revised figures (file modified 2026-11-09). https://www.inegi.org.mx/datosprimarios/iavl/\n\n"
        "**Cleaning (clean_data.py).** Brands harmonized (Chrysler and Fiat into Stellantis; JETOUR and Jetour Soueast as one brand), "
        "model name variants merged, monthly dates built from year and month, zero-unit rows dropped, negative corrections kept. "
        "Years are compared January to October because 2026 only has ten months. Segments are grouped: Cars = subcompacts + compacts; "
        "Other = luxury, sports, minivans.\n\n"
        "**Limits.** The registry only has brands that report: BYD is absent and other brands enter or leave (Chirey and Omoda end in "
        "Mar 2025, MOTORNATION in Jun 2026, Geely, GAC and Foton start in Jan 2024), so volumes of newcomers are a lower bound. "
        "There are no prices, margins or state-level sales in this table. Brand nationality is our classification.\n\n"
        "**Events on the charts (press and trade reports, not the official gazette):**\n"
        "- COVID-19: plants announced suspensions from 19 Mar 2020 "
        "([Expansión](https://expansion.mx/empresas/2020/03/25/el-cierre-de-plantas-de-autos-desencadena-un-efecto-domino-en-mexico)); "
        "non-essential activities suspended 30 Mar to 30 Apr 2020 "
        "([Cluster Industrial](https://clusterindustrial.com.mx/es-esencial-la-industria-automotriz-la-dificil-balanza-entre-la-industria-y-la-emergencia/)).\n"
        "- Chip shortage: production fell for months from mid-2021 "
        "([Bloomberg Línea](https://www.bloomberglinea.com/2022/02/04/industria-automotriz-de-mexico-vuelve-a-caer-en-produccion-por-chips-y-omicron/)); "
        "normalization expected in the second half of 2022 "
        "([La Razón](https://www.razon.com.mx/negocios/escasez-chips-retrasa-recuperacion-automotriz-450461/)); "
        "impact lower in Jan-Jun 2022 "
        "([Mexico Industry](https://mexicoindustry.com/noticia/como-afecto-la-escasez-de-chips-a-la-industria-automotriz-mexicana)). "
        "The shaded period (Jul 2021 to Dec 2022) is approximate.\n"
        "- Tariffs: the Senate approved them on 10 Dec 2025 "
        "([Thomson Reuters](https://www.thomsonreuters.com/en-us/help/onesource-global-trade/regulatory-insights/2025/december-15th/mexico-approves-tariff-hikes-on-imports-from-china)); "
        "up to 50% on cars from non-FTA countries, effective 1 Jan 2026 "
        "([Mexico News Daily](https://mexiconewsdaily.com/news/mexico-tariffs-go-into-effect-china/), "
        "[Automotive World](https://www.automotiveworld.com/news/mexico-hits-chinese-made-cars-with-50-tariffs/))."
    )
