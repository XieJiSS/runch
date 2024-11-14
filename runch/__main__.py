import sys
from runch.script.schema_generator import (
    generate_model,
    __doc__ as schema_generator_doc,
)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            schema_generator_doc,
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
