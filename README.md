# Runch

Refined [munch](https://github.com/Infinidat/munch). Provides basic munch functionality (attribute-style access for python dicts) with additional generic typing support and runtime validation.

Also provides a config reader that reads config files into predefined `runch` models. Say goodbye to `config["key"]`, `config.get("key")` and runtime errors caused by missing keys!

## Installation

```bash
pip install runch
```

If you find any bugs, please submit an issue or a pull request at [GitHub](https://github.com/XieJiSS/runch).

## Usage

### Example Config Model Definition:

```bash
$ python3 -m runch ./etc/base.yaml
```

```python
# Generated from base{.example,}.yaml by runch
# Please be aware that `float` fields might be annotated as `int` due to the lack of type info in the config.

from __future__ import annotations

from typing import List

from pydantic import Field
from runch import RunchModel, RunchConfigReader

class BaseConfigModel(RunchModel):
    host: str
    port: str
    user: str
    password: str


base_reader = RunchConfigReader[BaseConfigModel]("base.yaml", config_dir="./etc", config_type="yaml")
base = base_reader.read()

# example:
print(base.config.host, base.config.port)  # with awesome intellicode support & runtime validation!

# uncomment the following line to enable the watch_update feature
# _base_reader.enable_feature("watch_update", {"update_interval": 10})
```

### Model Definition Generator

```bash
$ python -m runch <config_path> [config_ext]
```

Usage:

```
Usage: python -m runch <config_path> [config_name [config_ext]]
    Generate a model definition from a config file.

    config_path: path to your config file.
    config_name: controls generated variable name and class name.
    config_type: content type of your config file. Default is `yaml`.

    Example:
        python -m runch path/to/my_config.foo
        python -m runch path/to/my_config.foo chat_config
        python -m runch path/to/my_config.foo chat_config yaml
```

### `RunchConfigReader` Arguments

```python
# Read config from file.                 ↓ square brackets
example_config_reader = RunchConfigReader[ExampleConfig](
                                        # ^^^^^^^^^^^^^ Config model class name
    config_name="config_file_name",     # with file extension, but don't include the ".example" part
    config_dir="config_dir",            # default is os.environ.get("RUNCH_CONFIG_DIR", "./etc")
    config_type="yaml",                 # default is "yaml"
    config_encoding="utf-8",            # default is "utf-8"
    config_logger=getLogger("example"), # default is None
)
example_config = example_config_reader.read()  # Or .read_lazy() for lazy loading

print(example_config.config.db_host)
```

```bash
$ touch example_config_dir/example_config_file.yaml
```

```yaml
db_host: localhost
db_port: 5432
db_user: user
db_password: password
db_name: database
```

## Supported File Formats

- YAML
- JSON
- TOML
- arbitrary file formats with custom parser, specified via the `custom_config_parser` param of `RunchConfigReader.__init__()`. The custom parser should be a function that takes a `str`-type file content as its first argument, and returns a parsed dictionary.

## Use Remote Config Source

```python
from httpx import AsyncClient
from runch import (
    RunchModel,
    RunchAsyncCustomConfigReader,
)


class TestConfig(RunchModel):
    status: str
    method: str


async def example_config_loader(config_name: str) -> TestConfig:
    """Load config from a remote source."""

    print(f"Loading config from remote source for {config_name=}...")

    # Simulate a network request to fetch the config.
    async with AsyncClient() as client:
        response = await client.get(
            f"https://dummyjson.com/test",
            headers=headers,
        )
        response.raise_for_status()

    return TestConfig(**response.json())


test_reader = RunchAsyncCustomConfigReader[TestConfig](
    config_name="example",
    config_loader=example_config_loader,
)

async def main():
    test_config = await test_reader.read()
    print(test_config.config.status)

    # read_cached() does not require `await`, but it raises RunchLookupError if there's no prior sucessful call to `read()`
    print(test_config, test_reader.read_cached())
```

Note that you can raise `runch.exceptions.RunchConfigUnchanged` inside custom config loaders to prevent unnecessary config reloads / updates.

## Other Features

- configurable auto sync & update.
- optional lazy load & evaluate. Useful for optional configs that may not exist.
- configurable example merging for fast local development.
- read arbitrary file formats from any places (e.g. disk, network, db) with sync reader + custom config parser / async reader + custom config loader.

### Auto Update

```python
test_reader.enable_feature("watch_update", {"update_interval": 2})  # update every 2s
test_reader.enable_feature(
    "watch_update",
    {
        "update_interval": 2.5,  # update every 2.5s
        "on_update_error": "ignore"  # ignore or raise. default=ignore
    }
)
```

### Merge Example Yaml for Local Dev

```python
test_reader = RunchConfigReader[TestConfig](
    config_name="test.yaml",
    config_type="yaml",
)
if os.environ.get("SERVE_MODE") != "prod":
    test_reader.enable_feature("merge_example", {})
```

### User-Defined Custom Config Validation Logic

Note that this is different from the custom config loader feature.

```python
from runch import RunchModel, RunchConfigReader

class CustomConfigModel(RunchModel):
    host: str
    port: int

    def __init__(self, *args: Any, **kw: Any):
        super().__init__(*args, **kw)

        if self.port % 2 == 0:
            raise ValueError("Only odd port numbers are accepted")
```

### Logging

```python
import logging
from logging import getLogger
from typing import Any
from runch import (
    RunchModel,
    RunchConfigReader,
    RunchLogLevel,
)

logging.basicConfig(level=RunchLogLevel.INFO)

class RunchLogAdapter:
    def log(self, level: RunchLogLevel, msg: str, /, *, exc_info: BaseException | None = None, **kwargs: Any):
        getLogger("runch").log(level, f'{msg} %s', " ".join(["{k}={v}" for k, v in kwargs.items()]), exc_info=exc_info)

class TestConfig(RunchModel):
    x: int

test_reader = RunchConfigReader[TestConfig](
    config_name="test.yaml", config_dir="runch/test", logger=RunchLogAdapter()
)
test_reader.enable_feature("watch_update", {"update_interval": 1})
test_config = test_reader.read()  # will call RunchLogAdapter().log with level RunchLogLevel.ERROR if config is invalid.
```
