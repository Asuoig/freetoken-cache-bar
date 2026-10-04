# -*- coding: utf-8 -*-
"""FreeToken Cache Bar — floating always-on-top toolbar for cache presets.

A small, topmost Tk window that docks to the edge of the screen and lets you
switch between FreeToken cache presets (including user-defined Custom presets)
with one click, without touching the FreeToken Desktop UI.

Usage:
    python ft_cache_bar.pyw                 # run windowed, no console
    python ft_cache_bar.pyw --pin right     # dock to a screen edge
    python ft_cache_bar.pyw --host 127.0.0.1 --port 1919

Persists Custom presets to ~/.freetoken/cache-presets.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import ttk, messagebox

APP_TITLE = "FreeToken Cache Bar"
PRESETS_PATH = Path.home() / ".freetoken" / "cache-presets.json"

# Built-in presets (mirrors FreeToken Desktop's built-in trio).
# Values match the units FreeToken REST API uses:
#   - kv_tokens:   num_pages   (1 page = 1 token for KV in this build)
#   - swa_tokens:  num_swa_pages
#   - moe_slots:   moe_cache_size
BUILTIN_PRESETS = [
    {
        "name": "基础",
        "desc": "KV 8K · MoE 0 层",
        "kv_tokens": 8192,
        "swa_tokens": 1609,
        "moe_slots": 32,
        "builtin": True,
    },
    {
        "name": "Chat",
        "desc": "KV 120K · 长对话",
        "kv_tokens": 120000,
        "swa_tokens": 25000,
        "moe_slots": 200,
        "builtin": True,
    },
    {
        "name": "Agent",
        "desc": "KV 100K + MoE 2 层",
        "kv_tokens": 100000,
        "swa_tokens": 25000,
        "moe_slots": 254,
        "builtin": True,
    },
]


# ----------------------------- FreeToken REST client -----------------------------

class FreeTokenClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 1919, timeout: float = 6.0):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout

    def get(self, path: str) -> dict:
        req = urllib.request.Request(self.base + path, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def cache_status(self) -> dict:
        return self.get("/v1/cache/status")

    def cache_rebuild(self, kv_tokens: int, swa_tokens: int, moe_slots: int,
                      mode: str = "if_idle", timeout: float = 300.0) -> dict:
        return self.post("/v1/cache/rebuild", {
            "num_pages": int(kv_tokens),
            "num_swa_pages": int(swa_tokens),
            "moe_cache_size": int(moe_slots),
            "mode": mode,
            "timeout": timeout,
        })


# ----------------------------- Preset persistence -----------------------------

def load_custom_presets() -> list[dict]:
    if not PRESETS_PATH.exists():
        return []
    try:
        with PRESETS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        out = []
        for p in data:
            if not isinstance(p, dict):
                continue
            p.setdefault("builtin", False)
            p.setdefault("desc", "")
            for k in ("kv_tokens", "swa_tokens", "moe_slots"):
                p[k] = int(p.get(k, 0))
            p["name"] = str(p.get("name", "")).strip() or "Custom"
            out.append(p)
        return out
    except Exception:
        return []


def save_custom_presets(items: list[dict]) -> None:
    PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [{k: v for k, v in p.items() if k in {"name", "desc", "kv_tokens", "swa_tokens", "moe_slots"}} for p in items]
    with PRESETS_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ----------------------------- Main window -----------------------------

class CacheBar(tk.Tk):
    BG = "#0f1115"
    PANEL = "#161a22"
    FIELD = "#1d2230"
    BORDER = "#262c39"
    TEXT = "#e6e8ee"
    MUTED = "#9aa3b2"
    ACCENT = "#7c9cff"
    DANGER = "#ff7c7c"

    def __init__(self, client: FreeTokenClient, pin: str = "right"):
        super().__init__()
        self.client = client
        self.title(APP_TITLE)
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self.wm_overrideredirect(True)
        self.wm_attributes("-topmost", True)
        # On Windows, '-toolwindow' removes the entry from the taskbar/Alt-Tab.
        try:
            self.wm_attributes("-toolwindow", True)
        except tk.TclError:
            pass

        # Slim footprint.
        self.width = 290
        self.update_idletasks()
        self._pin_to(pin)

        self.collapsed = False
        self.custom_presets: list[dict] = load_custom_presets()
        self.preset_buttons: list[tk.Button] = []
        self._status_thread_stop = threading.Event()
        self._status_lock = threading.Lock()
        self._last_status: dict | None = None

        self._build_ui()
        self._refresh_preset_row()
        self._kick_status_loop()

        # Bindings
        self.bind("<Button-1>", self._start_drag)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<Double-Button-1>", lambda e: self._toggle_collapse())
        self.bind("<Escape>", lambda e: self.iconify() if False else self._toggle_collapse())

    # ---------- layout helpers ----------

    def _pin_to(self, edge: str) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        h = 420  # approximate; gets resized after layout
        if edge == "right":
            x = sw - self.width - 16
            y = (sh - h) // 2
        elif edge == "left":
            x = 16
            y = (sh - h) // 2
        elif edge == "top":
            x = (sw - self.width) // 2
            y = 16
        else:
            x = (sw - self.width) // 2
            y = sh - h - 60
        self.geometry(f"{self.width}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        # Header
        head = tk.Frame(self, bg=self.BG, height=28)
        head.pack(fill="x")
        tk.Label(head, text="FreeToken · Cache Bar", bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=10)
        tk.Button(head, text="—", bg=self.BG, fg=self.MUTED, relief="flat",
                  bd=0, command=self._toggle_collapse, width=3).pack(side="right", padx=2)
        tk.Button(head, text="⟳", bg=self.BG, fg=self.MUTED, relief="flat",
                  bd=0, command=self._refresh_status_sync, width=3).pack(side="right")
        tk.Button(head, text="✕", bg=self.BG, fg=self.DANGER, relief="flat",
                  bd=0, command=self.destroy, width=3).pack(side="right")

        self.body = tk.Frame(self, bg=self.BG)
        self.body.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        # Connection line
        conn = tk.Frame(self.body, bg=self.BG)
        conn.pack(fill="x")
        self.conn_label = tk.Label(conn, text="●  连接中…", bg=self.BG, fg=self.MUTED,
                                   font=("Segoe UI", 9), anchor="w")
        self.conn_label.pack(side="left")

        # Status panel
        status = tk.Frame(self.body, bg=self.PANEL, bd=1, relief="solid")
        status.configure(highlightbackground=self.BORDER, highlightthickness=1)
        status.pack(fill="x", pady=(8, 6))
        tk.Label(status, text="当前配置", bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=10, pady=(6, 2))

        self.var_kv = tk.StringVar(value="—")
        self.var_swa = tk.StringVar(value="—")
        self.var_moe = tk.StringVar(value="—")
        self.var_budget = tk.StringVar(value="—")

        grid = tk.Frame(status, bg=self.PANEL)
        grid.pack(fill="x", padx=10, pady=(2, 8))
        for i, (label, var) in enumerate([
            ("KV 缓存", self.var_kv),
            ("SWA 池", self.var_swa),
            ("MoE 槽", self.var_moe),
        ]):
            cell = tk.Frame(grid, bg=self.PANEL)
            cell.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            grid.columnconfigure(i, weight=1)
            tk.Label(cell, text=label, bg=self.PANEL, fg=self.MUTED,
                     font=("Segoe UI", 8)).pack(anchor="w")
            tk.Label(cell, textvariable=var, bg=self.PANEL, fg=self.TEXT,
                     font=("Consolas", 11, "bold")).pack(anchor="w")
        tk.Label(status, textvariable=self.var_budget, bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=10, pady=(0, 6))

        # Preset row
        tk.Label(self.body, text="预设", bg=self.BG, fg=self.MUTED,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(4, 2))
        self.preset_row = tk.Frame(self.body, bg=self.BG)
        self.preset_row.pack(fill="x")

        # Custom section
        tk.Frame(self.body, bg=self.BORDER, height=1).pack(fill="x", pady=8)
        tk.Label(self.body, text="Custom 配置", bg=self.BG, fg=self.MUTED,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")

        self.custom_vars = {
            "kv_tokens": tk.StringVar(value="131072"),
            "swa_tokens": tk.StringVar(value="26214"),
            "moe_slots": tk.StringVar(value="254"),
        }
        sliders = tk.Frame(self.body, bg=self.BG)
        sliders.pack(fill="x", pady=(2, 4))
        for key, label, unit in [
            ("kv_tokens", "KV 缓存", "tokens"),
            ("swa_tokens", "滑窗池", "tokens"),
            ("moe_slots", "MoE 槽", "experts"),
        ]:
            row = tk.Frame(sliders, bg=self.BG)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, bg=self.BG, fg=self.TEXT,
                     font=("Segoe UI", 9), width=8, anchor="w").pack(side="left")
            e = tk.Entry(row, textvariable=self.custom_vars[key], bg=self.FIELD, fg=self.TEXT,
                         insertbackground=self.TEXT, relief="flat", width=10,
                         font=("Consolas", 10), justify="right")
            e.pack(side="left", padx=(0, 6))
            tk.Label(row, text=unit, bg=self.BG, fg=self.MUTED,
                     font=("Segoe UI", 9)).pack(side="left")

        btn_row = tk.Frame(self.body, bg=self.BG)
        btn_row.pack(fill="x", pady=(4, 0))
        tk.Button(btn_row, text="保存为 Custom", bg=self.PANEL, fg=self.TEXT,
                  activebackground=self.FIELD, relief="flat",
                  command=self._save_custom).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="应用", bg=self.ACCENT, fg="#0b1020",
                  activebackground="#a3b9ff", relief="flat", font=("Segoe UI", 9, "bold"),
                  command=self._apply_custom).pack(side="right", padx=(4, 0))
        tk.Button(btn_row, text="重置", bg=self.PANEL, fg=self.MUTED,
                  activebackground=self.FIELD, relief="flat",
                  command=self._reset_custom).pack(side="right")

    # ---------- preset row ----------

    def _refresh_preset_row(self) -> None:
        for b in self.preset_buttons:
            b.destroy()
        self.preset_buttons.clear()

        items = BUILTIN_PRESETS + self.custom_presets
        for i, p in enumerate(items):
            b = tk.Button(
                self.preset_row,
                text=p["name"],
                bg=self.PANEL,
                fg=self.TEXT,
                activebackground=self.FIELD,
                relief="flat",
                font=("Segoe UI", 9, "bold"),
                padx=10, pady=4,
                command=lambda pp=p: self._apply_preset(pp),
            )
            b.grid(row=0, column=i, padx=2, sticky="ew")
            self.preset_row.columnconfigure(i, weight=1)
            tip = f"{p['desc']}\nKV {p['kv_tokens']} · SWA {p['swa_tokens']} · MoE {p['moe_slots']}"
            self._attach_tooltip(b, tip)
            if not p.get("builtin"):
                b.bind("<Button-3>", lambda e, pp=p: self._delete_custom(pp))
            self.preset_buttons.append(b)

    def _attach_tooltip(self, widget, text):
        tip = [None]

        def show(e):
            if tip[0] is not None:
                return
            x = widget.winfo_rootx() + 10
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            t = tk.Toplevel(self)
            t.wm_overrideredirect(True)
            t.wm_geometry(f"+{x}+{y}")
            lbl = tk.Label(t, text=text, bg="#000", fg="#ddd",
                           font=("Segoe UI", 8), padx=6, pady=3, justify="left")
            lbl.pack()
            tip[0] = t

        def hide(e):
            if tip[0] is not None:
                tip[0].destroy()
                tip[0] = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    # ---------- actions ----------

    def _parse_custom(self) -> tuple[int, int, int] | None:
        try:
            kv = int(self.custom_vars["kv_tokens"].get())
            swa = int(self.custom_vars["swa_tokens"].get())
            moe = int(self.custom_vars["moe_slots"].get())
            if min(kv, swa, moe) <= 0:
                raise ValueError
            return kv, swa, moe
        except ValueError:
            messagebox.showerror(APP_TITLE, "数值必须为正整数。")
            return None

    def _apply_preset(self, preset: dict) -> None:
        self._submit(preset["kv_tokens"], preset["swa_tokens"], preset["moe_slots"],
                     label=f"切到「{preset['name']}」")

    def _apply_custom(self) -> None:
        v = self._parse_custom()
        if v is None:
            return
        self._submit(*v, label="应用 Custom")

    def _save_custom(self) -> None:
        v = self._parse_custom()
        if v is None:
            return
        kv, swa, moe = v
        name = tk.simpledialog.askstring(APP_TITLE, "为这套配置命名：", parent=self)
        if not name:
            return
        name = name.strip()
        if any(p["name"] == name for p in self.custom_presets + BUILTIN_PRESETS):
            messagebox.showerror(APP_TITLE, "已存在同名预设。")
            return
        preset = {
            "name": name,
            "desc": f"自定义 KV {kv} · SWA {swa} · MoE {moe}",
            "kv_tokens": kv,
            "swa_tokens": swa,
            "moe_slots": moe,
            "builtin": False,
        }
        self.custom_presets.append(preset)
        save_custom_presets(self.custom_presets)
        self._refresh_preset_row()

    def _delete_custom(self, preset: dict) -> None:
        if preset.get("builtin"):
            return
        if not messagebox.askyesno(APP_TITLE, f"删除「{preset['name']}」？"):
            return
        self.custom_presets = [p for p in self.custom_presets if p["name"] != preset["name"]]
        save_custom_presets(self.custom_presets)
        self._refresh_preset_row()

    def _reset_custom(self) -> None:
        self.custom_vars["kv_tokens"].set("131072")
        self.custom_vars["swa_tokens"].set("26214")
        self.custom_vars["moe_slots"].set("254")

    def _submit(self, kv: int, swa: int, moe: int, label: str) -> None:
        def run():
            self.conn_label.configure(text=f"●  {label}…", fg=self.ACCENT)
            try:
                self.client.cache_rebuild(kv, swa, moe, mode="if_idle", timeout=300.0)
            except urllib.error.URLError as e:
                self.after(0, lambda: messagebox.showerror(APP_TITLE, f"请求失败：{e}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(APP_TITLE, f"出错：{e}"))
            finally:
                self.after(0, lambda: self._refresh_status_sync())
        threading.Thread(target=run, daemon=True).start()

    # ---------- status polling ----------

    def _kick_status_loop(self) -> None:
        def loop():
            while not self._status_thread_stop.is_set():
                try:
                    s = self.client.cache_status()
                    self._last_status = s
                    self.after(0, self._render_status, s)
                except Exception:
                    self.after(0, self._render_offline)
                self._status_thread_stop.wait(2.0)
        threading.Thread(target=loop, daemon=True).start()

    def _refresh_status_sync(self) -> None:
        try:
            s = self.client.cache_status()
            self._last_status = s
            self._render_status(s)
        except Exception:
            self._render_offline()

    def _render_status(self, s: dict) -> None:
        g = s.get("geometry", {}) or {}
        last = s.get("last_rebuild", {}) or {}
        np_p = int(g.get("num_pages", 0))
        np_s = int(g.get("num_swa_pages", 0))
        moe = int(g.get("moe_cache_size", 0))
        lim = (s.get("limits") or {}).get("kv_tokens", {})
        if lim:
            self.var_kv.set(f"{np_p:,} / {lim.get('max', 0):,}")
        else:
            self.var_kv.set(f"{np_p:,}")
        self.var_swa.set(f"{np_s:,}")
        self.var_moe.set(f"{moe} / {g.get('num_experts', 0) * g.get('num_moe_layers', 0)}")

        ub = g.get("unit_bytes", {}) or {}
        budget = int(g.get("cache_budget_bytes", 0))
        kv_b = np_p * int(ub.get("kv_per_token", 0))
        swa_b = np_s * int(ub.get("swa_per_token", 0))
        moe_b = moe * int(ub.get("moe_per_expert", 0))
        used = kv_b + swa_b + moe_b
        self.var_budget.set(
            f"显存 {used/1024**3:.2f} / {budget/1024**3:.2f} GiB"
        )

        busy = last.get("status") == "busy"
        self.conn_label.configure(
            text=("● 重建中…" if busy else "● 已连接"),
            fg=(self.ACCENT if busy else "#5ec27a"),
        )

    def _render_offline(self) -> None:
        self.conn_label.configure(text="● 连接失败", fg=self.DANGER)
        self.var_kv.set("—")
        self.var_swa.set("—")
        self.var_moe.set("—")
        self.var_budget.set("FreeToken server 未响应 (127.0.0.1:1919)")

    # ---------- collapse / drag ----------

    def _toggle_collapse(self) -> None:
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.body.pack_forget()
            self.geometry(f"{self.width}x36")
        else:
            self.body.pack(fill="both", expand=True, padx=10, pady=(2, 10))
            self.geometry(f"{self.width}x420")

    def _start_drag(self, e):
        self._drag_x = e.x
        self._drag_y = e.y

    def _on_drag(self, e):
        x = self.winfo_x() + (e.x - self._drag_x)
        y = self.winfo_y() + (e.y - self._drag_y)
        self.geometry(f"+{x}+{y}")

    def destroy(self):
        self._status_thread_stop.set()
        super().destroy()


# ----------------------------- Entry point -----------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="FreeToken Cache Bar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1919)
    parser.add_argument("--pin", default="right",
                        choices=["left", "right", "top", "bottom"],
                        help="Dock the window to a screen edge.")
    args, _ = parser.parse_known_args()

    client = FreeTokenClient(args.host, args.port)
    app = CacheBar(client, pin=args.pin)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
