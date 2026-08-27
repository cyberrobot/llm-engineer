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

assert(genericWorkflow.jobs && typeof genericWorkflow.jobs === 'object')
assert(
  !Object.entries(genericWorkflow.jobs).some(
    ([jobId, job]) =>
      jobId.toLowerCase().includes('assistant-widget') ||
      job.name?.toLowerCase().includes('assistant widget') ||
      JSON.stringify(job).includes('@redmoor/assistant-widget'),
  ),
  'Generic workflow must not define an Assistant widget job',
)

const triggers = widgetWorkflow.on
const asArray = (value) => (Array.isArray(value) ? value : [value])

assert(triggers?.pull_request, 'Assistant widget workflow must define a pull_request trigger')
assert(
  asArray(triggers.pull_request.branches).includes('main'),
  'Assistant widget pull requests must target main',
)
assert(triggers.pull_request.paths, 'Assistant widget pull requests must use path filtering')
assert(
  asArray(triggers.push?.branches).includes('main'),
  'Assistant widget workflow must run on main pushes',
)

const configuredPaths = asArray(triggers.pull_request.paths)

const expectedPaths = [
  'packages/assistant-widget/**',
  '.changeset/**',
  'package.json',
  'package-lock.json',
  '.github/workflows/test-assistant-widget.yml',
  '.github/workflows/publish-assistant-widget.yml',
]
for (const path of expectedPaths) {
  assert(configuredPaths.includes(path), `Assistant widget paths must include ${path}`)
}

function matchesWidgetPath(path) {
  return configuredPaths.some((pattern) =>
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

assert(widgetWorkflow.jobs && typeof widgetWorkflow.jobs === 'object')

function runsWidgetCommand(step, script) {
  if (typeof step.run !== 'string' || !step.run.includes('@redmoor/assistant-widget')) {
    return false
  }

  const normalizedCommand = step.run.replace(/\s+/g, ' ').trim()
  return normalizedCommand.includes(`npm run ${script} `)
}

const job = Object.values(widgetWorkflow.jobs).find((candidate) =>
  candidate.steps?.some((step) => runsWidgetCommand(step, 'lint')),
)
assert(job, 'Assistant widget workflow must define a widget validation job')
assert(!Object.hasOwn(job, 'if'), 'Assistant widget validation job must run whenever triggered')

const steps = job.steps
assert(Array.isArray(steps), 'Assistant widget validation job must define steps')

const checkout = findStep(
  steps,
  (step) => step.uses?.startsWith('actions/checkout@'),
  'repository checkout',
)
assert.equal(String(checkout.with?.['fetch-depth']), '0')
assertAlwaysRuns(checkout)

const setupNode = findStep(
  steps,
  (step) => step.uses?.startsWith('actions/setup-node@'),
  'Node setup',
)
assertAlwaysRuns(setupNode)

const installDependencies = findStep(
  steps,
  (step) => typeof step.run === 'string' && /(^|\s)npm\s+ci(\s|$)/.test(step.run),
  'dependency installation with npm ci',
)
assertAlwaysRuns(installDependencies)

for (const script of ['lint', 'test', 'build', 'pack:verify']) {
  const step = findStep(
    steps,
    (candidate) => runsWidgetCommand(candidate, script),
    `widget ${script}`,
  )
  assertAlwaysRuns(step)
}

const changeset = findStep(
  steps,
  (step) =>
    typeof step.run === 'string' &&
    /(^|\s)npx\s+changeset\s+status(\s|$)/.test(step.run) &&
    step.run.includes('--since') &&
    step.run.includes('github.event.pull_request.base.sha'),
  'Changesets validation against the pull request base SHA',
)
assert.equal(typeof changeset.if, 'string', 'Changesets validation must define its PR condition')

function evaluateChangesetCondition(expression, context) {
  const variables = {
    'github.event.pull_request.head.repo.full_name': context.headRepository,
    'github.event.pull_request.head.ref': context.headBranch,
    'github.event_name': context.eventName,
    'github.repository': context.repository,
  }
  let substituted = expression.replaceAll('${{', '').replaceAll('}}', '')

  for (const [variable, value] of Object.entries(variables)) {
    substituted = substituted.replaceAll(variable, JSON.stringify(value))
  }

  const withoutStrings = substituted.replace(/'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"/g, '')
  assert(
    /^[\s()!&|=]+$/.test(withoutStrings),
    'Changesets condition contains unsupported variables or operators',
  )

  // Only substituted strings and boolean operators reach the evaluator.
  return Boolean(Function(`"use strict"; return (${substituted})`)())
}

const releasePullRequest = {
  eventName: 'pull_request',
  repository: 'owner/repo',
  headRepository: 'owner/repo',
  headBranch: 'changeset-release/main',
}
assert.equal(evaluateChangesetCondition(changeset.if, releasePullRequest), false)
assert.equal(
  evaluateChangesetCondition(changeset.if, { ...releasePullRequest, headRepository: 'fork/repo' }),
  true,
)
assert.equal(
  evaluateChangesetCondition(changeset.if, { ...releasePullRequest, headBranch: 'feature/widget' }),
  true,
)
assert.equal(
  evaluateChangesetCondition(changeset.if, { ...releasePullRequest, eventName: 'push' }),
  false,
)

const serializedWidgetWorkflow = JSON.stringify(widgetWorkflow)
assert(!serializedWidgetWorkflow.includes('dorny/paths-filter'))
assert(!serializedWidgetWorkflow.includes('steps.filter'))

console.log('Assistant widget CI workflow configuration is valid.')
