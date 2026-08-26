"""Shared color palette — used by KPI cards, charts, and status badges alike
so a color always means the same thing everywhere in the dashboard.
"""
from utils.calculations import STATUS_AMAN, STATUS_TIDAK_AMAN

COLOR_AMAN = "#0ca30c"
COLOR_TIDAK_AMAN = "#d03b3b"
COLOR_WARNING = "#c98500"
COLOR_NEUTRAL = "#52514e"

STATUS_COLOR_MAP = {STATUS_AMAN: COLOR_AMAN, STATUS_TIDAK_AMAN: COLOR_TIDAK_AMAN}

SERIES_BLUE = "#2a78d6"
SERIES_ORANGE = "#eb6834"

SEQUENTIAL_BLUE = ["#cde2fb", "#86b6ef", "#3987e5", "#184f95"]
