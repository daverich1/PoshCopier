"""Focused unit tests for sharing batch coordination and safety gates."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import Mock, patch

from sharing.share_config import ShareConfig
from sharing.share_engine import FollowCandidate, PoshmarkShareEngine, ShareableListing
from sharing.follow_runner import USERNAME_PATTERN
from sharing.share_progress import ShareResult, ShareStatus
from sharing.share_runner import closet_name_from_url, listing_id_from_url
from sharing.party_runner import run_party_candidate
from party.eligibility import is_listing_eligible_for_party
from party.party_models import (
    GuidelineParseConfidence,
    PartyEligibilityStatus,
    PartyGuidelines,
    PartyType,
    PoshParty,
)
from scraper.availability import AvailabilityStatus


@dataclass
class FakeParty:
    party_id: str = "party-1"
    name: str = "Test Party"
    is_live: bool = True


class SharingBatchTests(unittest.TestCase):
    def make_engine(self, **config_values):
        progress = []
        config = ShareConfig(
            closet_url="https://poshmark.com/closet/test",
            delay_seconds=0,
            jitter_seconds=0,
            **config_values,
        )
        engine = PoshmarkShareEngine(Mock(), config, progress.append)
        return engine, progress

    def test_follower_batch_respects_limit_and_reports_progress(self):
        engine, progress = self.make_engine(max_shares=2)
        engine.share_listing = Mock(return_value=ShareResult(
            success=True,
            shared=1,
            message="Shared",
        ))
        listings = [
            ShareableListing(str(index), f"https://example/{index}", f"Item {index}")
            for index in range(3)
        ]

        result = engine.share_batch(listings)

        self.assertTrue(result.success)
        self.assertEqual(result.shared, 2)
        self.assertEqual(engine.share_listing.call_count, 2)
        self.assertEqual(progress[-1].status, ShareStatus.COMPLETE)
        self.assertEqual((progress[-1].current, progress[-1].total), (2, 2))

    def test_listing_id_is_extracted_from_poshmark_url(self):
        listing_id = "6a787cd595154f1af9ebbb27"
        url = f"https://poshmark.com/listing/Example-Title-{listing_id}?utm_source=test"

        self.assertEqual(listing_id_from_url(url), listing_id)
        self.assertEqual(listing_id_from_url("https://example.com/not-a-listing"), "")

    def test_closet_url_validation_is_strict(self):
        self.assertEqual(
            closet_name_from_url("https://poshmark.com/closet/OtherSeller"),
            "otherseller",
        )
        self.assertEqual(closet_name_from_url("https://example.com/closet/test"), "")
        self.assertEqual(closet_name_from_url("https://poshmark.com/listing/test"), "")

    def test_community_batch_is_disabled_by_default(self):
        engine, progress = self.make_engine()

        result = engine.share_community_batch([])

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Community sharing disabled")
        self.assertEqual(progress, [])

    def test_community_batch_respects_explicit_limit(self):
        engine, progress = self.make_engine(
            share_community_listings=True,
            community_share_limit=2,
        )
        engine.share_listing = Mock(return_value=ShareResult(
            success=True,
            shared=1,
            message="Shared",
        ))
        listings = [
            ShareableListing(str(index), f"https://example/{index}", f"Item {index}")
            for index in range(3)
        ]

        result = engine.share_community_batch(listings)

        self.assertTrue(result.success)
        self.assertEqual(result.shared, 2)
        self.assertEqual(engine.share_listing.call_count, 2)
        self.assertEqual(progress[-1].total, 2)

    def test_follow_back_batch_is_disabled_by_default(self):
        engine, progress = self.make_engine()

        result = engine.follow_back_batch([])

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Follow-backs disabled")
        self.assertEqual(progress, [])

    def test_follow_back_batch_respects_explicit_limit(self):
        engine, progress = self.make_engine(
            follow_backs_enabled=True,
            follow_back_limit=1,
        )
        engine.follow_back = Mock(return_value=ShareResult(
            success=True,
            shared=1,
            message="Followed",
        ))
        candidates = [
            FollowCandidate("first", "https://poshmark.com/closet/first", "@first"),
            FollowCandidate("second", "https://poshmark.com/closet/second", "@second"),
        ]

        result = engine.follow_back_batch(candidates)

        self.assertTrue(result.success)
        self.assertEqual(result.shared, 1)
        engine.follow_back.assert_called_once_with(candidates[0])
        self.assertEqual(progress[-1].total, 1)

    def test_follower_candidate_username_pattern_is_strict(self):
        self.assertEqual(USERNAME_PATTERN.fullmatch("/closet/example_1").group(1), "example_1")
        self.assertIsNone(USERNAME_PATTERN.fullmatch("/listing/example_1"))
        self.assertIsNone(USERNAME_PATTERN.fullmatch("/closet/example/extra"))

    def test_party_runner_rejects_invalid_listing_url_before_browser(self):
        result = run_party_candidate(
            "https://poshmark.com/listing/not-valid",
            "Example Party",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.failed, 1)
        self.assertIn("valid Poshmark ID", result.message)

    def test_party_eligibility_matches_combined_department_category(self):
        party = PoshParty(
            party_id="tops",
            name="Tops Party",
            url="https://poshmark.com/party/tops",
            start_time_text="Today at 3:00 PM",
            start_at=None,
            is_live=False,
            guidelines=PartyGuidelines(
                theme="Tops Party",
                brands_allowed=["All"],
                categories_allowed=["Women Tops"],
                departments_allowed=[],
                sizes_allowed=[],
                other_rules=[],
                parse_confidence=GuidelineParseConfidence.HIGH,
            ),
            party_type=PartyType.CATEGORY_LIMITED,
        )
        listing = {
            "availability": AvailabilityStatus.AVAILABLE,
            "brand": "Example",
            "department": "Women",
            "category": "Tops",
            "subcategory": "Blouses",
            "size": "M",
        }

        result = is_listing_eligible_for_party(listing, party)

        self.assertEqual(result.status, PartyEligibilityStatus.ELIGIBLE)

    def test_batch_skips_unavailable_listing_without_sharing_it(self):
        engine, progress = self.make_engine()
        engine.share_listing = Mock(return_value=ShareResult(success=True, shared=1))
        listings = [
            ShareableListing("1", "https://example/1", "Unavailable", available=False),
            ShareableListing("2", "https://example/2", "Available"),
        ]

        result = engine.share_batch(listings)

        self.assertTrue(result.success)
        self.assertEqual((result.shared, result.skipped, result.failed), (1, 1, 0))
        engine.share_listing.assert_called_once_with(listings[1])
        self.assertEqual(progress[-1].status, ShareStatus.COMPLETE)

    def test_batch_stops_after_configured_consecutive_failures(self):
        engine, progress = self.make_engine(stop_on_failures=2)
        engine.share_listing = Mock(return_value=ShareResult(
            success=False,
            failed=1,
            message="Failed",
        ))
        listings = [
            ShareableListing(str(index), f"https://example/{index}", f"Item {index}")
            for index in range(3)
        ]

        result = engine.share_batch(listings)

        self.assertFalse(result.success)
        self.assertEqual(result.failed, 2)
        self.assertEqual(engine.share_listing.call_count, 2)
        self.assertEqual(progress[-1].status, ShareStatus.FAILED)

    def test_party_batch_is_disabled_by_default(self):
        engine, progress = self.make_engine()

        result = engine.share_batch_to_party([], FakeParty())

        self.assertFalse(result.success)
        self.assertEqual(result.failed, 1)
        self.assertEqual(progress, [])

    def test_party_gate_requires_confirmed_eligibility(self):
        engine, _ = self.make_engine(share_to_parties=True)
        listing = ShareableListing(
            "1",
            "https://example/1",
            "Unchecked",
            active=True,
        )

        result = engine.share_listing_to_party(listing, FakeParty(), retry=False)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Listing not eligible for party")
        self.assertEqual(result.eligibility_status, "NOT_ELIGIBLE")

    def test_direct_party_share_is_disabled_by_default(self):
        engine, _ = self.make_engine()
        listing = ShareableListing(
            "1",
            "https://example/1",
            "Eligible",
            active=True,
            party_eligible=True,
        )

        result = engine.share_listing_to_party(listing, FakeParty(), retry=False)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Party sharing disabled")

    def test_party_batch_respects_single_share_default(self):
        engine, progress = self.make_engine(share_to_parties=True)
        engine.share_listing_to_party = Mock(return_value=ShareResult(
            success=True,
            shared=1,
            message="Shared",
        ))
        listings = [
            ShareableListing(
                str(index),
                f"https://example/{index}",
                f"Item {index}",
                party_eligible=True,
            )
            for index in range(2)
        ]

        with patch.object(engine, "_apply_delay"):
            result = engine.share_batch_to_party(listings, FakeParty())

        self.assertTrue(result.success)
        self.assertEqual(result.shared, 1)
        self.assertEqual(engine.share_listing_to_party.call_count, 1)
        self.assertEqual(progress[-1].total, 1)


if __name__ == "__main__":
    unittest.main()
