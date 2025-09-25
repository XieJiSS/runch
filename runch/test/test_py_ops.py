from runch import RunchModel, RunchStrictModel, RunchConfigReader, Runch

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    Runch()


class TestConfig(RunchModel):
    x: int


class TestStrictConfig(RunchStrictModel):
    x: int


test_strict_reader = RunchConfigReader[TestStrictConfig](
    config_name="test_strict.yaml", config_dir="runch/test"
)
test_strict_config = test_strict_reader.read()

test_lazy_strict_reader = RunchConfigReader[TestStrictConfig](
    config_name="test_strict.yaml", config_dir="runch/test"
)
test_lazy_strict_config = test_strict_reader.read_lazy()

test_reader = RunchConfigReader[TestConfig](
    config_name="test.yaml", config_dir="runch/test"
)
test_config = test_reader.read()

test_lazy_reader = RunchConfigReader[TestConfig](
    config_name="test.yaml", config_dir="runch/test"
)
test_lazy_config = test_reader.read_lazy()


def print_and_test(t: str, expected: Any):
    print(f"{t} == {expected}:", end=" ")
    val = eval(t)
    try:
        assert val == expected
        print("passed")
    except AssertionError:
        print("failed")
        raise


print_and_test("isinstance(test_strict_config, Runch)", True)
print_and_test("isinstance(test_lazy_strict_config, Runch)", False)
print_and_test("isinstance(test_config, Runch)", True)
print_and_test("isinstance(test_lazy_config, Runch)", False)
print_and_test("isinstance(test_lazy_config, type(test_lazy_config))", True)
print_and_test("isinstance(test_lazy_config, dict)", False)
