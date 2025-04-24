"""Immutable registry of every token, conditional token pair and pool required
by **one** futarchy proposal. Nothing here touches the chain at runtime."""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Mapping

__all__ = ["ConditionalPools", "ConditionalPair", "Proposal", "proposal", "pool"]


@dataclass(frozen=True, slots=True)
class ConditionalPools:
    type: str          # provider name, e.g. "swapr", "cow"
    yes_pool: str      # YES-side liquidity pool
    no_pool: str       # NO-side  liquidity pool
    router: str        # AMM router for swaps

@dataclass(frozen=True, slots=True)
class ConditionalPair:
    yes_token: str
    no_token: str
    contract: str      # ConditionalTokens contract

@dataclass(frozen=True, slots=True)
class Proposal:
    name: str
    company_token: str
    currency_token: str
    condition_id: str
    company_conditionals: ConditionalPair
    currency_conditional: ConditionalPair
    pools: Mapping[str, ConditionalPools]

proposal = Proposal(
    name="Gnosis Treasury Allocation 12-MAY-2025",
    company_token=os.environ.get("GNO_ADDRESS", "0x0000000000000000000000000000000000000000"),            # GNO
    currency_token=os.environ.get("SDAI_ADDRESS", "0x0000000000000000000000000000000000000000"),           # sDAI
    condition_id=os.environ.get("CONDITION_ID", "0x0000000000000000000000000000000000000000"),

    company_conditionals=ConditionalPair(
        yes_token=os.environ.get("SWAPR_GNO_YES_ADDRESS", "0x0000000000000000000000000000000000000000"), 
        no_token=os.environ.get("SWAPR_GNO_NO_ADDRESS", "0x0000000000000000000000000000000000000000"), 
        contract=os.environ.get("CONDITIONAL_TOKENS_CONTRACT", "0x0000000000000000000000000000000000000000")
    ),
    currency_conditional=ConditionalPair(
        yes_token=os.environ.get("SWAPR_SDAI_YES_ADDRESS", "0x0000000000000000000000000000000000000000"), 
        no_token=os.environ.get("SWAPR_SDAI_NO_ADDRESS", "0x0000000000000000000000000000000000000000"), 
        contract=os.environ.get("CONDITIONAL_TOKENS_CONTRACT", "0x0000000000000000000000000000000000000000")
    ),
    pools={
        "swapr": ConditionalPools(
            type="swapr",
            yes_pool=os.environ.get("SWAPR_POOL_YES_ADDRESS", "0x0000000000000000000000000000000000000000"),
            no_pool=os.environ.get("SWAPR_POOL_NO_ADDRESS", "0x0000000000000000000000000000000000000000"),
            router=os.environ.get("SWAPR_ROUTER_ADDRESS", "0x0000000000000000000000000000000000000000"),
        ),
    },
)

def pool(provider: str) -> ConditionalPools:
    try:
        return proposal.pools[provider]
    except KeyError as exc:
        raise KeyError(
            f"Unknown provider '{provider}'. Valid: {list(proposal.pools)}"
        ) from exc
