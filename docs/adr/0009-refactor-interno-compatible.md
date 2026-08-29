# 0009 · Refactorización interna compatible y por etapas

## Estado

Aceptado.

## Contexto

`packages/analitica` concentra contratos de datos, preparación de paneles, modelos,
persistencia, tracking, scripts y utilidades. Cambiarlo todo en una sola operación aumenta
el riesgo de romper columnas, fórmulas, consultas SQL, comandos o pantallas que ya consumen
la biblioteca.

## Decisión

La refactorización se hace por bloques pequeños y verificables. Cada bloque sigue este ciclo:

1. identificar el contrato que no puede cambiar;
2. mover o extraer la implementación a un módulo con una responsabilidad clara;
3. conservar una fachada en la ruta histórica;
4. comprobar identidad de símbolos públicos, imports y comportamiento numérico;
5. ejecutar pruebas con `python -m pytest`, compilación y Ruff;
6. pedir una auditoría independiente y esperar su resultado completo antes de continuar.

La API pública, las columnas, el grano de las filas, las reglas as-of, las fórmulas y las
consultas SQL son contratos. Si una corrección cambia un resultado histórico, se registra
como una decisión explícita y no se disfraza de simple movimiento de archivos.

## Consecuencias

- Se puede revisar cada cambio y conservar los nombres históricos mediante la fachada.
- La fachada no es por sí sola un rollback: volver a una implementación anterior exige un
  commit/tag o wheel versionado que contenga esa implementación.
- Las personas no desarrolladoras pueden entender el avance por bloques y pruebas concretas.
- Durante la transición pueden existir módulos fachada y nombres históricos duplicados de
  forma intencional.
- El estado del repositorio puede contener archivos nuevos no staged; no se deben eliminar
  ni limpiar automáticamente cambios del usuario.

## Criterios de salida

La refactorización termina cuando se ejecutan y registran, como mínimo:

- `python -m pytest packages/analitica/tests -q`;
- `python -m pytest apps/dashboard/tests -q`;
- `python -m pytest etl/tests -q` después de instalar el paquete ETL en el mismo entorno;
- `python -m compileall -q packages/analitica apps/dashboard`;
- Ruff focal sobre los archivos modificados del bloque (el lint global conserva deuda
  preexistente hasta que se aborde por separado);
- construcción e instalación de un wheel en un entorno limpio;
- smoke tests de los imports públicos y de `aquanqa-analytics`;
- validación PostgreSQL de migraciones, `90_checks` y persistencia.

En PowerShell, una verificación local reproducible usa:

```powershell
python -m pytest packages/analitica/tests -q
python -m pytest apps/dashboard/tests -q
python -m compileall -q packages/analitica apps/dashboard
python -m ruff check packages/analitica/cli.py packages/analitica/visualizaciones packages/analitica/servicios packages/analitica/proyeccion/candidatos packages/analitica/proyeccion/horizonte packages/analitica/proyeccion/parametros packages/analitica/proyeccion/infraestructura packages/analitica/proyeccion/persistencia packages/analitica/nucleo/contratos.py packages/analitica/nucleo/ventanas.py
python -m build packages/analitica --wheel
$wheel = Get-ChildItem packages/analitica/dist -Filter '*.whl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $wheel) { throw 'No se encontró el wheel recién construido' }
python -m pip install --force-reinstall --no-deps $wheel.FullName
python -c "import analitica.proyeccion as p; [getattr(p, n) for n in p.__all__]; print(len(p.__all__))"
python -m analitica.cli --help
```

Las órdenes `analytics:validate-operational` y `analytics:operational-project` no contienen
rutas personales. Se debe pasar `--root <carpeta>` o definir `AQUANQA_OPERATIVO_ROOT` en `.env`.

Para validar el ETL desde un checkout antes de ejecutar sus pruebas, instala su paquete con
el mismo Python que usará pytest: `python -m pip install -e domain -e "etl[dev]"` y luego
`python -m pytest etl/tests -q`. En Windows no es necesario que el directorio `Scripts` esté
en `PATH`: se invocan siempre `python -m pip` y `python -m pytest`.

La prueba PostgreSQL se ejecuta en CI con `AQUANQA_TEST_POSTGRES_DSN` apuntando al servicio
efímero; nunca se debe apuntar el smoke test a una base productiva. La evidencia de CI debe
conservar el run de workflow y el resultado del test.

Además debe existir un commit/tag o wheel anterior identificable para rollback, y un informe
de advertencias, diferencias históricas y decisiones pendientes. Mientras los archivos sigan
sin staging/commit, el rollback es una operación de versionado pendiente del equipo, no una
capacidad que este cambio pueda prometer por sí mismo.

Cuando exista ese baseline, el procedimiento es seleccionar el tag/commit aprobado o desplegar
el wheel anterior, volver a ejecutar las pruebas de humo y registrar la operación. No se usa
`git reset --hard` ni se borran cambios no versionados para simular un rollback.

## Alternativas descartadas

- Reescribir el paquete completo de una vez: dificulta atribuir una regresión.
- Cambiar nombres públicos primero: fuerza una migración externa innecesaria.
- Eliminar módulos legacy sin fachada: rompe imports de consumidores existentes.
