# Usage Analytics — Phase 0 (initial source investigation)

Status: source-confirmed findings; runtime validation pending. No production plugin yet.

## Scope
Cage-local Code usage only. Separate input, output, cache read and cache creation; request list and cache ratio. Subscription quotas remain native. No proxy, credentials, transcript bodies, external telemetry or core changes.

## Source evidence
Cage revision 2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703:
- [token_usage.py](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/token_usage.py#L51-L117): default and managed config roots, main/subagent JSONL, assistant usage extraction and hashed identity.
- [daily_totals](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/token_usage.py#L129-L150): groups by local date, model, source and client.
- [collect](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/token_usage.py#L153-L200): private SQLite database, requests schema, revision triggers, cutoff and additive client migration.
- [upsert](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/token_usage.py#L249-L269): deduplication by hashed identity, earliest timestamp, per-counter maxima and conflicting source/client handling.
- [main](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/token_usage.py#L289-L301): Linux database ~/.local/share/cage/token-usage/counters.sqlite3.
- [UI metrics](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/ui/src/token-usage.mjs): upstream already defines individual metric selectors; plugin differentiates by simultaneous presentation and request-level analytics.
- [Account guide](https://github.com/Lee-xeo/Claude-Cage/blob/main/docs/guide/accounts.md): coverage, native refresh, privacy, reset and pause semantics.
- [Plugin API](https://github.com/Lee-xeo/Claude-Cage/blob/main/docs/plugins.md): guest environment, stdio MCP, app-only tools, view bridge, no localStorage, poll rather than rely on server notifications.

## Data flow and recommendation
Native JSONL -> native collector -> requests SQLite -> native daily summary.
Proposed plugin: requests SQLite (read-only) -> bounded parameterized queries -> app-only MCP tools -> extension view.

Columns: id (hashed), stamp, model, source, input, output, read, write; newer schemas add client and client_conflict. No project/session IDs in this table. Source is NOT billing account. No HTTP status or latency. Request rows are deduplicated usage records, not a complete HTTP audit log.

Prefer documented public API if discovered and sufficient; none established yet. Direct SQLite read is a private-schema dependency, but avoids duplicated collection, respects native reset/pause and retains native historical coverage. Independent JSONL collector is a fallback requiring separate privacy/reset design and explicit review; do not silently enable it.

## PoC acceptance criteria
- Guest can open existing database with SQLite URI mode=ro and PRAGMA query_only=ON; never create, migrate or write native database. Do not use immutable=1 for live database.
- Validate schema via PRAGMA table_info; support missing client as unknown; fail clearly on unsupported schema, missing DB or permission denial. Use bounded timeout and paginated queries; do not expose raw filesystem errors.
- Return four totals, request count, cache hit rate = read/(input+read+write), null for zero denominator; group by local day/model and provide bounded request rows.
- Use a single read transaction per response; avoid long-lived locks. Validate date ranges, limits and filter parameters.
- Test synthetic DB with duplicate handling already reflected in native rows, zero denominators, legacy schema, missing DB, reset, concurrent writer, timezones and no writes. Compare totals against native UI on a real Cage instance.
- Do not read account credential directories, raw transcripts or host files; no network. Respect native data availability; missing data is not zero.
- Follow marketplace manifest, localization, packaging and submission requirements; verify against actual fork README/build scripts before implementation.

## Remaining Phase 0 work
Inspect Go bridge and exact marketplace example/manifest; review CC-Switch pricing and log semantics; verify guest UID and database read access in real Cage, including remote environments and native pause/reset behavior. Pricing, project/session attribution and billing-account attribution are deferred; do not infer them from native request rows.
