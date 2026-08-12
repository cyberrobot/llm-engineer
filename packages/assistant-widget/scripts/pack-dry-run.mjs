import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'

const cacheDirectory = await mkdtemp(join(tmpdir(), 'assistant-widget-pack-cache-'))

try {
  const result = spawnSync('npm', ['pack', '--dry-run', '--json'], {
    cwd: import.meta.dirname + '/..',
    encoding: 'utf8',
    env: { ...process.env, npm_config_cache: cacheDirectory },
  })
  process.stdout.write(result.stdout)
  process.stderr.write(result.stderr)
  if (result.status !== 0) process.exitCode = result.status ?? 1
} finally {
  await rm(cacheDirectory, { recursive: true, force: true })
}
