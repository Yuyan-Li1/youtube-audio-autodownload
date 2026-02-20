# CLAUDE.md

## Project Overview

YouTube Audio Downloader - automatically downloads audio from YouTube channels and moves files to a podcast app directory (e.g., Castro sideloads). Designed for cron job execution.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for testing/linting

# Run the downloader
python3 audio_downloader.py
python3 audio_downloader.py -d          # debug logging
python3 audio_downloader.py --dry-run   # mock data, no API calls

# Tests
pytest                    # run all tests with coverage
pytest tests/test_config.py  # run a single test file
pytest -k "test_name"     # run a specific test

# Linting & formatting
ruff check .              # lint
ruff format --check .     # check formatting
ruff format .             # auto-format
mypy .                    # type checking
```

## Architecture

All source files are in the project root (no `src/` directory). Tests are in `tests/`.

| File | Purpose |
|------|---------|
| `audio_downloader.py` | Main entry point, orchestrates the pipeline |
| `config.py` | Configuration loading from env vars / `.env` file |
| `youtube_api.py` | YouTube Data API v3 client, video fetching, shorts/stream filtering |
| `downloader.py` | Audio downloading via yt-dlp with retry logic |
| `file_ops.py` | Moving downloaded files to the target directory |
| `history.py` | Download history tracking (JSON-based) |
| `lock.py` | Lock file to prevent concurrent runs |
| `chapters.py` | YouTube chapter embedding into audio files |
| `thumbnail.py` | YouTube thumbnail embedding into audio files |

## Data Flow

1. `config.py` loads all settings from `.env` + `channel_ids` file
2. `youtube_api.py` fetches recent videos, filters shorts/streams
3. `history.py` filters out already-downloaded videos
4. `downloader.py` downloads audio via yt-dlp, embeds thumbnails and chapters
5. `file_ops.py` moves completed files to the target directory

## Config Pattern

All configuration is loaded once at startup via `load_config()` into a frozen `Config` dataclass. Environment variables are read from `.env` via `python-dotenv`. New config fields require:
1. Add constant/default in `config.py`
2. Add field to `Config` dataclass
3. Add parsing/validation in `load_config()`
4. Add to `Config(...)` constructor call
5. Add to `.env.example` with documentation
6. Add tests in `tests/test_config.py`

## Testing Patterns

- Uses `pytest` with `unittest.mock` (patch, MagicMock)
- Tests are organized into classes per function/feature (`TestClassName`)
- External services are always mocked (YouTube API, yt-dlp, filesystem)
- Uses `tmp_path` fixture for filesystem tests
- `patch.dict(os.environ, ...)` for environment variable tests
- Coverage target: 80%+ (enforced by pytest config)

## Code Style

- Python 3.12+ (type hints use `X | Y` syntax, not `Optional`)
- Ruff for linting and formatting (line length: 100)
- Type annotations on function signatures
- Docstrings on all public functions (Google style)
- Frozen dataclasses for immutable data structures
- `tuple` for immutable sequences, `frozenset` for immutable sets in Config

## Important Notes

- Never commit `.env` or `API_key` files (contain secrets)
- `channel_ids` file has one YouTube channel ID per line
- yt-dlp and ffmpeg are runtime dependencies
- The `--dry-run` flag uses mock data to avoid consuming YouTube API quota
- Lock file prevents concurrent cron runs
