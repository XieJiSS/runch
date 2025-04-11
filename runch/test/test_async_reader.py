import asyncio
import random

from httpx import AsyncClient

from runch import (
    RunchModel,
    RunchAsyncCustomConfigReader,
)


class TestConfig(RunchModel):
    status: str
    method: str


async def config_loader(config_name: str, auth: str | None = None) -> TestConfig:
    """Load config from a remote source."""

    print(f"Loading config from remote source for {config_name=}...")

    headers = {"Authorization": f"Bearer {auth}"}

    # Simulate a network request to fetch the config.

    async with AsyncClient() as client:
        if random.random() < 0.5:
            response = await client.get(
                f"https://dummyjson.com/test",
                headers=headers,
            )
        else:
            response = await client.post(
                f"https://dummyjson.com/test",
                headers=headers,
            )

        response.raise_for_status()

    return TestConfig(**response.json())


test_reader_1 = RunchAsyncCustomConfigReader[TestConfig](
    config_name="example1",
    config_loader=config_loader,
)

test_reader_2 = RunchAsyncCustomConfigReader[TestConfig, *tuple[str]](
    config_name="example2",
    config_loader=config_loader,
    config_loader_extra_args=("sk-example_secret_auth_key",),
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
