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
