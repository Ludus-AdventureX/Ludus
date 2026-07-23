from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


def to_camel(value: str) -> str:
    """Convert internal snake_case names to the canonical camelCase wire contract."""

    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class CanonicalModel(BaseModel):
    """Strict base for Pydantic models that feed the generated OpenAPI contract."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
]

_HASH_PATTERN = re.compile(r"^(?:sha256:)?[A-Za-z0-9._:+/=~-]+$")


ContentHash = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=256,
        pattern=_HASH_PATTERN,
    ),
]
NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
