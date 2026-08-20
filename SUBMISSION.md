# Submission — Solana Ecosystem Auto-Updating Report & Interactive Dashboard

**Sponsor:** Superteam Canada · **Reward pool:** $1,000 USDG (500/300/200) · **Deadline:** Sep 1, 2026

## Đã hoàn thành (Chaos Team — Chaos build, verified live)

| Yêu cầu bounty | Trạng thái |
|---|---|
| Public GitHub repo + code + setup instructions + README | ✅ https://github.com/ChaosAIVision/solana-pulse |
| Live hosted interactive dashboard (dark theme) | ✅ https://chaosaivision.github.io/solana-pulse/ |
| Interactive HTML dashboard | ✅ 8 KPI cards, sparklines (inline SVG), top-validator table, stake concentration bars, anomaly panel |
| Human-readable Markdown report | ✅ https://chaosaivision.github.io/solana-pulse/report.md |
| Machine-readable JSON | ✅ https://chaosaivision.github.io/solana-pulse/report.json |
| Automation (configurable interval) | ✅ GitHub Actions cron — đang chạy thực tế mỗi 2h, tự commit + Pages rebuild |
| Solana RPC metrics (getSlot, getBlockTime, getEpochInfo, getRecentPerformanceSamples, getVoteAccounts, getBalance, getSignaturesForAddress, getHealth, getSupply) | ✅ Tất cả 9 method, batched 1 round-trip |
| Network: TPS, slot time, block height, epoch progress | ✅ |
| Validators: active/delinquent, stake distribution, top validators, commission, delinquency alerts | ✅ |
| Economics: SOL price, stablecoin supply, DEX volume, fees/REV proxy, median fees | ✅ (fees 24h tổng — median per-tx cần data lưu trữ thêm) |
| Ecosystem growth / daily active addresses | ⚠️ Jupiter signature throughput proxy (DAA cần indexer riêng) |
| Anomaly detection (TPS drops, slow slots, delinquency, TVL/price moves) | ✅ Z-score ≥3σ trên 4 metric + rule thresholds |
| No API keys / external dependencies (stdlib only) | ✅ 100% — fork và chạy được ngay |
| Write-up: sources, automation strategy, anomaly detection, setup | ✅ README đầy đủ + mermaid diagram |
| Sample Markdown + JSON | ✅ committed trong repo |

## Cách submit (5 phút, cần account của anh)

1. Vào **https://earn.superteam.fun/listing/develop-solana-ecosystem-auto-updating-report-and-interactive-dashboard/**
2. Login bằng Google/GitHub (tạo account Superteam Earn — free, không KYC)
3. Bấm **Submit Now**, dán nội dung:

```
Live dashboard: https://chaosaivision.github.io/solana-pulse/
GitHub repo: https://github.com/ChaosAIVision/solana-pulse

Auto-updating Solana ecosystem report — Python stdlib ONLY (zero API keys, zero dependencies), refreshed every 2h by GitHub Actions with zero-maintenance auto-commit + Pages deploy.

► Interactive dark-theme HTML dashboard: 8 live KPI cards (SOL price w/ sparkline, non-vote TPS w/ sparkline, TVL, stablecoin supply, DEX volume, fees/REV, validator health, epoch), stake concentration bars, top-10 validator table, live anomaly panel.
► Markdown report + machine-readable JSON regenerated each run.
► Data: 9 Solana RPC methods (single batched JSON-RPC round-trip, id-matched) + DeFiLlama (TVL, DEX vol, fees, stablecoins) + CoinGecko keyless (price/vol/MC).
► Anomaly detection: rolling 60-snapshot z-score engine (TPS, slot time, TVL, price; alert at |z|≥3) + rule thresholds (delinquency >5% critical, ±10% price move, DEX vol -30% vs 7d). Alerts surface in all 3 output formats.
► Running since Aug 20, 2026 — public commit history proves continuous automation: https://github.com/ChaosAIVision/solana-pulse/commits/main
```

4. Nếu form hỏi socials/social proof: điền repo + live URL ở trên.

## Sau khi submit

- Workflow tự chạy mỗi 2h → commit history dài dần theo thời gian = bằng chứng automation thật (criterion "Automation & Maintainability").
- Ngày 01/09 trước deadline tôi có thể thêm: median tx fee từ getRecentPerformanceSamples history, DeFiLlama chain-specific charts, SIMD/Alpenglow news section nếu cần tăng điểm "Comprehensiveness".
