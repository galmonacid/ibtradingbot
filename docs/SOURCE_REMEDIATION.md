# Public-source remediation after Step 3

Date: 2026-10-04. Stage: **bounded identity/source remediation implemented and audited; full remediation incomplete; Step 4 not ready**.

The user's request to continue the next steps authorizes this bounded public-source follow-up to the completed Step 3 audit. It does not change historical results, date windows, source/feature admission rules or risk limits. See [the next research cycle](NEXT_RESEARCH_CYCLE.md) and [roadmap](ROADMAP.md).

The user has requested completion of the remaining R3 work. The [current completion record](R3_COMPLETION_PROGRESS.md) documents the full 793-identity universe audit, public-source discovery, pending acquisition needs and the unaltered forward-evidence gates. Offline continuation is authorized; R3 is not complete and no new model has been fitted.

## Implementation and observations

[`src/data/r3_identity.py`](../src/data/r3_identity.py) extracts SEC inline cover observations by exact context, retaining issuer, accession, share-class title, trading symbol, visible exchange text, acceptance/availability timestamps and source hash. It does not infer security intervals, normalize vendor symbols, classify every security as common equity, or modify the canonical master.

[`src/cli/r3_identity_audit.py`](../src/cli/r3_identity_audit.py) verifies a local manifest's document and acceptance-source hashes, locates the exact accession in retained SEC submissions metadata, and writes an immutable audit report. The manifest sets the existing 24-hour processing-latency assumption. Fiscal context dates do not backdate publication. The report binds the input manifest, implementation-file hashes, Git revision/committed tree and Python version. The supplementary findings artifact records dependency versions and canonical/source hashes.

Three filings yielded **17 complete cover observations**: Meta 1, Berkshire 12 and Alphabet 4. Five describe the relevant common/capital share classes. The other 12 describe debt or preferred depositary securities and are not admitted to the stock universe. Alphabet also has **22 incomplete contexts**, which remain explicit; the parser never borrows another context's symbol/exchange to complete one.

The implementation handles visible nested formatting and inline exclusions, rejects unsupported continuations/transforms and conflicting issuer evidence, and rejects individual incomplete/conflicting contexts. For `ixt-sec:exchnameen`, it retains visible exchange text, not a normalized exchange code. Context entities/dimensions are not independently validated; this extractor is a source-audit primitive, not a qualifying security master or trading input.

## What the sources establish

| Case | New evidence | Remaining work |
| --- | --- | --- |
| Meta | The May 31, 2022 SEC filing announces Class A's FB-to-META change effective June 9. Nasdaq's June 3 notice independently identifies the same class and effective date. | Local ID `IC-US-cb012790a1db93bf` has the matching FB/META boundary. Separate ID `IC-US-63aa8d99585c7f98` contains META before that boundary. Reconcile source lineage, prices, membership and actions before any proposed merge/exclusion. Neither source establishes a 1996 inception. |
| Berkshire | The retained 2021 filing distinguishes Class A / BRK.A from Class B / BRK.B and debt contexts. | Local BRK-B and BRK.B IDs need vendor-specific alias evidence and price/action reconciliation. Punctuation replacement alone is not a causal merge rule. |
| Alphabet | The retained 2026 filing separately identifies Class A / GOOGL and Class C / GOOG, as well as preferred depositary securities. | This late observation cannot establish earlier inception, historical availability or predecessor/successor continuity. Preserve the two common/capital share classes separately. |

Primary sources: [Meta SEC event filing](https://www.sec.gov/Archives/edgar/data/1326801/000132680122000070/fb-20220531.htm), [Nasdaq change notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-125), [Berkshire cover](https://www.sec.gov/Archives/edgar/data/1067983/000156459021009611/brka-10k_20201231.htm), and [Alphabet cover](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000071/goog-20260630.htm). Nasdaq's notice supplies a publication date, not an observed intraday publication timestamp. No earlier intraday availability was invented.

## Follow-up: local price, membership and action lineage

The subsequent continuation request led to a read-only inventory of the six ambiguous IDs. All four canonical files were verified against the existing canonical manifest; provider manifest `343d182a2d7d9388c2a5936be723d33f0ca500aa0bd333b0047481067f68d3f1` and the inspected successful raw responses were also verified.

| Local identity | Canonical bars | Observed coverage | Finding |
| --- | ---: | --- | --- |
| Meta shadow `IC-US-63aa8d99585c7f98` | 0 | None | No membership or action rows; no duplicate economic rows to merge |
| Meta FB/META `IC-US-cb012790a1db93bf` | 1,070 | 2022-06-09–2026-09-15 | FB provider request failed; META succeeded. Pre-change history is absent, not repaired by merging the shadow ID |
| Berkshire BRK-B `IC-US-066d2b46d7ae75f1` | 3,702 | 2009-01-12–2023-09-26 | Source request succeeded for the retained coverage |
| Berkshire BRK.B `IC-US-c17dca0bffde127c` | 0 | None | Provider request failed; no membership or action rows in the retained canonical slice |
| Alphabet GOOGL `IC-US-1b565bc34cc7ad4d` | 5,421 | 2005-02-28–2026-09-15 | Distinct class history |
| Alphabet GOOG `IC-US-f260b973e756018f` | 3,136 | 2014-03-27–2026-09-15 | Distinct class history |

GOOG and GOOGL overlap on 3,136 sessions, with zero rows identical across the six compared price/volume fields. This supports retaining the source distinction; numerical difference alone is not proof of legal identity. The two other pairs have no overlapping price rows. There is no return calculation, model selection or automatic merge in this audit.

The provider manifest records 832 successful and 388 failed requests. Request counts are not unique securities or a measured survivorship-bias estimate. The retained native membership-change file includes FB's 2013 addition and Berkshire punctuation switches; the canonical slice omits the corresponding failed-provider histories. A source repair must address acquisition/coverage and account for exclusions, rather than presenting symbol normalization as recovered history.

Immutable follow-up package: `data/local/r3_identity_20261004_lineage_v2`, identity `fd11ec7676e61c4dace40559cc1e2de8212a3fb31432cd7f48c9fd35ffd41106`; report SHA-256 `9d9ab084c5df3ec422e7f76e48e5172d9b0dc1b09ffc93984238276ea73dd041`. Its retained source script and fixed-timestamp repeat reproduce byte-for-byte. The initial exploratory v1 remains untouched. To reproduce into a new directory:

```bash
PYTHONPATH=. python data/local/r3_identity_20261004_lineage_v2/reproduce.py \
  --output-directory data/local/r3_identity_lineage_reproduction \
  --run-timestamp 2026-10-04T16:32:53+00:00
```

Next acquisition work should resolve historical FB and BRK.B requests against documented provider identifiers and date ranges, bind new raw responses to a new manifest, and reconcile prices/actions before rebuilding any canonical dataset. Existing provider credentials or paid access are not assumed. Public filings establish class/transition evidence; they do not fill missing trading histories.

## Historical industry-data route

The current [SEC Financial Statement Data Sets documentation](https://www.sec.gov/files/financial-statement-data-sets.pdf) identifies accession-level SIC codes as assigned at filing time. This is a candidate historical industry source, rather than present-day company metadata. No classification rows were ingested in this pass; it is not a completed sector feature.

Two limitations are material. SIC is not interchangeable with the proposed sector taxonomy. Also, the [SEC dataset page](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets) explains quarterly publication and December 2024 reprocessing. A downloaded bulk archive's values cannot automatically be treated as a contemporaneously available vintage at filing acceptance. Validate the original filing/header values and distinguish filing availability from bulk publication before admission. This source still does not supply the missing pre-2009 fundamental history.

The current documents were archived separately from the older `fsds.pdf` retrieved during discovery. Raw source bytes, access timestamps, URLs and hashes remain ignored/local. Public no-auth access incurred no observed charge; it does not establish complete recurring operating costs or unrestricted redistribution rights. Existing source-permission limitations remain. No key, account, paid subscription or broker access was used.

## Evidence and reproduction

Immutable package: `data/local/r3_identity_20261004_audit_v1`.

- Package identity: `47409e643d6766e2f6ec156c4bf995a08bdbf72646fb97da033e550fd3d4c0c7`.
- Cover audit and byte-identical repeat: `a1153131fff0fcb36a884b9c35a106f46e4d2ec4d2ec3ec0bcb7cd1ec9215be3`.
- Input manifest: `2f7ad5486c4676833a72c6cc95b14d5ba6a3fc4669b30e7e7eaf0ce5f80bbd86`.
- Remediation findings: `4a45fde48c849bf6e4ca3fc4bff816081ab9281f314170905825008d4e1fd9de`.
- Preserved-evidence verification: `48f0d40ca0764d7dfe39149598b0253752a3d51c892a0125e984bba30c420182`.

New raw archives are `data/local/r3_identity_20261004_raw_v2` and `data/local/r3_sector_20261004_raw_v1`. The failed sandbox-DNS attempts remain recorded in `data/local/r3_identity_20261004_raw_v1`; subsequent approved public downloads succeeded. The pre-existing raw filings/acceptance records and original/corrected R3 reports/models were read and hash-verified only.

With the recorded local sources available, run from the repository root using Python 3.12+:

```bash
python -m src.cli.r3_identity_audit \
  --manifest data/local/r3_identity_20261004_audit_v1/input_manifest.json \
  --output data/local/r3_identity_reproduction/cover_audit.json \
  --run-timestamp 2026-10-04T16:32:53+00:00
```

The output must be new. Reproducing the full report hash requires the recorded implementation tree; later documentation/code edits change provenance without rewriting old reports. The recorded repeat was run against identical inputs and tree before this documentation update.

## Verification and remaining exit conditions

Seventeen focused tests passed, covering class separation, missing/conflicting contexts, publication-time filtering/prefix invariance, fiscal-date non-backdating, inline text handling, source tampering, future acceptance rejection and immutable output. The full suite recorded 455 passes and one optional-calendar dependency skip; after restoring the declared `exchange-calendars` dependency, all four calendar/evidence tests passed separately. The declared scikit-learn dependency was also restored before the full suite. These were verification-environment repairs, not project dependency or research-protocol changes.

Ruff passed. Full strict mypy passed for 110 source files after dependency repair and explicit interpreter selection. The isolated package build produced an sdist and wheel; the initial no-isolation attempt failed because Hatchling was missing. The existing Python launcher resolves to the bundled Python 3.12.14 runtime, so dependency installations affected that active runtime rather than a self-contained temporary environment. No historical experiment was rerun with the repaired environment. The full suite emitted a joblib CPU-detection fallback warning; it did not fail tests. Local links, whitespace, ignored-artifact and preservation checks passed.

Full remediation still needs historical issuer/security/class intervals and corporate-action reconciliation, an admitted industry taxonomy with dated coverage, macro-vintage access if that feature family is retained, and an evidenced cost/permission budget. No canonical data, features, labels, portfolio rule, model or historical performance result changed. The existing nine folds still lack enriched pre-2009 history.

The user explicitly approved the later-period direction on 2026-10-07. The separate [later-period design](LATER_PERIOD_DESIGN.md) retains initial 8/2/1 windows and records six calendar-complete folds. This supersedes the pending design question; no further permission is needed for that scoped work. Full-universe feature coverage and the remaining source gates are still required before registering model trials.
