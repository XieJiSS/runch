from __future__ import annotations

import enum
import logging
import yaml
import pydantic

from pydantic_core import from_json

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Type,
    TypeAlias,
    TypeVar,
    cast,
)
from typing_extensions import deprecated

__all__ = ["RunchModel", "Runch"]

IncEx: TypeAlias = set[int] | set[str] | dict[int, Any] | dict[str, Any] | None
T = TypeVar("T")


class RunchModel(pydantic.BaseModel):
    """`RunchModel` is a pydantic `BaseModel` with extra configurations. All config models should inherit from this class.

    Note: Please avoid using `enum.Enum` as a field type in your `RunchModel`. Pydantic has limited support for enums.
    """

    model_config = pydantic.ConfigDict(
        extra="ignore",
        strict=True,
        protected_namespaces=(),
        use_enum_values=True,
    )

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self.model_fields:
            return default

        try:
            return self.__getattribute__(key)
        except AttributeError:
            return default


class RunchStrictModel(RunchModel):
    """RunchModel but with stricter validation: Disallows unrecognized fields."""

    model_config = pydantic.ConfigDict(
        extra="forbid",
        strict=True,
        protected_namespaces=(),
        use_enum_values=True,
    )

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

class RunchLaxModel(RunchModel):
    """RunchModel but with looser validation: Allows some implicit type conversions."""

    model_config = pydantic.ConfigDict(
        extra="ignore",
        strict=False,
        protected_namespaces=(),
        use_enum_values=True,
    )

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

class RunchLogLevel(enum.IntEnum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class Runch[C: RunchModel](pydantic.RootModel[C]):
    """Runch Config Class

    Args:
        Generic TypeVar `T`: a `RunchModel` defining the schema of a config.

    Raises:
        `ValidationError`: when provided args or kwargs do not match your schema.

    Exmaple:
        ```python
        class Test(RunchModel):
            a: int
            b: str

        config = Runch[Test]({"a": 1, "b": "c"}).config
        print(config.a)
        ```
    """

    if TYPE_CHECKING:
        # User needs to use .config and should not access the .root attribute directly.
        root: None
    else:
        # we need to expose this attribute to pyright for run-time reflection
        root: C

    def __init__(self, *args: Any, **kwargs: Any):
        self.__init_args = args
        self.__init_kwargs = kwargs
        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            *self.__init_args, **self.__init_kwargs
        )

    @property
    def config(self) -> C:
        return cast(C, self.root)

    @config.setter
    def config(self, value: C) -> None:
        self.root = value  # pyright: ignore

    @classmethod
    def signature(cls) -> Type[C]:
        # this is a workaround for dynamic generated generic class `get_args(Runch[type_])` is ().
        # We have to use dynamic generated generic class Runch[type_] because Runch[C] causes the
        # actual type of `C` to be lost.
        # Conclusion: ConfigReader[C] -> type_ = get_generic_arg_kv_map(cls)[C] -> Runch[type_] and
        # Runch[type_].signature() returns type_. This also works for static type Runch[X] where X
        # is a statically defined RunchModel.
        return cls.__signature__.parameters["root"].annotation

    def __getitem__(self, key: str) -> Any:
        return self.config.__getattribute__(key)

    def __setitem__(self, key: str, value: Any) -> None:
        raise NotImplementedError(
            "Runch config is immutable. Use `update` method to create a new config in-place."
        )

    def __iter__(self):
        return iter(self.config)

    def __len__(self):
        return len(self.config.model_fields)

    def __contains__(self, key: str) -> bool:
        return key in self.config.model_fields

    def __repr__(self):
        sig = self.signature()

        return f"<Runch[{sig.__qualname__}]>"

    def __str__(self):
        return repr(self)

    @deprecated("use __getitem__ instead")
    def get(self, key: str, default: Any = None) -> Any:
        try:
            self.config.__getattribute__(key)
        except AttributeError:
            return default

    if TYPE_CHECKING:

        def toJSON(
            self,
            *,
            indent: int | None = None,
            include: IncEx = None,
            exclude: IncEx = None,
            by_alias: bool = False,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
            exclude_none: bool = False,
            round_trip: bool = False,
            warnings: bool = True,
            serialize_as_any: bool = False,
            **dumps_kwargs: Any,
        ) -> str: ...

        to_json = toJSON

    else:

        def toJSON(self, *args: Any, **kwargs: Any) -> str:
            return self.config.model_dump_json(
                *args,
                **kwargs,
            )

        to_json = toJSON

    @classmethod
    def fromJSON(cls, json_str: str):
        type_ = cls.signature()
        return Runch[type_](from_json(json_str))

    @classmethod
    def from_json(cls, json_str: str):
        return cls.fromJSON(json_str)

    if TYPE_CHECKING:

        def toYAML(
            self,
            *,
            allow_unicode: bool = True,
            default_style: str | None = None,
            default_flow_style: bool | None = False,
            canonical: bool | None = None,
            indent: int | None = None,
            width: int | float | None = None,
            line_break: str | None = None,
            explicit_start: bool | None = None,
            explicit_end: bool | None = None,
            version: tuple[int, int] | None = None,
            tags: Mapping[str, str] | None = None,
            sort_keys: bool = True,
            **dumps_kwargs: Any,
        ) -> str: ...

        to_yaml = toYAML

    else:

        def toYAML(
            self,
            *,
            allow_unicode: bool = True,
            **kwargs: Any,
        ) -> str:
            return yaml.safe_dump(
                data=self.toJSON(),
                stream=None,  # make sure we return a string instead of None
                encoding=None,  # make sure we return a string instead of bytes
                allow_unicode=allow_unicode,  # default is changed to True
                **kwargs,
            )

        to_yaml = toYAML

    @classmethod
    def fromYAML(cls, yaml_str: str):
        type_ = cls.signature()
        return Runch[type_](yaml.safe_load(yaml_str))

    @classmethod
    def from_yaml(cls, yaml_str: str):
        return cls.fromYAML(yaml_str)

    if TYPE_CHECKING:

        def toDict(
            self,
            *,
            mode: str | Literal["json", "python"] = "python",
            include: IncEx = None,
            exclude: IncEx = None,
            context: Any | None = None,
            by_alias: bool = False,
            exclude_unset: bool = False,
            exclude_defaults: bool = False,
            exclude_none: bool = False,
            round_trip: bool = False,
            warnings: bool | Literal["none", "warn", "error"] = True,
            serialize_as_any: bool = False,
            **dumps_kwargs: Any,
        ) -> dict[str, Any]: ...

        to_dict = toDict

    else:

        def toDict(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return self.config.model_dump(*args, **kwargs)

        to_dict = toDict

    @classmethod
    def fromDict(
        cls,
        dict_obj: dict[Any, Any],
    ):
        type_ = cls.signature()
        return Runch[type_](dict_obj)

    @classmethod
    def from_dict(cls, dict_obj: dict[Any, Any]):
        return cls.fromDict(dict_obj)

    def update(self, new_runch: Runch[C]):
        """Update (replace) the current config with a new config."""

        self.config = new_runch.config

    # @classmethod
    # def from_model(cls, model: RunchModel):
    #     """Create a new Runch instance from a pydantic model."""
    #     type_ = cls.signature()
    #     return Runch[type_](model.model_dump())
