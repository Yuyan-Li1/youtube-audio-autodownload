"""Tests for youtube_api module."""

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from youtube_api import (
    _create_mock_videos,
    _get_uploads_playlist_id,
    _parse_playlist_response,
    _validate_max_results,
    create_youtube_client,
    fetch_all_channels_videos,
    fetch_channel_videos,
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
        import googleapiclient.errors

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
        import googleapiclient.errors

        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        client.playlistItems().list().execute.side_effect = googleapiclient.errors.HttpError(
            resp=MagicMock(status=403), content=b"Quota exceeded"
        )

        result = fetch_channel_videos(client, "UCtest", since, dry_run=False)
        assert result == []

    def test_handles_generic_error(self) -> None:
        """Test that generic errors are handled gracefully."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        client.playlistItems().list().execute.side_effect = Exception("Network error")

        result = fetch_channel_videos(client, "UCtest", since, dry_run=False)
        assert result == []

    def test_no_playlist_returns_empty(self) -> None:
        """Test that no playlist ID returns empty list."""
        client = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)

        with patch("youtube_api._get_uploads_playlist_id", return_value=None):
            result = fetch_channel_videos(client, "NON_UC", since, dry_run=False)

        assert result == []


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
        assert result == []


class TestCreateYoutubeClient:
    """Tests for create_youtube_client function."""

    def test_creates_client(self) -> None:
        """Test that client is created with correct parameters."""
        with patch("googleapiclient.discovery.build") as mock_build:
            mock_build.return_value = MagicMock()
            client = create_youtube_client("test_api_key")

        mock_build.assert_called_once_with("youtube", "v3", developerKey="test_api_key")
        assert client is not None
