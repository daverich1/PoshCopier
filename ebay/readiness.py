"""Bulk offline eBay draft-readiness scanning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ebay.draft import EbayDraftBuilder
from ebay.category_rules import EbayCategoryRuleStore
from ebay.condition_rules import EbayConditionRuleStore, condition_rule_key
from ebay.draft_store import EbayDraftReviewStore
from ebay.settings import EbaySettings, EbaySettingsStore
from ebay.source_scope import dveshop_source_listing_ids
from runtime_paths import DOWNLOADS_DIR


@dataclass(frozen=True)
class EbayReadinessItem:
    listing_id: str
    title: str
    source_category: str
    category_suggestion: str
    category_id: str
    status: str
    blocker_count: int
    warning_count: int
    blockers: tuple[str, ...]
    source_condition: str
    ebay_condition: str


@dataclass(frozen=True)
class EbayReadinessReport:
    items: tuple[EbayReadinessItem, ...]
    ready: int
    needs_configuration: int
    needs_source_fix: int
    category_confirmed: int
    database_eligible: int
    missing_local_files: int
    category_groups: tuple["EbayCategoryGroup", ...]
    condition_groups: tuple["EbayConditionGroup", ...]

    @property
    def total(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class EbayCategoryGroup:
    source_category: str
    category_suggestion: str
    listing_count: int
    category_id: str


@dataclass(frozen=True)
class EbayConditionGroup:
    source_category: str
    source_condition: str
    listing_count: int
    ebay_condition: str


class EbayReadinessScanner:
    def __init__(
        self,
        downloads_dir: Path = DOWNLOADS_DIR,
        *,
        settings_store: EbaySettingsStore | None = None,
        review_store: EbayDraftReviewStore | None = None,
        eligible_listing_ids: set[str] | None = None,
        category_rule_store: EbayCategoryRuleStore | None = None,
        condition_rule_store: EbayConditionRuleStore | None = None,
    ) -> None:
        self.downloads_dir = downloads_dir
        self.settings_store = settings_store or EbaySettingsStore()
        self.review_store = review_store or EbayDraftReviewStore()
        self.builder = EbayDraftBuilder()
        self.eligible_listing_ids = eligible_listing_ids
        self.category_rule_store = category_rule_store or EbayCategoryRuleStore()
        self.condition_rule_store = condition_rule_store or EbayConditionRuleStore()

    def scan(self) -> EbayReadinessReport:
        settings = self.settings_store.load()
        items: list[EbayReadinessItem] = []
        ready = 0
        needs_configuration = 0
        needs_source_fix = 0
        category_confirmed = 0
        category_rules = self.category_rule_store.load()
        condition_rules = self.condition_rule_store.load()
        eligible_listing_ids = (
            self.eligible_listing_ids
            if self.eligible_listing_ids is not None
            else dveshop_source_listing_ids()
        )
        local_listing_ids = {
            path.parent.name
            for path in self.downloads_dir.glob("*/listing.json")
        }

        for listing_file in sorted(self.downloads_dir.glob("*/listing.json")):
            if listing_file.parent.name not in eligible_listing_ids:
                continue
            item = self._scan_listing(
                listing_file,
                settings,
                category_rules,
                condition_rules,
            )
            items.append(item)
            if item.status == "Ready":
                ready += 1
            elif item.status == "Needs Source Fix":
                needs_source_fix += 1
            else:
                needs_configuration += 1
            if item.category_id:
                category_confirmed += 1

        grouped: dict[str, list[EbayReadinessItem]] = {}
        for item in items:
            grouped.setdefault(item.source_category, []).append(item)
        category_groups = tuple(
            EbayCategoryGroup(
                source_category=source_category,
                category_suggestion=group_items[0].category_suggestion,
                listing_count=len(group_items),
                category_id=self._group_category_status(
                    source_category,
                    group_items,
                    category_rules,
                ),
            )
            for source_category, group_items in sorted(grouped.items())
        )
        grouped_conditions: dict[str, list[EbayReadinessItem]] = {}
        for item in items:
            key = condition_rule_key(item.source_category, item.source_condition)
            grouped_conditions.setdefault(key, []).append(item)
        condition_groups = tuple(
            EbayConditionGroup(
                source_category=group_items[0].source_category,
                source_condition=group_items[0].source_condition,
                listing_count=len(group_items),
                ebay_condition=(
                    condition_rules.get(key, "")
                    or self._group_condition_status(group_items)
                ),
            )
            for key, group_items in sorted(grouped_conditions.items())
        )

        return EbayReadinessReport(
            items=tuple(items),
            ready=ready,
            needs_configuration=needs_configuration,
            needs_source_fix=needs_source_fix,
            category_confirmed=category_confirmed,
            database_eligible=len(eligible_listing_ids),
            missing_local_files=len(eligible_listing_ids - local_listing_ids),
            category_groups=category_groups,
            condition_groups=condition_groups,
        )

    @staticmethod
    def _group_category_status(
        source_category: str,
        group_items: list[EbayReadinessItem],
        category_rules: dict[str, str],
    ) -> str:
        bulk_rule = category_rules.get(source_category, "")
        if bulk_rule:
            return bulk_rule
        item_category_ids = {
            item.category_id
            for item in group_items
            if item.category_id
        }
        if len(item_category_ids) == 1 and len(group_items) > 0:
            return next(iter(item_category_ids))
        if item_category_ids and all(item.category_id for item in group_items):
            return "PER_LISTING"
        return ""

    @staticmethod
    def _group_condition_status(
        group_items: list[EbayReadinessItem],
    ) -> str:
        item_conditions = {
            item.ebay_condition
            for item in group_items
            if item.ebay_condition
        }
        if len(item_conditions) == 1 and group_items:
            return next(iter(item_conditions))
        if item_conditions and all(item.ebay_condition for item in group_items):
            return "PER_LISTING"
        return ""

    def _scan_listing(
        self,
        listing_file: Path,
        settings: EbaySettings,
        category_rules: dict[str, str],
        condition_rules: dict[str, str],
    ) -> EbayReadinessItem:
        try:
            payload = json.loads(listing_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("Listing JSON must contain an object.")
        except (OSError, json.JSONDecodeError, TypeError):
            return EbayReadinessItem(
                listing_id=listing_file.parent.name,
                title="Unreadable listing",
                source_category="",
                category_suggestion="",
                category_id="",
                status="Needs Source Fix",
                blocker_count=1,
                warning_count=0,
                blockers=("Source data: listing JSON is unreadable.",),
                source_condition="",
                ebay_condition="",
            )

        listing_id = str(payload.get("listing_id", listing_file.parent.name)).strip()
        source_category = str(payload.get("category", "")).strip()
        source_condition = str(payload.get("condition", "")).strip()
        review = self.review_store.load(listing_id)
        category_id = review.category_id or category_rules.get(source_category, "")
        condition = review.condition or condition_rules.get(
            condition_rule_key(source_category, source_condition),
            "",
        )
        draft = self.builder.build(
            payload,
            listing_file.parent,
            category_id=category_id or None,
            merchant_location_key=settings.merchant_location_key,
            payment_policy_id=settings.payment_policy_id,
            fulfillment_policy_id=settings.fulfillment_policy_id,
            return_policy_id=settings.return_policy_id,
            condition_override=condition or None,
        )
        if draft.ready_to_publish:
            status = "Ready"
        elif draft.ready_for_review:
            status = "Needs Configuration"
        else:
            status = "Needs Source Fix"
        return EbayReadinessItem(
            listing_id=listing_id,
            title=draft.title,
            source_category=source_category,
            category_suggestion=draft.category_suggestion or "",
            category_id=category_id,
            status=status,
            blocker_count=len(draft.blockers),
            warning_count=len(draft.warnings),
            blockers=tuple(draft.blockers),
            source_condition=source_condition,
            ebay_condition=draft.condition or "",
        )
