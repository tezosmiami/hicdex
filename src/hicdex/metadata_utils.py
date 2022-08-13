import json
import logging
import os
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List

import aiohttp
from dipdup.context import DipDupContext
from tortoise.expressions import Q

import hicdex.models as models
from hicdex.utils import clean_null_bytes, http_request

METADATA_PATH = '/home/dipdup/metadata/tokens'
SUBJKT_PATH = '/home/dipdup/metadata/subjkts'
IPFS_API = os.environ.get('IPFS_API', 'https://cloudflare-ipfs.com/ipfs/')

_logger = logging.getLogger(__name__)

broken_ids = []
try:
    with open(f'{METADATA_PATH}/broken.json') as broken_list:
        broken_ids = json.load(broken_list)
except Exception as exc:
    _logger.error(f'Unable to load {METADATA_PATH}/broken.json: %s', exc)


async def fix_token_metadata(ctx: DipDupContext, token: models.Token) -> bool:
    metadata = await get_metadata(ctx, token)
    token.title = get_name(metadata)
    token.description = get_description(metadata)
    token.artifact_uri = get_artifact_uri(metadata)
    token.display_uri = get_display_uri(metadata)
    token.thumbnail_uri = get_thumbnail_uri(metadata)
    token.mime = get_mime(metadata)
    token.extra = metadata.get('extra', {})
    token.rights = get_rights(metadata)
    token.right_uri = get_right_uri(metadata)
    token.formats = metadata.get('formats', {})
    token.language = get_language(metadata)
    token.attributes = metadata.get('attributes', {})
    token.content_rating = get_content_rating(metadata)
    token.accessibility = metadata.get('accessibility', {})
    await add_tags(token, metadata)
    await token.save()
    return metadata != {}


async def fix_other_metadata(ctx: DipDupContext) -> None:
    _logger.info(f'running fix_missing_metadata job')
    async for token in models.Token.filter(
        Q(artifact_uri='') | Q(rights__isnull=True) & ~Q(id__in=broken_ids)
    ).order_by('id'):
        fixed = await fix_token_metadata(ctx, token)
        if fixed:
            _logger.info(f'fixed metadata for {token.id}')
        else:
            _logger.info(f'failed to fix metadata for {token.id}')
            broken_ids.append(token.id)


async def add_tags(token: models.Token, metadata: Dict[str, Any]) -> None:
    tags = [await get_or_create_tag(tag) for tag in get_tags(metadata)]
    for tag in tags:
        token_tag = await models.TokenTag(token=token, tag=tag)
        await token_tag.save()


async def get_or_create_tag(tag: str) -> models.TagModel:
    tag_model, _ = await models.TagModel.get_or_create(tag=tag)
    return tag_model


async def get_subjkt_metadata(holder: models.Holder) -> Dict[str, Any]:
    failed_attempt = 0
    with suppress(Exception), open(subjkt_path(holder.address)) as json_file:
        metadata = json.load(json_file)
        failed_attempt = metadata.get('__failed_attempt')
        if failed_attempt and failed_attempt > 1:
            return {}
        if not failed_attempt:
            return metadata

    return await fetch_subjkt_metadata_ipfs(holder, failed_attempt)


async def get_metadata(ctx: DipDupContext, token: models.Token) -> Dict[str, Any]:
    # FIXME: hard coded contract
    metadata_datasource = ctx.get_metadata_datasource('metadata')
    metadata = await metadata_datasource.get_token_metadata('KT1RJ6PbjHpwc3M5rw5s2Nbmefwbuwbdxton', token.id)
    if metadata is not None:
        _logger.info(f'found metadata for {token.id} from metadata_datasource')
        if isinstance(metadata, str):
            return json.loads(metadata)
        return metadata

    data = await fetch_metadata_ipfs(token)
    if data != {}:
        _logger.info(f'found metadata for {token.id} from IPFS')
    else:
        data = await fetch_metadata_bcd(token)
        if data != {}:
            _logger.info(f'metadata for {token.id} from BCD')

    return data


def write_subjkt_metadata_file(holder: models.Holder, metadata: Dict[str, Any]) -> None:
    with open(subjkt_path(holder.address), 'w') as write_file:
        json.dump(metadata, write_file)


async def fetch_metadata_bcd(token: models.Token) -> Dict[str, Any]:
    session = aiohttp.ClientSession()
    data = await http_request(
        session,
        'get',
        url=f'https://api.better-call.dev/v1/tokens/mainnet/metadata?contract:KT1Hkg5qeNhfwpKW4fXvq7HGZB9z2EnmCCA9&token_id={token.id}',
    )
    await session.close()

    data = [
        obj
        for obj in data
        if 'symbol' in obj and (obj['symbol'] == 'OBJKT' or obj['contract'] == 'KT1RJ6PbjHpwc3M5rw5s2Nbmefwbuwbdxton')
    ]
    with suppress(FileNotFoundError):
        if data and not isinstance(data[0], list):
            return data[0]
    return {}


async def fetch_subjkt_metadata_ipfs(holder: models.Holder, failed_attempt: int = 0) -> Dict[str, Any]:
    addr = holder.metadata_file.replace('ipfs://', '')
    try:
        session = aiohttp.ClientSession()
        data = await http_request(session, 'get', url=f'{IPFS_API}/{addr}', timeout=10)
        await session.close()
        if data and not isinstance(data, list):
            write_subjkt_metadata_file(holder, data)
            return data
        with open(subjkt_path(holder.address), 'w') as write_file:
            json.dump({'__failed_attempt': failed_attempt + 1}, write_file)
    except Exception:
        await session.close()
    return {}


async def fetch_metadata_ipfs(token: models.Token) -> Dict[str, Any]:
    addr = token.metadata.replace('ipfs://', '')
    try:
        session = aiohttp.ClientSession()
        data = await http_request(session, 'get', url=f'{IPFS_API}/{addr}', timeout=10)
        await session.close()
        if data and not isinstance(data, list):
            return data
    except Exception:
        await session.close()
    return {}


def get_mime(metadata: Dict[str, Any]) -> str:
    if ('formats' in metadata) and metadata['formats'] and ('mimeType' in metadata['formats'][0]):
        return metadata['formats'][0]['mimeType']
    return ''


def get_tags(metadata: Dict[str, Any]) -> List[str]:
    tags = metadata.get('tags', [])
    cleaned = [clean_null_bytes(tag) for tag in tags]
    lowercased = [tag.lower() for tag in cleaned]
    uniqued = list(set(lowercased))
    return [tag for tag in uniqued if len(tag) < 255]


def get_name(metadata: Dict[str, Any]) -> str:
    return clean_null_bytes(metadata.get('name', ''))


def get_rights(metadata: Dict[str, Any]) -> str:
    return clean_null_bytes(metadata.get('rights', ''))


def get_content_rating(metadata: Dict[str, Any]) -> str:
    return clean_null_bytes(metadata.get('contentRating', ''))


def get_language(metadata: Dict[str, Any]) -> str:
    return clean_null_bytes(metadata.get('language', ''))


def get_description(metadata: Dict[str, Any]) -> str:
    return clean_null_bytes(metadata.get('description', ''))


def get_artifact_uri(metadata: Dict[str, Any]) -> str:
    return clean_null_bytes(metadata.get('artifact_uri', '') or metadata.get('artifactUri', ''))


def get_display_uri(metadata: Dict[str, Any]) -> str:
    return clean_null_bytes(metadata.get('display_uri', '') or metadata.get('displayUri', ''))


def get_thumbnail_uri(metadata: Dict[str, Any]) -> str:
    return clean_null_bytes(metadata.get('thumbnail_uri', '') or metadata.get('thumbnailUri', ''))


def get_right_uri(metadata: Dict[str, Any]) -> str:
    return clean_null_bytes(metadata.get('right_uri', '') or metadata.get('rightUri', ''))


def subjkt_path(addr: str) -> str:
    lvl = addr[-1]
    folder = f'{SUBJKT_PATH}/{lvl}'
    Path(folder).mkdir(parents=True, exist_ok=True)
    return f'{folder}/{addr}.json'
