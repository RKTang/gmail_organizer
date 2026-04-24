from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .config import load_json, save_json
from .engine import PlanStats, PlannedEmailAction, apply_plan, build_plan, build_relabel_plan, undo_last_run
from .gmail_client import build_service, list_user_labels


class GmailOrganizerApp(tk.Tk):
    def __init__(self, rules_path: Path, history_path: Path, credentials_path: Path, token_path: Path) -> None:
        super().__init__()
        self.title("Gmail Organizer")
        self.geometry("1120x760")
        self.minsize(1000, 680)

        self.rules_path = rules_path
        self.history_path = history_path
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.is_busy = False

        self.auto_archive_var = tk.BooleanVar(value=False)
        self.theme_var = tk.StringVar(value="default")
        self.font_size_var = tk.IntVar(value=10)
        self.query_var = tk.StringVar(value="")
        self.max_results_var = tk.IntVar(value=200)
        self.default_label_var = tk.StringVar(value="To-Review")
        self.source_label_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Idle")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.processed_var = tk.StringVar(value="Processed: 0")
        self.skipped_var = tk.StringVar(value="Skipped: 0")
        self.labeled_var = tk.StringVar(value="Labeled: 0")

        self.query_options: list[str] = []
        self.label_options: list[str] = []
        self.preview_plan: list[PlannedEmailAction] = []
        self.plan_by_id: dict[str, PlannedEmailAction] = {}
        self.selected_ids: set[str] = set()

        self.style = ttk.Style(self)
        self._build_widgets()
        self.refresh_settings_view()
        self.after(150, self.auto_connect_if_possible)

    def _build_widgets(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        self.style.configure("Primary.TButton", padding=(12, 6))
        self.style.configure("Secondary.TButton", padding=(10, 6))
        self.style.configure("Apply.TButton", padding=(14, 6))
        self.style.map("Apply.TButton", foreground=[("!disabled", "#FFFFFF")], background=[("!disabled", "#2563EB")])

        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x", pady=(0, 10))

        left_actions = ttk.Frame(toolbar)
        left_actions.pack(side="left")
        self.connect_btn = ttk.Button(left_actions, text="Connect Gmail", style="Primary.TButton", command=self.connect)
        self.connect_btn.pack(side="left")
        self.save_settings_btn = ttk.Button(left_actions, text="Save Settings", style="Secondary.TButton", command=self.save_settings)
        self.save_settings_btn.pack(side="left", padx=6)
        self.refresh_labels_btn = ttk.Button(left_actions, text="Refresh Labels", style="Secondary.TButton", command=self.refresh_labels)
        self.refresh_labels_btn.pack(side="left")

        right_actions = ttk.Frame(toolbar)
        right_actions.pack(side="right")
        self.clear_log_btn = ttk.Button(right_actions, text="Clear", style="Secondary.TButton", command=self.clear_activity)
        self.clear_log_btn.pack(side="right")
        self.undo_btn = ttk.Button(right_actions, text="Undo", style="Secondary.TButton", command=self.undo)
        self.undo_btn.pack(side="right", padx=6)
        self.apply_btn = ttk.Button(right_actions, text="Apply", style="Apply.TButton", command=self.apply)
        self.apply_btn.pack(side="right")
        self.preview_btn = ttk.Button(right_actions, text="Preview", style="Primary.TButton", command=self.preview)
        self.preview_btn.pack(side="right", padx=6)

        stats_row = ttk.Frame(root)
        stats_row.pack(fill="x", pady=(0, 10))
        ttk.Label(stats_row, textvariable=self.status_var).pack(side="left")
        ttk.Separator(stats_row, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(stats_row, textvariable=self.processed_var).pack(side="left")
        ttk.Label(stats_row, text="  ").pack(side="left")
        ttk.Label(stats_row, textvariable=self.skipped_var).pack(side="left")
        ttk.Label(stats_row, text="  ").pack(side="left")
        ttk.Label(stats_row, textvariable=self.labeled_var).pack(side="left")
        ttk.Checkbutton(
            stats_row,
            text="Auto archive",
            variable=self.auto_archive_var,
            command=self.toggle_auto_archive,
        ).pack(side="right")

        settings_title = ttk.Label(root, text="Settings", font=("Segoe UI", 10, "bold"))
        settings_title.pack(anchor="w")
        settings = ttk.Frame(root)
        settings.pack(fill="x", pady=(4, 14))

        left = ttk.Frame(settings)
        left.pack(side="left", fill="x", expand=True, padx=(0, 12))
        right = ttk.Frame(settings)
        right.pack(side="left", fill="x", expand=True)

        ttk.Label(left, text="Scope").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(left, text="Query").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.query_picker = ttk.Combobox(
            left,
            textvariable=self.query_var,
            state="normal",
            postcommand=self._refresh_query_picker_values,
        )
        self.query_picker.grid(row=1, column=1, sticky="ew")
        self.query_picker.bind("<Button-1>", self._open_query_dropdown, add="+")
        ttk.Label(left, text="Max Results").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        ttk.Spinbox(left, from_=25, to=1000, textvariable=self.max_results_var, width=10).grid(
            row=2, column=1, sticky="w", pady=(6, 0)
        )
        left.columnconfigure(1, weight=1)

        ttk.Label(right, text="Styling").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(right, text="Theme").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.theme_picker = ttk.Combobox(right, textvariable=self.theme_var, state="readonly", width=18)
        self.theme_picker["values"] = sorted(self.style.theme_names())
        self.theme_picker.grid(row=1, column=1, sticky="w")
        self.theme_picker.bind("<<ComboboxSelected>>", self.on_theme_changed)
        ttk.Label(right, text="Font Size").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        ttk.Spinbox(right, from_=9, to=18, textvariable=self.font_size_var, width=10, command=self.apply_visual_prefs).grid(
            row=2, column=1, sticky="w", pady=(6, 0)
        )
        ttk.Label(right, text="Fallback Label").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        ttk.Entry(right, textvariable=self.default_label_var, width=18).grid(row=3, column=1, sticky="w", pady=(6, 0))

        ttk.Separator(root, orient="horizontal").pack(fill="x", pady=(0, 10))

        relabel = ttk.Frame(root)
        relabel.pack(fill="x", pady=(0, 10))
        ttk.Label(relabel, text="Relabel Source").pack(side="left")
        self.source_label_picker = ttk.Combobox(
            relabel,
            textvariable=self.source_label_var,
            state="readonly",
            width=30,
            postcommand=self.refresh_labels,
        )
        self.source_label_picker.pack(side="left", padx=8)
        self.source_label_picker.bind("<Button-1>", self._open_source_dropdown, add="+")
        self.preview_relabel_btn = ttk.Button(relabel, text="Preview Relabel", command=self.preview_relabel)
        self.preview_relabel_btn.pack(side="left")
        self.apply_relabel_btn = ttk.Button(relabel, text="Apply Relabel", command=self.apply_relabel)
        self.apply_relabel_btn.pack(side="left", padx=6)

        ttk.Label(root, text="Activity", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        table_wrap = ttk.Frame(root)
        table_wrap.pack(fill="both", expand=True)

        columns = ("selected", "label", "subject", "sender")
        self.activity_table = ttk.Treeview(table_wrap, columns=columns, show="headings", selectmode="none")
        self.activity_table.heading("selected", text="Use")
        self.activity_table.heading("label", text="Label")
        self.activity_table.heading("subject", text="Subject")
        self.activity_table.heading("sender", text="Sender")
        self.activity_table.column("selected", width=56, anchor="center", stretch=False)
        self.activity_table.column("label", width=140, anchor="w", stretch=False)
        self.activity_table.column("subject", width=520, anchor="w")
        self.activity_table.column("sender", width=320, anchor="w")
        self.activity_table.tag_configure("odd", background="#FFFFFF")
        self.activity_table.tag_configure("even", background="#F8FAFC")
        self.activity_table.tag_configure("newsletter", foreground="#166534")
        self.activity_table.tag_configure("finance", foreground="#1D4ED8")
        self.activity_table.tag_configure("jobs", foreground="#7C2D12")
        self.activity_table.tag_configure("school", foreground="#4C1D95")

        y_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.activity_table.yview)
        x_scroll = ttk.Scrollbar(table_wrap, orient="horizontal", command=self.activity_table.xview)
        self.activity_table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.activity_table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)
        self.activity_table.bind("<Button-1>", self._on_table_click)

        footer = ttk.Frame(root)
        footer.pack(fill="x", pady=(8, 0))
        self.progress_bar = ttk.Progressbar(footer, orient="horizontal", mode="determinate", variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x")

    def _load_config(self) -> dict:
        return load_json(self.rules_path)

    def _save_config(self, config: dict) -> None:
        save_json(self.rules_path, config)

    def _default_query_presets(self) -> list[str]:
        return [
            "in:inbox newer_than:30d",
            "in:inbox newer_than:60d",
            "from:alerts",
            "label:Finance",
            "label:To-Review",
        ]

    def _sync_query_dropdown(self, cfg: dict) -> None:
        configured = [str(item).strip() for item in cfg.get("query_presets", []) if str(item).strip()]
        merged: list[str] = []
        for query in configured + self._default_query_presets():
            if query not in merged:
                merged.append(query)
        current = self.query_var.get().strip()
        if current and current not in merged:
            merged.insert(0, current)
        self.query_options = merged
        self.query_picker["values"] = self.query_options

    def _refresh_query_picker_values(self) -> None:
        cfg = self._load_config()
        self._sync_query_dropdown(cfg)

    def _open_query_dropdown(self, _event=None):
        self.after(1, lambda: self.query_picker.event_generate("<Down>"))

    def _open_source_dropdown(self, _event=None):
        self.after(1, lambda: self.source_label_picker.event_generate("<Down>"))

    def apply_visual_prefs(self) -> None:
        theme = self.theme_var.get().strip()
        if theme in set(self.style.theme_names()):
            self.style.theme_use(theme)
        size = max(9, min(18, int(self.font_size_var.get())))
        self.style.configure("Treeview", font=("Segoe UI", size), rowheight=size + 14)
        self.style.configure("Treeview.Heading", font=("Segoe UI", max(9, size - 1), "bold"))

    def on_theme_changed(self, _event=None) -> None:
        self.apply_visual_prefs()

    def _set_stats(self, stats: PlanStats | None = None) -> None:
        if stats is None:
            self.processed_var.set("Processed: 0")
            self.skipped_var.set("Skipped: 0")
            self.labeled_var.set("Labeled: 0")
            return
        self.processed_var.set(f"Processed: {stats.processed}")
        self.skipped_var.set(f"Skipped: {stats.skipped}")
        self.labeled_var.set(f"Labeled: {stats.labeled}")

    def _progress_update(self, current: int, total: int, status: str) -> None:
        def update_ui() -> None:
            self.status_var.set(f"{status}: {current}/{total}" if total else status)
            self.progress_var.set((current / total) * 100.0 if total else 0.0)

        self.after(0, update_ui)

    def _progress_reset(self) -> None:
        self.progress_var.set(0.0)
        self.status_var.set("Idle")

    def _run_background(self, work, on_success) -> None:
        def runner() -> None:
            try:
                result = work()
                self.after(0, lambda: on_success(result))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._handle_background_error(exc))

        threading.Thread(target=runner, daemon=True).start()

    def _handle_background_error(self, exc: Exception) -> None:
        self.set_busy(False)
        self.status_var.set("Error")
        messagebox.showerror("Gmail Organizer", str(exc))

    def set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        state = "disabled" if busy else "normal"
        for widget in [
            self.connect_btn,
            self.save_settings_btn,
            self.refresh_labels_btn,
            self.preview_btn,
            self.apply_btn,
            self.undo_btn,
            self.preview_relabel_btn,
            self.apply_relabel_btn,
        ]:
            widget.configure(state=state)
        self.clear_log_btn.configure(state="normal")

    def clear_activity(self) -> None:
        self.preview_plan = []
        self.plan_by_id = {}
        self.selected_ids.clear()
        self._clear_table()
        self._set_stats(None)
        self.status_var.set("Cleared")

    def _clear_table(self) -> None:
        for item in self.activity_table.get_children():
            self.activity_table.delete(item)

    def _fill_table(self, plan: list[PlannedEmailAction]) -> None:
        self._clear_table()
        self.preview_plan = plan
        self.plan_by_id = {item.message_id: item for item in plan}
        self.selected_ids = {item.message_id for item in plan}
        for index, item in enumerate(plan):
            archive = " + archive" if item.remove_label_ids else ""
            label = (item.add_label_name or "(archive)") + archive
            subject = item.subject.strip() or "(No subject)"
            sender = item.sender.strip() or "(Unknown sender)"
            row_tag = "even" if index % 2 == 0 else "odd"
            lowered = (item.add_label_name or "").lower()
            color_tag = ""
            if "newsletter" in lowered:
                color_tag = "newsletter"
            elif "finance" in lowered:
                color_tag = "finance"
            elif "job" in lowered:
                color_tag = "jobs"
            elif "school" in lowered:
                color_tag = "school"
            tags = (row_tag, color_tag) if color_tag else (row_tag,)
            self.activity_table.insert(
                "",
                "end",
                iid=item.message_id,
                values=("☑", label, subject, sender),
                tags=tags,
            )

    def _on_table_click(self, event) -> None:
        if self.is_busy or not self.preview_plan:
            return
        row_id = self.activity_table.identify_row(event.y)
        col_id = self.activity_table.identify_column(event.x)
        if not row_id or col_id != "#1":
            return
        if row_id in self.selected_ids:
            self.selected_ids.remove(row_id)
            self.activity_table.set(row_id, "selected", "☐")
        else:
            self.selected_ids.add(row_id)
            self.activity_table.set(row_id, "selected", "☑")

    def _selected_plan(self) -> list[PlannedEmailAction]:
        return [self.plan_by_id[mid] for mid in self.selected_ids if mid in self.plan_by_id]

    def refresh_settings_view(self) -> None:
        cfg = self._load_config()
        self.auto_archive_var.set(bool(cfg.get("auto_archive", False)))
        self.query_var.set(str(cfg.get("query", "in:inbox")))
        self._sync_query_dropdown(cfg)
        self.max_results_var.set(int(cfg.get("max_results", 200)))
        self.default_label_var.set(str(cfg.get("default_label", "To-Review")))
        ui_cfg = cfg.get("ui", {})
        self.theme_var.set(str(ui_cfg.get("theme", self.style.theme_use())))
        self.font_size_var.set(int(ui_cfg.get("font_size", 10)))
        self.apply_visual_prefs()

    def save_settings(self) -> None:
        cfg = self._load_config()
        query = self.query_var.get().strip() or "in:inbox"
        cfg["query"] = query
        presets: list[str] = []
        for item in [query] + self.query_options:
            value = str(item).strip()
            if value and value not in presets:
                presets.append(value)
        cfg["query_presets"] = presets[:20]
        cfg["max_results"] = max(25, min(1000, int(self.max_results_var.get())))
        cfg["default_label"] = self.default_label_var.get().strip() or "To-Review"
        cfg["auto_archive"] = bool(self.auto_archive_var.get())
        cfg["ui"] = {"theme": self.theme_var.get(), "font_size": int(self.font_size_var.get()), "compact": False}
        self._save_config(cfg)
        self.refresh_settings_view()
        self.status_var.set("Settings saved")

    def toggle_auto_archive(self) -> None:
        cfg = self._load_config()
        cfg["auto_archive"] = bool(self.auto_archive_var.get())
        self._save_config(cfg)

    def connect(self) -> None:
        if self.is_busy:
            return
        if not self.credentials_path.exists():
            messagebox.showerror("Gmail Organizer", f"Missing OAuth credentials file at:\n{self.credentials_path}")
            return
        self.set_busy(True)
        self.status_var.set("Connecting...")
        self._run_background(
            work=lambda: build_service(self.credentials_path, self.token_path),
            on_success=lambda service: self._on_connect_done(service, notify=True),
        )

    def auto_connect_if_possible(self) -> None:
        if self.service is not None or self.is_busy:
            return
        if not self.credentials_path.exists() or not self.token_path.exists():
            return
        self.set_busy(True)
        self.status_var.set("Auto-connecting...")
        self._run_background(
            work=lambda: build_service(self.credentials_path, self.token_path),
            on_success=lambda service: self._on_connect_done(service, notify=False),
        )

    def _on_connect_done(self, service, notify: bool = True) -> None:
        self.service = service
        self.refresh_labels()
        self.set_busy(False)
        self.status_var.set("Connected")
        if notify:
            messagebox.showinfo("Gmail Organizer", "Connected successfully.")

    def refresh_labels(self) -> None:
        if self.service is None:
            return
        labels = sorted(list_user_labels(self.service).keys())
        self.label_options = labels
        self.source_label_picker["values"] = labels
        if labels and self.source_label_var.get() not in labels:
            self.source_label_var.set(labels[0])
        return None

    def _ensure_connected(self) -> bool:
        if self.service is not None:
            return True
        messagebox.showwarning("Gmail Organizer", "Please connect Gmail first.")
        return False

    def preview(self) -> None:
        if self.is_busy or not self._ensure_connected():
            return
        self.set_busy(True)
        self._progress_reset()
        self._run_background(
            work=lambda: build_plan(self.service, self._load_config(), on_progress=self._progress_update),
            on_success=self._on_preview_done,
        )

    def _on_preview_done(self, result: tuple[list[PlannedEmailAction], PlanStats]) -> None:
        plan, stats = result
        self._set_stats(stats)
        self._fill_table(plan)
        self.status_var.set("Preview complete")
        self.set_busy(False)

    def apply(self) -> None:
        if self.is_busy or not self._ensure_connected():
            return
        selected_plan = self._selected_plan()
        if not selected_plan:
            messagebox.showinfo("Gmail Organizer", "Nothing selected to apply.")
            return
        if not messagebox.askyesno("Confirm Apply", f"Apply {len(selected_plan)} selected changes?"):
            return
        self.set_busy(True)
        self._progress_reset()
        self._run_background(
            work=lambda: apply_plan(self.service, selected_plan, self.history_path, on_progress=self._progress_update),
            on_success=self._on_apply_done,
        )

    def _on_apply_done(self, changed: int) -> None:
        self.status_var.set("Apply complete")
        self.set_busy(False)
        messagebox.showinfo("Gmail Organizer", f"Updated {changed} message(s).")

    def preview_relabel(self) -> None:
        if self.is_busy or not self._ensure_connected():
            return
        source_label = self.source_label_var.get().strip()
        if not source_label:
            messagebox.showwarning("Gmail Organizer", "Pick a source label first.")
            return
        self.set_busy(True)
        self._progress_reset()
        self._run_background(
            work=lambda: build_relabel_plan(
                self.service, self._load_config(), source_label, on_progress=self._progress_update
            ),
            on_success=self._on_preview_done,
        )

    def apply_relabel(self) -> None:
        self.apply()

    def undo(self) -> None:
        if self.is_busy or not self._ensure_connected():
            return
        if not messagebox.askyesno("Confirm Undo", "Undo the most recent run?"):
            return
        self.set_busy(True)
        self._run_background(
            work=lambda: undo_last_run(self.service, self.history_path),
            on_success=self._on_undo_done,
        )

    def _on_undo_done(self, undone: int) -> None:
        self.set_busy(False)
        self.status_var.set("Undo complete")
        messagebox.showinfo("Gmail Organizer", f"Undo completed for {undone} message(s).")

