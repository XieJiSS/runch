# Runch

Refined [munch](https://github.com/Infinidat/munch). Provides basic `munch` functionality with additional generic typing support and runtime validation.

## Installation

```bash
pip install runch
```

## Usage

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
#                                         ^^^^^^^^^^^^^ Config model class name
    config_name="example_config_file",  # without extension
    config_dir="example_config_dir",    # default is os.environ.get("RUNCH_CONFIG_DIR", "./etc")
    config_ext="yaml"                   # default is "yaml"
    config_encoding="utf-8"             # default is "utf-8"
)
example_config = example_config_reader.read()

print(example_config.config.db_host)  # with awesome intellicode support & runtime validation!
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
- arbitrary file formats with custom reader, specified via the `custom_config_loader` param of `RunchConfigReader.__init__()`. The custom reader should be a callable that takes a `str`-type file content and returns a dictionary.

## Model Generator

```bash
$ python -m runch <config_name> [config_ext]
```

Manual:

```
Generate a model definition from a config file.

config_name: the name of the config file without the extension.
config_ext: the extension of the config file. Default is `yaml`.

Use RUNCH_CONFIG_DIR environment variable to specify the directory of the config files. Default is `./etc`.

Example:
    python -m runch my_config
    python -m runch my_config yaml
```
