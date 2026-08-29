[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AccessPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

# Inspecciona una copia de Access sin abrirla para escritura. DAO expone relaciones y
# QueryDef.SQL que ACE/ODBC no siempre publica. El resultado es JSON para que el ETL pueda
# conservarlo junto al snapshot y no tenga que inferir el modelo a partir de los datos.
$ErrorActionPreference = 'Stop'
$engine = $null
$database = $null

function Get-DaoValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Property,
        $Default = $null
    )
    try {
        $value = $Object.$Property
        if ($null -eq $value) { return $Default }
        return $value
    }
    catch {
        return $Default
    }
}

function Convert-DaoScalar {
    param($Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [datetime]) { return $Value.ToString('o') }
    if ($Value -is [byte[]]) { return ([BitConverter]::ToString($Value)).Replace('-', '') }
    if ($Value -is [bool]) { return [bool]$Value }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [decimal] -or $Value -is [double]) {
        return $Value
    }
    return [string]$Value
}

function Test-SystemObject {
    param([string]$Name)
    return [string]::IsNullOrWhiteSpace($Name) -or $Name.StartsWith('MSys') -or $Name.StartsWith('~')
}

try {
    $resolved = (Resolve-Path -LiteralPath $AccessPath).Path
    $parent = Split-Path -Parent $OutputPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    try {
        $engine = New-Object -ComObject DAO.DBEngine.120
    }
    catch {
        # Equipos con una versión antigua de Access pueden tener DAO 3.6 en vez de 12.0.
        $engine = New-Object -ComObject DAO.DBEngine.36
    }
    $database = $engine.OpenDatabase($resolved, $true, $true)

    $tables = @()
    foreach ($tableDef in $database.TableDefs) {
        $name = [string](Get-DaoValue $tableDef 'Name' '')
        if (Test-SystemObject $name) { continue }

        $fields = @()
        $ordinal = 0
        foreach ($field in $tableDef.Fields) {
            $ordinal++
            $fieldName = [string](Get-DaoValue $field 'Name' '')
            $fields += [ordered]@{
                nombre = $fieldName
                tipo = Convert-DaoScalar (Get-DaoValue $field 'Type' $null)
                tamano = Convert-DaoScalar (Get-DaoValue $field 'Size' $null)
                requerido = Convert-DaoScalar (Get-DaoValue $field 'Required' $null)
                permite_cero = Convert-DaoScalar (Get-DaoValue $field 'AllowZeroLength' $null)
                por_defecto = Convert-DaoScalar (Get-DaoValue $field 'DefaultValue' $null)
                validacion = Convert-DaoScalar (Get-DaoValue $field 'ValidationRule' $null)
                posicion = Convert-DaoScalar (Get-DaoValue $field 'OrdinalPosition' $ordinal)
                atributos = Convert-DaoScalar (Get-DaoValue $field 'Attributes' $null)
            }
        }

        $indexes = @()
        foreach ($index in $tableDef.Indexes) {
            $indexFields = @()
            $indexOrdinal = 0
            foreach ($indexField in $index.Fields) {
                $indexOrdinal++
                $indexFields += [ordered]@{
                    nombre = [string](Get-DaoValue $indexField 'Name' '')
                    posicion = Convert-DaoScalar (Get-DaoValue $indexField 'OrdinalPosition' $indexOrdinal)
                    orden = Convert-DaoScalar (Get-DaoValue $indexField 'Attributes' $null)
                }
            }
            $indexes += [ordered]@{
                nombre = [string](Get-DaoValue $index 'Name' '')
                unico = Convert-DaoScalar (Get-DaoValue $index 'Unique' $null)
                primario = Convert-DaoScalar (Get-DaoValue $index 'Primary' $null)
                requerido = Convert-DaoScalar (Get-DaoValue $index 'Required' $null)
                ignora_nulos = Convert-DaoScalar (Get-DaoValue $index 'IgnoreNulls' $null)
                atributos = Convert-DaoScalar (Get-DaoValue $index 'Attributes' $null)
                campos = @($indexFields)
            }
        }

        $tables += [ordered]@{
            nombre = $name
            tipo = 'table'
            atributos = Convert-DaoScalar (Get-DaoValue $tableDef 'Attributes' $null)
            campos = @($fields)
            indices = @($indexes)
        }
    }

    $knownTables = @($tables | ForEach-Object { [string]$_.nombre })
    $knownObjects = @($knownTables)
    foreach ($knownQueryDef in $database.QueryDefs) {
        $knownQueryName = [string](Get-DaoValue $knownQueryDef 'Name' '')
        if (-not (Test-SystemObject $knownQueryName)) {
            $knownObjects += $knownQueryName
        }
    }
    $relations = @()
    foreach ($relation in $database.Relations) {
        $relationName = [string](Get-DaoValue $relation 'Name' '')
        if (Test-SystemObject $relationName) { continue }
        $fieldMappings = @()
        foreach ($relationField in $relation.Fields) {
            $fieldMappings += [ordered]@{
                campo_padre = [string](Get-DaoValue $relationField 'Name' '')
                campo_hijo = [string](Get-DaoValue $relationField 'ForeignName' '')
            }
        }
        $relations += [ordered]@{
            nombre = $relationName
            tabla_padre = [string](Get-DaoValue $relation 'Table' '')
            tabla_hija = [string](Get-DaoValue $relation 'ForeignTable' '')
            atributos = Convert-DaoScalar (Get-DaoValue $relation 'Attributes' $null)
            campos = @($fieldMappings)
        }
    }

    $querydefs = @()
    foreach ($queryDef in $database.QueryDefs) {
        $queryName = [string](Get-DaoValue $queryDef 'Name' '')
        if (Test-SystemObject $queryName) { continue }
        $sql = [string](Get-DaoValue $queryDef 'SQL' '')
        $dependencies = @(
            $knownObjects |
                Where-Object {
                    $pattern = '(?i)(?<![A-Za-z0-9_])(?:\[\s*)?' + [regex]::Escape($_) + '(?:\s*\])?(?![A-Za-z0-9_])'
                    $sql -match $pattern
                } |
                Sort-Object -Unique
        )
        $querydefs += [ordered]@{
            nombre = $queryName
            tipo_objeto = 'QUERYDEF'
            tipo_codigo = Convert-DaoScalar (Get-DaoValue $queryDef 'Type' $null)
            definicion_sql = $sql
            dependencias = @($dependencies)
            devuelve_registros = Convert-DaoScalar (Get-DaoValue $queryDef 'ReturnsRecords' $null)
        }
    }

    $payload = [ordered]@{
        backend = 'dao'
        estado = 'disponible'
        ruta_origen = $resolved
        generado_en = [datetime]::UtcNow.ToString('o')
        tablas = @($tables)
        relaciones = @($relations)
        querydefs = @($querydefs)
    }
    $json = $payload | ConvertTo-Json -Depth 20
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($OutputPath, $json, $utf8NoBom)
    Write-Output "DAO catalogado: $($tables.Count) tablas, $($relations.Count) relaciones, $($querydefs.Count) consultas"
}
catch {
    Write-Error ("No se pudo catalogar Access mediante DAO: " + $_.Exception.Message)
    exit 1
}
finally {
    if ($database -ne $null) {
        try { $database.Close() } catch {}
        try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($database) } catch {}
    }
    if ($engine -ne $null) {
        try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($engine) } catch {}
    }
}
