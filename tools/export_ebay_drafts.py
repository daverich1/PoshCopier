"""Export offline eBay drafts for review; never logs in or publishes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ebay.draft import EbayDraftBuilder
from ebay.category_rules import EbayCategoryRuleStore
from ebay.condition_rules import EbayConditionRuleStore
from ebay.draft_store import EbayDraftReviewStore
from ebay.settings import EbaySettingsStore
from ebay.source_scope import dveshop_source_listing_ids
from runtime_paths import DOWNLOADS_DIR


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/ebay_drafts.json"),
    )
    args = parser.parse_args()
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")

    builder = EbayDraftBuilder()
    settings = EbaySettingsStore().load()
    review_store = EbayDraftReviewStore()
    eligible_listing_ids = dveshop_source_listing_ids()
    category_rules = EbayCategoryRuleStore().load()
    condition_rule_store = EbayConditionRuleStore()
    drafts: list[dict] = []
    for listing_file in sorted(DOWNLOADS_DIR.glob("*/listing.json")):
        listing = json.loads(listing_file.read_text(encoding="utf-8"))
        listing_id = str(listing.get("listing_id", "")).strip()
        if listing_id not in eligible_listing_ids:
            continue
        review = review_store.load(listing_id) if listing_id else None
        source_category = str(listing.get("category", "")).strip()
        category_id = (
            review.category_id if review and review.category_id
            else category_rules.get(source_category)
        )
        condition = (
            review.condition if review and review.condition
            else condition_rule_store.get_rule(
                source_category,
                str(listing.get("condition", "")).strip(),
            )
        )
        drafts.append(
            builder.build(
                listing,
                listing_file.parent,
                category_id=category_id,
                merchant_location_key=settings.merchant_location_key,
                payment_policy_id=settings.payment_policy_id,
                fulfillment_policy_id=settings.fulfillment_policy_id,
                return_policy_id=settings.return_policy_id,
                condition_override=condition or None,
            ).to_dict()
        )
        if len(drafts) >= args.limit:
            break

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(drafts, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Exported {len(drafts)} offline drafts to {args.output}")
    print("No eBay login, API call, or publishing action was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
