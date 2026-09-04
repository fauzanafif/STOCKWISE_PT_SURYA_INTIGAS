"""Plotly visualizations for the inventory dashboard.

Colors follow a fixed, reserved role scheme:
  - Status (AMAN / TIDAK AMAN / BEP) always uses the same three colors everywhere.
  - Two-series comparisons (Sisa Stok vs Safety Stock) use fixed categorical
    slots 1 (blue) and 2 (orange), in that order, every time.
  - Pure-magnitude bars (e.g. top deficit) use a single sequential blue ramp.
"""
import plotly.express as px
import plotly.graph_objects as go

from utils.calculations import STATUS_AMAN, STATUS_BEP, STATUS_TIDAK_AMAN
from utils.theme import (
    COLOR_AMAN,
    COLOR_BEP,
    COLOR_TIDAK_AMAN,
    SEQUENTIAL_BLUE,
    SERIES_BLUE,
    SERIES_ORANGE,
    STATUS_COLOR_MAP,
)

CHART_FONT = dict(family="'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif")


def _style(fig, height=380):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=CHART_FONT,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(gridcolor="#dde6f4", zeroline=False)
    fig.update_yaxes(gridcolor="#dde6f4", zeroline=False)
    return fig


def status_donut(df):
    counts = df["Status"].value_counts().reindex([STATUS_AMAN, STATUS_TIDAK_AMAN, STATUS_BEP]).fillna(0)
    fig = go.Figure(
        data=[
            go.Pie(
                labels=counts.index,
                values=counts.values,
                hole=0.58,
                marker=dict(colors=[STATUS_COLOR_MAP[s] for s in counts.index]),
                sort=False,
                # % only on the slices; the color legend below says which is which.
                # "label+percent" on every slice made the small ones collide with
                # the legend and the centre.
                texttemplate="%{percent}",
                textposition="inside",
                hovertemplate="%{label}: %{value:,.0f} barang (%{percent})<extra></extra>",
            )
        ]
    )
    fig = _style(fig, height=340)
    # legend under the chart, not overlapping the title/centre
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center", x=0.5),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


def top_deficit_bar(df, top_n=10):
    data = df[df["Defisit"] > 0].sort_values("Defisit", ascending=False).head(top_n)
    if data.empty:
        return None
    label_col = "Deskripsi Barang" if "Deskripsi Barang" in data.columns else "Kode Barang"
    plot_df = data.sort_values("Defisit").copy()
    plot_df["_label"] = [_short(v) for v in plot_df[label_col]]
    fig = px.bar(
        plot_df,
        x="Defisit",
        y="_label",
        orientation="h",
        color="Defisit",
        color_continuous_scale=SEQUENTIAL_BLUE,
    )
    fig.update_coloraxes(showscale=False)
    fig.update_layout(yaxis_title="", xaxis_title="Kekurangan (unit)")
    return _style(fig, height=max(340, 34 * len(data)))


def _short(label, n=34):
    label = str(label)
    return label if len(label) <= n else label[: n - 1] + "…"


def stock_vs_safety_bar(df, top_n=10):
    # Only meaningful for items that are actually short of their safety stock —
    # otherwise the chart is a row of near-empty bars with unreadable labels.
    data = df[df["Defisit"] > 0].sort_values("Defisit", ascending=False).head(top_n)
    if data.empty:
        return None
    label_col = "Deskripsi Barang" if "Deskripsi Barang" in data.columns else "Kode Barang"
    data = data.iloc[::-1]  # biggest deficit on top for a horizontal bar
    labels = [_short(v) for v in data[label_col]]
    fig = go.Figure()
    fig.add_bar(name="Stok sekarang", y=labels, x=data["Sisa Stok"], orientation="h", marker_color=SERIES_BLUE)
    fig.add_bar(name="Batas aman", y=labels, x=data["Safety Stock"], orientation="h", marker_color=SERIES_ORANGE)
    fig.update_layout(barmode="group", xaxis_title="Qty", yaxis_title="")
    return _style(fig, height=max(320, 46 * len(data)))


def warehouse_status_bar(df):
    if "Letak Gudang" not in df.columns or df.empty:
        return None
    grouped = (
        df.groupby("Letak Gudang")["Status"]
        .value_counts()
        .unstack(fill_value=0)
        .reindex(columns=[STATUS_AMAN, STATUS_TIDAK_AMAN, STATUS_BEP], fill_value=0)
    )
    grouped = grouped.loc[grouped.sum(axis=1).sort_values(ascending=False).index]
    fig = go.Figure()
    fig.add_bar(name=STATUS_AMAN, x=grouped.index, y=grouped[STATUS_AMAN], marker_color=COLOR_AMAN)
    fig.add_bar(name=STATUS_TIDAK_AMAN, x=grouped.index, y=grouped[STATUS_TIDAK_AMAN], marker_color=COLOR_TIDAK_AMAN)
    fig.add_bar(name=STATUS_BEP, x=grouped.index, y=grouped[STATUS_BEP], marker_color=COLOR_BEP)
    fig.update_layout(barmode="stack", xaxis_title="", yaxis_title="Jumlah Barang")
    return _style(fig)


def warehouse_stock_bar(df):
    if "Letak Gudang" not in df.columns or df.empty:
        return None
    grouped = df.groupby("Letak Gudang")[["Sisa Stok", "Safety Stock"]].sum()
    grouped = grouped.loc[grouped["Sisa Stok"].sort_values(ascending=False).index]
    fig = go.Figure()
    fig.add_bar(name="Total Stok", x=grouped.index, y=grouped["Sisa Stok"], marker_color=SERIES_BLUE)
    fig.add_bar(name="Total Safety Stock", x=grouped.index, y=grouped["Safety Stock"], marker_color=SERIES_ORANGE)
    fig.update_layout(barmode="group", xaxis_title="", yaxis_title="Qty")
    return _style(fig)


def category_status_bar(df):
    if "Kategori Induk" not in df.columns or df.empty:
        return None
    grouped = (
        df.groupby("Kategori Induk")["Status"]
        .value_counts()
        .unstack(fill_value=0)
        .reindex(columns=[STATUS_AMAN, STATUS_TIDAK_AMAN, STATUS_BEP], fill_value=0)
    )
    grouped = grouped.loc[grouped.sum(axis=1).sort_values(ascending=False).index]
    fig = go.Figure()
    fig.add_bar(name=STATUS_AMAN, x=grouped.index, y=grouped[STATUS_AMAN], marker_color=COLOR_AMAN)
    fig.add_bar(name=STATUS_TIDAK_AMAN, x=grouped.index, y=grouped[STATUS_TIDAK_AMAN], marker_color=COLOR_TIDAK_AMAN)
    fig.add_bar(name=STATUS_BEP, x=grouped.index, y=grouped[STATUS_BEP], marker_color=COLOR_BEP)
    fig.update_layout(barmode="stack", xaxis_title="", yaxis_title="Jumlah Barang")
    return _style(fig)


def lead_time_scatter(df):
    if df.empty:
        return None
    label_col = "Deskripsi Barang" if "Deskripsi Barang" in df.columns else "Kode Barang"
    fig = px.scatter(
        df,
        x="Lead Time",
        y="Defisit",
        color="Status",
        color_discrete_map=STATUS_COLOR_MAP,
        size="Defisit" if df["Defisit"].sum() > 0 else None,
        hover_name=label_col,
        category_orders={"Status": [STATUS_AMAN, STATUS_TIDAK_AMAN, STATUS_BEP]},
    )
    fig.update_layout(xaxis_title="Lead Time", yaxis_title="Defisit")
    return _style(fig)
