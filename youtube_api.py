"""YouTube API module for fetching video information.

Contains pure functions for interacting with the YouTube Data API.

OPTIMIZATION: Uses playlistItems.list (1 quota unit) instead of search.list (100 quota units)
to significantly reduce API quota consumption. For each channel:
- channels.list: 1 unit (get uploads playlist ID)
- playlistItems.list: 1 unit (get videos from playlist)
Total: ~2 units per channel vs 100 units with search.list
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import TypedDict

import dateutil.parser
import googleapiclient.discovery
import googleapiclient.errors

logger = logging.getLogger(__name__)

# API constants
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# Default rate limiting delay between API calls (in seconds)
DEFAULT_API_DELAY = 1.0

# Maximum results per API request (YouTube API limit is 50)
MAX_RESULTS_LIMIT = 50
MIN_RESULTS_LIMIT = 1


class VideoInfo(TypedDict):
    """Type definition for video information."""

    id: str
    title: str
    channel_id: str
    published_at: datetime


def create_youtube_client(api_key: str):
    """Create a YouTube API client.

    This is the only function that creates the client -
    no module-level side effects.

    Args:
        api_key: YouTube Data API v3 key.

    Returns:
        YouTube API client resource.
    """
    return googleapiclient.discovery.build(
        API_SERVICE_NAME,
        API_VERSION,
        developerKey=api_key,
    )


def _validate_max_results(max_results: int) -> int:
    """Validate and clamp max_results to YouTube API limits.

    Args:
        max_results: Requested maximum results.

    Returns:
        Validated max_results within API limits (1-50).
    """
    if max_results < MIN_RESULTS_LIMIT:
        logger.warning(f"max_results {max_results} is below minimum, using {MIN_RESULTS_LIMIT}")
        return MIN_RESULTS_LIMIT
    if max_results > MAX_RESULTS_LIMIT:
        logger.warning(f"max_results {max_results} exceeds API limit, using {MAX_RESULTS_LIMIT}")
        return MAX_RESULTS_LIMIT
    return max_results


def _get_uploads_playlist_id(client, channel_id: str) -> str | None:
    """Get the uploads playlist ID for a channel.

    Every YouTube channel has an uploads playlist where all their videos are listed.
    The playlist ID is derived from the channel ID by replacing 'UC' with 'UU'.

    Args:
        client: YouTube API client.
        channel_id: YouTube channel ID.

    Returns:
        Uploads playlist ID, or None if not found.
    """
    # Optimization: uploads playlist ID can be derived from channel ID
    # Channel IDs start with 'UC', uploads playlists start with 'UU'
    if channel_id.startswith("UC"):
        return "UU" + channel_id[2:]

    # Fallback: query the API (costs 1 quota unit)
    try:
        request = client.channels().list(
            part="contentDetails",
            id=channel_id,
        )
        response = request.execute()

        items = response.get("items", [])
        if items:
            return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        return None

    except googleapiclient.errors.HttpError as e:
        logger.error(f"YouTube API error getting uploads playlist for {channel_id}: {e}")
        return None


def fetch_channel_videos(
    client,
    channel_id: str,
    since: datetime,
    max_results: int = 50,
    dry_run: bool = False,
) -> list[VideoInfo]:
    """Fetch videos from a channel published after a given date.

    Uses playlistItems.list API (1 quota unit) instead of search.list (100 quota units)
    for significant quota savings.

    Args:
        client: YouTube API client.
        channel_id: YouTube channel ID.
        since: Only return videos published after this datetime.
        max_results: Maximum number of videos to fetch (1-50, default 50).
        dry_run: If True, return mock data instead of calling the API.

    Returns:
        List of VideoInfo dictionaries for videos published after 'since'.
    """
    # Validate max_results
    max_results = _validate_max_results(max_results)

    # Dry run mode: return mock data without calling the API
    if dry_run:
        mock_count = int(os.getenv("DRY_RUN_MOCK_VIDEO_COUNT", "2"))
        mock_videos = _create_mock_videos(channel_id, since, count=mock_count)
        logger.info(f"[DRY RUN] Channel {channel_id}: returning {len(mock_videos)} mock videos")
        return mock_videos

    try:
        # Get uploads playlist ID (usually derived, no API call needed)
        playlist_id = _get_uploads_playlist_id(client, channel_id)
        if not playlist_id:
            logger.warning(f"Could not find uploads playlist for channel {channel_id}")
            return []

        # Fetch videos from uploads playlist (1 quota unit)
        request = client.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=max_results,
        )
        response = request.execute()

        videos = _parse_playlist_response(response, channel_id, since)
        logger.debug(f"Channel {channel_id}: found {len(videos)} videos since {since}")
        return videos

    except googleapiclient.errors.HttpError as e:
        logger.error(f"YouTube API error for channel {channel_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching videos for channel {channel_id}: {e}")
        return []


def fetch_all_channels_videos(
    client,
    channel_ids: tuple[str, ...],
    since: datetime,
    dry_run: bool = False,
    api_delay: float | None = None,
) -> list[VideoInfo]:
    """Fetch videos from multiple channels with rate limiting.

    Args:
        client: YouTube API client.
        channel_ids: Tuple of channel IDs to fetch from.
        since: Only return videos published after this datetime.
        dry_run: If True, return mock data instead of calling the API.
        api_delay: Delay between API calls in seconds (default from env or 1.0).

    Returns:
        Combined list of videos from all channels, sorted by publish date (newest first).
    """
    all_videos: list[VideoInfo] = []

    # Get delay from environment or use default
    if api_delay is None:
        api_delay = float(os.getenv("API_RATE_LIMIT_DELAY", str(DEFAULT_API_DELAY)))

    for i, channel_id in enumerate(channel_ids):
        # Rate limiting: add delay between channel requests (skip first)
        if i > 0 and not dry_run and api_delay > 0:
            logger.debug(f"Rate limiting: waiting {api_delay}s before next API call")
            time.sleep(api_delay)

        videos = fetch_channel_videos(client, channel_id, since, dry_run=dry_run)
        all_videos.extend(videos)

    # Sort by publish date, newest first
    all_videos.sort(key=lambda v: v["published_at"], reverse=True)

    logger.info(f"Found {len(all_videos)} total videos from {len(channel_ids)} channels")
    return all_videos


def _parse_playlist_response(response: dict, channel_id: str, since: datetime) -> list[VideoInfo]:
    """Parse YouTube playlistItems API response into VideoInfo list.

    Args:
        response: Raw API response dictionary.
        channel_id: The channel ID these videos are from.
        since: Only include videos published after this datetime.

    Returns:
        List of VideoInfo dictionaries.
    """
    videos: list[VideoInfo] = []

    items = response.get("items", [])
    for item in items:
        try:
            # Get video ID from contentDetails
            video_id = item["contentDetails"]["videoId"]
            snippet = item["snippet"]
            title = snippet["title"]

            # Parse published date - use videoPublishedAt from contentDetails if available
            published_str = item["contentDetails"].get(
                "videoPublishedAt", snippet.get("publishedAt")
            )
            if not published_str:
                logger.warning(f"No publish date for video {video_id}, skipping")
                continue

            published_at = dateutil.parser.isoparse(published_str)

            # Filter by date
            if published_at < since:
                continue

            videos.append(
                {
                    "id": video_id,
                    "title": title,
                    "channel_id": channel_id,
                    "published_at": published_at,
                }
            )
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse video from response: {e}")
            continue

    return videos


def _create_mock_videos(channel_id: str, since: datetime, count: int = 2) -> list[VideoInfo]:
    """Create mock video data for dry run testing.

    Args:
        channel_id: YouTube channel ID.
        since: Base date for mock videos.
        count: Number of mock videos to create (configurable via DRY_RUN_MOCK_VIDEO_COUNT).

    Returns:
        List of mock VideoInfo dictionaries.
    """
    mock_videos: list[VideoInfo] = []

    for i in range(count):
        # Create videos at different times after 'since'
        published_at = since + timedelta(hours=12 * (i + 1))
        video_id = f"MOCK{channel_id[:8]}{i:02d}"

        mock_videos.append(
            {
                "id": video_id,
                "title": f"[DRY RUN] Mock Video {i + 1} from Channel {channel_id[:8]}",
                "channel_id": channel_id,
                "published_at": published_at,
            }
        )

    return mock_videos
