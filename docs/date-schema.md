# Date-first Legacy card data

This migration is limited to Legacy. `data/<CARD_ID>.json` keeps every existing filename. The keys are ascending `YYYY-MM-DD` Korean calendar dates. The first dated record is the entire available historical gameplay baseline; later records contain only changed fields. Field names remain `cost`, `races`, `spellSchool`, `durability`, and `armor`.

## Operations and confidence

- A missing field in a later record means inherit it.
- Zero, false, null, an empty string, and an empty array remain literal values. They are never interpreted as missing or deletion.
- `"__remove": ["attack", "health"]` deletes those fields. It cannot overlap fields written by the same record. Type changes explicitly remove old type-specific fields.
- Arrays and objects replace the complete prior field value; there is no deep merge or text concatenation. Recursive JSON equality distinguishes booleans from numbers, including nested effect objects.
- Card ID and DBF identity/presence cannot change after the first record.
- Empty legacy `race`, `races` and `spellSchool` placeholders are omitted. Losing one of these attributes produces an explicit removal. Genuine non-minion races are preserved when source-backed.
- Display text uses `<br></br>`. Native and archived raw text stays byte-for-byte equivalent in the sidecar source.

A date key is NOT evidence that a date is verified. Of the 609 original source files, 607 already had an adopted release date: **74 verified and 533 estimated**. This migration preserves all 533 existing estimates without creating or promoting dates. `metadata/<ID>.json.release` stores the confidence independently from card stats.

Two source files had no adopted release date. `data/skele21.json` and `data/ds1_whelptoken.json` are empty maps rather than invented release events. Their full baseline and original dated events are preserved in `metadata/<ID>.json.undated`. The existing current catalogue rows remain available. In particular, the standalone `ds1_whelptoken` source still has no proven DBF mapping. Its existing catalogue row DBF 54 is preserved separately, never asserted to be the native source's identity.

`date_schema.fold` is a mathematical fold of dated records and returns `None` before the first date. `date_schema.resolve` is the default compatibility resolver: verified releases gate existence; estimated releases remain visible before their estimate, as in the existing API; pending sources use the explicitly undated baseline and known deltas. `strict=True` is an opt-in verification helper only. It refuses uncertain releases AND incomplete baseline evidence. Even the 74 verified release dates do not prove every baseline field. Every existing baseline is therefore honestly marked `partially-verified`; strict mode does not silently validate one.

## What is historically dated

A canonical state includes ID/DBF identity, name, actual type, class/classes, rarity, collectible status, actual type-specific stats, text, known race/school/mechanic deltas, and dated hero-power links where verified. It does not claim installed client metadata was present on release day.

The sidecar contains:

- `originalSource`: the complete pre-migration JSON, including raw native tags/text, unresolved observations, provenance, parent/child/choice/transform relationships and current metadata. It is immutable migration evidence, not a second mutable timeline.
- `currentCatalog`: the approved current import metadata, ID/DBF mapping and artwork/relationship links. The canonical timeline overrides its gameplay fields during builds.
- `release`, `baselineStatus`, and explicit `undated` records when needed.
- `sourceCommit`: the exact Legacy source revision, `7704a5e6217323415c7f7d9d0f9d17f444448d2a` for this migration.

Unclassified fields cause an explicit projection error until they are classified with supporting evidence. Additional real effect fields can be preserved through the explicit `gameplay_fields` argument; unknown fields are never silently discarded or automatically backdated. Known installed and Battlegrounds exporter metadata remains in sidecars.

Current set labels, portraits, flavor text, artist, watermark, relationship lists and installed `nativeTags` are retained separately because their historical effective dates have not all been established. No original field or relationship is silently discarded. Historical set changes or relationship changes require their own verified dates before moving them into a timeline.

## Type projection and the real type-change correction

MINION keeps attack/health, SPELL has no fabricated combat stats, WEAPON uses attack/durability without a health mirror, LOCATION uses durability, and HERO_POWER does not inherit minion/weapon stats. Generic fold tests also cover ENCHANTMENT effect objects without forced stats. A real zero is retained whenever its field applies.

HERO is role-aware. Playable replacement cards use armor. A basic/skin/transformed hero entity may have real health; it is not automatically removed. Legacy's `EX1_323h` transformed hero keeps its original health 15, with role documented in metadata.

`EX1_323` had a pre-existing historical defect: current HERO type, armor and hero-power link were backdated to the 2013 baseline, and minion attack/race had been lost. The migration separately corrects this verified transition:

- Before 20.0: MINION, attack 3, health 15, Demon.
- 2021-03-26 KST: HERO, armor 5, hero power DBF 1178; explicitly remove attack/health/race/races.
- Existing text/cost changes remain on their original verified dates.

Evidence: archived CardDefs before and after 20.0, and the already adopted Korean date in `tools/archived-build-dates.json`. Exact extracted evidence and source URLs are in `tools/date-schema-type-evidence.json`. The original erroneous fields remain visible in immutable `originalSource` for auditing; this correction is not hidden as a byte-equivalent migration.

## Generated transports: API-only, dual output

The plugin change is postponed. No plugin source, installed configuration, database or live import is changed by this migration. All six generated bundles are siblings at the repository root, so their existing `art/<ID>` paths resolve to the same original artwork directory.

**Unchanged-consumer entry points:**

- `cards.json`: schema 1 legacy import projection. All 609 rows and every current imported field match the pinned pre-migration catalogue exactly in this release.
- `render.json`: schema 1 current projection plus ordinary reverse history.
- `history.json`: schema 1 object keyed by DBF ID, retaining the existing `id` + reverse `history` contract. No `__remove`, authoritative snapshot or `historySchema: 2` is sent to old clients.

These are regenerated from canonical data on every build, not frozen copies. The explicit `legacy_projection.py` boundary supplies the old mandatory cost/numeric placeholders, empty race/school sentinels and weapon-health encoding. Those values NEVER flow back into canonical date maps. Old inclusive-from/exclusive-before intervals and before-release fallback visibility are retained; no new existence or strict gating is enabled. Jaraxxus's verified historical type/attack/armor/race correction is representable and remains included.

**Precise opt-in entry points:**

- `cards-date.json`: current type-specific gameplay plus separately retained current metadata.
- `render-date.json`: schema 1 array with `historySchema: 2`, explicit removal histories and confidence/current-only metadata.
- `history-date.json`: schema 1 object, `historySchema: 2`, complete canonical current gameplay plus reverse intervals for all 609 cards, even unchanged ones.

Precise consumers explicitly map `cards-date.json` to `render-date.json` and `history-date.json`. Existing configured `cards.json` sources continue using their unchanged siblings. Do not configure the old plugin to use the precise endpoints: it cannot express absence, arbitrary removal or complete authoritative states. Root URL placement avoids new artwork-base exceptions or `../art` paths. Tests check all 609 asset paths against the pinned repository tree and all six URL bases.

`tools/legacy-compatibility-losses.json` documents the unavoidable old-consumer limitations: absent numbers become zero, native current tags can still leak into historical rendering, some array/effect fields are ignored by the old whitelist, DB presence is not preserved, and existing unsupported frame types remain unsupported. This is not claimed as precise historical rendering. The original root README claim that 7.12.11+ stopped requesting history was wrong: inspected 7.12.14 still requests it, so it remains.

At this revision, root history is 213391 bytes and precise history is 492774 bytes, both below the existing 524288-byte limit. No additional request is introduced for existing clients. The separately prepared plugin work remains postponed and is not required to continue the old root endpoints.

## Reviewed weapon source encoding

Eleven old source records have true weapon durability in `health`/native tag45 but an exporter-added `durability: 0`: DS1_188, EX1_133, EX1_247, EX1_323w, EX1_366, EX1_383t, EX1_398t, EX1_409t, EX1_411, EX1_536 and EX1_567. The migration explicitly decodes only these reviewed IDs into canonical durability. It is NOT a runtime `durability || health` fallback; genuine canonical zero remains zero.

`tools/date-schema-weapon-encoding-evidence.json` preserves the exact original values/tags, archived 2015/2021 client cross-checks, and the existing 334-build stat-audit evidence. No durability patch dates are invented, and their release/baseline confidence is not promoted. Root compatibility deliberately retains the former health-backed representation and visual behavior; precise output uses actual durability with no health mirror. Both the original JSON and native tags remain verbatim in sidecars.

## Editing and rebuilding

Edit canonical date records and the corresponding source/evidence metadata. Do not edit generated gameplay values in `cards.json`, or mutate the immutable original source to alter a date. Sidecar `currentCatalog` is the source for current-only asset metadata.

Client-only misprints and display glitches that did not change actual card behavior are excluded entirely from card history. Remove both the spurious dated text and the subsequent correction-only reversal from `data/<ID>.json` and any erroneous client-text observations from `metadata/<ID>.json`; do not retain a separate card-level bug entry. Preserve real balance patches and their dates.

Run:

1. `python3 tools/migrate-date-schema.py` (idempotent; only converts old wrappers once).
2. `python3 tools/normalize-card-linebreaks.py` (dated display text only).
3. `python3 tools/build-api.py` (regenerates both root compatibility and precise `-date` bundles).
4. `python3 tools/test-chronology.py` (all existing historical balance regressions retained).
5. `python3 tools/test-date-schema.py` (every precise source and every original date boundary, day before/on/after).
6. `python3 tools/test-legacy-compatibility.py` (old-consumer projection, all IDs, historical behavior and artwork paths).

The publication workflow uses that sequence and `actions/checkout` with `fetch-depth: 0`. Preservation tests need the pinned pre-migration source commit; a shallow checkout lacking it fails with an explicit instruction to fetch full history or that exact commit. Checks are never silently skipped. A fresh depth-one repository was exercised separately for failure detection and explicit pinned-fetch recovery.

The first-migration current catalogue equivalence assertion intentionally catches drift; future approved gameplay changes require reviewing/updating the expected difference policy, not freezing the builder.

The publication workflow uses that sequence. Superseded wrapper mutators now fail explicitly on a migrated repository rather than silently recreating `card/patches` or claiming an import succeeded. Their manifests and audit evidence are preserved. Read-only effect scanning uses a compatibility view of the date maps. Future balance imports should be implemented against the date-map operations and independent evidence, not re-enable wrapper writers.

`tools/date-schema-validation.json` records the all-card comparison and intentional current projection changes. The before/after snapshot oracle independently replays original patches, except for the documented type-specific placeholder removal and Jaraxxus correction. Tests preserve original JSON structure/value equality, all metadata/relationships, IDs/DBFs, current assets, unknown evidence, confidence, zero/empty/removal/type changes, no redundant deltas, current output and reverse transport reconstruction. Real browser/WordPress rendering and deployment checks remain separate from the data migration tests.

## Unchanged plugin validation

`tools/test-legacy-plugin.php` loads unmodified plugin files supplied as its first argument and a local fixture as its second argument. It uses offline WordPress stubs only. Generate the fixture with `python3 tools/test-legacy-compatibility.py --fixture /tmp/legacy-compatibility-fixture.json`, then run the PHP test with the pinned unmodified HSdeck-plugin 78ce6fd sources. The local validation used the already available PHP 7.4 WASM runtime: 609 imports and 7,327 date cases passed (7,328 checks). No plugin files, network services or live database were modified.
