import os
import sys
import mergedeep
import json
import yaml
import tomllib

from pathlib import Path
from tempfile import TemporaryDirectory

from datamodel_code_generator import InputFileType, generate
from datamodel_code_generator import DataModelType

from typing import Any, Literal, NamedTuple, TextIO, cast

__doc__ = """Usage: python -m runch <config_path> [config_ext]
    Generate a model definition from a config file.
  
    config_path: path to your config file.
    config_ext: content type of your config file. Default is `yaml`.
        
    Example:
        python -m runch path/to/my_config.foo
        python -m runch path/to/my_config.foo yaml"""


def file_to_dict(
    f: TextIO,
    ext: Literal["yaml", "yml", "json", "toml"],
) -> dict[Any, Any]:
    if ext == "yaml" or ext == "yml":
        config_dict = yaml.safe_load(f)
        # yaml.safe_load may return None if the file is empty, we should make an empty config be a valid config
        if config_dict is None:
            config_dict = {}
        if not isinstance(config_dict, dict):
            raise TypeError(
                f"Invalid config format: {f.name} type={type(config_dict)}, expecting a dict"
            )
        return cast(dict[Any, Any], config_dict)
    elif ext == "json":
        config_dict = json.load(f)
        # we may got a list or even a string / number from json.load, and runtime type checking for these is not supported
        if not isinstance(config_dict, dict):
            raise TypeError(
                f"Invalid config format: {f.name} type={type(config_dict)}, expecting a dict"
            )
        return cast(dict[Any, Any], config_dict)
    elif ext == "toml":
        return tomllib.loads(f.read())
    else:
        raise ValueError(f"Unsupported file type: {ext}")


class FileNameInfo(NamedTuple):
    name: str
    ext: str


def parse_file_name(file_name: str) -> FileNameInfo:
    # is a path?
    if os.path.sep in file_name:
        raise ValueError(f"Invalid file name: {file_name}")

    name, ext = os.path.splitext(file_name)
    ext = ext[1:]

    return FileNameInfo(name=name, ext=ext)


def generate_model(config_path: str, config_ext: str):
    file_ext = config_ext.lower()

    if file_ext not in ["yaml", "yml", "json", "toml"]:
        raise ValueError(f"Unsupported file type: {config_ext}")

    config_file_name = os.path.basename(config_path)
    config_file_name_info = parse_file_name(config_file_name)

    example_config_name = ".".join(
        [config_file_name_info.name, "example", config_file_name_info.ext]
    )
    example_config_path = os.path.join(
        os.path.dirname(config_path), example_config_name
    )

    config: dict[Any, Any] = {}
    example_config: dict[Any, Any] = {}

    config_exists = False
    example_config_exists = False

    try:
        with open(config_path, "r") as f:
            config = file_to_dict(
                f, cast(Literal["yaml", "yml", "json", "toml"], file_ext)
            )
            config_exists = True
    except FileNotFoundError:
        pass

    try:
        with open(example_config_path, "r") as f:
            example_config = file_to_dict(
                f, cast(Literal["yaml", "yml", "json", "toml"], file_ext)
            )
            example_config_exists = True
    except FileNotFoundError:
        pass

    if not config_exists and not example_config_exists:
        raise FileNotFoundError(
            f"Neither {config_path} nor {example_config_path} exists"
        )

    merged_config = mergedeep.merge(
        example_config, config, strategy=mergedeep.Strategy.TYPESAFE_REPLACE
    )

    if config_file_name_info.ext != "":
        display_ext = "." + config_file_name_info.ext
    else:
        display_ext = ""

    config_display_name = config_file_name_info.name + "{.example,}" + display_ext

    header = f"# Generated from {config_display_name} by runch"
    header += "\n# Please be aware that `float` fields might be annotated as `int` due to the lack of type info in the config."

    with TemporaryDirectory() as temporary_directory_name:
        temporary_directory = Path(temporary_directory_name)
        rand = os.urandom(1).hex()
        output = Path(temporary_directory / f"model_{rand}.py")

        generate(
            merged_config,
            input_file_type=InputFileType.Dict,
            input_filename="placeholder",
            output=output,
            output_model_type=DataModelType.PydanticV2BaseModel,
            custom_file_header=header,
            custom_formatters=["runch.script.custom_formatter"],
            custom_formatters_kwargs={
                "config_file_name": config_file_name_info.name,
                "config_file_ext": config_file_name_info.ext,
                "config_path": config_path,
                "config_type": file_ext,
            },
            snake_case_field=True,
        )
        model: str = output.read_text()

    return model


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            __doc__,
            file=sys.stderr,
        )
        sys.exit(1)

    config_name = sys.argv[1]

    if len(sys.argv) == 3:
        config_ext = sys.argv[2]
    else:
        config_ext = "yaml"

    model = generate_model(config_name, config_ext)
    print(model)
