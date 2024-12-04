from __future__ import annotations

import asyncio
import json
import os
import threading
import tomllib
import weakref
import yaml
import mergedeep

from asyncer import asyncify

from .runch import Runch, RunchModel
from ._type_utils import get_orig_class, get_generic_arg_kv_map

from collections.abc import Callable, Mapping, MutableMapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Self,
    TextIO,
    Type,
    TypeVar,
    TypeAlias,
    TypeVarTuple,
    TypedDict,
    Unpack,
    assert_type,
    cast,
    get_args,
)


M = TypeVar("M", bound=RunchModel)
FeatureKey: TypeAlias = Literal["watch_file_update", "merge_example"]
SupportedExtension: TypeAlias = Literal[
    "yaml", "YAML", "yml", "YML", "json", "JSON", "toml", "TOML"
]

_UserCustomFileType: TypeAlias = Literal["_user_custom"]
_USER_CUSTOM_FILE_TYPE: _UserCustomFileType = "_user_custom"

_RUNCH_DEFAULT_CONFIG_DIR = os.environ.get(
    "RUNCH_CONFIG_DIR", os.path.join(os.getcwd(), "etc")
)

_BuiltinSupportedFileType: TypeAlias = Literal["yaml", "yml", "json", "toml"]
_SupportedFileType: TypeAlias = _BuiltinSupportedFileType | _UserCustomFileType

_normalized_supported_extensions: set[str] = set(get_args(_BuiltinSupportedFileType))


class FeatureConfig(TypedDict):
    enabled: bool
    args: tuple[Any, ...]


def file_to_dict(
    f: TextIO,
    ext: _SupportedFileType,
    *,
    custom_loader: Callable[[str], dict[Any, Any]] | None = None,
) -> dict[Any, Any]:
    if custom_loader is not None:
        # custom loader is provided, we don't care about the file extension. we return whatever the custom loader returns
        # without checking if it is a dict. it is the user's responsibility to ensure the returned data is what they want
        return custom_loader(f.read())

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
        # According to tomllib docs, a whole toml document is always parsed into a dict
        return tomllib.loads(f.read())
    elif ext == _USER_CUSTOM_FILE_TYPE:
        if custom_loader is None:
            raise ValueError(
                "custom_loader must be provided when reading configs from user custom file type"
            )
        # dead code just for completeness
        assert_type("dead code reached", None)
        return custom_loader(f.read())
    else:
        # dead code just for completeness
        assert_type("dead code reached", None)
        raise ValueError(f"Unsupported file type: {ext}")


def read_config(
    config_name: str,
    config_dir: str,
    config_ext: SupportedExtension | str = "yaml",
    config_encoding: str = "utf-8",
    *,
    custom_loader: Callable[[str], dict[Any, Any]] | None = None,
    should_merge_example: bool = False,
) -> dict[Any, Any]:
    file_ext = config_ext.lower()
    real_config_path = os.path.join(config_dir, f"{config_name}.{file_ext}")
    example_config_path = os.path.join(config_dir, f"{config_name}.example.{file_ext}")

    if not should_merge_example:
        with open(real_config_path, "r", encoding=config_encoding) as f:
            if file_ext in _normalized_supported_extensions:
                return file_to_dict(
                    f, cast(_SupportedFileType, file_ext), custom_loader=custom_loader
                )
            else:
                return file_to_dict(
                    f, _USER_CUSTOM_FILE_TYPE, custom_loader=custom_loader
                )

    real_config: dict[Any, Any] = {}
    example_config: dict[Any, Any] = {}

    real_config_exists = False
    example_config_exists = False

    try:
        with open(real_config_path, "r", encoding=config_encoding) as f:
            real_config = file_to_dict(
                f, cast(_SupportedFileType, file_ext), custom_loader=custom_loader
            )
            real_config_exists = True
    except FileNotFoundError:
        pass

    try:
        with open(example_config_path, "r", encoding=config_encoding) as f:
            example_config = file_to_dict(
                f, cast(_SupportedFileType, file_ext), custom_loader=custom_loader
            )
            example_config_exists = True
    except FileNotFoundError:
        pass

    if not real_config_exists and not example_config_exists:
        raise FileNotFoundError(
            f"Neither {real_config_path} nor {example_config_path} exists"
        )

    merged_config = cast(
        dict[str, Any],
        mergedeep.merge(
            example_config, real_config, strategy=mergedeep.Strategy.TYPESAFE_REPLACE
        ),
    )
    return merged_config


_CONFIG_READER_DEFAULT_FEATURES: dict[FeatureKey, FeatureConfig] = {
    "watch_file_update": FeatureConfig(enabled=False, args=()),
    "merge_example": FeatureConfig(enabled=False, args=()),
}


def update_reader_default_feature(
    feature_name: FeatureKey, feature_config: FeatureConfig
):
    _CONFIG_READER_DEFAULT_FEATURES[feature_name] = feature_config


def set_reader_default_features(features: dict[FeatureKey, FeatureConfig]):
    valid_feature_keys = FeatureKey.__args__

    _old_features = _CONFIG_READER_DEFAULT_FEATURES.copy()
    _CONFIG_READER_DEFAULT_FEATURES.clear()
    _CONFIG_READER_DEFAULT_FEATURES.update(features)

    for key in valid_feature_keys:
        if key not in _CONFIG_READER_DEFAULT_FEATURES:
            # refuse invalid input and restore the old features
            _CONFIG_READER_DEFAULT_FEATURES.clear()
            _CONFIG_READER_DEFAULT_FEATURES.update(_old_features)
            raise ValueError(f"Feature key {key} not in CONFIG_READER_DEFAULT_FEATURES")

    for key in _CONFIG_READER_DEFAULT_FEATURES:
        if key not in valid_feature_keys:
            # refuse invalid input and restore the old features
            _CONFIG_READER_DEFAULT_FEATURES.clear()
            _CONFIG_READER_DEFAULT_FEATURES.update(_old_features)
            raise ValueError(f"Feature key {key} is not recognized")


T = TypeVar("T")
U = TypeVarTuple("U")


def _run_sync_in_background(func: Callable[[Unpack[U]], T], *args: Unpack[U]) -> None:
    def thread_entry():
        func(*args)

    thread = threading.Thread(target=thread_entry, daemon=True)
    thread.start()


class RunchConfigReader[C: RunchModel]:
    _config_name: str
    _config_dir: str
    _config_ext: SupportedExtension | str
    _config_encoding: str

    _config_schema: Type[C]
    _config: Runch[C] | None

    _custom_config_loader: Callable[[str], dict[Any, Any]] | None
    _features: MutableMapping[FeatureKey, FeatureConfig]
    _is_updating: bool

    if TYPE_CHECKING:
        # this attribute is defined on the Generic class, simply adding it here to avoid pyright error
        __orig_class__: Type[RunchConfigReader[C]]

    def __init__(
        self,
        config_name: str,
        config_dir: str = _RUNCH_DEFAULT_CONFIG_DIR,
        config_ext: SupportedExtension | str = "yaml",
        config_encoding: str = "utf-8",
        *,
        custom_config_loader: Callable[[str], dict[Any, Any]] | None = None,
        features: Mapping[FeatureKey, FeatureConfig] | None = None,
    ):
        self._config = None
        self._config_name = config_name
        self._config_dir = config_dir
        self._config_ext = config_ext
        self._config_encoding = config_encoding
        self._config_schema = get_generic_arg_kv_map(get_orig_class(self))[C]
        self._custom_config_loader = custom_config_loader
        self._features = {}
        self._is_updating = False

        if features is not None:
            for feature, value in features.items():
                self.set_feature(feature, value)

        # make sure _features is always fully initialized
        for feature, value in _CONFIG_READER_DEFAULT_FEATURES.items():
            if feature not in self._features:
                self.set_feature(feature, value)

    def read(self) -> Runch[C]:
        if self._config is not None:
            return self._config

        type_ = self._config_schema
        config = read_config(
            self._config_name,
            self._config_dir,
            self._config_ext,
            self._config_encoding,
            custom_loader=self._custom_config_loader,
            should_merge_example=self._features["merge_example"]["enabled"],
        )

        self._config = Runch[type_].fromDict(config)
        return self._config

    async def read_async(self) -> Runch[C]:
        return await asyncify(self.read)()

    def update(self, *, overwrite_uninitialized: bool = True):
        if self._config is None:
            if overwrite_uninitialized:
                # force update even if the config is not initialized due to lazy load
                self.read()

            return

        type_ = self._config_schema
        raw_config = read_config(
            self._config_name,
            self._config_dir,
            self._config_ext,
            self._config_encoding,
            custom_loader=self._custom_config_loader,
            should_merge_example=self._features["merge_example"]["enabled"],
        )

        new_config = Runch[type_].fromDict(raw_config)
        self._config.update(new_config)

    def read_lazy(self) -> Runch[C]:
        """
        Returns a lazy proxy object that will not read the config until any attribute is accessed

        Type checks are also postponed
        """
        type_ = self._config_schema
        that = self

        class Proxy:
            def __getattribute__(self, name: str) -> Any:
                if that._config is not None:
                    return that._config.__getattribute__(name)

                config = read_config(
                    that._config_name,
                    that._config_dir,
                    that._config_ext,
                    that._config_encoding,
                    custom_loader=that._custom_config_loader,
                    should_merge_example=that._features["merge_example"]["enabled"],
                )
                that._config = Runch[type_].fromDict(config)

                return that._config.__getattribute__(name)

            def __repr__(self) -> str:
                if that._config is not None:
                    return f"<Proxy of {repr(that._config)}>"
                return f"<Proxy of {repr(Runch[type_])} (not evaluated yet)>"

        return Proxy()  # pyright: ignore[reportReturnType]

    def set_feature(self, feature: FeatureKey, feature_config: FeatureConfig) -> Self:
        """Set a feature's configuration. See **Features** section for available features.

        Args:
            feature (FeatureKey): The feature's key
            value (FeatureConfig): The feature's configuration.
              - enabled: Whether the feature is enabled
              - args: The arguments for the feature

        ## Features
        - feature="watch_file_update": Automatically update the config every `n` seconds. `n` should be passed as the only element in `FeatureConfig`'s `args`.
        - feature="merge_example": Merge the example config with the actual config. This is useful for development. Should always pass empty tuple `()` as `args`.
        """
        self._features[feature] = feature_config

        if feature == "watch_file_update" and feature_config["enabled"]:
            self._start_auto_update()

        return self

    def enable_feature(self, feature: FeatureKey, *args: Any) -> Self:
        return self.set_feature(feature, FeatureConfig(enabled=True, args=args))

    def disable_feature(self, feature: FeatureKey) -> Self:
        return self.set_feature(feature, FeatureConfig(enabled=False, args=()))

    def _start_auto_update(self):
        if not self._features["watch_file_update"]["enabled"]:
            return
        if len(self._features["watch_file_update"]["args"]) != 1:
            raise ValueError(
                "watch_file_update feature must have exactly one argument: update interval in seconds"
            )

        if self._is_updating:
            return

        self._is_updating = True

        # use weakref to avoid circular reference to `self`
        self_ref = weakref.ref(self)

        # watchdog will stop automatically if the feature is disabled / the reader is deleted
        async def a_watchdog():
            # NOTE: under very rare circumstances, the auto update watchdog thread may not be able to be recreated.
            # That is, if the user disables this feature, watchdog will quit in the next iteration. However, if the
            # user enables the feature again between the `break` of `while True` and `self._auto_updating = False`,
            # the new watchdog thread will not be created due to the `if self._auto_updating` check.
            # This is a very very rare edge case and is not quite fixable without adding a lock and some complexity.
            while True:
                self_ = self_ref()
                if self_ is None:
                    # reader is deleted
                    break

                if not self_._features["watch_file_update"]["enabled"]:
                    break

                await asyncio.sleep(self_._features["watch_file_update"]["args"][0])

                if not self_._features["watch_file_update"]["enabled"]:
                    break

                self_.update(overwrite_uninitialized=False)
                del self_

            self_ = self_ref()
            if self_:
                self_._is_updating = False

        def watchdog():
            asyncio.run(a_watchdog())

        _run_sync_in_background(watchdog)

    def __del__(self):
        self.set_feature("watch_file_update", FeatureConfig(enabled=False, args=()))

    def close(self):
        self.__del__()


def require_lazy_runch_configs(*runches: Runch[Any]):
    """
    This function is used to force evaluation of runch configs, useful if you are using read_lazy().
    """
    for runch in runches:
        # access any attribute (e.g. __module__) to force evaluation.
        runch.config.__module__
