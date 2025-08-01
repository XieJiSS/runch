import re
import os
import sys
import mergedeep # pyright: ignore[reportMissingTypeStubs]

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from datamodel_code_generator import InputFileType, generate
from datamodel_code_generator import DataModelType

from runch._reader import str_to_dict, _SupportedFileType # pyright: ignore[reportPrivateUsage]

from typing import Any, cast

__doc__ = """Usage: python -m runch <config_path> [config_name [config_ext]]
    Generate a model definition from a config file.

    config_path: path to your config file.
    config_name: controls generated variable name and class name.
    config_type: content type of your config file. Default is `yaml`.

    Example:
        python -m runch path/to/my_config.foo
        python -m runch path/to/my_config.foo chat_config
        python -m runch path/to/my_config.foo chat_config yaml"""


@dataclass
class FileNameInfo:
    name: str
    ext: str

    def __str__(self) -> str:
        if self.ext:
            return f"{self.name}.{self.ext}"
        else:
            return self.name


def parse_file_name(file_name: str) -> FileNameInfo:
    # is a path?
    if os.path.sep in file_name:
        raise ValueError(f"Invalid file name: {file_name}")

    name, ext = os.path.splitext(file_name)
    ext = ext[1:]

    return FileNameInfo(name=name, ext=ext)


def generate_model(
    config_path: str, file_type: _SupportedFileType, config_name: str | None = None
):
    if file_type not in ["yaml", "json", "toml"]:
        raise ValueError(f"Unsupported content type: {file_type}")

    config_file_name = os.path.basename(config_path)
    config_file_name_info = parse_file_name(config_file_name)

    if config_file_name_info.name.endswith(".example"):
        config_file_name_info.name = config_file_name_info.name[:-8]
        config_path = os.path.join(
            os.path.dirname(config_path), str(config_file_name_info)
        )

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
            config = str_to_dict(
                f.read(),
                file_type,
                filename=f.name,
            )
            config_exists = True
    except FileNotFoundError:
        pass

    try:
        with open(example_config_path, "r") as f:
            example_config = str_to_dict(
                f.read(),
                file_type,
                filename=f.name,
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

    if config_name is None:
        if len(config_file_name_info.name) == 0:
            raise ValueError(
                "config_name is required as we can't infer it from the provided file name"
            )

        initial_inferred_config_name = config_file_name_info.name

        allowed_leading_chars = re.compile(r"[a-zA-Z_]")
        allowed_chars = re.compile(r"[a-zA-Z0-9_]")

        inferred_config_name = initial_inferred_config_name

        if len(inferred_config_name) == 1 and not allowed_leading_chars.match(
            inferred_config_name
        ):
            raise ValueError(
                f"Invalid inferred config_name: {initial_inferred_config_name}"
            )

        if len(inferred_config_name) > 1:
            # first, select the first valid leading char
            while len(inferred_config_name) > 0 and not allowed_leading_chars.match(
                inferred_config_name[0]
            ):
                inferred_config_name = inferred_config_name[1:]

            if len(inferred_config_name) == 0:
                raise ValueError(
                    f"Invalid inferred config_name: {initial_inferred_config_name}"
                )

            # then, remove all invalid following chars
            curr_checking_index = 1

            while curr_checking_index < len(inferred_config_name):
                has_stripped_chars = False
                while curr_checking_index < len(
                    inferred_config_name
                ) and not allowed_chars.match(
                    inferred_config_name[curr_checking_index]
                ):
                    inferred_config_name = (
                        inferred_config_name[:curr_checking_index]
                        + inferred_config_name[curr_checking_index + 1 :]
                    )
                    has_stripped_chars = True

                if (
                    has_stripped_chars
                    and not inferred_config_name[curr_checking_index - 1] == "_"
                ):
                    # add underscore. data-model-generator will convert snake_case to CamelCase
                    # when generating class names, so we don't need to worry about it
                    inferred_config_name = (
                        inferred_config_name[:curr_checking_index]
                        + "_"
                        + inferred_config_name[curr_checking_index:]
                    )

                if curr_checking_index < len(inferred_config_name):
                    curr_checking_index += 1

        config_name = inferred_config_name.rstrip("_")

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
                "config_file_ext": config_file_name_info.ext,
                "config_name": config_name,
                "config_path": config_path,
                "config_type": file_type,
            },
            snake_case_field=True,
        )
        model: str = output.read_text()

    return model


if __name__ == "__main__":
    # TODO: move to argparse
    if len(sys.argv) < 2:
        print(
            __doc__,
            file=sys.stderr,
        )
        sys.exit(1)

    config_path = sys.argv[1]
    config_name = None
    config_type: _SupportedFileType = "yaml"

    if len(sys.argv) == 3:
        config_name = sys.argv[2]
    elif len(sys.argv) == 4:
        config_name = sys.argv[2]
        config_type = cast(_SupportedFileType, sys.argv[3])
    elif len(sys.argv) > 4:
        print(
            __doc__,
            file=sys.stderr,
        )
        sys.exit(1)

    model = generate_model(config_path, config_type, config_name=config_name)
    print(model)
