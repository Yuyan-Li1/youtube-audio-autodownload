# youtube-audio-autodownload

There are a lot of YouTube videos that are mostly talking, I like listening to them as podcasts instead of watching the
videos. This is a Python script that checks for updates and downloads audio from new videos of specified channels. I set
up a crontab with this to download audio from YouTube channels and put them into my podcast client's sideloads folder in
iCloud drive with Automator.

## Usage

Normal mode:

```shell
python3 youtube-audio-autodownload.py
```

Debug mode:

```shell
python3 youtube-audio-autodownload.py -D
```

The script will not download anything the first time it runs, it will generate a file called 'last_downloaded' with the
latest videos of each channel. It is a plain JSON file and can be modified if you like.

## Dependency (other than Python packages in requirements.txt)

- ffmpeg
- youtube-dlp
- Having a YouTube API key and rename it to 'API_key', and put it in the same directory as this script. You can find out
  how to get
  one [here](https://developers.google.com/youtube/v3/getting-started).
