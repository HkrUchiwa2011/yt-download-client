# yt-download-client

[![PyPI](https://img.shields.io/pypi/v/yt-download-client.svg)](https://pypi.org/project/yt-download-client/)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)

Python client for [yt-download-api](https://github.com/HkrUchiwa2011/yt-download-api).

Download YouTube videos from any Python script, Discord bot, or Telegram bot — without dealing with HTTP, polling, or error handling yourself.

```bash
pip install yt-download-client
```

---

## Requirements

A running instance of [yt-download-api](https://github.com/HkrUchiwa2011/yt-download-api). Deploy your own in one click or run it locally.

---

## Quick start

```python
from yt_download_client import YTDownloadClient

client = YTDownloadClient(
    base_url="https://your-api.onrender.com",
    api_key="YOUR_KEY",
)

path = client.download("https://youtu.be/dQw4w9WgXcQ")
print(f"Saved to {path}")
```

---

## Usage

### One-liner download

```python
path = client.download(
    url="https://youtu.be/dQw4w9WgXcQ",
    format="mp4",
    quality="720p",
    output="video.mp4",
)
```

Supported formats: `mp4`, `mp3`, `webm`
Supported qualities: `best`, `1080p`, `720p`, `480p`, `360p`, `audio_only`

### With progress tracking

```python
from yt_download_client import Job

def on_progress(job: Job):
    if job.status == "progress" and job.progress:
        downloaded = job.progress.get("downloaded_bytes", 0)
        total = job.progress.get("total_bytes", 0)
        if total:
            pct = round(downloaded / total * 100)
            print(f"{pct}%", end="\r")

path = client.download(
    "https://youtu.be/dQw4w9WgXcQ",
    on_progress=on_progress,
)
```

### Step by step

For more control — submit, wait, and fetch separately:

```python
# Submit and get a job ID immediately
job = client.submit("https://youtu.be/dQw4w9WgXcQ", format="mp3", quality="audio_only")
print(f"Job submitted: {job.id}")

# Wait until done (blocks, polls every 5s)
job = client.wait(job.id, poll_interval=5, timeout=300)

# Download the file
path = client.fetch(job.id, output="song.mp3")
print(f"Saved to {path}")
```

### Get video info before downloading

```python
info = client.info("https://youtu.be/dQw4w9WgXcQ")
print(info.title)
print(info.duration_formatted)  # "03:33"
print(info.uploader)
for fmt in info.formats:
    print(fmt["resolution"], fmt["ext"])
```

### Discord bot example

```python
import discord
from yt_download_client import YTDownloadClient, JobFailedError

client = YTDownloadClient(base_url="https://your-api.onrender.com", api_key="YOUR_KEY")
bot = discord.Client(intents=discord.Intents.default())

@bot.event
async def on_message(message):
    if message.content.startswith("!download "):
        url = message.content.split(" ", 1)[1]
        await message.channel.send("Downloading...")
        try:
            path = client.download(url, format="mp4", quality="720p")
            await message.channel.send(file=discord.File(str(path)))
        except JobFailedError as e:
            await message.channel.send(f"Failed: {e}")
```

---

## Error handling

```python
from yt_download_client import (
    YTDownloadClient,
    AuthenticationError,
    RateLimitError,
    JobFailedError,
    JobTimeoutError,
    ServerBusyError,
    YTDownloadError,
)

try:
    client.download("https://youtu.be/dQw4w9WgXcQ")
except AuthenticationError:
    print("Bad API key")
except RateLimitError as e:
    print(f"Slow down: {e}")
except JobFailedError as e:
    print(f"Download failed: {e}")
except JobTimeoutError:
    print("Took too long")
except ServerBusyError:
    print("Server is busy, retry later")
except YTDownloadError as e:
    print(f"Something went wrong: {e}")
```

---

## API reference

### `YTDownloadClient(base_url, api_key, timeout=30)`

| Method | Description |
|--------|-------------|
| `download(url, format, quality, output, poll_interval, timeout, on_progress)` | Full flow in one call |
| `submit(url, format, quality, webhook_url)` → `Job` | Submit a job |
| `wait(job_id, poll_interval, timeout, on_progress)` → `Job` | Wait for completion |
| `fetch(job_id, output)` → `Path` | Download the output file |
| `status(job_id)` → `Job` | Get current job status |
| `info(url)` → `VideoInfo` | Fetch video metadata |
| `health()` → `dict` | Check API health |
| `delete(job_id)` → `dict` | Delete a file from the server |

### `Job`

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `str` | Job ID |
| `status` | `str` | `pending`, `started`, `progress`, `post_processing`, `success`, `failure` |
| `progress` | `dict` | Progress info (speed, ETA, bytes) |
| `download_url` | `str` | Relative download path when done |
| `error` | `str` | Error message on failure |
| `done` | `bool` | True if success or failure |
| `successful` | `bool` | True if success |

### `VideoInfo`

| Attribute | Type | Description |
|-----------|------|-------------|
| `title` | `str` | Video title |
| `duration` | `int` | Duration in seconds |
| `duration_formatted` | `str` | Human-readable duration (`03:33`) |
| `uploader` | `str` | Channel name |
| `thumbnail` | `str` | Thumbnail URL |
| `formats` | `list` | Available formats |
| `filesize_approx` | `int` | Approximate file size in bytes |

---

## License

[MIT](LICENSE)
