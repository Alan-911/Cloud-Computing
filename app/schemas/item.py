from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

ItemName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ItemDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ItemCreate(BaseModel):
    """Body for creating an item, and for a full replace (PUT)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"name": "alpha", "description": "First item"}]},
    )

    name: ItemName
    description: ItemDescription | None = None


class ItemPatch(BaseModel):
    """Body for a partial update. Only the fields sent are changed."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"description": "Updated"}]}
    )

    name: ItemName | None = None
    description: ItemDescription | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ItemPatch":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null.")
        return self


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def assume_utc(cls, value: datetime) -> datetime:
        # SQLite drops tzinfo; values are always written in UTC.
        return value if value.tzinfo else value.replace(tzinfo=UTC)


class ItemPage(BaseModel):
    items: list[ItemRead]
    total: int = Field(description="Total items across all pages.")
    limit: int
    offset: int
