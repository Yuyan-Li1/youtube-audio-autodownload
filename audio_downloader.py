# -*- coding: utf-8 -*-

from pathlib import Path

import googleapiclient.discovery
import googleapiclient.errors

DEBUG = True

scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
api_service_name = "youtube"
api_version = "v3"

youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=Path('API_key').read_text())


def main():
    get_video_list("UCe4_UPAmhz2sqorGbF8oZHA")


def get_video_list(channel_id):
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


def debug_print(message):
    if DEBUG:
        print(message)


if __name__ == "__main__":
    main()
