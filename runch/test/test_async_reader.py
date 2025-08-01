import asyncio
import os
import random

from httpx import AsyncClient

from runch import (
    RunchModel,
    RunchAsyncCustomConfigReader,
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
        if random.random() < 0.5:
            response = await client.get(
                "https://dummyjson.com/test",
                headers=headers,
            )
        else:
            response = await client.post(
                "https://dummyjson.com/test",
                headers=headers,
            )

        response.raise_for_status()

    return TestConfig(**response.json())


test_reader_1 = RunchAsyncCustomConfigReader[TestConfig](
    config_name="example1",
    config_loader=config_loader,
)

test_reader_2 = RunchAsyncCustomConfigReader[TestConfig](
    config_name="example2",
    config_loader=config_loader,
)

test_reader_1.enable_feature("watch_update", {"update_interval": 2})
test_reader_2.enable_feature("watch_update", {"update_interval": 2})


async def main():
    test_config_1 = await test_reader_1.read()
    test_config_2 = await test_reader_2.read()

    while True:
        print("test_config_1.config", test_config_1.config)
        print("test_config_2.config", test_config_2.config)
        await asyncio.sleep(2)


asyncio.run(main())
