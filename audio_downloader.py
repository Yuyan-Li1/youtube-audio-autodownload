# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path
from pprint import pprint

import dateutil.parser
import googleapiclient.discovery
import googleapiclient.errors
import yt_dlp

debug = False

scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
api_service_name = "youtube"
api_version = "v3"

youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=Path('API_key').read_text())


def main(arg_debug=False):
    global debug
    debug = arg_debug
    videos = []
    data = Path('last_downloaded')

    with open('channel_ids') as f:
        channel_ids = f.read().splitlines()

    if not data.exists():
        debug_print('Datafile does not exist')
        init_dict(channel_ids)
        return

    data = read_dict()
    debug_print(f'Read from the datafile: {data}')

    for channel in data:
        result = get_video_list(channel['channel_id'], channel['video_id'])
        videos += result[0]
        latest = result[1]
        channel['video_id'] = latest

    for video in videos:
        download_audio(video['id'])

    write_dict(data)


def get_video_list(channel_id, last_downloaded=None):
    """
    Returns a list of videos from a YouTube channel.
    Args:
        channel_id: the channel id of the channel to get the video list from.
        last_downloaded: if this is not None, it will be used to get the latest videos up to this one.

    Returns:
        A list of videos from the channel up to the last downloaded video provided (exclusive)
            and the last video of the channel.
        The id of the last video of the channel is returned if no last_downloaded is provided, t

    """
    if last_downloaded:
        request = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            maxResults=25,
            order="date",
            type="video"
        )
        response = request.execute()
        videos = []
        lastest = response['items'][0]['id']['videoId']
        for video in response['items']:
            new_video = {
                'id': video['id']['videoId'],
                'title': video['snippet']['title'],
                'publishedAt': dateutil.parser.isoparse(video['snippet']['publishedAt']),
            }
            if new_video['id'] == last_downloaded:
                break
            else:
                videos.append(new_video)

        debug_print(f'From channel {channel_id}, fetched new videos: {videos}')
        return videos, lastest
    else:
        request = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            maxResults=1,
            order="date",
            type="video"
        )
        response = request.execute()
        return response['items'][0]['id']['videoId']


# uses youtube_dlp instead of youtube_dl for speed.
def download_audio(video_id):
    video_link_prefix = 'https://www.youtube.com/watch?v='

    ydl_opts = {
        'paths': {'home': './downloads/'},
        'format': 'm4a/bestaudio/best',
        'outtmpl': '%(title)s - %(channel)s.%(ext)s'
        # 'postprocessors': [{  # Extract audio using ffmpeg
        #     'key': 'FFmpegExtractAudio',
        #     'preferredcodec': 'm4a',
        # }]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        error_code = ydl.download(f'{video_link_prefix}{video_id}')


def debug_print(message):
    if debug:
        pprint(message)


# these functions read and writes the data from and to the file last_downloaded
def read_dict():
    with open('last_downloaded', 'r') as file:
        return json.load(file)


def write_dict(data):
    with open('last_downloaded', 'w') as file:
        json.dump(data, file)
    debug_print(f'Wrote to the datafile')


def init_dict(channels):
    data = []
    for channel in channels:
        video_id = get_video_list(channel)
        last_downloaded = {
            'channel_id': channel,
            'video_id': video_id
        }
        data.append(last_downloaded)
    write_dict(data)
    debug_print(f'Initialized the datafile: {data}')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download audio from YouTube channels specified in channel_id.txt.')
    parser.add_argument('-D', '--debug', action='store_true', help='Print debug messages.')
    args = parser.parse_args()
    main(args.debug)
