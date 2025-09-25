from time import sleep
from runch import (
    RunchModel,
    RunchLaxModel,
    RunchStrictModel,
    RunchConfigReader,
)


class TestConfig(RunchModel):
    x: int


class TestLaxConfig(RunchLaxModel):
    x: set[int]


class TestStrictConfig(RunchStrictModel):
    x: int


test_strict_reader = RunchConfigReader[TestStrictConfig](
    config_name="test_strict.yaml", config_dir="runch/test"
)
test_strict_config = test_strict_reader.read()
print("test_strict_config", test_strict_config.config)

test_lax_reader = RunchConfigReader[TestLaxConfig](
    config_name="test_lax.yaml", config_dir="runch/test"
)
test_lax_config = test_lax_reader.read()
print("test_lax_config", test_lax_config.config)

test_reader = RunchConfigReader[TestConfig](
    config_name="test.yaml", config_dir="runch/test"
)
test_reader.enable_feature("watch_update", {"update_interval": 1})
test_config = test_reader.read_lazy()

while True:
    print("test_config", test_config.config)
    sleep(1)
