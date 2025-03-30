# Runch

Refined [munch](https://github.com/Infinidat/munch). Provides basic munch functionality (attribute-style access for python dicts) with additional generic typing support and runtime validation.

Also provides a config reader that reads config files into predefined `runch` models. Say goodbye to `config["key"]`, `config.get("key")` and runtime errors caused by missing keys!

## Installation

```bash
pip install runch
```

If you find any bugs, please submit an issue or a pull request at [GitHub](https://github.com/XieJiSS/runch).

## Usage

### Via Model Definition Generator

```bash
$ python -m runch <config_path> [config_ext]
```

Manual:

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

Example of generated config reader:

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
    db: DBConfig
    services: List[ServiceConfig]

class PostgresConfig(RunchModel):
    host: str
    port: str
    user: str
    password: str
    name: str
    pool_size: int
    register_: int = Field(..., alias='register')


class DBConfig(RunchModel):
    postgres: PostgresConfig


class ServiceConfig(RunchModel):
    name: str
    host: str
    port: str
    path: str

_base_reader = RunchConfigReader[BaseConfigModel]("base.yaml", config_dir="./etc", config_type="yaml")
base = _base_reader.read_lazy()

# uncomment the following line to enable the watch_file_update feature
# _base_reader.set_feature("watch_file_update", {"enabled": True, "args": {"update_interval": 10}})
```

### Write Config Manually

```python
from runch import RunchModel, RunchConfigReader

class ExampleConfig(RunchModel):
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str

# Read config from file.                 ↓ square brackets
example_config_reader = RunchConfigReader[ExampleConfig](
                                        # ^^^^^^^^^^^^^ Config model class name
    config_name="config_file_name",     # with file extension, but don't include the ".example" part
    config_dir="config_dir",            # default is os.environ.get("RUNCH_CONFIG_DIR", "./etc")
    config_type="yaml"                  # default is "yaml"
    config_encoding="utf-8"             # default is "utf-8"
)
example_config = example_config_reader.read()  # Or .read_lazy() for lazy loading

print(example_config.config.db_host)    # with awesome intellicode support & runtime validation!
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
- arbitrary file formats with custom reader, specified via the `custom_config_loader` param of `RunchConfigReader.__init__()`. The custom reader should be a function that takes a `str`-type file content as its first argument, and returns a dictionary.

## Other Features

- configurable auto sync & update.
- optional lazy load & evaluate. Useful for optional configs that may not exist.
- configurable example merging for fast local development.
- read arbitrary file formats from any places (e.g. network, db) with custom reader.
  - Note: custom readers are sync functions. We highly recommend avoid combining lazy loading via `read_lazy()` & fetching configs from network / db, because this may block the main thread at runtime. Use `read()` instead so that the program won't get blocked after the initialization phase.
