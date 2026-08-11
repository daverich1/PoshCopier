"""Offline eBay crosslisting settings panel."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ebay.settings import EbaySettings, EbaySettingsStore
from ebay.category_rules import EbayCategoryRuleStore
from ebay.condition_rules import EbayConditionRuleStore, SUPPORTED_EBAY_CONDITIONS
from ebay.readiness import EbayReadinessReport, EbayReadinessScanner
from dashboard.ebay_readiness_wizard import EbayReadinessWizard


class EbayPanel(ttk.LabelFrame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, text="eBay Crosslisting", padding=14)
        self.store = EbaySettingsStore()
        self.marketplace_var = tk.StringVar(value="EBAY_US")
        self.environment_var = tk.StringVar(value="sandbox")
        self.location_var = tk.StringVar()
        self.payment_var = tk.StringVar()
        self.fulfillment_var = tk.StringVar()
        self.return_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.scan_summary_var = tk.StringVar(
            value="Not scanned — scope: listings transferred to dveshop"
        )
        self.filter_var = tk.StringVar(value="All")
        self.rule_category_id_var = tk.StringVar()
        self.category_rule_store = EbayCategoryRuleStore()
        self.condition_rule_store = EbayConditionRuleStore()
        self.rule_condition_var = tk.StringVar()
        self._build_interface()
        self.load()

    def _build_interface(self) -> None:
        self.columnconfigure(1, weight=1)
        ttk.Label(
            self,
            text=(
                "Configure non-secret IDs used to prepare eBay drafts. "
                "This screen does not connect to eBay or publish listings."
            ),
            wraplength=760,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        fields = (
            ("Marketplace", self.marketplace_var),
            ("API environment", self.environment_var),
            ("Merchant location key", self.location_var),
            ("Payment policy ID", self.payment_var),
            ("Fulfillment policy ID", self.fulfillment_var),
            ("Return policy ID", self.return_var),
        )
        for row, (label, variable) in enumerate(fields, start=1):
            ttk.Label(self, text=f"{label}:").grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=5
            )
            if label == "Marketplace":
                widget = ttk.Combobox(
                    self,
                    textvariable=variable,
                    values=("EBAY_US",),
                    state="readonly",
                )
            elif label == "API environment":
                widget = ttk.Combobox(
                    self,
                    textvariable=variable,
                    values=("sandbox", "production"),
                    state="readonly",
                )
            else:
                widget = ttk.Entry(self, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=5)

        actions = ttk.Frame(self)
        actions.grid(row=7, column=0, columnspan=2, sticky="w", pady=(14, 8))
        ttk.Button(actions, text="Save Settings", command=self.save).pack(side="left")
        ttk.Button(actions, text="Reload", command=self.load).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(self, textvariable=self.status_var, wraplength=760).grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        readiness = ttk.LabelFrame(
            self,
            text="Offline Draft Readiness",
            padding=10,
        )
        readiness.grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(16, 0),
        )
        self.rowconfigure(9, weight=1)
        readiness.columnconfigure(0, weight=1)
        readiness.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(readiness)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.scan_button = ttk.Button(
            toolbar,
            text="Scan All Drafts",
            command=self.scan_all,
        )
        self.scan_button.pack(side="left")
        self.wizard_button = ttk.Button(
            toolbar,
            text="Open Readiness Wizard",
            command=self.open_readiness_wizard,
            state="disabled",
        )
        self.wizard_button.pack(side="left", padx=(8, 0))
        ttk.Label(toolbar, text="Filter:").pack(side="left", padx=(12, 6))
        filter_box = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            values=("All", "Ready", "Needs Configuration", "Needs Source Fix"),
            state="readonly",
            width=22,
        )
        filter_box.pack(side="left")
        filter_box.bind("<<ComboboxSelected>>", self._apply_scan_filter)
        ttk.Label(readiness, textvariable=self.scan_summary_var).grid(
            row=1, column=0, sticky="w", pady=(0, 8)
        )
        result_tabs = ttk.Notebook(readiness)
        result_tabs.grid(row=2, column=0, columnspan=2, sticky="nsew")
        listing_results = ttk.Frame(result_tabs)
        rule_results = ttk.Frame(result_tabs)
        condition_results = ttk.Frame(result_tabs)
        result_tabs.add(listing_results, text="Listings")
        result_tabs.add(rule_results, text="Bulk Category Rules")
        result_tabs.add(condition_results, text="Bulk Condition Rules")
        listing_results.columnconfigure(0, weight=1)
        listing_results.rowconfigure(0, weight=1)
        rule_results.columnconfigure(0, weight=1)
        rule_results.rowconfigure(0, weight=1)
        condition_results.columnconfigure(0, weight=1)
        condition_results.rowconfigure(0, weight=1)

        columns = ("status", "title", "suggestion", "category_id", "issues")
        self.readiness_tree = ttk.Treeview(
            listing_results,
            columns=columns,
            show="headings",
            height=12,
        )
        for name, label, width in (
            ("status", "Status", 135),
            ("title", "Listing", 260),
            ("suggestion", "Suggested eBay Category", 210),
            ("category_id", "Category ID", 90),
            ("issues", "Issues", 55),
        ):
            self.readiness_tree.heading(name, text=label)
            self.readiness_tree.column(name, width=width, anchor="w")
        self.readiness_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            listing_results,
            orient="vertical",
            command=self.readiness_tree.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.readiness_tree.configure(yscrollcommand=scrollbar.set)

        self.rule_tree = ttk.Treeview(
            rule_results,
            columns=("source", "suggestion", "count", "category_id"),
            show="headings",
            height=11,
            selectmode="browse",
        )
        for name, label, width in (
            ("source", "Poshmark Category", 250),
            ("suggestion", "Suggested eBay Family", 240),
            ("count", "Listings", 70),
            ("category_id", "Confirmed ID", 100),
        ):
            self.rule_tree.heading(name, text=label)
            self.rule_tree.column(name, width=width, anchor="w")
        self.rule_tree.grid(row=0, column=0, sticky="nsew")
        rule_actions = ttk.Frame(rule_results)
        rule_actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(rule_actions, text="Confirmed category ID:").pack(side="left")
        ttk.Entry(
            rule_actions,
            textvariable=self.rule_category_id_var,
            width=16,
        ).pack(side="left", padx=(6, 8))
        ttk.Button(
            rule_actions,
            text="Apply to Selected Category Group",
            command=self.apply_category_rule,
        ).pack(side="left")
        self.rule_tree.bind("<<TreeviewSelect>>", self._on_rule_selected)

        self.condition_tree = ttk.Treeview(
            condition_results,
            columns=("source", "condition", "count", "ebay"),
            show="headings",
            height=11,
            selectmode="browse",
        )
        for name, label, width in (
            ("source", "Poshmark Category", 250),
            ("condition", "Source Condition", 150),
            ("count", "Listings", 70),
            ("ebay", "eBay Condition", 160),
        ):
            self.condition_tree.heading(name, text=label)
            self.condition_tree.column(name, width=width, anchor="w")
        self.condition_tree.grid(row=0, column=0, sticky="nsew")
        condition_actions = ttk.Frame(condition_results)
        condition_actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(condition_actions, text="Confirmed eBay condition:").pack(
            side="left"
        )
        ttk.Combobox(
            condition_actions,
            textvariable=self.rule_condition_var,
            values=SUPPORTED_EBAY_CONDITIONS,
            state="readonly",
            width=24,
        ).pack(side="left", padx=(6, 8))
        ttk.Button(
            condition_actions,
            text="Apply to Selected Condition Group",
            command=self.apply_condition_rule,
        ).pack(side="left")
        self.condition_tree.bind(
            "<<TreeviewSelect>>",
            self._on_condition_rule_selected,
        )
        self._scan_report: EbayReadinessReport | None = None

    def _settings_from_form(self) -> EbaySettings:
        return EbaySettings(
            marketplace_id=self.marketplace_var.get().strip() or "EBAY_US",
            api_environment=self.environment_var.get().strip() or "sandbox",
            merchant_location_key=self.location_var.get().strip(),
            payment_policy_id=self.payment_var.get().strip(),
            fulfillment_policy_id=self.fulfillment_var.get().strip(),
            return_policy_id=self.return_var.get().strip(),
        )

    def load(self) -> None:
        settings = self.store.load()
        self.marketplace_var.set(settings.marketplace_id)
        self.environment_var.set(settings.api_environment)
        self.location_var.set(settings.merchant_location_key)
        self.payment_var.set(settings.payment_policy_id)
        self.fulfillment_var.set(settings.fulfillment_policy_id)
        self.return_var.set(settings.return_policy_id)
        self._update_status(settings)

    def save(self) -> None:
        settings = self._settings_from_form()
        try:
            self.store.save(settings)
        except OSError as error:
            messagebox.showerror("Save Failed", str(error))
            return
        self._update_status(settings)
        messagebox.showinfo("eBay Settings", "eBay draft settings were saved.")

    def _update_status(self, settings: EbaySettings) -> None:
        prefix = "EBAY_SANDBOX" if settings.api_environment == "sandbox" else "EBAY"
        credentials_ready = bool(
            os.environ.get(f"{prefix}_CLIENT_ID", "").strip()
            and os.environ.get(f"{prefix}_CLIENT_SECRET", "").strip()
        )
        credential_status = (
            f"Read-only credentials detected from {prefix}_CLIENT_ID/CLIENT_SECRET. "
            if credentials_ready
            else f"Set {prefix}_CLIENT_ID and {prefix}_CLIENT_SECRET to enable read-only lookup. "
        )
        missing = settings.missing_fields()
        if missing:
            self.status_var.set(
                credential_status
                + "Draft preparation only. Still needed before publishing: "
                + ", ".join(missing)
                + ". Numeric category IDs are selected per listing."
            )
        else:
            self.status_var.set(
                credential_status
                + "Account-independent settings are complete. Numeric eBay "
                "category IDs are still selected and validated per listing."
            )

    def scan_all(self) -> None:
        self.scan_button.configure(state="disabled")
        self.scan_summary_var.set("Scanning local drafts...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        try:
            report = EbayReadinessScanner().scan()
        except Exception as error:
            self.after(0, self._scan_failed, str(error))
            return
        self.after(0, self._show_scan_report, report)

    def _scan_failed(self, error: str) -> None:
        self.scan_button.configure(state="normal")
        self.scan_summary_var.set("Scan failed")
        messagebox.showerror("eBay Readiness Scan", error)

    def _show_scan_report(self, report: EbayReadinessReport) -> None:
        self._scan_report = report
        self.scan_button.configure(state="normal")
        self.wizard_button.configure(state="normal")
        self.scan_summary_var.set(
            f"dveshop listings: {report.total}  |  Ready: {report.ready}  |  "
            f"Needs configuration: {report.needs_configuration}  |  "
            f"Needs source fix: {report.needs_source_fix}  |  "
            f"Categories confirmed: {report.category_confirmed}/{report.total}  |  "
            f"Copied DB records without local draft data: {report.missing_local_files}"
        )
        self._apply_scan_filter()
        self._populate_category_groups()
        self._populate_condition_groups()

    def open_readiness_wizard(self) -> None:
        if self._scan_report is None:
            messagebox.showwarning(
                "eBay Readiness Wizard",
                "Run the offline draft scan first.",
            )
            return
        EbayReadinessWizard(self, self._scan_report, self._show_scan_report)

    def _apply_scan_filter(self, _event=None) -> None:
        for item_id in self.readiness_tree.get_children():
            self.readiness_tree.delete(item_id)
        if self._scan_report is None:
            return
        selected_filter = self.filter_var.get()
        for index, item in enumerate(self._scan_report.items):
            if selected_filter != "All" and item.status != selected_filter:
                continue
            self.readiness_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item.status,
                    item.title,
                    item.category_suggestion or "Manual review",
                    item.category_id or "—",
                    item.blocker_count + item.warning_count,
                ),
            )

    def _populate_category_groups(self) -> None:
        for item_id in self.rule_tree.get_children():
            self.rule_tree.delete(item_id)
        if self._scan_report is None:
            return
        for index, group in enumerate(self._scan_report.category_groups):
            self.rule_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    group.source_category,
                    group.category_suggestion or "Manual review",
                    group.listing_count,
                    group.category_id or "—",
                ),
            )

    def _on_rule_selected(self, _event=None) -> None:
        selection = self.rule_tree.selection()
        if not selection or self._scan_report is None:
            return
        group = self._scan_report.category_groups[int(selection[0])]
        self.rule_category_id_var.set(group.category_id)

    def apply_category_rule(self) -> None:
        selection = self.rule_tree.selection()
        if not selection or self._scan_report is None:
            messagebox.showwarning(
                "Bulk Category Rule",
                "Select one Poshmark category group first.",
            )
            return
        group = self._scan_report.category_groups[int(selection[0])]
        category_id = self.rule_category_id_var.get().strip()
        try:
            self.category_rule_store.set_rule(group.source_category, category_id)
        except (OSError, ValueError) as error:
            messagebox.showerror("Bulk Category Rule", str(error))
            return
        messagebox.showinfo(
            "Bulk Category Rule",
            f"Category {category_id} will apply to {group.listing_count} "
            f"listing(s) in {group.source_category}. Per-listing choices override it.",
        )
        self.scan_all()

    def _populate_condition_groups(self) -> None:
        for item_id in self.condition_tree.get_children():
            self.condition_tree.delete(item_id)
        if self._scan_report is None:
            return
        for index, group in enumerate(self._scan_report.condition_groups):
            self.condition_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    group.source_category,
                    group.source_condition,
                    group.listing_count,
                    group.ebay_condition or "—",
                ),
            )

    def _on_condition_rule_selected(self, _event=None) -> None:
        selection = self.condition_tree.selection()
        if not selection or self._scan_report is None:
            return
        group = self._scan_report.condition_groups[int(selection[0])]
        self.rule_condition_var.set(group.ebay_condition)

    def apply_condition_rule(self) -> None:
        selection = self.condition_tree.selection()
        if not selection or self._scan_report is None:
            messagebox.showwarning(
                "Bulk Condition Rule",
                "Select one source category and condition group first.",
            )
            return
        group = self._scan_report.condition_groups[int(selection[0])]
        condition = self.rule_condition_var.get().strip()
        try:
            self.condition_rule_store.set_rule(
                group.source_category,
                group.source_condition,
                condition,
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("Bulk Condition Rule", str(error))
            return
        messagebox.showinfo(
            "Bulk Condition Rule",
            f"{condition} will apply to {group.listing_count} listing(s) in "
            f"{group.source_category} with source condition "
            f"{group.source_condition}. Per-listing choices override it.",
        )
        self.scan_all()
