import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    host = "0.0.0.0" if settings.lan_mode and settings.backend_host == "127.0.0.1" else settings.backend_host
    uvicorn.run(
        "app.main:app",
        host=host,
        port=settings.backend_port,
        reload=settings.app_env == "development" and settings.debug and not settings.lan_mode,
        ws_max_size=300000,
        access_log=False,
    )


if __name__ == "__main__":
    main()
