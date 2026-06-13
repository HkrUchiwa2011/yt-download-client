class YTDownloadError(Exception):
    pass


class AuthenticationError(YTDownloadError):
    pass


class RateLimitError(YTDownloadError):
    pass


class JobFailedError(YTDownloadError):
    pass


class JobNotFoundError(YTDownloadError):
    pass


class JobTimeoutError(YTDownloadError):
    pass


class ServerBusyError(YTDownloadError):
    pass
