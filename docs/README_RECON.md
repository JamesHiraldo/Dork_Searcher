# Wayback reconnaissance

`wayback-recon` uses the shared HTTPS CDX client. It retries transient failures,
honors `Retry-After`, paginates with resumption keys, validates that every archived
URL belongs to the requested scope, and reports truncation and errors explicitly.

```powershell
wayback-recon --targets example.com api.example.com `
  --max-urls 100000 --rate 0.5 `
  --output Result\recon.json --csv Result\recon.csv
```

Add `--include-subdomains` when the program scope authorizes child hosts.

The JSON report contains:

- retrieval status, page count, error, and truncation status;
- archived URL and unique endpoint counts;
- a deterministic endpoint sample;
- parameter occurrence and unique-value counts;
- token-like parameter classification and redaction;
- scoped, validated archived URLs.

Parameter values are decoded exactly once. Sensitive values are redacted in both
the URL list and parameter examples unless `--include-sensitive-values` is set.
