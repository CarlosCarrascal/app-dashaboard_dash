#!/usr/bin/env node
/**
 * Orquestador del monorepo. Sin dependencias: solo Node.
 *
 * Existe para que un solo comando funcione en cualquier equipo Windows sin activar conda
 * ni añadir psql al PATH — la fricción que hace fallar el arranque de un proyecto nuevo.
 *
 *   node scripts/run.mjs sql 00_bootstrap --database aquanqa_migracion
 *                                            ejecuta en orden los .sql de esa carpeta
 *   node scripts/run.mjs psql -c "select 1"    psql suelto con el entorno ya resuelto
 *   node scripts/run.mjs py extract --all      python -m aquanqa_etl.cli extract --all
 *   node scripts/run.mjs setup | build | validate | validate-fixture
 */
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, readdirSync, mkdirSync, rmSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { homedir, tmpdir } from 'node:os'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SQL_DIR = join(ROOT, 'db', 'sql')

// Los paquetes Python del monorepo, en orden de instalación. Las aplicaciones se instalan
// después de sus librerías; el dashboard Streamlit legado no forma parte del entorno oficial.
const PAQUETES_PYTHON = [
  'etl',
  join('backend', 'campo-api'),
  join('packages', 'analitica'),
  join('apps', 'dashboard'),
]

// ── .env ─────────────────────────────────────────────────────────────────────
function loadEnv() {
  const env = {}
  for (const file of ['.env', '.env.local']) {
    const path = join(ROOT, file)
    if (!existsSync(path)) continue
    for (const raw of readFileSync(path, 'utf8').split(/\r?\n/)) {
      const line = raw.trim()
      if (!line || line.startsWith('#')) continue
      const eq = line.indexOf('=')
      if (eq < 1) continue
      env[line.slice(0, eq).trim()] = line.slice(eq + 1).trim().replace(/^["']|["']$/g, '')
    }
  }
  return env
}

const dotenv = loadEnv()
const env = { PGCLIENTENCODING: 'UTF8', ...dotenv, ...process.env }
// process.env gana salvo que esté vacío: permite `PGPASSWORD=x npm run ...` sin editar .env
for (const k of Object.keys(dotenv)) if (!process.env[k] && dotenv[k]) env[k] = dotenv[k]

// ── Localizar binarios ───────────────────────────────────────────────────────
function which(cmd) {
  const r = spawnSync(process.platform === 'win32' ? 'where' : 'which', [cmd], { encoding: 'utf8' })
  if (r.status !== 0 || !r.stdout) return null
  const rutas = r.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  if (process.platform !== 'win32') return rutas[0] ?? null
  // En Windows `where` devuelve también shims sin extensión (fnm, nvm, scoop) que spawnSync
  // no puede ejecutar: ENOENT. Hay que quedarse con el .cmd/.exe/.bat.
  const ejecutable = rutas.find((p) => /\.(cmd|exe|bat|ps1)$/i.test(p))
  return ejecutable ?? rutas[0] ?? null
}

function findPostgresTool(name, envKeys) {
  for (const key of envKeys) if (env[key] && existsSync(env[key])) return env[key]
  const onPath = which(name)
  if (onPath) return onPath
  for (const v of ['18', '17', '16', '15']) {
    const p = `C:\\Program Files\\PostgreSQL\\${v}\\bin\\${name}.exe`
    if (existsSync(p)) return p
  }
  return null
}

function findPsql() {
  const psql = findPostgresTool('psql', ['PSQL_EXE'])
  if (psql) return psql
  fail(
    'No encuentro psql. Instala PostgreSQL o define PSQL_EXE en .env con la ruta completa\n' +
      '  (habitualmente C:\\Program Files\\PostgreSQL\\18\\bin\\psql.exe).'
  )
}

function findPgDump() {
  const pgDump = findPostgresTool('pg_dump', ['PGDUMP_EXE', 'PG_DUMP_EXE'])
  if (pgDump) return pgDump
  fail(
    'No encuentro pg_dump. Instala PostgreSQL o define PGDUMP_EXE en .env con la ruta completa\n' +
      '  (habitualmente C:\\Program Files\\PostgreSQL\\18\\bin\\pg_dump.exe).'
  )
}

function findPgRestore() {
  const pgRestore = findPostgresTool('pg_restore', ['PGRESTORE_EXE', 'PG_RESTORE_EXE'])
  if (pgRestore) return pgRestore
  fail(
    'No encuentro pg_restore. Instala PostgreSQL o define PGRESTORE_EXE en .env con la ruta completa\n' +
      '  (habitualmente C:\\Program Files\\PostgreSQL\\18\\bin\\pg_restore.exe).'
  )
}

/** Python del entorno conda `aquanqa`; si no existe, el del PATH. */
function findPython() {
  if (env.PYTHON_EXE && existsSync(env.PYTHON_EXE)) return env.PYTHON_EXE
  const conda = findConda()
  if (conda) {
    const resolved = spawnSync(
      conda,
      ['run', '--no-capture-output', '-n', 'aquanqa', 'python', '-c', 'import sys; print(sys.executable)'],
      { encoding: 'utf8', env }
    )
    const condaPython = (resolved.stdout ?? '')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .reverse()
      .find((line) => line && existsSync(line))
    if (condaPython) return condaPython
  }
  const candidates = [
    join(homedir(), 'miniconda3', 'envs', 'aquanqa', 'python.exe'),
    join(homedir(), 'anaconda3', 'envs', 'aquanqa', 'python.exe'),
    'C:\\tools\\Anaconda3\\envs\\aquanqa\\python.exe',
  ]
  for (const c of candidates) if (existsSync(c)) return c
  const onPath = which('python') || which('python3') || which('py')
  if (onPath) return onPath
  fail('No encuentro Python. Ejecuta `npm run setup` o define PYTHON_EXE en .env.')
}

function findConda() {
  if (env.CONDA_EXE && existsSync(env.CONDA_EXE)) return env.CONDA_EXE
  for (const c of [
    join(homedir(), 'miniconda3', 'Scripts', 'conda.exe'),
    join(homedir(), 'anaconda3', 'Scripts', 'conda.exe'),
    'C:\\ProgramData\\miniconda3\\Scripts\\conda.exe',
    'C:\\ProgramData\\anaconda3\\Scripts\\conda.exe',
  ]) {
    if (existsSync(c)) return c
  }
  return which('conda')
}

// ── Utilidades ───────────────────────────────────────────────────────────────
const C = { dim: '\x1b[2m', red: '\x1b[31m', green: '\x1b[32m', yellow: '\x1b[33m', bold: '\x1b[1m', off: '\x1b[0m' }
const log = (m) => console.log(m)
const step = (m) => log(`${C.bold}▸ ${m}${C.off}`)
function fail(msg) {
  console.error(`${C.red}✗ ${msg}${C.off}`)
  process.exit(1)
}

function run(cmd, args, opts = {}) {
  log(`${C.dim}  $ ${cmd} ${args.join(' ')}${C.off}`)
  // Node 20+ se niega a ejecutar .cmd/.bat sin shell (mitigación de CVE-2024-27980) y
  // devuelve EINVAL. npm en Windows es siempre un .cmd, así que hay que pedirle shell.
  const necesitaShell = process.platform === 'win32' && /\.(cmd|bat)$/i.test(cmd)
  const r = spawnSync(
    necesitaShell ? `"${cmd}"` : cmd,
    necesitaShell ? args.map((a) => (/\s/.test(a) ? `"${a}"` : a)) : args,
    { stdio: 'inherit', env, cwd: opts.cwd ?? ROOT, shell: necesitaShell }
  )
  if (r.error) fail(`${cmd}: ${r.error.message}`)
  if (r.status !== 0 && !opts.allowFail) fail(`${cmd} terminó con código ${r.status}`)
  return r.status
}

function requirePassword() {
  if (!env.PGPASSWORD) {
    fail(
      'Falta PGPASSWORD.\n' +
        '  Copia .env.example a .env y pon la contraseña de PostgreSQL,\n' +
        '  o ejecútalo así una vez:  $env:PGPASSWORD="..."; npm run <comando>'
    )
  }
}

/** psql con ON_ERROR_STOP: un error a mitad de un script no debe dejar la base a medias. */
function psql(args, { db, allowFail = false } = {}) {
  requirePassword()
  const base = [
    '-v', 'ON_ERROR_STOP=1',
    '--no-psqlrc',
    '-P', 'pager=off',
    '-h', env.PGHOST ?? 'localhost',
    '-p', env.PGPORT ?? '5432',
    '-U', env.PGUSER ?? 'postgres',
    '-d', db ?? env.PGDATABASE ?? 'aquanqa',
  ]
  return run(findPsql(), [...base, ...args], { allowFail })
}

function sqlFile(file, { db, allowFail = false } = {}) {
  if (!existsSync(file)) fail(`No existe ${file}`)
  return psql(['-f', file], { db, allowFail })
}

function sqlFolder(folder, { db, allowFail = false, exclude = [] } = {}) {
  const dir = join(SQL_DIR, folder)
  if (!existsSync(dir)) fail(`No existe ${dir}`)
  const files = readdirSync(dir)
    .filter((f) => f.endsWith('.sql') && !exclude.includes(f))
    .sort()
  if (files.length === 0) {
    log(`${C.yellow}  (sin archivos .sql todavía en ${folder})${C.off}`)
    return 0
  }
  step(`${folder} — ${files.length} archivo(s)`)
  for (const f of files) {
    const status = sqlFile(join(dir, f), { db, allowFail })
    if (status !== 0) return status
  }
  return 0
}

/** Cita un identificador PostgreSQL sin interpolar comillas del entorno. */
function quoteIdentifier(identifier) {
  return `"${String(identifier).replaceAll('"', '""')}"`
}

function py(args) {
  return run(findPython(), ['-m', 'aquanqa_etl.cli', ...args], { cwd: join(ROOT, 'etl') })
}

function optionValue(args, option) {
  const index = args.indexOf(option)
  if (index < 0) return null
  if (!args[index + 1] || args[index + 1].startsWith('--')) {
    fail(`Falta el valor de ${option}`)
  }
  return args[index + 1]
}

/** Backup físico + línea base de conteos. No cambia la base origen. */
function cmdBackup(args) {
  requirePassword()
  const db = optionValue(args, '--database') ?? env.PGDATABASE ?? 'aquanqa'
  const marca = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z')
  const outputArg = optionValue(args, '--output')
  const dumpFile = resolve(ROOT, outputArg ?? join('data', 'salida', 'guardas', `${db}_${marca}.dump`))
  const baselineArg = optionValue(args, '--baseline')
  const baselineFile = resolve(
    ROOT,
    baselineArg ?? dumpFile.replace(/\.dump$/i, '.baseline.json'),
  )
  mkdirSync(dirname(dumpFile), { recursive: true })
  step(`Backup físico de ${db}`)
  run(findPgDump(), [
    '--no-password', '--format=custom', '--file', dumpFile,
    '--no-owner', '--no-privileges',
    '-h', env.PGHOST ?? 'localhost', '-p', env.PGPORT ?? '5432',
    '-U', env.PGUSER ?? 'postgres', '-d', db,
  ])
  step(`Baseline de ${db}`)
  return py(['baseline', '--database', db, '--output', baselineFile])
}

/** Construye únicamente la primera etapa de migración: esquema raw y sus controles. */
function cmdRawOnly(args) {
  const db = optionValue(args, '--database') ?? env.PGDATABASE ?? 'aquanqa_migracion'
  if (db === 'aquanqa') {
    fail('raw-only bloqueado para aquanqa: esa base es la línea operativa del dashboard. Use --database aquanqa_migracion.')
  }
  step(`Modelo mínimo raw de ${db}`)
  psql(['-c', 'CREATE SCHEMA IF NOT EXISTS raw'], { db })
  return sqlFolder('10_raw', { db })
}

const FASES_PROTEGIDAS_DASHBOARD = new Set([
  '00_bootstrap', '10_raw', '20_core', '30_stg', '40_qua', '50_carga_core',
  '60_dim_fact', '70_reporting', '80_analytics',
])

function cmdSql(args) {
  const folder = args[0]
  if (!folder || folder.startsWith('--')) fail('uso: run.mjs sql <carpeta> [--database <bd>]')
  const db = optionValue(args, '--database') ?? env.PGDATABASE ?? 'aquanqa'
  if (db === 'aquanqa' && FASES_PROTEGIDAS_DASHBOARD.has(folder)) {
    fail(`SQL bloqueado para aquanqa: ${folder} pertenece al modelo protegido del dashboard. Use --database aquanqa_migracion.`)
  }
  return sqlFolder(folder, { db })
}

function cmdPreflight(args) {
  const db = optionValue(args, '--database') ?? env.PGDATABASE ?? 'aquanqa_migracion'
  if (db !== 'aquanqa_migracion') {
    fail(`preflight bloqueado para ${db}: solo puede validar aquanqa_migracion.`)
  }
  return sqlFile(join(ROOT, 'db', 'tools', 'preflight_migracion.sql'), { db })
}

function cmdAnalytics(args) {
  return run(findPython(), ['-m', 'analitica.cli', ...args], { cwd: ROOT })
}

function cmdMlflow(args) {
  const artifactRoot = resolve(ROOT, env.MLFLOW_ARTIFACT_ROOT ?? join('data', 'salida', 'mlflow'))
  mkdirSync(artifactRoot, { recursive: true })
  const backend = env.MLFLOW_BACKEND_STORE_URI
  if (!backend) fail('Falta MLFLOW_BACKEND_STORE_URI en .env para iniciar MLflow.')
  return run(findPython(), [
    '-m', 'mlflow', 'server', '--backend-store-uri', backend,
    '--default-artifact-root', artifactRoot,
    '--host', env.MLFLOW_HOST ?? '127.0.0.1', '--port', env.MLFLOW_PORT ?? '5000',
    ...args,
  ])
}

/** Dashboard oficial Dash. El proyecto es autocontenido en `apps/dashboard`. */
function cmdDashboard(args) {
  const app = join(ROOT, 'apps', 'dashboard', 'app.py')
  if (!existsSync(app)) fail(`No existe ${app}`)
  return run(findPython(), [app, ...args], { cwd: DASHBOARD_DIR })
}

const DASHBOARD_DIR = join(ROOT, 'apps', 'dashboard')

/**
 * CLI standalone de Tailwind: un binario suelto, sin `npm install` ni `node_modules`.
 * ADR-0006 prohíbe dependencias npm; el binario standalone no es un paquete de Node, así
 * que compilar el CSS del tablero Dash con él no rompe esa regla.
 *
 * Descarga manual (una vez): https://github.com/tailwindlabs/tailwindcss/releases
 * → guardar el binario como `apps/dashboard/bin/tailwindcss.exe` (Windows) o
 * definir TAILWIND_EXE en `.env` con la ruta completa.
 */
function findTailwind() {
  if (env.TAILWIND_EXE && existsSync(env.TAILWIND_EXE)) return env.TAILWIND_EXE
  const local = join(DASHBOARD_DIR, 'bin', process.platform === 'win32' ? 'tailwindcss.exe' : 'tailwindcss')
  if (existsSync(local)) return local
  const onPath = which('tailwindcss')
  if (onPath) return onPath
  fail(
    'No encuentro el CLI standalone de Tailwind.\n' +
      '  Descargalo de https://github.com/tailwindlabs/tailwindcss/releases (el binario\n' +
      '  standalone, no el paquete npm) y guardalo en\n' +
      `  ${join('apps', 'dashboard', 'bin', 'tailwindcss.exe')}\n` +
      '  o definí TAILWIND_EXE en .env con la ruta completa.'
  )
}

function cmdTailwind(args) {
  const watch = args.includes('--watch')
  const tailwind = findTailwind()
  const flags = [
    '-i', join(DASHBOARD_DIR, 'src', 'input.css'),
    '-o', join(DASHBOARD_DIR, 'assets', 'tailwind.css'),
  ]
  if (watch) flags.push('--watch')
  else flags.push('--minify')
  return run(tailwind, flags)
}

// ── Comandos ─────────────────────────────────────────────────────────────────
function cmdSetup() {
  step('Entorno Python (conda env `aquanqa`)')
  const conda = findConda()
  if (!conda) {
    log(`${C.yellow}  conda no encontrado; se usará el Python del PATH.${C.off}`)
  } else {
    const envs = spawnSync(conda, ['env', 'list'], { encoding: 'utf8' }).stdout ?? ''
    if (/[\\/]envs[\\/]aquanqa\b/.test(envs)) {
      log('  el entorno ya existe')
    } else {
      run(conda, ['create', '-y', '-n', 'aquanqa', 'python=3.13'])
    }
  }

  // Fuera del bloque de conda a propósito: sin conda se usa el Python del PATH, pero los
  // paquetes del monorepo hay que instalarlos igualmente.
  step('Paquetes Python del monorepo')
  for (const pkg of PAQUETES_PYTHON) {
    run(findPython(), ['-m', 'pip', 'install', '-e', join(ROOT, pkg)])
  }

  step(`Base de datos ${env.PGDATABASE ?? 'aquanqa'}`)
  requirePassword()
  const db = env.PGDATABASE ?? 'aquanqa'
  const exists = spawnSync(
    findPsql(),
    ['--no-psqlrc', '-tAc', `SELECT 1 FROM pg_database WHERE datname='${db}'`,
     '-h', env.PGHOST ?? 'localhost', '-p', env.PGPORT ?? '5432', '-U', env.PGUSER ?? 'postgres', '-d', 'postgres'],
    { encoding: 'utf8', env }
  )
  if (exists.stdout?.trim() === '1') {
    log('  la base ya existe')
  } else {
    psql(['-c', `CREATE DATABASE ${db} ENCODING 'UTF8' TEMPLATE template0`], { db: 'postgres' })
  }

  sqlFolder('00_bootstrap')
  // La carga ETL necesita que las tablas raw existan antes de recibir el primer CSV.
  // También se repite en `build` porque ambos comandos son idempotentes y así se puede
  // reconstruir una base recién reiniciada sin recordar una orden oculta.
  sqlFolder('10_raw')

  // Las contraseñas de los roles no viven en el SQL versionado: se aplican aquí desde .env.
  step('Contraseñas de los roles')
  for (const [role, key] of [
    [env.APP_DB_USER ?? 'aquanqa_app', 'APP_DB_PASSWORD'],
    [env.BI_DB_USER ?? 'aquanqa_bi', 'BI_DB_PASSWORD'],
    [env.ETL_DB_USER ?? 'aquanqa_etl', 'ETL_DB_PASSWORD'],
    [env.ANALYTICS_DB_USER ?? 'aquanqa_analytics', 'ANALYTICS_DB_PASSWORD'],
  ]) {
    if (env[key]) {
      psql(['-q', '-c', `ALTER ROLE ${role} PASSWORD '${env[key].replace(/'/g, "''")}'`])
    } else {
      log(`${C.yellow}  ${role}: sin ${key} en .env, se deja sin contraseña${C.off}`)
    }
  }

  mkdirSync(join(ROOT, 'data', 'salida'), { recursive: true })
  log(`${C.green}✓ Entorno listo. Siguiente: npm run extract${C.off}`)
}

/**
 * Orden de las capas. El número del directorio ES la dependencia: no reordenar.
 * Incluye 00_bootstrap y 10_raw para que `build` funcione también justo después de un
 * `db:reset`, o si alguien ejecuta el flujo sin pasar por `setup`.
 */
const CAPAS_MODELO = [
  '00_bootstrap', '10_raw', '20_core', '30_stg', '40_qua', '50_carga_core', '60_dim_fact',
  '70_reporting', '80_analytics',
]

function cmdBuild({ db, allowFail = false, skipRoles = false, full = false, excludeFiles = [] } = {}) {
  if (db === 'aquanqa') {
    fail('build/migrate bloqueado para aquanqa: esa base es la línea operativa del dashboard. Use --database aquanqa_migracion.')
  }
  if (!full) {
    log(`${C.yellow}  build/migrate en ${db}: fase incremental; solo se construye raw. Use --full únicamente para un entorno efímero o una reconstrucción legacy.${C.off}`)
    return cmdRawOnly(['--database', db])
  }
  for (const f of CAPAS_MODELO) {
    const exclude = [
      ...(skipRoles && f === '00_bootstrap' ? ['020_roles.sql'] : []),
      ...(f === '50_carga_core' ? excludeFiles : []),
    ]
    const status = sqlFolder(f, { db, allowFail, exclude })
    if (status !== 0) return status
  }
  log(`${C.green}✓ Modelo construido. Siguiente: npm run validate${C.off}`)
  return 0
}

/**
 * Ejecuta los checks contra un clon efímero de PGDATABASE.
 *
 * Algunos checks reconstruyen qua.control y funciones auxiliares. El contrato público de
 * `validate` sigue siendo el mismo (valida el estado de la base configurada), pero esas
 * mutaciones ocurren exclusivamente en el clon y nunca en la base de trabajo.
 */
function cmdValidate() {
  const sourceDb = env.PGDATABASE ?? 'aquanqa'
  const db = `aquanqa_ci_validate_${process.pid}_${Date.now()}`
  const dumpFile = join(tmpdir(), `${db}.dump`)
  let status = 1
  let created = false
  let restoredFromDump = false

  try {
    step(
      `Validación aislada: base temporal ${db} (clon de ${sourceDb}; ` +
        `${sourceDb} no se modificará)`
    )
    status = psql(
      ['-c', `CREATE DATABASE ${quoteIdentifier(db)} TEMPLATE ${quoteIdentifier(sourceDb)}`],
      { db: 'postgres', allowFail: true }
    )
    if (status === 0) created = true

    // CREATE DATABASE ... TEMPLATE es rápido, pero PostgreSQL lo rechaza si el origen
    // tiene sesiones activas. En ese caso se conserva el mismo aislamiento con un dump
    // consistente y una restauración en template0, sin desconectar ni terminar sesiones.
    if (status !== 0) {
      log(`${C.yellow}  No se pudo clonar por TEMPLATE; se usará dump/restauración aislados${C.off}`)
      requirePassword()
      const pgDump = findPgDump()
      const pgRestore = findPgRestore()
      status = run(
        pgDump,
        [
          '--no-password',
          '--format=custom',
          '--file', dumpFile,
          '--no-owner',
          '--no-privileges',
          '-h', env.PGHOST ?? 'localhost',
          '-p', env.PGPORT ?? '5432',
          '-U', env.PGUSER ?? 'postgres',
          '-d', sourceDb,
        ],
        { allowFail: true }
      )
      if (status === 0) {
        status = psql(
          ['-c', `CREATE DATABASE ${quoteIdentifier(db)} ENCODING 'UTF8' TEMPLATE template0`],
          { db: 'postgres', allowFail: true }
        )
      }
      if (status === 0) {
        created = true
        restoredFromDump = true
        status = run(
          pgRestore,
          [
            '--no-password',
            '--exit-on-error',
            '--no-owner',
            '--no-privileges',
            '-h', env.PGHOST ?? 'localhost',
            '-p', env.PGPORT ?? '5432',
            '-U', env.PGUSER ?? 'postgres',
            '-d', db,
            dumpFile,
          ],
          { allowFail: true }
        )
      }
    }
    if (status === 0) {
      if (restoredFromDump) log(`${C.dim}  Origen restaurado en la base temporal${C.off}`)
      status = sqlFolder('90_checks', { db, allowFail: true })
    }
  } finally {
    if (created) {
      const cleanup = psql(
        ['-c', `DROP DATABASE ${quoteIdentifier(db)}`],
        { db: 'postgres', allowFail: true }
      )
      if (status === 0 && cleanup !== 0) status = cleanup
    }
    try {
      rmSync(dumpFile, { force: true })
    } catch (error) {
      if (status === 0) status = 1
      console.error(`${C.red}✗ No pude eliminar el dump temporal ${dumpFile}: ${error.message}${C.off}`)
    }
  }
  return status
}

/**
 * Ejecuta el gate completo sobre una base efímera y un fixture sintético.
 *
 * La base destino nunca es PGDATABASE: siempre se crea con un nombre generado por este
 * proceso, se valida y se elimina. Esto permite ejecutar la compuerta positiva tanto en CI
 * como en un equipo local sin riesgo de truncar la base de trabajo.
 */
function cmdValidateFixture() {
  const db = `aquanqa_ci_positive_${process.pid}_${Date.now()}`
  const fixture = join(ROOT, 'db', 'ci', 'fixtures', 'positive_gate.sql')
  let status = 1
  let created = false

  try {
    step(`Base efímera ${db}`)
    status = psql(
      ['-c', `CREATE DATABASE "${db}" ENCODING 'UTF8' TEMPLATE template0`],
      { db: 'postgres', allowFail: true }
    )
    if (status === 0) {
      created = true
      // 020_roles.sql modifica roles/default privileges del clúster; no forma parte
      // de la prueba de contrato y se excluye para mantener el harness aislado.
      status = cmdBuild({
        db,
        allowFail: true,
        skipRoles: true,
        full: true,
        excludeFiles: ['090_ejecutar.sql'],
      })
      if (status === 0) {
        status = sqlFile(join(SQL_DIR, '90_checks', '010_contrato.sql'), { db, allowFail: true })
      }
      if (status === 0) {
        status = sqlFile(join(SQL_DIR, '90_checks', '020_funciones.sql'), { db, allowFail: true })
      }
      if (status === 0) status = sqlFile(fixture, { db, allowFail: true })
      if (status === 0) {
        // El fixture declara un universo vacío, pero el contrato contiene controles que
        // consultan tablas materializadas de stg directamente. Se materializan todas las
        // vistas vacías para que el smoke test mida el contrato completo y no confunda una
        // tabla aún no creada con un error de datos. En una migración real esta operación
        // sigue siendo selectiva por bloque.
        status = psql(
          ['-c', "CALL stg.sp_materializar(); CALL core.sp_cargar_ubicacion();"],
          { db, allowFail: true }
        )
      }
      if (status === 0) {
        status = sqlFile(join(SQL_DIR, '90_checks', '030_analytics.sql'), { db, allowFail: true })
      }
      if (status === 0) {
        status = sqlFile(join(SQL_DIR, '90_checks', '090_informe.sql'), { db, allowFail: true })
      }
      if (status === 0) log(`${C.green}✓ Compuerta positiva aceptó el fixture aislado${C.off}`)
    }
  } finally {
    if (created) {
      const cleanup = psql(
        ['-c', `DROP DATABASE "${db}"`],
        { db: 'postgres', allowFail: true }
      )
      if (status === 0 && cleanup !== 0) status = cleanup
    }
  }
  return status
}

const [target, ...rest] = process.argv.slice(2)
switch (target) {
  case 'setup':    cmdSetup(); break
  case 'sql':      cmdSql(rest); break
  case 'psql':     psql(rest); break
  case 'preflight': cmdPreflight(rest); break
  case 'py':       py(rest); break
  case 'build':    cmdBuild({ db: optionValue(rest, '--database') ?? env.PGDATABASE ?? 'aquanqa', full: rest.includes('--full') }); break
  case 'migrate':  cmdBuild({ db: optionValue(rest, '--database') ?? env.PGDATABASE ?? 'aquanqa', full: rest.includes('--full') }); break
  case 'validate': {
    const status = cmdValidate()
    if (status !== 0) fail(`validate terminó con código ${status}`)
    break
  }
  case 'validate-fixture': {
    const status = cmdValidateFixture()
    if (status !== 0) fail(`validate-fixture terminó con código ${status}`)
    break
  }
  case 'backup': {
    const status = cmdBackup(rest)
    if (status !== 0) fail(`backup terminó con código ${status}`)
    break
  }
  case 'raw-only': {
    const status = cmdRawOnly(rest)
    if (status !== 0) fail(`raw-only terminó con código ${status}`)
    break
  }
  case 'dashboard': cmdDashboard(rest); break
  case 'dashboard-dash': cmdDashboard(rest); break
  case 'tailwind': cmdTailwind(rest); break
  case 'analytics': cmdAnalytics(rest); break
  case 'mlflow': cmdMlflow(rest); break
  default:
    log(
      'Uso: node scripts/run.mjs ' +
      '<setup|migrate|build [--full]|validate|validate-fixture|dashboard|tailwind [--watch]|' +
        'backup [--database <bd>]|raw-only [--database <bd>]|sql <carpeta> [--database <bd>]|' +
        'preflight [--database aquanqa_migracion]|psql <args>|py <args>|' +
        'analytics <comando>|mlflow>'
    )
    process.exit(target ? 1 : 0)
}
