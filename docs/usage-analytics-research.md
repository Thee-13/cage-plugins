# Usage Analytics — Phase 0 research

Status: Phase 0 source investigation complete. A guest plugin and synthetic tests are included. Real Cage runtime validation is pending.

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

## Phase 0 source verification

Completed against the pinned Cage revision above. Live guest validation is tracked in the [installation and verification steps](../plugins/usage-analytics/README.md#在真实-cage-环境验证).

- [Workbench routes](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/server.go#L419-L420) expose the native workbench GET/POST endpoint. [The Go implementation](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/token_usage.go#L107-L257) serves the saved aggregate, gates refresh with the pause flag and runs the collector over SSH. The endpoint does not expose request rows. The plugin's documented view bridge only calls its own server; it does not provide a public request-level usage API.
- [Guest launcher](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/host_tools_guest.go#L377-L425) uses the same `s.sshTarget()` as the collector and runs under the ordinary environment session. [The launcher script](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/host_tools_guest.go#L146-L178) retains `HOME` and timezone-related variables in its sanitized environment. The implementation supports the Linux guest path. The native helper's Windows branch requires a separate runtime environment variable that this launcher does not forward.
- [View and tool routing](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/workbench/host_tools_views.go) resolves the owning plugin/view. [The MCP bridge](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/internal/hostbridge/external.go#L615-L657) checks page tool visibility. The extension uses `ui/initialize`, `tools/call`, theme and visibility events over the sandbox's documented message channel.
- The native collector creates its Linux database directory privately (0700) and uses a 0077 umask. The source predicts same-user read access. Check the actual UID, database visibility and timezone on both local and remote deployments. The native collector uses SQLite's default rollback journaling. The test suite also exercises an active WAL writer to check read-snapshot consistency.
- Native pause is stored in the controller profile and stops collection. The guest reader can still see retained rows. Native clear stores the cutoff and deletes old request rows in the collector's own transaction. A fresh dashboard read reflects the after-clear database when the original action completes successfully.
- [CC Switch's usage documentation](https://github.com/farion1231/cc-switch/blob/e6fd4accd257406bf9141baa402caaa78f975ba1/docs/user-manual/en/4-proxy/4.4-usage.md) uses date/model filters, separate counters, a trend chart, and paginated records. Its routing and CLI logs provide different coverage. Its pricing depends on configured prices and model matching and represents estimated API cost. The plugin adopts the overview-to-trend-to-log flow and the same Token-weighted cache ratio. It displays native usage records with client metadata and leaves cost, status, latency and billing attribution outside the dashboard.

## Marketplace submission requirements

The [fork marketplace README](../README.md), [build script](../scripts/build.py) and [PR template](../.github/PULL_REQUEST_TEMPLATE.md) define the submission format. Package source under `plugins/usage-analytics/` with a guest manifest, English defaults, only documented manifest fields, one to three known categories and all 15 marketplace translations. Register `Thee-13` in `authors.json`. The native database stays within the environment, so the guest's permission manifest is empty under the [official permission rule](https://github.com/Lee-xeo/Claude-Cage/blob/2d224b4bbf5affe85330ec7de4ce1ccfbd6a2703/docs/plugins.md#L115-L125). No runtime dependencies are downloaded.

Run `python3 scripts/build.py` and commit its archive and index with the source. `python3 scripts/build.py --check` is the official CI gate. The script emits deterministic archives and keeps released versions immutable. It generates the official market URLs, SHA-256 and size. The change uses the repository's MIT license. A marketplace submission also requires real Cage screenshots or a short recording in the PR description, outside the archive.
