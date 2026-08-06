from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from inventory.inventory_item import InventoryItem
from inventory.inventory_manager import InventoryManager
from inventory.thumbnail_cache import ThumbnailCache
from dashboard.listing_editor import ListingEditor
from dashboard.upload_dialog import UploadDialog


class InventoryPanel(ttk.LabelFrame):
    def __init__(
        self,
        parent: tk.Misc,
    ) -> None:
        super().__init__(
            parent,
            text="Inventory Manager",
            padding=10,
        )

        self.manager = InventoryManager()
        self.thumbnail_cache = ThumbnailCache(
            size=(180, 180)
        )

        self.items: list[InventoryItem] = []
        self.filtered_items: list[InventoryItem] = []

        self.search_var = tk.StringVar()
        self.count_var = tk.StringVar(
            value="0 listings"
        )
        self.health_filter_var = tk.StringVar(
            value="All"
        )

        self.title_var = tk.StringVar(
            value="Select a listing"
        )
        self.brand_var = tk.StringVar(
            value="—"
        )
        self.price_var = tk.StringVar(
            value="—"
        )
        self.size_var = tk.StringVar(
            value="—"
        )
        self.category_var = tk.StringVar(
            value="—"
        )
        self.status_var = tk.StringVar(
            value="—"
        )
        self.health_var = tk.StringVar(
            value="—"
        )

        self.preview_photo = None
        self.selected_item: InventoryItem | None = None
        self.upload_dialog: UploadDialog | None = None

        self._build_interface()
        self.refresh()

    def _build_interface(self) -> None:
        self.columnconfigure(
            0,
            weight=1,
        )
        self.rowconfigure(
            1,
            weight=1,
        )

        toolbar = ttk.Frame(self)
        toolbar.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )

        toolbar.columnconfigure(
            1,
            weight=1,
        )

        ttk.Label(
            toolbar,
            text="Search:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
        )

        search_entry = ttk.Entry(
            toolbar,
            textvariable=self.search_var,
        )
        search_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, 8),
        )

        self.search_var.trace_add(
            "write",
            self._on_search_changed,
        )

        ttk.Label(
            toolbar,
            text="Health:",
        ).grid(
            row=0,
            column=2,
            sticky="e",
            padx=(8, 8),
        )

        self.health_filter = ttk.Combobox(
            toolbar,
            textvariable=self.health_filter_var,
            values=(
                "All",
                "Ready",
                "Needs Attention",
                "Broken",
            ),
            state="readonly",
            width=18,
        )
        self.health_filter.grid(
            row=0,
            column=3,
            sticky="w",
            padx=(0, 8),
        )
        self.health_filter.bind(
            "<<ComboboxSelected>>",
            self._on_health_filter_changed,
        )

        ttk.Button(
            toolbar,
            text="Refresh",
            command=self.refresh,
        ).grid(
            row=0,
            column=4,
            padx=(0, 8),
        )

        ttk.Label(
            toolbar,
            textvariable=self.count_var,
        ).grid(
            row=0,
            column=5,
            sticky="e",
        )

        content = ttk.Panedwindow(
            self,
            orient="horizontal",
        )
        content.grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        list_frame = ttk.Frame(
            content,
            padding=(0, 0, 8, 0),
        )

        detail_frame = ttk.Frame(
            content,
            padding=(8, 0, 0, 0),
        )

        content.add(
            list_frame,
            weight=3,
        )
        content.add(
            detail_frame,
            weight=2,
        )

        list_frame.columnconfigure(
            0,
            weight=1,
        )
        list_frame.rowconfigure(
            0,
            weight=1,
        )

        columns = (
            "health",
            "title",
            "brand",
            "price",
            "size",
            "status",
        )

        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        self.tree.heading(
            "health",
            text="Health",
        )
        self.tree.heading(
            "title",
            text="Title",
        )
        self.tree.heading(
            "brand",
            text="Brand",
        )
        self.tree.heading(
            "price",
            text="Price",
        )
        self.tree.heading(
            "size",
            text="Size",
        )
        self.tree.heading(
            "status",
            text="Status",
        )

        self.tree.column(
            "health",
            width=125,
            anchor="center",
        )
        self.tree.column(
            "title",
            width=300,
            anchor="w",
        )
        self.tree.column(
            "brand",
            width=120,
            anchor="w",
        )
        self.tree.column(
            "price",
            width=70,
            anchor="center",
        )
        self.tree.column(
            "size",
            width=90,
            anchor="center",
        )
        self.tree.column(
            "status",
            width=90,
            anchor="center",
        )

        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        tree_scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        tree_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.tree.configure(
            yscrollcommand=tree_scrollbar.set,
        )

        self.tree.bind(
            "<<TreeviewSelect>>",
            self._on_item_selected,
        )

        self.tree.bind(
            "<ButtonRelease-1>",
            self._on_tree_click,
        )

        self.tree.bind(
            "<Double-1>",
            self._on_item_double_click,
        )

        detail_frame.columnconfigure(
            0,
            weight=1,
        )

        self.image_label = ttk.Label(
            detail_frame,
            text="No image",
            anchor="center",
        )
        self.image_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )

        ttk.Label(
            detail_frame,
            textvariable=self.title_var,
            font=("Segoe UI", 11, "bold"),
            wraplength=360,
            justify="left",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(0, 12),
        )

        details = ttk.Frame(
            detail_frame
        )
        details.grid(
            row=2,
            column=0,
            sticky="ew",
        )

        details.columnconfigure(
            1,
            weight=1,
        )

        self._add_detail_row(
            details,
            0,
            "Brand:",
            self.brand_var,
        )
        self._add_detail_row(
            details,
            1,
            "Price:",
            self.price_var,
        )
        self._add_detail_row(
            details,
            2,
            "Size:",
            self.size_var,
        )
        self._add_detail_row(
            details,
            3,
            "Category:",
            self.category_var,
        )
        self._add_detail_row(
            details,
            4,
            "Health:",
            self.health_var,
        )
        self._add_detail_row(
            details,
            5,
            "Status:",
            self.status_var,
        )

        actions = ttk.Frame(
            detail_frame
        )
        actions.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(16, 0),
        )

        self.open_folder_button = ttk.Button(
            actions,
            text="Open Folder",
            command=self.open_selected_folder,
            state="disabled",
        )
        self.open_folder_button.pack(
            side="left",
        )

        self.open_json_button = ttk.Button(
            actions,
            text="Open JSON",
            command=self.open_selected_json,
            state="disabled",
        )
        self.open_json_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.edit_button = ttk.Button(
            actions,
            text="Edit Listing",
            command=self.edit_selected_listing,
            state="disabled",
        )
        self.edit_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.dry_run_button = ttk.Button(
            actions,
            text="Dry Run Selected",
            command=self.dry_run_selected_listing,
            state="disabled",
        )
        self.dry_run_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.upload_button = ttk.Button(
            actions,
            text="Upload This Listing",
            command=self.upload_selected_listing,
            state="disabled",
        )
        self.upload_button.pack(
            side="left",
            padx=(8, 0),
        )
    def _add_detail_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(
            parent,
            text=label,
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=row,
            column=0,
            sticky="nw",
            padx=(0, 8),
            pady=3,
        )

        ttk.Label(
            parent,
            textvariable=variable,
            wraplength=280,
            justify="left",
        ).grid(
            row=row,
            column=1,
            sticky="w",
            pady=3,
        )

    def refresh(self) -> None:
        self.items = self.manager.load_items()
        self._apply_filter()

    def _on_search_changed(
        self,
        *_args,
    ) -> None:
        self._apply_filter()

    def _on_health_filter_changed(
        self,
        _event=None,
    ) -> None:
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search_var.get().strip().lower()
        health_filter = self.health_filter_var.get().strip()

        filtered: list[InventoryItem] = []

        for item in self.items:
            if (
                health_filter != "All"
                and item.health_status != health_filter
            ):
                continue

            searchable_text = " ".join(
                (
                    item.title,
                    item.brand,
                    item.price,
                    item.size,
                    item.category,
                    item.listing_id,
                    item.health_status,
                )
            ).lower()

            if query and query not in searchable_text:
                continue

            filtered.append(item)

        self.filtered_items = filtered
        self._populate_tree()

    def _populate_tree(self) -> None:
        for item_id in self.tree.get_children():
            self.tree.delete(
                item_id
            )

        for index, item in enumerate(
            self.filtered_items
        ):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    self._health_text(item),
                    item.title,
                    item.brand,
                    item.price,
                    item.size,
                    self._status_text(item),
                ),
            )

        count = len(
            self.filtered_items
        )

        self.count_var.set(
            f"{count} listing"
            if count == 1
            else f"{count} listings"
        )

        self._clear_preview()

    def _health_text(
        self,
        item: InventoryItem,
    ) -> str:
        if item.health_status == "Ready":
            return "Ready"

        if item.health_status == "Needs Attention":
            return "Needs Attention"

        if item.health_status == "Broken":
            return "Broken"

        return item.health_status or "Unknown"

    def _status_text(
        self,
        item: InventoryItem,
    ) -> str:
        if item.failed:
            return "Failed"

        if item.duplicate:
            return "Duplicate"

        if item.uploaded:
            return "Uploaded"

        return "Ready"

    def _on_tree_click(
        self,
        event,
    ) -> None:
        item_id = self.tree.identify_row(
            event.y
        )

        if not item_id:
            return

        self.tree.selection_set(
            item_id
        )
        self.tree.focus(
            item_id
        )

        self._show_selected_item(
            item_id
        )

    def _on_item_selected(
        self,
        _event=None,
    ) -> None:
        selection = self.tree.selection()

        item_id = (
            selection[0]
            if selection
            else self.tree.focus()
        )

        if not item_id:
            return

        self._show_selected_item(
            item_id
        )

    def _show_selected_item(
        self,
        item_id: str,
    ) -> None:
        try:
            index = int(
                item_id
            )
            item = self.filtered_items[
                index
            ]
        except (
            ValueError,
            IndexError,
        ):
            return

        self._show_item(
            item
        )

    def _show_item(
        self,
        item: InventoryItem,
    ) -> None:
        self.selected_item = item
        self.title_var.set(
            item.title or "Untitled listing"
        )
        self.brand_var.set(
            item.brand or "—"
        )
        self.price_var.set(
            item.price or "—"
        )
        self.size_var.set(
            item.size or "—"
        )
        self.category_var.set(
            item.category or "—"
        )
        self.health_var.set(
            item.health_status
        )
        self.status_var.set(
            self._status_text(item)
        )

        photo = self.thumbnail_cache.get(
            item.image_path
        )

        self.preview_photo = photo

        if photo is None:
            self.image_label.configure(
                image="",
                text="No image",
            )
        else:
            self.image_label.configure(
                image=photo,
                text="",
            )

        self.open_folder_button.configure(state="normal")
        self.open_json_button.configure(state="normal")
        self.edit_button.configure(state="normal")
        upload_state = "normal" if item.ready_for_upload else "disabled"
        self.dry_run_button.configure(state=upload_state)
        self.upload_button.configure(state=upload_state)

    def _clear_preview(self) -> None:
        self.selected_item = None
        self.preview_photo = None

        self.image_label.configure(
            image="",
            text="No image",
        )

        self.title_var.set(
            "Select a listing"
        )
        self.brand_var.set("—")
        self.price_var.set("—")
        self.size_var.set("—")
        self.category_var.set("—")
        self.health_var.set("—")
        self.status_var.set("—")

    def _set_action_state(
        self,
        *,
        enabled: bool,
    ) -> None:
        state = "normal" if enabled else "disabled"

        self.open_folder_button.configure(
            state=state
        )
        self.open_json_button.configure(
            state=state
        )
        self.edit_button.configure(
            state=state
        )
        self.dry_run_button.configure(
            state=state
        )
        self.upload_button.configure(
            state=state
        )

    def open_selected_folder(self) -> None:
        item = self.selected_item

        if item is None:
            return

        folder = item.listing_path.parent

        if not folder.exists():
            messagebox.showerror(
                "Folder Not Found",
                f"Could not find:\n{folder}",
            )
            return

        self._open_path(folder)

    def open_selected_json(self) -> None:
        item = self.selected_item

        if item is None:
            return

        json_file = item.listing_path

        if not json_file.exists():
            messagebox.showerror(
                "JSON Not Found",
                f"Could not find:\n{json_file}",
            )
            return

        self._open_path(json_file)

    def _on_item_double_click(
        self,
        event,
    ) -> None:
        item_id = self.tree.identify_row(
            event.y
        )

        if not item_id:
            return

        self.tree.selection_set(
            item_id
        )
        self.tree.focus(
            item_id
        )

        self._show_selected_item(
            item_id
        )

        self.edit_selected_listing()
        
    def edit_selected_listing(self) -> None:
        item = self.selected_item

        if item is None:
            return

        try:
            ListingEditor(
                self,
                item,
                on_saved=self.refresh,
            )
        except Exception as error:
            messagebox.showerror(
                "Editor Failed",
                str(error),
            )


    def dry_run_selected_listing(self) -> None:
        self._open_upload_dialog(
            mode="dry_run"
        )

    def upload_selected_listing(self) -> None:
        self._open_upload_dialog(
            mode="publish"
        )

    def _open_upload_dialog(
        self,
        *,
        mode: str,
    ) -> None:
        item = self.selected_item

        if item is None:
            return

        existing_dialog = self.upload_dialog

        if (
            existing_dialog is not None
            and existing_dialog.winfo_exists()
        ):
            existing_dialog.lift()
            existing_dialog.focus_force()
            return

        try:
            dialog = UploadDialog(
                self,
                item,
                on_finished=self._on_upload_finished,
            )
        except Exception as error:
            messagebox.showerror(
                "Upload Dialog Failed",
                str(error),
            )
            return

        self.upload_dialog = dialog
        dialog.mode_var.set(
            mode
        )

        dialog.bind(
            "<Destroy>",
            self._on_upload_dialog_destroyed,
            add="+",
        )

    def _on_upload_finished(self) -> None:
        current_listing_id = (
            self.selected_item.listing_id
            if self.selected_item is not None
            else None
        )

        self.items = self.manager.load_items()
        self._apply_filter()

        if current_listing_id is None:
            return

        for index, item in enumerate(
            self.filtered_items
        ):
            if item.listing_id != current_listing_id:
                continue

            tree_id = str(index)

            if self.tree.exists(
                tree_id
            ):
                self.tree.selection_set(
                    tree_id
                )
                self.tree.focus(
                    tree_id
                )
                self.tree.see(
                    tree_id
                )
                self._show_selected_item(
                    tree_id
                )

            break

    def _on_upload_dialog_destroyed(
        self,
        event,
    ) -> None:
        dialog = self.upload_dialog

        if dialog is None:
            return

        if event.widget is dialog:
            self.upload_dialog = None

    def _open_path(
        self,
        path: Path,
    ) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(
                    ["open", str(path)]
                )
            else:
                subprocess.Popen(
                    ["xdg-open", str(path)]
                )
        except Exception as error:
            messagebox.showerror(
                "Could Not Open",
                str(error),
            )

