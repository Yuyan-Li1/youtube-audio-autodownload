# YouTube Audio Downloader

Automatically download audio from YouTube videos and move them to your podcast app. Designed to run as a cron job to keep your podcast library updated with new videos from your favorite YouTube channels.

## Features

- **Idempotent operation**: Safe to run multiple times - already downloaded videos are skipped
- **Automatic retry**: Failed downloads are retried on the next run
- **Lock file**: Prevents concurrent runs from cron
- **Download history**: Tracks what was downloaded and when
- **Configurable lookback**: Checks last N days for new videos (default: 7)
- **Smart filtering**: Automatically skips YouTube Shorts and live streams
- **Proper logging**: File-based logging for cron job debugging
- **SponsorBlock integration**: Optionally remove or mark sponsored segments, intros, outros, and more
- **API quota efficient**: Uses optimized API calls to minimize quota usage

## Installation

1. Clone or download this repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Install ffmpeg (required by yt-dlp):

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

4. Get a YouTube Data API v3 key from [Google Cloud Console](https://developers.google.com/youtube/v3/getting-started)

5. Create your configuration file:

```bash
cp .env.example .env
```

6. Edit `.env` with your settings:

```bash
YOUTUBE_API_KEY=your_api_key_here
TARGET_DIRECTORY=/path/to/your/podcast/sideloads
```

7. Create a `channel_ids` file with YouTube channel IDs (one per line):

```
UCxxxxxxxxxxxxxxxxxxxxxxx
UCyyyyyyyyyyyyyyyyyyyyyyy
```

To find a channel ID, use [this tool](https://commentpicker.com/youtube-channel-id.php) or check the channel's URL.

## Usage

### Manual Run

```bash
python3 audio_downloader.py
```

### Debug Mode

```bash
python3 audio_downloader.py -d
```

### Dry Run Mode

Test the script without consuming Google API quota:

```bash
python3 audio_downloader.py --dry-run
```

In dry run mode:

- Mock video data is used instead of calling the YouTube API
- Downloads and file operations work normally
- Perfect for testing configuration and downloads without using API quota

### Cron Job (Recommended)

To run twice daily at 9 AM and 9 PM:

```bash
crontab -e
```

Add this line:

```cron
0 9,21 * * * cd /path/to/youtube-audio-autodownload && /usr/bin/python3 audio_downloader.py >> /tmp/youtube_downloader.log 2>&1
```

Or if you have logging configured in `.env`:

```cron
0 9,21 * * * cd /path/to/youtube-audio-autodownload && /usr/bin/python3 audio_downloader.py
```

## Configuration

All configuration is done via environment variables. Create a `.env` file (copy from `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `YOUTUBE_API_KEY` | Yes | - | YouTube Data API v3 key |
| `TARGET_DIRECTORY` | Yes | - | Where to move completed downloads |
| `DOWNLOAD_DIRECTORY` | No | `./downloads/` | Temporary download location |
| `LOOKBACK_DAYS` | No | `7` | How many days back to check for new videos |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FILE` | No | - | File to write logs to |
| `SPONSORBLOCK_ENABLED` | No | `false` | Enable SponsorBlock segment removal/marking |
| `SPONSORBLOCK_CATEGORIES` | No | `sponsor,intro,...` | Comma-separated categories (or `all`) |
| `SPONSORBLOCK_ACTION` | No | `remove` | `remove` (cut segments) or `mark` (chapter markers) |

### Example for Castro (macOS)

```bash
TARGET_DIRECTORY=/Users/yourusername/Library/Mobile Documents/iCloud~co~supertop~castro/Documents/Sideloads
```

## How It Works

1. **Load configuration**: Reads all settings from `.env` and `channel_ids`
2. **Check history**: Loads `download_history.json` to see what's already downloaded
3. **Fetch videos**: Queries YouTube API for videos from the last N days
4. **Filter shorts and streams**: Automatically removes:
   - YouTube Shorts (videos ≤60 seconds)
   - Live streams (active, upcoming, and completed stream VODs)
5. **Filter downloaded**: Removes already downloaded videos from the list
6. **Download**: Downloads audio using yt-dlp
7. **Update history**: Records successful downloads
8. **Move files**: Moves audio files to the target directory

The download history ensures:

- Videos are never downloaded twice
- Failed downloads are automatically retried on the next run
- The script is safe to run at any frequency

### Filtering Details

**YouTube Shorts**: Videos with duration of 60 seconds or less are automatically skipped, as they're typically not suitable for podcast-style listening.

**Live Streams**: All live stream content is filtered out, including:

- Active live streams
- Upcoming scheduled streams
- Completed live stream VODs (past broadcasts)

If you want to include completed stream VODs, you can modify the detection logic in `youtube_api.py`.

**API Quota Impact**: The filtering feature uses the efficient `videos.list` API call (1 quota unit per 50 videos), keeping the total quota usage very low (~3 units per channel).

### SponsorBlock

When enabled (`SPONSORBLOCK_ENABLED=true`), the downloader uses yt-dlp's built-in SponsorBlock integration to automatically handle sponsored segments and other non-content sections in videos.

**Actions:**
- `remove` (default): Cuts sponsored segments out of the audio file entirely
- `mark`: Adds chapter markers around sponsored segments without removing them

**Categories** (default: `sponsor,intro,outro,selfpromo,interaction,poi_highlight`):
- `sponsor` - Paid promotions and sponsorship segments
- `intro` - Intermission/intro animations
- `outro` - End credits/outros
- `selfpromo` - Unpaid self-promotion (merch, Patreon, etc.)
- `interaction` - Subscribe reminders, like/comment prompts
- `poi_highlight` - Highlight/key moment
- `filler` - Tangential filler content
- `music_offtopic` - Non-music section in music videos
- `preview` - Preview/recap of other content

Use `SPONSORBLOCK_CATEGORIES=all` to process all categories. SponsorBlock data is crowdsourced, so not all videos will have segments marked.

## Files

| File | Purpose |
|------|---------|
| `audio_downloader.py` | Main entry point |
| `config.py` | Configuration loading |
| `youtube_api.py` | YouTube API interactions |
| `downloader.py` | Audio downloading with yt-dlp |
| `file_ops.py` | File moving operations |
| `history.py` | Download history management |
| `lock.py` | Lock file for preventing concurrent runs |
| `channel_ids` | List of YouTube channel IDs to monitor |
| `download_history.json` | Record of downloaded videos (auto-generated) |
| `.env` | Your configuration (create from `.env.example`) |

## Migrating from Old Version

If you were using the old version with `API_key` file and `last_download_time`:

1. Move your API key to `.env`:

   ```bash
   echo "YOUTUBE_API_KEY=$(cat API_key)" >> .env
   ```

2. Set your target directory in `.env`

3. The old `last_download_time`, `last_download_date`, and `last_downloaded` files can be deleted

4. On first run, videos from the last 7 days will be downloaded and history will be built

## Dependencies

- Python 3.10+
- ffmpeg
- yt-dlp
- google-api-python-client
- python-dotenv
- python-dateutil

See `requirements.txt` for full list.

## Troubleshooting

### Cron job not working

1. Enable file logging in `.env`:

   ```
   LOG_FILE=./logs/downloader.log
   LOG_LEVEL=DEBUG
   ```

2. Check the log file for errors

3. Make sure the cron command uses absolute paths

### Downloads fail

- Check if yt-dlp is up to date: `pip install -U yt-dlp`
- Some videos may be region-locked or private
- Check the error message in the logs

### API quota exceeded

- YouTube API has daily quotas (default: 10,000 units per day)
- This script uses ~3 quota units per channel:
  - channels.list: 1 unit (get uploads playlist ID, usually cached)
  - playlistItems.list: 1 unit (get videos from playlist)
  - videos.list: 1 unit per batch of up to 50 videos (for shorts/stream filtering)
- Reduce `LOOKBACK_DAYS` if you're checking too many days
- Reduce the number of channels you're monitoring
- Use `--dry-run` mode for testing without consuming quota

## License

MIT License - see [LICENSE](LICENSE) file.
