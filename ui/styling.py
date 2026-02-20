# ui/styling.py
import pandas as pd

PALETA = {
    "VERDE": "#C6EFCE",
    "AMARILLO": "#FFEB9C",
    "ROJO": "#FFC7CE",
    "NA": "#E7E6E6",
    "": "#FFFFFF"
}

EMOJI = {
    "VERDE": "🟢",
    "AMARILLO": "🟡",
    "ROJO": "🔴",
    "NA": "⚪",
    "": "⚪"
}

def map_emoji(v: str) -> str:
    return EMOJI.get(str(v), "⚪")

def style_semaforo_column(df: pd.DataFrame, col: str):
    def colorize(val):
        color = PALETA.get(str(val), "#FFFFFF")
        return f"background-color: {color}; font-weight: 600;"
    if hasattr(df, "style"):
        return df.style.applymap(colorize, subset=pd.IndexSlice[:, [col]])
    return df

def style_matrix(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    # Aplica color por celda en todas las columnas salvo "Propiedad"
    def colorize(val):
        color = PALETA.get(str(val), "#FFFFFF")
        return f"background-color: {color}; font-weight: 600; text-align: center;"
    cols = [c for c in df.columns if c != "Propiedad"]
    return df.style.applymap(colorize, subset=pd.IndexSlice[:, cols])
