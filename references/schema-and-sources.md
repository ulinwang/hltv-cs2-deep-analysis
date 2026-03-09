# Schema And Sources

## Canonical Detailed CSV Schema

Required columns:
- `date` (`YYYY-MM-DD`)
- `event`
- `opponent`
- `map`
- `subject_rounds`
- `opponent_rounds`
- `result` (`W` or `L`)
- `round_diff`
- `went_ot` (`0` or `1`)
- `subject_team`
- `opponent_team`
- `match_url`
- `mapstats_url`
- `team_rating_3_subject`
- `team_rating_3_opponent`
- `first_kills_subject`
- `first_kills_opponent`
- `clutches_won_subject`
- `clutches_won_opponent`
- `rating` (subject-side average player rating 3.0)
- `adr` (subject-side average ADR)
- `kast` (subject-side average KAST)
- `swing` (subject-side average round swing)
- `opening_duel_diff` (subject-side average opening K-D delta)
- `clutches_won` (subject-side total clutches)
- `best_player`
- `best_player_rating`
- `best_player_adr`
- `subject_label`
- `source_url`

Optional advanced columns:
- `pistol_win_pct`

## HLTV Source Patterns

Team sample:
- `https://www.hltv.org/stats/teams/matches/<teamId>/<slug>`

Player sample:
- `https://www.hltv.org/stats/players/matches/<playerId>/<slug>`

Per-map detail:
- `https://www.hltv.org/stats/matches/mapstatsid/<id>/<slug>?contextIds=<id>&contextTypes=team|player`

Typical filters:
- `startDate=YYYY-MM-DD`
- `endDate=YYYY-MM-DD`
- `teamId=<id>` for player-page team scoping

## Data Quality Checks

- Date range matches requested start/end period.
- No duplicate rows by `(date, opponent, map, subject_rounds, opponent_rounds)`.
- Row count matches baseline expected maps from roster/player context.
- Latest row date is not stale versus latest known match in source page.
- Advanced fields are populated for most rows (`team_rating_3_subject`, `rating`, `adr`, `kast` at minimum).

## Missing-Data Handling Standard

- First pass: re-open missing mapstats pages and retry extraction for those specific rows.
- Second pass: if still missing, impute for analysis using:
  - map-level median
  - opponent-level median
  - global median
- Always disclose:
  - total missing before/after
  - per-column filled counts
  - any residual missing after imputation

## Actionable Recommendations Output

- Report should include a prioritized action plan (`P1/P2/P3`).
- Each action must include:
  - issue diagnosis
  - concrete execution steps
  - measurable KPI target
  - scope (map or opponent-map matchup)
