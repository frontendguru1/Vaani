from pydantic import BaseModel, ConfigDict, Field


class EntryIn(BaseModel):
    term: str = Field(max_length=200)
    replacement: str = Field(max_length=400)
    language: str | None = None
    case_sensitive: bool = False


class EntryUpdate(BaseModel):
    term: str | None = Field(default=None, max_length=200)
    replacement: str | None = Field(default=None, max_length=400)
    language: str | None = None
    case_sensitive: bool | None = None


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    term: str
    replacement: str
    language: str | None
    case_sensitive: bool


class PreviewIn(BaseModel):
    text: str = Field(max_length=20_000)
    language: str


class AppliedOut(BaseModel):
    term: str
    replacement: str
    count: int


class PreviewOut(BaseModel):
    text: str
    applied: list[AppliedOut]
