# -*- coding: utf-8 -*-
"""YouTube API module for fetching video information.

Contains pure functions for interacting with the YouTube Data API.
"""

import logging
from datetime import datetime
from typing import TypedDict

import dateutil.parser
import googleapiclient.discovery
import googleapiclient.errors

logger = logging.getLogger(__name__)

# API constants
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"


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


def fetch_channel_videos(
    client,
    channel_id: str,
    since: datetime,
    max_results: int = 50,
    dry_run: bool = False,
) -> list[VideoInfo]:
    """Fetch videos from a channel published after a given date.

    This is a pure function with respect to the client -
    it doesn't modify any state.

    Args:
        client: YouTube API client.
        channel_id: YouTube channel ID.
        since: Only return videos published after this datetime.
        max_results: Maximum number of videos to fetch (default 50).
        dry_run: If True, return mock data instead of calling the API.

    Returns:
        List of VideoInfo dictionaries for videos published after 'since'.
    """
    # Dry run mode: return mock data without calling the API
    if dry_run:
        mock_videos = _create_mock_videos(channel_id, since)
        logger.info(
            f"[DRY RUN] Channel {channel_id}: returning {len(mock_videos)} mock videos"
        )
        return mock_videos

    try:
        # Format the publishedAfter parameter for the API
        published_after = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        request = client.search().list(
            part="snippet",
            channelId=channel_id,
            publishedAfter=published_after,
            maxResults=max_results,
            order="date",
            type="video",
        )
        response = request.execute()

        videos = _parse_video_response(response, channel_id)
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
) -> list[VideoInfo]:
    """Fetch videos from multiple channels.

    Args:
        client: YouTube API client.
        channel_ids: Tuple of channel IDs to fetch from.
        since: Only return videos published after this datetime.
        dry_run: If True, return mock data instead of calling the API.

    Returns:
        Combined list of videos from all channels, sorted by publish date (newest first).
    """
    all_videos: list[VideoInfo] = []

    for channel_id in channel_ids:
        videos = fetch_channel_videos(client, channel_id, since, dry_run=dry_run)
        all_videos.extend(videos)

    # Sort by publish date, newest first
    all_videos.sort(key=lambda v: v["published_at"], reverse=True)

    logger.info(
        f"Found {len(all_videos)} total videos from {len(channel_ids)} channels"
    )
    return all_videos


def _parse_video_response(response: dict, channel_id: str) -> list[VideoInfo]:
    """Parse YouTube API response into VideoInfo list.

    Args:
        response: Raw API response dictionary.
        channel_id: The channel ID these videos are from.

    Returns:
        List of VideoInfo dictionaries.
    """
    videos: list[VideoInfo] = []

    items = response.get("items", [])
    for item in items:
        try:
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]
            title = snippet["title"]
            published_at = dateutil.parser.isoparse(snippet["publishedAt"])

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


def _create_mock_videos(channel_id: str, since: datetime) -> list[VideoInfo]:
    """Create mock video data for dry run testing.

    Args:
        channel_id: YouTube channel ID.
        since: Base date for mock videos.

    Returns:
        List of mock VideoInfo dictionaries.
    """
    from datetime import timedelta

    # Create 2-3 mock videos per channel for testing
    mock_videos: list[VideoInfo] = []

    for i in range(2):
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
