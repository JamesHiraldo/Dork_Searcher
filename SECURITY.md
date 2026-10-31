# Security policy

## Supported versions

Security fixes are applied to the current 4.x release line.

## Reporting a vulnerability

Please use the repository's private GitHub Security Advisory flow. Do not include
API keys, live authentication material, private bug bounty evidence, or sensitive
target URLs in a public issue.

## Operational boundaries

Discovery queries third-party data sources. Wayback-Recon check/watch samples DNS and HTTP
availability only when selected; it never performs ARP injection. The separate HTTP
metadata probe is active and requires explicit scope acknowledgement. Private and
local addresses, credential-bearing URLs, and out-of-scope redirects are blocked by
default. These controls supplement—not replace—the authorization and rate limits of
the applicable bug bounty program.

Result artifacts can contain sensitive reconnaissance data and are ignored by Git.
Store, transmit, and dispose of them according to the target program's rules.
