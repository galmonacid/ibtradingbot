# Phase 3 Research Report

## Overall decision

**FAIL CLOSED — not ready for paper trading.**

## Provenance

| Field | Value |
|---|---|
| artifact_sha256 | 56302d6a3e48c7c7124057d6bb8731096e302cb892904fa8f4a6877b613d7fb9 |
| calendar_sessions_sha256 | 518345cb7910fa018602487dcc95bcedfda20c423afe60592e677db2cc5c0393 |
| calendar_sha256 | 4d380c64c5adbe2ce865d026c763302e044ef1f8cc84a23038fe99499d6bffc3 |
| calendar_version | synthetic-weekday-calendar-v1 |
| config_sha256 | cb8df9781c6c3996c8748cb7b704b9a619fb99951e2b1935239b247010d5e46e |
| corporate_actions_sha256 | d40c9caff200bc8668ae5eefe430f85e8a4b79967fbce4b2206665d4c1bc2606 |
| corporate_actions_version | actions-fixture-v1 |
| data_sha256 | 11dc1c0bd75fa55c8eae80e817accc9c0fd90aa84e69a18723a75e32a93a0b47 |
| data_version | synthetic-phase3-v1 |
| git_dirty | yes |
| git_revision | 3ecb920f3bb7e3d98da6865efce6f5fecf15d681 |
| run_timestamp_utc | 2026-09-10T00:00:00+00:00 |
| strategy_version | phase2-risk-portfolio-v1 |
| universe_sha256 | 46d9abbbd9b475cb4b68486b361c2c8549cb0e730171189001a9642b331a4894 |
| universe_version | seed-v1 |

## Dataset and admissibility

- Name: synthetic Phase 3 engineering fixture
- Version: synthetic-phase3-v1
- Period: 2007-01-01 to 2020-12-31
- Sessions: 3654
- Point-in-time: no
- Synthetic: yes
- Admissible deployment evidence: no

## Walk-forward folds

| Fold | Train | Validation | Test | OOS observations | Parameters |
|---:|---|---|---|---:|---|
| 0 | 2007-01-01 to 2014-12-31 | 2015-01-01 to 2016-12-30 | 2017-01-02 to 2017-12-29 | 260 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 |
| 1 | 2007-01-01 to 2015-06-30 | 2015-07-01 to 2017-06-30 | 2017-07-03 to 2018-06-29 | 260 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 |
| 2 | 2007-01-01 to 2015-12-31 | 2016-01-01 to 2017-12-29 | 2018-01-01 to 2018-12-31 | 261 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 |
| 3 | 2007-01-01 to 2016-06-30 | 2016-07-01 to 2018-06-29 | 2018-07-02 to 2019-06-28 | 260 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 |
| 4 | 2007-01-01 to 2016-12-30 | 2017-01-02 to 2018-12-31 | 2019-01-01 to 2019-12-31 | 261 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 |
| 5 | 2007-01-01 to 2017-06-30 | 2017-07-03 to 2019-06-28 | 2019-07-01 to 2020-06-30 | 262 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 |
| 6 | 2007-01-01 to 2017-12-29 | 2018-01-01 to 2019-12-31 | 2020-01-01 to 2020-12-31 | 262 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 |

## Sensitivity analysis

| Fold | Parameters | Validation score | Selected | Viable |
|---:|---|---:|---|---|
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.95 | yes | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=3, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=5, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=0, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=10, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.1, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.15, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.55, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.65, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=biweekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Thursday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=0.8 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1.2 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.3, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.4, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=2, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=2, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 0 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=10, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.95 | yes | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=3, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=5, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=0, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=10, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.1, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.15, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.55, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.65, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=biweekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Thursday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=0.8 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1.2 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.3, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.4, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=2, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=2, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 1 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=10, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.95 | yes | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=3, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=5, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=0, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=10, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.1, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.15, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.55, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.65, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=biweekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Thursday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=0.8 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1.2 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.3, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.4, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=2, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=2, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 2 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=10, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.95 | yes | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=3, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=5, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=0, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=10, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.1, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.15, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.55, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.65, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=biweekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Thursday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=0.8 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1.2 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.3, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.4, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=2, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=2, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 3 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=10, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.95 | yes | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=3, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=5, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=0, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=10, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.1, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.15, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.55, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.65, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=biweekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Thursday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=0.8 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1.2 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.3, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.4, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=2, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=2, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 4 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=10, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.95 | yes | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=3, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=5, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=0, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=10, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.1, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.15, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.55, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.65, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=biweekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Thursday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=0.8 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1.2 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.3, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.4, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=2, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=2, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 5 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=10, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.95 | yes | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=3, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=5, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=0, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=10, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.1, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.15, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.55, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.65, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=biweekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Thursday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=0.8 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1.2 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.3, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.4, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=2, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=2, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=5, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |
| 6 | commission_multiplier=1, execution_delay_sessions=1, momentum_63d_weight=0.35, rebalance_day=Friday, rebalance_frequency=weekly, risk_on_breadth_threshold=0.6, skip_recent_days=5, slippage_bps_each_side=10, target_annual_volatility=0.12, target_positions=4, trend_window_scale=1 | 0.9 | no | yes |

## Bootstrap summaries

| Source | Metric | q05 | q50 | q95 |
|---|---|---:|---:|---:|
| daily | cagr | 0.0669204 | 0.0674874 | 0.0680546 |
| daily | maximum_drawdown | 0.00229985 | 0.00299775 | 0.00299775 |
| daily | sharpe_ratio | 4.6324 | 4.67867 | 4.72515 |
| daily | one_year_return | 0.0661919 | 0.0685411 | 0.0685411 |
| daily | three_year_return | 0.21468 | 0.217357 | 0.217357 |
| regime_blocks | cagr | 0.0672694 | 0.0674884 | 0.0676008 |
| regime_blocks | maximum_drawdown | 0.0015 | 0.0015 | 0.0015 |
| regime_blocks | sharpe_ratio | 4.66092 | 4.67878 | 4.68802 |
| regime_blocks | one_year_return | 0.0661919 | 0.0661919 | 0.0661919 |
| regime_blocks | three_year_return | 0.21468 | 0.21468 | 0.21468 |
| trade_returns | mean | 0.00625 | 0.00625 | 0.00625 |

## Ablation testing

| Scenario | Metrics | Delta vs full |
|---|---|---|
| without_momentum | cagr=0.0674874, maximum_drawdown=0.0015, sharpe_ratio=4.67867 | cagr=0, maximum_drawdown=0, sharpe_ratio=0 |
| without_trend | cagr=0.0674874, maximum_drawdown=0.0015, sharpe_ratio=4.67867 | cagr=0, maximum_drawdown=0, sharpe_ratio=0 |
| without_regime | cagr=0.0674874, maximum_drawdown=0.0015, sharpe_ratio=4.67867 | cagr=0, maximum_drawdown=0, sharpe_ratio=0 |
| without_inverse_volatility | cagr=0.0674874, maximum_drawdown=0.0015, sharpe_ratio=4.67867 | cagr=0, maximum_drawdown=0, sharpe_ratio=0 |
| without_risk_controls | cagr=0.0674874, maximum_drawdown=0.0015, sharpe_ratio=4.67867 | cagr=0, maximum_drawdown=0, sharpe_ratio=0 |
| full_deterministic | cagr=0.0674874, maximum_drawdown=0.0015, sharpe_ratio=4.67867 | cagr=0, maximum_drawdown=0, sharpe_ratio=0 |

## OOS strategy metrics

| Field | Value |
|---|---|
| cagr | 0.0674874 |
| annualized_volatility | 0.0139813 |
| sharpe_ratio | 4.67867 |
| sortino_ratio | 6.13981 |
| maximum_drawdown | 0.0015 |
| calmar_ratio | 44.9916 |
| win_rate | 0.75 |
| profit_factor | 6 |
| turnover | 21.7843 |
| average_holding_period | 1.38889 |
| exposure | 0.75 |
| number_of_trades | 180 |
| average_trade_return | 0.00625 |
| median_trade_return | 0.01 |
| best_trade | 0.01 |
| worst_trade | -0.005 |
| best_month | 0.00731749 |
| worst_month | 0.00369727 |
| best_year | 0.0713184 |
| worst_year | 0.0682154 |

## Stressed OOS metrics

| Field | Value |
|---|---|
| cagr | 0.0541245 |
| annualized_volatility | 0.0139813 |
| sharpe_ratio | 3.77746 |
| sortino_ratio | 4.79725 |
| maximum_drawdown | 0.00155 |
| calmar_ratio | 36.1743 |
| win_rate | NOT ASSESSABLE |
| profit_factor | NOT ASSESSABLE |
| turnover | NOT ASSESSABLE |
| average_holding_period | NOT ASSESSABLE |
| exposure | NOT ASSESSABLE |
| number_of_trades | NOT ASSESSABLE |
| average_trade_return | NOT ASSESSABLE |
| median_trade_return | NOT ASSESSABLE |
| best_trade | NOT ASSESSABLE |
| worst_trade | NOT ASSESSABLE |
| best_month | 0.00616007 |
| worst_month | 0.0026441 |
| best_year | 0.0573789 |
| worst_year | 0.0543689 |

## Benchmark metrics

| Field | Value |
|---|---|
| cash_cagr | 0 |
| down_market_capture | 1.25 |
| excess_cagr | 0.0143479 |
| information_ratio | 4.67867 |
| spy_cagr | 0.0555812 |
| tracking_error | 0.00279626 |
| up_market_capture | 1.25 |

## Mandatory deployment gates

| Gate | Status | Observed | Requirement | Detail |
|---|---|---:|---:|---|
| admissible_point_in_time_evidence | FAIL | no | yes | requires out-of-sample results from admissible point-in-time data |
| out_of_sample_cagr | FAIL | 0.0674874 | 0.08 | requires out_of_sample_cagr >= 0.08 |
| out_of_sample_sharpe | PASS | 4.67867 | 0.8 | requires out_of_sample_sharpe >= 0.8 |
| out_of_sample_maximum_drawdown | PASS | 0.0015 | 0.15 | requires out_of_sample_maximum_drawdown <= 0.15 |
| stressed_cagr | FAIL | 0.0541245 | 0.06 | requires stressed_cagr >= 0.06 |
| stressed_sharpe | PASS | 3.77746 | 0.6 | requires stressed_sharpe >= 0.6 |
| closed_trades | PASS | 180 | 150 | requires closed_trades >= 150 |
| year_profit_concentration | PASS | 0.253333 | 0.35 | largest positive contributor / net cumulative profit must be <= 0.35 |
| stock_profit_concentration | FAIL | 0.266667 | 0.2 | largest positive contributor / net cumulative profit must be <= 0.2 |
| parameter_robustness | PASS | yes | yes | nearby parameter values must remain economically viable |
| bootstrap_cagr_q05 | PASS | 0.0669204 | 0 | requires bootstrap_cagr_q05 >= 0.0 |
| bootstrap_sharpe_q05 | PASS | 4.6324 | 0 | requires bootstrap_sharpe_q05 >= 0.0 |
| bootstrap_maximum_drawdown_q95 | PASS | 0.00299775 | 0.25 | requires bootstrap_maximum_drawdown_q95 <= 0.25 |

## Limitations

- Synthetic returns and a weekday-only calendar are engineering fixtures.
- The fixed seed universe is not point-in-time deployment evidence.
