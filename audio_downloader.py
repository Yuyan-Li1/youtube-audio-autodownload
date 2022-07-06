# -*- coding: utf-8 -*-

import argparse
import datetime
from pathlib import Path

import googleapiclient.discovery
import googleapiclient.errors
import yt_dlp

debug = False

scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
api_service_name = "youtube"
api_version = "v3"

youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=Path('API_key').read_text())


def main(date=None, arg_debug=False):
    global debug
    debug = arg_debug
    with open('channel_ids') as f:
        channel_ids = f.read().splitlines()

    if date:
        for channel_id in channel_ids:
            get_video_list(channel_id, date)
    else:
        # todo: add read date from file
        pass

    # todo: add download audio
    

def get_video_list(channel_id, date):
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
            'publishedAt': video['snippet']['publishedAt'],
        }
        videos.append(new_video)

    debug_print(videos)


# uses youtube_dlp instead of youtube_dl for speed.
def download_audio(video_id):
    video_link_prefix = 'https://www.youtube.com/watch?v='

    ydl_opts = {
        'paths': {'home': './downloads/'},
        'format': 'm4a/bestaudio/best',
        'postprocessors': [{  # Extract audio using ffmpeg
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        error_code = ydl.download(f'{video_link_prefix}{video_id}')


def debug_print(message):
    if debug:
        print(message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download audio from YouTube channels specified in channel_id.txt.')
    parser.add_argument('-d', '--date', type=datetime.date.fromisoformat,
                        help='Download audio that is released after this date. The date should be in ISO format ('
                             'YYYY-MM-DD).')
    parser.add_argument('-D', '--debug', action='store_true', help='Print debug messages.')
    args = parser.parse_args()
    main(args.date, args.debug)
