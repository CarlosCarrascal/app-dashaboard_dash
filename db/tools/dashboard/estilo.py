"""Hoja de estilo del tablero.

Streamlit no expone tipografía ni densidad por configuración, así que se ajustan acá. El
alcance es deliberadamente estrecho: espaciado y jerarquía. **Ningún color de dato se toca
desde el CSS** — ésos viven en `config.py` y los aplica Plotly, para que lo que se ve en
pantalla sea lo mismo que sale exportado.

La navegación del menú lateral **no** se estiliza con CSS. Se probó y salió mal: dependía
de `:has()` y de acertarle a la estructura interna del widget de radio, que Streamlit
cambia entre versiones. Ahora son botones nativos, y el resaltado del activo lo hace
Streamlit con `type="primary"`. Menos control fino, pero se ve bien en cualquier versión
y en los dos temas.

Todo lo que queda se apoya en las variables de tema (`--text-color`,
`--secondary-background-color`), así que funciona igual en claro y en oscuro.
"""

from __future__ import annotations

import streamlit as st

CSS = """
<style>
  /* ── Lienzo ─────────────────────────────────────────────────────────── */
  .block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1400px; }

  h1 { font-size: 1.8rem; font-weight: 700; letter-spacing: -.02em; margin-bottom: .1rem; }
  h2 { font-size: 1.28rem; font-weight: 650; letter-spacing: -.01em; padding-top: .7rem; }
  h3 { font-size: 1.05rem; font-weight: 620; }
  hr { margin: 1.3rem 0; opacity: .16; }

  /* ── Menú lateral ───────────────────────────────────────────────────── */
  section[data-testid="stSidebar"] { width: 19rem !important; }
  section[data-testid="stSidebar"] > div { padding-top: 1.2rem; }
  section[data-testid="stSidebar"] hr { margin: .9rem 0; }

  /* Los botones de navegación, apretados y alineados a la izquierda.
     Streamlit centra el contenido del botón en varios niveles a la vez (el <button>, su
     <div> interno y el <p> del texto), así que hay que forzar los tres. */
  section[data-testid="stSidebar"] div[data-testid="stButton"] { margin-bottom: .15rem; }
  section[data-testid="stSidebar"] div[data-testid="stButton"] button {
      display: flex;
      justify-content: flex-start !important;
      text-align: left !important;
      padding: .36rem .7rem;
      min-height: 0;
      border-radius: .45rem;
  }
  section[data-testid="stSidebar"] div[data-testid="stButton"] button > div {
      justify-content: flex-start !important;
      text-align: left !important;
      width: 100%;
  }
  section[data-testid="stSidebar"] div[data-testid="stButton"] button p {
      font-size: .89rem;
      font-weight: 500;
      margin: 0;
      text-align: left !important;
      width: 100%;
  }

  /* El cargador de archivos, compacto: la línea de «200MB per file» ocupa más que el
     control en sí y no aporta nada en un tablero de uso interno. */
  section[data-testid="stSidebar"] div[data-testid="stFileUploader"] section {
      padding: .55rem .7rem;
      border-radius: .5rem;
      min-height: 0;
  }
  section[data-testid="stSidebar"] div[data-testid="stFileUploader"] section > div,
  section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzoneInstructions"]
      > div > small { display: none; }
  section[data-testid="stSidebar"] div[data-testid="stFileUploader"] button {
      padding: .2rem .7rem; font-size: .82rem; min-height: 0;
  }
  section[data-testid="stSidebar"] div[data-testid="stFileUploader"] span {
      font-size: .82rem;
  }

  /* ── Métricas ───────────────────────────────────────────────────────── */
  div[data-testid="stMetric"] {
      background: var(--secondary-background-color);
      border: 1px solid rgba(128,128,128,.18);
      border-radius: .6rem; padding: .7rem .9rem;
  }
  div[data-testid="stMetricLabel"] p { font-size: .76rem; opacity: .72; font-weight: 500; }
  div[data-testid="stMetricValue"] { font-size: 1.45rem; font-weight: 680;
                                     letter-spacing: -.02em; }
  div[data-testid="stMetricDelta"] { font-size: .74rem; }

  /* ── Contenedores, avisos, pestañas ─────────────────────────────────── */
  div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: .7rem; }
  div[data-testid="stAlert"] { border-radius: .6rem; font-size: .9rem; }
  div[data-testid="stAlert"] p { line-height: 1.5; }
  button[data-baseweb="tab"] { font-size: .9rem; padding: .35rem .1rem; }
  div[data-baseweb="tab-list"] { gap: 1.3rem; }
  div[data-testid="stDataFrame"] { border-radius: .5rem; }
  details summary { font-size: .9rem; font-weight: 550; }
  .stPlotlyChart { border-radius: .5rem; overflow: hidden; }

  /* ── Responsivo ─────────────────────────────────────────────────────── */
  @media (max-width: 900px) {
      .block-container { padding-left: 1rem; padding-right: 1rem; }
      div[data-testid="stMetricValue"] { font-size: 1.2rem; }
      h1 { font-size: 1.42rem; }
  }
</style>
"""


def aplicar() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
