"""ETL de la plataforma de datos Aqu Anqa.

Extrae `BD_AQUANQA_26.accdb` y el maestro de lotes hacia el esquema `raw` de PostgreSQL.

Dos invariantes que el código respeta en todo momento:

1. **El origen no se modifica.** La conexión a Access es de solo lectura y nunca se escribe
   en el `.accdb`. Access puede seguir en uso durante la migración.
2. **Nada se descarta en silencio.** Cada carga deja su recuento en `raw.carga_log` y se
   compara contra la cifra publicada en la auditoría. Una extracción truncada que pasa
   desapercibida es exactamente cómo nacieron los hallazgos H-03 y H-08.
"""

__version__ = "0.1.0"
