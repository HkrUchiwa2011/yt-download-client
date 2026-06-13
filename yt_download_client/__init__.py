from .client import YTDownloadClient
from .models import Job, VideoInfo
from .exceptions import (
    YTDownloadError,
    AuthenticationError,
    RateLimitError,
    JobFailedError,
    JobNotFoundError,
    JobTimeoutError,
    ServerBusyError,
)

__version__ = "1.0.1"
__all__ = [
    "YTDownloadClient",
    "Job",
    "VideoInfo",
    "YTDownloadError",
    "AuthenticationError",
    "RateLimitError",
    "JobFailedError",
    "JobNotFoundError",
    "JobTimeoutError",
    "ServerBusyError",
]
