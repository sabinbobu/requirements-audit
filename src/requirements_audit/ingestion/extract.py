"""Entity and cross-reference extraction.

Entities: every requirement yields one `requirement` entity; every named parameter
yields a `parameter` entity carrying its value. These back the audit step, which
pairs candidate requirements by shared entity.

Cross-references: each `refs` entry becomes a CrossRef, marked resolved only if the
target requirement exists in the corpus — dangling references are flagged, not dropped.
"""

from __future__ import annotations

from collections.abc import Iterable

from requirements_audit.models import CrossRef, Entity, EntityType, RequirementDocument


def extract_entities(doc: RequirementDocument) -> list[Entity]:
    entities: list[Entity] = []
    for req in doc.requirements:
        entities.append(
            Entity(
                name=req.id,
                entity_type=EntityType.REQUIREMENT,
                requirement_id=req.id,
                doc_id=doc.id,
            )
        )
        for param_name, param_value in req.parameters.items():
            entities.append(
                Entity(
                    name=param_name,
                    entity_type=EntityType.PARAMETER,
                    requirement_id=req.id,
                    doc_id=doc.id,
                    value=param_value,
                )
            )
    return entities


def extract_refs(doc: RequirementDocument, known_ids: Iterable[str]) -> list[CrossRef]:
    known = set(known_ids)
    refs: list[CrossRef] = []
    for req in doc.requirements:
        for target in req.refs:
            refs.append(CrossRef(from_req=req.id, to_req=target, resolved=target in known))
    return refs
