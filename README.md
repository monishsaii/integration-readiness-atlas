# Integration Readiness Atlas

A 100-app Composio integration research case study. The matrix compares developer access, API authentication, API breadth, MCP availability, and the first realistic route to a toolkit prototype.

## Run

Requires Python 3.9+ and outbound HTTPS to refresh documentation. No credentials or dependencies are required.

```sh
python3 research.py
python3 -m http.server 8765 --directory dist
```

Open http://localhost:8765. Use `python3 research.py --cached` to reproduce the committed snapshot without network access. You can also open `dist/index.html` directly.

## How the evidence is produced

1. An AI agent creates and freezes `apps.psv`, the 100 initial hypotheses in the assignment's category order. This is the baseline for comparison.
2. `research.py` fetches first-party documentation, records response status and redirect targets, and extracts candidate passages about authentication, API scope, access tiers and MCP. It writes `dist/evidence.json`. Keyword matches are review leads. Absence of a match may reflect rendering or wording, and an HTTP 200 only establishes reachability.
3. Targeted vendor searches supply alternate links and documented MCP entries in `sources.json`. Selected claims are checked against primary sources in `review.json`, including a rendered browser check of Otter's API documentation. The script compares normalized claims with the frozen baseline and applies the documented changes for the published matrix. It does not infer an access tier from a keyword alone.
4. The build emits the static case study, structured `dist/data.json` and a blind human audit worksheet. The worksheet excludes the cases used to tune the snapshot.

The current run uses a standard-library pipeline with an AI research and adjudication pass. It does not use the Composio SDK or issue authenticated calls to the target APIs. A future authenticated pass can cross-reference Composio's toolkit catalog for existing coverage, then smoke-test one read action per authorized test tenant. Toolkit presence does not establish direct vendor access.

## Independent audit

Open `dist/human-audit.csv` before inspecting the corresponding app rows. It selects one held-out app per category using the fixed seed 20261123 and excludes the targeted review cases. Open the vendor docs yourself and record the exact API/auth scope, cheapest credential path, MCP surface if documented, and supporting URLs. Mark unclear claims as unresolved and retain them in your reporting. After recording your findings, compare with `dist/data.json`. Report verified, contradicted and unresolved counts by field. Do not include this worksheet in an accuracy claim until the check has been performed.

The targeted sample measures the effect of reconciling specifically examined claims with their sources. It is purposive and the same evidence informed the corrections. The score cannot be generalized to the full roster. Production access, real credentials and endpoint behavior were not exercised.
