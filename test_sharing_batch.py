"""Focused unit tests for sharing batch coordination and safety gates."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import Mock, patch

from sharing.share_config import MAX_FOLLOWER_SHARES_PER_RUN, ShareConfig
from sharing.share_engine import FollowCandidate, PoshmarkShareEngine, ShareableListing
from sharing.follow_runner import USERNAME_PATTERN
from sharing.share_progress import ShareResult, ShareStatus
from sharing.share_runner import (
    closet_name_from_url,
    collect_shareable_listings,
    listing_id_from_url,
)
from sharing.party_runner import run_live_party_batch, run_party_candidate
from party.eligibility import is_listing_eligible_for_party, party_brand_matches
from party.party_models import (
    GuidelineParseConfidence,
    PartyEligibilityStatus,
    PartyGuidelines,
    PartyType,
    PoshParty,
)
from scraper.availability import (
    AvailabilityResult,
    AvailabilityStatus,
)


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

    def test_follower_share_limit_accepts_1000_and_rejects_more(self):
        config = ShareConfig(
            closet_url="https://poshmark.com/closet/test",
            max_shares=MAX_FOLLOWER_SHARES_PER_RUN,
        )
        self.assertEqual(config.max_shares, 1000)
        with self.assertRaisesRegex(ValueError, "cannot exceed 1000"):
            ShareConfig(
                closet_url="https://poshmark.com/closet/test",
                max_shares=1001,
            )

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

    def test_listing_collection_scrolls_beyond_initial_page(self):
        ids = [f"{index:024x}" for index in range(1, 6)]

        class FakeLink:
            def __init__(self, listing_id):
                self.listing_id = listing_id

            def get_attribute(self, name):
                if name == "href":
                    return f"/listing/Test-{self.listing_id}"
                if name == "title":
                    return f"Item {self.listing_id}"
                return None

        class FakeLocator:
            def __init__(self, page):
                self.page = page

            def all(self):
                visible = ids[: min(len(ids), (self.page.scrolls + 1) * 2)]
                return [FakeLink(listing_id) for listing_id in visible]

        class FakePage:
            def __init__(self):
                self.scrolls = 0

            def goto(self, *_args, **_kwargs):
                return None

            def wait_for_timeout(self, _milliseconds):
                return None

            def locator(self, selector):
                self.assert_selector = selector
                return FakeLocator(self)

            def evaluate(self, _script):
                self.scrolls += 1

        page = FakePage()
        with patch(
            "sharing.share_runner._apply_available_items_filter",
            return_value=True,
        ), patch(
            "sharing.share_runner.verify_listing_availability",
            return_value=AvailabilityResult(
                AvailabilityStatus.AVAILABLE,
                True,
                "active purchase control",
            ),
        ):
            listings = collect_shareable_listings(
                page,
                "https://poshmark.com/closet/test",
                5,
            )

        self.assertEqual([listing.listing_id for listing in listings], ids)
        self.assertTrue(all(listing.available and listing.active for listing in listings))
        self.assertGreaterEqual(page.scrolls, 2)

    def test_listing_collection_excludes_unavailable_and_ambiguous_items(self):
        ids = [f"{index:024x}" for index in range(1, 4)]

        link = lambda listing_id: Mock(
            get_attribute=Mock(
                side_effect=lambda name: (
                    f"/listing/Test-{listing_id}" if name == "href" else "Test"
                )
            )
        )
        page = Mock()
        page.locator.return_value.all.return_value = [link(value) for value in ids]
        results = iter(
            (
                AvailabilityResult(AvailabilityStatus.SOLD, False, "sold"),
                AvailabilityResult(AvailabilityStatus.UNKNOWN, False, "ambiguous"),
                AvailabilityResult(AvailabilityStatus.AVAILABLE, True, "in stock"),
            )
        )

        with patch(
            "sharing.share_runner._apply_available_items_filter",
            return_value=True,
        ), patch(
            "sharing.share_runner.verify_listing_availability",
            side_effect=lambda _page: next(results),
        ):
            listings = collect_shareable_listings(
                page,
                "https://poshmark.com/closet/test",
                3,
            )

        self.assertEqual([listing.listing_id for listing in listings], [ids[2]])
        self.assertTrue(listings[0].available)
        self.assertTrue(listings[0].active)

    def test_listing_collection_stops_when_poshmark_filters_are_not_verified(self):
        page = Mock()
        with patch(
            "sharing.share_runner._apply_available_items_filter",
            return_value=False,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Available Items and Active Items filters",
            ):
                collect_shareable_listings(
                    page,
                    "https://poshmark.com/closet/test",
                    10,
                )
        page.locator.assert_not_called()

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

    def test_automatic_party_batch_enforces_finite_safety_limit(self):
        result = run_live_party_batch(51, perform_share=False)
        self.assertFalse(result.success)
        self.assertIn("1-50", result.message)

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

    def test_party_eligibility_accepts_confirmed_hoka_brand_alias(self):
        party = PoshParty(
            party_id="activewear",
            name="Activewear Party",
            url="https://poshmark.com/party/activewear",
            start_time_text="Happening now",
            start_at=None,
            is_live=True,
            party_type=PartyType.BRAND_LIMITED,
            guidelines=PartyGuidelines(
                theme="Activewear Party",
                brands_allowed=["Hoka"],
                categories_allowed=["All"],
                departments_allowed=[],
                sizes_allowed=[],
                other_rules=[],
                parse_confidence=GuidelineParseConfidence.HIGH,
            ),
        )
        result = is_listing_eligible_for_party(
            {
                "availability": AvailabilityStatus.AVAILABLE,
                "brand": "Hoka One One",
                "department": "Women",
                "category": "Shoes",
                "subcategory": "Sneakers",
                "size": "10.5",
            },
            party,
        )
        self.assertEqual(result.status, PartyEligibilityStatus.ELIGIBLE)

    def test_party_brand_phrase_matching_uses_word_boundaries(self):
        self.assertTrue(party_brand_matches("Hoka One One", "Hoka"))
        self.assertTrue(party_brand_matches("Champion Sports", "Champion"))
        self.assertFalse(party_brand_matches("Adrienne Vittadini", "REI"))
        self.assertFalse(party_brand_matches("Steve Madden", "Teva"))

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
