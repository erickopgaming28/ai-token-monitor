# AI Token Monitor

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PySide6-Qt-green?logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/platform-Windows%20|%20macOS%20|%20Linux-0078D6?logo=desktop&logoColor=white" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="License">
</p>

**AI Token Monitor** is a lightweight cross-platform system tray application that automatically detects, tracks, and visualizes AI token consumption across your local projects.

It monitors tools like **Claude Code**, **OpenAI Codex**, **Gemini CLI**, **Cursor**, **Aider**, and more — showing input/output token breakdowns and estimated costs per project, all running silently in the background.

<p align="center">
  <a href="https://buymeacoffee.com/erickgio">
    <img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Buy Me A Coffee">
  </a>
</p>

---

## Features

- **System Tray App** — Lives next to your clock, zero distraction
- **Cross-platform** — Windows 10/11, macOS, and Linux
- **Auto-detection** — Scans your system for installed AI tools (Claude Code, Codex, Gemini CLI, Cursor, Aider, Continue)
- **Per-project tracking** — Input tokens, output tokens, cache read/write tokens
- **Cost estimation** — Configurable pricing per model/provider (USD per million tokens)
- **Live pricing updates** — Fetches current pricing from provider APIs (cached 24h)
- **10+ providers built-in** — Claude, OpenAI, Gemini, DeepSeek, Qwen, Mistral, and more
- **Custom providers** — Add your own providers and models via Settings
- **Visual breakdown** — Color-coded bars showing input vs output proportion
- **Detail view** — Click any project for full cost breakdown by provider, model, and day
- **Dark theme** — Catppuccin Mocha inspired UI
- **Settings panel** — Edit pricing, scan intervals, auto-start, add custom models
- **Local & private** — All data stays on your machine in a local SQLite database

## How It Works

```
AI Tool Logs  ──►  Scanner (FileWatcher + Polling)
                           │
                     Token Parser (dedup by message_id)
                           │
                     SQLite Database
                           │
                ┌──────────┴──────────┐
           Cost Engine          Aggregator
                └──────────┬──────────┘
                           │
            ┌──────────────┼──────────────┐
       AI Detector    Pricing Fetcher   System Tray UI
```

1. **AI Detector** scans for installed tools on startup (Claude Code, Codex, Gemini CLI, Cursor, Aider, Continue)
2. **Scanner** watches log directories for new/modified files
3. **Parser** extracts token usage from structured logs (only final responses, not streaming chunks)
4. **Database** stores events with deduplication via unique `message_id`
5. **Pricing Fetcher** updates model prices from provider APIs every 24h
6. **Cost Engine** calculates costs using per-model pricing
7. **Aggregator** pre-computes daily rollups for fast UI queries
8. **Tray UI** shows a compact popup with project list, token bars, and costs

## Screenshots

### Popup Panel
```
┌──────────────────────────────────┐
│ AI Token Monitor   [All Time ▼]  │
│ $48.52                           │
│ 5 projects                       │
├──────────────────────────────────┤
│ my-web-app                $23.07 │
│ 372.4K tokens                    │
│ [█ IN █████████████ OUT ████████]│
│ IN: 3.8K  OUT: 368.6K           │
├──────────────────────────────────┤
│ api-server                $15.78 │
│ 269.1K tokens                    │
│ [█ IN ████████████ OUT █████████]│
│ IN: 8.1K  OUT: 261.0K           │
└──────────────────────────────────┘
```

### Detail View
```
┌──────────────────────────────────┐
│ <- Back                          │
│ PROJECT: my-web-app              │
│ Path: ~/projects/my-web-app      │
│ Last activity: 2m ago            │
├──────────────────────────────────┤
│ TOKENS        IN         OUT     │
│ Input:       3,782               │
│ Output:    368,648               │
│ Cache read: 12,450,200           │
│ Cache write: 1,230,500           │
├──────────────────────────────────┤
│ COST BY PROVIDER                 │
│ Claude Code:           $23.07 [E]│
│   Sonnet 4:    $21.30           │
│   Haiku 4.5:    $1.77           │
├──────────────────────────────────┤
│ [E] = Exact   [~] = Estimated   │
│ [Open Folder]                    │
└──────────────────────────────────┘
```

## Installation

### Requirements
- Python 3.10+
- PySide6
- Windows 10/11, macOS 12+, or Linux (with system tray support)

### Setup

```bash
git clone https://github.com/erickopgaming28/ai-token-monitor.git
cd ai-token-monitor
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

On Windows, you can also double-click `start.bat` to launch in background (no console window).

### Auto-start

Open the app → Right-click tray icon → Settings → Check "Start with system" → Save.

- **Windows**: Adds to registry Run key
- **macOS**: Creates a LaunchAgent plist

## Supported Providers

| Provider | Detection | Token Source | Pricing |
|----------|-----------|-------------|---------|
| Claude Code | CLI + logs | JSONL session logs (`~/.claude/projects/`) | Built-in + API |
| OpenAI / Codex | CLI + config | Adapter ready | Built-in + API |
| Gemini CLI | CLI | Adapter ready | Built-in |
| DeepSeek | — | Adapter ready | Built-in |
| Qwen | — | Free models ($0.00) | Built-in |
| Mistral | — | Adapter ready | Built-in |
| GitHub Copilot | `gh` extension | Adapter ready | — |
| Cursor | App + config | Adapter ready | — |
| Aider | CLI | Adapter ready | — |
| Continue | Config dir | Adapter ready | — |
| **Custom** | User-defined | User-defined | User-defined |

### Adding Custom Providers

Go to Settings → Custom Models tab to add any provider or model not listed above.

## Default Pricing (USD per million tokens)

| Model | Input | Output | Cache Read | Cache Write |
|-------|------:|-------:|-----------:|------------:|
| Claude Opus 4 | $15.00 | $75.00 | $1.50 | $18.75 |
| Claude Sonnet 4 | $3.00 | $15.00 | $0.30 | $3.75 |
| Claude Haiku 4.5 | $1.00 | $5.00 | $0.10 | $1.25 |
| GPT-4o | $2.50 | $10.00 | $1.25 | — |
| GPT-4.1 | $2.00 | $8.00 | $0.50 | — |
| Gemini 2.5 Pro | $1.25 | $10.00 | — | — |
| DeepSeek V3 | $0.27 | $1.10 | $0.07 | — |
| DeepSeek R1 | $0.55 | $2.19 | $0.14 | — |
| Qwen3 235B | $0.00 | $0.00 | — | — |
| Mistral Large | $2.00 | $6.00 | — | — |
| Codestral | $0.30 | $0.90 | — | — |

All prices are editable in Settings → Pricing tab. Click "Update Prices from APIs" to fetch the latest rates.

## Project Structure

```
ai-token-monitor/
├── main.py                 # Entry point
├── start.bat               # Launch without console (Windows)
├── core/
│   ├── scanner.py          # File watcher + periodic scanner
│   ├── event_bus.py        # Qt signal-based event system
│   ├── aggregator.py       # Daily rollup queries
│   ├── cost_engine.py      # Cost calculation engine
│   ├── ai_detector.py      # Auto-detect installed AI tools
│   └── pricing_fetcher.py  # Live pricing from provider APIs
├── providers/
│   ├── base.py             # Abstract adapter + TokenEvent
│   ├── claude_code.py      # Claude Code JSONL parser
│   ├── openai_adapter.py   # OpenAI placeholder
│   └── gemini_adapter.py   # Gemini placeholder
├── db/
│   └── database.py         # SQLite manager (8 tables)
├── ui/
│   ├── tray.py             # System tray icon
│   ├── popup.py            # Main popup panel
│   ├── project_card.py     # Project summary widget
│   ├── detail_panel.py     # Expanded project view
│   ├── token_bar.py        # Input/output bar widget
│   ├── settings_dialog.py  # Settings window (4 tabs)
│   └── styles.py           # Dark theme (Catppuccin)
└── config/
    ├── settings.py         # App configuration
    └── default_pricing.json # 10 providers, 25+ models
```

## Contributing

Pull requests are welcome. To add a new AI provider:

1. Create a new adapter in `providers/` extending `ProviderAdapter`
2. Implement `discover_files()` and `parse_file()`
3. Add default pricing in `config/default_pricing.json`
4. Add a detector in `core/ai_detector.py`
5. Enable it in `main.py`

## Support the Project

If you find this tool useful, consider supporting its development:

<p align="center">
  <a href="https://buymeacoffee.com/erickgio">
    <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="200">
  </a>
</p>

## License

MIT License — see [LICENSE](LICENSE) for details.
