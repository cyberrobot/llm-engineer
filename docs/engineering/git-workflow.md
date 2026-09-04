# Git and GitHub Workflow

When Git operations are requested, inspect `git status -sb` and the focused diff first. Fetch the latest remote state before creating a feature branch; create it from `origin/main` with `git switch --no-track -c <branch> origin/main` and do not track the default branch.

Stage only in-scope files and leave unrelated work untouched. Commit a concise complete description. On first push, use `git push --set-upstream origin <branch>` and verify the same-named remote branch tracks it; never push to the default branch.

Open a draft pull request against the repository default branch unless requested otherwise. Its Markdown body should describe the change, impact, and checks that actually passed. Report the branch, commit, base, URL, draft state, and deliberately uncommitted files.

Before requesting login, run `gh auth status` and `gh repo view --json nameWithOwner,defaultBranchRef` with required host permission. Request `gh auth login` only if those checks fail outside the sandbox.
