import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { load } from 'js-yaml'

const repositoryRoot = new URL('../../../', import.meta.url)

function readWorkflow(relativePath) {
  const source = readFileSync(new URL(relativePath, repositoryRoot), 'utf8')
  const workflow = load(source)

  assert(workflow && typeof workflow === 'object', `${relativePath} must contain a YAML object`)
  return workflow
}

function findStep(steps, predicate, description) {
  const step = steps.find(predicate)
  assert(step, `Assistant widget workflow must include ${description}`)
  return step
}

function assertAlwaysRuns(step) {
  assert(!Object.hasOwn(step, 'if'), `${step.name} must run for every triggered workflow`)
}

const genericWorkflow = readWorkflow('.github/workflows/test.yml')
const widgetWorkflow = readWorkflow('.github/workflows/test-assistant-widget.yml')

assert(!Object.hasOwn(genericWorkflow.jobs, 'assistant-widget'))
assert(
  !Object.values(genericWorkflow.jobs).some((job) => job.name?.includes('Assistant widget')),
  'Generic workflow must not define an Assistant widget job',
)

assert.equal(widgetWorkflow.name, 'Assistant widget CI')

const triggers = widgetWorkflow.on
assert(triggers?.pull_request, 'Assistant widget workflow must define a pull_request trigger')
assert.deepEqual(triggers.pull_request.branches, ['main'])
assert.deepEqual(triggers.push?.branches, ['main'])

const expectedPaths = [
  'packages/assistant-widget/**',
  '.changeset/**',
  'package.json',
  'package-lock.json',
  '.github/workflows/test-assistant-widget.yml',
  '.github/workflows/publish-assistant-widget.yml',
]
assert.deepEqual(triggers.pull_request.paths, expectedPaths)

function matchesWidgetPath(path) {
  return expectedPaths.some((pattern) =>
    pattern.endsWith('/**') ? path.startsWith(pattern.slice(0, -2)) : path === pattern,
  )
}

const triggerCases = [
  ['packages/assistant-widget/src/AssistantWidget.tsx', true],
  ['packages/assistant-widget/package.json', true],
  ['package.json', true],
  ['package-lock.json', true],
  ['.changeset/widget.md', true],
  ['.github/workflows/test-assistant-widget.yml', true],
  ['.github/workflows/publish-assistant-widget.yml', true],
  ['apps/admin/src/App.tsx', false],
  ['apps/backend/operations/api/router.py', false],
  ['docs/widget.md', false],
  ['.codex/tasks/widget.md', false],
]

for (const [path, expected] of triggerCases) {
  assert.equal(matchesWidgetPath(path), expected, `Unexpected widget CI selection for ${path}`)
}

const job = widgetWorkflow.jobs?.test
assert(job, 'Assistant widget workflow must define its validation job')
assert.equal(job.name, 'Assistant widget validation')

const steps = job.steps
assert(Array.isArray(steps), 'Assistant widget validation job must define steps')

const checkout = findStep(
  steps,
  (step) => step.uses === 'actions/checkout@v4',
  'actions/checkout@v4',
)
assert.equal(checkout.with?.['fetch-depth'], 0)
assertAlwaysRuns(checkout)

const setupNode = findStep(
  steps,
  (step) => step.uses === 'actions/setup-node@v4',
  'actions/setup-node@v4',
)
assertAlwaysRuns(setupNode)

const requiredCommands = [
  'npm ci',
  'npm run verify:ci --workspace @redmoor/assistant-widget',
  'npm run lint --workspace @redmoor/assistant-widget',
  'npm run test --workspace @redmoor/assistant-widget',
  'npm run build --workspace @redmoor/assistant-widget',
  'npm run pack:verify --workspace @redmoor/assistant-widget',
]

for (const command of requiredCommands) {
  const step = findStep(steps, (candidate) => candidate.run === command, command)
  assertAlwaysRuns(step)
}

const changeset = findStep(
  steps,
  (step) => step.run === 'npx changeset status --since=${{ github.event.pull_request.base.sha }}',
  'Changesets validation against the pull request base SHA',
)
const expectedChangesetCondition =
  "github.event_name == 'pull_request' && " +
  '(github.event.pull_request.head.repo.full_name != github.repository || ' +
  "github.event.pull_request.head.ref != 'changeset-release/main')"
assert.equal(changeset.if, expectedChangesetCondition)

const isCanonicalReleasePullRequest = (repository, headRepository, headBranch) =>
  repository === headRepository && headBranch === 'changeset-release/main'

assert(isCanonicalReleasePullRequest('owner/repo', 'owner/repo', 'changeset-release/main'))
assert(!isCanonicalReleasePullRequest('owner/repo', 'fork/repo', 'changeset-release/main'))
assert(!isCanonicalReleasePullRequest('owner/repo', 'owner/repo', 'feature/widget'))

const serializedWidgetWorkflow = JSON.stringify(widgetWorkflow)
assert(!serializedWidgetWorkflow.includes('dorny/paths-filter'))
assert(!serializedWidgetWorkflow.includes('steps.filter'))

console.log('Assistant widget CI workflow configuration is valid.')
