# Git

## 30-second answer
Git is a distributed version-control system: every clone has the full history, and work happens in **commits** on **branches** that are merged back. GitHub hosts the repositories and adds pull requests, reviews and Actions. In my projects: **MedVision AI** follows a **feature-branch + pull-request workflow** (`feat/explainable-classifier`, `feat/plain-language-ui`, `chore/cleanup` merged as PRs #44–#49) with **Conventional Commit** messages (`feat(frontend): …`, `fix: …`, `docs: …`) and **pre-commit hooks**; **CareFlow** develops on `develop` (which Render deploys automatically) with commits that reference **decision-log ids** (`… (D-139)`). Model weights are *not* in Git — they are published as **GitHub Releases** with checksums.

---

## Basics you must know

### Core concepts
- **Working directory → staging area (index) → repository.**
- **Commit:** a snapshot + message + parent(s), identified by a SHA hash.
- **Branch:** a movable pointer to a commit. **HEAD:** what you have checked out.
- **Remote:** another copy (e.g. `origin` on GitHub).

### Everyday commands
```bash
git status / git diff / git diff --staged
git add <file> ; git commit -m "feat: add noise gate"
git log --oneline --graph
git switch -c feat/noise-gate          # new branch (older: git checkout -b)
git push -u origin feat/noise-gate
git pull                               # fetch + merge (or --rebase)
git fetch origin
git merge main
git rebase main                        # replay your commits on top of main
git stash / git stash pop
git restore <file>                     # discard working changes
git reset --soft HEAD~1                # undo last commit, keep changes staged
git revert <sha>                       # new commit that undoes a commit (safe on shared branches)
git cherry-pick <sha>
git tag model-v2.2.0
```

### Merge vs rebase
- **Merge** keeps history as it happened (merge commit).
- **Rebase** rewrites your commits onto a new base — linear history. **Never rebase shared/public branches.**

### Resolving conflicts
Edit the conflicted files (`<<<<<<<`, `=======`, `>>>>>>>`), `git add`, then `git commit` (merge) or `git rebase --continue`.

### Branching strategies
- **GitHub Flow:** short-lived feature branches → PR → `main` (deploy from main). *MedVision.*
- **Git Flow:** `develop`, `feature/*`, `release/*`, `main`. CareFlow uses a `develop` branch as its deploy branch.
- **Trunk-based:** tiny branches merged daily, feature flags.

### Good commits
Small and focused; imperative message ("Add …"); explain *why* in the body. **Conventional Commits:** `type(scope): subject` — `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`.

### `.gitignore` and large files
Ignore build outputs, virtualenvs, `.env`, datasets, model files. Use **Git LFS** or **releases/artifact storage** for large binaries.

### Hooks
`pre-commit` framework runs checks before each commit.

---

## How I used it

### MedVision AI
- **Feature branches + PRs:** e.g. `Merge pull request #49 from OmkarJayvantJadhav/feat/explainable-classifier`.
- **Conventional Commits:** `feat(frontend): rewrite the interface in plain language`, `fix(frontend): update the page title…`, `chore: remove dead code and outdated media`, `docs: describe the clinical interface and record D54`.
- **CI on every PR** (lint, types, tests, Docker smoke test) and `main` deploys to Render only after checks pass.
- **Pre-commit hooks** (`.pre-commit-config.yaml`): end-of-file fixer, trailing whitespace, check YAML/TOML, **check merge conflicts**, **detect private keys**, **block files > 1 MB**, plus ruff and mypy through `make lint` / `make typecheck` (same locked versions as CI). Installed by `make setup`.
- **Model artifacts outside Git:** `models/` only has `.gitkeep`; the ONNX model, head weights and gate statistics are attached to a **GitHub Release** (`model-v2.2.0`) with SHA-256 checksums in `model_meta.json`, and the Docker build verifies them.
- `.gitignore` excludes data, artifacts, caches and builds; `.editorconfig` for consistent whitespace.

### CareFlow
- Default/deploy branch **`develop`**; Render redeploys automatically on push (`render.yaml`: `branch: develop`, `autoDeploy: true`).
- Commit messages reference the **decision log** (`docs/DECISIONS.md`, D-00a … D-140), e.g. "Write a hospital's department and doctor pages from its setup (D-139)" — every change can be traced to its reasoning.
- CI runs on every push and PR.
- The trained LightGBM model (small text files) *is* committed in `app/ml/artifacts/` so the image can load it without a training step; `eval/results/` JSON is committed so README numbers are traceable.

---

## Interview questions

**Q: `git merge` vs `git rebase`?**
Merge joins histories with a merge commit (non-destructive). Rebase moves your commits onto another base for a linear history but rewrites hashes — only on your own, unshared branches.

**Q: `git reset` vs `git revert`?**
Reset moves the branch pointer (rewrites history; local use). Revert adds a new commit that undoes an old one (safe for shared branches).

**Q: How do you undo the last commit but keep the changes?**
`git reset --soft HEAD~1`.

**Q: `git fetch` vs `git pull`?**
Fetch downloads remote changes without touching your branch; pull = fetch + merge (or rebase).

**Q: How do you handle large model files?**
Not in Git history — I publish them as GitHub Release assets with checksums (MedVision) and verify them during the Docker build. Git LFS is the other option.

**Q: What's in your PR workflow?**
Feature branch → small commits with Conventional Commit messages → PR → CI must pass (lint, types, tests, Docker smoke test) → merge → automatic deploy after checks.
