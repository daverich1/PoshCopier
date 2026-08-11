"""Tests for the offline eBay readiness wizard progress model."""

from __future__ import annotations

import unittest

from ebay.readiness import EbayCategoryGroup, EbayConditionGroup, EbayReadinessReport
from ebay.readiness_wizard import EbayReadinessWizardState


class EbayReadinessWizardStateTests(unittest.TestCase):
    def _report(self):
        return EbayReadinessReport(
            items=(),
            ready=0,
            needs_configuration=0,
            needs_source_fix=0,
            category_confirmed=4,
            database_eligible=10,
            missing_local_files=0,
            category_groups=(
                EbayCategoryGroup("WomenDresses", "Dresses", 4, "63861"),
                EbayCategoryGroup("WomenBags", "Bags", 6, ""),
            ),
            condition_groups=(
                EbayConditionGroup("WomenDresses", "NWT", 4, "NEW"),
                EbayConditionGroup("WomenBags", "Used", 6, ""),
            ),
        )

    def test_returns_first_unresolved_groups(self):
        state = EbayReadinessWizardState(self._report())
        self.assertEqual(state.next_category().source_category, "WomenBags")
        self.assertEqual(state.next_condition().source_condition, "Used")

    def test_progress_is_weighted_by_affected_listings(self):
        report = self._report()
        report = EbayReadinessReport(
            **{**report.__dict__, "items": tuple(object() for _ in range(10))}
        )
        progress = EbayReadinessWizardState(report).progress()
        self.assertEqual(progress.completed_listing_checks, 8)
        self.assertEqual(progress.total_listing_checks, 20)
        self.assertEqual(progress.percent, 40.0)


if __name__ == "__main__":
    unittest.main()
