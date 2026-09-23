# Nova Extraction Record

This standalone repository was extracted from source
`f3a4d358ed00833925db0c7bd740aee4a91e5f08` with the installed
`git-filter-repo` build `ed61b4050b71` using 40 selectors. The immutable
selector manifest is `docs/extraction/nova-filter-paths.v1.txt`.

Extraction command:

```sh
git clone --no-local /repos/salesos nova-canonical-v2
cd nova-canonical-v2
git checkout --detach f3a4d358ed00833925db0c7bd740aee4a91e5f08
git filter-repo --paths-from-file /absolute/path/to/nova-filter-paths.v1.txt --force
```

The resulting filtered commit is
`f320346b228ef1223f221eb8aebd6459133d9a0d`, with tree
`2f89d47c5b28c843cfc1a53cf9dd9de04b64f9ec`. The manifest is copied into
this repository only after filtering, so it cannot affect that commit.

The prior filtered reference `c50b058` and standalone candidate
`e461f5f4cb081324b0a9632251f27b11f2853f6a` are historical and
non-recoverable: the original selector list, bundle, and Git objects no
longer exist. The operator approved this documented replacement baseline.

Files added after filtering are standalone configuration, the `apps/nova`
frontend, local DB/auth/CRM adapters, CI/deploy assets, current contract
tests, and this documentation. `presentation.css` and the old pilot UI are
not runtime dependencies; the retained filtered copies are historical only.

The extraction is intentionally independent: Nova owns its six prospecting
tables on the shared platform Postgres service during transition, receives
platform JWTs, and reaches CRM only through a versioned HTTP API.

## Gate B verification — 2026-09-23

The current standalone repository was verified from a clean working tree
(generated virtualenv, npm dependencies and build output were not committed):

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest` | 4 passed |
| `python3 scripts/audit-coupling.py` | passed |
| `npm --prefix apps/nova run test:static` | passed |
| `npm --prefix apps/nova run build` | passed |
| `git diff --check` | passed |
| `git grep` credential-pattern scan | no matches |

The historical `c50b058` comparison cannot be recreated because that object
and its selector manifest are unavailable. The approved replacement baseline,
source SHA, filtered SHA, selector manifest and final standalone SHA above are
the reproducible Gate B record. Gate B does not authorize any database
migration, production cutover or legacy-code deletion.
