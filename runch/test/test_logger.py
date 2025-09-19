import logging

from time import sleep

from typing import Any

from runch import (
    RunchModel,
    RunchConfigReader,
    RunchLogLevel,
)

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
    x: int


test_reader = RunchConfigReader[TestConfig](
    config_name="test.yaml", config_dir="runch/test", logger=RunchLogAdapter()
)
test_reader.enable_feature("watch_update", {"update_interval": 1})
test_config = test_reader.read_lazy()

while True:
    print("test_config", test_config.config)
    sleep(1)
