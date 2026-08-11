"""Guided offline review for eBay category and condition rules."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from ebay.category_rules import EbayCategoryRuleStore
from ebay.condition_rules import EbayConditionRuleStore, SUPPORTED_EBAY_CONDITIONS
from ebay.readiness import EbayReadinessReport, EbayReadinessScanner
from ebay.readiness_wizard import EbayReadinessWizardState


class EbayReadinessWizard(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        report: EbayReadinessReport,
        on_saved: Callable[[EbayReadinessReport], None],
    ) -> None:
        super().__init__(parent)
        self.report = report
        self.on_saved = on_saved
        self.state_model = EbayReadinessWizardState(report)
        self.category_store = EbayCategoryRuleStore()
        self.condition_store = EbayConditionRuleStore()
        self.category_id_var = tk.StringVar()
        self.condition_var = tk.StringVar()
        self.heading_var = tk.StringVar()
        self.detail_var = tk.StringVar()
        self.progress_var = tk.StringVar()
        self.mode = "category"
        self.current_group = None

        self.title("eBay Listing Readiness Wizard")
        self.geometry("720x470")
        self.minsize(640, 420)
        self.transient(parent)
        self.grab_set()
        self._build_interface()
        self._show_next()

    def _build_interface(self) -> None:
        main = ttk.Frame(self, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        ttk.Label(main, text="Offline eBay Readiness Wizard", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            main,
            text=(
                "Review one reusable rule at a time. Nothing here contacts eBay, "
                "creates inventory, or publishes a listing."
            ),
            wraplength=660,
        ).grid(row=1, column=0, sticky="w", pady=(6, 14))

        ttk.Label(main, textvariable=self.progress_var).grid(
            row=2, column=0, sticky="w"
        )
        self.progressbar = ttk.Progressbar(main, maximum=100)
        self.progressbar.grid(row=3, column=0, sticky="ew", pady=(4, 18))

        card = ttk.LabelFrame(main, text="Current review", padding=14)
        card.grid(row=4, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        ttk.Label(card, textvariable=self.heading_var, wraplength=620).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(card, textvariable=self.detail_var, wraplength=620).grid(
            row=1, column=0, sticky="w", pady=(8, 14)
        )

        self.category_frame = ttk.Frame(card)
        self.category_frame.grid(row=2, column=0, sticky="ew")
        self.category_frame.columnconfigure(1, weight=1)
        ttk.Label(self.category_frame, text="Confirmed numeric eBay category ID:").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Entry(self.category_frame, textvariable=self.category_id_var).grid(
            row=0, column=1, sticky="ew"
        )

        self.condition_frame = ttk.Frame(card)
        self.condition_frame.columnconfigure(1, weight=1)
        ttk.Label(self.condition_frame, text="Confirmed eBay condition:").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Combobox(
            self.condition_frame,
            textvariable=self.condition_var,
            values=SUPPORTED_EBAY_CONDITIONS,
            state="readonly",
        ).grid(row=0, column=1, sticky="ew")

        actions = ttk.Frame(main)
        actions.grid(row=5, column=0, sticky="e", pady=(18, 0))
        self.save_button = ttk.Button(
            actions, text="Save and Continue", command=self._save_current
        )
        self.save_button.pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy).pack(
            side="left", padx=(8, 0)
        )

    def _show_next(self) -> None:
        progress = self.state_model.progress()
        self.progressbar["value"] = progress.percent
        self.progress_var.set(
            f"Review progress: {progress.percent:.1f}%  |  "
            f"Category groups remaining: {progress.category_groups_remaining}  |  "
            f"Condition groups remaining: {progress.condition_groups_remaining}"
        )
        group = self.state_model.next_category()
        if group is not None:
            self.mode = "category"
            self.current_group = group
            self.heading_var.set(group.source_category or "Uncategorized source listings")
            self.detail_var.set(
                f"Applies to {group.listing_count} listing(s). Suggested eBay family: "
                f"{group.category_suggestion or 'manual review required'}. Confirm the "
                "numeric leaf-category ID before saving."
            )
            self.category_id_var.set("")
            self.condition_frame.grid_remove()
            self.category_frame.grid()
            return

        group = self.state_model.next_condition()
        if group is not None:
            self.mode = "condition"
            self.current_group = group
            self.heading_var.set(group.source_category or "Uncategorized source listings")
            self.detail_var.set(
                f"Applies to {group.listing_count} listing(s) whose source condition is "
                f"'{group.source_condition or 'blank'}'. Choose the strict eBay condition "
                "that accurately describes all items in this group."
            )
            self.condition_var.set("")
            self.category_frame.grid_remove()
            self.condition_frame.grid(row=2, column=0, sticky="ew")
            return

        self.current_group = None
        self.heading_var.set("Bulk category and condition review is complete")
        self.detail_var.set(
            "Run a fresh readiness scan to see any listing-specific source, policy, "
            "image, or required-aspect blockers."
        )
        self.category_frame.grid_remove()
        self.condition_frame.grid_remove()
        self.save_button.configure(state="disabled")

    def _save_current(self) -> None:
        group = self.current_group
        if group is None:
            return
        try:
            if self.mode == "category":
                value = self.category_id_var.get().strip()
                self.category_store.set_rule(group.source_category, value)
            else:
                value = self.condition_var.get().strip()
                self.condition_store.set_rule(
                    group.source_category,
                    group.source_condition,
                    value,
                )
        except (OSError, ValueError) as error:
            messagebox.showerror("Rule Not Saved", str(error), parent=self)
            return
        try:
            self.report = EbayReadinessScanner().scan()
        except Exception as error:
            messagebox.showerror("Readiness Rescan Failed", str(error), parent=self)
            return
        self.state_model = EbayReadinessWizardState(self.report)
        self.on_saved(self.report)
        self._show_next()
