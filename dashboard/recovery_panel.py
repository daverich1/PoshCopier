from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from inventory.recovery_manager import (
    RecoveryItem,
    RecoveryManager,
)


class RecoveryPanel(ttk.LabelFrame):
    def __init__(
        self,
        parent: tk.Misc,
    ) -> None:
        super().__init__(
            parent,
            text="Recovery Center",
            padding=10,
        )

        self.manager = RecoveryManager()
        self.items: list[RecoveryItem] = []
        self.selected_item: RecoveryItem | None = None

        self.count_var = tk.StringVar(
            value="0 broken folders"
        )
        self.folder_var = tk.StringVar(
            value="Select a broken folder"
        )
        self.problem_var = tk.StringVar(
            value="—"
        )
        self.images_var = tk.StringVar(
            value="—"
        )
        self.details_var = tk.StringVar(
            value="—"
        )
        self.delete_status_var = tk.StringVar(
            value="—"
        )

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

        toolbar = ttk.Frame(
            self
        )
        toolbar.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )

        toolbar.columnconfigure(
            0,
            weight=1,
        )

        ttk.Label(
            toolbar,
            textvariable=self.count_var,
            font=("Segoe UI", 10, "bold"),
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )

        ttk.Button(
            toolbar,
            text="Refresh",
            command=self.refresh,
        ).grid(
            row=0,
            column=1,
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
            "folder",
            "problem",
            "images",
            "safe_delete",
        )

        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        self.tree.heading(
            "folder",
            text="Folder",
        )
        self.tree.heading(
            "problem",
            text="Problem",
        )
        self.tree.heading(
            "images",
            text="Images",
        )
        self.tree.heading(
            "safe_delete",
            text="Safe Delete",
        )

        self.tree.column(
            "folder",
            width=260,
            anchor="w",
        )
        self.tree.column(
            "problem",
            width=190,
            anchor="w",
        )
        self.tree.column(
            "images",
            width=70,
            anchor="center",
        )
        self.tree.column(
            "safe_delete",
            width=90,
            anchor="center",
        )

        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.tree.configure(
            yscrollcommand=scrollbar.set,
        )

        self.tree.bind(
            "<<TreeviewSelect>>",
            self._on_selected,
        )

        detail_frame.columnconfigure(
            0,
            weight=1,
        )

        ttk.Label(
            detail_frame,
            textvariable=self.folder_var,
            font=("Segoe UI", 12, "bold"),
            wraplength=380,
            justify="left",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 12),
        )

        details = ttk.Frame(
            detail_frame
        )
        details.grid(
            row=1,
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
            "Problem:",
            self.problem_var,
        )
        self._add_detail_row(
            details,
            1,
            "Images:",
            self.images_var,
        )
        self._add_detail_row(
            details,
            2,
            "Delete:",
            self.delete_status_var,
        )
        self._add_detail_row(
            details,
            3,
            "Details:",
            self.details_var,
        )

        actions = ttk.Frame(
            detail_frame
        )
        actions.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(16, 0),
        )

        self.open_button = ttk.Button(
            actions,
            text="Open Folder",
            command=self.open_selected_folder,
            state="disabled",
        )
        self.open_button.pack(
            side="left",
        )

        self.delete_button = ttk.Button(
            actions,
            text="Delete Folder",
            command=self.delete_selected_folder,
            state="disabled",
        )
        self.delete_button.pack(
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
            pady=4,
        )

        ttk.Label(
            parent,
            textvariable=variable,
            wraplength=300,
            justify="left",
        ).grid(
            row=row,
            column=1,
            sticky="w",
            pady=4,
        )

    def refresh(self) -> None:
        self.items = self.manager.scan_broken_folders()

        for item_id in self.tree.get_children():
            self.tree.delete(
                item_id
            )

        for index, item in enumerate(
            self.items
        ):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item.folder_name,
                    item.problem,
                    item.image_count,
                    "Yes"
                    if item.can_delete
                    else "No",
                ),
            )

        count = len(
            self.items
        )

        self.count_var.set(
            f"{count} broken folder"
            if count == 1
            else f"{count} broken folders"
        )

        self._clear_selection()

    def _on_selected(
        self,
        _event=None,
    ) -> None:
        selection = self.tree.selection()

        if not selection:
            return

        try:
            index = int(
                selection[0]
            )
            item = self.items[
                index
            ]
        except (
            ValueError,
            IndexError,
        ):
            return

        self.selected_item = item

        self.folder_var.set(
            item.folder_name
        )
        self.problem_var.set(
            item.problem
        )
        self.images_var.set(
            str(
                item.image_count
            )
        )
        self.details_var.set(
            item.details or "—"
        )
        self.delete_status_var.set(
            "Safe to delete"
            if item.can_delete
            else "Contains files; review first"
        )

        self.open_button.configure(
            state="normal",
        )
        self.delete_button.configure(
            state=(
                "normal"
                if item.can_delete
                else "disabled"
            ),
        )

    def _clear_selection(self) -> None:
        self.selected_item = None

        self.folder_var.set(
            "Select a broken folder"
        )
        self.problem_var.set("—")
        self.images_var.set("—")
        self.details_var.set("—")
        self.delete_status_var.set("—")

        self.open_button.configure(
            state="disabled",
        )
        self.delete_button.configure(
            state="disabled",
        )

    def open_selected_folder(self) -> None:
        item = self.selected_item

        if item is None:
            return

        folder = item.folder_path

        if not folder.exists():
            messagebox.showerror(
                "Folder Not Found",
                f"Could not find:\n{folder}",
            )
            self.refresh()
            return

        self._open_path(
            folder
        )

    def delete_selected_folder(self) -> None:
        item = self.selected_item

        if item is None:
            return

        if not item.can_delete:
            messagebox.showwarning(
                "Delete Blocked",
                (
                    "This folder contains files that may be "
                    "important. Open it and review the contents "
                    "before deleting anything."
                ),
            )
            return

        confirmed = messagebox.askyesno(
            "Delete Broken Folder",
            (
                f"Delete this folder permanently?\n\n"
                f"{item.folder_path}"
            ),
        )

        if not confirmed:
            return

        try:
            self.manager.delete_folder(
                item
            )
        except Exception as error:
            messagebox.showerror(
                "Delete Failed",
                str(error),
            )
            return

        messagebox.showinfo(
            "Folder Deleted",
            "The broken folder was deleted.",
        )

        self.refresh()

    def _open_path(
        self,
        path: Path,
    ) -> None:
        try:
            if os.name == "nt":
                os.startfile(
                    str(path)
                )
            elif sys.platform == "darwin":
                subprocess.Popen(
                    [
                        "open",
                        str(path),
                    ]
                )
            else:
                subprocess.Popen(
                    [
                        "xdg-open",
                        str(path),
                    ]
                )
        except Exception as error:
            messagebox.showerror(
                "Could Not Open",
                str(error),
            )
