import asyncio
import logging
import os
import random

from time import sleep
from httpx import AsyncClient
from runch import (
    RunchModel,
    RunchLogLevel,
    RunchAsyncCustomConfigReader,
)
from runch.exceptions import RunchConfigUnchanged

from typing import Any

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


class TestConfig(RunchModel):
    status: str
    method: str


TEST_AUTH_KEY = os.environ.get("TEST_AUTH_KEY", "sk-example_secret_auth_key")


async def config_loader(config_name: str) -> TestConfig:
    """Load config from a remote source."""

    print(f"Loading config from remote source for {config_name=}...")

    headers = {"Authorization": f"Bearer {TEST_AUTH_KEY}"}

    # Simulate a network request to fetch the config.

    async with AsyncClient() as client:
        rnd = random.random()
        if rnd < 0.3:
            response = await client.get(
                "https://dummyjson.com/test",
                headers=headers,
            )
        elif rnd < 0.6:
            response = await client.post(
                "https://dummyjson.com/test",
                headers=headers,
            )
        else:
            print("config_loader: simulating config unchanged...")
            raise RunchConfigUnchanged()

        response.raise_for_status()

    return TestConfig(**response.json())


test_reader = RunchAsyncCustomConfigReader[TestConfig](
    config_name="example1", config_loader=config_loader, logger=RunchLogAdapter()
)
test_reader.enable_feature("watch_update", {"update_interval": 2})


async def main():
    while True:
        test_config = await test_reader.read()
        print("test_config", test_config.config)
        sleep(1)


asyncio.run(main())
