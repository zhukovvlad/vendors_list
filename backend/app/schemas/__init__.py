"""Pydantic v2 схемы запросов/ответов.

Ответы повторяют колонки готовых объектов БД (вьюх/таблиц). Бизнес-логику
статусов/звезды НЕ дублируем — приходит из БД как есть.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_from_row = ConfigDict(from_attributes=True)


# --- Справочники / мета ------------------------------------------------------
class BuildingType(BaseModel):
    model_config = _from_row
    id: int
    code: str
    name: str
    sort_order: int


class Segment(BaseModel):
    model_config = _from_row
    id: int
    building_type_id: int
    group_id: int | None
    name: str
    sort_order: int


class MetaPosition(BaseModel):
    id: int
    name: str
    category_path: str | None


# --- Живой перечень (listing_live) ------------------------------------------
class ListingRow(BaseModel):
    model_config = _from_row
    id: int
    position_id: int
    segment_id: int
    vendor_id: int | None
    status: str
    spec_text: str | None
    ujin_integration: bool
    note: str | None
    sort_order: int
    category_path: str | None
    position_name: str
    segment_group_name: str | None
    segment_name: str
    vendor_name: str | None
    vendor_starred: bool
    updated_at: datetime
    updated_by: str


# --- Матрица перечня (server pivot над listing_live) ------------------------
class MatrixVendorRef(BaseModel):
    vendor_id: int
    name: str
    starred: bool          # = vendor_starred, как есть
    ujin_integration: bool
    note: str | None       # per-vendor (атрибут ряда)


class MatrixCell(BaseModel):
    segment_id: int
    vendors: list[MatrixVendorRef]  # непусто ⇒ вендорная ячейка
    spec_text: str | None           # требование (vendor NULL)
    note: str | None                # значим только для ячейки-требования


class MatrixRow(BaseModel):
    position_id: int
    position_name: str
    category_path: str              # position.category_id NOT NULL ⇒ путь всегда есть
    cells: list[MatrixCell]


class SegmentRef(BaseModel):
    id: int
    name: str
    sort_order: int


class SegmentGroupRef(BaseModel):
    id: int
    name: str


class MatrixColumnGroup(BaseModel):
    group: SegmentGroupRef | None   # None ⇒ плоские leaf-колонки (жилые/социальные)
    segments: list[SegmentRef]


class Matrix(BaseModel):
    columns: list[MatrixColumnGroup]
    items: list[MatrixRow]
    total: int                      # число РАЗЛИЧНЫХ позиций под фильтром
    limit: int
    offset: int


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Обёртка серверной пагинации для таблиц (TanStack Table)."""

    items: list[T]
    total: int
    limit: int
    offset: int


# --- Издания (release_listing) ----------------------------------------------
class ReleaseListingRow(BaseModel):
    model_config = _from_row
    id: int
    release_id: int
    position_id: int | None
    segment_id: int | None
    vendor_id: int | None
    status: str
    spec_text: str | None
    ujin_integration: bool
    note: str | None
    sort_order: int
    category_path: str | None
    position_name: str | None
    segment_group_name: str | None
    segment_name: str | None
    vendor_name: str | None
    vendor_starred: bool


# --- Соответствие ------------------------------------------------------------
class PositionStatus(BaseModel):
    model_config = _from_row
    project_id: int
    project_code: str
    position_id: int
    category_path: str | None
    position_name: str
    allowed_vendor_count: int
    selected_vendor_count: int
    off_standard_count: int
    in_standard_selected_count: int
    has_selection: bool
    in_standard_scope: bool
    standard_requirement: str | None
    position_state: str  # compliant | deviation | manual_check | open


class ProjectSummary(BaseModel):
    model_config = _from_row
    project_id: int
    project_code: str
    total_positions: int
    compliant_positions: int
    deviation_positions: int
    manual_check_positions: int
    open_positions: int
    judged_positions: int
    off_standard_selections: int
    compliance_pct: float | None


# --- Проекты и выбор вендоров ------------------------------------------------
class Project(BaseModel):
    model_config = _from_row
    id: int
    code: str
    name: str
    segment_id: int
    release_id: int | None
    note: str | None


class ProjectCreate(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    segment_id: int
    release_id: int | None = None
    note: str | None = None


class SelectionCreate(BaseModel):
    position_id: int
    vendor_id: int
    rationale: str | None = None
    source_ref: str | None = None


class Selection(BaseModel):
    model_config = _from_row
    id: int
    project_id: int
    position_id: int
    vendor_id: int
    rationale: str | None
    source_ref: str | None


# --- Дашборд «Обзор» --------------------------------------------------------
class DashboardSummary(BaseModel):
    positions_active: int
    releases_published: int
    drafts_open: int
    vendors_total: int
    vendors_with_agreement: int
    merge_candidate_pairs: int | None  # None ⇒ детект не отработал (не 500)


class DashboardDraft(BaseModel):
    model_config = _from_row
    release_id: int
    building_type_name: str
    label: str
    last_touched_at: datetime
    last_touched_by: str | None
    is_stale: bool


class Dashboard(BaseModel):
    summary: DashboardSummary
    drafts: list[DashboardDraft]


# --- Карточка вендора --------------------------------------------------------
class VendorAlias(BaseModel):
    model_config = _from_row
    id: int
    alias: str


class VendorRepresents(BaseModel):
    model_config = _from_row
    id: int
    name: str


class VendorCard(BaseModel):
    id: int
    name: str
    kind: str
    note: str | None
    starred: bool
    represents: VendorRepresents | None
    represented_count: int
    aliases: list[VendorAlias]


class WhereAllowedChip(BaseModel):
    segment_id: int
    segment_name: str
    state: Literal["allowed", "excluded"]
    release_label: str | None     # для 'excluded' — тултип


class WhereAllowedPosition(BaseModel):
    position_id: int
    position_name: str
    chips: list[WhereAllowedChip]


class WhereAllowedStandard(BaseModel):
    building_type_id: int
    building_type_name: str
    position_count: int
    segment_count: int      # всего классов (сегментов) у типа — знаменатель «все классы»
    positions: list[WhereAllowedPosition]


class WhereAllowed(BaseModel):
    standards: list[WhereAllowedStandard]


# --- Мутации карточки вендора ------------------------------------------------
class AgreementToggle(BaseModel):
    active: bool


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1)


_VENDOR_KINDS = {"manufacturer", "supplier", "other"}


class VendorHeaderUpdate(BaseModel):
    """Инлайн-правка шапки. Partial: в эндпоинте читаем model_dump(exclude_unset=True),
    чтобы отличить «поле не пришло» от «note: null (очистить)»."""

    name: str | None = None
    note: str | None = None
    kind: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Имя не может быть пустым")
        return stripped

    @field_validator("kind")
    @classmethod
    def _kind_in_enum(cls, v: str | None) -> str | None:
        if v is not None and v not in _VENDOR_KINDS:
            raise ValueError("Недопустимый тип вендора")
        return v


class ListingAdd(BaseModel):
    position_id: int
    segment_ids: list[int] = Field(min_length=1)


class ListingExclude(BaseModel):
    """scope-дискриминатор. Обязательность полей — по scope (валидатор)."""

    scope: Literal["class", "position", "standard"]
    position_id: int | None = None
    segment_id: int | None = None
    building_type_id: int | None = None

    @model_validator(mode="after")
    def _require_scope_fields(self) -> "ListingExclude":
        if self.scope == "class" and (self.position_id is None or self.segment_id is None):
            raise ValueError("scope=class требует position_id и segment_id")
        if self.scope == "position" and (self.position_id is None or self.building_type_id is None):
            raise ValueError("scope=position требует position_id и building_type_id")
        if self.scope == "standard" and self.building_type_id is None:
            raise ValueError("scope=standard требует building_type_id")
        return self


class ListingRestore(BaseModel):
    position_id: int
    segment_id: int


class ListingExcludeResult(BaseModel):
    excluded_positions: int
    excluded_classes: int
