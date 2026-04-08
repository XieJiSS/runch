# pyright: reportPrivateUsage=false

import asyncio
import logging

from typing import Any

from aiohttp import ClientSession

from runch import (
    RunchModel,
    RunchConfigReader,
    RunchLogLevel,
    FeatureConfig,
    start_runch_config_server,
)
from runch._reader import get_config_server_registry

logging.basicConfig(level=logging.INFO)


class RunchLogAdapter:

    def log(
        self,
        level: RunchLogLevel,
        msg: str,
        /,
        *,
        exc_info: BaseException | None = None,
        **kwargs: Any,
    ):
        logging.getLogger("runch").log(
            level,
            f"{msg} %s",
            " ".join([f"{key}={value}" for key, value in kwargs.items()]),
            exc_info=exc_info,
        )


logger = RunchLogAdapter()


class TestConfig(RunchModel):
    x: int


def test_register_to_config_server():
    """Test that enabling the feature registers the reader in the global registry."""
    reader = RunchConfigReader[TestConfig](
        config_name="test.yaml",
        config_dir="runch/test",
        logger=logger,
        features={
            "register_to_config_server": FeatureConfig(enabled=True, args={}),
        },
    )

    registry = get_config_server_registry()
    key = ("runch/test", "test.yaml")
    assert key in registry, "reader should be registered"
    assert registry[key]() is reader, "weakref should resolve to the reader"

    # disable should remove from registry
    reader.disable_feature("register_to_config_server")
    assert key not in registry, "reader should be unregistered after disable"

    # re-enable
    reader.enable_feature("register_to_config_server", {})
    assert key in registry, "reader should be re-registered"

    # close should clean up
    reader.close()
    assert key not in registry, "reader should be unregistered after close"

    print("PASS test_register_to_config_server")


def test_raw_config_content():
    """Test that _raw_config_content is populated after read()."""
    reader = RunchConfigReader[TestConfig](
        config_name="test.yaml",
        config_dir="runch/test",
        logger=logger,
    )
    assert reader._raw_config_content is None, "should be None before read"

    reader.read()
    assert reader._raw_config_content is not None, "should be set after read"
    assert isinstance(reader._raw_config_content, str)
    assert len(reader._raw_config_content) > 0
    print(f"raw_config_content: {repr(reader._raw_config_content)}")

    reader.close()
    print("PASS test_raw_config_content")


def test_raw_config_content_lazy():
    """Test that _raw_config_content is populated after lazy read is evaluated."""
    reader = RunchConfigReader[TestConfig](
        config_name="test.yaml",
        config_dir="runch/test",
        logger=logger,
    )
    assert reader._raw_config_content is None

    lazy = reader.read_lazy()
    assert reader._raw_config_content is None, "should still be None before lazy eval"

    # trigger lazy evaluation
    _ = lazy.config
    assert reader._raw_config_content is not None, "should be set after lazy eval"

    reader.close()
    print("PASS test_raw_config_content_lazy")


async def test_config_server_tcp():
    """Test the config server end-to-end with TCP."""
    reader = RunchConfigReader[TestConfig](
        config_name="test.yaml",
        config_dir="runch/test",
        logger=logger,
        features={
            "register_to_config_server": FeatureConfig(enabled=True, args={}),
        },
    )
    reader.read()

    runner = await start_runch_config_server(
        host="127.0.0.1", port=18923, logger=logger
    )

    try:
        async with ClientSession() as session:
            # normal request
            async with session.get(
                "http://127.0.0.1:18923/config",
                params={"path": "runch/test", "name": "test.yaml"},
            ) as resp:
                assert resp.status == 200, f"expected 200, got {resp.status}"
                text = await resp.text()
                assert len(text) > 0, "response should not be empty"
                assert text == reader._raw_config_content
                print(f"server response: {repr(text)}")

            # missing params -> 400
            async with session.get("http://127.0.0.1:18923/config") as resp:
                assert resp.status == 400, f"expected 400, got {resp.status}"

            # missing name -> 400
            async with session.get(
                "http://127.0.0.1:18923/config",
                params={"path": "runch/test"},
            ) as resp:
                assert resp.status == 400, f"expected 400, got {resp.status}"

            # unknown config -> 404
            async with session.get(
                "http://127.0.0.1:18923/config",
                params={"path": "nonexistent", "name": "nope.yaml"},
            ) as resp:
                assert resp.status == 404, f"expected 404, got {resp.status}"
    finally:
        await runner.cleanup()
        reader.close()

    print("PASS test_config_server_tcp")


async def test_config_server_unix():
    """Test the config server with Unix socket."""
    import os
    import tempfile

    reader = RunchConfigReader[TestConfig](
        config_name="test.yaml",
        config_dir="runch/test",
        logger=logger,
        features={
            "register_to_config_server": FeatureConfig(enabled=True, args={}),
        },
    )
    reader.read()

    sock_path = os.path.join(tempfile.mkdtemp(), "runch_test.sock")

    runner = await start_runch_config_server(unix_socket=sock_path, logger=logger)

    try:
        from aiohttp import UnixConnector

        async with ClientSession(connector=UnixConnector(path=sock_path)) as session:
            async with session.get(
                "http://localhost/config",
                params={"path": "runch/test", "name": "test.yaml"},
            ) as resp:
                assert resp.status == 200, f"expected 200, got {resp.status}"
                text = await resp.text()
                assert text == reader._raw_config_content
                print(f"unix socket response: {repr(text)}")
    finally:
        await runner.cleanup()
        reader.close()
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        os.rmdir(os.path.dirname(sock_path))

    print("PASS test_config_server_unix")


async def test_config_server_not_loaded():
    """Test that server returns 404 when config is registered but not yet loaded."""
    reader = RunchConfigReader[TestConfig](
        config_name="test.yaml",
        config_dir="runch/test",
        logger=logger,
        features={
            "register_to_config_server": FeatureConfig(enabled=True, args={}),
        },
    )
    # do NOT call reader.read()

    runner = await start_runch_config_server(
        host="127.0.0.1", port=18924, logger=logger
    )

    try:
        async with ClientSession() as session:
            async with session.get(
                "http://127.0.0.1:18924/config",
                params={"path": "runch/test", "name": "test.yaml"},
            ) as resp:
                assert resp.status == 404, f"expected 404, got {resp.status}"
                text = await resp.text()
                assert "not loaded" in text
    finally:
        await runner.cleanup()
        reader.close()

    print("PASS test_config_server_not_loaded")


async def test_config_server_param_validation():
    """Test that start_runch_config_server validates parameters."""
    try:
        await start_runch_config_server(
            unix_socket="/tmp/x.sock", host="127.0.0.1", port=8080
        )
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "both" in str(e)

    try:
        await start_runch_config_server()
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "either" in str(e)

    print("PASS test_config_server_param_validation")


if __name__ == "__main__":
    test_register_to_config_server()
    test_raw_config_content()
    test_raw_config_content_lazy()

    asyncio.run(test_config_server_tcp())
    asyncio.run(test_config_server_unix())
    asyncio.run(test_config_server_not_loaded())
    asyncio.run(test_config_server_param_validation())

    print("\nAll tests passed!")
