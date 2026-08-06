---
name: entorno-local-ccarrascal
description: Herramientas disponibles en el equipo del usuario y cómo leer el .accdb sin instalar nada
metadata:
  node_type: memory
  type: reference
  originSessionId: 141cb603-6181-44a5-a1c9-1122f53ba6b4
  modified: 2026-08-03T21:35:43.606Z
---

Windows 11 Pro. Verificado el 2026-08-03:

- **PostgreSQL 18.4** local, servicio `postgresql-x64-18`, puerto 5432. `psql` **no** está en
  PATH: usar `C:\Program Files\PostgreSQL\18\bin\psql.exe`. `pg_hba.conf` usa
  `scram-sha-256` y no hay `pgpass.conf` — las credenciales hay que pedirlas.
- **Access sin Office instalado, pero ACE OLEDB 12/16 registrados** y driver ODBC
  *Microsoft Access Driver (\*.mdb, \*.accdb)* de 64 bits. Lectura fiable del `.accdb` con
  `System.Data.OleDb` desde PowerShell (`Provider=Microsoft.ACE.OLEDB.16.0;Mode=Read`);
  `OleDbCommand.ExecuteScalar` es mucho más rápido que recorrer un recordset por COM, que
  agota el timeout de 2 min en tablas de 100 mil filas.
- Nombres con `ñ`/acentos (`R08_Forecast_Campaña`, `Paña`) hay que construirlos con
  `[char]0xF1`; y cuidado con `@('a'+$N+'b','c')` en PowerShell, que concatena el array
  entero en un solo string.
- **miniconda** en `C:\Users\CCARRASCAL\miniconda3` (Python 3.13, solo pandas/numpy: falta
  pyodbc y psycopg). Hay otro Python 3.14 en PATH sin paquetes. **Node 24 / npm 11.**
  Sin Docker, sin psql en PATH.
- `Get-ChildItem -Recurse` sobre `C:\Users\CCARRASCAL` dispara el guardián del sandbox
  ("Remove-Item on system path is blocked"): usar rutas concretas o `find` desde Bash.

Ver [[plataforma-datos-aquanqa]].
