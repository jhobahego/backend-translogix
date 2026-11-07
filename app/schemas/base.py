"""Base Pydantic schema configurations."""

from pydantic import BaseModel, ConfigDict


class AppBaseModel(BaseModel):
    """Base for request and domain models: rejects unknown fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class OrmBaseModel(BaseModel):
    """Base for response models built from ORM instances."""

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )
