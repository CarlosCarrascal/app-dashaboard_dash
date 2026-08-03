import { defineConfig } from 'drizzle-kit'

/**
 * Drizzle gobierna únicamente `core` — el modelo operativo que escribe la aplicación.
 * Las capas raw/stg/qua/dim/fact/reporting son SQL versionado en `sql/` (ADR-0004),
 * y se excluyen de la introspección para que `drizzle-kit check` no las reclame.
 */
export default defineConfig({
  dialect: 'postgresql',
  schema: './drizzle/schema/*.ts',
  out: './drizzle/migrations',
  schemaFilter: ['core'],
  dbCredentials: {
    url:
      process.env.DATABASE_URL ??
      `postgresql://${process.env.PGUSER ?? 'postgres'}:${process.env.PGPASSWORD ?? ''}` +
        `@${process.env.PGHOST ?? 'localhost'}:${process.env.PGPORT ?? '5432'}/` +
        `${process.env.PGDATABASE ?? 'aquanqa'}`,
  },
  verbose: true,
  strict: true,
})
