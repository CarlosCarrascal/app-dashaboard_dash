<#
.SYNOPSIS
  Reemplaza únicamente core y qua de Neon con un dump local ya generado.

.DESCRIPTION
  El script respalda primero los mismos esquemas en Neon y exige -Confirmar.
  No crea, borra ni restaura raw, stg, dim, fact, reporting ni analytics.

.EXAMPLE
  $env:AQUANQA_NEON_DATABASE_URL = 'postgresql://...'
  .\db\tools\restaurar_neon_core_qua.ps1 -Confirmar
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$NeonDatabaseUrl = $env:AQUANQA_NEON_DATABASE_URL,

    [Parameter()]
    [string]$DumpPath,

    [Parameter(Mandatory)]
    [switch]$Confirmar
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($NeonDatabaseUrl)) {
    throw 'Falta AQUANQA_NEON_DATABASE_URL. No se puede elegir Neon por inferencia.'
}

$neonUri = [uri]$NeonDatabaseUrl
if ($neonUri.Scheme -notin @('postgresql', 'postgres') -or
    $neonUri.Host -notmatch '(^|\.)neon\.tech$') {
    throw 'La URL destino no corresponde a Neon; la restauración fue bloqueada.'
}

$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$artifactDirectory = Join-Path $repositoryRoot 'artifacts\neon-core-qua'
if ([string]::IsNullOrWhiteSpace($DumpPath)) {
    $DumpPath = Get-ChildItem -LiteralPath $artifactDirectory -Filter '*.dump' -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if ([string]::IsNullOrWhiteSpace($DumpPath) -or -not (Test-Path -LiteralPath $DumpPath)) {
    throw 'No se encontró un dump core+qua para restaurar.'
}

$pgDump = 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe'
$pgRestore = 'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe'
$psql = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
foreach ($tool in @($pgDump, $pgRestore, $psql)) {
    if (-not (Test-Path -LiteralPath $tool)) { throw "No se encontró $tool" }
}

$listing = & $pgRestore --list $DumpPath
if ($LASTEXITCODE -ne 0) { throw 'No se pudo inspeccionar el dump local.' }
$unexpectedSchema = $listing | Where-Object {
    $_ -match ' SCHEMA - ' -and $_ -notmatch ' SCHEMA - (core|qua) '
}
if ($unexpectedSchema) {
    throw 'El dump contiene esquemas fuera de core/qua; restauración bloqueada.'
}

New-Item -ItemType Directory -Path $artifactDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$neonBackup = Join-Path $artifactDirectory "neon_before_core_qua_$stamp.dump"
$displayTarget = "$($neonUri.Host)$($neonUri.AbsolutePath)"
Write-Host "Destino Neon: $displayTarget"
Write-Host "Dump local: $DumpPath"
Write-Host "Backup previo Neon: $neonBackup"

$env:PGPASSWORD = $neonUri.Password
& $pgDump --no-password --format=custom --no-owner --no-privileges `
    --schema=core --schema=qua --file $neonBackup --dbname $NeonDatabaseUrl
if ($LASTEXITCODE -ne 0) { throw 'Falló el backup de core+qua en Neon; no se borró nada.' }

$cleanupSql = @'
BEGIN;
DROP SCHEMA IF EXISTS core CASCADE;
DROP SCHEMA IF EXISTS qua CASCADE;
CREATE SCHEMA core;
CREATE SCHEMA qua;
COMMIT;
'@
$cleanupSql | & $psql --no-password -v ON_ERROR_STOP=1 --no-psqlrc --dbname $NeonDatabaseUrl
if ($LASTEXITCODE -ne 0) { throw 'Falló la limpieza de core/qua en Neon.' }

& $pgRestore --no-password --exit-on-error --no-owner --no-privileges `
    --schema=core --schema=qua --dbname $NeonDatabaseUrl $DumpPath
if ($LASTEXITCODE -ne 0) { throw 'Falló la restauración de core/qua en Neon.' }

$verificationSql = @'
SELECT n.nspname AS schema, count(c.oid) FILTER (WHERE c.relkind IN ('r', 'p')) AS tables
FROM pg_namespace n
LEFT JOIN pg_class c ON c.relnamespace = n.oid
WHERE n.nspname IN ('core', 'qua')
GROUP BY n.nspname
ORDER BY n.nspname;

SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'core' AND table_name = 'ev_flores'
      AND column_name = 'yemas_muertas'
) AS yemas_muertas,
EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'core' AND table_name = 'ev_flores'
      AND column_name = 'brotes_tiernos'
) AS brotes_tiernos;
'@
$verificationSql | & $psql --no-password -v ON_ERROR_STOP=1 --no-psqlrc --dbname $NeonDatabaseUrl
if ($LASTEXITCODE -ne 0) { throw 'La restauración terminó, pero falló su verificación.' }

Write-Host 'Core y qua restaurados y verificados en Neon.'
