import sys
import typing

from typing import (
    Any,
    Generic,
    ParamSpec,
    Type,
    TypeVar,
    TypeVarTuple,
    get_args,
    get_origin,
)

_typing_3_7 = False
try:
    from typing import ForwardRef as _

    _typing_3_7 = True
except:
    pass

T = TypeVar("T")


def is_generic(tp: Type[Any]):
    """adapted from pytypes.get_orig_class: Check if a type is a generic type."""
    try:
        return isinstance(tp, typing.GenericMeta)  # type: ignore
    except AttributeError:
        try:
            return issubclass(tp, typing.Generic)
        except AttributeError:
            return False
        except TypeError:
            return isinstance(tp, typing._GenericAlias)  # type: ignore


def unwrap[T](x: T | None) -> T:
    if x is None:
        raise Exception("unwrap: arg should not be None")
    return x


def currentframe():
    """adapted from pytypes.get_orig_class: Return the frame of the caller."""
    if hasattr(sys, "_getframe"):
        return sys._getframe(1)  # type: ignore
    raise ValueError("No frame information")


def get_orig_class(obj: Any, default_to__class__: bool = False) -> Any:
    """adapted from pytypes.get_orig_class:

    Robust way to access `obj.__orig_class__`. Compared to a direct access this has the
    following advantages:
    1) It works around https://github.com/python/typing/issues/658.
    2) It prevents infinite recursion when wrapping a method (`obj` is `self` or `cls`) and either
       - the object's class defines `__getattribute__`
       or
       - the object has no `__orig_class__` attribute and the object's class defines `__getattr__`.
       See discussion at https://github.com/Stewori/pytypes/pull/53.
    If `default_to__class__` is `True` it returns `obj.__class__` as final fallback.
    Otherwise, `AttributeError` is raised in failure case (default behavior).
    """
    try:
        # See https://github.com/Stewori/pytypes/pull/53:
        # Returns  `obj.__orig_class__` protecting from infinite recursion in `__getattr[ibute]__`
        # wrapped in a `checker_tp`.
        # (See `checker_tp` in `typechecker._typeinspect_func for context)
        # Necessary if:
        # - we're wrapping a method (`obj` is `self`/`cls`) and either
        #     - the object's class defines __getattribute__
        # or
        #     - the object doesn't have an `__orig_class__` attribute
        #       and the object's class defines __getattr__.
        # In such a situation, `parent_class = obj.__orig_class__`
        # would call `__getattr[ibute]__`. But that method is wrapped in a `checker_tp` too,
        # so then we'd go into the wrapped `__getattr[ibute]__` and do
        # `parent_class = obj.__orig_class__`, which would call `__getattr[ibute]__`
        # again, and so on. So to bypass `__getattr[ibute]__` we do this:
        return object.__getattribute__(obj, "__orig_class__")
    except AttributeError:
        if sys.version_info.major >= 3:
            cls = object.__getattribute__(obj, "__class__")
        else:
            # Python 2 may return instance objects from object.__getattribute__.
            cls = obj.__class__
        if _typing_3_7 and is_generic(cls):
            # Workaround for https://github.com/python/typing/issues/658
            # Searching from index 2 is sufficient: At 0 is get_orig_class, at 1 is the caller.
            # We assume the caller is not typing._GenericAlias.__call__ which we are after.
            frame = unwrap(currentframe().f_back).f_back
            try:
                while frame:
                    try:
                        res = frame.f_locals["self"]
                        if res.__origin__ is cls:
                            return res
                    except (KeyError, AttributeError):
                        frame = frame.f_back
            finally:
                del frame

        if default_to__class__:
            return cls  # Fallback
        raise


def get_generic_arg_kv_map(type_: Type[T]) -> dict[TypeVar | TypeVarTuple, Type[Any]]:
    type_origin = get_origin(type_) or type_
    generic_arg_kv_map: dict[TypeVar | TypeVarTuple, Type[Any]] = {}

    # this check is equivalent to `_is_generic_type(type_)`
    if type_origin != type_:
        generic_arg_types = get_args(type_)

        # we can't just use issubclass(type_origin, Generic) here,
        # because both `class X[T]:` and `class X(Generic[T])` are subclass of Generic
        if issubclass(type_origin, Generic):
            if len(type_origin.__type_params__) == 0:
                # class X(Generic[T, U]):
                generic_arg_vars = get_args(type_origin.__orig_bases__[0])  # type: ignore
            else:
                # class X[T, U]:
                generic_arg_vars = type_origin.__type_params__

            if len(generic_arg_vars) != len(generic_arg_types):
                raise ValueError(
                    f"get_generic_arg_kv_map: {type_origin=} is malformed, typevar arg count {len(generic_arg_vars)=} != provided arg count {len(generic_arg_types)=}"
                )

            for i in range(len(generic_arg_vars)):
                var = generic_arg_vars[i]
                if isinstance(var, ParamSpec):
                    # we don't include ParamSpec in the returned map
                    continue
                if not isinstance(var, TypeVar) and not isinstance(var, TypeVarTuple):
                    raise ValueError(
                        f"get_generic_arg_kv_map: {type_origin=} has non-TypeVar generic arg {var}"
                    )
                generic_arg_kv_map[var] = generic_arg_types[i]

    return generic_arg_kv_map
