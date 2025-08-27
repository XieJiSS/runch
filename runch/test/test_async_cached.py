import asyncio
import random

from httpx import AsyncClient

from runch import (
    RunchModel,
    RunchAsyncCustomConfigReader,
)
from runch.exceptions import RunchConfigUnchanged, RunchLookupError

cached_version_num_map: dict[str, str] = {}


class RemoteConfig(RunchModel):

    class RemoteConfigDataModel(RunchModel):
        a: int

    version: str
    data: RemoteConfigDataModel


async def config_loader_with_cache(
    config_name: str, auth: str | None = None
) -> RemoteConfig:
    """Load config from a remote source."""

    print("fetching config...")

    global cached_version_num_map
    cached_version_num_map.setdefault(config_name, "N/A")

    headers = {"Authorization": f"Bearer {auth}"}

    # Simulate a network request to fetch the config.

    async with AsyncClient() as client:
        if random.random() < 0.5:
            response = await client.get(
                "https://dummyjson.com/c/884c-58bd-49bf-96c8",
                headers=headers,
            )
        else:
            response = await client.get(
                "https://dummyjson.com/c/d40f-4842-4e12-8b3d",
                headers=headers,
            )

        response.raise_for_status()

    # This is just a demonstration. In a real-world scenario, you would like to store & compare ETags obtained via
    # a HEAD request to avoid unnecessary network traffics.

    new_config = RemoteConfig(**response.json())
    if new_config.version != cached_version_num_map[config_name]:
        print(
            f"Config updated from {cached_version_num_map[config_name]} to {new_config.version}"
        )
        cached_version_num_map[config_name] = new_config.version
        return new_config
    else:
        print("Config unchanged, skipping update")
        raise RunchConfigUnchanged()


test_cached_reader = RunchAsyncCustomConfigReader[RemoteConfig](
    config_name="example_cached",
    config_loader=config_loader_with_cache,
)

test_cached_reader.enable_feature("watch_update", {"update_interval": 2})


async def main():
    try:
        test_cached_reader.read_cached()
        exc = None
    except Exception as e:
        exc = e
    assert isinstance(exc, RunchLookupError)

    config = await test_cached_reader.read()

    while True:
        assert test_cached_reader.read_cached() == await test_cached_reader.read()
        print(f"{config.config!r}")
        await asyncio.sleep(2)


asyncio.run(main())
