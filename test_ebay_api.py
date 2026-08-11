"""Tests for read-only eBay OAuth and Taxonomy clients."""

from __future__ import annotations

import json
import os
import time
import unittest

from ebay.api import EbayCredentials, EbayOAuthClient, EbayTaxonomyClient, EbayUserToken


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class EbayApiTests(unittest.TestCase):
    def test_user_token_uses_environment_and_is_not_serialized(self):
        previous = os.environ.get("EBAY_SANDBOX_USER_TOKEN")
        os.environ["EBAY_SANDBOX_USER_TOKEN"] = "seller-token"
        try:
            self.assertEqual(
                EbayUserToken.from_environment("sandbox").value, "seller-token"
            )
        finally:
            if previous is None:
                os.environ.pop("EBAY_SANDBOX_USER_TOKEN", None)
            else:
                os.environ["EBAY_SANDBOX_USER_TOKEN"] = previous

    def test_client_credentials_token_is_cached(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeResponse({"access_token": "token", "expires_in": 7200})

        client = EbayOAuthClient(
            EbayCredentials("id", "secret"),
            opener=opener,
        )
        self.assertEqual(client.access_token(), "token")
        self.assertEqual(client.access_token(), "token")
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0][0].get_header("Authorization").startswith("Basic "))

    def test_taxonomy_returns_leaf_suggestions(self):
        client = EbayOAuthClient(EbayCredentials("id", "secret"))
        client._token = "token"
        client._expires_at = time.monotonic() + 3600
        responses = iter(
            [
                {"categoryTreeId": "0"},
                {
                    "categorySuggestions": [
                        {
                            "category": {
                                "categoryId": "63861",
                                "categoryName": "Dresses",
                            },
                            "categoryTreeNodeAncestors": [
                                {"category": {"categoryName": "Women"}}
                            ],
                        }
                    ]
                },
            ]
        )
        client._open_json = lambda _request: next(responses)
        results = EbayTaxonomyClient(client).category_suggestions("blue dress")
        self.assertEqual(results[0].category_id, "63861")
        self.assertEqual(results[0].breadcrumb, "Women > Dresses")

    def test_taxonomy_parses_required_aspects(self):
        client = EbayOAuthClient(EbayCredentials("id", "secret"))
        client._token = "token"
        client._expires_at = time.monotonic() + 3600
        responses = iter(
            [
                {"categoryTreeId": "0"},
                {
                    "aspects": [
                        {
                            "localizedAspectName": "Brand",
                            "aspectConstraint": {
                                "aspectRequired": True,
                                "aspectUsage": "RECOMMENDED",
                            },
                            "aspectValues": [
                                {"localizedValue": "Unbranded"}
                            ],
                        },
                        {
                            "localizedAspectName": "Style",
                            "aspectConstraint": {
                                "aspectRequired": False,
                                "aspectUsage": "OPTIONAL",
                            },
                        },
                    ]
                },
            ]
        )
        client._open_json = lambda _request: next(responses)
        aspects = EbayTaxonomyClient(client).item_aspects("63861")
        self.assertEqual(aspects[0].name, "Brand")
        self.assertTrue(aspects[0].required)
        self.assertEqual(aspects[0].allowed_values, ("Unbranded",))


if __name__ == "__main__":
    unittest.main()
