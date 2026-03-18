# AI Token Monitor

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PySide6-Qt-green?logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="License">
</p>

**AI Token Monitor** is a lightweight Windows system tray application that automatically detects, tracks, and visualizes AI token consumption across your local projects.

It monitors tools like **Claude Code**, **OpenAI**, and **Gemini**, showing input/output token breakdowns and estimated costs per project — all running silently in the background.

<p align="center">
  <a href="https://buymeacoffee.com/erickgio">
    <img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Buy Me A Coffee">
  </a>
</p>

---

## Features

- **System Tray App** — Lives next to your clock, zero distraction
- **Auto-detection** — Finds active AI projects by scanning Claude Code JSONL session logs
- **Per-project tracking** — Input tokens, output tokens, cache read/write tokens
- **Cost estimation** — Configurable pricing per model/provider (USD per million tokens)
- **Visual breakdown** — Color-coded bars showing input vs output proportion
- **Detail view** — Click any project for full cost breakdown by provider, model, and day
- **Multi-provider ready** — Claude Code (fully working), OpenAI & Gemini (adapter placeholders)
- **Dark theme** — Catppuccin Mocha inspired UI
- **Settings panel** — Edit pricing, scan intervals, auto-start with Windows
- **Local & private** — All data stays on your machine in a local SQLite database

## How It Works

```
Claude Code JSONL logs  ──►  Scanner (FileWatcher + Polling)
                                    │
                              Token Parser (dedup by message_id)
                                    │
                              SQLite Database
                                    │
                         ┌──────────┴──────────┐
                    Cost Engine          Aggregator
                         └──────────┬──────────┘
                                    │
                            System Tray UI
```

1. **Scanner** watches `~/.claude/projects/` for new/modified JSONL files
2. **Parser** extracts token usage from assistant messages (only final responses, not streaming chunks)
3. **Database** stores events with deduplication via unique `message_id`
4. **Cost Engine** calculates costs using configurable per-model pricing
5. **Aggregator** pre-computes daily rollups for fast UI queries
6. **Tray UI** shows a compact popup with project list, token bars, and costs

## Screenshots

### Popup Panel
```
┌──────────────────────────────────┐
│ AI Token Monitor   [All Time ▼]  │
│ $321.78                          │
│ 12 projects                      │
├──────────────────────────────────┤
│ botones_mando_juego      $123.07 │
│ 372.4K tokens                    │
│ [█ IN █████████████ OUT ████████]│
│ IN: 3.8K  OUT: 368.6K           │
├──────────────────────────────────┤
│ bolt_twitch              $110.78 │
│ 269.1K tokens                    │
│ [█ IN ████████████ OUT █████████]│
│ IN: 8.1K  OUT: 261.0K           │
└──────────────────────────────────┘
```

### Detail View
```
┌──────────────────────────────────┐
│ <- Back                          │
│ PROJECT: botones_mando_juego     │
│ Path: C:/Users/.../proyecto      │
│ Last activity: 2m ago            │
├──────────────────────────────────┤
│ TOKENS        IN         OUT     │
│ Input:       3,782               │
│ Output:    368,648               │
│ Cache read: 39,587,440           │
│ Cache write: 2,537,338           │
├──────────────────────────────────┤
│ COST BY PROVIDER                 │
│ Claude Code:          $123.07 [E]│
│   Sonnet 4:   $120.50           │
│   Haiku 4.5:    $2.57           │
├──────────────────────────────────┤
│ [E] = Exact   [~] = Estimated   │
│ [Open Folder]                    │
└──────────────────────────────────┘
```

## Installation

### Requirements
- Windows 10/11
- Python 3.10+
- PySide6

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

Or double-click `start.bat` to launch in background (no console window).

### Auto-start with Windows

Open the app → Right-click tray icon → Settings → Check "Start with Windows" → Save.

## Default Pricing (USD per million tokens)

| Model | Input | Output | Cache Read | Cache Write |
|-------|------:|-------:|-----------:|------------:|
| Claude Opus 4 | $15.00 | $75.00 | $1.50 | $18.75 |
| Claude Sonnet 4 | $3.00 | $15.00 | $0.30 | $3.75 |
| Claude Haiku 4.5 | $1.00 | $5.00 | $0.10 | $1.25 |
| GPT-4o | $2.50 | $10.00 | — | — |
| GPT-4o mini | $0.15 | $0.60 | — | — |
| Gemini 2.5 Pro | $1.25 | $10.00 | — | — |
| Gemini 2.5 Flash | $0.15 | $0.60 | — | — |

All prices are editable in Settings → Pricing tab.

## Project Structure

```
ai-token-monitor/
├── main.py                 # Entry point
├── start.bat               # Launch without console
├── core/
│   ├── scanner.py          # File watcher + periodic scanner
│   ├── event_bus.py        # Qt signal-based event system
│   ├── aggregator.py       # Daily rollup queries
│   └── cost_engine.py      # Cost calculation engine
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
│   ├── settings_dialog.py  # Settings window
│   └── styles.py           # Dark theme (Catppuccin)
└── config/
    ├── settings.py         # App configuration
    └── default_pricing.json
```

## Data Sources

| Provider | Status | Source |
|----------|--------|--------|
| Claude Code | **Working** | JSONL session logs (`~/.claude/projects/`) |
| OpenAI | Placeholder | Adapter ready for future CLI/log integration |
| Gemini | Placeholder | Adapter ready for future CLI/log integration |

## Contributing

Pull requests are welcome. To add a new AI provider:

1. Create a new adapter in `providers/` extending `ProviderAdapter`
2. Implement `discover_files()` and `parse_file()`
3. Add default pricing in `config/default_pricing.json`
4. Enable it in `main.py`

## Support the Project

If you find this tool useful, consider supporting its development:

<p align="center">
  <a href="https://buymeacoffee.com/erickgio">
    <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="200">
  </a>
</p>

## License

MIT License — see [LICENSE](LICENSE) for details.
