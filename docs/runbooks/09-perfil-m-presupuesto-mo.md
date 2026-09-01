# Perfilado de M_PresupuestoMO

**Fecha:** 2026-08-30  
**Base:** aquanqa_migracion  
**Snapshot Access publicado:** 4 (BD_AQUANQA_26(1).accdb)  
**Objeto físico de Access:** M_PresupuetoMO  
**Decisión actual:** raw_only; no promover a core todavía.

El perfilado es reproducible y de solo lectura:

    node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/perfil_m_presupuesto_mo.sql

## Qué contiene la fuente

El catálogo físico de Access registra cinco columnas: Año, Semana, Fundo,
Evaluación y MOSem. No se detectaron índices ni clave primaria en el objeto de
Access. La tabla raw.m_presupuesto_mo conserva esos campos como texto, junto con
el linaje del snapshot y de cada fila; el tipado se comprueba durante el perfilado.

El prefijo M_ del nombre de Access no convierte la fuente en un maestro. Por su
contenido, esta tabla parece representar una planificación semanal de mano de obra:
la decisión de modelo queda pendiente hasta confirmar su semántica.

## Evidencia observada

| Control | Resultado |
|---|---:|
| Filas del snapshot publicado | 1.272 |
| Hashes de origen distintos | 1.272 |
| Filas extra por hash dentro del snapshot | 0 |
| Año observado | 2026 |
| Semana observada | 1–53 |
| Fundos distintos | 4 |
| Evaluaciones distintas | 6 |
| Campos de negocio vacíos | 0 |
| Valores MOSem inválidos o negativos | 0 |
| Valores MOSem iguales a cero | 504 |
| Valores MOSem positivos | 768 |
| Rango observado de MOSem | 0–34 |
| Total observado de MOSem | 4.600,62760386616 |

La unidad de MOSem no se deduce de los valores. No se convierte a horas,
personas, jornales ni otra unidad sin confirmación operativa.

## Grano y cobertura

La clave candidata observada es:

    (Año, Semana, Fundo, Evaluación)

No hay duplicados con esa clave. La fuente forma una grilla completa de
53 semanas × 4 fundos × 6 evaluaciones = 1.272 combinaciones.

Los vocabularios presentes son:

- Fundos: Arena Azul, Ayllu Allpa+, Kawsay Allpa, Quri Allpa.
- Evaluaciones: Brotes, Conteo, Crecimiento, Flores, Ramas, Seguimiento.

## Tiempo

Las 53 parejas (Año, Semana) encuentran correspondencia en
core.t_calendario, por lo que el campo Semana se comporta como semana de
calendario/ISO en este snapshot.

También hay coincidencias numéricas con core.t_semana_evaluacion, pero los 53
ranges de fechas son distintos. Eso demuestra que no se debe unir esta fuente
contra la semana de evaluación solo porque ambos campos se llamen Semana.

## Identidad de fundo

La resolución contra core.m_fundo_alias no es completa:

| Valor de Access | Filas | Resultado |
|---|---:|---|
| Arena Azul | 318 | resuelve a fundo_id = 2 |
| Quri Allpa | 318 | resuelve a fundo_id = 3 |
| Ayllu Allpa+ | 318 | no tiene alias aprobado |
| Kawsay Allpa | 318 | alias ambiguo; abarca más de un fundo físico |

Solo 636 de 1.272 filas tienen un fundo físico resuelto sin ambigüedad. No se
rellenaron aliases ni se eligió un fundo por aproximación.

## Relación con la configuración de muestreo

Los seis valores de Evaluación no coinciden exactamente con los valores actuales
de core.cfg_muestra_requerida (ConteoEstados y ConteoFlor). Esto no invalida
el presupuesto, pero indica que no es correcto crear una FK automática hacia esa
configuración ni asumir que ambos catálogos significan lo mismo.

## Historial de cargas

raw conserva cuatro cargas de esta fuente (source_snapshot_id 1, 3, 4 y 5),
cada una con 1.272 filas. El control de deltas no registra filas nuevas,
eliminadas ni modificadas respecto del snapshot de referencia. Son particiones
históricas por snapshot, no duplicados dentro del snapshot publicado.

## Decisión

M_PresupuestoMO permanece completa y auditable en raw_only. No se crea una
tabla core todavía porque faltan decisiones que cambian el modelo:

1. confirmar qué representa Ayllu Allpa+ frente al maestro de fundos;
2. definir cómo se identifica Kawsay Allpa si el presupuesto viene agregado para
   más de un fundo físico;
3. aprobar el catálogo de las seis evaluaciones y su relación —o no— con la
   configuración de muestreo;
4. confirmar la unidad y la regla de negocio de MOSem;
5. confirmar que el vínculo temporal debe ser a semana calendario y no a semana de
   evaluación agronómica.

Una vez cerrados esos puntos, la fuente podría modelarse como un hecho de
planificación semanal, no como un maestro. Hasta entonces no se modifica core
ni la base operativa del dashboard.
