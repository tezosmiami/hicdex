import json
import logging
from contextlib import suppress
from typing import Any

import aiohttp

_logger = logging.getLogger(__name__)


def clean_null_bytes(string: str) -> str:
    if string is None:
        return ''
    if type(string) is dict:
        return json.dumps(string)
    else:
        return ''.join(string.split('\x00'))


def fromhex(hexbytes: str) -> str:
    string = None
    with suppress(Exception):
        try:
            string = bytes.fromhex(hexbytes).decode()
        except Exception:
            string = bytes.fromhex(hexbytes).decode('latin-1')
    return clean_null_bytes(string or '')


async def http_request(
    session: aiohttp.ClientSession,
    method: str,
    **kwargs: Any,
) -> Any:
    """Wrapped aiohttp call with preconfigured headers and logging"""
    headers = {
        **kwargs.pop('headers', {}),
        'User-Agent': 'dipdup',
    }
    request_string = (
        kwargs['url'] + '?' + '&'.join([f'{key}={value}' for key, value in kwargs.get('params', {}).items()])
    )
    _logger.debug('Calling `%s`', request_string)
    async with getattr(session, method)(
        skip_auto_headers={'User-Agent'},
        headers=headers,
        **kwargs,
    ) as response:
        return await response.json(content_type=None)
