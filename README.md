# AI Crypto Predictor

Local crypto contract simulation and AI prediction dashboard.

This project fetches crypto market data, asks an AI model for simulated contract predictions, records results in SQLite, and provides a Flask dashboard for manual prediction, scheduled auto tasks, paper/live execution records, validation, advice, charts, i18n, and sentiment input.

> This is a simulation and research tool. It is not financial advice.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
python main.py init-db
python main.py web --debug
```

Open the dashboard at:

```text
http://127.0.0.1:8000
```

For normal local development, use `--debug`. Flask will restart when Python files change. Template and static files are configured to avoid browser caching, so a browser refresh should show frontend changes.

## Project Name

- Python package name: `crypto_predictor`
- Python distribution name: `ai-crypto`
- CLI entrypoint after package install: `ai-crypto`
- Compatibility entrypoint: `python main.py ...`

The package name `crypto_predictor` follows Python naming conventions. The root folder name can be anything, but the project metadata uses the normalized distribution name `ai-crypto`.

## Common Commands

```powershell
python main.py web --debug
python main.py predict --symbol BTC/USDT --timeframe 1h --limit 24
python main.py predict --all-symbols
python main.py check
python main.py stats
python main.py auto-run --interval-seconds 3600 --all-symbols
python main.py list-symbols
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill local secrets.

Important sections:

- `providers.openai`: OpenAI or OpenAI-compatible API settings.
- `exchange`: public market-data exchange settings and proxy options.
- `crypto`: symbols, default timeframe, candidate timeframes, Kline limit.
- `contract`: simulated contract assumptions.
- `trading`: paper/live execution controls.
- `risk`: max margin, leverage, and allowed symbols.
- `sentiment`: Crypto Fear & Greed Index integration.
- `web`: host, port, debug, refresh interval, timezone.
- `automation`: default auto-task behavior.

Database backend settings:

```yaml
database:
  backend: "sqlite"
  path: "crypto_predictions.sqlite3"
  postgres_dsn: ""
```

`sqlite` is the current working repository implementation. `postgresql` is exposed as a backend boundary so the persistence layer can be replaced without changing prediction, web, or broker modules.

Repository boundary:

```python
from crypto_predictor.repositories import get_repository

repo = get_repository()
repo.init_schema()
```

For PostgreSQL schema creation on an empty database:

```powershell
python -m pip install "psycopg[binary]>=3.1"
```

```yaml
database:
  backend: "postgresql"
  postgres_dsn: "postgresql://user:password@localhost:5432/aicrypto"
```

Then run:

```powershell
python main.py init-db
```

PostgreSQL `init_schema()` is implemented. The app still uses the SQLite repository for runtime read/write methods until the remaining SQL methods are ported.

Market data resilience settings:

```yaml
crypto:
  market_data_cache_ttl_seconds: 5
  market_data_retry_attempts: 3
  market_data_retry_initial_delay_seconds: 0.5
```

`config.yaml` is intentionally ignored by Git because it can contain API keys.

## Features

- Manual AI prediction from market OHLCV data.
- Scheduled auto prediction and optional paper/live execution.
- Web auto tasks run serially by default; the dashboard can enable overlap so a new cycle starts on schedule even if the previous cycle is still running.
- Server-side pagination for prediction records and auto task logs.
- SQLite persistence for predictions, orders, auto logs, and advice actions.
- Accuracy validation after prediction expiry.
- Paper trading records and guarded live execution.
- Crypto Fear & Greed Index as an auxiliary sentiment input.
- Chinese and English dashboard i18n.
- Dashboard charts powered by ECharts.
- Chart date-range filtering converts the selected dashboard timezone dates to UTC query bounds.
- Local timezone rendering while storing timestamps in UTC.

## Architecture

```text
main.py                         compatibility CLI entry
crypto_predictor/cli.py         command-line interface
crypto_predictor/web_app.py     Flask app and routes
crypto_predictor/service.py     prediction orchestration
crypto_predictor/market_data.py market data payload builder
crypto_predictor/sentiment.py   Fear & Greed Index provider
crypto_predictor/ai/            AI provider implementations
crypto_predictor/contract.py    simulated contract enrichment
crypto_predictor/database.py    SQLite persistence
crypto_predictor/auto_runner.py scheduled cycle logic
crypto_predictor/auto_task_manager.py web-controlled background task
crypto_predictor/broker/        paper/live execution and risk checks
crypto_predictor/infrastructure/replaceable cache, retry, queue, status, db boundaries
crypto_predictor/backtesting.py backtest module boundary
crypto_predictor/model_evaluation.py multi-model evaluation helpers
crypto_predictor/templates/     Jinja templates
crypto_predictor/static/        CSS and JavaScript
```

## Replaceable Modules

The project now has explicit boundaries for future upgrades:

- Database backend: `crypto_predictor.infrastructure.database_backends`
- Repository interface: `crypto_predictor.repositories`
- Task queue: `crypto_predictor.infrastructure.task_queue`
- Market data cache: `crypto_predictor.infrastructure.cache`
- Retry policy: `crypto_predictor.infrastructure.retry`
- Observability events: `crypto_predictor.infrastructure.observability`
- Task status store: `crypto_predictor.infrastructure.task_status`
- Risk policy: `crypto_predictor.infrastructure.risk_policy`
- Backtesting: `crypto_predictor.backtesting`
- Multi-model evaluation: `crypto_predictor.model_evaluation`

Default implementations are intentionally local and lightweight. You can later swap individual modules for PostgreSQL, Redis, Celery/RQ, Prometheus, or a high-performance execution service without rewriting the whole application.

System status endpoint:

```text
GET /api/system-status
```

It reports the selected database backend and observable task states.

## Frontend Stack

- Flask + Jinja2 server-rendered templates.
- Plain CSS.
- Browser-native JavaScript ES modules.
- `fetch()` for partial dashboard refresh.
- ECharts for chart rendering.

No React/Vue build step is required.

## Development Notes

Use this while editing Python files:

```powershell
python main.py web --debug
```

Use this if you only edit templates, CSS, or JS and already have the server running:

```text
Refresh the browser page.
```

The Flask app disables static cache and enables template auto reload, so frontend/template changes should not require a server restart. Python module changes still require Flask debug reloader or a manual restart.

## Runtime Files

These are generated locally and ignored:

- `config.yaml`
- `crypto_predictions.sqlite3`
- `logs/`
- `web*.log`
- `web*.err`
- `__pycache__/`
- `_live_dashboard.html`

## Safety

Live execution is guarded by config and confirmation text. Keep `trading.enable_live_trading: false` unless you fully understand the broker path and account mode.

Market metadata cache:

- The Web app and CLI auto-run warm ccxt exchange markets once at startup.
- Scheduled cycles reuse the in-memory exchange instance, so hourly OHLCV fetches do not intentionally reload Binance exchangeInfo.


Sentiment and technical weighting:

- Crypto Fear & Greed Index is included as daily macro sentiment context when enabled.
- The prediction prompt treats Extreme Fear as risk-off by default, not a blind contrarian long signal.
- Short-term predictions lean primarily on OHLCV, RSI, and volume structure; sentiment is auxiliary context.


Prediction logging:

- Scheduled cycles log a clear start/end banner and cycle parameters.
- Binance/OHLCV failures are logged under the market stage with hints for rate limits, IP blocking, proxy, or network congestion.
- Fear & Greed failures are warnings only; the system degrades to pure OHLCV mode for that prediction.
- CLI auto-run records a failed cycle and continues to the next interval instead of exiting.

