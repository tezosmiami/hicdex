from dipdup.context import HandlerContext
from dipdup.models import Transaction

import hicdex.models as models
from hicdex.types.split_sign.parameter.sign import SignParameter
from hicdex.types.split_sign.storage import SplitSignStorage


async def on_split_sign(
    ctx: HandlerContext,
    sign: Transaction[SignParameter, SplitSignStorage],
) -> None:
    sender = sign.data.sender_address
    objkt_id = sign.parameter.__root__

    token, _ = await models.Token.get_or_create(id=int(objkt_id))
    contract, _ = await models.SplitContract.get_or_create(contract_id=token.creator_id)

    await models.Signatures.get_or_create(holder_id=sender, token_id=token.id)

    try:
        core_participants = await models.Shareholder.filter(
            split_contract=contract, holder_type=models.ShareholderStatus.core_participant
        ).all()
        sig_required = {sharesholder.holder_id for sharesholder in core_participants}
        signers = await models.Signatures.filter(token=token).all()
        sig_created = {signer.holder_id for signer in signers}

        if sig_required.issubset(sig_created):
            token.is_signed = True
            await token.save()
    except Exception as exc:
        ctx.logger.error('Failed to update token %s: %s', token.id, exc)
