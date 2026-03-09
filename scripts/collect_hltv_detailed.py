#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect detailed HLTV map rows online via Playwright browser session."
    )
    parser.add_argument("--subject-type", choices=["team", "player"], required=True)
    parser.add_argument("--subject-id", required=True, help="HLTV numeric subject ID.")
    parser.add_argument("--subject-slug", required=True, help="HLTV slug, e.g. falcons.")
    parser.add_argument("--subject-label", required=True, help="Display label for output.")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--max-rows", type=int, default=0, help="0 means unlimited.")
    parser.add_argument("--max-pages", type=int, default=0, help="0 means unlimited pagination pages.")
    parser.add_argument(
        "--player-team-filter",
        default=None,
        help="Only keep rows whose player_team matches this token (for subject-type=player).",
    )
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--session", default="hltv-online")
    parser.add_argument("--headed", dest="headed", action="store_true", help="Run browser in headed mode.")
    parser.add_argument("--headless", dest="headed", action="store_false", help="Run browser in headless mode.")
    parser.set_defaults(headed=True)
    parser.add_argument(
        "--persistent",
        dest="persistent",
        action="store_true",
        help="Use persistent browser context (recommended for Cloudflare-heavy pages).",
    )
    parser.add_argument("--ephemeral", dest="persistent", action="store_false", help="Disable persistent context.")
    parser.set_defaults(persistent=True)
    parser.add_argument("--browser", default="chrome")
    parser.add_argument("--request-delay", type=float, default=0.2)
    parser.add_argument("--cli-timeout", type=int, default=120, help="Timeout in seconds for each playwright-cli call.")
    parser.add_argument("--nav-timeout", type=int, default=120, help="Timeout in seconds for page navigation calls.")
    parser.add_argument("--retries", type=int, default=2, help="Retry times for navigation/eval failures.")
    parser.add_argument("--retry-delay", type=float, default=1.0, help="Delay in seconds between retries.")
    return parser.parse_args()


def build_matches_url(args) -> str:
    if args.subject_type == "team":
        base = f"https://www.hltv.org/stats/teams/matches/{args.subject_id}/{args.subject_slug}"
    else:
        base = f"https://www.hltv.org/stats/players/matches/{args.subject_id}/{args.subject_slug}"
    params = []
    if args.start_date:
        params.append(f"startDate={args.start_date}")
    if args.end_date:
        params.append(f"endDate={args.end_date}")
    if params:
        return base + "?" + "&".join(params)
    return base


def run_cli(session: str, args_list: list[str], timeout: int = 120) -> str:
    cmd = [
        "npx",
        "--yes",
        "--package",
        "@playwright/cli",
        "playwright-cli",
        "-s",
        session,
    ] + args_list
    env = dict(os.environ)
    env["NPM_CONFIG_REGISTRY"] = env.get("NPM_CONFIG_REGISTRY", "https://registry.npmjs.org")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency: npx (Node.js runtime).\n"
            "Run: skills/hltv-cs2-deep-analysis/scripts/install_deps.sh"
        ) from exc
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        hint = ""
        lower = output.lower()
        if "enotfound" in lower or "eai_again" in lower or "registry.npmjs.org" in lower:
            hint = (
                "\nDependency hint: failed to download @playwright/cli from npm registry.\n"
                "Check network/proxy and rerun: skills/hltv-cs2-deep-analysis/scripts/install_deps.sh"
            )
        raise RuntimeError(f"playwright-cli failed: {' '.join(args_list)}\n{output}{hint}")
    return output


def run_cli_retry(
    session: str,
    args_list: list[str],
    timeout: int,
    retries: int,
    retry_delay: float,
) -> str:
    attempts = max(1, retries + 1)
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            return run_cli(session, args_list, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt == attempts:
                break
            time.sleep(max(0.0, retry_delay))
    raise RuntimeError(f"playwright-cli failed after {attempts} attempts: {' '.join(args_list)}\n{last_err}") from last_err


def extract_result_json(output: str):
    marker = "### Result\n"
    end = "\n### Ran Playwright code"
    if marker not in output or end not in output:
        raise ValueError(f"Unexpected eval output:\n{output}")
    raw = output.split(marker, 1)[1].split(end, 1)[0].strip()
    return json.loads(raw)


def eval_json(session: str, js_func: str, timeout: int, retries: int, retry_delay: float):
    out = run_cli_retry(
        session,
        ["eval", js_func],
        timeout=timeout,
        retries=retries,
        retry_delay=retry_delay,
    )
    return extract_result_json(out)


def browser_flags(args) -> list[str]:
    flags = []
    if args.browser:
        flags += ["--browser", args.browser]
    if args.headed:
        flags += ["--headed"]
    if args.persistent:
        flags += ["--persistent"]
    return flags


def normalize_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {raw}")


def parse_score(score: str):
    m = re.match(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$", score or "")
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


MATCH_ROWS_JS = r"""
() => {
  const txt = (el) => (el?.textContent || '').replace(/\s+/g, ' ').trim();
  const parseTrailingRounds = (raw) => {
    const m = (raw || '').match(/\((\d{1,2})\)\s*$/);
    return m ? Number(m[1]) : null;
  };
  const normalizeMap = (raw) => {
    const m = (raw || '').trim().toLowerCase();
    const alias = {
      d2: 'Dust2',
      mrg: 'Mirage',
      inf: 'Inferno',
      anc: 'Ancient',
      anb: 'Anubis',
      anubis: 'Anubis',
      nuke: 'Nuke',
      trn: 'Train',
      ovp: 'Overpass',
      vtg: 'Vertigo',
      cbl: 'Cobblestone',
      tuscan: 'Tuscan',
      cache: 'Cache',
    };
    return alias[m] || raw;
  };
  const rows = Array.from(document.querySelectorAll('table tbody tr')).map((tr) => {
    const cells = Array.from(tr.querySelectorAll('td'));
    const dateLink = tr.querySelector('td.time a') || cells[0]?.querySelector('a');
    const date = txt(dateLink) || txt(cells[0]);
    let event = tr.querySelector('td:nth-child(2) a span')?.textContent?.trim()
      || tr.querySelector('td:nth-child(2) a')?.textContent?.replace(/\s+/g,' ').trim() || '';
    let opponent = tr.querySelector('td:nth-child(4) a')?.textContent?.replace(/\s+/g,' ').trim() || '';
    let map = tr.querySelector('td.statsMapPlayed')?.textContent?.trim() || '';
    let score = tr.querySelector('td:nth-child(6)')?.textContent?.replace(/\s+/g,' ').trim() || '';
    let result = tr.querySelector('td:nth-child(7)')?.textContent?.trim() || '';
    let player_team = '';
    const mapstats_url = dateLink?.href || '';

    // Player match history table has no "event/result" column and puts rounds in team cells.
    const scoreLooksLikeRounds = /^\s*\d{1,2}\s*-\s*\d{1,2}\s*$/.test(score || '');
    if (!scoreLooksLikeRounds && cells.length >= 7) {
      const subjectCell = txt(cells[1]);
      const opponentCell = txt(cells[2]);
      const sRounds = parseTrailingRounds(subjectCell);
      const oRounds = parseTrailingRounds(opponentCell);
      const opponentLink = cells[2]?.querySelector('a');
      const subjectTeamLink = cells[1]?.querySelector('a');
      if (sRounds !== null && oRounds !== null && opponentLink) {
        score = `${sRounds}-${oRounds}`;
        result = sRounds > oRounds ? 'W' : (sRounds < oRounds ? 'L' : 'D');
        event = '';
        opponent = txt(opponentLink);
        player_team = txt(subjectTeamLink);
        map = normalizeMap(txt(cells[3]));
      }
    }

    return { date, event, opponent, map, score, result, mapstats_url, player_team };
  });
  const currentUrl = new URL(location.href);
  const currentOffset = Number(currentUrl.searchParams.get('offset') || '0');
  let nextUrl = '';
  let nextOffset = null;
  for (const a of Array.from(document.querySelectorAll('a[href*="offset="]'))) {
    try {
      const u = new URL(a.href, location.href);
      const off = Number(u.searchParams.get('offset') || '0');
      if (Number.isFinite(off) && off > currentOffset && (nextOffset === null || off < nextOffset)) {
        nextOffset = off;
        nextUrl = u.toString();
      }
    } catch (_) {}
  }
  return { rows, next_url: nextUrl, current_offset: currentOffset };
}
"""


MAPSTATS_JS = r"""
() => {
  const toNum = (v) => {
    if (v === null || v === undefined) return null;
    const s = String(v).replace(/[^0-9.\-]/g, '');
    if (!s) return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  };
  const splitMainParen = (raw) => {
    const s = (raw || '').trim();
    const m = s.match(/^(-?\d+(?:\.\d+)?)\s*(?:\(([-+]?\d+(?:\.\d+)?)\))?$/);
    if (!m) return { main: toNum(s), extra: null };
    return { main: toNum(m[1]), extra: toNum(m[2]) };
  };
  const pctToNum = (raw) => {
    if (!raw) return null;
    return toNum(String(raw).replace('%', ''));
  };
  const metricPair = (label) => {
    const leaf = Array.from(document.querySelectorAll('*')).find(
      (el) => el.children.length === 0 && el.textContent.trim() === label
    );
    if (!leaf || !leaf.parentElement) return { left: null, right: null, raw: '' };
    const raw = leaf.parentElement.firstElementChild?.textContent?.trim() || '';
    const m = raw.match(/(-?\d+(?:\.\d+)?)\s*:\s*(-?\d+(?:\.\d+)?)/);
    if (!m) return { left: null, right: null, raw };
    return { left: Number(m[1]), right: Number(m[2]), raw };
  };
  const parseRow = (tr) => {
    const t = (sel) => tr.querySelector(sel)?.textContent?.replace(/\s+/g, ' ').trim() || '';
    const name = t('td.st-player a.text-ellipsis');
    const opening = t('td.st-opkd.traditional-data');
    const openingM = opening.match(/(-?\d+)\s*:\s*(-?\d+)/);
    const kills = splitMainParen(t('td.st-kills.traditional-data'));
    const assists = splitMainParen(t('td.st-assists'));
    const deaths = splitMainParen(t('td.st-deaths.traditional-data'));
    return {
      name,
      opening_kills: openingM ? Number(openingM[1]) : null,
      opening_deaths: openingM ? Number(openingM[2]) : null,
      multi_kills: toNum(t('td.st-mks')),
      kast: pctToNum(t('td.st-kast.gtSmartphone-only.traditional-data') || t('td.st-kast.traditional-data')),
      clutches: toNum(t('td.st-clutches')),
      kills: kills.main,
      hs_kills: kills.extra,
      assists: assists.main,
      flash_assists: assists.extra,
      deaths: deaths.main,
      traded_deaths: deaths.extra,
      adr: toNum(t('td.st-adr.traditional-data')),
      swing: pctToNum(t('td.st-roundSwing')),
      rating: toNum(t('td.st-rating')),
    };
  };
  const parseTable = (table) => {
    const team = table.querySelector('thead th')?.textContent?.replace(/\s+/g, ' ').trim() || '';
    const players = Array.from(table.querySelectorAll('tbody tr')).map(parseRow);
    return { team, players };
  };
  const totalTables = Array.from(document.querySelectorAll('table.stats-table.totalstats')).slice(0, 2);
  const tables = totalTables.map(parseTable);
  const matchLink = Array.from(document.querySelectorAll('a')).find((a) => /match page/i.test(a.textContent || ''));
  return {
    match_url: matchLink?.href || '',
    team_rating_3: metricPair('Team rating 3.0'),
    first_kills: metricPair('First kills'),
    clutches_won: metricPair('Clutches won'),
    tables,
  };
}
"""


def select_rows(
    rows,
    start_date: str | None,
    end_date: str | None,
    max_rows: int,
    player_team_filter: str | None = None,
):
    out = []
    player_team_filter_key = norm_key(player_team_filter) if player_team_filter else ""
    start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None
    for row in rows:
        s1, s2 = parse_score(row.get("score", ""))
        if s1 is None:
            continue
        if not row.get("mapstats_url", "").startswith("http"):
            continue
        date_norm = normalize_date(row["date"])
        d = datetime.strptime(date_norm, "%Y-%m-%d")
        if start and d < start:
            continue
        if end and d > end:
            continue
        player_team = row.get("player_team", "").strip()
        if player_team_filter_key and player_team_filter_key not in norm_key(player_team):
            continue
        out.append(
            {
                "date": date_norm,
                "event": row.get("event", "").strip(),
                "opponent": row.get("opponent", "").strip(),
                "map": row.get("map", "").strip(),
                "subject_rounds": s1,
                "opponent_rounds": s2,
                "result": row.get("result", "").strip() or ("W" if s1 > s2 else "L"),
                "round_diff": s1 - s2,
                "went_ot": int(s1 > 13 or s2 > 13),
                "mapstats_url": row.get("mapstats_url", ""),
                "player_team": player_team,
            }
        )
    if max_rows and max_rows > 0:
        out = out[:max_rows]
    out.sort(key=lambda r: (r["date"], r["opponent"], r["map"], r["mapstats_url"]))
    return out


def mean_num(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    return sum(vals) / len(vals)


def norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def choose_subject_table(tables: list[dict], subject_slug: str, player_team: str | None = None):
    if not tables:
        return {"team": "", "players": []}, {"team": "", "players": []}
    if len(tables) == 1:
        return tables[0], {"team": "", "players": []}

    player_team_key = norm_key(player_team or "")
    slug = norm_key(subject_slug)
    a = tables[0]
    b = tables[1]
    a_key = norm_key(a.get("team", ""))
    b_key = norm_key(b.get("team", ""))

    if player_team_key and player_team_key in a_key and player_team_key not in b_key:
        return a, b
    if player_team_key and player_team_key in b_key and player_team_key not in a_key:
        return b, a
    if slug and slug in a_key and slug not in b_key:
        return a, b
    if slug and slug in b_key and slug not in a_key:
        return b, a
    return a, b


def enrich_row_with_mapstats(row: dict, detail: dict, subject_slug: str):
    tables = detail.get("tables", [])
    subject, opponent = choose_subject_table(tables, subject_slug, row.get("player_team"))
    s_players = subject.get("players", [])

    s_rating = mean_num([p.get("rating") for p in s_players])
    s_adr = mean_num([p.get("adr") for p in s_players])
    s_kast = mean_num([p.get("kast") for p in s_players])
    s_swing = mean_num([p.get("swing") for p in s_players])
    s_opening_diff = mean_num(
        [
            (p.get("opening_kills") or 0) - (p.get("opening_deaths") or 0)
            for p in s_players
            if p.get("opening_kills") is not None and p.get("opening_deaths") is not None
        ]
    )
    s_clutches = sum((p.get("clutches") or 0) for p in s_players)

    best_player = None
    if s_players:
        best_player = sorted(
            s_players, key=lambda p: (p.get("rating") or -999, p.get("adr") or -999), reverse=True
        )[0]

    row["subject_team"] = subject.get("team", "")
    row["opponent_team"] = opponent.get("team", "")
    row["match_url"] = detail.get("match_url", "")

    tr_left = detail.get("team_rating_3", {}).get("left")
    tr_right = detail.get("team_rating_3", {}).get("right")
    fk_left = detail.get("first_kills", {}).get("left")
    fk_right = detail.get("first_kills", {}).get("right")
    cw_left = detail.get("clutches_won", {}).get("left")
    cw_right = detail.get("clutches_won", {}).get("right")

    subject_is_first = norm_key(subject.get("team", "")) == norm_key(tables[0].get("team", "")) if tables else True
    if subject_is_first:
        row["team_rating_3_subject"] = tr_left
        row["team_rating_3_opponent"] = tr_right
        row["first_kills_subject"] = fk_left
        row["first_kills_opponent"] = fk_right
        row["clutches_won_subject"] = cw_left
        row["clutches_won_opponent"] = cw_right
    else:
        row["team_rating_3_subject"] = tr_right
        row["team_rating_3_opponent"] = tr_left
        row["first_kills_subject"] = fk_right
        row["first_kills_opponent"] = fk_left
        row["clutches_won_subject"] = cw_right
        row["clutches_won_opponent"] = cw_left

    row["rating"] = round(s_rating, 3) if s_rating is not None else None
    row["adr"] = round(s_adr, 3) if s_adr is not None else None
    row["kast"] = round(s_kast, 3) if s_kast is not None else None
    row["swing"] = round(s_swing, 3) if s_swing is not None else None
    row["opening_duel_diff"] = round(s_opening_diff, 3) if s_opening_diff is not None else None
    row["clutches_won"] = s_clutches
    row["pistol_win_pct"] = None

    if best_player:
        row["best_player"] = best_player.get("name") or ""
        row["best_player_rating"] = best_player.get("rating")
        row["best_player_adr"] = best_player.get("adr")
    else:
        row["best_player"] = ""
        row["best_player_rating"] = None
        row["best_player_adr"] = None


def write_csv(rows: list[dict], output_csv: Path, subject_label: str, source_url: str):
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "date",
        "event",
        "opponent",
        "map",
        "subject_rounds",
        "opponent_rounds",
        "result",
        "round_diff",
        "went_ot",
        "subject_team",
        "opponent_team",
        "match_url",
        "mapstats_url",
        "player_team",
        "team_rating_3_subject",
        "team_rating_3_opponent",
        "first_kills_subject",
        "first_kills_opponent",
        "clutches_won_subject",
        "clutches_won_opponent",
        "rating",
        "adr",
        "kast",
        "swing",
        "opening_duel_diff",
        "clutches_won",
        "pistol_win_pct",
        "best_player",
        "best_player_rating",
        "best_player_adr",
        "subject_label",
        "source_url",
    ]
    with output_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            out = dict(row)
            out["subject_label"] = subject_label
            out["source_url"] = source_url
            w.writerow(out)


def main():
    args = parse_args()
    source_url = build_matches_url(args)
    flags = browser_flags(args)
    all_raw_rows: list[dict] = []
    page = 0
    page_url = source_url
    visited_pages = set()

    while page_url:
        if page_url in visited_pages:
            break
        if args.max_pages and page >= args.max_pages:
            break
        visited_pages.add(page_url)
        page += 1

        run_cli_retry(
            args.session,
            ["goto", page_url] + flags,
            timeout=args.nav_timeout,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
        page_data = eval_json(
            args.session,
            MATCH_ROWS_JS,
            timeout=args.cli_timeout,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
        page_rows = page_data.get("rows", []) or []
        all_raw_rows.extend(page_rows)
        page_url = page_data.get("next_url") or ""
        print(
            f"page={page} page_rows={len(page_rows)} raw_total={len(all_raw_rows)} next={'yes' if page_url else 'no'}",
            flush=True,
        )

    rows = select_rows(
        all_raw_rows,
        args.start_date,
        args.end_date,
        args.max_rows,
        player_team_filter=args.player_team_filter,
    )
    if not rows:
        raise SystemExit("No rows selected from matches page.")
    print(f"selected_rows={len(rows)} pages={page} source={source_url}", flush=True)

    for i, row in enumerate(rows, start=1):
        run_cli_retry(
            args.session,
            ["goto", row["mapstats_url"]],
            timeout=args.nav_timeout,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
        detail = eval_json(
            args.session,
            MAPSTATS_JS,
            timeout=args.cli_timeout,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
        enrich_row_with_mapstats(row, detail, args.subject_slug)
        if args.request_delay > 0:
            time.sleep(args.request_delay)
        print(
            f"[{i}/{len(rows)}] {row['date']} {row['map']} "
            f"{row['subject_rounds']}-{row['opponent_rounds']} {row.get('best_player','')}",
            flush=True,
        )

    write_csv(rows, Path(args.output_csv), args.subject_label, source_url)
    print(f"source={source_url}")
    print(f"rows={len(rows)}")
    print(f"output={args.output_csv}")


if __name__ == "__main__":
    main()
