from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.indexer.chunking.tokens import TokenEstimator

_MERGE_SEP = "\n\n"
_UNIT_SEP = " "


@dataclass(frozen=True)
class Block:
    """Bloc logique à normaliser.

    `atomic=True` : unité insécable (ex. fence de code/diagramme) — jamais
    fusionnée vers le haut (floor) ni découpée sur les mots (ceiling). Si elle
    dépasse le plafond dur, `ChunkTooLargeError` est levée (ADR 0001 §3).
    """

    text: str
    atomic: bool = False

    @staticmethod
    def prose(text: str) -> Block:
        """Bloc prose (fusionnable / splittable) — le défaut historique."""
        return Block(text=text, atomic=False)


@dataclass(frozen=True)
class TokenBounds:
    """Bornes de normalisation, exprimées en tokens.

    - `child_target_tokens` : taille cible de l'enfant (levier qualité récup).
    - `floor_tokens`        : en dessous, on fusionne vers le haut.
    - `overlap_tokens`      : recouvrement entre pièces issues d'un même bloc.
    - `hard_ceiling_tokens` : plafond dur provider, infranchissable.
    """

    child_target_tokens: int
    floor_tokens: int
    overlap_tokens: int
    hard_ceiling_tokens: int


class TokenNormalizer:
    """Normalise une liste de blocs logiques en chunks bornés en tokens.

    Pipeline : (1) floor = merge des blocs trop petits ; (2) ceiling = split
    des blocs trop gros sur frontière de mot, avec overlap ; (3) garde-fou dur :
    toute unité insécable dépassant le plafond provider lève `ChunkTooLargeError`
    (jamais de troncature silencieuse — ADR 0001 §3).
    """

    def __init__(self, estimator: TokenEstimator, bounds: TokenBounds) -> None:
        self._validate(bounds)
        self._est = estimator
        self._b = bounds

    @staticmethod
    def _validate(b: TokenBounds) -> None:
        if b.child_target_tokens <= 0:
            raise ValueError(f"child_target_tokens must be > 0, got {b.child_target_tokens}")
        if b.floor_tokens < 0:
            raise ValueError(f"floor_tokens must be >= 0, got {b.floor_tokens}")
        if b.overlap_tokens < 0:
            raise ValueError(f"overlap_tokens must be >= 0, got {b.overlap_tokens}")
        if b.floor_tokens > b.child_target_tokens:
            raise ValueError("floor_tokens must be <= child_target_tokens")
        if b.overlap_tokens >= b.child_target_tokens:
            raise ValueError("overlap_tokens must be < child_target_tokens")
        if b.child_target_tokens > b.hard_ceiling_tokens:
            raise ValueError("child_target_tokens must be <= hard_ceiling_tokens")

    def normalize(self, blocks: Sequence[str | Block]) -> list[str]:
        coerced = [self._coerce(b) for b in blocks if self._coerce(b).text.strip()]
        merged = self._merge_floor(coerced)
        result: list[str] = []
        for block in merged:
            if block.atomic:
                result.append(self._emit_atomic(block.text))
            elif self._est.estimate(block.text) <= self._b.child_target_tokens:
                result.append(block.text)
            else:
                result.extend(self._split_ceiling(block.text))
        return result

    @staticmethod
    def _coerce(block: str | Block) -> Block:
        return block if isinstance(block, Block) else Block.prose(block)

    def _emit_atomic(self, text: str) -> str:
        estimated = self._est.estimate(text)
        if estimated > self._b.hard_ceiling_tokens:
            raise ChunkTooLargeError(
                estimated_tokens=estimated,
                hard_ceiling_tokens=self._b.hard_ceiling_tokens,
            )
        return text

    def _merge_floor(self, blocks: list[Block]) -> list[Block]:
        merged: list[Block] = []
        buffer = ""
        for block in blocks:
            if block.atomic:
                if buffer:
                    merged.append(Block.prose(buffer))
                    buffer = ""
                merged.append(block)
                continue
            if not buffer:
                buffer = block.text
                continue
            combined = f"{buffer}{_MERGE_SEP}{block.text}"
            below_floor = self._est.estimate(buffer) < self._b.floor_tokens
            fits = self._est.estimate(combined) <= self._b.child_target_tokens
            if below_floor and fits:
                buffer = combined
            else:
                merged.append(Block.prose(buffer))
                buffer = block.text
        if buffer:
            merged.append(Block.prose(buffer))
        return merged

    def _split_ceiling(self, block: str) -> list[str]:
        budget = self._b.child_target_tokens - self._b.overlap_tokens
        pieces = self._pack_units(block.split(), budget)
        if self._b.overlap_tokens <= 0 or len(pieces) <= 1:
            return pieces
        return self._apply_overlap(pieces)

    def _pack_units(self, units: list[str], budget: int) -> list[str]:
        pieces: list[str] = []
        current: list[str] = []
        for unit in units:
            if self._est.estimate(unit) > self._b.hard_ceiling_tokens:
                raise ChunkTooLargeError(
                    estimated_tokens=self._est.estimate(unit),
                    hard_ceiling_tokens=self._b.hard_ceiling_tokens,
                )
            candidate = _UNIT_SEP.join([*current, unit])
            if current and self._est.estimate(candidate) > budget:
                pieces.append(_UNIT_SEP.join(current))
                current = [unit]
            else:
                current.append(unit)
        if current:
            pieces.append(_UNIT_SEP.join(current))
        return pieces

    def _apply_overlap(self, pieces: list[str]) -> list[str]:
        result = [pieces[0]]
        for i in range(1, len(pieces)):
            prefix = self._suffix_tokens(pieces[i - 1], self._b.overlap_tokens)
            result.append(f"{prefix}{_UNIT_SEP}{pieces[i]}")
        return result

    def _suffix_tokens(self, text: str, n_tokens: int) -> str:
        """Suffixe minimal de `text` dont l'estimation atteint `n_tokens`."""
        for length in range(1, len(text) + 1):
            suffix = text[-length:]
            if self._est.estimate(suffix) >= n_tokens:
                return suffix
        return text
