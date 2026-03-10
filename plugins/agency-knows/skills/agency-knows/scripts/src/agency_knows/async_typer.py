from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Coroutine
from functools import partial, wraps
from typing import Any, cast

from typer import Typer
from typer.models import CommandFunctionType
from typing_extensions import override


class AsyncTyper(Typer):
    @staticmethod
    def maybe_run_async(
        decorator: Callable[[CommandFunctionType], CommandFunctionType],
        func: CommandFunctionType,
    ) -> CommandFunctionType:
        if inspect.iscoroutinefunction(cast(object, func)):

            @wraps(cast(Callable[..., Any], func))
            def runner(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
                coro = cast(Callable[..., Coroutine[Any, Any, Any]], func)(*args, **kwargs)
                return asyncio.run(coro)

            decorator(runner)  # type: ignore
        else:
            decorator(func)
        return func

    @override
    def callback(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[[CommandFunctionType], CommandFunctionType]:
        decorator = super().callback(*args, **kwargs)
        return cast(
            Callable[[CommandFunctionType], CommandFunctionType],
            partial(self.maybe_run_async, decorator),
        )

    @override
    def command(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[[CommandFunctionType], CommandFunctionType]:
        decorator = super().command(*args, **kwargs)
        return cast(
            Callable[[CommandFunctionType], CommandFunctionType],
            partial(self.maybe_run_async, decorator),
        )
