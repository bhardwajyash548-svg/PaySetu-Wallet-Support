"""Shared chart pieces for the Dashboard and Admin Analytics pages (one consistent look)."""
import altair as alt
import pandas as pd
import streamlit as st

# Chart colours: fixed categorical order (validated palette), used by role, never cycled.
C_BLUE, C_ORANGE, C_AQUA, C_YELLOW, C_MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
INK, INK_2, GRID = "#0B2540", "#52606D", "#E6EDF3"


CHART_CSS = """
<style>
.block-container { max-width: 1180px !important; }
/* White cards around each chart (the bordered block that directly holds a card title) */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .ps-card-title) {
  background: #fff; border: 1px solid #DCE6EF !important; border-radius: 16px;
  box-shadow: 0 4px 18px rgba(11,37,64,.06); padding: 16px 18px;
}
.ps-card-title { font-weight: 700; color: #0B2540; font-size: 1.02rem; margin: 0 0 2px; }
.ps-card-sub { color: #52606D; font-size: .82rem; margin: 0 0 6px; }
/* KPI tiles */
.ps-kpis { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 14px; margin: 4px 0 18px; }
@media (max-width: 900px) { .ps-kpis { grid-template-columns: repeat(2, minmax(0,1fr)); } }
.ps-kpi { background: #fff; border: 1px solid #DCE6EF; border-radius: 16px; padding: 14px 16px;
  box-shadow: 0 4px 18px rgba(11,37,64,.06); position: relative; overflow: hidden; }
.ps-kpi::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 5px; background: var(--accent); }
.ps-kpi .lbl { color: #52606D; font-size: .82rem; display: flex; gap: 6px; align-items: center; }
.ps-kpi .val { color: #0B2540; font-size: 1.9rem; font-weight: 800; line-height: 1.15; margin-top: 4px; }
.ps-kpi .sub { color: #52606D; font-size: .76rem; }
.ps-meter { height: 6px; background: #E6EDF3; border-radius: 99px; margin-top: 8px; overflow: hidden; }
.ps-meter > span { display: block; height: 100%; background: #1baf7a; border-radius: 99px; }
/* Top questions list */
.ps-q { display: grid; grid-template-columns: 26px 1fr auto; gap: 10px; align-items: center;
  padding: 8px 0; border-bottom: 1px solid #EEF2F6; }
.ps-q:last-child { border-bottom: 0; }
.ps-q .rank { width: 26px; height: 26px; border-radius: 8px; background: #E8F1FB; color: #1554A6;
  font-weight: 800; font-size: .8rem; display: flex; align-items: center; justify-content: center; }
.ps-q .txt { color: #0B2540; font-size: .9rem; }
.ps-q .bar { height: 5px; background: #E6EDF3; border-radius: 99px; margin-top: 5px; }
.ps-q .bar > span { display: block; height: 100%; background: #2a78d6; border-radius: 99px; }
.ps-q .n { color: #0B2540; font-weight: 700; font-size: .9rem; }
.ps-sample { background: #FFF7E6; border: 1px solid #F5D08A; color: #7A4B00; border-radius: 12px;
  padding: 8px 12px; font-size: .85rem; margin-bottom: 12px; }
.ps-pill-high { background:#FDE8E8; color:#B42318; border-radius:999px; padding:2px 10px; font-size:.82rem; }
.ps-pill-normal { background:#E0F2FE; color:#075985; border-radius:999px; padding:2px 10px; font-size:.82rem; }
.ps-empty { color: #52606D; font-size: .88rem; padding: 18px 0; text-align: center; }
</style>
"""


def card(title, subtitle=""):
    box = st.container(border=True)
    box.markdown(f'<p class="ps-card-title">{title}</p>' + (f'<p class="ps-card-sub">{subtitle}</p>' if subtitle else ""),
                 unsafe_allow_html=True)
    return box


def style(chart):
    return (chart.configure(background="transparent").configure_view(stroke=None)
            .configure_axis(labelColor=INK_2, titleColor=INK_2, gridColor=GRID, domainColor=GRID, tickColor=GRID,
                            labelFontSize=12, titleFontSize=12)
            .configure_legend(labelColor=INK, titleColor=INK_2, labelFontSize=12, symbolType="circle"))


def hbar(df, label, value, color, height=None):
    base = alt.Chart(df).encode(
        y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=330, ticks=False, domain=False)),
        x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d", grid=True)),
        tooltip=[alt.Tooltip(f"{label}:N", title=label.capitalize()), alt.Tooltip(f"{value}:Q", title="Count")],
    )
    bars = base.mark_bar(color=color, cornerRadiusEnd=4, height={"band": 0.62})
    text = base.mark_text(align="left", dx=6, color=INK, fontWeight="bold").encode(text=f"{value}:Q")
    return style(bars + text).properties(height=height or max(120, 38 * len(df)))



def donut(df: pd.DataFrame, cat: str, value: str, domain: list[str], colors: list[str],
          center: str, center_sub: str, height: int = 250):
    """Donut for one whole split into a few parts (legend always shown, hover shows count and share)."""
    df = df.copy()
    df["share"] = df[value] / df[value].sum() if df[value].sum() else 0
    df["order"] = df[cat].map({c: i for i, c in enumerate(domain)})
    arc = alt.Chart(df).mark_arc(innerRadius=58, outerRadius=100, stroke="#fff", strokeWidth=2).encode(
        theta=alt.Theta(f"{value}:Q", stack=True),
        color=alt.Color(f"{cat}:N", scale=alt.Scale(domain=domain, range=colors),
                        legend=alt.Legend(title=None, orient="right")),
        order=alt.Order("order:Q"),
        tooltip=[alt.Tooltip(f"{cat}:N", title=cat.capitalize()), alt.Tooltip(f"{value}:Q", title="Count"),
                 alt.Tooltip("share:Q", title="Share", format=".0%")])
    c1 = alt.Chart(pd.DataFrame({"t": [center]})).mark_text(fontSize=26, fontWeight="bold", color=INK, dy=-8).encode(text="t:N")
    c2 = alt.Chart(pd.DataFrame({"t": [center_sub]})).mark_text(fontSize=12, color=INK_2, dy=15).encode(text="t:N")
    return style(arc + c1 + c2).properties(height=height)


def line(df: pd.DataFrame, x: str, y: str, color: str, y_title: str, domain: tuple | None = None, height: int = 220):
    """Line with points and a zero rule; hover shows the value."""
    scale = alt.Scale(domain=list(domain)) if domain else alt.Undefined
    base = alt.Chart(df).encode(x=alt.X(f"{x}:T", title=None, axis=alt.Axis(grid=False, labelAngle=0)),
                                y=alt.Y(f"{y}:Q", title=y_title, scale=scale))
    rule = alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(color="#9AA9B8", strokeDash=[4, 4]).encode(y="z:Q")
    path = base.mark_line(color=color, strokeWidth=2, interpolate="monotone")
    pts = base.mark_point(color=color, filled=True, size=70, stroke="#fff", strokeWidth=2).encode(
        tooltip=[alt.Tooltip(f"{x}:T", title="Time", format="%d %b %H:%M"), alt.Tooltip(f"{y}:Q", title=y_title)])
    return style(rule + path + pts).properties(height=height)
