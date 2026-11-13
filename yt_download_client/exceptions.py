class YTDownloadError(Exception):
    pass


class AuthenticationError(YTDownloadError):
    pass


class RateLimitError(YTDownloadError):
    def __init__(self, message, *, retry_after=5):
        super().__init__(message)
        self.retry_after = retry_after


class JobFailedError(YTDownloadError):
    pass


class JobNotFoundError(YTDownloadError):
    pass


class JobTimeoutError(YTDownloadError):
    pass


class ServerBusyError(YTDownloadError):
    def __init__(self, message, *, retry_after=5):
        super().__init__(message)
        self.retry_after = retry_after
