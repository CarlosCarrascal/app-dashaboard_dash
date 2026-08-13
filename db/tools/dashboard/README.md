# Tablero de impacto agronómico y aporte predictivo

Aplicación Streamlit sobre `docs/data/IA.final.xlsx` (campaña 2025) y cruza `M_Poda.xlsx`
para agregar el reloj biológico de poda. Arma el panel
**Fundo × Módulo × Semana** y separa tres resultados: asociación agronómica observada,
aporte predictivo y explicación de XGBoost con SHAP. La inferencia causal queda marcada
como trabajo futuro hasta incorporar poda, fases y varias campañas.

```bash
npm run dashboard                                  # localiza el Python de conda solo
npm run dashboard -- --server.address=localhost    # que no salga de la máquina
```

Dependencias declaradas en `db/tools/pyproject.toml`, instaladas por `npm run setup`.

A mano: `pip install -e db/tools`.

Para apuntar a otro archivo sin tocar el código: `AQUANQA_XLSX=ruta/al/archivo.xlsx`.

## Estado actualizado de poda

`M_Poda.xlsx` ya se cruza al cargar el panel como proxy de reloj biol�gico. La inferencia
causal sigue pendiente porque faltan fases fenol�gicas observadas, manejo completo y
varias campa�as.

## Secciones

Se eligen en el menú lateral, y **solo se calcula la que está abierta**.

| Sección | Contenido | En frío |
|---|---|---|
| **Pregunta, datos y límites** | Objetivo, capas de resultado, grano y tamaño efectivo | ~5 s |
| **Conclusiones y hallazgos** | Lectura unificada de asociación, poda, frutos, peso y límites | ~1 s |
| **Impacto agronómico** | Relación con kg/ha, calendario, desfases, placebo, módulos, frutos y peso; GDD/forma quedan como diagnósticos técnicos | 0,3 s |
| **Qué explica el R²** | Techo, importancia por grupos, aporte marginal y validación | a demanda |
| **Modelo predictivo** | Modelos simples, XGBoost, ventanas y calibración | a demanda |
| **Explicación del modelo** | SHAP global y auditoría de una celda | 0,6 s |
| **Datos y calidad** | Hallazgos, panel filtrable y exportación | 0,5 s |
| **Marco metodológico y referencias** | Fuentes, alcance y datos necesarios antes de DML | 0,1 s |

Los bloques caros (aporte marginal ~17 s, esquemas ~10 s, comparación de familias ~7 s)
se calculan **a demanda**, detrás de un selector, y quedan en caché.

## Cómo está organizado

```
app.py                    menú lateral, cabecera y despacho de secciones
config.py                 variables, etiquetas, glosario, hiperparámetros, paleta, iconos
estilo.py                 la hoja de estilo
datos_origen.py           el control que elige qué Excel entra
verificar_capas.py        comprueba que lo de abajo siga siendo cierto

nucleo/                   cálculo puro · NO importa Streamlit ni Plotly
    datos.py                  Excel → Panel + hallazgos de calidad
    clima.py                  el estudio estadístico completo
    modelo.py                 ajuste XGBoost + SHAP + verificación de consistencia
    evaluacion.py             conjuntos, particiones, referencias, plan de validación
    exportar.py               el motor del .xlsx (formato)
    informe.py                qué hojas lleva el .xlsx y cómo se explican

servicios/                orquestación y caché
vistas/                   una sección por módulo, cada una con render()
```

**Las dependencias van en un solo sentido:** `vistas` → `servicios` → `núcleo` → `config`,
y `núcleo/` no conoce Streamlit ni Plotly:

```python
from nucleo import cargar_panel, clima
panel = cargar_panel(open("docs/data/IA.final.xlsx", "rb").read())
print(clima.correlacion_parcial(clima.agregar_por_semana(panel.tabla)))
```

Ambas reglas están verificadas: `python db/tools/dashboard/verificar_capas.py`.

## El riego: qué se corrigió

El archivo trae dos columnas de riego **agregadas con criterios distintos**: `m3/ha` es la
**suma** sobre los turnos y `Lt/planta` la **media**. Se detecta desde el propio archivo —
el cociente entre ambas es constante dentro de cada módulo pero salta entre módulos en
proporción entera, que es la firma de un conteo de turnos, no de un caudal.

El análisis usa **`Lt/planta`**, que es la columna al grano del módulo. `m3/ha` se conserva
solo para mostrar y su magnitud **no** debe leerse como lámina de riego: da 171 mm/semana
contra una ETo de 29, casi seis veces la demanda hídrica. Datos y calidad lo advierte.

No hay lógica de turnos en ninguna parte del código: si el archivo trae la columna, se
consolida a módulo al leer y no vuelve a aparecer.

## El grano semanal del clima

Temperatura, radiación, ETo y DPV traen **un valor por semana**, común a los 18 módulos.
Eso **representa bien la realidad** —dentro del fundo no varían de un módulo al vecino— y
tiene dos consecuencias que el tablero hace explícitas:

1. El **n efectivo es 50 semanas, no 452 celdas**. Un intervalo de confianza calculado
   sobre las celdas saldría 3,0 veces más estrecho de lo correcto.
2. Ninguna variable climática puede explicar las diferencias **entre módulos de la misma
   semana**, porque vale lo mismo para todos.

## Caché y rerenderizado

- **`@st.cache_resource`** para el ajuste del modelo (`cache_data` copiaría 376 KB por
  acceso).
- **`@st.cache_data`** para todo lo demás, incluida la lectura del Excel (por ruta y
  `mtime`).
- **`@st.fragment`** en las vistas con controles.
- **Renderizado perezoso**: una sección por corrida, y dentro de las caras, un bloque por
  corrida.

`n_jobs=1` en XGBoost a propósito: con 452 filas repartir un ajuste entre hilos cuesta más
de lo que ahorra (17,4 s contra 18,8 s), y fija el resultado. El paralelismo entre
configuraciones se probó y se descartó — ver el docstring de `en_paralelo`.

`st.session_state` conserva la sección activa y las ventanas del modelo. Los cálculos se
invalidan cuando cambia esa configuración.

## Lo que hay que saber antes de usarlo

**Es una herramienta de auditoría, no de pronóstico.** Ninguna variable climática sobrevive
al control del calendario, y una onda senoidal sin significado físico correlaciona con el
rendimiento (r = −0,918) más fuerte que la temperatura mínima (−0,706). El análisis
completo está en
[`docs/modelo/03_relacion_clima_riego_kgha_2025.md`](../../../docs/modelo/03_relacion_clima_riego_kgha_2025.md).

En **Impacto agronómico**, la ruta principal responde en orden: asociación bruta, control
del calendario, desfases, placebo, consistencia por módulo y descomposición en frutos/peso.
GDD y la forma univariada se mantienen dentro de **Diagnósticos técnicos** porque no
responden por sí solos qué variable tiene mayor impacto real. Una ventana de 7 semanas
es una media móvil de calendario, no una fase fenológica; el modelo lo muestra en su
auditoría de desfases.
