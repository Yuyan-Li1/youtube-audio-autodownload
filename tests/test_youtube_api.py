"""Tests for youtube_api module."""

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import googleapiclient.errors

from youtube_api import (
    _create_mock_videos,
    _get_uploads_playlist_id,
    _parse_iso8601_duration,
    _parse_playlist_response,
    _validate_max_results,
    create_youtube_client,
    fetch_all_channels_videos,
    fetch_channel_videos,
    fetch_video_details,
    filter_shorts_and_streams,
)


class TestValidateMaxResults:
    """Tests for _validate_max_results function."""

    def test_valid_value_unchanged(self) -> None:
        """Test that valid values pass through unchanged."""
        assert _validate_max_results(25) == 25
        assert _validate_max_results(1) == 1
        assert _validate_max_results(50) == 50

    def test_below_minimum_clamped(self) -> None:
        """Test that values below minimum are clamped."""
        assert _validate_max_results(0) == 1
        assert _validate_max_results(-5) == 1

    def test_above_maximum_clamped(self) -> None:
        """Test that values above maximum are clamped."""
        assert _validate_max_results(100) == 50
        assert _validate_max_results(51) == 50


class TestGetUploadsPlaylistId:
    """Tests for _get_uploads_playlist_id function."""

    def test_derives_playlist_from_channel_id(self) -> None:
        """Test that playlist ID is derived from UC channel ID."""
        client = MagicMock()
        result = _get_uploads_playlist_id(client, "UCtest123456")
        assert result == "UUtest123456"
        # Verify no API call was made
        client.channels.assert_not_called()

    def test_api_fallback_for_non_uc_channel(self) -> None:
        """Test API fallback for non-UC channel IDs."""
        client = MagicMock()
        client.channels().list().execute.return_value = {
            "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUfallback123"}}}]
        }

        result = _get_uploads_playlist_id(client, "NON_UC_CHANNEL")
        assert result == "UUfallback123"

    def test_api_fallback_no_items(self) -> None:
        """Test API fallback returns None when no items."""
        client = MagicMock()
        client.channels().list().execute.return_value = {"items": []}

        result = _get_uploads_playlist_id(client, "NON_UC_CHANNEL")
        assert result is None

    def test_api_error_returns_none(self) -> None:
        """Test that API errors return None."""
        client = MagicMock()
        client.channels().list().execute.side_effect = googleapiclient.errors.HttpError(
            resp=MagicMock(status=403), content=b"Quota exceeded"
        )

        result = _get_uploads_playlist_id(client, "NON_UC_CHANNEL")
        assert result is None


class TestParsePlaylistResponse:
    """Tests for _parse_playlist_response function."""

    def test_parses_valid_response(self) -> None:
        """Test parsing a valid API response."""
        since = datetime(2024, 1, 1, tzinfo=UTC)
        response = {
            "items": [
                {
                    "contentDetails": {
                        "videoId": "vid123",
                        "videoPublishedAt": "2024-01-15T12:00:00Z",
                    },
                    "snippet": {
                        "title": "Test Video",
                        "publishedAt": "2024-01-15T12:00:00Z",
                    },
                }
            ]
        }

        result = _parse_playlist_response(response, "UCtest", since)
        assert len(result) == 1
        assert result[0]["id"] == "vid123"
        assert result[0]["title"] == "Test Video"
        assert result[0]["channel_id"] == "UCtest"

    def test_filters_by_date(self) -> None:
        """Test that videos before 'since' date are filtered out."""
        since = datetime(2024, 1, 10, tzinfo=UTC)
        response = {
            "items": [
                {
                    "contentDetails": {
                        "videoId": "vid_new",
                        "videoPublishedAt": "2024-01-15T12:00:00Z",
                    },
                    "snippet": {"title": "New Video"},
                },
                {
                    "contentDetails": {
                        "videoId": "vid_old",
                        "videoPublishedAt": "2024-01-05T12:00:00Z",
                    },
                    "snippet": {"title": "Old Video"},
                },
            ]
        }

        result = _parse_playlist_response(response, "UCtest", since)
        assert len(result) == 1
        assert result[0]["id"] == "vid_new"

    def test_handles_missing_publish_date(self) -> None:
        """Test that videos without publish dates are skipped."""
        since = datetime(2024, 1, 1, tzinfo=UTC)
        response = {
            "items": [
                {
                    "contentDetails": {"videoId": "vid_no_date"},
                    "snippet": {"title": "No Date Video"},
                }
            ]
        }

        result = _parse_playlist_response(response, "UCtest", since)
        assert len(result) == 0

    def test_handles_parse_errors(self) -> None:
        """Test that parse errors are handled gracefully."""
        since = datetime(2024, 1, 1, tzinfo=UTC)
        response = {
            "items": [
                {"contentDetails": {}},  # Missing videoId
                {
                    "contentDetails": {
                        "videoId": "vid_valid",
                        "videoPublishedAt": "2024-01-15T12:00:00Z",
                    },
                    "snippet": {"title": "Valid Video"},
                },
            ]
        }

        result = _parse_playlist_response(response, "UCtest", since)
        assert len(result) == 1
        assert result[0]["id"] == "vid_valid"


class TestCreateMockVideos:
    """Tests for _create_mock_videos function."""

    def test_creates_correct_count(self) -> None:
        """Test that correct number of mock videos are created."""
        since = datetime(2024, 1, 1, tzinfo=UTC)
        result = _create_mock_videos("UCtest123", since, count=3)
        assert len(result) == 3

    def test_mock_video_structure(self) -> None:
        """Test that mock videos have correct structure."""
        since = datetime(2024, 1, 1, tzinfo=UTC)
        result = _create_mock_videos("UCtest123", since, count=1)

        assert "id" in result[0]
        assert "title" in result[0]
        assert "channel_id" in result[0]
        assert "published_at" in result[0]
        assert result[0]["channel_id"] == "UCtest123"

    def test_published_dates_after_since(self) -> None:
        """Test that published dates are after 'since'."""
        since = datetime(2024, 1, 1, tzinfo=UTC)
        result = _create_mock_videos("UCtest123", since, count=2)

        for video in result:
            assert video["published_at"] > since


class TestFetchChannelVideos:
    """Tests for fetch_channel_videos function."""

    def test_dry_run_returns_mock_videos(self) -> None:
        """Test that dry run mode returns mock videos."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        with patch.dict(os.environ, {"DRY_RUN_MOCK_VIDEO_COUNT": "3"}):
            result = fetch_channel_videos(client, "UCtest", since, dry_run=True)

        assert len(result) == 3
        # Verify no API calls were made
        client.playlistItems.assert_not_called()

    def test_fetches_from_api(self) -> None:
        """Test that videos are fetched from API."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        client.playlistItems().list().execute.return_value = {
            "items": [
                {
                    "contentDetails": {
                        "videoId": "vid123",
                        "videoPublishedAt": "2024-01-15T12:00:00Z",
                    },
                    "snippet": {"title": "Test Video"},
                }
            ]
        }

        result = fetch_channel_videos(client, "UCtest", since, dry_run=False)
        assert len(result) == 1
        assert result[0]["id"] == "vid123"

    def test_handles_api_error(self) -> None:
        """Test that API errors are handled gracefully."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        client.playlistItems().list().execute.side_effect = googleapiclient.errors.HttpError(
            resp=MagicMock(status=403), content=b"Quota exceeded"
        )

        result = fetch_channel_videos(client, "UCtest", since, dry_run=False)
        assert not result

    def test_handles_generic_error(self) -> None:
        """Test that generic errors are handled gracefully."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        client.playlistItems().list().execute.side_effect = Exception("Network error")

        result = fetch_channel_videos(client, "UCtest", since, dry_run=False)
        assert not result

    def test_no_playlist_returns_empty(self) -> None:
        """Test that no playlist ID returns empty list."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        with patch("youtube_api._get_uploads_playlist_id", return_value=None):
            result = fetch_channel_videos(client, "NON_UC", since, dry_run=False)

        assert not result


class TestFetchAllChannelsVideos:
    """Tests for fetch_all_channels_videos function."""

    def test_fetches_from_multiple_channels(self) -> None:
        """Test fetching from multiple channels."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        with patch("youtube_api.fetch_channel_videos") as mock_fetch:
            mock_fetch.side_effect = [
                [
                    {
                        "id": "vid1",
                        "title": "Video 1",
                        "channel_id": "UC1",
                        "published_at": datetime(2024, 1, 15, tzinfo=UTC),
                    }
                ],
                [
                    {
                        "id": "vid2",
                        "title": "Video 2",
                        "channel_id": "UC2",
                        "published_at": datetime(2024, 1, 14, tzinfo=UTC),
                    }
                ],
            ]

            result = fetch_all_channels_videos(
                client, ("UC1", "UC2"), since, dry_run=True, api_delay=0
            )

        assert len(result) == 2
        # Should be sorted by date, newest first
        assert result[0]["id"] == "vid1"
        assert result[1]["id"] == "vid2"

    def test_rate_limiting_applied(self) -> None:
        """Test that rate limiting is applied between channels."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        with patch("youtube_api.fetch_channel_videos") as mock_fetch:
            mock_fetch.return_value = []
            with patch("time.sleep") as mock_sleep:
                fetch_all_channels_videos(
                    client, ("UC1", "UC2", "UC3"), since, dry_run=False, api_delay=0.5
                )

        # Should sleep between channels (not before first)
        assert mock_sleep.call_count == 2

    def test_no_rate_limiting_in_dry_run(self) -> None:
        """Test that rate limiting is skipped in dry run mode."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        with patch("youtube_api.fetch_channel_videos") as mock_fetch:
            mock_fetch.return_value = []
            with patch("time.sleep") as mock_sleep:
                fetch_all_channels_videos(
                    client, ("UC1", "UC2"), since, dry_run=True, api_delay=0.5
                )

        mock_sleep.assert_not_called()

    def test_empty_channels_returns_empty(self) -> None:
        """Test that empty channel list returns empty result."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        result = fetch_all_channels_videos(client, (), since, dry_run=True)
        assert not result


class TestCreateYoutubeClient:
    """Tests for create_youtube_client function."""

    def test_creates_client(self) -> None:
        """Test that client is created with correct parameters."""
        with patch("googleapiclient.discovery.build") as mock_build:
            mock_build.return_value = MagicMock()
            client = create_youtube_client("test_api_key")

        mock_build.assert_called_once_with("youtube", "v3", developerKey="test_api_key")
        assert client is not None


class TestParseISO8601Duration:
    """Tests for _parse_iso8601_duration function."""

    def test_parses_hours_minutes_seconds(self) -> None:
        """Test parsing duration with hours, minutes, and seconds."""
        assert _parse_iso8601_duration("PT1H30M15S") == 5415  # 1*3600 + 30*60 + 15

    def test_parses_seconds_only(self) -> None:
        """Test parsing duration with only seconds."""
        assert _parse_iso8601_duration("PT45S") == 45

    def test_parses_minutes_only(self) -> None:
        """Test parsing duration with only minutes."""
        assert _parse_iso8601_duration("PT1M") == 60

    def test_parses_hours_only(self) -> None:
        """Test parsing duration with only hours."""
        assert _parse_iso8601_duration("PT1H") == 3600

    def test_parses_zero_duration(self) -> None:
        """Test parsing zero duration."""
        assert _parse_iso8601_duration("PT0S") == 0

    def test_parses_hours_and_minutes(self) -> None:
        """Test parsing duration with hours and minutes."""
        assert _parse_iso8601_duration("PT2H30M") == 9000  # 2*3600 + 30*60

    def test_parses_minutes_and_seconds(self) -> None:
        """Test parsing duration with minutes and seconds."""
        assert _parse_iso8601_duration("PT5M30S") == 330  # 5*60 + 30

    def test_handles_malformed_duration(self) -> None:
        """Test that malformed durations return 0."""
        assert _parse_iso8601_duration("invalid") == 0
        assert _parse_iso8601_duration("") == 0
        assert _parse_iso8601_duration("PT") == 0

    def test_handles_days_component(self) -> None:
        """Test that days component is converted to hours."""
        # P1DT2H = 1 day + 2 hours = 26 hours
        assert _parse_iso8601_duration("P1DT2H") == 93600  # 26*3600

    def test_handles_days_with_full_time(self) -> None:
        """Test that days with full time components are parsed correctly."""
        # P1DT1H30M15S = 1 day + 1:30:15 = 25:30:15
        assert _parse_iso8601_duration("P1DT1H30M15S") == 91815  # 25*3600 + 30*60 + 15


class TestFetchVideoDetails:
    """Tests for fetch_video_details function."""

    def test_empty_input_returns_empty(self) -> None:
        """Test that empty input returns empty dictionary."""
        client = MagicMock()
        result = fetch_video_details(client, [])
        assert not result
        client.videos.assert_not_called()

    def test_fetches_video_details(self) -> None:
        """Test fetching video details from API."""
        client = MagicMock()
        client.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "vid123",
                    "contentDetails": {"duration": "PT10M30S"},
                    "snippet": {"liveBroadcastContent": "none"},
                }
            ]
        }

        result = fetch_video_details(client, ["vid123"])
        assert "vid123" in result
        assert result["vid123"]["duration_seconds"] == 630  # 10*60 + 30
        assert result["vid123"]["is_live"] is False

    def test_detects_live_streams(self) -> None:
        """Test detection of live streams."""
        client = MagicMock()
        client.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "live_vid",
                    "contentDetails": {"duration": "PT0S"},
                    "snippet": {"liveBroadcastContent": "live"},
                    "liveStreamingDetails": {},
                }
            ]
        }

        result = fetch_video_details(client, ["live_vid"])
        assert result["live_vid"]["is_live"] is True

    def test_detects_upcoming_streams(self) -> None:
        """Test detection of upcoming streams."""
        client = MagicMock()
        client.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "upcoming_vid",
                    "contentDetails": {"duration": "PT0S"},
                    "snippet": {"liveBroadcastContent": "upcoming"},
                    "liveStreamingDetails": {},
                }
            ]
        }

        result = fetch_video_details(client, ["upcoming_vid"])
        assert result["upcoming_vid"]["is_live"] is True

    def test_detects_completed_stream_vods(self) -> None:
        """Test detection of completed live stream VODs."""
        client = MagicMock()
        client.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "vod_vid",
                    "contentDetails": {"duration": "PT1H30M"},
                    "snippet": {"liveBroadcastContent": "none"},
                    "liveStreamingDetails": {},  # Has live details but not currently live
                }
            ]
        }

        result = fetch_video_details(client, ["vod_vid"])
        assert result["vod_vid"]["is_live"] is True  # Filters out completed stream VODs

    def test_detects_shorts(self) -> None:
        """Test detection of YouTube Shorts (<=60s)."""
        client = MagicMock()
        client.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "short_vid",
                    "contentDetails": {"duration": "PT45S"},
                    "snippet": {"liveBroadcastContent": "none"},
                }
            ]
        }

        result = fetch_video_details(client, ["short_vid"])
        assert result["short_vid"]["duration_seconds"] == 45
        assert result["short_vid"]["is_live"] is False

    def test_handles_api_error(self) -> None:
        """Test that API errors are handled gracefully."""

        client = MagicMock()
        client.videos().list().execute.side_effect = googleapiclient.errors.HttpError(
            resp=MagicMock(status=403), content=b"Quota exceeded"
        )

        result = fetch_video_details(client, ["vid123"])
        assert not result

    def test_handles_generic_error(self) -> None:
        """Test that generic errors are handled gracefully."""
        client = MagicMock()
        client.videos().list().execute.side_effect = Exception("Network error")

        result = fetch_video_details(client, ["vid123"])
        assert not result

    def test_batch_size_limit(self) -> None:
        """Test that only first 50 videos are processed."""
        client = MagicMock()
        client.videos().list().execute.return_value = {"items": []}

        # Create 60 video IDs
        video_ids = [f"vid{i}" for i in range(60)]
        fetch_video_details(client, video_ids)

        # Verify only first 50 were requested
        call_args = client.videos().list.call_args
        requested_ids = call_args[1]["id"].split(",")
        assert len(requested_ids) == 50

    def test_multiple_videos(self) -> None:
        """Test fetching details for multiple videos."""
        client = MagicMock()
        client.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "vid1",
                    "contentDetails": {"duration": "PT5M"},
                    "snippet": {"liveBroadcastContent": "none"},
                },
                {
                    "id": "vid2",
                    "contentDetails": {"duration": "PT30S"},
                    "snippet": {"liveBroadcastContent": "none"},
                },
            ]
        }

        result = fetch_video_details(client, ["vid1", "vid2"])
        assert len(result) == 2
        assert result["vid1"]["duration_seconds"] == 300
        assert result["vid2"]["duration_seconds"] == 30

    def test_missing_contentdetails(self) -> None:
        """Test handling of missing contentDetails."""
        client = MagicMock()
        client.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "vid_no_details",
                    "snippet": {"liveBroadcastContent": "none"},
                }
            ]
        }

        result = fetch_video_details(client, ["vid_no_details"])
        # Should handle missing duration gracefully
        assert "vid_no_details" in result
        assert result["vid_no_details"]["duration_seconds"] == 0


class TestFilterShortsAndStreams:
    """Tests for filter_shorts_and_streams function."""

    def test_empty_input_returns_empty(self) -> None:
        """Test that empty input returns empty list."""
        client = MagicMock()
        result = filter_shorts_and_streams(client, [])
        assert not result

    def test_dry_run_returns_all_videos(self) -> None:
        """Test that dry run mode returns all videos without filtering."""
        client = MagicMock()
        videos = [
            {
                "id": "vid1",
                "title": "Video 1",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            }
        ]

        result = filter_shorts_and_streams(client, videos, dry_run=True)
        assert result == videos
        client.videos.assert_not_called()

    def test_filters_out_shorts(self) -> None:
        """Test that shorts (<=60s) are filtered out."""
        client = MagicMock()
        videos = [
            {
                "id": "short1",
                "title": "Short Video",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            },
            {
                "id": "regular1",
                "title": "Regular Video",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            },
        ]

        with patch("youtube_api.fetch_video_details") as mock_fetch:
            mock_fetch.return_value = {
                "short1": {"duration_seconds": 45, "is_live": False},
                "regular1": {"duration_seconds": 300, "is_live": False},
            }

            result = filter_shorts_and_streams(client, videos, dry_run=False)

        assert len(result) == 1
        assert result[0]["id"] == "regular1"

    def test_filters_out_streams(self) -> None:
        """Test that live streams are filtered out."""
        client = MagicMock()
        videos = [
            {
                "id": "stream1",
                "title": "Live Stream",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            },
            {
                "id": "regular1",
                "title": "Regular Video",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            },
        ]

        with patch("youtube_api.fetch_video_details") as mock_fetch:
            mock_fetch.return_value = {
                "stream1": {"duration_seconds": 0, "is_live": True},
                "regular1": {"duration_seconds": 300, "is_live": False},
            }

            result = filter_shorts_and_streams(client, videos, dry_run=False)

        assert len(result) == 1
        assert result[0]["id"] == "regular1"

    def test_filters_both_shorts_and_streams(self) -> None:
        """Test filtering both shorts and streams together."""
        client = MagicMock()
        videos = [
            {
                "id": "short1",
                "title": "Short",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            },
            {
                "id": "stream1",
                "title": "Stream",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            },
            {
                "id": "regular1",
                "title": "Regular",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            },
        ]

        with patch("youtube_api.fetch_video_details") as mock_fetch:
            mock_fetch.return_value = {
                "short1": {"duration_seconds": 30, "is_live": False},
                "stream1": {"duration_seconds": 0, "is_live": True},
                "regular1": {"duration_seconds": 600, "is_live": False},
            }

            result = filter_shorts_and_streams(client, videos, dry_run=False)

        assert len(result) == 1
        assert result[0]["id"] == "regular1"

    def test_fail_open_when_details_unavailable(self) -> None:
        """Test fail-open behavior when video details cannot be fetched."""
        client = MagicMock()
        videos = [
            {
                "id": "vid_unknown",
                "title": "Unknown Video",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            }
        ]

        with patch("youtube_api.fetch_video_details") as mock_fetch:
            mock_fetch.return_value = {}  # No details available

            result = filter_shorts_and_streams(client, videos, dry_run=False)

        # Should include video when details are unavailable (fail open)
        assert len(result) == 1
        assert result[0]["id"] == "vid_unknown"

    def test_boundary_case_60_seconds(self) -> None:
        """Test boundary case: exactly 60 seconds (should be filtered as short)."""
        client = MagicMock()
        videos = [
            {
                "id": "boundary_vid",
                "title": "60 Second Video",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            }
        ]

        with patch("youtube_api.fetch_video_details") as mock_fetch:
            mock_fetch.return_value = {"boundary_vid": {"duration_seconds": 60, "is_live": False}}

            result = filter_shorts_and_streams(client, videos, dry_run=False)

        # 60 seconds should be filtered (<=60)
        assert len(result) == 0

    def test_boundary_case_61_seconds(self) -> None:
        """Test boundary case: 61 seconds (should NOT be filtered)."""
        client = MagicMock()
        videos = [
            {
                "id": "regular_vid",
                "title": "61 Second Video",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            }
        ]

        with patch("youtube_api.fetch_video_details") as mock_fetch:
            mock_fetch.return_value = {"regular_vid": {"duration_seconds": 61, "is_live": False}}

            result = filter_shorts_and_streams(client, videos, dry_run=False)

        # 61 seconds should NOT be filtered (>60)
        assert len(result) == 1

    def test_all_videos_filtered(self) -> None:
        """Test when all videos are filtered out."""
        client = MagicMock()
        videos = [
            {
                "id": "short1",
                "title": "Short 1",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            },
            {
                "id": "short2",
                "title": "Short 2",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            },
        ]

        with patch("youtube_api.fetch_video_details") as mock_fetch:
            mock_fetch.return_value = {
                "short1": {"duration_seconds": 30, "is_live": False},
                "short2": {"duration_seconds": 45, "is_live": False},
            }

            result = filter_shorts_and_streams(client, videos, dry_run=False)

        assert len(result) == 0
