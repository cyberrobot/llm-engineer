import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { load } from 'js-yaml'

import {
  ADMIN_RELEVANT_PATHS,
  evaluateRequiredGate,
  matchesAdminPath,
} from './run-required-ci-gate.mjs'

const repositoryRoot = new URL('../../../', import.meta.url)
const workflowPath = '.github/workflows/test-admin.yml'
const requiredWorkflowPath = '.github/workflows/test-admin-required.yml'

function readWorkflow(relativePath) {
  const source = readFileSync(new URL(relativePath, repositoryRoot), 'utf8')
  const parsed = load(source)
  assert(parsed && typeof parsed === 'object', `${relativePath} must contain a YAML object`)
  return parsed
}

const workflow = readWorkflow(workflowPath)

assert.equal(workflow.name, 'Admin UI CI')

const asArray = (value) => (Array.isArray(value) ? value : [value])
const triggers = workflow.on

assert(triggers?.pull_request, 'Admin workflow must define a pull_request trigger')
assert(asArray(triggers.pull_request.branches).includes('main'), 'Admin pull requests must target main')
assert(triggers.pull_request.paths, 'Admin pull requests must use path filtering')
assert(asArray(triggers.push?.branches).includes('main'), 'Admin workflow must run on relevant main pushes')
assert(triggers.push.paths, 'Admin main pushes must use path filtering')

const expectedPaths = [
  'apps/admin/**',
  'packages/assistant-widget/**',
  'package.json',
  'package-lock.json',
  '.github/workflows/test-admin.yml',
  '.github/workflows/test-admin-required.yml',
]
const pullRequestPaths = asArray(triggers.pull_request.paths)
const pushPaths = asArray(triggers.push.paths)

assert.deepEqual(pullRequestPaths, expectedPaths, 'Admin pull-request paths must match verified inputs')
assert.deepEqual(pushPaths, expectedPaths, 'Admin push paths must match verified inputs')

assert.deepEqual(ADMIN_RELEVANT_PATHS, expectedPaths, 'Required gate paths must match Admin workflow paths')

const triggerCases = [
  ['apps/admin/src/App.tsx', true],
  ['apps/admin/src/App.test.tsx', true],
  ['apps/admin/src/features/operations/Operations.stories.tsx', true],
  ['apps/admin/package.json', true],
  ['package.json', true],
  ['package-lock.json', true],
  ['packages/assistant-widget/src/AssistantWidget.tsx', true],
  ['.github/workflows/test-admin.yml', true],
  ['.github/workflows/test-admin-required.yml', true],
  ['apps/backend/operations/api/router.py', false],
  ['docs/example.md', false],
  ['.codex/tasks/example.md', false],
]

for (const [path, expected] of triggerCases) {
  assert.equal(matchesAdminPath(path), expected, `Unexpected Admin CI selection for ${path}`)
}

assert(workflow.jobs && typeof workflow.jobs === 'object')
const job = workflow.jobs.admin
assert(job, 'Admin workflow must define the admin job')
assert.equal(job.name, 'Admin validation')
assert(!Object.hasOwn(job, 'if'), 'Admin validation must run whenever the workflow is triggered')
assert(Array.isArray(job.steps), 'Admin validation must define steps')

function findStep(predicate, description) {
  const step = job.steps.find(predicate)
  assert(step, `Admin workflow must include ${description}`)
  return step
}

function assertRequiredStep(step) {
  assert(!Object.hasOwn(step, 'if'), `${step.name} must run whenever the workflow is triggered`)
  assert.notEqual(step['continue-on-error'], true, `${step.name} must fail the Admin validation job`)
}

const checkout = findStep(
  (step) => step.uses?.startsWith('actions/checkout@'),
  'repository checkout',
)
assertRequiredStep(checkout)

const setupNode = findStep(
  (step) => step.uses?.startsWith('actions/setup-node@'),
  'Node setup',
)
assert.equal(String(setupNode.with?.['node-version']), '24')
assert.equal(setupNode.with?.cache, 'npm')
assert.equal(setupNode.with?.['cache-dependency-path'], 'package-lock.json')
assertRequiredStep(setupNode)

const installDependencies = findStep(
  (step) => typeof step.run === 'string' && /(^|\s)npm\s+ci(\s|$)/.test(step.run),
  'dependency installation with npm ci',
)
assertRequiredStep(installDependencies)

function runsAdminScript(step, script) {
  if (typeof step.run !== 'string' || !step.run.includes('@ai-discovery-assistant/admin')) {
    return false
  }

  const normalizedCommand = step.run.replace(/\s+/g, ' ').trim()
  if (script === 'test') {
    return normalizedCommand.startsWith('npm test ')
  }
  return normalizedCommand.startsWith(`npm run ${script} `)
}

for (const script of ['test', 'lint', 'typecheck', 'build', 'build-storybook']) {
  const step = findStep(
    (candidate) => runsAdminScript(candidate, script),
    `Admin ${script}`,
  )
  assertRequiredStep(step)
}

for (const [script, description] of [
  ['install-playwright', 'Playwright Chromium installation'],
  ['test:e2e', 'Admin browser tests'],
]) {
  const step = findStep(
    (candidate) => runsAdminScript(candidate, script),
    description,
  )
  assertRequiredStep(step)
  assert(
    !step.run.includes('--update-snapshots'),
    `${step.name} must not update visual baselines in CI`,
  )
}

const serializedWorkflow = JSON.stringify(workflow)
assert(!serializedWorkflow.includes('dorny/paths-filter'))
assert(!serializedWorkflow.includes('steps.filter'))

const requiredWorkflow = readWorkflow(requiredWorkflowPath)
assert.equal(requiredWorkflow.name, 'Admin UI CI required gate')
assert(requiredWorkflow.on?.pull_request, 'Required Admin gate must run for pull requests')
assert(
  asArray(requiredWorkflow.on.pull_request.branches).includes('main'),
  'Required Admin gate pull requests must target main',
)
assert(
  !Object.hasOwn(requiredWorkflow.on.pull_request, 'paths'),
  'Required Admin gate must be present on Admin-relevant and unrelated pull requests',
)
assert(!requiredWorkflow.on.push, 'Required Admin gate is a pull-request merge condition only')

const requiredJob = requiredWorkflow.jobs?.required
assert(requiredJob, 'Required Admin workflow must define the required job')
assert.equal(requiredJob.name, 'Admin UI CI / Required')
assert(!Object.hasOwn(requiredJob, 'if'), 'Required Admin gate must run on every pull request')
assert.notEqual(requiredJob['continue-on-error'], true, 'Required Admin gate failures must block merging')
assert.equal(requiredJob.permissions?.actions, 'read')
assert.equal(requiredJob.permissions?.['pull-requests'], 'read')

const gateStep = requiredJob.steps?.find(
  (step) => step.run === 'node apps/admin/scripts/run-required-ci-gate.mjs',
)
assert(gateStep, 'Required Admin gate must execute its verified gate implementation')
assertRequiredStep(gateStep)

for (const [path, expected] of triggerCases) {
  const result = evaluateRequiredGate([path])
  assert.equal(
    result.outcome,
    expected ? 'waiting' : 'not_applicable',
    `Unexpected required Admin gate selection for ${path}`,
  )
}

const relevantPaths = ['apps/admin/src/App.tsx']
assert.equal(
  evaluateRequiredGate(relevantPaths, { status: 'completed', conclusion: 'success' }).outcome,
  'success',
)
for (const conclusion of ['failure', 'cancelled', 'skipped', 'timed_out', 'neutral', 'stale']) {
  assert.equal(
    evaluateRequiredGate(relevantPaths, { status: 'completed', conclusion }).outcome,
    'failure',
    `Required Admin gate must fail when validation concludes ${conclusion}`,
  )
}
assert.equal(
  evaluateRequiredGate(relevantPaths, { status: 'in_progress', conclusion: null }).outcome,
  'waiting',
)
assert.equal(evaluateRequiredGate(relevantPaths).outcome, 'waiting')

console.log('Admin CI workflow configuration is valid.')
