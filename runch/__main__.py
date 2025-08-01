import sys

from runch.script.schema_generator import (
    generate_model,
    __doc__ as schema_generator_doc,
)
from runch._reader import _SupportedFileType  # pyright: ignore[reportPrivateUsage]

from typing import cast

if __name__ == "__main__":
    # TODO: move to argparse

    if len(sys.argv) < 2:
        print(
            schema_generator_doc,
            file=sys.stderr,
        )
        sys.exit(1)

    config_path = sys.argv[1]
    config_name = None
    config_ext: _SupportedFileType = "yaml"

    if len(sys.argv) == 3:
        config_name = sys.argv[2]
    elif len(sys.argv) == 4:
        config_name = sys.argv[2]
        config_ext = cast(_SupportedFileType, sys.argv[3])
    elif len(sys.argv) > 4:
        print(
            __doc__,
            file=sys.stderr,
        )
        sys.exit(1)

    model = generate_model(config_path, config_ext, config_name=config_name)
    print(model)
