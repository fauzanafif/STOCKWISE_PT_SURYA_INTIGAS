"""Plotly visualizations for the inventory dashboard.

Colors follow a fixed, reserved role scheme:
  - Status (AMAN / TIDAK AMAN) always uses the same two colors everywhere.
  - Two-series comparisons (Sisa Stok vs Safety Stock) use fixed categorical
    slots 1 (blue) and 2 (orange), in that order, every time.
  - Pure-magnitude bars (e.g. top deficit) use a single sequential blue ramp.
"""
import plotly.express as px
import plotly.graph_objects as go

from utils.calculations import STATUS_AMAN, STATUS_TIDAK_AMAN
from utils.theme import (
    COLOR_AMAN,
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
    counts = df["Status"].value_counts().reindex([STATUS_AMAN, STATUS_TIDAK_AMAN]).fillna(0)
    fig = go.Figure(
        data=[
            go.Pie(
                labels=counts.index,
                values=counts.values,
                hole=0.55,
                marker=dict(colors=[STATUS_COLOR_MAP[s] for s in counts.index]),
                sort=False,
            )
        ]
    )
    fig.update_traces(textinfo="label+percent")
    return _style(fig, height=340)


def top_deficit_bar(df, top_n=10):
    data = df[df["Defisit"] > 0].sort_values("Defisit", ascending=False).head(top_n)
    if data.empty:
        return None
    label_col = "Deskripsi Barang" if "Deskripsi Barang" in data.columns else "Kode Barang"
    fig = px.bar(
        data.sort_values("Defisit"),
        x="Defisit",
        y=label_col,
        orientation="h",
        color="Defisit",
        color_continuous_scale=SEQUENTIAL_BLUE,
    )
    fig.update_coloraxes(showscale=False)
    fig.update_layout(yaxis_title="", xaxis_title="Defisit")
    return _style(fig, height=max(340, 32 * len(data)))


def stock_vs_safety_bar(df, top_n=10):
    data = df.sort_values("Defisit", ascending=False).head(top_n)
    if data.empty:
        return None
    label_col = "Deskripsi Barang" if "Deskripsi Barang" in data.columns else "Kode Barang"
    fig = go.Figure()
    fig.add_bar(name="Sisa Stok", x=data[label_col], y=data["Sisa Stok"], marker_color=SERIES_BLUE)
    fig.add_bar(name="Safety Stock", x=data[label_col], y=data["Safety Stock"], marker_color=SERIES_ORANGE)
    fig.update_layout(barmode="group", xaxis_title="", yaxis_title="Qty")
    return _style(fig, height=380)


def warehouse_status_bar(df):
    if "Letak Gudang" not in df.columns or df.empty:
        return None
    grouped = (
        df.groupby("Letak Gudang")["Status"]
        .value_counts()
        .unstack(fill_value=0)
        .reindex(columns=[STATUS_AMAN, STATUS_TIDAK_AMAN], fill_value=0)
    )
    grouped = grouped.loc[grouped.sum(axis=1).sort_values(ascending=False).index]
    fig = go.Figure()
    fig.add_bar(name=STATUS_AMAN, x=grouped.index, y=grouped[STATUS_AMAN], marker_color=COLOR_AMAN)
    fig.add_bar(name=STATUS_TIDAK_AMAN, x=grouped.index, y=grouped[STATUS_TIDAK_AMAN], marker_color=COLOR_TIDAK_AMAN)
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
        .reindex(columns=[STATUS_AMAN, STATUS_TIDAK_AMAN], fill_value=0)
    )
    grouped = grouped.loc[grouped.sum(axis=1).sort_values(ascending=False).index]
    fig = go.Figure()
    fig.add_bar(name=STATUS_AMAN, x=grouped.index, y=grouped[STATUS_AMAN], marker_color=COLOR_AMAN)
    fig.add_bar(name=STATUS_TIDAK_AMAN, x=grouped.index, y=grouped[STATUS_TIDAK_AMAN], marker_color=COLOR_TIDAK_AMAN)
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
        category_orders={"Status": [STATUS_AMAN, STATUS_TIDAK_AMAN]},
    )
    fig.update_layout(xaxis_title="Lead Time", yaxis_title="Defisit")
    return _style(fig)
