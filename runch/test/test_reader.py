from time import sleep
from runch import (
    RunchModel,
    Runch,
    RunchConfigReader,
    FeatureConfig,
    require_lazy_runch_configs,
)


class TestConfig(RunchModel):
    x: int


test_reader = RunchConfigReader[TestConfig](
    config_name="test.yaml", config_dir="runch/test"
)

test_reader.enable_feature("watch_file_update", 1)

test_config = test_reader.read_lazy()

while True:
    print(test_config.config)
    sleep(1)
