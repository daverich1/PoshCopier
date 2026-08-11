"""Review one offline eBay draft from the Inventory screen."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ebay.draft import EbayDraft, EbayDraftBuilder
from ebay.inventory_payload import EbayInventoryPayloadBuilder
from ebay.category_rules import EbayCategoryRuleStore
from ebay.condition_rules import EbayConditionRuleStore, SUPPORTED_EBAY_CONDITIONS
from ebay.api import EbayApiError, EbayCredentials, EbayOAuthClient, EbayTaxonomyClient
from ebay.draft_store import EbayDraftReview, EbayDraftReviewStore
from ebay.settings import EbaySettingsStore
from inventory.inventory_item import InventoryItem


class EbayDraftDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, item: InventoryItem) -> None:
        super().__init__(parent)
        self.item = item
        self.builder = EbayDraftBuilder()
        self.settings_store = EbaySettingsStore()
        self.review_store = EbayDraftReviewStore()
        self.category_rule_store = EbayCategoryRuleStore()
        self.condition_rule_store = EbayConditionRuleStore()
        self.payload = json.loads(item.listing_path.read_text(encoding="utf-8"))
        self.category_id_var = tk.StringVar()
        self.category_suggestion_var = tk.StringVar()
        self.condition_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.search_var = tk.StringVar(value=item.title)
        self._aspect_requirements = []
        self.title(f"Review eBay Draft - {item.title or item.listing_id}")
        self.geometry("820x760")
        self.minsize(720, 620)
        self.transient(parent)
        self.grab_set()
        self._build_interface()
        review = self.review_store.load(item.listing_id)
        source_category = str(self.payload.get("category", "")).strip()
        self.category_id_var.set(
            review.category_id
            or self.category_rule_store.load().get(source_category, "")
        )
        source_condition = str(self.payload.get("condition", "")).strip()
        self.condition_var.set(
            review.condition
            or self.condition_rule_store.get_rule(source_category, source_condition)
        )
        self.category_id_var.trace_add("write", self._on_category_changed)
        self.condition_var.trace_add("write", self._on_category_changed)
        self._refresh_preview()

    def _build_interface(self) -> None:
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(8, weight=1)

        ttk.Label(main, text="eBay Draft Review", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(main, text="Suggested category:").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Label(main, textvariable=self.category_suggestion_var).grid(
            row=1, column=1, sticky="w", pady=4
        )
        ttk.Label(main, text="Confirmed numeric category ID:").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(main, textvariable=self.category_id_var).grid(
            row=2, column=1, sticky="ew", pady=4
        )
        ttk.Label(
            main,
            text=(
                "The suggestion is informational. Enter only an eBay category ID "
                "you have confirmed; unknown or blank IDs remain blocked."
            ),
            wraplength=730,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 10))

        ttk.Label(main, text="Confirmed eBay condition:").grid(
            row=4, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Combobox(
            main,
            textvariable=self.condition_var,
            values=("", *SUPPORTED_EBAY_CONDITIONS),
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(main, textvariable=self.status_var, wraplength=730).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        search = ttk.LabelFrame(main, text="Read-only eBay Category Lookup", padding=8)
        search.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        search.columnconfigure(0, weight=1)
        ttk.Entry(search, textvariable=self.search_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        self.lookup_button = ttk.Button(
            search, text="Find Categories", command=self.lookup_categories
        )
        self.lookup_button.grid(row=0, column=1)
        self.aspect_button = ttk.Button(
            search,
            text="Check Required Aspects",
            command=self.lookup_aspects,
        )
        self.aspect_button.grid(row=0, column=2, padx=(8, 0))
        self.results = ttk.Treeview(
            search,
            columns=("id", "category"),
            show="headings",
            height=5,
            selectmode="browse",
        )
        self.results.heading("id", text="Category ID")
        self.results.heading("category", text="eBay category path")
        self.results.column("id", width=100, anchor="center")
        self.results.column("category", width=560, anchor="w")
        self.results.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.results.bind("<Double-1>", self._use_selected_category)

        self.summary = tk.Text(main, height=8, wrap="word", state="disabled")
        self.summary.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.issues = tk.Text(main, wrap="word", state="disabled")
        self.issues.grid(row=8, column=0, columnspan=2, sticky="nsew")

        actions = ttk.Frame(main)
        actions.grid(row=9, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Save Draft Review", command=self.save).pack(
            side="left"
        )
        ttk.Button(
            actions,
            text="Preview Sandbox Inventory JSON",
            command=self.preview_inventory_json,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Close", command=self.destroy).pack(
            side="left", padx=(8, 0)
        )

    def preview_inventory_json(self) -> None:
        try:
            preview = EbayInventoryPayloadBuilder().preview(
                self._build_draft(), environment="sandbox"
            )
        except ValueError as error:
            messagebox.showerror("Inventory Preview Blocked", str(error))
            return
        window = tk.Toplevel(self)
        window.title("Unpublished eBay Sandbox Inventory Request")
        window.geometry("780x620")
        text = tk.Text(window, wrap="none")
        text.pack(fill="both", expand=True, padx=12, pady=12)
        text.insert("1.0", preview.to_json())
        text.configure(state="disabled")

    def _build_draft(self) -> EbayDraft:
        settings = self.settings_store.load()
        return self.builder.build(
            self.payload,
            self.item.listing_path.parent,
            category_id=self.category_id_var.get().strip() or None,
            merchant_location_key=settings.merchant_location_key,
            payment_policy_id=settings.payment_policy_id,
            fulfillment_policy_id=settings.fulfillment_policy_id,
            return_policy_id=settings.return_policy_id,
            condition_override=self.condition_var.get().strip() or None,
        )

    def _on_category_changed(self, *_args) -> None:
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        draft = self._build_draft()
        self.category_suggestion_var.set(
            draft.category_suggestion or "No suggestion — manual review required"
        )
        self.status_var.set(
            "Ready to publish configuration" if draft.ready_to_publish
            else "Draft is blocked until the items below are resolved"
        )
        summary = (
            f"SKU: {draft.sku}\n"
            f"Title: {draft.title}\n"
            f"Price: ${draft.price or '—'}    Quantity: {draft.quantity}\n"
            f"Condition: {draft.condition or 'Unmapped'}\n"
            f"Images: {len(draft.image_paths)}\n"
            f"Aspects: {draft.aspects}"
        )
        issue_lines = ["BLOCKERS"]
        issue_lines.extend(f"• {value}" for value in draft.blockers)
        issue_lines.append("\nWARNINGS")
        issue_lines.extend(f"• {value}" for value in draft.warnings)
        if not draft.warnings:
            issue_lines.append("• None")
        if self._aspect_requirements:
            provided = {name.casefold() for name in draft.aspects}
            issue_lines.append("\nEBAY CATEGORY ASPECTS")
            for requirement in self._aspect_requirements:
                state = "provided" if requirement.name.casefold() in provided else "missing"
                level = "REQUIRED" if requirement.required else requirement.usage
                issue_lines.append(
                    f"• {level}: {requirement.name} — {state}"
                )
        self._set_text(self.summary, summary)
        self._set_text(self.issues, "\n".join(issue_lines))

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def save(self) -> None:
        category_id = self.category_id_var.get().strip()
        if category_id and not category_id.isdigit():
            messagebox.showerror(
                "Invalid Category ID",
                "The eBay category ID must contain digits only.",
            )
            return
        try:
            path = self.review_store.save(
                EbayDraftReview(
                    source_listing_id=self.item.listing_id,
                    category_id=category_id,
                    condition=self.condition_var.get().strip(),
                )
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("Save Failed", str(error))
            return
        self._refresh_preview()
        messagebox.showinfo("Draft Review Saved", f"Saved to:\n{path}")

    def lookup_categories(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Category Lookup", "Enter category keywords first.")
            return
        self.lookup_button.configure(state="disabled")
        self.status_var.set("Requesting read-only suggestions from eBay...")
        threading.Thread(
            target=self._lookup_worker,
            args=(query,),
            daemon=True,
        ).start()

    def _lookup_worker(self, query: str) -> None:
        try:
            settings = self.settings_store.load()
            credentials = EbayCredentials.from_environment(settings.api_environment)
            client = EbayTaxonomyClient(
                EbayOAuthClient(credentials, settings.api_environment)
            )
            results = client.category_suggestions(query, settings.marketplace_id)
        except (EbayApiError, RuntimeError, ValueError) as error:
            self.after(0, self._lookup_failed, str(error))
            return
        self.after(0, self._show_lookup_results, results)

    def _lookup_failed(self, error: str) -> None:
        self.lookup_button.configure(state="normal")
        self._refresh_preview()
        messagebox.showerror("eBay Category Lookup", error)

    def _show_lookup_results(self, results) -> None:
        for item_id in self.results.get_children():
            self.results.delete(item_id)
        for index, result in enumerate(results):
            self.results.insert(
                "",
                "end",
                iid=str(index),
                values=(result.category_id, result.breadcrumb),
            )
        self.lookup_button.configure(state="normal")
        self.status_var.set(
            f"eBay returned {len(results)} leaf-category suggestion(s). "
            "Double-click one to use its ID."
        )

    def _use_selected_category(self, _event=None) -> None:
        selection = self.results.selection()
        if not selection:
            return
        values = self.results.item(selection[0], "values")
        if values:
            self.category_id_var.set(str(values[0]))

    def lookup_aspects(self) -> None:
        category_id = self.category_id_var.get().strip()
        if not category_id.isdigit():
            messagebox.showwarning(
                "eBay Item Specifics",
                "Select or enter a numeric eBay category ID first.",
            )
            return
        self.aspect_button.configure(state="disabled")
        self.status_var.set("Requesting read-only item requirements from eBay...")
        threading.Thread(
            target=self._aspect_worker,
            args=(category_id,),
            daemon=True,
        ).start()

    def _aspect_worker(self, category_id: str) -> None:
        try:
            settings = self.settings_store.load()
            credentials = EbayCredentials.from_environment(settings.api_environment)
            client = EbayTaxonomyClient(
                EbayOAuthClient(credentials, settings.api_environment)
            )
            requirements = client.item_aspects(
                category_id,
                settings.marketplace_id,
            )
        except (EbayApiError, RuntimeError, ValueError) as error:
            self.after(0, self._aspect_failed, str(error))
            return
        self.after(0, self._show_aspects, requirements)

    def _aspect_failed(self, error: str) -> None:
        self.aspect_button.configure(state="normal")
        self._refresh_preview()
        messagebox.showerror("eBay Item Specifics", error)

    def _show_aspects(self, requirements) -> None:
        self._aspect_requirements = list(requirements)
        self.aspect_button.configure(state="normal")
        required = sum(1 for value in requirements if value.required)
        self._refresh_preview()
        self.status_var.set(
            f"Loaded {len(requirements)} item specifics from eBay; "
            f"{required} required. Review the category-aspects section below."
        )
