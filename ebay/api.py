"""Read-only eBay OAuth and Taxonomy API clients."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"
INVENTORY_SCOPE = "https://api.ebay.com/oauth/api_scope/sell.inventory"


@dataclass(frozen=True)
class EbayCredentials:
    client_id: str
    client_secret: str

    @classmethod
    def from_environment(cls, environment: str) -> "EbayCredentials":
        prefix = "EBAY_SANDBOX" if environment == "sandbox" else "EBAY"
        client_id = os.environ.get(f"{prefix}_CLIENT_ID", "").strip()
        client_secret = os.environ.get(f"{prefix}_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise RuntimeError(
                f"Set {prefix}_CLIENT_ID and {prefix}_CLIENT_SECRET "
                "in the process environment."
            )
        return cls(client_id=client_id, client_secret=client_secret)


@dataclass(frozen=True)
class EbayUserToken:
    """A seller-authorized token loaded only from the process environment."""

    value: str

    @classmethod
    def from_environment(cls, environment: str) -> "EbayUserToken":
        if environment not in ("sandbox", "production"):
            raise ValueError("environment must be sandbox or production")
        variable = (
            "EBAY_SANDBOX_USER_TOKEN"
            if environment == "sandbox"
            else "EBAY_USER_TOKEN"
        )
        value = os.environ.get(variable, "").strip()
        if not value:
            raise RuntimeError(f"Set {variable} in the process environment.")
        return cls(value=value)


@dataclass(frozen=True)
class EbayCategoryResult:
    category_id: str
    category_name: str
    breadcrumb: str


@dataclass(frozen=True)
class EbayAspectRequirement:
    name: str
    required: bool
    usage: str
    allowed_values: tuple[str, ...]


class EbayApiError(RuntimeError):
    """Sanitized API failure safe to show in the desktop UI."""


class EbayOAuthClient:
    def __init__(
        self,
        credentials: EbayCredentials,
        environment: str = "sandbox",
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if environment not in ("sandbox", "production"):
            raise ValueError("environment must be sandbox or production")
        self.credentials = credentials
        self.environment = environment
        self.opener = opener
        self._token = ""
        self._expires_at = 0.0

    @property
    def api_root(self) -> str:
        return (
            "https://api.sandbox.ebay.com"
            if self.environment == "sandbox"
            else "https://api.ebay.com"
        )

    def access_token(self) -> str:
        if self._token and time.monotonic() < self._expires_at - 60:
            return self._token
        credential_bytes = (
            f"{self.credentials.client_id}:{self.credentials.client_secret}"
        ).encode("utf-8")
        authorization = base64.b64encode(credential_bytes).decode("ascii")
        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": OAUTH_SCOPE}
        ).encode("ascii")
        request = urllib.request.Request(
            f"{self.api_root}/identity/v1/oauth2/token",
            data=body,
            headers={
                "Authorization": f"Basic {authorization}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        payload = self._open_json(request)
        token = str(payload.get("access_token", "")).strip()
        if not token:
            raise EbayApiError("eBay did not return an application access token.")
        try:
            expires_in = max(60, int(payload.get("expires_in", 7200)))
        except (TypeError, ValueError):
            expires_in = 7200
        self._token = token
        self._expires_at = time.monotonic() + expires_in
        return token

    def _open_json(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with self.opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise EbayApiError(f"eBay returned HTTP {error.code}.") from error
        except urllib.error.URLError as error:
            raise EbayApiError("Could not connect to eBay.") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise EbayApiError("eBay returned an unreadable response.") from error
        if not isinstance(payload, dict):
            raise EbayApiError("eBay returned an unexpected response.")
        return payload


class EbayTaxonomyClient:
    def __init__(self, oauth: EbayOAuthClient) -> None:
        self.oauth = oauth

    def category_suggestions(
        self,
        query: str,
        marketplace_id: str = "EBAY_US",
    ) -> list[EbayCategoryResult]:
        cleaned_query = " ".join(str(query).split())
        if not cleaned_query:
            raise ValueError("A category search query is required.")
        tree = self._get(
            "/commerce/taxonomy/v1/get_default_category_tree_id",
            {"marketplace_id": marketplace_id},
        )
        tree_id = str(tree.get("categoryTreeId", "")).strip()
        if not tree_id:
            raise EbayApiError("eBay did not return a category tree ID.")
        payload = self._get(
            f"/commerce/taxonomy/v1/category_tree/{tree_id}/get_category_suggestions",
            {"q": cleaned_query},
        )
        results: list[EbayCategoryResult] = []
        for suggestion in payload.get("categorySuggestions", []):
            if not isinstance(suggestion, dict):
                continue
            category = suggestion.get("category", {})
            if not isinstance(category, dict):
                continue
            category_id = str(category.get("categoryId", "")).strip()
            category_name = str(category.get("categoryName", "")).strip()
            if not category_id or not category_name:
                continue
            ancestors = suggestion.get("categoryTreeNodeAncestors", [])
            names = []
            if isinstance(ancestors, list):
                for ancestor in ancestors:
                    if isinstance(ancestor, dict):
                        ancestor_category = ancestor.get("category", {})
                        if isinstance(ancestor_category, dict):
                            name = str(
                                ancestor_category.get("categoryName", "")
                            ).strip()
                            if name:
                                names.append(name)
            results.append(
                EbayCategoryResult(
                    category_id=category_id,
                    category_name=category_name,
                    breadcrumb=" > ".join([*names, category_name]),
                )
            )
        return results

    def item_aspects(
        self,
        category_id: str,
        marketplace_id: str = "EBAY_US",
    ) -> list[EbayAspectRequirement]:
        cleaned_id = str(category_id).strip()
        if not cleaned_id.isdigit():
            raise ValueError("A numeric eBay category ID is required.")
        tree = self._get(
            "/commerce/taxonomy/v1/get_default_category_tree_id",
            {"marketplace_id": marketplace_id},
        )
        tree_id = str(tree.get("categoryTreeId", "")).strip()
        if not tree_id:
            raise EbayApiError("eBay did not return a category tree ID.")
        payload = self._get(
            f"/commerce/taxonomy/v1/category_tree/{tree_id}/get_item_aspects_for_category",
            {"category_id": cleaned_id},
        )
        requirements: list[EbayAspectRequirement] = []
        for aspect in payload.get("aspects", []):
            if not isinstance(aspect, dict):
                continue
            name = str(aspect.get("localizedAspectName", "")).strip()
            constraint = aspect.get("aspectConstraint", {})
            if not name or not isinstance(constraint, dict):
                continue
            values = []
            for value in aspect.get("aspectValues", []):
                if isinstance(value, dict):
                    localized = str(value.get("localizedValue", "")).strip()
                    if localized:
                        values.append(localized)
            requirements.append(
                EbayAspectRequirement(
                    name=name,
                    required=bool(constraint.get("aspectRequired", False)),
                    usage=str(constraint.get("aspectUsage", "OPTIONAL")).strip(),
                    allowed_values=tuple(values),
                )
            )
        requirements.sort(key=lambda item: (not item.required, item.name.casefold()))
        return requirements

    def _get(self, path: str, parameters: dict[str, str]) -> dict[str, Any]:
        url = f"{self.oauth.api_root}{path}?{urllib.parse.urlencode(parameters)}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.oauth.access_token()}",
                "Accept": "application/json",
            },
            method="GET",
        )
        return self.oauth._open_json(request)
