# Phase 3 V2 external-input register

Recorded before acquisition, 2026-09-22. These inputs support offline development
research; they do not establish an account-specific broker tariff or deployment eligibility.

## FX source and permitted use

Source: European Central Bank daily euro foreign-exchange reference rates,
[publication page](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html),
[historical CSV archive](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip).
The ECB's [copyright terms](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html)
permit free use with accurate reproduction, attribution and explicit disclosure of
modifications. Source attribution: **European Central Bank**. Modification: divide the
GBP-per-EUR series by USD-per-EUR to derive GBP per USD. No investment transaction
rate is implied; these informational reference rates are not executable broker quotes.

Acquire the original archive into ignored `data/local/phase3_v2/`, preserve its SHA-256,
and normalize 2021-06-21 through 2026-06-30 inclusive. The normalized schema is
`observed_at,available_at,gbp_per_usd`, bound by `fx_manifest.json` to source, licence,
retrieval time, original archive hash and normalized hash.

The daily observation is dated at 14:10 Europe/Berlin, following the ECB's described
concertation time. The documented normal publication is around 16:00 CET. Historical
archive rows lack actual release timestamps and revision vintages. We conservatively
assign **00:00 UTC on the next calendar day** as modeled availability, ensuring the
current day's fixing cannot fund an earlier US opening trade. This is a disclosed
publication-lag assumption, not verified point-in-time release evidence. Retain this
limitation in certification. The historical archive may include revisions; it supports
development currency modeling and does not by itself certify historical FX vintages.
No forward fill is created; the loader selects the most recent already-available fixing
subject to its explicit age bound. Target-calendar holidays can require an age allowance
above four calendar days (for example Easter); missing/stale rates must fail closed.

## Published broker cost evidence

Official pages checked 2026-09-22:

- [IBKR UK ISA overview](https://www.interactivebrokers.co.uk/en/accounts/isa-accounts.php):
  US commissions start at USD 0.005 per share; example FX conversion cost 0.03%; adult
  ISA minimum monthly activity fee £3; cash-only account. Model actual conversion fee
  separately from the strategy's conservative 5 bps per-side FX buffer.
- [US stock commission table](https://www.interactivebrokers.co.uk/en/pricing/commissions-stocks.php):
  fixed pricing USD 0.005/share, USD 1 minimum/order and 1% maximum; tiered USD 0.0035/share
  in the lowest volume bracket with USD 0.35 minimum, plus listed third-party charges.
  The fixed table also lists regulatory fees. The strategy's USD 0.35 floor alone is
  not a verified conservative complete tariff.
- [Required minimums](https://www.interactivebrokers.co.uk/en/accounts/required-minimums.php):
  adult ISA monthly minimum activity fee £3. Charging the full £3 in addition to trade
  commissions is an explicit conservative modeling assumption pending verification
  of the actual commission-offset treatment; it is not a claim about the billed amount.

Exact account/instrument fractional permissions and current tariff selection are not
verified by these public pages. Whole-share scenarios are the actionable conservative
research mode; fractional scenarios remain hypothetical until account eligibility is
verified. The official ISA help link currently redirects to a generic FAQ and therefore
has not established the current fractional-share restriction or currency sweep timing.
Do not infer permission or currency-conversion operation from unrelated general-account
fractional support. No account connection was used.

## Acquisition status

The first sandbox attempt on 2026-09-22 failed DNS resolution. On 2026-09-23 the
explicitly approved network retry downloaded the fixed public ECB archive successfully.
Source/licence registration above preceded both attempts; the official licence and
publication pages were rechecked on 2026-09-23. No account access or purchase occurred.

Ignored local artifacts in `data/local/phase3_v2/`:

- `fx_ecb_archive.zip`: original archive, SHA-256
  `c63a1996014663ba3188c7b2820646882b07276513c0b3851a69581add38cb77`.
- `fx.csv`: 1,288 normalized observations, 2021-06-21 through 2026-06-30; SHA-256
  `9d05289f35f8b15804bc44f3bb6773bbd523be3b32ca47a053b2ef0add982e8c`.
- `fx_manifest.json`: retrieval time `2026-09-23T07:52:42.560113+00:00`, both hashes,
  cross-rate transformation, source/licence, availability assumption, row count and
  explicit `vintage_certified: false` / development-only usage.

The extra June 21–23 observations warm up causal lookup for development beginning
June 24, 2021. The June 30, 2026 observation becomes available July 1 under the modeled
lag; June 30 trading/valuation uses an earlier already-available observation. No
synthetic observation or future fixing substitutes for unavailable history. Repeating
normalization with the same archive, interval and retrieval timestamp is byte-identical.

Historical-vintage certification remains absent: this archive was retrieved after the
whole development period. Its reference prices and assumed availability can support
retrospective development diagnostics, but cannot establish untouched historical FX
or executable transaction prices. These limitations remain qualification blockers.
