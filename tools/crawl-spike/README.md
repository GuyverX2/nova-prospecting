# Crawl spike harness (ARCH-W1-001)

Three-way comparison for Nova/prospecting fetch:

| Arm | Provider | Default in spike |
|-----|----------|------------------|
| A | SalesOS `analyzer.fetch_public_html` + `agentic_extract` | **KEEP** baseline |
| B | Crawl4AI | Documented + optional live import |
| C | Crawlee | Documented + optional live import |

## Run (offline — CI default)

From repo root with API venv active:

```bash
source .venv/bin/activate
pip install -r tools/crawl-spike/requirements.txt   # PyYAML; live arms are optional
PYTHONPATH=tools/crawl-spike:services/api python -m crawl_spike.harness
```

Cases come from `docs/architecture-program/wave-0-3/fixtures/crawl-cases.yaml`,
the same fixture the decision record cites.

## Optional live libraries

```bash
python -m venv /tmp/crawl-spike-venv
source /tmp/crawl-spike-venv/bin/activate
pip install -r tools/crawl-spike/requirements.txt
CRAWL_SPIKE_LIVE=1 PYTHONPATH=tools/crawl-spike:services/api python -m crawl_spike.harness
```

**Do not** mass-crawl production or blocked sites. Fixtures under `fixtures/pages/` only.

## Outputs

- Fixture matrix: `fixtures/crawl-cases.yaml`
- Spike notes: `docs/architecture-program/wave-0-3/SPIKE_CRAWL.md`
- Decisions: `KEEP` | `HARVEST` | `INTEGRATE` | `REJECT` per competitor

## Rollback

Delete `tools/crawl-spike/` and spike tests. Zero production impact (`PROSPECTING_FETCH_ENABLED` unchanged).
