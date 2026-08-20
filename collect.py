#!/usr/bin/env python3
"""
Solana Pulse — auto-updating Solana ecosystem report.
Collects on-chain (Solana RPC) + off-chain (DeFiLlama, CoinGecko) data using
ONLY the Python standard library — no API keys, no pip dependencies.

Outputs (all regenerated each run):
  docs/index.html   — interactive dark-theme dashboard (self-contained)
  docs/report.md    — human-readable Markdown report
  docs/report.json  — machine-readable JSON
  data/history.json — rolling snapshot history (anomaly detection baseline)
"""

import json
import os
import statistics
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RPC_URL = os.environ.get("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
HISTORY_MAX = 720  # snapshots kept (at 2h cadence ~ 60 days)

# ---------------------------------------------------------------- helpers

def http_json(url, payload=None, timeout=25):
    """GET (payload=None) or POST a JSON request; return parsed JSON."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "solana-pulse/1.0 (+github)",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def rpc_batch(calls):
    """Batch JSON-RPC: calls = [(method, params), ...] -> list of results.
    Batch responses may arrive out of order, so match by id."""
    payload = [{"jsonrpc": "2.0", "id": i, "method": m, "params": p or []}
               for i, (m, p) in enumerate(calls)]
    out = http_json(RPC_URL, payload)
    by_id = {r.get("id"): r for r in out}
    return [by_id[i].get("result") if i in by_id and "result" in by_id[i] else None
            for i in range(len(calls))]


def lamports_to_sol(l):
    return (l or 0) / 1_000_000_000


def fmt_usd(x):
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(x) >= div:
            return f"${x/div:,.2f}{suf}"
    return f"${x:,.2f}"

# ---------------------------------------------------------------- collectors

def collect_rpc():
    """One batched RPC round-trip for most on-chain metrics."""
    burn = "1inc1nerator11111111111111111111111111111111"
    jupiter = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
    res = rpc_batch([
        ("getHealth", None),
        ("getSlot", None),
        ("getBlockTime", [None]),          # placeholder, replaced below
        ("getEpochInfo", None),
        ("getRecentPerformanceSamples", [20]),
        ("getVoteAccounts", None),
        ("getSupply", None),
        ("getBalance", [burn]),
        ("getSignaturesForAddress", [jupiter, {"limit": 1000}]),
    ])
    health, slot, _bt, epoch, perf, votes, supply, burn_bal, sigs = res

    # getBlockTime needs an explicit slot
    block_time = None
    if slot:
        bt = rpc_batch([("getBlockTime", [slot])])[0]
        block_time = bt

    m = {"health": health, "slot": slot, "block_time": block_time}

    # epoch (public RPC returns slotIndex; some nodes return slotsElapsed)
    if epoch:
        elapsed = epoch.get("slotsElapsed", epoch.get("slotIndex", 0))
        in_epoch = epoch.get("slotsInEpoch") or 1
        m["epoch"] = {
            "number": epoch["epoch"],
            "progress": elapsed / in_epoch,
            "slots_elapsed": elapsed,
            "slots_in_epoch": in_epoch,
            "absolute_slot": epoch["absoluteSlot"],
            "block_height": epoch.get("blockHeight"),
            "transaction_count": epoch.get("transactionCount"),
        }

    # performance (average over samples)
    if perf:
        tps_all = [s["numTransactions"] / s["samplePeriodSecs"] for s in perf]
        tps_nv = [(s.get("numNonVoteTransactions") or 0) / s["samplePeriodSecs"] for s in perf]
        slot_s = [s["samplePeriodSecs"] / s["numSlots"] for s in perf if s.get("numSlots")]
        m["performance"] = {
            "tps_incl_votes": round(statistics.mean(tps_all)),
            "tps_nonvote": round(statistics.mean(tps_nv)),
            "avg_slot_time_s": round(statistics.mean(slot_s), 3) if slot_s else None,
            "samples": len(perf),
        }

    # validators
    if votes:
        cur, delin = votes.get("current", []), votes.get("delinquent", [])
        allv = cur + delin
        total_stake = sum(v["activatedStake"] for v in allv)
        by_stake = sorted(allv, key=lambda v: -v["activatedStake"])
        top10_share = sum(v["activatedStake"] for v in by_stake[:10]) / total_stake if total_stake else 0
        commissions = [v.get("commission", 0) for v in allv]
        m["validators"] = {
            "active": len(cur),
            "delinquent": len(delin),
            "delinquency_pct": len(allv) and round(100 * len(delin) / len(allv), 2),
            "total_stake_sol": round(lamports_to_sol(total_stake)),
            "top10_stake_share_pct": round(100 * top10_share, 2),
            "avg_commission": round(statistics.mean(commissions), 1) if commissions else None,
            "top": [
                {
                    "vote_pk": v["votePubkey"],
                    "stake_sol": round(lamports_to_sol(v["activatedStake"])),
                    "commission": v.get("commission"),
                }
                for v in by_stake[:10]
            ],
        }

    # supply
    if supply and supply.get("value"):
        sv = supply["value"]
        m["supply"] = {
            "total_sol": round(lamports_to_sol(sv["total"])),
            "circulating_sol": round(lamports_to_sol(sv["circulating"])),
        }

    # burned SOL (incinerator account) + ecosystem activity proxy
    m["burned_sol"] = round(lamports_to_sol(burn_bal or 0))
    m["jupiter_sigs_last_window"] = len(sigs) if isinstance(sigs, list) else None

    return m


def collect_defillama():
    out = {}
    try:
        chains = http_json("https://api.llama.fi/v2/chains")
        sol = next(c for c in chains if c.get("name") == "Solana")
        out["tvl_usd"] = sol.get("tvl")
        out["tvl_change_1d_pct"] = sol.get("change_1d")
    except Exception as e:
        out["tvl_error"] = str(e)
    try:
        dex = http_json("https://api.llama.fi/overview/dexs/solana")
        out["dex_vol_24h_usd"] = dex.get("total24h")
        out["dex_vol_change_7d_pct"] = dex.get("change_1d")
    except Exception as e:
        out["dex_error"] = str(e)
    try:
        fees = http_json("https://api.llama.fi/overview/fees/solana")
        out["fees_24h_usd"] = fees.get("total24h")
        # REV ≈ fees + MEV-ish "revenue" where reported
        out["rev_24h_usd"] = fees.get("total24h")  # conservative proxy
    except Exception as e:
        out["fees_error"] = str(e)
    try:
        st = http_json("https://stablecoins.llama.fi/stablecoinchains")
        s = next(c for c in st if c.get("name") == "Solana")
        tc = s.get("totalCirculatingUSD")
        if isinstance(tc, dict):
            out["stablecoin_supply_usd"] = tc.get("peggedUSD")
        else:
            out["stablecoin_supply_usd"] = tc
    except Exception as e:
        out["stablecoin_error"] = str(e)
    return out


def collect_price():
    try:
        d = http_json("https://api.coingecko.com/api/v3/simple/price"
                      "?ids=solana&vs_currencies=usd&include_24hr_change=true"
                      "&include_24hr_vol=true&include_market_cap=true")
        s = d["solana"]
        return {
            "sol_usd": s.get("usd"),
            "change_24h_pct": s.get("usd_24h_change"),
            "vol_24h_usd": s.get("usd_24h_vol"),
            "market_cap_usd": s.get("usd_market_cap"),
        }
    except Exception as e:
        return {"price_error": str(e)}

# ---------------------------------------------------------------- anomalies

def detect_anomalies(hist, snap):
    """Rule + z-score based anomaly flags. Returns list of alert dicts."""
    alerts = []

    def hist_vals(key):
        vals = []
        for h in hist[-60:]:
            try:
                vals.append(h["metrics"][key])
            except (KeyError, TypeError):
                pass
        return [v for v in vals if isinstance(v, (int, float))]

    def zflag(key, label, lo=-3, hi=3):
        vals = hist_vals(key)
        if len(vals) >= 12:
            mu, sd = statistics.mean(vals), statistics.pstdev(vals)
            cur = snap["metrics"][key]
            if sd > 0:
                z = (cur - mu) / sd
                if z < lo or z > hi:
                    side = "drop" if z < 0 else "spike"
                    alerts.append({
                        "metric": label, "severity": "warning",
                        "value": cur, "baseline_mean": round(mu, 4),
                        "z_score": round(z, 2),
                        "message": f"{label} {side} (z={z:.1f}, mean={mu:,.4g})",
                    })

    zflag("tps_nonvote", "Non-vote TPS")
    zflag("avg_slot_time_s", "Slot time")
    zflag("tvl_usd", "TVL")
    zflag("sol_usd", "SOL price")

    v = snap["metrics"]
    if isinstance(v.get("delinquency_pct"), (int, float)) and v["delinquency_pct"] > 5:
        alerts.append({"metric": "Validator delinquency", "severity": "critical",
                       "value": v["delinquency_pct"],
                       "message": f"{v['delinquency_pct']}% of validators delinquent (threshold 5%)"})
    if isinstance(v.get("change_24h_pct"), (int, float)) and abs(v["change_24h_pct"]) >= 10:
        alerts.append({"metric": "SOL price 24h", "severity": "info",
                       "value": v["change_24h_pct"],
                       "message": f"SOL moved {v['change_24h_pct']:+.1f}% in 24h"})
    if isinstance(v.get("dex_vol_change_7d_pct"), (int, float)) and v["dex_vol_change_7d_pct"] <= -30:
        alerts.append({"metric": "DEX volume", "severity": "warning",
                       "value": v["dex_vol_change_7d_pct"],
                       "message": f"DEX volume down {v['dex_vol_change_7d_pct']:.0f}% vs 7d ago"})
    return alerts

# ---------------------------------------------------------------- outputs

def load_history():
    p = os.path.join(HERE, "data", "history.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(hist):
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    with open(os.path.join(HERE, "data", "history.json"), "w") as f:
        json.dump(hist[-HISTORY_MAX:], f, indent=1)


def render_markdown(snap, report_top_validators=None):
    m = snap["metrics"]
    L = []
    L.append(f"# Solana Ecosystem Pulse — {snap['generated_at_human']}")
    L.append("")
    L.append(f"*Auto-generated by [Solana Pulse](https://github.com/ChaosAIVision/solana-pulse). "
             f"Data: Solana RPC · DeFiLlama · CoinGecko. No API keys.*")
    L.append("")
    L.append("## Network")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Health | {m.get('health')} |")
    L.append(f"| Current slot | {m.get('slot'):,} |" if m.get("slot") else "| Current slot | n/a |")
    if m.get("performance"):
        L.append(f"| TPS (non-vote) | {m['performance']['tps_nonvote']:,} |")
        L.append(f"| TPS (incl. votes) | {m['performance']['tps_incl_votes']:,} |")
        L.append(f"| Avg slot time | {m['performance']['avg_slot_time_s']} s |")
    if m.get("epoch"):
        e = m["epoch"]
        L.append(f"| Epoch | #{e['number']} ({e['progress']*100:.1f}% complete) |")
    L.append("")
    L.append("## Validators")
    if m.get("active") is not None:
        L.append("| Metric | Value |")
        L.append("|---|---|")
        L.append(f"| Active | {m['active']:,} |")
        L.append(f"| Delinquent | {m.get('delinquent',0):,} ({m.get('delinquency_pct',0)}%) |")
        L.append(f"| Total stake | {m.get('total_stake_sol',0):,} SOL |")
        L.append(f"| Top-10 stake share | {m.get('top10_stake_share_pct',0)}% |")
        L.append(f"| Avg commission | {m.get('avg_commission','—')}% |")
        L.append("")
        L.append("### Top validators by stake")
        L.append("| Vote account | Stake (SOL) | Commission |")
        L.append("|---|---|---|")
        top = report_top_validators or []
        for t in top:
            L.append(f"| `{t['vote_pk'][:16]}…` | {t['stake_sol']:,} | {t['commission']}% |")
    L.append("")
    L.append("## Economics")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| SOL price | ${m.get('sol_usd', 0):,.2f} ({m.get('change_24h_pct', 0):+.1f}% 24h) |")
    L.append(f"| Market cap | {fmt_usd(m.get('market_cap_usd') or 0)} |")
    L.append(f"| TVL (DeFiLlama) | {fmt_usd(m.get('tvl_usd') or 0)} |")
    L.append(f"| Stablecoin supply | {fmt_usd(m.get('stablecoin_supply_usd') or 0)} |")
    L.append(f"| DEX volume 24h | {fmt_usd(m.get('dex_vol_24h_usd') or 0)} |")
    L.append(f"| Fees 24h (REV proxy) | {fmt_usd(m.get('fees_24h_usd') or 0)} |")
    L.append(f"| Circulating supply | {m.get('circulating_sol', 0):,} SOL |" if m.get("circulating_sol") else "| Circulating supply | n/a |")
    L.append(f"| Burned (incinerator) | {m.get('burned_sol', 0):,} SOL |")
    L.append("")
    L.append("## Activity")
    L.append(f"- Jupiter program: {m.get('jupiter_sigs_last_window', 'n/a')} recent signatures sampled (activity proxy)")
    L.append("")
    if snap.get("alerts"):
        L.append("## ⚠️ Anomalies detected")
        for a in snap["alerts"]:
            L.append(f"- **{a['metric']}** — {a['message']} `{a.get('severity')}`")
    else:
        L.append("## ✅ No anomalies detected")
    L.append("")
    L.append("---")
    L.append(f"*Next update: every 2h via GitHub Actions. Last run: {snap['generated_at_human']} UTC.*")
    return "\n".join(L)


def render_dashboard(snap, hist, top_validators=None):
    """Self-contained dark dashboard; data inlined, inline SVG only."""
    m = snap["metrics"]
    series = [(h["ts"], h["metrics"].get("tps_nonvote"), h["metrics"].get("sol_usd"))
              for h in hist if isinstance(h.get("metrics"), dict)]
    series = [s for s in series if s[1] is not None][-120:]

    def spark(vals, w=260, h=44):
        if len(vals) < 2:
            return ""
        lo, hi = min(vals), max(vals)
        rng = (hi - lo) or 1
        pts = [f"{i*(w/(len(vals)-1)):.1f},{h-((v-lo)/rng)*h:.1f}"
               for i, v in enumerate(vals)]
        return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" class="spark">'
                f'<polyline fill="none" stroke="currentColor" stroke-width="1.6" '
                f'points="{" ".join(pts)}"/></svg>')

    tps_hist = [s[1] for s in series]
    px_hist = [s[2] for s in series if s[2]]
    p = m  # flat metrics
    v = m  # flat metrics

    top_rows = "".join(
        f"<tr><td class='mono'>{t['vote_pk'][:20]}…</td>"
        f"<td class='num'>{t['stake_sol']:,}</td>"
        f"<td class='num'>{t['commission']}%</td></tr>"
        for t in (top_validators or [])[:10])

    alert_html = ""
    if snap.get("alerts"):
        items = "".join(
            f"<li class='alert {a.get('severity')}'><b>{a['metric']}</b> — {a['message']}</li>"
            for a in snap["alerts"])
        alert_html = f"<section class='card'><h2>⚠️ Anomalies</h2><ul class='alerts'>{items}</ul></section>"
    else:
        alert_html = "<section class='card ok'><h2>✅ Nominal</h2><p>No anomalies detected in this run.</p></section>"

    def card(label, value, sub="", spark_svg=""):
        s = f"<span class='spark-wrap'>{spark_svg}</span>" if spark_svg else ""
        sub = f"<div class='sub'>{sub}</div>" if sub else ""
        return (f"<div class='card metric'><div class='label'>{label}</div>"
                f"<div class='value'>{value}</div>{sub}{s}</div>")

    dl = (m.get("tvl_change_1d_pct") or 0)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Solana Pulse — Ecosystem Report</title>
<style>
 :root {{ --bg:#0b0f14; --panel:#111820; --line:#1e2a36; --fg:#dbe4ee;
         --dim:#7d8fa3; --acc:#4fd1c5; --warn:#f6c177; --crit:#f7768e; }}
 * {{ box-sizing:border-box; margin:0 }}
 body {{ background:var(--bg); color:var(--fg);
        font:14px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif; padding:24px; }}
 a {{ color:var(--acc); text-decoration:none }}
 header {{ display:flex; justify-content:space-between; align-items:baseline;
          flex-wrap:wrap; gap:8px; margin-bottom:18px }}
 h1 {{ font-size:20px; font-weight:650 }}
 h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.08em;
      color:var(--dim); margin-bottom:10px }}
 .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
         gap:12px; margin-bottom:14px }}
 .card {{ background:var(--panel); border:1px solid var(--line);
         border-radius:10px; padding:14px 16px }}
 .metric .label {{ color:var(--dim); font-size:12px }}
 .metric .value {{ font-size:26px; font-weight:700; margin:2px 0 }}
 .metric .sub {{ color:var(--dim); font-size:12px }}
 .spark {{ width:100%; height:44px; color:var(--acc); margin-top:6px;
          display:block }}
 .num {{ text-align:right; font-variant-numeric:tabular-nums }}
 .mono {{ font-family:ui-monospace,Menlo,monospace; font-size:12px }}
 table {{ width:100%; border-collapse:collapse }}
 td,th {{ padding:6px 8px; border-bottom:1px solid var(--line); text-align:left }}
 th {{ color:var(--dim); font-size:12px; text-transform:uppercase; letter-spacing:.06em }}
 .alerts {{ list-style:none; padding:0 }}
 .alert {{ padding:8px 10px; border-left:3px solid var(--warn);
          background:#1a2130; border-radius:4px; margin-bottom:6px }}
 .alert.critical {{ border-color:var(--crit) }}
 .alert.info {{ border-color:var(--acc) }}
 .ok {{ color:var(--acc) }}
 .meta {{ color:var(--dim); font-size:12px }}
 .bar {{ height:6px; background:var(--line); border-radius:3px; overflow:hidden }}
 .bar>i {{ display:block; height:100%; background:var(--acc) }}
 .cols {{ display:grid; grid-template-columns:1fr 1fr; gap:12px }}
 @media(max-width:760px){{ .cols{{grid-template-columns:1fr}} body{{padding:12px}} }}
</style></head><body>
<header>
 <h1>◎ Solana Pulse</h1>
 <div class="meta">Auto-updating ecosystem report · updated {snap['generated_at_human']} UTC ·
 <a href="report.md">Markdown</a> · <a href="report.json">JSON</a> ·
 <a href="https://github.com/ChaosAIVision/solana-pulse">GitHub</a></div>
</header>

<div class="grid">
 {card("SOL Price", f"${m.get('sol_usd',0):,.2f}", f"{m.get('change_24h_pct',0):+.1f}% 24h · MC {fmt_usd(m.get('market_cap_usd') or 0)}", spark(px_hist))}
 {card("TPS (non-vote)", f"{p.get('tps_nonvote',0):,}", f"incl. votes {p.get('tps_incl_votes',0):,} · slot {p.get('avg_slot_time_s','—')}s", spark(tps_hist))}
 {card("DeFi TVL", fmt_usd(m.get('tvl_usd') or 0), f"{(m.get('tvl_change_1d_pct') or 0):+.1f}% 24h")}
 {card("Stablecoins", fmt_usd(m.get('stablecoin_supply_usd') or 0), "on Solana")}
 {card("DEX Volume 24h", fmt_usd(m.get('dex_vol_24h_usd') or 0), f"7d trend {m.get('dex_vol_change_7d_pct') or 0:+.0f}%")}
 {card("Fees / REV 24h", fmt_usd(m.get('fees_24h_usd') or 0), "protocol fees")}
 {card("Validators", f"{v.get('active',0):,}", f"{v.get('delinquent',0)} delinquent ({v.get('delinquency_pct',0)}%) · top-10 {v.get('top10_stake_share_pct',0)}% stake")}
 {card("Epoch", f"#{m.get('epoch_number','—')}", f"{(m.get('epoch_progress') or 0)*100:.1f}% complete")}
</div>

<div class="cols">
 <section class="card"><h2>Epoch progress</h2>
  <div class="bar"><i style="width:{(m.get('epoch_progress') or 0)*100:.1f}%"></i></div>
  <p class="meta" style="margin-top:6px">Epoch #{m.get('epoch_number','—')} · absolute slot {m.get('slot',0):,}</p>
  <h2 style="margin-top:16px">Stake concentration (top 10)</h2>
  <div class="bar"><i style="width:{v.get('top10_stake_share_pct',0):.0f}%"></i></div>
  <p class="meta" style="margin-top:6px">Total stake {v.get('total_stake_sol',0):,} SOL · avg commission {v.get('avg_commission','—')}%</p>
  <h2 style="margin-top:16px">Supply</h2>
  <p class="meta">Circulating {m.get('circulating_sol',0):,} SOL · burned {m.get('burned_sol',0):,} SOL</p>
 </section>
 <section class="card"><h2>Top validators by stake</h2>
  <table><tr><th>Vote account</th><th class="num">SOL</th><th class="num">Comm</th></tr>{top_rows}</table>
 </section>
</div>

{alert_html}

<footer class="meta" style="margin-top:14px">
 Sources: Solana JSON-RPC (getHealth · getSlot · getBlockTime · getEpochInfo ·
 getRecentPerformanceSamples · getVoteAccounts · getSupply · getBalance ·
 getSignaturesForAddress) · DeFiLlama · CoinGecko. Stdlib-only Python, no API keys.
 Refresh: GitHub Actions cron, every 2h.
</footer>
</body></html>"""


def main():
    now = time.time()
    hist = load_history()

    rpc_data = collect_rpc()
    dl = collect_defillama()
    px = collect_price()

    metrics = {
        "health": rpc_data.get("health"),
        "slot": rpc_data.get("slot"),
        "block_time": rpc_data.get("block_time"),
        **(rpc_data.get("performance") or {}),
        **(rpc_data.get("validators") or {}),
        "epoch_number": (rpc_data.get("epoch") or {}).get("number"),
        "epoch_progress": (rpc_data.get("epoch") or {}).get("progress"),
        "circulating_sol": (rpc_data.get("supply") or {}).get("circulating_sol"),
        "total_supply_sol": (rpc_data.get("supply") or {}).get("total_sol"),
        "burned_sol": rpc_data.get("burned_sol"),
        "jupiter_sigs_last_window": rpc_data.get("jupiter_sigs_last_window"),
        **{k: v for k, v in dl.items() if not k.endswith("_error")},
        **{k: v for k, v in px.items() if not k.endswith("_error")},
    }

    snap = {
        "ts": int(now),
        "generated_at_human": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "metrics": metrics,
        "alerts": [],
    }
    snap["alerts"] = detect_anomalies(hist, snap)

    hist.append({"ts": int(now), "metrics": metrics})
    save_history(hist)

    # flatten full detail for the JSON report
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "rpc": RPC_URL,
            "offchain": ["api.llama.fi", "stablecoins.llama.fi", "api.coingecko.com"],
        },
        "summary": metrics,
        "detail": {
            "performance": rpc_data.get("performance"),
            "validators": rpc_data.get("validators"),
            "epoch": rpc_data.get("epoch"),
            "supply": rpc_data.get("supply"),
        },
        "alerts": snap["alerts"],
        "errors": [k for k in {**dl, **px} if k.endswith("_error")],
    }

    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    with open(os.path.join(HERE, "docs", "report.json"), "w") as f:
        json.dump(report, f, indent=1)
    with open(os.path.join(HERE, "docs", "report.md"), "w") as f:
        f.write(render_markdown(snap, (rpc_data.get("validators") or {}).get("top")))
    with open(os.path.join(HERE, "docs", "index.html"), "w") as f:
        f.write(render_dashboard(snap, hist, (rpc_data.get("validators") or {}).get("top")))

    print(f"OK snapshot ts={snap['ts']} alerts={len(snap['alerts'])} "
          f"history={len(hist)}")


if __name__ == "__main__":
    main()
