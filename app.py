# app.py
# Streamlit dashboard: Mexico's light-vehicle market 2016-2026 (INEGI RAIAVL, monthly sales)
# Role: market-entry analyst for a brand deciding whether to enter Mexico in 2027.
#
# Run with:  streamlit run app.py
# The clean data comes from clean_data.py (data/clean/*.csv).

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Is Mexico worth entering? Light-vehicle market 2016-2026", layout="wide")

DATA_DIR = Path(__file__).parent / "data" / "clean"

# ---------------------------------------------------------------
# 1. Colors (one palette, checked for color-blind safety)
# ---------------------------------------------------------------
SURFACE = "#ffffff"   # chart background (also used as the gap between stacked bars)
INK = "#0b0b0b"
INK2 = "#52514e"      # secondary text
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
MAGENTA, GREEN, VIOLET, RED = "#e87ba4", "#008300", "#6250d6", "#e34948"

# Each category always keeps the same color, even when a filter hides others
SEGMENT_ORDER = ["SUVs", "Subcompacts", "Compacts", "Pick-ups", "Luxury", "Sports", "Minivans"]
SEGMENT_COLORS = dict(zip(SEGMENT_ORDER, [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET]))
TYPE_COLORS = {"Cars": BLUE, "Light trucks": ORANGE}
ORIGIN_COLORS = {"Made in Mexico": GREEN, "Imported": VIOLET}
BRAND_COLORS = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED]

# ---------------------------------------------------------------
# 2. Events shown on the charts (with sources in the "Sources" box at the bottom)
# ---------------------------------------------------------------
MACRO_EVENTS = [
    # label, start, end (None = a single line)
    ("COVID-19 shutdown", "2020-03-30", "2020-04-30"),
    ("Chip shortage (approx.)", "2021-07-01", "2022-12-31"),
    ("Tariffs up to 50% (non-FTA)", "2026-01-01", None),
]
REGISTRY_EVENTS = [
    ("MG joins registry", "2020-10-01"),
    ("Chirey joins", "2022-07-01"),
    ("Geely, GAC, Foton join*", "2024-01-01"),
    ("Chirey, Omoda: last sales", "2025-03-01"),
    ("MOTORNATION: last sales", "2026-06-01"),
]

# Brand nationality is NOT in the INEGI data. This is our own classification by the
# brand's parent company (MG has British heritage but Chinese ownership;
# MOTORNATION is a distributor that reports BAIC and Changan models).
CHINESE_BRANDS = {
    "MG", "JAC", "Chirey", "Omoda", "Jetour", "Great Wall Motor", "Geely", "GAC",
    "Changan", "Foton", "Zeekr", "Lynk&Co", "Leapmotor", "MOTORNATION",
}
# Countries named in the press reports about the January 2026 tariffs
TARIFF_OTHER_ORIGINS = ["India", "South Korea", "Thailand", "Indonesia"]


# ---------------------------------------------------------------
# 3. Load the clean data
# ---------------------------------------------------------------
@st.cache_data
def load_data():
    sales = pd.read_csv(DATA_DIR / "sales_clean.csv", parse_dates=["date"])
    coverage = pd.read_csv(DATA_DIR / "brand_coverage.csv", parse_dates=["first_month", "last_month"])
    sales["chinese_brand"] = sales["brand"].isin(CHINESE_BRANDS)
    return sales, coverage


sales, coverage = load_data()

LAST = sales["date"].max()                      # last month in the data (Oct 2026)
LAST_M, LAST_Y = LAST.month, LAST.year
ALL_MONTHS = pd.date_range(sales["date"].min(), LAST, freq="MS")
FIRST_REVISED = sales.loc[sales["status"] == "Revised", "date"].min()
N_STABLE = int(coverage["stable_brand"].sum())


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


def fmt_pct(p, digits=1):
    return "n/a" if p is None else f"{p:+.{digits}f}%"


def ytd(frame, year):
    """Units from January to the last month of the data (Oct) in a given year.
    Using the same months every year makes years comparable (2026 only has 10 months)."""
    return frame[(frame["year"] == year) & (frame["month"] <= LAST_M)]["units"].sum()


def monthly(frame):
    """Monthly units with no missing months."""
    return frame.groupby("date")["units"].sum().reindex(ALL_MONTHS, fill_value=0)


def month_label(ts):
    return ts.strftime("%b %Y")


def style(fig, height=380, yfmt=",.0f", ytitle=None, right=20, top=55):
    """Same look for every chart: light grid, thin axes, legend on top."""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=right, t=top, b=10),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family="sans-serif", size=13, color=INK2),
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=12), traceorder="normal"),
        hoverlabel=dict(bgcolor="white", font=dict(color=INK)),
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, ticks="outside", tickcolor=AXIS)
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, zeroline=False, tickformat=yfmt, title=ytitle)
    return fig


def show(fig, table=None, table_label="Show data table"):
    """Draw a chart and (optionally) a table with the same numbers under it."""
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    if table is not None:
        with st.expander(table_label):
            st.dataframe(table, hide_index=True, width="stretch")


def add_events(fig, start, end, macro=True, registry=False):
    """Mark events on a monthly chart (shaded bands for periods, lines for dates)."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    items = []
    if macro:
        items += [(label, pd.Timestamp(a), pd.Timestamp(b) if b else None, INK2) for label, a, b in MACRO_EVENTS]
    if registry:
        items += [(label, pd.Timestamp(a), None, MUTED) for label, a in REGISTRY_EVENTS]
    for label, a, b, color in items:
        if a < start or a > end:
            continue
        if b is not None:  # period -> shaded band
            fig.add_shape(type="rect", xref="x", yref="paper", x0=a.to_pydatetime(), x1=b.to_pydatetime(),
                          y0=0, y1=1, fillcolor="rgba(137,135,129,0.16)", line_width=0, layer="below")
        else:  # single date -> thin line
            fig.add_shape(type="line", xref="x", yref="paper", x0=a.to_pydatetime(), x1=a.to_pydatetime(),
                          y0=0, y1=1, line=dict(color=color, width=1))
        fig.add_annotation(x=a.to_pydatetime(), y=0.99, yref="paper", text=label, textangle=-90,
                           showarrow=False, xanchor="right", yanchor="top", xshift=-2,
                           font=dict(size=11, color=color))


def end_label(fig, x, y, text, color):
    """Direct label at the end of a line."""
    fig.add_annotation(x=x, y=y, text=text, showarrow=False, xanchor="left", xshift=6,
                       font=dict(size=12, color=color))


def headline(text):
    st.markdown(f"### {text}")


def takeaway(text):
    st.info(f"**Key takeaway.** {text}")


# ---------------------------------------------------------------
# 5. Page header: who is this for, and what do they have to decide?
# ---------------------------------------------------------------
st.title("Is Mexico worth entering in 2027?")
st.caption("Mexico's light-vehicle market, 2016 to October 2026 | Source: INEGI, RAIAVL (retail sales)")

with st.container(border=True):
    left, right = st.columns([3, 2])
    with left:
        st.markdown(
            "**Who I am:** a market-entry analyst on the strategy team of a brand that does not sell in Mexico yet.  \n"
            "**Who this is for:** the team deciding whether to launch in Mexico in 2027.  \n"
            "**The decision:** go or no-go, which vehicle to lead with, and how fast to expect to grow."
        )
    with right:
        st.markdown(
            "**Data vintage:** sales figures revised through Oct 2026 (INEGI file dated 9 Nov 2026). "
            f"Definitive up to {month_label(FIRST_REVISED - pd.DateOffset(months=1))}; "
            f"revised (may still change) from {month_label(FIRST_REVISED)}."
        )

st.warning(
    "**Coverage notice.** RAIAVL is an administrative record: it only has the brands that report to INEGI. "
    "**BYD does not report**, so newcomer volumes here are a lower bound. Chirey and Omoda stop appearing after "
    "Mar 2025 and MOTORNATION after Jun 2026; Geely, GAC and Foton appear from Jan 2024 (GAC's data was added "
    "back to that date). Totals can move because the brand panel changed, not only because the market did. "
    "Use the *Brand panel* filter to see only brands present for the whole period."
)

# ---------------------------------------------------------------
# 6. Sidebar filters (they apply to the charts in all sections)
# ---------------------------------------------------------------
st.sidebar.header("Filters")
months = list(ALL_MONTHS)
start, end = st.sidebar.select_slider(
    "Time window", options=months, value=(months[0], months[-1]), format_func=month_label,
    help="Monthly charts show this window. Year-by-year charts use the years inside it.",
)
segments = st.sidebar.multiselect("Segment", SEGMENT_ORDER, default=SEGMENT_ORDER)
origins = st.sidebar.multiselect("Vehicle origin", ["Made in Mexico", "Imported"], default=["Made in Mexico", "Imported"])
panel = st.sidebar.radio(
    "Brand panel",
    ["All reporting brands", f"Stable brands only ({N_STABLE})"],
    help="Stable brands are in the registry from Jan 2016 to Oct 2026. Use this to remove the effect of "
         "brands that entered or left the registry.",
)
st.sidebar.caption("Section 04 (newcomers) ignores the Brand panel filter, because newcomers are not stable brands.")

if not segments or not origins:
    st.warning("Select at least one segment and one origin in the sidebar.")
    st.stop()

base = sales[sales["segment"].isin(segments) & sales["origin"].isin(origins)]   # segment + origin filters
view = base[base["stable_brand"]] if panel.startswith("Stable") else base        # + brand panel filter
if view.empty:
    st.warning("No data for this combination of filters.")
    st.stop()

# Numbers for the top KPI row (they follow the filters)
k_now, k_prev, k_2019, k_2016 = ytd(view, LAST_Y), ytd(view, LAST_Y - 1), ytd(view, 2019), ytd(view, 2016)
imp_share = ytd(view[view["origin"] == "Imported"], LAST_Y) / k_now * 100 if k_now else None

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Jan-{month_label(LAST)[:3]} {LAST_Y} units", fmt(k_now))
c2.metric(f"vs Jan-{month_label(LAST)[:3]} {LAST_Y - 1}", fmt_pct(pct_change(k_now, k_prev)))
c3.metric("vs same months of 2019", fmt_pct(pct_change(k_now, k_2019)))
c4.metric("Imported share", "n/a" if imp_share is None else f"{imp_share:.1f}%")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "01 Is Mexico ready?",
    "02 Where is the opportunity?",
    "03 Who owns the market?",
    "04 What can we learn from newcomers?",
    "05 How should we enter?",
])

# Numbers for headlines and takeaways always use the FULL registry (no filters)
full_now, full_prev = ytd(sales, LAST_Y), ytd(sales, LAST_Y - 1)
full_2019, full_2016 = ytd(sales, 2019), ytd(sales, 2016)
stable_sales = sales[sales["stable_brand"]]
stable_now, stable_2019 = ytd(stable_sales, LAST_Y), ytd(stable_sales, 2019)

# ===============================================================
# SECTION 01: Is Mexico ready?
# ===============================================================
with tab1:
    headline(
        f"Jan-Oct sales are {fmt_pct(pct_change(full_now, full_2019), 0)} vs 2019, but only "
        f"{fmt_pct(pct_change(stable_now, stable_2019), 0)} on a like-for-like brand panel "
        f"(and {fmt_pct(pct_change(full_now, full_2016), 0)} vs 2016)"
    )
    st.caption("Headlines and takeaways describe the full registry. The charts below respond to the filters.")

    # --- Chart A: January-October by year, against a baseline year
    st.subheader("A. Is the market back? Same months, every year")
    baseline = st.radio("Baseline year", [2016, 2019], index=1, horizontal=True,
                        help="2016 is the last high point before the decline; 2019 is the year before COVID-19.")
    years = list(range(start.year, end.year + 1))
    vals = [ytd(view, y) for y in years]
    base_val = ytd(view, baseline)
    texts = [fmt(v) if y in (baseline, years[-1]) else "" for y, v in zip(years, vals)]
    fig = go.Figure(go.Bar(x=[str(y) for y in years], y=vals, marker_color=BLUE, marker_line_color=SURFACE,
                           marker_line_width=2, text=texts, textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}: %{y:,.0f} units<extra></extra>", name="Jan-Oct units"))
    fig.add_hline(y=base_val, line=dict(color=INK2, width=1.5),
                  annotation_text=f"{baseline} level", annotation_position="right",
                  annotation_font=dict(color=INK2, size=12))
    style(fig, height=360, ytitle=f"Units, January to {month_label(LAST)[:3]}", right=80)
    fig.update_xaxes(type="category", dtick=1)
    fig.update_layout(showlegend=False)
    show(fig, pd.DataFrame({
        "Year": years,
        "Jan-Oct units": vals,
        "Full-year units": [view[view["year"] == y]["units"].sum() for y in years],
        f"Jan-Oct vs {baseline}": [fmt_pct(pct_change(v, base_val)) for v in vals],
    }))
    if len(years) > 1:
        st.caption(f"Jan-Oct {years[-1]} is {fmt_pct(pct_change(vals[-1], base_val))} vs Jan-Oct {baseline} (current filters).")

    # --- Chart B: monthly view with seasonality handled and events marked
    st.subheader("B. Month by month: what happened, and when")
    metric = st.radio(
        "Show", ["12-month rolling total", "Change vs same month last year (%)", "Monthly units"],
        horizontal=True,
        help="Comparing a month with the same month a year earlier (or using a 12-month total) removes seasonality.",
    )
    ev1, ev2 = st.columns(2)
    show_macro = ev1.toggle("Mark COVID-19, chip shortage and tariffs", value=True)
    show_registry = ev2.toggle("Mark brands joining or leaving the registry", value=False)

    m = monthly(view)
    if metric == "Monthly units":
        series, ytitle, yfmt, hover = m, "Units per month", ",.0f", "%{y:,.0f} units"
    elif metric.startswith("Change"):
        prev = m.shift(12)
        series = ((m / prev - 1) * 100).where(prev > 0)
        ytitle, yfmt, hover = "% vs same month a year earlier", ".0f", "%{y:+.1f}%"
    else:
        series, ytitle, yfmt, hover = m.rolling(12).sum(), "Units in the last 12 months", ",.0f", "%{y:,.0f} units"
    series = series[(series.index >= start) & (series.index <= end)]

    fig = go.Figure(go.Scatter(x=series.index, y=series.values, mode="lines", line=dict(color=BLUE, width=2),
                               hovertemplate="%{x|%b %Y}: " + hover + "<extra></extra>", name=metric))
    if metric.startswith("Change"):
        fig.add_hline(y=0, line=dict(color=AXIS, width=1))
    add_events(fig, start, end, macro=show_macro, registry=show_registry)
    style(fig, height=400, yfmt=yfmt, ytitle=ytitle, top=40)
    fig.update_layout(showlegend=False)
    show(fig, series.rename("value").reset_index().rename(columns={"index": "date"}).assign(
        date=lambda d: d["date"].dt.strftime("%b %Y")))
    st.caption(
        f"Figures are definitive up to {month_label(FIRST_REVISED - pd.DateOffset(months=1))} and revised afterwards. "
        "* Geely, GAC and Foton first appear in Jan 2024; for GAC this is when its data was added to the registry, "
        "so it may not be its commercial launch. The shaded chip-shortage period is approximate (see Sources)."
    )

    # --- Chart C: how much of the recovery is explained by the brand panel?
    st.subheader("C. Is the recovery real, or explained by new brands?")
    all_roll = monthly(base).rolling(12).sum()
    stable_roll = monthly(base[base["stable_brand"]]).rolling(12).sum()
    a = all_roll[(all_roll.index >= start) & (all_roll.index <= end)]
    s = stable_roll[(stable_roll.index >= start) & (stable_roll.index <= end)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=a.index, y=a.values, mode="lines", name="All reporting brands",
                             line=dict(color=BLUE, width=2), hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra>All brands</extra>"))
    fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", name=f"Stable brands only ({N_STABLE})",
                             line=dict(color=MUTED, width=2), fill="tonexty", fillcolor="rgba(42,120,214,0.12)",
                             hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra>Stable brands</extra>"))
    if a.notna().any():
        end_label(fig, a.index[-1], a.dropna().iloc[-1], "All", BLUE)
        end_label(fig, s.index[-1], s.dropna().iloc[-1], "Stable", INK2)
    add_events(fig, start, end, macro=True, registry=False)
    style(fig, height=380, ytitle="Units in the last 12 months", right=60, top=40)
    show(fig, pd.DataFrame({"Month": a.index.strftime("%b %Y"), "All brands": a.values, "Stable brands": s.values}).dropna())
    st.caption("The blue shaded gap is the sales of brands that entered or left the registry. It ignores the Brand panel filter on purpose.")

    last12_all = sales[sales["date"] > LAST - pd.DateOffset(months=12)]
    gap_now = (1 - last12_all[last12_all["stable_brand"]]["units"].sum() / last12_all["units"].sum()) * 100
    growth_full = pct_change(full_now, full_prev)
    pace_word = "modestly" if growth_full < 10 else "strongly"
    pre = pct_change(full_2019, full_2016)
    takeaway(
        f"The market is growing {pace_word} ({fmt_pct(growth_full)} Jan-Oct vs the same months of 2025), so entering means "
        f"winning share from incumbents rather than riding a boom. The slide started before COVID-19 (Jan-Oct 2019 was "
        f"{fmt_pct(pre, 0)} vs 2016), which makes 2019 a low baseline. "
        f"Brands that entered or left the registry now make up {gap_now:.0f}% of the last 12 months of sales: "
        "newcomers are a real part of the story, and they are already taking volume."
    )

# ===============================================================
# SECTION 02: Where is the opportunity?
# ===============================================================
with tab2:
    # 12-month windows for growth (full registry, no filters, for the headline)
    cut = LAST - pd.DateOffset(months=12)
    cut2 = LAST - pd.DateOffset(months=24)

    def seg_growth(frame):
        last12 = frame[frame["date"] > cut].groupby("segment")["units"].sum()
        prev12 = frame[(frame["date"] <= cut) & (frame["date"] > cut2)].groupby("segment")["units"].sum()
        out = pd.DataFrame({"last12": last12, "prev12": prev12}).fillna(0)
        out["growth"] = [pct_change(a, b) for a, b in zip(out["last12"], out["prev12"])]
        out["share"] = out["last12"] / out["last12"].sum() * 100
        return out

    g_full = seg_growth(sales)
    biggest = g_full["share"].idxmax()
    fastest = g_full["growth"].idxmax()
    headline(
        f"{biggest} are the largest segment ({g_full.loc[biggest, 'share']:.0f}% of units), "
        f"but {fastest} grew fastest ({fmt_pct(g_full.loc[fastest, 'growth'])}) in the last 12 months"
    )
    st.caption("Headlines and takeaways describe the full registry. The charts below respond to the filters.")

    # --- Chart A: mix over time
    st.subheader("A. What Mexicans buy: the mix has shifted")
    dim = st.radio("Group vehicles by", ["Segment", "Vehicle type"], horizontal=True)
    col = "segment" if dim == "Segment" else "vehicle_type"
    colors = SEGMENT_COLORS if dim == "Segment" else TYPE_COLORS
    order = [c for c in (SEGMENT_ORDER if dim == "Segment" else ["Cars", "Light trucks"]) if c in set(view[col])]

    years = list(range(start.year, end.year + 1))
    mix = (view[(view["month"] <= LAST_M) & (view["year"].isin(years))]
           .groupby(["year", col])["units"].sum().unstack(fill_value=0).reindex(years, fill_value=0))
    share = mix.div(mix.sum(axis=1).replace(0, float("nan")), axis=0)
    fig = go.Figure()
    for c in order:
        if c in share:
            fig.add_trace(go.Bar(x=[str(y) for y in share.index], y=share[c], name=c, marker_color=colors[c],
                                 marker_line_color=SURFACE, marker_line_width=2,
                                 hovertemplate="%{x} | " + c + ": %{y:.1%}<extra></extra>"))
    fig.update_layout(barmode="stack")
    style(fig, height=380, yfmt=".0%", ytitle=f"Share of Jan-{month_label(LAST)[:3]} units")
    show(fig, (share * 100).round(1).reset_index().rename(columns={"year": "Year"}))

    # --- Chart B: growth by segment, last 12 months vs the 12 before
    st.subheader("B. Which segments are growing? Last 12 months vs the 12 before")
    g = seg_growth(view).dropna(subset=["growth"]).sort_values("growth")
    fig = go.Figure(go.Bar(
        x=g["growth"], y=g.index, orientation="h", marker_color=BLUE, marker_line_color=SURFACE, marker_line_width=2,
        text=[f"{v:+.1f}%" for v in g["growth"]], textposition="outside", cliponaxis=False,
        customdata=g[["share", "last12"]].values,
        hovertemplate="%{y}: %{x:+.1f}%<br>Share of units: %{customdata[0]:.1f}%<br>"
                      "Units last 12 months: %{customdata[1]:,.0f}<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color=AXIS, width=1))
    style(fig, height=340, yfmt=None, top=20)
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor=GRID, title="Change in units")
    fig.update_yaxes(title=None, gridcolor=SURFACE)
    show(fig)

    # --- Table: segment x origin (opportunity table)
    st.subheader("C. Opportunity table: size, growth and how each segment is supplied")
    last12 = view[view["date"] > cut]
    rows = []
    for seg, row in seg_growth(view).sort_values("last12", ascending=False).iterrows():
        sub = last12[last12["segment"] == seg]
        imp = sub[sub["origin"] == "Imported"]["units"].sum() / sub["units"].sum() * 100 if sub["units"].sum() else None
        rows.append({"Segment": seg, "Units, last 12 months": row["last12"], "Share of units (%)": row["share"],
                     "Growth vs previous 12 months (%)": row["growth"], "Imported share (%)": imp})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "Units, last 12 months": st.column_config.NumberColumn(format="localized"),
        "Share of units (%)": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100),
        "Growth vs previous 12 months (%)": st.column_config.NumberColumn(format="%+.1f"),
        "Imported share (%)": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
    })
    st.caption("Vehicle type is not a separate axis here because it is nested inside the segment "
               "(SUVs and pick-ups are all light trucks; compact and subcompact are all cars).")

    big_segments = g_full[g_full["share"] >= 5]          # compare only segments that matter in size
    weakest = big_segments["growth"].idxmin()
    suv_share_2016 = sales[(sales["year"] == 2016) & (sales["month"] <= LAST_M)]
    suv_pick_2016 = suv_share_2016[suv_share_2016["segment"].isin(["SUVs", "Pick-ups"])]["units"].sum() / suv_share_2016["units"].sum() * 100
    now_rows = sales[(sales["year"] == LAST_Y) & (sales["month"] <= LAST_M)]
    suv_pick_now = now_rows[now_rows["segment"].isin(["SUVs", "Pick-ups"])]["units"].sum() / now_rows["units"].sum() * 100
    takeaway(
        f"SUVs and pick-ups went from {suv_pick_2016:.0f}% of Jan-Oct units in 2016 to {suv_pick_now:.0f}% in {LAST_Y}: "
        f"that is where the volume is. But size is not the same as momentum: {fastest} grew {fmt_pct(g_full.loc[fastest, 'growth'])} "
        f"while {weakest} ({g_full.loc[weakest, 'share']:.0f}% of units) moved {fmt_pct(g_full.loc[weakest, 'growth'])}. "
        f"The evidence points to a SUV or crossover as the lead model; {fastest.lower()} may be worth testing as a volume entry point."
    )

# ===============================================================
# SECTION 03: Who owns the market?
# ===============================================================
with tab3:
    def brand_shares(frame, year):
        t = frame[(frame["year"] == year) & (frame["month"] <= LAST_M)].groupby("brand")["units"].sum()
        return t / t.sum() * 100 if t.sum() else t

    sh_2019, sh_now = brand_shares(sales, 2019), brand_shares(sales, LAST_Y)
    top5_2019, top5_now = sh_2019.nlargest(5).sum(), sh_now.nlargest(5).sum()
    n_2019, n_now = int((sh_2019 > 0).sum()), int((sh_now > 0).sum())
    headline(
        f"The five largest brands hold {top5_now:.0f}% of the market, down from {top5_2019:.0f}% in 2019, "
        f"while brands with sales rose from {n_2019} to {n_now}"
    )
    st.caption("Headlines and takeaways describe the full registry. The charts below respond to the filters.")

    # --- Chart A: brand ranking
    st.subheader("A. Who sells the most vehicles?")
    years_avail = [y for y in range(2016, LAST_Y + 1)]
    ycol, ncol = st.columns([1, 1])
    year_sel = ycol.selectbox("Year (Jan-Oct)", years_avail[::-1], index=0)
    top_n = ncol.slider("Brands to show", 8, 20, 12)
    sh = brand_shares(view, year_sel).nlargest(top_n)
    order_brands = list(sh.index)
    fig = go.Figure()
    for label, flag, color in [("Chinese brands*", True, ORANGE), ("Other brands", False, BLUE)]:
        sel = [b for b in order_brands if (b in CHINESE_BRANDS) == flag]
        fig.add_trace(go.Bar(x=[sh[b] for b in sel], y=sel, orientation="h", name=label, marker_color=color,
                             marker_line_color=SURFACE, marker_line_width=2,
                             hovertemplate="%{y}: %{x:.1f}% of units<extra></extra>"))
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(order_brands)))
    style(fig, height=max(340, 28 * len(order_brands) + 90), yfmt=None)
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor=GRID, title="Share of Jan-Oct units")
    fig.update_yaxes(gridcolor=SURFACE)
    show(fig, sh.round(2).rename("Share (%)").reset_index().rename(columns={"brand": "Brand"}))
    st.caption("*Brand nationality is not in the INEGI data. It is our classification by parent company "
               "(MG: British heritage, Chinese-owned; MOTORNATION is a distributor of BAIC and Changan models).")

    # --- Chart B: who is winning and losing share?
    st.subheader("B. Who is gaining and losing share?")
    base_year = st.radio("Compare with", [2016, 2019], index=1, horizontal=True, key="share_base")
    s_old, s_new = brand_shares(view, base_year), brand_shares(view, LAST_Y)
    chg = pd.DataFrame({"old": s_old, "new": s_new}).fillna(0)
    chg = chg[(chg["old"] >= 1) | (chg["new"] >= 1)]
    chg["change"] = chg["new"] - chg["old"]
    chg = chg.sort_values("change")
    labels = [f"{v:+.1f}" if (i < 3 or i >= len(chg) - 3) else "" for i, v in enumerate(chg["change"])]
    fig = go.Figure(go.Bar(
        x=chg["change"], y=chg.index, orientation="h", marker_color=[BLUE if v >= 0 else RED for v in chg["change"]],
        marker_line_color=SURFACE, marker_line_width=2, text=labels, textposition="outside", cliponaxis=False,
        customdata=chg[["old", "new"]].values,
        hovertemplate="%{y}: %{x:+.1f} pts<br>" + str(base_year) + ": %{customdata[0]:.1f}%<br>"
                      + str(LAST_Y) + ": %{customdata[1]:.1f}%<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=AXIS, width=1))
    style(fig, height=max(340, 26 * len(chg) + 80), yfmt=None, top=20)
    fig.update_xaxes(showgrid=True, gridcolor=GRID, title=f"Change in share of Jan-Oct units, {base_year} to {LAST_Y} (percentage points)")
    fig.update_yaxes(gridcolor=SURFACE)
    show(fig, chg.round(2).reset_index().rename(columns={"brand": "Brand", "old": f"Share {base_year} (%)",
                                                         "new": f"Share {LAST_Y} (%)", "change": "Change (pts)"}))
    st.caption("Blue = gaining share, red = losing share. Only brands with at least 1% share in one of the two years. "
               "Part of a brand's gain or loss can come from brands joining or leaving the registry.")

    # --- Where are vehicles built? Origin and the tariff question
    st.subheader("C. Where are the vehicles built?")
    years = list(range(start.year, end.year + 1))
    org = (view[(view["month"] <= LAST_M) & (view["year"].isin(years))]
           .groupby(["year", "origin"])["units"].sum().unstack(fill_value=0).reindex(years, fill_value=0))
    fig = go.Figure()
    for o in ["Made in Mexico", "Imported"]:
        if o in org:
            fig.add_trace(go.Bar(x=[str(y) for y in org.index], y=org[o], name=o, marker_color=ORIGIN_COLORS[o],
                                 marker_line_color=SURFACE, marker_line_width=2,
                                 hovertemplate="%{x} | " + o + ": %{y:,.0f}<extra></extra>"))
    fig.update_layout(barmode="stack")
    style(fig, height=340, ytitle=f"Units, January to {month_label(LAST)[:3]}")
    show(fig, org.reset_index().rename(columns={"year": "Year"}))
    if len(org) and "Imported" in org and org.iloc[0].sum() and org.iloc[-1].sum():
        st.caption(f"Imported share of Jan-Oct units: {org['Imported'].iloc[0] / org.iloc[0].sum() * 100:.1f}% in {org.index[0]} "
                   f"to {org['Imported'].iloc[-1] / org.iloc[-1].sum() * 100:.1f}% in {org.index[-1]}.")

    st.markdown("**Did the January 2026 tariffs slow imports from the affected countries?**")
    st.caption("Mexico applied tariffs of up to 50% on cars from countries without a free-trade agreement "
               "from 1 Jan 2026, with China, India, South Korea, Thailand and Indonesia named in press reports. "
               "This compares Jan-Oct 2026 with Jan-Oct 2025 in the registry. It is a description, not proof of cause.")
    imports = view[view["origin"] == "Imported"]
    groups = {
        "China": imports["origin_country"] == "China",
        "India, S. Korea, Thailand, Indonesia": imports["origin_country"].isin(TARIFF_OTHER_ORIGINS),
        "Other imports": ~imports["origin_country"].isin(["China"] + TARIFF_OTHER_ORIGINS),
    }
    cols = st.columns(4)
    for col_, (name, mask) in zip(cols, groups.items()):
        a_now, a_prev = ytd(imports[mask], LAST_Y), ytd(imports[mask], LAST_Y - 1)
        col_.metric(name, fmt(a_now), fmt_pct(pct_change(a_now, a_prev)), delta_color="off")
    mx = view[view["origin"] == "Made in Mexico"]
    cols[3].metric("Made in Mexico", fmt(ytd(mx, LAST_Y)), fmt_pct(pct_change(ytd(mx, LAST_Y), ytd(mx, LAST_Y - 1))), delta_color="off")

    cn = monthly(imports[groups["China"]])
    oth = monthly(imports[~groups["China"]])
    cn, oth = cn[(cn.index >= start) & (cn.index <= end)], oth[(oth.index >= start) & (oth.index <= end)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cn.index, y=cn.values, mode="lines", name="Imported from China",
                             line=dict(color=ORANGE, width=2), hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra>China</extra>"))
    fig.add_trace(go.Scatter(x=oth.index, y=oth.values, mode="lines", name="Imported from other countries",
                             line=dict(color=VIOLET, width=2), hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra>Other imports</extra>"))
    if len(cn):
        end_label(fig, cn.index[-1], cn.iloc[-1], "China", ORANGE)
        end_label(fig, oth.index[-1], oth.iloc[-1], "Other", VIOLET)
    add_events(fig, start, end, macro=True, registry=False)
    style(fig, height=380, ytitle="Units per month", right=60, top=40)
    show(fig, pd.DataFrame({"Month": cn.index.strftime("%b %Y"), "From China": cn.values, "Other imports": oth.values}))

    # Countries table (Jan-Oct)
    ctab = pd.DataFrame({
        f"Jan-Oct {LAST_Y - 1}": imports[(imports["year"] == LAST_Y - 1) & (imports["month"] <= LAST_M)].groupby("origin_country")["units"].sum(),
        f"Jan-Oct {LAST_Y}": imports[(imports["year"] == LAST_Y) & (imports["month"] <= LAST_M)].groupby("origin_country")["units"].sum(),
    }).fillna(0)
    ctab["Change (%)"] = [pct_change(b, a) for a, b in zip(ctab.iloc[:, 0], ctab.iloc[:, 1])]
    ctab["Named in tariff reports"] = ["Yes" if c in ["China"] + TARIFF_OTHER_ORIGINS else "" for c in ctab.index]
    ctab = ctab.sort_values(f"Jan-Oct {LAST_Y}", ascending=False).head(10).reset_index().rename(columns={"origin_country": "Country of origin"})
    st.dataframe(ctab, hide_index=True, width="stretch", column_config={
        f"Jan-Oct {LAST_Y - 1}": st.column_config.NumberColumn(format="localized"),
        f"Jan-Oct {LAST_Y}": st.column_config.NumberColumn(format="localized"),
        "Change (%)": st.column_config.NumberColumn(format="%+.1f"),
    })

    cn_brands = imports[groups["China"] & (imports["month"] <= LAST_M) & (imports["year"] >= LAST_Y - 1)]
    cb = cn_brands.pivot_table(index="brand", columns="year", values="units", aggfunc="sum", fill_value=0)
    if len(cb):
        cb = cb.sort_values(LAST_Y, ascending=False).head(8).reset_index()
        cb.columns = [str(c) for c in cb.columns]   # year columns as text
        cb["Chinese brand*"] = ["Yes" if b in CHINESE_BRANDS else "No" for b in cb["brand"]]
        with st.expander("Which brands bring the vehicles built in China?"):
            st.dataframe(cb.rename(columns={"brand": "Brand"}), hide_index=True, width="stretch")
            st.caption("Vehicles built in China are not only from Chinese brands: established brands also import from China. "
                       "That is why we separate country of manufacture (INEGI) from brand nationality (our classification).")

    cn_now, cn_prev = ytd(sales[(sales["origin_country"] == "China")], LAST_Y), ytd(sales[(sales["origin_country"] == "China")], LAST_Y - 1)
    takeaway(
        f"Competition is fragmenting: the top five brands lost {top5_2019 - top5_now:.0f} points of share since 2019 and "
        f"{n_now - n_2019} more brands now sell vehicles. Vehicles built in China are {fmt_pct(pct_change(cn_now, cn_prev))} in "
        f"Jan-Oct {LAST_Y} vs {LAST_Y - 1}, the first ten months of the tariffs, so the registry shows no slowdown yet. "
        "That does not prove the tariffs have no effect: it covers only ten months and has no price or import-cost data."
    )

# ===============================================================
# SECTION 04: What can we learn from newcomers?
# ===============================================================
ENTRANTS = coverage[(coverage["first_month"] >= "2017-01-01") & (coverage["total_units"] >= 20000)] \
    .sort_values("total_units", ascending=False)["brand"].tolist()
ENTRANT_COLOR = dict(zip(ENTRANTS, BRAND_COLORS))   # a brand keeps its color in every chart


def brand_series(frame, brand):
    """Monthly units of a brand from its first month in the registry.
    A brand that stopped appearing is cut at its last month with sales (we do not know if it stopped selling)."""
    row = coverage[coverage["brand"] == brand].iloc[0]
    end_month = LAST if row["last_month"] >= LAST else row["last_month"]
    idx = pd.date_range(row["first_month"], end_month, freq="MS")
    return frame[frame["brand"] == brand].groupby("date")["units"].sum().reindex(idx, fill_value=0)


def months_to(series, threshold):
    """Months since first sale until the 3-month average reaches a monthly level."""
    reached = series.rolling(3).mean()
    hit = reached[reached >= threshold]
    return None if hit.empty else int(reached.index.get_loc(hit.index[0]))


entrant_info = []
for b in ENTRANTS:
    srs = brand_series(sales, b)
    brand_rows = sales[sales["brand"] == b]
    entrant_info.append({
        "brand": b, "series": srs,
        "first": coverage.loc[coverage["brand"] == b, "first_month"].iloc[0],
        "last": coverage.loc[coverage["brand"] == b, "last_month"].iloc[0],
        "m1k": months_to(srs, 1000), "m3k": months_to(srs, 3000),
        "imported": brand_rows[brand_rows["origin"] == "Imported"]["units"].sum() / brand_rows["units"].sum() * 100,
        "origin": brand_rows.groupby("origin_country")["units"].sum().idxmax(),
    })
info = {e["brand"]: e for e in entrant_info}

with tab4:
    imported_all = [e for e in entrant_info if e["imported"] >= 99]
    local = [e for e in entrant_info if e["imported"] < 50]
    mostly = [e for e in entrant_info if 50 <= e["imported"] < 99]
    best = min([e for e in entrant_info if e["m3k"] is not None], key=lambda e: e["m3k"], default=None)
    headline(
        f"{best['brand']} reached 3,000 units a month in {best['m3k']} months; "
        f"{len(imported_all)} of {len(entrant_info)} newcomers came 100% imported"
        if best else "Newcomers: no brand has reached 3,000 units a month yet"
    )
    st.caption("This section uses the segment and origin filters, but ignores the Brand panel filter.")

    st.warning(
        "**Read with care.** 'Month 0' is the first month a brand appears in the registry, which is not always its commercial "
        "launch: GAC's data was added back to Jan 2024, and Geely and Foton also start that month. BYD, the best-known newcomer, "
        "does not report to INEGI, so it cannot be benchmarked here. Chirey stops appearing after Mar 2025."
    )

    st.subheader("A. How fast do newcomers grow? Cumulative units since the first month in the registry")
    c_a, c_b = st.columns([3, 1])
    chosen = c_a.multiselect("Brands to compare", ENTRANTS, default=ENTRANTS[:5], max_selections=8)
    horizon = c_b.slider("Months shown", 12, 60, 36)

    fig = go.Figure()
    table_rows = []
    for b in chosen:
        srs = brand_series(base, b).iloc[: horizon + 1]
        cum = srs.cumsum()
        x = list(range(len(srs)))
        fig.add_trace(go.Scatter(x=x, y=cum.values, mode="lines", name=b, line=dict(color=ENTRANT_COLOR[b], width=2),
                                 hovertemplate="Month %{x}: %{y:,.0f} cumulative units<extra>" + b + "</extra>"))
        marks = [m for m in (12, 24) if m < len(srs)]       # milestone markers at month 12 and 24
        fig.add_trace(go.Scatter(x=marks, y=[cum.iloc[m] for m in marks], mode="markers", showlegend=False,
                                 marker=dict(color=ENTRANT_COLOR[b], size=9, line=dict(color=SURFACE, width=2)),
                                 hovertemplate="Month %{x}: %{y:,.0f}<extra>" + b + "</extra>"))
        left_registry = info[b]["last"] < LAST and len(srs) == len(brand_series(base, b)) and len(srs) <= horizon + 1
        if left_registry:   # mark where the brand stops appearing in the registry
            fig.add_trace(go.Scatter(x=[x[-1]], y=[cum.iloc[-1]], mode="markers", showlegend=False,
                                     marker=dict(symbol="x", color=ENTRANT_COLOR[b], size=11, line=dict(width=2)),
                                     hovertemplate="Last month in registry: " + month_label(info[b]["last"]) + "<extra>" + b + "</extra>"))
        if len(chosen) <= 4:
            end_label(fig, x[-1], cum.iloc[-1], b, INK2)
        table_rows.append({"Brand": b, **{f"Month {m}": cum.iloc[m] if m < len(cum) else None for m in (6, 12, 24, 36)}})
    style(fig, height=420, ytitle="Cumulative units", right=90 if len(chosen) <= 4 else 20)
    fig.update_xaxes(title="Months since first month in the registry", showgrid=True, gridcolor=GRID, dtick=6)
    show(fig, pd.DataFrame(table_rows) if table_rows else None)
    st.caption("Dots mark month 12 and month 24. An X marks the last month a brand appears in the registry.")

    st.subheader("B. How quickly did each brand reach meaningful monthly volume?")
    def num(v):
        return "-" if v is None else f"{v:,.0f}"

    rows = []
    for e in entrant_info:
        s_ = e["series"]
        rows.append({
            "Brand": e["brand"],
            "First month": month_label(e["first"]),
            "Status": "Active" if e["last"] >= LAST else f"Last sales {month_label(e['last'])}",
            "Units, year 1": num(s_.iloc[:12].sum() if len(s_) >= 12 else None),
            "Units, year 2": num(s_.iloc[12:24].sum() if len(s_) >= 24 else None),
            "Months to 1,000/month": num(e["m1k"]),
            "Months to 3,000/month": num(e["m3k"]),
            "Imported (%)": e["imported"],
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "Imported (%)": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
    })
    st.caption(
        "Brands with at least 20,000 units in the registry that first appear in 2017 or later (full registry, no filters). "
        "'Months to X/month' uses the 3-month average of monthly units; '-' means the level was never reached. "
        "A year shows '-' if the brand has less than that much history."
    )

    loc_txt = ", ".join(f"{e['brand']} ({e['m1k']} months to 1,000 a month)" if e["m1k"] is not None else f"{e['brand']} (never reached 1,000)" for e in local)
    takeaway(
        f"Pace varies a lot: " + (f"{best['brand']} took {best['m1k']} months to reach 1,000 units a month and {best['m3k']} to reach 3,000. " if best else "")
        + f"Chirey was quick to 1,000 ({info['Chirey']['m1k']} months) but never reached 3,000 and disappears from the registry after Mar 2025: "
        "a fast start did not guarantee staying power. "
        f"{len(imported_all)} of {len(entrant_info)} newcomers came 100% imported"
        + (f" and {len(mostly)} more mostly imported ({', '.join(e['brand'] for e in mostly)})" if mostly else "")
        + f"; the one built in Mexico was {loc_txt or 'none'}. "
        "That is a small sample, so it is a pattern to test, not a rule."
    )

# ===============================================================
# SECTION 05: How should we enter?
# ===============================================================
with tab5:
    headline("Lead with a SUV, expect years rather than months to reach scale, and plan for tariffs on the import route")
    st.caption("Everything in this section uses the full registry (no filters). It builds on sections 01 to 04.")

    # --- A. Market attractiveness
    st.subheader("A. Market attractiveness")
    ma1, ma2, ma3, ma4 = st.columns(4)
    ma1.metric(f"Units, Jan-{month_label(LAST)[:3]} {LAST_Y}", fmt(full_now), fmt_pct(pct_change(full_now, full_prev)) + f" vs {LAST_Y - 1}")
    ma2.metric("Vs same months of 2019", fmt_pct(pct_change(full_now, full_2019)))
    ma3.metric("Top-5 brands' share", f"{top5_now:.1f}%", f"{top5_now - top5_2019:+.1f} pts vs 2019", delta_color="off")
    ma4.metric("Brands with sales", f"{n_now}", f"{n_now - n_2019:+d} vs 2019", delta_color="off")

    # --- B. Evidence for the entry decision
    st.subheader("B. What the evidence says about how to enter")
    e1, e2, e3 = st.columns(3)
    with e1:
        with st.container(border=True):
            st.markdown("**Which vehicle**")
            st.write(f"{biggest} are the largest segment ({g_full.loc[biggest, 'share']:.0f}% of units, "
                     f"{fmt_pct(g_full.loc[biggest, 'growth'])}). {fastest} grew fastest ({fmt_pct(g_full.loc[fastest, 'growth'])}).")
    with e2:
        with st.container(border=True):
            st.markdown("**How to supply it**")
            st.write(f"{len(imported_all)} of {len(entrant_info)} newcomers came 100% imported. "
                     + (f"{local[0]['brand']}, built in Mexico, was the slowest to scale." if local and local[0]['m1k'] else ""))
    with e3:
        with st.container(border=True):
            st.markdown("**How fast**")
            reached = sorted([e for e in entrant_info if e["m3k"] is not None], key=lambda e: e["m3k"])
            names = " and ".join(f"{e['brand']} ({e['m3k']} months)" for e in reached)
            st.write((f"{names} reached 3,000 units a month; " if reached else "No newcomer has reached 3,000 units a month; ")
                     + f"the other {len(entrant_info) - len(reached)} have not.")

    # --- C. Benchmark scenarios built from observed newcomer paces
    st.subheader("C. Benchmark scenarios: what newcomers actually achieved")
    st.caption(
        "These are not forecasts. For each year after a brand's first sale we take the slowest, the median and the fastest "
        "result among newcomers with a full year of history (brands that left the registry are excluded after they leave). "
        "They need explicit assumptions on distribution, product and capacity before being used as targets."
    )
    market_12m = sales[sales["date"] > cut]["units"].sum()
    scen_rows = []
    for k in (1, 2, 3):
        results = {}
        for e in entrant_info:
            srs = e["series"]
            if len(srs) >= 12 * k:
                results[e["brand"]] = srs.iloc[12 * (k - 1): 12 * k].sum()
        if results:
            r = pd.Series(results)
            scen_rows.append({"Year after first sale": f"Year {k}", "Brands (n)": len(r),
                              "Conservative (slowest)": r.min(), "Base (median)": round(r.median()), "Accelerated (fastest)": r.max(),
                              "Slowest brand": r.idxmin(), "Fastest brand": r.idxmax()})
    scen = pd.DataFrame(scen_rows)
    if not scen.empty:
        fig = go.Figure()
        for name, color in [("Conservative (slowest)", BLUE), ("Base (median)", ORANGE), ("Accelerated (fastest)", AQUA)]:
            fig.add_trace(go.Bar(x=scen["Year after first sale"], y=scen[name], name=name, marker_color=color,
                                 marker_line_color=SURFACE, marker_line_width=2,
                                 hovertemplate="%{x} | " + name + ": %{y:,.0f} units (%{customdata:.1f}% of the market)<extra></extra>",
                                 customdata=scen[name] / market_12m * 100))
        fig.update_layout(barmode="group")
        style(fig, height=360, ytitle="Units sold in the year")
        show(fig)
        st.dataframe(scen, hide_index=True, width="stretch", column_config={
            "Conservative (slowest)": st.column_config.NumberColumn(format="localized"),
            "Base (median)": st.column_config.NumberColumn(format="localized"),
            "Accelerated (fastest)": st.column_config.NumberColumn(format="localized"),
        })
        fastest_last = scen.iloc[-1]
        st.caption(
            f"For scale: the fastest {fastest_last['Year after first sale'].lower()} result ({fmt(fastest_last['Accelerated (fastest)'])} units, "
            f"{fastest_last['Fastest brand']}) equals {fastest_last['Accelerated (fastest)'] / market_12m * 100:.1f}% of the last-12-month market "
            f"({fmt(market_12m)} units). The sample is {int(fastest_last['Brands (n)'])} brands in that year, so the range is wide and the median is not a reliable central estimate. "
            "JAC (assembled in Mexico) and MOTORNATION (a distributor) set the slowest results, so the conservative case is a floor, "
            "not a likely outcome for a new importer."
        )

    # --- D. Recommendations
    st.subheader("D. Recommendations")
    cn_all_now = ytd(sales[sales["origin_country"] == "China"], LAST_Y)
    cn_all_prev = ytd(sales[sales["origin_country"] == "China"], LAST_Y - 1)
    recs = [
        f"**Lead with a SUV or crossover and test a subcompact variant.** {biggest} are {g_full.loc[biggest, 'share']:.0f}% of units "
        f"and grew {fmt_pct(g_full.loc[biggest, 'growth'])}; {fastest.lower()} grew {fmt_pct(g_full.loc[fastest, 'growth'])}.",
        f"**Plan to take share, not ride growth.** The market is {fmt_pct(pct_change(full_now, full_prev))} on 2025 and "
        f"{fmt_pct(pct_change(full_now, full_2016), 0)} vs 2016 (Jan-Oct). The top five brands lost {top5_2019 - top5_now:.0f} points of share since 2019, "
        "which is the opening newcomers have used.",
        ("**Benchmark the ramp on the successful cases, not on the average.** "
         + (f"{best['brand']} needed {best['m1k']} months to reach 1,000 units a month and {best['m3k']} to reach 3,000; " if best else "")
         + "Chirey shows a quick start can still end with the brand disappearing from the registry."),
        f"**Expect to enter as an importer.** {len(imported_all)} of {len(entrant_info)} newcomers did. "
        + (f"The only brand built in Mexico, {local[0]['brand']}, scaled slowest. " if local else "")
        + "This is an observation from few brands, not proof that local assembly is a worse route.",
        f"**Stress-test sourcing against tariffs.** Cars from countries without a trade agreement face up to 50% tariffs since Jan 2026. "
        f"The registry shows vehicles built in China {fmt_pct(pct_change(cn_all_now, cn_all_prev))} in Jan-Oct {LAST_Y}, so no visible slowdown yet, "
        "but the registry has no prices or import costs. Treat this as an open risk to model with trade data.",
    ]
    for i, r in enumerate(recs, 1):
        st.markdown(f"{i}. {r}")

    # --- E. Limits of the data
    st.subheader("E. What this registry cannot see")
    st.markdown(
        "- **Brands that do not report.** BYD is absent, and other brands enter, leave or are added back in time (table below). "
        "Newcomer volumes are a lower bound.\n"
        "- **Prices and margins.** Units only: we cannot say which segment is profitable, or what a price position would cost.\n"
        "- **Imports by origin for non-reporting brands, and vehicle-level costs.** Origin country is reported only for brands in the registry.\n"
        "- **Where the vehicles are sold inside Mexico.** There is no state or dealer breakdown in this table.\n"
        "- **Brand nationality.** Not in the data; we classified it ourselves.\n"
        "- **Revisions.** Figures from Nov 2023 are 'revised' and can change; rows with zero units were dropped and 24 negative corrections were kept."
    )
    with st.expander("Brand coverage in the registry (full table)"):
        cov_view = coverage.copy()
        cov_view["first_month"] = cov_view["first_month"].dt.strftime("%b %Y")
        cov_view["last_month"] = cov_view["last_month"].dt.strftime("%b %Y")
        cov_view = cov_view.rename(columns={
            "brand": "Brand", "first_month": "First month with sales", "last_month": "Last month with sales",
            "months_reported": "Months with sales", "total_units": "Total units", "stable_brand": "Stable brand"})
        st.dataframe(cov_view, hide_index=True, width="stretch")

    fast = [e["brand"] for e in entrant_info if e["m3k"] is not None and e["m3k"] <= 24]
    takeaway(
        "The case for entering rests on a market that is stable rather than booming, with incumbents ceding share and some newcomers "
        f"({', '.join(fast) if fast else 'none so far'}) reaching 3,000 units a month within two years. The case against is that the evidence on newcomers is thin, "
        "tariffs on non-FTA imports are new, and the registry cannot show prices or profitability. A go decision should come with a "
        "sourcing plan that does not depend on tariff-exposed imports."
    )

# ---------------------------------------------------------------
# 7. Sources and method
# ---------------------------------------------------------------
with st.expander("Sources and method"):
    st.markdown(
        "**Data.** INEGI, Registro Administrativo de la Industria Automotriz de Vehículos Ligeros (RAIAVL), monthly sales 2016 to "
        "Oct 2026, revised figures (file modified 2026-11-09). https://www.inegi.org.mx/datosprimarios/iavl/\n\n"
        "**Cleaning (clean_data.py).** Brands harmonized (Chrysler and Fiat into Stellantis; JETOUR and Jetour Soueast as one brand), "
        "monthly dates built from year and month, status of figures kept, zero-unit rows dropped, negative corrections kept. "
        "A brand is 'stable' if it appears from Jan 2016 to Oct 2026.\n\n"
        "**Events on the charts (sources are press and trade reports, not the official gazette):**\n"
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
        "[Automotive World](https://www.automotiveworld.com/news/mexico-hits-chinese-made-cars-with-50-tariffs/)).\n"
        "- Registry changes (brands joining, leaving or added back) come from the INEGI data itself and the INEGI methodological notes."
    )
