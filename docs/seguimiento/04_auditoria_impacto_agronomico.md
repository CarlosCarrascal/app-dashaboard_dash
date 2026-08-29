# Auditoría de continuidad · Impacto agronómico

**Fecha:** 2026-08-18
**Objeto:** `apps/dashboard/pages/impacto/*` y `packages/analitica/nucleo/clima.py`
**Pregunta:** si el módulo permite un análisis agronómico serio y si está alineado con el
objetivo de explicar y proyectar frutos por planta, peso de baya y rendimiento.

> **Copia versionada** de `.md/contexto-impacto-agronomico-2026-08-18.md`.
> La carpeta `.md/` está ignorada por Git
> (`.gitignore:54`), así que este archivo es el que sobrevive a un clon limpio y
> manda si ambos divergen. Replica aquí todo cambio de fondo.

## Veredicto ejecutivo

**Impacto agronómico es útil, pero su alcance real es diagnóstico observacional.** No es una
capa causal, no es un modelo de proyección y no debe publicar sus valores p o sus “mejores
rezagos” como evidencia de manejo.

La mayor fortaleza es que detecta correctamente el problema central de la campaña: las
variables climáticas semanales comparten el calendario de cosecha y pueden parecer factores
agronómicos aunque solo estén siguiendo la misma estación. El placebo de una onda anual incluso
correlaciona más con el rendimiento que las variables climáticas reales.

La mayor debilidad es que las pruebas visibles todavía son exploratorias: usan correlaciones
con p-valores convencionales, controles polinómicos y búsqueda de rezagos, pero no incorporan
en esta capa corrección por múltiples pruebas, errores HAC, bootstrap temporal por bloques,
modelos longitudinales o una estrategia de identificación causal. La capa nueva de
`/analitica/*` ya contiene parte de esa infraestructura; Impacto agronómico todavía no la
consume como fuente única de claims.

**Clasificación recomendada:** conservarlo como **diagnóstico observacional** y como interfaz
de descubrimiento, pero no usarlo como fuente oficial de conclusiones causales ni de
proyecciones. Sus resultados deben migrar progresivamente a `analytics.evidence_claim`, con
snapshot, método, incertidumbre, corrección por multiplicidad y etiqueta de evidencia.

## 1. Qué contiene actualmente

El grupo tiene cuatro páginas:

- **Evidencia:** correlación semanal clima–kg/ha, control polinómico del calendario, rezagos y
  placebo.
- **Por módulo:** correlaciones dentro de cada módulo y relación entre el inicio de cosecha y
  el signo de la correlación.
- **Frutos y peso:** separa el objetivo en frutos por planta y peso del fruto, revisa
  trayectorias, peaks, floración y rezagos.
- **Descubrimientos:** sigue siendo un placeholder de contenido pendiente; no publica una
  síntesis ejecutiva generada desde claims persistidos.

La capa usa principalmente `nucleo.clima`. No utiliza XGBoost ni SHAP para presentar la
asociación climática, lo cual es correcto: una explicación interna de un modelo no sustituye
el análisis agronómico.

## 2. Datos y grano real de la campaña

La ejecución local con las fuentes actuales produjo:

| Elemento | Estado observado |
|---|---:|
| Celdas módulo-semana | 452 |
| Módulos/celdas analizadas | 18 |
| Fundos | 4 |
| Semanas calendario | 50, de S01 a S52 con huecos |
| Campaña de poda | C2025 |
| Variedad | Sekoya Pop en todas las filas |
| Frutos y peso completos | 433 celdas; 19 faltantes |
| Floración disponible | 317 celdas; 135 faltantes |
| Observaciones de floración con rezago | 301 en rezago 0; 177 en rezago 8 |

El clima está correctamente tratado como una medición del fundo por semana: cada variable
climática tiene exactamente un valor dentro de cada semana. Por tanto, para clima el tamaño
efectivo es aproximadamente **50 semanas**, no 452 celdas.

La poda está integrada a nivel de módulo desde lotes. Esto es mejor que ignorarla, pero sigue
siendo un proxy: la dispersión de poda dentro del módulo no desaparece al usar una fecha
promedio. En la base actual hay módulos con dispersión relevante y no todos los lotes tienen
una fecha perfectamente completa.

## 3. Qué resultados sí son informativos

### 3.1 Clima y rendimiento

En el agregado semanal, la asociación cruda más fuerte fue:

- temperatura mínima: `r = -0,706`, IC95 % `[-0,823; -0,532]`;
- GDD acumulado: `r = +0,662`;
- GDD semanal: `r = -0,653`;
- temperatura máxima: `r = -0,572`;
- DPV: `r = -0,504`.

Estos números son descriptivos, no efectos. La prueba de placebo es decisiva: la onda anual
del seno obtuvo `r = -0,918`, por encima de todas las variables físicas. La serie ficticia
conoce la semana, no la planta. Esto demuestra que la forma estacional explica una parte
importante de la asociación observada.

Al descontar la semana mediante un polinomio de grado 5, ninguna de las ocho variables
climáticas quedó con `p < 0,05` en la implementación actual. El control por días desde poda
dejó a DPV con `p = 0,040`, pero es un resultado nominal entre varias pruebas y no está
corregido por multiplicidad.

La lectura rigurosa es: **en esta campaña no se identifica un efecto climático independiente
del calendario con la precisión suficiente para recomendar una intervención.** Esto no prueba
que el clima sea fisiológicamente irrelevante; prueba que este diseño observacional no separa
su efecto del calendario de poda/cosecha.

### 3.2 Variación entre módulos

La página “Por módulo” aporta un control de realidad importante: el signo de la correlación no
es uniforme. La asociación entre el inicio de cosecha y la correlación dentro del módulo es
alta para varias variables, por ejemplo:

- temperatura máxima: `r = +0,799`, `p nominal = 0,00007`;
- DPV: `r = +0,794`, `p nominal = 0,00008`;
- GDD semanal: `r = +0,714`, `p nominal = 0,00086`.

Esto respalda la hipótesis de que la ventana observada de cada módulo cambia la lectura. No es
una estimación causal del clima y tampoco prueba que todos los módulos sean réplicas
independientes: comparten el mismo termómetro, calendario y parte de la estructura productiva.

### 3.3 Separación de frutos y peso

La separación es conceptualmente correcta porque el rendimiento puede descomponerse como:

```text
kg/ha = plantas productivas/ha × frutos por planta × peso medio de baya / 1000
```

En la implementación actual, después del control polinómico del calendario se observaron:

| Objetivo | Señales nominales `p < 0,05` en la interfaz | Resultado `q` aproximado tras BH dentro del objetivo |
|---|---|---|
| Frutos | Riego `r = +0,315`, `p = 0,026` | No queda bajo `q < 0,05`; `q ≈ 0,156` |
| Peso | Riego `r = -0,515`, `p = 0,00013`; TempMin `r = +0,375`, `p = 0,0073`; Rad `r = -0,342`, `p = 0,015`; ETo `r = -0,300`, `p = 0,035` | Riego, TempMin y Rad sobreviven; ETo queda limítrofe `q ≈ 0,052` |

La tabla BH es una sensibilidad calculada sobre las seis pruebas de cada objetivo. Si se
consideran simultáneamente los objetivos, rezagos, controles y familias de variables, el
umbral efectivo debe ser todavía más conservador.

Por eso no es correcto comunicar “el riego causa más frutos” o “la temperatura mínima aumenta
el peso”. La lectura válida es: **hay patrones candidatos distintos para cantidad y tamaño,
que deben probarse en una base longitudinal con estructura de lote, planta y manejo.**

### 3.4 Floración hacia frutos

La prueba `flores → frutos` es la pieza más cercana a una relación biológica temporal porque
usa dos mediciones internas y controla el promedio de módulo además del calendario. En la
campaña actual, la mayor asociación controlada fue aproximadamente `r = +0,305` a 5–6 semanas
de rezago, con 203–217 celdas y los 18 módulos.

Es una señal prometedora, pero sigue siendo observacional y está concentrada en una sola
campaña. No estima todavía:

- proporción de cuajado `frutos/flores`;
- supervivencia por etapa E1–E5;
- efecto de polinización;
- densidad de plantas productivas;
- peso final condicionado a la carga frutal.

La literatura experimental respalda que polinización, cuajado, número de semillas y peso de
baya pueden actuar como componentes distintos del rendimiento, por lo que medir flores y
frutos por separado es una buena dirección. El estudio de polinización de arándano expresa el
rendimiento mediante componentes de plantas, estructuras, frutos por estructura, cuajado y
peso, pero esa formulación experimental aún no está implementada aquí. [Estudio experimental
de componentes de rendimiento y polinización](https://pmc.ncbi.nlm.nih.gov/articles/PMC4938509/)

## 4. Defectos metodológicos que impiden llamarlo inferencia seria

### 4.1 P-valores sin HAC ni dependencia temporal

Las correlaciones semanales y los residuos del polinomio se evalúan con `pearsonr`. Ese cálculo
asume observaciones independientes para sus p-valores. Las semanas consecutivas tienen
autocorrelación climática y productiva, y la curva de cosecha es suave; por tanto, el número
nominal de 50 semanas sobrestima la información efectiva.

Como sensibilidad externa, al ajustar regresiones semanales con errores HAC de hasta cuatro
rezagos, los p-valores cambian sustancialmente frente a los p-valores convencionales. Después
del control polinómico, la única señal nominal con HAC menor que 0,05 fue TempMin (`p ≈ 0,008`),
pero ninguna de las ocho señales quedó bajo BH a `q < 0,05` (`q` mínimo aproximado `0,065`).

Esto no reemplaza el modelo oficial; demuestra que el módulo no debe mostrar significancia
convencional como si fuera inferencia longitudinal.

### 4.2 Multiplicidad y selección post hoc de rezagos

La página busca el mejor rezago entre 0 y 8 semanas para 7 predictores y varios objetivos.
Entre kg/ha, Frutos, Peso y Floración se exploran hasta 252 combinaciones antes de escoger el
mejor resultado. El código sí advierte cuando muchas combinaciones eligen el máximo de 8
semanas, pero no ajusta los p-valores ni separa selección y confirmación.

Por ejemplo, los mejores rezagos actuales incluyen muchos máximos en 7–8 semanas. Eso puede
ser una señal biológica, pero también el resultado esperado de buscar el máximo entre muchos
intentos sobre 50 semanas.

La selección de rezago debe pasar a folds internos temporales y la afirmación final debe
reportar la distribución completa, no solo el máximo.

### 4.3 Control polinómico de grado 5

El polinomio absorbe la forma de la campaña y es mejor que no controlar nada, pero no equivale
a controlar el calendario de forma causal. Con 50 semanas, grado 5 puede retirar señal real,
dejar residuos con autocorrelación o ser sensible a los extremos. La sensibilidad debe incluir
splines regularizados, términos de calendario predefinidos, GDD desde poda y modelos mixtos;
no solo una cifra con grado fijo.

### 4.4 Ponderación inconsistente del estimando

`kg/ha` se calcula con kilos y área, mientras que `agregar_por_semana` resume con medias simples:

- riego: media simple de módulos;
- Frutos: media simple de módulos;
- Peso: media simple de módulos;
- kg/ha: ponderado por área.

En la ejecución actual, la correlación de rendimiento semanal con riego cambia de
aproximadamente `r = 0,157` usando el promedio simple a `r = 0,005` usando riego ponderado
por área. En Frutos el cambio es pequeño (`0,976` frente a `0,977`), y en Peso cambia de
`0,090` a `0,138`.

No significa automáticamente que el promedio simple sea incorrecto: podría representar el
módulo típico. El problema es que el módulo no declara si su estimando es módulo típico,
planta típica o producción del fundo. Para decisiones de rendimiento debe fijarse y
versionarse la ponderación por área, plantas o estructuras productivas.

### 4.5 Componentes biológicos sin identidad completa

El panel calcula `Frutos` y `Peso`, pero no tiene todavía una densidad de plantas productivas
por módulo/semana que cierre la identidad de kg/ha. La razón observada

```text
kg/ha / (Frutos × Peso)
```

tiene mediana aproximadamente `5,82` y outliers de hasta `67,2`, compatibles en parte con
diferencias de densidad o con celdas pequeñas, pero no auditables como una identidad exacta
sin el denominador de plantas.

La corrección necesaria no es correlacionar más: es incorporar plantas productivas, estructuras
por planta, flores, cuajado, frutos y peso al mismo grano de lote/módulo, con unidades y reglas
de agregación explícitas.

### 4.6 Ventanas observadas que no representan etapas biológicas

“Peak”, “inicio”, “final” y “cuatro semanas pre-peak” se calculan sobre la ventana observada de
cada módulo. No son equivalentes a E1–E5 ni a una fase BBCH. Comparar el peso inicial con el
final de dos módulos que empiezan en semanas diferentes mezcla etapa biológica, fecha de
observación y disponibilidad de cosecha.

La evidencia experimental muestra que el crecimiento del fruto de arándano sigue una dinámica
aproximadamente doble sigmoidal, con fases rápidas y lentas; por ello una línea única o una
ventana calendario fija no debe interpretarse como crecimiento fisiológico. [Desarrollo
celular y curva doble sigmoidal del fruto de arándano](https://pmc.ncbi.nlm.nih.gov/articles/PMC10929238/)

### 4.7 Ausencia de intervención y confundidores críticos

El módulo no puede estimar efectos causales de riego, DPV o temperatura porque el manejo puede
responder al estado observado del cultivo. Por ejemplo, regar más cuando el módulo viene
estresado crea causalidad inversa: el riego aparece asociado a peor peso aunque haya sido una
respuesta correctiva.

La evidencia experimental de riego en arándano muestra que el agua puede afectar el rendimiento
bajo tratamientos definidos, pero también que el efecto depende de variedad, edad, método y
nivel de reposición de ETo. El estudio de siete años en Chile fue realizado en Bluetta y bajo
condiciones específicas; no entrega un coeficiente transferible a Sekoya Pop–Trujillo. [Ensayo
de irrigación en arándano en Chile](https://doi.org/10.1016/j.agwat.2004.02.008)

## 5. Relación con el objetivo no negociable

| Pregunta | ¿Impacto agronómico actual la responde? | Veredicto |
|---|---|---|
| ¿Qué variables se mueven con kg/ha? | Sí, descriptivamente | Útil como cribado; no causal |
| ¿La relación sobrevive al calendario? | Parcialmente | Control exploratorio; falta HAC/BH/robustez |
| ¿Se repite por módulo? | Sí, con correlaciones | Diagnóstico de heterogeneidad; no réplica causal |
| ¿Afecta frutos o peso? | Parcialmente | Buena separación conceptual, pero sin modelo de componentes |
| ¿Floración anticipa frutos? | Sí, como asociación temporal | Prometedora; no valida cuajado ni intervención |
| ¿Predice frutos/planta? | No | Solo analiza observaciones actuales |
| ¿Predice peso de baya? | No | Solo analiza observaciones actuales |
| ¿Proyecta kg por lote-semana? | No | Esa función pertenece a `/analitica/proyeccion` |
| ¿Persiste claims auditables? | No en esta capa | La fuente oficial debe ser `analytics.evidence_claim` |
| ¿Demuestra causalidad? | No | No hay intervención ni diseño causal |

## 6. Qué debe conservarse

No conviene eliminar el módulo. Tiene cuatro activos importantes:

- hace visible la diferencia entre señal estacional y señal física;
- usa un placebo comprensible para usuarios no estadísticos;
- obliga a separar frutos y peso en lugar de esconder todo en kg/ha;
- introduce módulo, poda y floración como controles que la capa predictiva necesita.

Debe conservarse como una vista de diagnóstico, pero con una etiqueta explícita de alcance:

> **Diagnóstico observacional de relaciones y componentes. No estima efectos causales ni
> constituye un pronóstico operativo.**

## 7. Qué debe cambiar para alinearlo con la plataforma oficial

### Prioridad alta

1. Sustituir los p-valores aislados por resultados provenientes de
   `analytics.evidence_claim`, con snapshot, método, clase de evidencia, intervalo, tamaño
   efectivo y estado de multiplicidad.
2. Aplicar bootstrap temporal por bloques y HAC en las relaciones semanales.
3. Ajustar BH por familia de hipótesis y reportar cuántas pruebas se hicieron antes de escoger
   un rezago.
4. Fijar el estimando y la ponderación: módulo típico, planta típica o fundo ponderado por
   área/plantas.
5. Evitar presentar el “mejor rezago” como descubrimiento hasta seleccionarlo en folds internos
   y confirmarlo en folds externos.

### Prioridad media

6. Reemplazar el polinomio fijo de grado 5 por una comparación de controles: spline regularizado,
   GDD desde poda, días desde poda y efectos de campaña/módulo.
7. Incorporar modelos mixtos para el tramo flores → frutos y frutos → peso, con interceptos por
   módulo/lote y errores agrupados.
8. Añadir controles negativos y placebos de resultado/intervención, no solo ondas estacionales.
9. Completar el DAG visible con poda → floración → cuajado → frutos → peso → kg y registrar
   confundidores, mediadores y variables no observadas.

### Datos que desbloquean el objetivo

10. Plantas productivas y densidad por lote/módulo.
11. Estructuras productivas por planta y frutos por estructura.
12. Flores, cuajado y supervivencia con fechas/etapas comparables por lote.
13. Polinización, suelo, nutrición y manejo con fechas as-of.
14. Fenología y cosecha de varias campañas, no únicamente C2025.
15. Pronóstico meteorológico futuro para convertir relaciones históricas en proyección.

## 8. Decisión operativa

**No eliminar. No usar como fuente de promoción ni como módulo de predicción.**

La decisión recomendada es mantener “Impacto agronómico” como diagnóstico observacional y
conectar sus resultados con la capa oficial de relaciones. El modelo de producción debe leer
las conclusiones versionadas de `analytics.evidence_claim`, no recalcular p-valores diferentes
cada vez que se abre la página.

La proyección oficial seguirá usando el torneo temporal de `/analitica/proyeccion`. Impacto
agronómico debe responder “qué relación merece ser investigada y con qué limitación”, mientras
que la capa oficial responde “qué evidencia se confirmó fuera de muestra y qué decisión se
puede tomar”.

## 9. Fuentes científicas usadas para interpretar los hallazgos

- Desarrollo de fruto y curva doble sigmoidal: [Cytological characteristics of blueberry fruit development](https://pmc.ncbi.nlm.nih.gov/articles/PMC10929238/).
- Componentes de rendimiento y polinización: [Contrasting Pollinators and Pollination in Native and Non-Native Regions of Highbush Blueberry Production](https://pmc.ncbi.nlm.nih.gov/articles/PMC4938509/).
- Efecto de riego bajo tratamientos experimentales en Chile: [Effect of irrigation on fruit production in blueberry](https://doi.org/10.1016/j.agwat.2004.02.008).
- Variación de temperatura base y fenología: [Highbush blueberry bloom phenology](https://journals.ashs.org/downloadpdf/view/journals/hortsci/47/9/article-p1291.pdf).

Estas fuentes justifican hipótesis y variables; no autorizan a transferir coeficientes a Sekoya
Pop–Trujillo sin calibración local.

El catálogo `docs/cientifico/catalogo_evidencia.json` fue actualizado a la versión `1.1.0` para
registrar también las fuentes metodológicas empleadas para interpretar el módulo: el artículo
original de [SHAP](https://arxiv.org/abs/1705.07874), la distinción entre predicción e inferencia
causal de [Mooney, Keil y Westreich](https://doi.org/10.1093/aje/kwab047), el análisis causal de
relevancia de [Janzing, Minorics y Bloebaum](https://proceedings.mlr.press/v108/janzing20a.html),
la combinación de cribado ML y ajuste estadístico de [Madakkatel et al.](https://www.nature.com/articles/s41598-021-02476-9),
el flujo ML–causal ambiental de [Han et al.](https://doi.org/10.1016/j.isci.2024.109012) y la
revisión reciente de [Moccia et al.](https://doi.org/10.1007/s10654-024-01173-x). Estas fuentes
respaldan la metodología y las restricciones de interpretación; tampoco proporcionan
coeficientes agronómicos transferibles.

También se incorporaron las referencias fundacionales del [Random Forest](https://doi.org/10.1023/A:1010933404324),
de [XGBoost](https://doi.org/10.1145/2939672.2939785) y del control de pruebas múltiples de
[Benjamini–Hochberg](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x). Su función es documentar
algoritmos y controles estadísticos, no respaldar por sí mismas un efecto agronómico.
