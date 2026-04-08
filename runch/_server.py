# pyright: basic
from __future__ import annotations

from aiohttp import web

from runch._reader import (
    RunchCompatibleLogger,
    RunchLogLevel,
    get_config_server_registry,
)


def _log(
    logger: RunchCompatibleLogger | None,
    level: RunchLogLevel,
    msg: str,
) -> None:
    if logger is not None:
        logger.log(
            level,
            f"RunchConfigServer: {msg}",
            runch_config=None,
        )


async def _handle_config(request: web.Request) -> web.Response:
    path = request.query.get("path")
    name = request.query.get("name")

    if not path or not name:
        return web.Response(
            status=400,
            text="missing required query parameters: path, name",
        )

    registry = get_config_server_registry()
    ref = registry.get((path, name))

    if ref is None:
        return web.Response(status=404, text="config reader not found")

    reader = ref()
    if reader is None:
        # weakref is dead, clean up
        registry.pop((path, name), None)
        return web.Response(status=404, text="config reader not found")

    raw_content = reader._raw_config_content
    if raw_content is None:
        return web.Response(status=404, text="config not loaded yet")

    return web.Response(status=200, text=raw_content, content_type="text/plain")


async def start_runch_config_server(
    *,
    unix_socket: str | None = None,
    host: str | None = None,
    port: int | None = None,
    logger: RunchCompatibleLogger | None = None,
) -> web.AppRunner:
    """Start an aiohttp server that serves raw config content from registered RunchConfigReaders.

    The server exposes a single endpoint: GET /config?path=<config_dir>&name=<config_name>

    Either `unix_socket` or `host`+`port` must be provided.

    The caller is responsible for stopping and cleaning up the returned AppRunner
    via `await runner.cleanup()`.

    Args:
        unix_socket: Path to a Unix domain socket to listen on.
        host: TCP host to bind to.
        port: TCP port to bind to.
        logger: Optional logger for server lifecycle messages.

    Returns:
        web.AppRunner: The running server's AppRunner instance.
    """
    if unix_socket and (host or port):
        raise ValueError("cannot specify both unix_socket and host/port")
    if not unix_socket and not (host and port):
        raise ValueError("must specify either unix_socket or host+port")

    app = web.Application()
    app.router.add_get("/config", _handle_config)

    runner = web.AppRunner(app)
    await runner.setup()

    if unix_socket:
        site = web.UnixSite(runner, unix_socket)
        await site.start()
        _log(logger, RunchLogLevel.INFO, f"listening on unix:{unix_socket}")
    else:
        site = web.TCPSite(runner, host, port)
        await site.start()
        _log(logger, RunchLogLevel.INFO, f"listening on {host}:{port}")

    return runner
