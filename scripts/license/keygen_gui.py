"""Окно выдачи лицензионных ключей «Строительной ERP» (только для разработчика)."""
import datetime
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keygen as kg  # noqa: E402

TERMS = [("Бессрочно", None), ("1 год", "1г"), ("6 месяцев", "6м"), ("3 месяца", "3м"),
         ("1 месяц", "1м"), ("До даты…", "date")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Строительная ERP — выдача лицензий (Actually_team)")
        self.geometry("900x620")
        self.minsize(760, 520)
        try:
            self.sk = kg.load_key()
        except SystemExit as e:
            messagebox.showerror("Нет секретного ключа", str(e))
            self.destroy()
            return
        style = ttk.Style(self)
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=8)
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Код компьютера клиента").grid(row=0, column=0, sticky="w")
        self.code = tk.StringVar()
        ttk.Entry(f, textvariable=self.code, font=("Consolas", 14), width=18).grid(
            row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Label(f, text="Компания").grid(row=0, column=1, sticky="w", padx=(16, 0))
        self.company = tk.StringVar()
        ttk.Entry(f, textvariable=self.company, font=("Segoe UI", 12), width=40).grid(
            row=1, column=1, sticky="we", padx=(16, 0), pady=(0, 10))

        ttk.Label(f, text="Срок").grid(row=2, column=0, sticky="w")
        tf = ttk.Frame(f)
        tf.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.term = tk.StringVar(value="Бессрочно")
        for label, _v in TERMS:
            ttk.Radiobutton(tf, text=label, value=label, variable=self.term,
                            command=self._term_changed).pack(side="left", padx=(0, 12))
        self.date = tk.StringVar(value=(datetime.date.today() + datetime.timedelta(days=365)).strftime("%d.%m.%Y"))
        self.date_entry = ttk.Entry(tf, textvariable=self.date, width=12, state="disabled")
        self.date_entry.pack(side="left")

        ttk.Button(f, text="Создать ключ", style="Big.TButton", command=self.create).grid(
            row=4, column=0, sticky="w", pady=(4, 10))

        self.result = tk.Text(f, height=4, wrap="char", font=("Consolas", 10))
        self.result.grid(row=5, column=0, columnspan=2, sticky="we")
        bf = ttk.Frame(f)
        bf.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 12))
        ttk.Button(bf, text="Копировать ключ", command=self.copy).pack(side="left")
        self.info = ttk.Label(bf, text="", foreground="#198754")
        self.info.pack(side="left", padx=12)

        ttk.Label(f, text="Выданные ключи (двойной щелчок — скопировать ключ)").grid(
            row=7, column=0, columnspan=2, sticky="w")
        cols = ("date", "company", "code", "until")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=10)
        for c, t, w in zip(cols, ("Дата", "Компания", "Код компьютера", "Срок"), (90, 320, 160, 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.grid(row=8, column=0, columnspan=2, sticky="nsew")
        self.tree.bind("<Double-1>", self.copy_row)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(8, weight=1)
        self.keys = {}
        self.reload()

    def _term_changed(self):
        self.date_entry.configure(state="normal" if self.term.get() == "До даты…" else "disabled")

    def _until(self):
        value = dict(TERMS)[self.term.get()]
        if value is None:
            return None
        if value == "date":
            return kg.parse_until(self.date.get())
        return kg.parse_until(value)

    def create(self):
        code = self.code.get().strip().upper().replace(" ", "")
        if not re.fullmatch(kg.CODE_RE, code):
            messagebox.showwarning("Код компьютера", "Введите код в виде XXXX-XXXX-XXXX\n(его показывает окно «Лицензия» у клиента).")
            return
        company = self.company.get().strip()
        if not company:
            messagebox.showwarning("Компания", "Введите название компании.")
            return
        try:
            until = self._until()
        except ValueError as e:
            messagebox.showwarning("Срок", str(e))
            return
        key, payload = kg.make_key(self.sk, code, company, until)
        kg.save_issued(payload, key)
        self.result.delete("1.0", "end")
        self.result.insert("1.0", key)
        self.copy()
        self.info.configure(text="Ключ создан и скопирован. Срок: %s" % (
            until.strftime("%d.%m.%Y") if until else "бессрочно"))
        self.reload()

    def copy(self):
        key = self.result.get("1.0", "end").strip()
        if key:
            self.clipboard_clear()
            self.clipboard_append(key)
            self.info.configure(text="Ключ скопирован — вставьте его в Telegram/WhatsApp клиенту.")

    def copy_row(self, _event):
        sel = self.tree.selection()
        if sel:
            key = self.keys.get(sel[0], "")
            self.result.delete("1.0", "end")
            self.result.insert("1.0", key)
            self.copy()

    def reload(self):
        self.tree.delete(*self.tree.get_children())
        self.keys.clear()
        for row in reversed(kg.read_issued()):
            if len(row) < 5:
                continue
            iid = self.tree.insert("", "end", values=row[:4])
            self.keys[iid] = row[4]


if __name__ == "__main__":
    App().mainloop()
