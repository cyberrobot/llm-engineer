import { cp, mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'

const packageDirectory = resolve(import.meta.dirname, '..')
const fixtureDirectory = join(packageDirectory, 'test-fixtures', 'consumer')
const temporaryDirectory = await mkdtemp(join(tmpdir(), 'assistant-widget-package-'))
const npmCacheDirectory = join(temporaryDirectory, 'npm-cache')

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: 'utf8',
    env: { ...process.env, npm_config_cache: npmCacheDirectory },
  })
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed\n${result.stdout}\n${result.stderr}`)
  }
  return result.stdout
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

try {
  const packResult = JSON.parse(
    run('npm', ['pack', '--json', '--pack-destination', temporaryDirectory], packageDirectory),
  )[0]
  const publishedFiles = packResult.files.map(({ path }) => path).sort()
  const requiredFiles = ['README.md', 'dist/index.d.ts', 'dist/index.js', 'dist/styles.css', 'package.json']

  for (const path of requiredFiles) {
    assert(publishedFiles.includes(path), `Packed artifact is missing ${path}`)
  }
  for (const path of publishedFiles) {
    assert(
      path === 'README.md' || path === 'package.json' || path.startsWith('dist/'),
      `Packed artifact contains an unintended file: ${path}`,
    )
    assert(
      !/(^|\/)(?:test-fixtures|demo|mocks?|coverage)(\/|\.|$)|\.(?:test|spec)\./i.test(path),
      `Packed artifact contains development-only content: ${path}`,
    )
  }

  const metadata = JSON.parse(await readFile(join(packageDirectory, 'package.json'), 'utf8'))
  assert(metadata.name === '@redmoor/assistant-widget', 'Package name is incorrect')
  assert(packResult.version === metadata.version, 'Packed package version differs from its manifest')
  assert(metadata.private === false, 'Package must be publishable')
  assert(metadata.exports?.['.']?.import === './dist/index.js', 'JavaScript export is incorrect')
  assert(metadata.exports?.['.']?.types === './dist/index.d.ts', 'Type export is incorrect')
  assert(metadata.exports?.['./styles.css'] === './dist/styles.css', 'CSS export is incorrect')
  assert(metadata.peerDependencies?.react, 'React must be a peer dependency')
  assert(metadata.peerDependencies?.['react-dom'], 'React DOM must be a peer dependency')
  assert(metadata.peerDependencies.react === '^19.0.0', 'React peer range is incorrect')
  assert(metadata.peerDependencies['react-dom'] === '^19.0.0', 'React DOM peer range is incorrect')
  assert(Object.keys(metadata.dependencies ?? {}).length === 0, 'Unexpected runtime dependencies')

  const builtJavaScript = await readFile(join(packageDirectory, 'dist', 'index.js'), 'utf8')
  assert(/from\s*["']react["']/.test(builtJavaScript), 'React import was not externalised')
  assert(!builtJavaScript.includes('@ai-discovery-assistant/'), 'Bundle contains a workspace alias')
  assert(!builtJavaScript.includes('import.meta.env'), 'Bundle contains a Vite environment reference')
  assert(!builtJavaScript.includes('Mock answer'), 'Bundle contains demo code')

  const consumerDirectory = join(temporaryDirectory, 'consumer')
  await cp(fixtureDirectory, consumerDirectory, { recursive: true })
  const tarball = join(temporaryDirectory, packResult.filename)
  run(
    'npm',
    ['install', '--ignore-scripts', '--no-audit', '--no-fund', '--package-lock=false', tarball],
    consumerDirectory,
  )
  run('npm', ['run', 'typecheck'], consumerDirectory)
  run('npm', ['run', 'build'], consumerDirectory)
  run(
    'node',
    ['--input-type=module', '--eval', "await import('@redmoor/assistant-widget')"],
    consumerDirectory,
  )

  console.log(JSON.stringify({
    filename: packResult.filename,
    packedSize: packResult.size,
    unpackedSize: packResult.unpackedSize,
    files: publishedFiles,
  }, null, 2))
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true })
}
