from pathlib import Path
from tempfile import TemporaryDirectory
from datamodel_code_generator import DataModelType, InputFileType, generate

with TemporaryDirectory() as temporary_directory_name:
    temporary_directory = Path(temporary_directory_name)
    output = Path(temporary_directory / "model.py")
    generate(
        {"foo": 1, "bar": {"baz": 2}},
        input_file_type=InputFileType.Dict,
        input_filename="placeholder",
        output=output,
        output_model_type=DataModelType.PydanticV2BaseModel,
        snake_case_field=True,
    )
    model: str = output.read_text()

print(model)
