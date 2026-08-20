# ◎ Solana Pulse — Auto-Updating Solana Ecosystem Report

**Live dashboard:** <https://chaosaivision.github.io/solana-pulse/> ·
[Markdown report](https://chaosaivision.github.io/solana-pulse/report.md) ·
[JSON](https://chaosaivision.github.io/solana-pulse/report.json)

An auto-updating, comprehensive report on the state of the Solana ecosystem:
network performance, validator health, economics, and ecosystem activity —
refreshed **every 2 hours** by GitHub Actions, with **zero API keys and zero
external dependencies** (Python stdlib only).

> Built for the *Superteam Canada — Solana Ecosystem Auto-Updating Report &
> Interactive Dashboard* bounty.

---

## What it tracks

| Area | Metrics | Source |
|---|---|---|
| Network | health, slot, block time, TPS (vote & non-vote), avg slot time | Solana RPC `getHealth` `getSlot` `getBlockTime` `getRecentPerformanceSamples` |
| Consensus | epoch number/progress, active vs delinquent validators, stake distribution, top-10 concentration, avg commission, top validators by stake | `getEpochInfo` `getVoteAccounts` |
| Monetary | total & circulating supply, burned SOL (incinerator address) | `getSupply` `getBalance` |
| Activity | Jupiter program signature throughput (proxy for DEX activity) | `getSignaturesForAddress` |
| Economics | SOL price, 24h change, volume, market cap | CoinGecko (keyless) |
| DeFi | TVL, DEX volume 24h, protocol fees (REV proxy), stablecoin supply | DeFiLlama (keyless) |

## Outputs

1. **`docs/index.html`** — interactive dark-theme dashboard. Self-contained
   (single file, no JS framework, no external assets): KPI cards, sparklines
   built from inline SVG, stake concentration bars, top-validator table,
   live anomaly panel.
2. **`docs/report.md`** — human-readable Markdown report (this is what gets
   re-generated each run).
3. **`docs/report.json`** — machine-readable structured report, including a
   `detail` section with full nested data (top validators, epoch info, supply).
4. **`data/history.json`** — rolling snapshot history (last ~60 days at 2h
   cadence). This powers the sparklines **and** the anomaly baselines.

## Anomaly detection

Two layers, both computed from `data/history.json` on every run:

- **Z-score drift** on TPS (non-vote), slot time, TVL, and SOL price: if the
  latest snapshot deviates ≥3σ from the trailing mean of the last 60
  snapshots, a warning is raised with the exact z-score.
- **Threshold rules**: validator delinquency > 5% (critical), 24h price move
  ≥ ±10% (info), DEX volume down ≥ 30% vs 7d ago (warning).

Alerts surface in all three outputs (dashboard panel, Markdown section,
JSON `alerts` array).

## Automation strategy

```mermaid
flow LR
    A[GitHub Actions cron\nevery 2h] --> B[collect.py\nstdlib-only]
    B --> C[Solana RPC\nbatched JSON-RPC]
    B --> D[DeFiLlama]
    B --> E[CoinGecko]
    C --> F[history.json\nrolling baseline]
    D --> F
    E --> F
    F --> G[z-score + rule\nanomaly engine]
    G --> H[docs/ HTML · MD · JSON]
    H --> I[git push]
    I --> J[GitHub Pages\nlive dashboard]
```

- One batched JSON-RPC round-trip for all on-chain calls (id-matched; batch
  responses may arrive out of order — handled).
- State lives entirely in `data/history.json` inside the repo; the runner is
  stateless.
- `concurrency: pulse` cancels overlapping runs; failures never corrupt
  history (each run writes only after a successful collection).

## Run it yourself

```bash
python3 collect.py          # regenerate all outputs (~5s, no deps)
open docs/index.html        # view dashboard
```

Optional: point at any Solana RPC node via `SOLANA_RPC=<url> python3 collect.py`.

## Repository layout

```
collect.py                    # collector + renderers + anomaly engine (stdlib only)
docs/index.html               # generated: live dashboard (GitHub Pages root)
docs/report.md                # generated: Markdown report
docs/report.json              # generated: JSON report
data/history.json             # generated: rolling snapshot history
.github/workflows/pulse.yml   # every-2h automation
```

## Why no API keys anywhere

By design: Solana public RPC + DeFiLlama + CoinGecko keyless endpoints cover
every metric in the bounty's scope. Nothing to sign up for, nothing to rotate,
nothing to leak. Fork it and it keeps working.

## License

MIT.
