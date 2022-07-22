import logging

from dipdup.context import HookContext

from hicdex.metadata_utils import fix_other_metadata


async def fix_missing_metadata(
    ctx: HookContext,
) -> None:
    await fix_other_metadata(ctx)
