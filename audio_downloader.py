# -*- coding: utf-8 -*-

import argparse
import datetime
from pathlib import Path
from pprint import pprint

import dateutil.parser
import googleapiclient.discovery
import googleapiclient.errors
import pytz
import yt_dlp

debug = False

scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
api_service_name = "youtube"
api_version = "v3"

youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=Path('API_key').read_text())


def main(date=None, arg_debug=False):
    global debug
    debug = arg_debug
    now = datetime.datetime.now()
    now = pytz.UTC.localize(now)
    videos = []

    with open('channel_ids') as f:
        channel_ids = f.read().splitlines()

    if date:
        dt = datetime.datetime.combine(date, datetime.time())
        dt = pytz.UTC.localize(dt)
        for channel_id in channel_ids:
            videos = get_video_list(channel_id, dt)
    else:
        debug_print(Path('last_download_date').read_text())
        last_run = dateutil.parser.isoparse(Path('last_download_date').read_text().strip())
        # last_run = pytz.UTC.localize(last_run)
        for channel_id in channel_ids:
            videos = videos + get_video_list(channel_id, last_run)

    debug_print(videos)
    for video in videos:
        download_audio(video['id'])

    Path('last_download_date').write_text(now.isoformat())


def get_video_list(channel_id, dt):
    request = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        maxResults=25,
        order="date",
        type="video"
    )
    response = request.execute()
    videos = []
    for video in response['items']:
        new_video = {
            'id': video['id']['videoId'],
            'title': video['snippet']['title'],
            'publishedAt': dateutil.parser.isoparse(video['snippet']['publishedAt']),
        }
        if new_video['publishedAt'] >= dt:
            videos.append(new_video)

    debug_print(videos)
    return videos


# uses youtube_dlp instead of youtube_dl for speed.
def download_audio(video_id):
    video_link_prefix = 'https://www.youtube.com/watch?v='

    ydl_opts = {
        'paths': {'home': './downloads/'},
        'format': 'm4a/bestaudio/best' #,
        # 'postprocessors': [{  # Extract audio using ffmpeg
        #    'key': 'FFmpegExtractAudio',
        #    'preferredcodec': 'm4a',
        # }]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        error_code = ydl.download(f'{video_link_prefix}{video_id}')


def debug_print(message):
    if debug:
        pprint(message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download audio from YouTube channels specified in channel_id.txt.')
    parser.add_argument('-d', '--date', type=datetime.date.fromisoformat,
                        help='Download audio that is released after this date. The date should be in ISO format ('
                             'YYYY-MM-DD).')
    parser.add_argument('-D', '--debug', action='store_true', help='Print debug messages.')
    args = parser.parse_args()
    main(args.date, args.debug)
