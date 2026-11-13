from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Job:
    id: str
    status: Literal["pending", "started", "progress", "post_processing", "success", "failure"]
    progress: dict | None = None
    download_url: str | None = None
    error: str | None = None

    @property
    def done(self) -> bool:
        return self.status in ("success", "failure")

    @property
    def successful(self) -> bool:
        return self.status == "success"


@dataclass
class VideoInfo:
    title: str
    duration: int | None
    uploader: str | None
    thumbnail: str | None
    formats: list[dict] = field(default_factory=list)
    filesize_approx: int | None = None

    @property
    def duration_formatted(self) -> str:
        if self.duration is None:
            return "unknown"
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
