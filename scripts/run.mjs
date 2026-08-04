#!/usr/bin/env node
/**
 * Orquestador del monorepo. Sin dependencias: solo Node.
 *
 * Existe para que un solo comando funcione en cualquier equipo Windows sin activar conda
 * ni añadir psql al PATH — la fricción que hace fallar el arranque de un proyecto nuevo.
 *
 *   node scripts/run.mjs sql 00_bootstrap      ejecuta en orden los .sql de esa carpeta
 *   node scripts/run.mjs psql -c "select 1"    psql suelto con el entorno ya resuelto
 *   node scripts/run.mjs py extract --all      python -m aquanqa_etl.cli extract --all
 *   node scripts/run.mjs setup | build | validate
 */
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, readdirSync, mkdirSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { homedir } from 'node:os'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SQL_DIR = join(ROOT, 'packages', 'db', 'sql')

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

function findPsql() {
  if (env.PSQL_EXE && existsSync(env.PSQL_EXE)) return env.PSQL_EXE
  const onPath = which('psql')
  if (onPath) return onPath
  for (const v of ['18', '17', '16', '15']) {
    const p = `C:\\Program Files\\PostgreSQL\\${v}\\bin\\psql.exe`
    if (existsSync(p)) return p
  }
  fail(
    'No encuentro psql. Instala PostgreSQL o define PSQL_EXE en .env con la ruta completa\n' +
      '  (habitualmente C:\\Program Files\\PostgreSQL\\18\\bin\\psql.exe).'
  )
}

/** Python del entorno conda `aquanqa`; si no existe, el del PATH. */
function findPython() {
  if (env.PYTHON_EXE && existsSync(env.PYTHON_EXE)) return env.PYTHON_EXE
  const candidates = [
    join(homedir(), 'miniconda3', 'envs', 'aquanqa', 'python.exe'),
    join(homedir(), 'anaconda3', 'envs', 'aquanqa', 'python.exe'),
    'C:\\tools\\Anaconda3\\envs\\aquanqa\\python.exe',
  ]
  for (const c of candidates) if (existsSync(c)) return c
  const onPath = which('python') || which('python3')
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
function psql(args, { db } = {}) {
  requirePassword()
  const base = [
    '-v', 'ON_ERROR_STOP=1',
    '--no-psqlrc',
    '-h', env.PGHOST ?? 'localhost',
    '-p', env.PGPORT ?? '5432',
    '-U', env.PGUSER ?? 'postgres',
    '-d', db ?? env.PGDATABASE ?? 'aquanqa',
  ]
  return run(findPsql(), [...base, ...args])
}

function sqlFolder(folder) {
  const dir = join(SQL_DIR, folder)
  if (!existsSync(dir)) fail(`No existe ${dir}`)
  const files = readdirSync(dir).filter((f) => f.endsWith('.sql')).sort()
  if (files.length === 0) {
    log(`${C.yellow}  (sin archivos .sql todavía en ${folder})${C.off}`)
    return
  }
  step(`${folder} — ${files.length} archivo(s)`)
  for (const f of files) psql(['-f', join(dir, f)])
}

function py(args) {
  return run(findPython(), ['-m', 'aquanqa_etl.cli', ...args], { cwd: join(ROOT, 'etl') })
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
    run(findPython(), ['-m', 'pip', 'install', '-e', join(ROOT, 'etl')])
  }

  step('Dependencias npm')
  run(which('npm') ?? 'npm.cmd', ['install'], { allowFail: true })

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

  // Las contraseñas de los roles no viven en el SQL versionado: se aplican aquí desde .env.
  step('Contraseñas de los roles')
  for (const [role, key] of [
    [env.APP_DB_USER ?? 'aquanqa_app', 'APP_DB_PASSWORD'],
    [env.BI_DB_USER ?? 'aquanqa_bi', 'BI_DB_PASSWORD'],
    [env.ETL_DB_USER ?? 'aquanqa_etl', 'ETL_DB_PASSWORD'],
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
 * Incluye 00_bootstrap para que `build` funcione también justo después de un `db:reset`.
 */
const CAPAS_MODELO = [
  '00_bootstrap', '20_core', '30_stg', '40_qua', '50_carga_core', '60_dim_fact', '70_reporting',
]

function cmdBuild() {
  for (const f of CAPAS_MODELO) sqlFolder(f)
  log(`${C.green}✓ Modelo construido. Siguiente: npm run validate${C.off}`)
}

const [target, ...rest] = process.argv.slice(2)
switch (target) {
  case 'setup':    cmdSetup(); break
  case 'sql':      if (!rest[0]) fail('uso: run.mjs sql <carpeta>'); sqlFolder(rest[0]); break
  case 'psql':     psql(rest); break
  case 'py':       py(rest); break
  case 'build':    cmdBuild(); break
  case 'migrate':  sqlFolder('10_raw'); cmdBuild(); break
  case 'validate': sqlFolder('90_checks'); break
  default:
    log(`Uso: node scripts/run.mjs <setup|migrate|build|validate|sql <carpeta>|psql <args>|py <args>>`)
    process.exit(target ? 1 : 0)
}
