# Session Handoff — 2026-08-01 → 2026-08-02

Audit remediation on `taskflow-api`, branch `develop`. This document is written to be
read cold: it assumes no memory of the previous session.

Governing documents, in order of authority:

1. `docs/audit/TODO.md` — the prioritized roadmap. **The work order.**
2. `docs/audit/AUDIT_REPORT.md` — the 57 findings, with implementation notes in §12.5.
3. `docs/audit/PROJECT_CONTEXT.md` — environment, stack, working-tree warnings.
4. This file — state as of the end of the 2026-08-01 session.

**Working agreement in force (from `TODO.md`, do not deviate):** one issue at a time,
smallest safe change, regression test for every fix, never touch unrelated code, do not
re-run the audit, stop and wait for approval after each issue.

---

## 1. Current Status

### Completed and verified this session

**C-2 — `is_staff` defaulted to `True` for every signup.** Code and migration were
finished in the prior session; this session closed the documentation step (implementation
note in `AUDIT_REPORT.md` §12.5). **Marked DONE in TODO.md.**

**M-3 — CI ran none of the quality tooling the project declared.** Added a `lint` stage
to `.gitlab-ci.yml` with three jobs, created `.flake8`, added `coverage` to the dev
dependency group with a measured floor in `pyproject.toml`, and wrote 11 regression tests
in `src/taskflow/tests_ci_config.py`. **Marked DONE in TODO.md.**

**C-3 — Production could not boot.** This was the session's main work. All six planned
sub-tasks are implemented and the primary success criterion is met: **`check --deploy`
went from 26 issues to zero**, and production settings now import and serve.

### In progress — nothing is mid-edit

C-3's implementation is complete, the tree is green, and its bookkeeping was completed
after the implementation freeze (documentation was the one change still permitted):

- ✅ `docs/audit/TODO.md` — C-3 marked `### ✅ … DONE 2026-08-01`, with M-6/S-15/S-13/S-14
  recorded as subsumed. The stale "advisory gates" note and the suggested-order list were
  updated so nothing still claims C-3 is open.
- ✅ `docs/audit/AUDIT_REPORT.md` §12.5 — C-3 implementation note added.
- ❌ **The C-3 summary has never been presented to the user for approval.** The working
  agreement requires that before C-4 starts.

**So the next session's first act is to present the C-3 summary and wait — not to write
code, and not to redo the TODO/report entries.** Details in §5.

### Intentionally left unfinished

| Item | Why |
|---|---|
| `lint_style` job is advisory (`allow_failure: true`) | Clearing it is a repo-wide `black` reformat of 47 files plus 183 flake8 findings. That is its own commit; "never touch unrelated code" rules it out as a side-effect of C-3. |
| Migration `0003` not applied to the dev database | Applying it changes local data (5 users lose `is_staff`). That is the developer's call, not mine. Command in §4. |
| `SECRET_KEY` rotation for the real deployment | The code path is fixed — production reads `DJANGO_SECRET_KEY` from the environment with no fallback. **Rotating the actual deployed secret is an operational act outside the repo** and must be done by whoever holds the deployment environment. See §6. |
| Nothing committed | No commit was ever requested. See §2. |
| `boards` app (C-4) | Next issue, not this one. |

---

## 2. Repository State

**Nothing is committed. Every change below is uncommitted in the working tree.** Three
audit issues' worth of work (C-2, M-3, C-3) sits unstaged on `develop`.

### Modified — C-3 (this session)

| File | Change |
|---|---|
| `src/taskflow/settings/base.py` | Adopted `django-environ`. `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASES`, `CACHES` LOCATION, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` are all env-driven with dev-safe defaults. Removed `debug_toolbar` middleware. Replaced the committed dev key with a freshly generated throwaway. |
| `src/taskflow/settings/development.py` | Received the `debug_toolbar` middleware (order preserved). `DATABASES` now honours `DATABASE_URL` with the compose values as its default. |
| `src/taskflow/settings/production.py` | **Rewritten from a 3-line stub into a real module** (~80 lines). |
| `src/taskflow/urls.py` | `drf_spectacular` and `debug_toolbar` includes moved behind `apps.is_installed()` guards; their imports are no longer unconditional. |
| `src/taskflow/celery.py` | Removed the import-time `DJANGO_SETTINGS_MODULE` `setdefault`, and the now-unused `import os`. |
| `src/taskflow/wsgi.py`, `src/taskflow/asgi.py` | Default changed from the settings *package* to `taskflow.settings.production`. |
| `.gitlab-ci.yml` | `deploy_check` now targets production settings and is **blocking**. Removed `echo "$DOTENV_CONTENT" > src/taskflow/.env` (S-15); added `DATABASE_URL` / `REDIS_URL` as plain CI variables. |

### Added — C-3 (this session)

- `.env.example` — every name the settings read, with safe placeholders. Confirmed **not**
  gitignored, so it will be committed as intended (`src/taskflow/.env` *is* ignored, at
  `.gitignore:210`).
- `src/taskflow/tests_production_settings.py` — 19 regression tests (see §3).

### Modified / added earlier — C-2 and M-3, still uncommitted

- `src/taskflow/accounts/models.py`, `src/taskflow/accounts/tests.py`
- `src/taskflow/accounts/migrations/0003_alter_customuser_is_staff.py` (untracked)
- `.flake8` (untracked), `pyproject.toml`, `poetry.lock`
- `src/taskflow/tests_ci_config.py` (untracked)

### Intentionally untouched — do not "fix" these

- **`src/taskflow/companies/tasks.py`**, **`companies/tests.py`**, **`companies/views.py`** —
  these carry the **developer's own uncommitted in-progress work**, present before this
  remediation began. Standing instruction: *do not modify them unless explicitly agreed.*
  Note the unregistered task (missing `@` on `shared_task`) inside `tasks.py` is tracked
  separately as **Q-1**; do not fix it as a drive-by.
- `docs/audit/*` other than TODO.md and AUDIT_REPORT.md.
- `nginx/`, `docker/`, `docker-compose*.yaml`, `scripts/` — read only; no changes needed.

### Local-only state NOT in the repository

1. **Four repo-root files copied into the container at `/app/`** — `.gitlab-ci.yml`,
   `pyproject.toml`, `.flake8`, `.env.example`. The dev stack bind-mounts **only `./src`
   and `./scripts`**, so repo-root files are invisible in-container. The config tests
   *skip* rather than fail without them. These copies are throwaway; they will vanish on
   container rebuild and must be re-copied to run those tests in-container. Commands in §3.
2. **`coverage 7.6.1` pip-installed into the container venv** at runtime, as root
   (`docker exec -u root`), because the runtime user `appuser` cannot write to
   `/app/.venv`. It is declared in `pyproject.toml`/`poetry.lock` but **not in the built
   image** — it disappears on rebuild.
3. **Migration `0003` is still unapplied** to the dev database (`showmigrations accounts`
   shows `[ ] 0003`).

---

## 3. Validation Performed

### Test results

| Suite | Result |
|---|---|
| **Full suite** (`manage.py test taskflow`) | **161 tests, `OK`** in 1739s (~29 min) |
| `tests_production_settings` (in-container, no repo root) | 15 run, **`OK`**, 2 classes skipped |
| `tests_production_settings` + `tests_ci_config` (repo root copied in) | **30 tests, `OK`**, 0 skipped |

The full suite was 131 tests when the M-3 coverage baseline was measured, then 142 with
M-3's tests. It is now **161** with C-3's 19. No failures, no errors.

Commands used:

```bash
# Full suite (~29 min)
docker exec -w /app/src taskflow_web /app/.venv/bin/python manage.py test taskflow \
  --settings=taskflow.settings.development

# C-3 tests only (~1 min)
docker exec -w /app/src taskflow_web /app/.venv/bin/python manage.py test \
  taskflow.tests_production_settings --settings=taskflow.settings.development

# To un-skip the config tests, copy the repo-root files in first:
for f in .gitlab-ci.yml pyproject.toml .flake8 .env.example; do
  docker cp "$f" taskflow_web:/app/"$f"
done
```

Note the container's working directory must be `/app/src`; `-w /app/src` is required or
Python cannot find the `taskflow` package.

### The fix was verified to fail before and pass after

`test_missing_database_url_is_fatal` **failed on first run** —
`AssertionError: 0 == 0 : production booted without DATABASE_URL`. That failure was
genuine and is worth understanding, because the first diagnosis was wrong:

- **Wrong first guess:** that `env.db()` silently returns instead of raising. A direct
  probe disproved it — `env.db('UNSET')` raises
  `ImproperlyConfigured: Set the UNSET environment variable`. A guard line added to
  `production.py` on that assumption was **reverted**.
- **Actual cause:** `base.py` reads `src/taskflow/.env`, which exists in this container
  and *contains* `DATABASE_URL`. The subprocess harness therefore never saw the variable
  as absent. The test's own comment claimed to isolate the `.env` but did not.
- **Fix:** `base.py` now accepts `DJANGO_ENV_FILE` to override the env-file location, and
  the harness points it at a non-existent path. Deploys leave it unset.

### `check --deploy` — the C-3 success criterion

```
production, full environment  → "System check identified no issues (0 silenced)."  exit 0
production, empty environment → ImproperlyConfigured: Set the DJANGO_SECRET_KEY ... exit 1
development                   → "System check identified no issues (0 silenced)."  exit 0
```

**26 issues → 0.** The empty-environment case exiting 1 is the deliberate design: a
misconfigured deploy must fail at startup, not boot insecurely.

One intermediate result worth knowing: a first pass reported exactly one remaining
warning, `security.W009` (SECRET_KEY too short). That was an artifact of the short probe
key, not a config defect; re-running with a 64-byte key gave zero. Any placeholder secret
used with this gate must be ≥ 50 chars and not prefixed `django-insecure-`.

### Linting

| Gate | Result |
|---|---|
| Blocking tier — `flake8 src --select=E9,F63,F7,F82` | **0 findings, exit 0** ✅ |
| Advisory sweep — `flake8 src` | **183 findings** (was 186 before C-3) |

The blocking tier being clean matters: removing `import os` from `celery.py` would
otherwise have tripped F401 and turned the pipeline red.

Largest advisory buckets: 24 × `W292` (no newline at EOF), 11 × `W391` (blank line at
EOF). Nearly all of it is mechanical `black` work.

### Coverage — NOT re-measured, and why

**There is no new coverage number.** The full-suite coverage run completed with all 161
tests `OK`, but coverage could not write its data file:

```
Couldn't use data file '/app/src/.coverage': unable to open database file
```

`appuser` cannot write to `/app/src`. The **last known good figure is 68%** (statements),
measured during M-3 on the 131-test suite, against which `fail_under = 65` was
calibrated. The floor is almost certainly still satisfied — 30 tests were added and no
source was deleted — **but this is inference, not measurement. Do not report a coverage
number as verified until it is re-run.** To fix, direct the data file somewhere writable:

```bash
docker exec -w /app/src -e COVERAGE_FILE=/tmp/.coverage taskflow_web \
  /app/.venv/bin/python -m coverage run --rcfile=/app/pyproject.toml \
  manage.py test taskflow --settings=taskflow.settings.development
docker exec -w /app/src -e COVERAGE_FILE=/tmp/.coverage taskflow_web \
  /app/.venv/bin/python -m coverage report --rcfile=/app/pyproject.toml
```

### Warnings that remain

- 183 advisory flake8 findings; 47 files unformatted by `black`. Both non-blocking by
  design.
- `security.W009` will fire in any environment whose `DJANGO_SECRET_KEY` is short or
  `django-insecure-`-prefixed. Correct behavior, not a defect.
- The two config test classes skip when repo-root files are not mounted. Deliberate:
  `CIConfigLocationTests` runs unconditionally so a broken `REPO_ROOT` fails loudly
  instead of turning the whole module into silent skips.

---

## 4. Known Issues

### Blocking nothing, but must be recorded

**C-3's TODO.md / AUDIT_REPORT.md entries are not written, and the C-3 summary was never
presented for approval.** The working agreement requires both before moving on. Cause:
the session was halted for handoff mid-bookkeeping. **Highest-priority item next session.**

**No coverage measurement for the current tree** (§3). Re-run before claiming the floor
holds.

**Nothing is committed.** Three issues' worth of work is unstaged, interleaved in the same
working tree as the developer's own in-progress `companies/*` changes. Anyone committing
must stage **selectively** — `git add .` would capture the developer's work too. See §7.

### Deferred deliberately

| Issue | Why not now | Risk of continuing |
|---|---|---|
| Migration `0003` unapplied | Changes local data (5 users demoted) | Local `is_staff` behavior won't match the code until applied |
| **S-8** — `companies/admin.py:316` owner dropdown | C-2 made this **live rather than theoretical**: the dropdown filters on `is_staff=True`, which now matches almost nobody. Entangled with Q-17. | Admin-created companies are hard to assign an owner. Do not start it unprompted. |
| `lint_style` advisory | Repo-wide reformat; own commit | Style debt keeps accruing |
| Q-1 — missing `@` in `companies/tasks.py` | Lives in the developer's uncommitted work | Do not drive-by fix |
| `pytest`/`pytest-django` declared but unused; CI uses `manage.py test` | Reconciling the runner is tracked under **M-8**, not M-3 | Two runners declared, one used |

### Risks for whoever continues

1. **The `.env` masking trap.** `base.py` reads `src/taskflow/.env`, so a locally-present
   variable can make a "fails when unset" test pass for the wrong reason. Use
   `DJANGO_ENV_FILE` pointing at a non-existent path. This already produced one wrong
   diagnosis (§3).
2. **`wsgi.py`/`asgi.py` now default to production.** Intended, but it means anything
   importing them without `DJANGO_SETTINGS_MODULE` set will demand a full production
   environment and fail loudly. That is the desired behavior; don't "fix" it by restoring
   a development default.
3. **Container rebuild wipes local-only state** (§2): re-copy the repo-root files and
   re-install `coverage`.
4. **The full suite takes ~29 minutes.** Run targeted tests first; budget for the full run.

---

## 5. Next Task

### Step 0 (mandatory first) — present C-3 for approval

The document updates are already done (TODO.md marked DONE, AUDIT_REPORT.md §12.5 note
added, forward-references corrected). **Do not redo them.** What remains is the one step
that needs a human: present a concise C-3 summary — modified files, why the fix is
correct, what was verified, and the three things that did *not* come with it (CSP,
rotation of the real deployed secret, coverage re-measurement) — then **wait for
approval** before touching C-4.

**When discussing the `SECRET_KEY` work: reference it by name only. Never copy the old
committed literal into any document, message, or commit.** It is already in git history;
do not amplify it.

### Then — C-4, verbatim from `docs/audit/TODO.md`

> ### C-4 — The `boards` app is wholly non-functional
> - **Description:** Views/serializers treat `owner`/`members` as users; the model and
>   migration declare `companies.Membership`. Create → `400 {}`; list → `500`.
> - **Complexity:** L
> - **Dependencies:** none technically, but **do Q-13 and Q-15 in the same pass** — the
>   role vocabulary fork is entangled with the model mismatch.
> - **Impact:** Restores a core feature. **Recommended interim step (S):** unregister the
>   `boards` routes now so the broken surface is not exposed, then fix properly and write
>   the test suite before re-enabling.
> - **Warning:** `boards/tests.py` is 0 lines. Any fix here is unverifiable until a suite
>   exists — budget for writing it, not just for the fix.

**Why it is next:** it is the last Critical issue (C-1, C-2, C-3 done), TODO.md line 391
names it as the successor, and it is the largest available coverage win —
`boards/views.py` sits at 30%.

**Prerequisites:** C-3 bookkeeping closed and approved; `boards/` not yet read (C-3 never
touched it — budget discovery time); decide with the user whether to take the interim
route-unregistration step, since it changes the public API surface.

**Implementation plan:**

1. Read `boards/models.py`, `views.py`, `serializers.py`, `urls.py`, and migrations.
   Establish whether `owner`/`members` should be `User` or `companies.Membership` — the
   model and migration say `Membership`; the views and serializers assume `User`. **That
   decision governs everything else and is worth confirming with the user.**
2. Reproduce both failures live (create → `400 {}`, list → `500`) and record the output
   as the before-evidence.
3. **Write `boards/tests.py` from zero, first.** It is 0 lines today, so nothing here is
   verifiable without it. Cover create/list/retrieve/update/delete, the membership
   relation, and permissions. Expect it to be red.
4. Fix the model/serializer/view mismatch in the direction chosen in step 1.
5. Fold in **Q-13** (`boards/views.py:70–80` — the success `Response` sits inside
   `if settings.DEBUG`, so production falls through to `Response(serializer.errors, 400)`
   with `errors == {}`) and **Q-15**, per the dependency note.
6. Run `boards` tests, then the full suite. Re-measure coverage with the `COVERAGE_FILE`
   workaround from §3 and **ratchet `fail_under` in `pyproject.toml`** upward, as TODO.md
   line 393 asks.
7. Mark C-4 done in TODO.md, note it in AUDIT_REPORT.md §12.5, summarize, wait.

---

## 6. Important Context

### Architectural decisions made this session

**Production reads secrets from the environment with no defaults.** `env("DJANGO_SECRET_KEY")`,
`env.list("DJANGO_ALLOWED_HOSTS")`, and `env.db("DATABASE_URL")` all raise
`ImproperlyConfigured` when unset. A misconfigured deploy dies at startup rather than
booting on development fallbacks. **This loud failure is the feature. Do not add defaults
to `production.py`.**

**Debug-only wiring is keyed on `INSTALLED_APPS`, not `DEBUG`.** `urls.py` uses
`apps.is_installed('debug_toolbar')` / `('drf_spectacular')`. The apps are added in
`development.py`, so `is_installed()` reflects what is actually loaded; `DEBUG` is a
separate flag that could be toggled independently and would be a guess.

**`celery.py` no longer sets `DJANGO_SETTINGS_MODULE`.** This was the session's most
consequential discovery, and it was worse than the audit documented. `taskflow/__init__.py`
imports `celery.py`, which called
`os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'taskflow.settings.development')` at
import time — *before* `wsgi.py` could apply its own default. **A gunicorn deploy that
omitted the variable silently served production traffic with `DEBUG=True`.** Every
entrypoint now supplies the variable explicitly (`manage.py`, `wsgi.py`, `asgi.py`,
compose); a bare `celery -A taskflow` with nothing set now fails loudly, which is correct.

**`wsgi.py`/`asgi.py` default to `taskflow.settings.production`.** The old default named
the settings *package*, whose `__init__.py` is empty; it only ever worked because of the
celery side effect above.

**`DJANGO_ENV_FILE` is a test affordance, not a feature.** It exists so a test can observe
a genuinely bare environment on a machine where `.env` exists. Deploys leave it unset.

**`CACHES` keeps its explicit dict.** `env.cache_url()` picks its own `BACKEND` and drops
`CLIENT_CLASS`, which would silently swap `django_redis` out. Only `LOCATION` is
env-driven. The reasoning is in a comment at the call site — please leave it there.

**CI uses individual environment variables, not a `.env` blob.** `$DOTENV_CONTENT`
echoed into `src/taskflow/.env` was an opaque secret that had to be hand-synced with the
settings (S-15). A regression test asserts `DOTENV_CONTENT` appears nowhere in CI.

### Assumptions made

- `env.list` does not strip whitespace — verified: `"a.com, b.com"` → `['a.com', ' b.com']`.
  Both `base.py` and `production.py` therefore strip explicitly, or the second host could
  never match a real `Host` header.
- nginx forwards `X-Forwarded-Proto` (confirmed in `nginx/conf.d/default.conf`), so
  `SECURE_PROXY_SSL_HEADER` is safe to set. Without it, `SECURE_SSL_REDIRECT` would see
  proxied requests as plain HTTP and redirect in a loop.
- HSTS defaults to one year, opt-out via env. Browsers cache it for its full duration and
  it cannot be revoked early, hence the env escape hatch.
- The dev-only `SECRET_KEY` default in `base.py` was **freshly generated** and is unrelated
  to the previously committed literal.

### Things the next session should NOT change

1. `production.py`'s no-default reads. Adding a fallback defeats the whole issue.
2. The `INSTALLED_APPS`-based guards in `urls.py` — do not convert them to `DEBUG` checks.
3. The absent `setdefault` in `celery.py` — do not restore it.
4. `allow_failure: true` on `lint_style` — dropping it means committing the reformat.
5. `companies/tasks.py`, `companies/tests.py`, `companies/views.py` — the developer's work.
6. `fail_under = 65` — raise it as part of C-4 with a fresh measurement, not by guess.
7. Branch coverage stays off; the floor was calibrated on statement coverage.

### Pitfalls and environment-specific issues

- **`poetry lock` fails *successfully* on this host.** A dbus/kwallet
  `Introspect error … NoReply` makes it print `Resolving dependencies...`, exit 0, and
  never write the file. Always run:
  ```bash
  PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring poetry lock --no-update
  ```
  and verify with `poetry check --lock` plus the file's mtime. An unwritten lock is easy
  to miss.
- **`pip install` in the container needs `-u root`.** Runtime user is `appuser`; without
  it you get `OSError: [Errno 13] … /app/.venv/…`. Do not pass `-q` — it hides the error.
- **Container cleanup of root-owned files** also needs `docker exec -u root`.
- **Container cwd must be `/app/src`.** Use `-w /app/src` or Python cannot import
  `taskflow`.
- **Coverage cannot write to `/app/src`.** Use `COVERAGE_FILE=/tmp/.coverage` (§3).
- **`check --deploy` exits 0 even with warnings** unless `--fail-level WARNING` is passed.
  Verified. Without the flag the gate is decorative.
- **Only `./src` and `./scripts` are bind-mounted.** Repo-root files need `docker cp`.
- **Full suite ≈ 29 minutes.**
- **Two pre-existing P-2 LocMem test artifacts** exist in the companies suite. They are
  not regressions. The full suite is currently `OK`, so they are not firing.

---

## 7. Resume Prompt

> Resume from this handoff.
>
> You are continuing audit remediation on `taskflow-api` (Django 5.2 + DRF, `src/`
> layout, Poetry, Docker Compose), branch `develop`. Read `docs/HANDOFF.md` first, then
> `docs/audit/TODO.md`. **Do not perform another audit** — a complete one is already
> documented. Do not re-review unrelated code.
>
> **Status:** C-1, C-2, C-3, and M-3 are implemented and verified. The full suite is
> **161 tests, `OK`**. C-3 drove `manage.py check --deploy` from 26 issues to **zero**;
> production settings now import and serve, and refuse to boot without
> `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DATABASE_URL`. **Nothing is
> committed.**
>
> **Your first task is not to write code.** C-3's implementation *and* its documentation
> are both complete — `TODO.md` marks it DONE and `AUDIT_REPORT.md` §12.5 carries the
> implementation note. **Do not redo that bookkeeping.** What is missing is the one step
> requiring a human: present a concise C-3 summary — modified files, why the fix is
> correct, what was verified, and the three things that did *not* come with it (CSP, the
> operational rotation of the real deployed secret, and coverage re-measurement) — then
> **wait for my approval before starting C-4.**
>
> **Constraints:**
> - One issue at a time. Never batch. Smallest safe fix. Keep the existing architecture.
> - Never modify unrelated code. Always leave the project working.
> - **Do not touch `src/taskflow/companies/tasks.py`, `companies/tests.py`, or
>   `companies/views.py`** — they hold the developer's own uncommitted in-progress work.
>   The missing `@` on `shared_task` in there is tracked as Q-1; do not drive-by fix it.
> - **Never print, copy, echo, or commit the old committed `SECRET_KEY` literal.**
>   Reference it by name only. It is in git history already; do not amplify it.
> - Do not add defaults to `production.py`'s required env reads, do not restore the
>   `setdefault` in `celery.py`, and do not convert the `apps.is_installed()` guards in
>   `urls.py` into `DEBUG` checks. §6 explains why for each.
> - Do not commit unless I ask. If I do ask, stage **selectively** — `git add .` would
>   capture the developer's `companies/*` work and the untracked `docs/`.
>
> **Validation requirements:** every fix needs a regression test that **fails before and
> passes after** — demonstrate both. Run targeted tests first, then the full suite
> (`docker exec -w /app/src taskflow_web /app/.venv/bin/python manage.py test taskflow
> --settings=taskflow.settings.development`, ~29 min). The blocking lint tier
> (`flake8 src --select=E9,F63,F7,F82`) must stay at 0 findings.
>
> **Before claiming anything is verified, check:** the full suite is `OK`;
> `makemigrations --check --dry-run` reports no changes; `check --deploy` still reports
> zero issues under production settings; and **coverage has actually been re-measured** —
> the last run produced no number because coverage could not write to `/app/src`, so use
> `COVERAGE_FILE=/tmp/.coverage`. The last known figure is 68% with `fail_under = 65`. Do
> not report a coverage number you have not measured.
>
> **Environment gotchas that will bite you:** container cwd must be `/app/src`;
> `pip install` in-container needs `-u root`; `poetry lock` silently no-ops on this host
> unless you set `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`; only `./src` and
> `./scripts` are bind-mounted, so repo-root config files need `docker cp` before the
> config tests will run instead of skip; `check --deploy` needs `--fail-level WARNING` to
> have any teeth. Also note `base.py` reads `src/taskflow/.env`, which can mask a
> "fails when unset" test — use `DJANGO_ENV_FILE` pointed at a non-existent path.
>
> **After C-3's bookkeeping is approved, the next issue is C-4** (the `boards` app is
> wholly non-functional). `boards/tests.py` is 0 lines, so budget for writing a suite
> before fixing anything, and fold in Q-13 and Q-15 per TODO.md's dependency note. A
> step-by-step plan is in §5 of the handoff.
