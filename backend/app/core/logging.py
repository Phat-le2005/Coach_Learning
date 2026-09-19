import logging


class SafeExceptionFilter(logging.Filter):
    def __init__(self, suppress_tracebacks: bool = True) -> None:
        super().__init__()
        self.suppress_tracebacks = suppress_tracebacks

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and self.suppress_tracebacks:
            exception_type = record.exc_info[0]
            record.msg = "ASGI application error (%s)"
            record.args = (exception_type.__name__ if exception_type else "Exception",)
            record.exc_info = None
            record.exc_text = None
        return True


def configure_logging(debug: bool = False) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("app").setLevel(logging.DEBUG if debug else logging.INFO)
    # Do not enable dependency debug logs, HTTP headers, or SQL parameter logging.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    server_logger = logging.getLogger("uvicorn.error")
    filters = [
        item for item in server_logger.filters if isinstance(item, SafeExceptionFilter)
    ]
    if filters:
        for item in filters:
            item.suppress_tracebacks = not debug
    else:
        server_logger.addFilter(SafeExceptionFilter(suppress_tracebacks=not debug))
