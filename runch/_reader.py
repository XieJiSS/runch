# pyright: basic
from __future__ import annotations

import asyncio
import inspect
import json
import os
import threading
import tomllib
import weakref
import yaml
import mergedeep

from datetime import datetime
from hashlib import blake2b
from io import StringIO

from runch.exceptions import RunchConfigUnchanged, RunchLookupError

from .runch import Runch, RunchModel, RunchLogLevel
from ._type_utils import get_orig_class, get_generic_arg_kv_map

from collections.abc import Callable, Coroutine, Mapping, MutableMapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    NamedTuple,
    Protocol,
    Self,
    Type,
    TypeVar,
    TypeAlias,
    TypeVarTuple,
    TypedDict,
    assert_type,
    cast,
    get_args,
)


M = TypeVar("M", bound=RunchModel)
FeatureKey: TypeAlias = Literal["watch_update", "merge_example"]
AsyncFeatureKey: TypeAlias = Literal["watch_update"]
SupportedFileType: TypeAlias = Literal["yaml", "json", "toml"]

_UserCustomFileType: TypeAlias = Literal["_user_custom"]
_USER_CUSTOM_FILE_TYPE: _UserCustomFileType = "_user_custom"

_RUNCH_DEFAULT_CONFIG_DIR = os.environ.get(
    "RUNCH_CONFIG_DIR", os.path.join(os.getcwd(), "etc")
)

_SupportedFileType: TypeAlias = SupportedFileType | _UserCustomFileType

_normalized_supported_file_types: set[str] = set(get_args(SupportedFileType))


class RunchCompatibleLogger(Protocol):

    def log(
        self,
        level: RunchLogLevel,
        msg: str,
        /,
        *,
        runch_config: Runch[Any] | None,
        exc_info: BaseException | None = None,
        **kwargs: Any,
    ) -> None: ...


class FeatureConfig(TypedDict):
    enabled: bool
    args: dict[str, Any]


def str_to_dict(
    s: str,
    filetype: _SupportedFileType,
    *,
    filename: str,
    custom_loader: Callable[[str], dict[Any, Any]] | None = None,
) -> dict[Any, Any]:
    if custom_loader is not None:
        # custom loader is provided, we don't care about the file extension. we return whatever the custom loader returns
        # without checking if it is a dict. it is the user's responsibility to ensure the returned data is what they want
        return custom_loader(s)

    if filetype == "yaml":
        f = StringIO(s)
        config_dict = yaml.safe_load(f)
        # yaml.safe_load may return None if the file is empty, we should make an empty config be a valid config
        if config_dict is None:
            config_dict = {}
        if not isinstance(config_dict, dict):
            raise TypeError(
                f"Invalid config format: {filename} type={type(config_dict)}, expecting a dict"
            )
        return cast(dict[Any, Any], config_dict)
    elif filetype == "json":
        config_dict = json.loads(s)
        # we may got a list or even a string / number from json.load, and runtime type checking for these is not supported
        if not isinstance(config_dict, dict):
            raise TypeError(
                f"Invalid config format: {filename} type={type(config_dict)}, expecting a dict"
            )
        return cast(dict[Any, Any], config_dict)
    elif filetype == "toml":
        # According to tomllib docs, a whole toml document is always parsed into a dict
        return tomllib.loads(s)
    elif filetype == _USER_CUSTOM_FILE_TYPE:
        if custom_loader is None:
            raise ValueError(
                "custom_loader must be provided when reading configs from user custom file type"
            )
        return custom_loader(s)
    else:
        # dead code just for completeness
        assert_type("dead code reached", None)
        raise ValueError(f"Unsupported file type: {filetype}")


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


class VersionedConfig(NamedTuple):
    config: dict[Any, Any]
    version: bytes


def read_config(
    config_name: str,
    config_dir: str,
    config_type: SupportedFileType | str = "yaml",
    config_encoding: str = "utf-8",
    *,
    custom_loader: Callable[[str], dict[Any, Any]] | None = None,
    should_merge_example: bool = False,
) -> VersionedConfig:
    real_config_path = os.path.join(config_dir, config_name)

    config_file_name_info = parse_file_name(config_name)

    example_config_name = ".".join(
        [config_file_name_info.name, "example", config_file_name_info.ext]
    )
    example_config_path = os.path.join(config_dir, example_config_name)

    if not should_merge_example:
        with open(real_config_path, "rb") as f:
            content_bytes = f.read()
            content = content_bytes.decode(encoding=config_encoding)
            version = blake2b(content_bytes).digest()
            if config_type in _normalized_supported_file_types:
                return VersionedConfig(
                    config=str_to_dict(
                        content,
                        cast(_SupportedFileType, config_type),
                        filename=f.name,
                        custom_loader=custom_loader,
                    ),
                    version=version,
                )
            else:
                return VersionedConfig(
                    config=str_to_dict(
                        content,
                        _USER_CUSTOM_FILE_TYPE,
                        filename=f.name,
                        custom_loader=custom_loader,
                    ),
                    version=version,
                )

    real_config: dict[Any, Any] = {}
    example_config: dict[Any, Any] = {}

    real_config_exists = False
    example_config_exists = False

    raw_configs_bytes = b""

    try:
        with open(real_config_path, "rb") as f:
            content_bytes = f.read()
            raw_configs_bytes += content_bytes
            real_config = str_to_dict(
                content_bytes.decode(encoding=config_encoding),
                cast(_SupportedFileType, config_type),
                filename=f.name,
                custom_loader=custom_loader,
            )
            real_config_exists = True
    except FileNotFoundError:
        pass

    try:
        with open(example_config_path, "rb") as f:
            content_bytes = f.read()
            raw_configs_bytes += content_bytes
            example_config = str_to_dict(
                content_bytes.decode(encoding=config_encoding),
                cast(_SupportedFileType, config_type),
                filename=f.name,
                custom_loader=custom_loader,
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
    return VersionedConfig(
        config=merged_config, version=blake2b(raw_configs_bytes).digest()
    )


_CONFIG_READER_DEFAULT_FEATURES: dict[FeatureKey, FeatureConfig] = {
    "watch_update": FeatureConfig(enabled=False, args={}),
    "merge_example": FeatureConfig(enabled=False, args={}),
}

_CUSTOM_A_CONFIG_READER_DEFAULT_FEATURES: dict[AsyncFeatureKey, FeatureConfig] = {
    "watch_update": FeatureConfig(enabled=False, args={}),
}

T = TypeVar("T")
U = TypeVarTuple("U")


def _run_sync_in_background(func: Callable[[*U], T], *args: *U) -> None:
    def thread_entry():
        func(*args)

    thread = threading.Thread(target=thread_entry, daemon=True)
    thread.start()


class LoggableConfigReader:
    _config_name: str
    _config: Runch[Any] | None

    _config_logger: RunchCompatibleLogger | None

    def __init__(self, config_logger: RunchCompatibleLogger | None) -> None:
        self._config_logger = config_logger

    def set_logger(self, config_logger: RunchCompatibleLogger | None) -> None:
        self._config_logger = config_logger

    def _log(
        self,
        level: RunchLogLevel,
        msg: str,
        exc_info: BaseException | None = None,
        **kwargs: Any,
    ):
        if (logger := self._config_logger) is not None:
            logger.log(
                level,
                f"{type(self).__name__}(name={self._config_name}): {msg}",
                exc_info=exc_info,
                runch_config=self._config,
                **kwargs,
            )

    def _debug(self, msg: str, exc_info: BaseException | None = None, **kwargs: Any):
        self._log(RunchLogLevel.DEBUG, msg, exc_info=exc_info, **kwargs)

    def _info(self, msg: str, exc_info: BaseException | None = None, **kwargs: Any):
        self._log(RunchLogLevel.INFO, msg, exc_info=exc_info, **kwargs)

    def _warning(self, msg: str, exc_info: BaseException | None = None, **kwargs: Any):
        self._log(RunchLogLevel.WARNING, msg, exc_info=exc_info, **kwargs)

    def _error(self, msg: str, exc_info: BaseException | None = None, **kwargs: Any):
        self._log(RunchLogLevel.ERROR, msg, exc_info=exc_info, **kwargs)

    def _critical(self, msg: str, exc_info: BaseException | None = None, **kwargs: Any):
        self._log(RunchLogLevel.CRITICAL, msg, exc_info=exc_info, **kwargs)


class RunchConfigReader[C: RunchModel](LoggableConfigReader):
    _config_name: str
    _config_dir: str
    _config_type: SupportedFileType | str
    _config_encoding: str

    _config_schema: Type[C]
    _config: Runch[C] | None
    _config_version: bytes | None
    _config_updated_at: datetime | None

    _custom_config_parser: Callable[[str], dict[Any, Any]] | None

    _features: MutableMapping[FeatureKey, FeatureConfig]
    _auto_update_started: bool

    if TYPE_CHECKING:
        # this attribute is defined on the Generic class, simply adding it here to avoid pyright error
        __orig_class__: Type[RunchConfigReader[C]]

    def __init__(
        self,
        config_name: str,
        config_dir: str = _RUNCH_DEFAULT_CONFIG_DIR,
        config_type: SupportedFileType | str = "yaml",
        config_encoding: str = "utf-8",
        *,
        custom_config_parser: Callable[[str], dict[Any, Any]] | None = None,
        logger: RunchCompatibleLogger | None = None,
        features: Mapping[FeatureKey, FeatureConfig] | None = None,
    ):
        super().__init__(config_logger=logger)

        self._config = None
        self._config_name = config_name
        self._config_dir = config_dir
        self._config_type = config_type
        self._config_encoding = config_encoding
        self._config_schema = get_generic_arg_kv_map(get_orig_class(self))[C]
        self._custom_config_parser = custom_config_parser
        self._features = {}
        self._config_updated_at = None
        self._config_version = None
        self._auto_update_started = False

        if features is not None:
            for feature, value in features.items():
                self.set_feature(feature, value)

        # make sure _features is always fully initialized
        for feature, value in _CONFIG_READER_DEFAULT_FEATURES.items():
            if feature not in self._features:
                self.set_feature(feature, value)

    def read(self) -> Runch[C]:
        """Load config from file. If the config has been loaded before, it will be returned directly.

        Use `update` to force reload the config.

        This method is not thread-safe.

        Returns:
            Runch[C]: The loaded config.
        """
        if self._config is not None:
            return self._config

        type_ = self._config_schema

        try:
            versioned_config = read_config(
                self._config_name,
                self._config_dir,
                self._config_type,
                self._config_encoding,
                custom_loader=self._custom_config_parser,
                should_merge_example=self._features["merge_example"]["enabled"],
            )
        except Exception as e:
            self._error("config read failed", exc_info=e)
            raise

        try:
            self._config = Runch[type_].fromDict(versioned_config.config)
        except Exception as e:
            self._error("config validate failed", exc_info=e)
            raise

        self._info("config initialized")

        self._config_version = versioned_config.version
        self._config_updated_at = datetime.now()

        return self._config

    def update(
        self,
        *,
        overwrite_uninitialized: bool = False,
        on_error: Literal["ignore", "raise"] = "ignore",
    ):
        """This function will try to update the config base on the latest config file.

        Args:
            overwrite_uninitialized (bool, optional): _If set to False, then update() will become a noop before read() is ever called. This can have side effects when used together with `read_lazy()`._
            Defaults to `False`.

            on_error ("raise" | "ignore" , optional): _Specifies the behavior when errors occurred during an attempt to update this config._
            Defaults to `"ignore"`, which means ignore the error and keep the old config.
        """

        if self._config is None:
            if self._config_updated_at is not None:
                raise RuntimeError(
                    "update: _config is None but _config_updated_at is not None. This is a bug."
                )
            if overwrite_uninitialized:
                # force update even if the config is not initialized due to lazy load
                try:
                    self.read()
                except Exception:
                    if on_error == "raise":
                        raise

            return

        type_ = self._config_schema

        try:
            versioned_config = read_config(
                self._config_name,
                self._config_dir,
                self._config_type,
                self._config_encoding,
                custom_loader=self._custom_config_parser,
                should_merge_example=self._features["merge_example"]["enabled"],
            )
        except Exception as e:
            self._error("config load failed", exc_info=e)
            if on_error == "raise":
                raise
            else:
                return

        if self._config_version == versioned_config.version:
            return

        try:
            new_config = Runch[type_].fromDict(versioned_config.config)
        except Exception as e:
            self._error("config validate failed", exc_info=e)
            if on_error == "raise":
                raise
            else:
                return

        self._config.update(new_config)
        self._config_version = versioned_config.version
        self._config_updated_at = datetime.now()

        self._info("config changed", version=self._config_version)

    def read_lazy(self) -> Runch[C]:
        """
        Returns a lazy proxy object that will not read the config until any attribute is accessed

        Type checks are also postponed

        :return: a `Proxy()` that will evaluates to `Runch[C]` when accessed
        """
        type_ = self._config_schema
        that = self

        class Proxy:
            def __instancecheck__(self, instance: Any) -> bool:
                if type(instance) is Proxy:
                    return True
                return False

            def __getattribute__(self, name: str) -> Any:
                if name == "__class__":
                    return type(self)
                if name == "__instancecheck__":
                    return inspect.getattr_static(self, name)

                if that._config is not None:
                    return that._config.__getattribute__(name)

                try:
                    versioned_config = read_config(
                        that._config_name,
                        that._config_dir,
                        that._config_type,
                        that._config_encoding,
                        custom_loader=that._custom_config_parser,
                        should_merge_example=that._features["merge_example"]["enabled"],
                    )
                except Exception as e:
                    that._error("config load failed", exc_info=e)
                    raise

                # no need to check if config_version matches, because we are sure it is None
                try:
                    that._config = Runch[type_].fromDict(versioned_config.config)
                except Exception as e:
                    that._error("config validate failed", exc_info=e)
                    raise

                that._config_version = versioned_config.version
                that._config_updated_at = datetime.now()

                that._info("lazy config evaluated")

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
        - feature="watch_update": Automatically update the config every `n` seconds.
            - args: `{"update_interval": n, "on_update_error": "ignore" | "raise"}`, where `update_interval` is always required.
        - feature="merge_example": Merge the example config with the actual config. This is useful for development.
            - args: `{}`.
        """
        self._features[feature] = feature_config

        if feature == "watch_update" and feature_config["enabled"]:
            self._start_auto_update()

        return self

    def enable_feature(self, feature: FeatureKey, args: dict[str, Any]) -> Self:
        return self.set_feature(feature, FeatureConfig(enabled=True, args=args))

    def disable_feature(self, feature: FeatureKey) -> Self:
        return self.set_feature(feature, FeatureConfig(enabled=False, args={}))

    def _start_auto_update(self):
        if not self._features["watch_update"]["enabled"]:
            return

        if "update_interval" not in self._features["watch_update"]["args"]:
            raise ValueError("watch_update feature requires `update_interval` in args")

        if "on_update_error" in self._features["watch_update"]["args"]:
            on_update_error = self._features["watch_update"]["args"]["on_update_error"]
            if on_update_error not in ["ignore", "raise"]:
                self._critical('on_update_error must be either "ignore" or "raise"')
                raise ValueError('on_update_error must be either "ignore" or "raise"')
        else:
            # will fallback to default later
            on_update_error = None

        if self._auto_update_started:
            return

        self._auto_update_started = True

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

                await asyncio.sleep(
                    self_._features["watch_update"]["args"]["update_interval"]
                )

                if not self_._features["watch_update"]["enabled"]:
                    # auto update is turned off
                    break

                if on_update_error is not None:
                    self_.update(
                        overwrite_uninitialized=False, on_error=on_update_error
                    )
                else:
                    self_.update(overwrite_uninitialized=False)

                del self_

            self_ = self_ref()
            if self_ is not None:
                self_._auto_update_started = False

        def watchdog():
            asyncio.run(a_watchdog())

        _run_sync_in_background(watchdog)

    def __del__(self):
        if not hasattr(self, "_features"):
            # not initialized yet
            return
        self.set_feature("watch_update", FeatureConfig(enabled=False, args={}))

    def close(self):
        if not hasattr(self, "_features"):
            # not initialized yet
            return
        self.set_feature("watch_update", FeatureConfig(enabled=False, args={}))


class RunchAsyncCustomConfigReader[C: RunchModel](LoggableConfigReader):
    _config_name: str
    _config_encoding: str

    _config_schema: Type[C]
    _config: Runch[C] | None
    _config_updated_at: datetime | None

    _config_loader: Callable[[str], Coroutine[Any, Any, C]]

    _features: MutableMapping[AsyncFeatureKey, FeatureConfig]
    _auto_update_started: bool

    if TYPE_CHECKING:
        # this attribute is defined on the Generic class, simply adding it here to avoid pyright error
        __orig_class__: Type[RunchConfigReader[C]]

    def __init__(
        self,
        config_name: str,
        config_encoding: str = "utf-8",
        *,
        config_loader: Callable[[str], Coroutine[Any, Any, C]],
        logger: RunchCompatibleLogger | None = None,
        features: Mapping[AsyncFeatureKey, FeatureConfig] | None = None,
    ):
        super().__init__(config_logger=logger)

        orig_class: type[Any] = get_orig_class(self)

        self._config = None
        self._config_updated_at = None
        self._config_name = config_name
        self._config_encoding = config_encoding
        self._config_schema = get_generic_arg_kv_map(orig_class)[C]
        self._config_loader = config_loader
        self._features = {}
        self._auto_update_started = False

        if features is not None:
            for feature, value in features.items():
                self.set_feature(feature, value)

        # make sure _features is always fully initialized
        for feature, value in _CUSTOM_A_CONFIG_READER_DEFAULT_FEATURES.items():
            if feature not in self._features:
                self.set_feature(feature, value)

    async def read(self) -> Runch[C]:
        """Load config from file. If the config has been loaded before, it will be returned directly.

        Use `update` to force reload the config.

        This method is not thread-safe.

        Returns:
            Runch[C]: The loaded config.
        """
        if self._config is not None:
            return self._config

        type_ = self._config_schema

        try:
            config = await self._config_loader(self._config_name)
        except Exception as e:
            self._error("config load failed", exc_info=e)
            raise

        if (
            self._config_updated_at is None
            and self._features["watch_update"]["enabled"]
            and not self._auto_update_started
        ):
            self._start_auto_update()

        try:
            self._config = Runch[type_](config)
        except Exception as e:
            self._error("config validate failed", exc_info=e)
            raise

        self._info("config initialized")

        self._config_updated_at = datetime.now()

        return self._config

    def read_cached(self) -> Runch[C]:
        """
        Return the cached config value. If no cached value exists, raise an exception.

        Raises:
            RunchLookupError: The config is not initialized yet.

        Returns:
            Runch[C: RunchModel]: The cached config value returned by the most recent successful call to the config loader.
        """
        if self._config is not None:
            return self._config

        self._critical("missing cached config value")

        raise RunchLookupError(
            f"RunchAsyncCustomConfig {self._config_name} has no cached config value."
        )

    async def update(
        self,
        *,
        overwrite_uninitialized: bool = False,
        on_error: Literal["ignore", "raise"] = "ignore",
    ):
        """This function will try to update the config base on the latest config file.

        Args:
            overwrite_uninitialized (bool, optional): _If set to False, then update() will become a noop before read() is ever called. This can have side effects when used together with `read_lazy()`._
            Defaults to `False`.

            on_error ("raise" | "ignore", optional): _Specifies the behavior when errors occurred during an attempt to update this config._
            Defaults to `"ignore"`, which means ignore the error and keep the old config.
        """

        if self._config is None:
            if self._config_updated_at is not None:
                self._critical("inconsistent _config and _config_updated_at")
                raise RuntimeError(
                    "update: _config is None but _config_updated_at is not None. This is a bug."
                )
            if overwrite_uninitialized:
                # force update even if the config is not initialized due to lazy load
                try:
                    await self.read()
                except Exception:
                    if on_error == "raise":
                        raise

            return

        type_ = self._config_schema

        try:
            new_config = Runch[type_](await self._config_loader(self._config_name))
        except RunchConfigUnchanged:
            return
        except Exception as e:
            self._error("config update failed", exc_info=e)
            if on_error == "raise":
                raise
            else:
                return

        self._config.update(new_config)
        self._config_updated_at = datetime.now()

        self._info("config changed")

    def set_feature(
        self, feature: AsyncFeatureKey, feature_config: FeatureConfig
    ) -> Self:
        """Set a feature's configuration. See **Features** section for available features.

        Args:
            feature (AsyncFeatureKey): The feature's key
            value (FeatureConfig): The feature's configuration.
              - enabled: Whether the feature is enabled
              - args: The arguments for the feature

        ## Features
        - feature="watch_update": Automatically update the config every `n` seconds.
            - args: `{"update_interval": n, "on_update_error": "ignore" | "raise"}`, where `update_interval` is always required.
        """
        self._features[feature] = feature_config

        if (
            feature == "watch_update"
            and feature_config["enabled"]
            and self._config_updated_at is not None
        ):
            self._start_auto_update()

        return self

    def enable_feature(self, feature: AsyncFeatureKey, args: dict[str, Any]) -> Self:
        return self.set_feature(feature, FeatureConfig(enabled=True, args=args))

    def disable_feature(self, feature: AsyncFeatureKey) -> Self:
        return self.set_feature(feature, FeatureConfig(enabled=False, args={}))

    def _start_auto_update(self):
        if not self._features["watch_update"]["enabled"]:
            return

        if "update_interval" not in self._features["watch_update"]["args"]:
            self._critical("watch_update feature requires `update_interval` in args")
            raise ValueError("watch_update feature requires `update_interval` in args")

        if "on_update_error" in self._features["watch_update"]["args"]:
            on_update_error = self._features["watch_update"]["args"]["on_update_error"]
            if on_update_error not in ["ignore", "raise"]:
                self._critical('on_update_error must be either "ignore" or "raise"')
                raise ValueError('on_update_error must be either "ignore" or "raise"')
        else:
            # will fallback to default later
            on_update_error = None

        if self._auto_update_started:
            return

        self._auto_update_started = True

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

                await asyncio.sleep(
                    self_._features["watch_update"]["args"]["update_interval"]
                )

                if not self_._features["watch_update"]["enabled"]:
                    # auto update is turned off
                    break

                if on_update_error is not None:
                    await self_.update(
                        overwrite_uninitialized=False, on_error=on_update_error
                    )
                else:
                    await self_.update(overwrite_uninitialized=False)

                del self_

            self_ = self_ref()
            if self_ is not None:
                self_._auto_update_started = False

        def watchdog():
            asyncio.run(a_watchdog())

        _run_sync_in_background(watchdog)

    def __del__(self):
        if not hasattr(self, "_features"):
            # not initialized yet
            return
        self.set_feature("watch_update", FeatureConfig(enabled=False, args={}))

    def close(self):
        if not hasattr(self, "_features"):
            # not initialized yet
            return
        self.set_feature("watch_update", FeatureConfig(enabled=False, args={}))


def require_lazy_runch_configs(*runches: Runch[Any]):
    """
    This function is used to force evaluation of runch configs, useful if you are using read_lazy().
    """
    for runch in runches:
        # access any attribute (e.g. __module__) to force evaluation.
        runch.config.__module__
