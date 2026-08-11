"""Offline progress model for guided eBay draft review."""

from __future__ import annotations

from dataclasses import dataclass

from ebay.readiness import EbayCategoryGroup, EbayConditionGroup, EbayReadinessReport


@dataclass(frozen=True)
class EbayWizardProgress:
    total_listing_checks: int
    completed_listing_checks: int
    category_groups_remaining: int
    condition_groups_remaining: int

    @property
    def percent(self) -> float:
        if self.total_listing_checks == 0:
            return 100.0
        return self.completed_listing_checks / self.total_listing_checks * 100.0


class EbayReadinessWizardState:
    """Select the next unresolved bulk rule without changing any data."""

    def __init__(self, report: EbayReadinessReport) -> None:
        self.report = report

    def next_category(self) -> EbayCategoryGroup | None:
        return next(
            (group for group in self.report.category_groups if not group.category_id),
            None,
        )

    def next_condition(self) -> EbayConditionGroup | None:
        return next(
            (group for group in self.report.condition_groups if not group.ebay_condition),
            None,
        )

    def progress(self) -> EbayWizardProgress:
        total = self.report.total * 2
        completed_categories = sum(
            group.listing_count
            for group in self.report.category_groups
            if group.category_id
        )
        completed_conditions = sum(
            group.listing_count
            for group in self.report.condition_groups
            if group.ebay_condition
        )
        return EbayWizardProgress(
            total_listing_checks=total,
            completed_listing_checks=completed_categories + completed_conditions,
            category_groups_remaining=sum(
                1 for group in self.report.category_groups if not group.category_id
            ),
            condition_groups_remaining=sum(
                1 for group in self.report.condition_groups if not group.ebay_condition
            ),
        )
