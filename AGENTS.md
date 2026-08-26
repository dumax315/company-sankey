# Agent guidelines

## SEC User-Agent

Any command that touches the SEC network (`--fetch-sec`, `discover-filings`)
requires a `--user-agent` identifying the requester, per SEC EDGAR fair-access
rules. Use:

```
--user-agent 'Theodore Halpern theomhalpern@gmail.com'
```

For example:

```bash
uv run stankey generate-series META --quarters 20 --from-quarter 2026Q2 \
  --fetch-sec --user-agent 'Theodore Halpern theomhalpern@gmail.com'
```

Alternatively export it once so the CLI picks it up automatically:

```bash
export SEC_USER_AGENT='Theodore Halpern theomhalpern@gmail.com'
```
