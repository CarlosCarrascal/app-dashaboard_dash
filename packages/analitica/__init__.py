"""Núcleo analítico independiente de cualquier framework de interfaz.

El paquete no importa submódulos al inicializarse: así leer la configuración no obliga a
cargar XGBoost, SHAP o Plotly. Los consumidores importan explícitamente el submódulo que
necesitan.
"""
