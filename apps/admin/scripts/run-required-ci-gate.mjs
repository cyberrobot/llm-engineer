import assert from 'node:assert/strict'
import { appendFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

export const ADMIN_RELEVANT_PATHS = [
  'apps/admin/**',
  'packages/assistant-widget/**',
  'package.json',
  'package-lock.json',
  '.github/workflows/test-admin.yml',
  '.github/workflows/test-admin-required.yml',
]

export function matchesAdminPath(path) {
  return ADMIN_RELEVANT_PATHS.some((pattern) =>
    pattern.endsWith('/**') ? path.startsWith(pattern.slice(0, -2)) : path === pattern,
  )
}

export function evaluateRequiredGate(paths, validationRun) {
  if (!paths.some(matchesAdminPath)) {
    return { outcome: 'not_applicable' }
  }
  if (!validationRun || validationRun.status !== 'completed') {
    return { outcome: 'waiting' }
  }
  if (validationRun.conclusion === 'success') {
    return { outcome: 'success', validationRun }
  }
  return { outcome: 'failure', validationRun }
}

function requiredEnvironment(name) {
  const value = process.env[name]
  assert(value, `${name} must be set`)
  return value
}

async function githubJson(path) {
  const apiUrl = requiredEnvironment('ADMIN_GATE_API_URL')
  const token = requiredEnvironment('GITHUB_TOKEN')
  const response = await fetch(`${apiUrl}${path}`, {
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
    },
  })
  if (!response.ok) {
    throw new Error(`GitHub API request failed with ${response.status} ${response.statusText}`)
  }
  return response.json()
}

async function listPullRequestPaths(repository, pullRequest) {
  const paths = []
  for (let page = 1; ; page += 1) {
    const files = await githubJson(
      `/repos/${repository}/pulls/${pullRequest}/files?per_page=100&page=${page}`,
    )
    paths.push(...files.map((file) => file.filename))
    if (files.length < 100) {
      return paths
    }
  }
}

async function findValidationRun(repository, pullRequest, headSha) {
  const response = await githubJson(
    `/repos/${repository}/actions/workflows/test-admin.yml/runs?event=pull_request&head_sha=${headSha}&per_page=100`,
  )
  return response.workflow_runs.find((run) =>
    run.pull_requests.some((candidate) => String(candidate.number) === pullRequest),
  )
}

function writeSummary(message) {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY
  if (summaryPath) {
    appendFileSync(summaryPath, `${message}\n`)
  }
  console.log(message)
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

export async function runRequiredGate() {
  const repository = requiredEnvironment('ADMIN_GATE_REPOSITORY')
  const pullRequest = requiredEnvironment('ADMIN_GATE_PULL_REQUEST')
  const headSha = requiredEnvironment('ADMIN_GATE_HEAD_SHA')
  const paths = await listPullRequestPaths(repository, pullRequest)
  let result = evaluateRequiredGate(paths)

  if (result.outcome === 'not_applicable') {
    writeSummary('Admin validation is not applicable because this pull request has no Admin-impacting changes.')
    return
  }

  const deadline = Date.now() + 20 * 60 * 1000
  while (Date.now() < deadline) {
    const validationRun = await findValidationRun(repository, pullRequest, headSha)
    result = evaluateRequiredGate(paths, validationRun)
    if (result.outcome === 'success') {
      writeSummary(`Required Admin validation passed: ${validationRun.html_url}`)
      return
    }
    if (result.outcome === 'failure') {
      throw new Error(
        `Required Admin validation concluded ${validationRun.conclusion}: ${validationRun.html_url}`,
      )
    }
    await delay(15_000)
  }

  throw new Error('Required Admin validation did not complete within 20 minutes.')
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await runRequiredGate()
}
