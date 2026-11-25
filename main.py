"""Sea Battle Lite - легкая версия 1x1 на встроенном Tkinter без ImGui и без картинок."""
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox
from PIL import ImageTk
import qrcode

from game_logic import Board, Ship, CELL_EMPTY, CELL_SHIP, CELL_MISS, CELL_HIT, CELL_SUNK
from network_relay import NetworkRelay, generate_room_code

SESSION_FILE = Path.home() / ".seabattle_lite_session.json"

BG = "#0A0A0B"
SIDEBAR = "#0D0E10"
PANEL = "#111214"
WIDGET = "#181A1E"
BORDER = "#2A2E36"
TEXT = "#FFFFFF"
MUTED = "#8A94A6"


class SeaBattleLiteApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Sea Battle Lite")
        self.root.geometry("980x660")
        self.root.minsize(860, 600)
        self.root.configure(bg=BG)

        self.size = 10
        self.player = Board(self.size)
        self.enemy = Board(self.size, {})
        self.phase = "placement"
        self.turn = "player"
        self.orientation = "H"
        self.selected_size = 4
        self.enemy_sunk_count = 0
        self.phone_ready = False
        self.room_locked = False
        self.current_page = "home"
        self._last_hb = 0.0
        self._qr_photo = None

        self.events = queue.Queue()
        self.relay = NetworkRelay()
        self.relay.on_phone_connected = lambda: self.events.put(("phone_connected", None))
        self.relay.on_phone_ready = lambda d: self.events.put(("phone_ready", d))
        self.relay.on_phone_shot = lambda r, c: self.events.put(("phone_shot", (r, c)))
        self.relay.on_defense_result = lambda d: self.events.put(("defense_result", d))
        self.relay.on_phone_restart = lambda: self.events.put(("phone_restart", None))
        self.relay.on_phone_left = lambda: self.events.put(("phone_left", None))
        self.relay.on_error = lambda e: self.events.put(("relay_error", e))

        self.root.bind("<r>", self._on_rotate_key)
        self.root.bind("<R>", self._on_rotate_key)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_layout()
        start_page = self._restore_session()
        self.show_page(start_page)
        self._tick()

    def _build_layout(self):
        self.sidebar = tk.Frame(self.root, bg=SIDEBAR, width=200, highlightbackground=BORDER, highlightthickness=1)
        self.sidebar.pack(side="left", fill="y", padx=(10, 6), pady=10)
        self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar, text="SEA BATTLE", bg=SIDEBAR, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(pady=(16, 18))

        self.nav_btns = {}
        for key, label in [("home", "Главная"), ("game", "Морской бой"), ("multiplayer", "Мультиплеер"), ("about", "О проекте")]:
            b = tk.Button(
                self.sidebar, text=label, bg=SIDEBAR, fg=MUTED,
                activebackground=WIDGET, activeforeground=TEXT,
                relief="flat", bd=0, anchor="w", padx=16, pady=10,
                font=("Segoe UI", 11, "bold"),
                command=lambda p=key: self._nav_click(p)
            )
            b.pack(fill="x", padx=8, pady=3)
            self.nav_btns[key] = b

        self.status_bar = tk.Label(self.sidebar, text="", bg=SIDEBAR, fg=MUTED, font=("Segoe UI", 9), wraplength=180, justify="left")
        self.status_bar.pack(side="bottom", fill="x", padx=10, pady=12)

        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(side="right", fill="both", expand=True, padx=(6, 10), pady=10)

    def notify(self, msg: str):
        self.status_bar.config(text=msg, fg=TEXT)

    def _nav_click(self, page: str):
        if self.room_locked and page not in ("game", "multiplayer"):
            self.notify("Вы в комнате! Нажмите «Выйти из комнаты»")
            return
        if page == "game":
            if not self.room_locked:
                self.notify("Сначала создайте комнату в Мультиплеере!")
                self.show_page("multiplayer")
            elif self.phase == "battle":
                self.show_page("game")
            else:
                self.show_page("placement")
        else:
            self.show_page(page)

    def show_page(self, page: str):
        self.current_page = page
        active_tab = "game" if page in ("game", "placement") else page
        for k, b in self.nav_btns.items():
            b.config(bg=WIDGET if k == active_tab else SIDEBAR, fg=TEXT if k == active_tab else MUTED)

        for w in self.content.winfo_children():
            w.destroy()

        if page == "home":
            self._page_home()
        elif page == "multiplayer":
            self._page_multiplayer()
        elif page == "placement":
            self._page_placement()
        elif page == "game":
            self._page_game()
        elif page == "about":
            self._page_about()

    def _page_home(self):
        box = tk.Frame(self.content, bg=BG)
        box.place(relx=0.5, rely=0.46, anchor="center")

        tk.Label(box, text="МОРСКОЙ БОЙ 1x1", bg=BG, fg=TEXT, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(box, text="Легкая сетевая версия без ImGui и лишних картинок", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 12))

        card = tk.Frame(box, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=18, pady=16)
        card.pack(fill="x")
        tk.Label(card, text="Сетевая игра с другом", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(card, text="Создайте комнату, передайте код или QR-код противнику и играйте в реальном времени.", bg=PANEL, fg=MUTED, font=("Segoe UI", 10), wraplength=430, justify="left").pack(anchor="w", pady=(4, 12))

        btns = tk.Frame(card, bg=PANEL)
        btns.pack(anchor="w")
        tk.Button(btns, text="Создать онлайн комнату", bg="#F5F5F7", fg="#0E0F12", relief="flat", padx=14, pady=7, font=("Segoe UI", 10, "bold"), command=lambda: self.show_page("multiplayer")).pack(side="left", padx=(0, 8))
        tk.Button(btns, text="О проекте", bg=WIDGET, fg=TEXT, relief="flat", padx=14, pady=7, font=("Segoe UI", 10, "bold"), command=lambda: self.show_page("about")).pack(side="left")

    def _page_multiplayer(self):
        tk.Label(self.content, text="Онлайн мультиплеер", bg=BG, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0, 2))
        tk.Label(self.content, text="Сетевой бой между вами и противником", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))

        card = tk.Frame(self.content, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=16, pady=16)
        card.pack(fill="both", expand=True)

        left = tk.Frame(card, bg=PANEL)
        left.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="КОД ВАШЕЙ КОМНАТЫ", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        code = self.relay.room_code if self.room_locked else "- - - - -"
        self.lbl_room_code = tk.Label(left, text=code, bg=PANEL, fg=TEXT, font=("Segoe UI", 22, "bold"))
        self.lbl_room_code.pack(anchor="w", pady=(2, 6))

        st_txt = "Комната не запущена"
        if self.phone_ready:
            st_txt = "Противник готов. Расставьте флот и нажмите «Начать бой»"
        elif self.relay.is_phone_connected:
            st_txt = "Противник подключился"
        elif self.relay.is_connected:
            st_txt = "Комната готова. Ожидание противника..."
        elif self.room_locked:
            st_txt = "Подключение к серверу..."

        self.lbl_net_status = tk.Label(left, text=st_txt, bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"), wraplength=360, justify="left")
        self.lbl_net_status.pack(anchor="w", pady=(0, 14))

        row1 = tk.Frame(left, bg=PANEL)
        row1.pack(anchor="w", pady=4)
        tk.Button(row1, text="Создать комнату", bg="#F5F5F7", fg="#0E0F12", relief="flat", padx=12, pady=7, font=("Segoe UI", 10, "bold"), command=self.create_room).pack(side="left", padx=(0, 8))
        tk.Button(row1, text="Копировать ссылку", bg=WIDGET, fg=TEXT, relief="flat", padx=12, pady=7, font=("Segoe UI", 10, "bold"), command=self.copy_link).pack(side="left")

        row2 = tk.Frame(left, bg=PANEL)
        row2.pack(anchor="w", pady=6)
        tk.Button(row2, text="Расставить флот", bg="#F5F5F7", fg="#0E0F12", relief="flat", padx=12, pady=7, font=("Segoe UI", 10, "bold"), command=self.go_to_placement).pack(side="left", padx=(0, 8))
        tk.Button(row2, text="Выйти из комнаты", bg="#231218", fg="#F87171", relief="flat", padx=12, pady=7, font=("Segoe UI", 10, "bold"), command=self.stop_room).pack(side="left")

        right = tk.Frame(card, bg=PANEL, width=220)
        right.pack(side="right", fill="y", padx=(12, 0))
        tk.Label(right, text="QR-КОД ДЛЯ ПОДКЛЮЧЕНИЯ", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(pady=(0, 8))
        self.lbl_qr = tk.Label(right, bg=WIDGET, fg=MUTED, text="Нажмите\n«Создать комнату»", width=26, height=12)
        self.lbl_qr.pack()
        if self.room_locked:
            self._render_qr()

    def _render_qr(self):
        if not hasattr(self, "lbl_qr") or not self.lbl_qr.winfo_exists():
            return
        qr = qrcode.QRCode(box_size=5, border=2)
        qr.add_data(self.relay.get_join_url())
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((200, 200))
        self._qr_photo = ImageTk.PhotoImage(img)
        self.lbl_qr.config(image=self._qr_photo, text="", width=200, height=200)

    def _build_grid(self, parent, prefix: str, clickable: bool):
        frame = tk.Frame(parent, bg=PANEL)
        frame.pack()
        letters = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К"]
        tk.Label(frame, text="", bg=PANEL, width=2).grid(row=0, column=0)
        for c in range(self.size):
            tk.Label(frame, text=letters[c], bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"), width=3).grid(row=0, column=c + 1)

        btns = {}
        for r in range(self.size):
            tk.Label(frame, text=str(r + 1), bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"), width=2).grid(row=r + 1, column=0)
            for c in range(self.size):
                b = tk.Button(
                    frame, text="", width=3, height=1, bg=WIDGET, fg=TEXT,
                    relief="flat", bd=1, font=("Segoe UI", 9, "bold")
                )
                if clickable:
                    b.config(command=lambda rr=r, cc=c, p=prefix: self.cell_click(p, rr, cc))
                b.bind("<Enter>", lambda e, rr=r, cc=c, p=prefix: self._set_coord_hint(p, rr, cc))
                b.grid(row=r + 1, column=c + 1, padx=1, pady=1)
                btns[(r, c)] = b
        return btns

    def _set_coord_hint(self, prefix: str, r: int, c: int):
        lbl = getattr(self, f"hint_{prefix}", None)
        if lbl and lbl.winfo_exists():
            lbl.config(text=f"[ {Board.coord_to_str(r, c)} ]")

    def _page_placement(self):
        tk.Label(self.content, text="Расстановка флота", bg=BG, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(self.content, text="Нажмите на клетку, чтобы поставить или убрать корабль. R - поворот.", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 8))

        wrap = tk.Frame(self.content, bg=BG)
        wrap.pack(fill="both", expand=True)

        left = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=12, pady=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        hdr = tk.Frame(left, bg=PANEL)
        hdr.pack(fill="x", pady=(0, 6))
        tk.Label(hdr, text="ВАШЕ ПОЛЕ", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.hint_placement = tk.Label(hdr, text="", bg=PANEL, fg="#C8DCF5", font=("Segoe UI", 10, "bold"))
        self.hint_placement.pack(side="right")
        self.grid_placement = self._build_grid(left, "placement", True)

        right = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=14, pady=14, width=300)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        tk.Label(right, text="ВЫБОР КОРАБЛЯ", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        self.ship_btns = {}
        names = {4: "Линкор (4)", 3: "Крейсер (3)", 2: "Эсминец (2)", 1: "Катер (1)"}
        for sz in (4, 3, 2, 1):
            b = tk.Button(right, text=names[sz], bg=WIDGET, fg=TEXT, relief="flat", pady=6, font=("Segoe UI", 10, "bold"), command=lambda s=sz: self.select_ship(s))
            b.pack(fill="x", pady=2)
            self.ship_btns[sz] = b

        self.lbl_orient = tk.Label(right, text="", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"))
        self.lbl_orient.pack(anchor="w", pady=(10, 8))

        r_row = tk.Frame(right, bg=PANEL)
        r_row.pack(fill="x", pady=3)
        tk.Button(r_row, text="Повернуть (R)", bg=WIDGET, fg=TEXT, relief="flat", pady=6, command=self.rotate).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(r_row, text="Очистить", bg="#231218", fg="#F87171", relief="flat", pady=6, command=self.clear_placement).pack(side="right", fill="x", expand=True, padx=(4, 0))

        tk.Button(right, text="Случайная расстановка", bg=WIDGET, fg=TEXT, relief="flat", pady=7, command=self.auto_place).pack(fill="x", pady=4)
        tk.Button(right, text="Начать бой", bg="#F5F5F7", fg="#0E0F12", relief="flat", pady=9, font=("Segoe UI", 10, "bold"), command=self.start_battle).pack(fill="x", pady=(6, 0))
        self.refresh_all()

    def _page_game(self):
        tk.Label(self.content, text="Морской бой", bg=BG, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        self.lbl_turn = tk.Label(self.content, text="", bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold"))
        self.lbl_turn.pack(anchor="w", pady=(0, 8))

        wrap = tk.Frame(self.content, bg=BG)
        wrap.pack(fill="both", expand=True)

        p_card = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=10, pady=10)
        p_card.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ph = tk.Frame(p_card, bg=PANEL)
        ph.pack(fill="x", pady=(0, 6))
        tk.Label(ph, text="ВАШ ФЛОТ", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.lbl_p_alive = tk.Label(ph, text="", bg=PANEL, fg=TEXT, font=("Segoe UI", 10))
        self.lbl_p_alive.pack(side="left", padx=10)
        self.hint_player = tk.Label(ph, text="", bg=PANEL, fg="#C8DCF5", font=("Segoe UI", 10, "bold"))
        self.hint_player.pack(side="right")
        self.grid_player = self._build_grid(p_card, "player", False)

        e_card = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=10, pady=10)
        e_card.pack(side="right", fill="both", expand=True, padx=(6, 0))
        eh = tk.Frame(e_card, bg=PANEL)
        eh.pack(fill="x", pady=(0, 6))
        tk.Label(eh, text="ПОЛЕ ПРОТИВНИКА", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.lbl_e_alive = tk.Label(eh, text="", bg=PANEL, fg="#F87171", font=("Segoe UI", 10))
        self.lbl_e_alive.pack(side="left", padx=10)
        self.hint_enemy = tk.Label(eh, text="", bg=PANEL, fg="#C8DCF5", font=("Segoe UI", 10, "bold"))
        self.hint_enemy.pack(side="right")
        self.grid_enemy = self._build_grid(e_card, "enemy", True)
        self.refresh_all()

    def _page_about(self):
        tk.Label(self.content, text="О проекте (Lite)", bg=BG, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0, 8))
        card = tk.Frame(self.content, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=16, pady=16)
        card.pack(fill="both", expand=True)
        info = (
            "Легкая версия Sea Battle 1x1 без Dear PyGui / ImGui и без графических ассетов.\n\n"
            "Файлы проекта:\n"
            "- main.py: интерфейс на встроенном Tkinter, логика экранов, таймер активности (AFK) и автосохранение сессии.\n"
            "- game_logic.py: правила поля 10x10, расстановка кораблей без касаний, выстрелы.\n"
            "- network_relay.py: обмен ходами с противником через облачный сервер и генерация QR-кода.\n"
            "- build.py: сборка в компактный SeaBattleLite.exe без тяжелых GUI-библиотек."
        )
        tk.Label(card, text=info, bg=PANEL, fg=TEXT, font=("Segoe UI", 10), justify="left", wraplength=660).pack(anchor="nw")

    def select_ship(self, sz: int):
        self.selected_size = sz
        self.refresh_all()

    def rotate(self):
        self.orientation = "V" if self.orientation == "H" else "H"
        self.refresh_all()

    def _on_rotate_key(self, event=None):
        if self.current_page == "placement":
            self.rotate()

    def auto_place(self):
        self.player.auto_place_all()
        self.notify("Флот расставлен автоматически")
        self.refresh_all()

    def clear_placement(self):
        self.player.reset()
        self.notify("Поле очищено")
        self.refresh_all()

    def cell_click(self, prefix: str, r: int, c: int):
        if prefix == "placement" and self.phase == "placement":
            if self.player.get_cell(r, c) == CELL_SHIP:
                removed = self.player.remove_ship_at(r, c)
                if removed:
                    self.selected_size = removed.size
            elif self.player.get_remaining_to_place().get(self.selected_size, 0) > 0:
                if self.player.place_ship(r, c, self.selected_size, self.orientation):
                    rem = self.player.get_remaining_to_place()
                    if rem.get(self.selected_size, 0) <= 0:
                        for nxt in (4, 3, 2, 1):
                            if rem.get(nxt, 0) > 0:
                                self.selected_size = nxt
                                break
                else:
                    self.notify("Нельзя поставить сюда!")
            self.refresh_all()
        elif prefix == "enemy" and self.phase == "battle" and self.turn == "player":
            if self.enemy.get_cell(r, c) != CELL_EMPTY:
                return
            self.turn = "waiting"
            self.relay.send_to_phone({"action": "incoming_shot", "r": r, "c": c})
            self.refresh_all()

    def start_battle(self):
        if not self.player.is_fleet_complete():
            self.notify("Расставьте весь флот!")
            return
        if not self.phone_ready:
            self.notify("Противник еще не готов")
            self.show_page("multiplayer")
            return
        self.enemy = Board(self.size, {})
        self.enemy_sunk_count = 0
        self.phase = "battle"
        self.turn = "player"
        self.relay.send_to_phone({"action": "game_start", "phone_turn": False, "size": self.size})
        self._save_session()
        self.show_page("game")

    def create_room(self):
        if self.relay.is_connected:
            self.relay.send_to_phone({"action": "room_closed"})
        self.relay.stop()
        self.room_locked = True
        self.phone_ready = False
        self.player = Board(self.size)
        self.enemy = Board(self.size, {})
        self.phase = "placement"
        self.turn = "player"
        self.enemy_sunk_count = 0

        code = generate_room_code()
        self.relay.room_code = code
        if hasattr(self, "lbl_room_code") and self.lbl_room_code.winfo_exists():
            self.lbl_room_code.config(text=code)
        if hasattr(self, "lbl_net_status") and self.lbl_net_status.winfo_exists():
            self.lbl_net_status.config(text="Подключение к серверу...")
        self._render_qr()
        threading.Thread(target=lambda: (self.relay.start(code), self.events.put(("room_updated", None))), daemon=True).start()
        self._save_session()
        self.notify(f"Комната: {code}")

    def stop_room(self):
        if self.relay.is_connected:
            self.relay.send_to_phone({"action": "room_closed"})
        self.relay.stop()
        self.room_locked = False
        self.phone_ready = False
        self.phase = "placement"
        self._clear_session()
        if self.current_page == "multiplayer":
            self.show_page("multiplayer")
        self.notify("Вы вышли из комнаты")

    def copy_link(self):
        url = self.relay.get_join_url()
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.notify("Ссылка скопирована!")

    def go_to_placement(self):
        self.player = Board(self.size)
        self.enemy = Board(self.size, {})
        self.phase = "placement"
        self.show_page("placement")

    def refresh_all(self):
        self._refresh_grid("grid_placement", self.player, False)
        self._refresh_grid("grid_player", self.player, False)
        self._refresh_grid("grid_enemy", self.enemy, True)

        if hasattr(self, "ship_btns"):
            rem = self.player.get_remaining_to_place()
            names = {4: "Линкор (4)", 3: "Крейсер (3)", 2: "Эсминец (2)", 1: "Катер (1)"}
            for sz, b in self.ship_btns.items():
                if b.winfo_exists():
                    tot = self.player.fleet_config[sz]
                    r_cnt = rem[sz]
                    b.config(
                        text=f"{names[sz]} [{tot - r_cnt}/{tot}]",
                        bg="#2A303C" if sz == self.selected_size else WIDGET
                    )
        if hasattr(self, "lbl_orient") and self.lbl_orient.winfo_exists():
            self.lbl_orient.config(text=f"Ориентация: {'Горизонтально' if self.orientation == 'H' else 'Вертикально'}")
        if hasattr(self, "lbl_p_alive") and self.lbl_p_alive.winfo_exists():
            self.lbl_p_alive.config(text=f"Кораблей: {self.player.count_alive_ships()}")
        if hasattr(self, "lbl_e_alive") and self.lbl_e_alive.winfo_exists():
            cnt = max(0, sum(self.player.fleet_config.values()) - self.enemy_sunk_count)
            self.lbl_e_alive.config(text=f"Кораблей: {cnt}")
        if hasattr(self, "lbl_turn") and self.lbl_turn.winfo_exists():
            txt = "Ваш ход - выберите клетку на поле противника" if self.turn == "player" else "Ход противника..."
            self.lbl_turn.config(text=txt, fg=TEXT if self.turn == "player" else "#F97316")

    def _refresh_grid(self, attr: str, board: Board, hide: bool):
        btns = getattr(self, attr, None)
        if not btns:
            return
        view = board.get_view(hide)
        styles = {
            CELL_EMPTY: ("", WIDGET, MUTED),
            CELL_SHIP: ("■", "#323844", TEXT),
            CELL_MISS: ("•", "#101114", MUTED),
            CELL_HIT: ("×", "#EA580C", TEXT),
            CELL_SUNK: ("×", "#DC2626", TEXT),
        }
        for (r, c), b in btns.items():
            if b.winfo_exists():
                t, bg, fg = styles[view[r][c]]
                b.config(text=t, bg=bg, fg=fg)

    def _save_session(self):
        try:
            payload = {
                "room_code": self.relay.room_code,
                "room_locked": self.room_locked,
                "phase": self.phase,
                "turn": self.turn,
                "current_page": self.current_page,
                "phone_ready": self.phone_ready,
                "enemy_sunk_count": self.enemy_sunk_count,
                "player_grid": self.player.grid,
                "player_ships": [{"size": s.size, "cells": s.cells, "hits": list(s.hits), "orientation": s.orientation} for s in self.player.ships],
                "enemy_grid": self.enemy.grid,
            }
            SESSION_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

    def _clear_session(self):
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
        except Exception:
            pass

    def _restore_session(self) -> str:
        if not SESSION_FILE.exists():
            return "home"
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            if not data.get("room_locked"):
                return "home"
            self.room_locked = True
            self.phase = data.get("phase", "placement")
            self.turn = data.get("turn", "player")
            self.phone_ready = bool(data.get("phone_ready", False))
            self.enemy_sunk_count = int(data.get("enemy_sunk_count", 0))
            self.player.grid = data.get("player_grid", self.player.grid)
            self.player.ships = []
            for sd in data.get("player_ships", []):
                sh = Ship(sd["size"], [tuple(c) for c in sd["cells"]], sd.get("orientation", "H"))
                sh.hits = {tuple(h) for h in sd.get("hits", [])}
                self.player.ships.append(sh)
            self.enemy.grid = data.get("enemy_grid", self.enemy.grid)
            code = data.get("room_code")
            if code:
                self.relay.room_code = code
                threading.Thread(target=lambda: self.relay.start(code), daemon=True).start()
            page = data.get("current_page", "multiplayer")
            return page if page in ("game", "placement", "multiplayer") else "multiplayer"
        except Exception:
            self._clear_session()
            return "home"

    def _tick(self):
        now = time.monotonic()
        if self.relay.is_connected and (now - self._last_hb) >= 3.0:
            self._last_hb = now
            self.relay.send_to_phone({"action": "heartbeat"})

        if self.relay.is_phone_connected and self.relay.last_phone_seen > 0 and (now - self.relay.last_phone_seen) > 12.0:
            self.relay.is_phone_connected = False
            self.relay.last_phone_seen = 0.0
            self.phone_ready = False
            self.events.put(("phone_afk", None))

        if self.relay.is_connected and hasattr(self, "lbl_net_status") and self.lbl_net_status.winfo_exists():
            if self.lbl_net_status.cget("text") == "Подключение к серверу...":
                self.lbl_net_status.config(text="Комната готова. Ожидание противника...")

        try:
            while True:
                action, data = self.events.get_nowait()
                if action == "phone_connected":
                    self.notify("Противник подключился!")
                    if hasattr(self, "lbl_net_status") and self.lbl_net_status.winfo_exists():
                        self.lbl_net_status.config(text="Противник подключился")
                elif action == "phone_ready":
                    self.phone_ready = True
                    self.notify("Противник готов к бою!")
                    if hasattr(self, "lbl_net_status") and self.lbl_net_status.winfo_exists():
                        self.lbl_net_status.config(text="Противник готов. Нажмите «Начать бой»")
                elif action in ("phone_left", "phone_afk"):
                    self.phone_ready = False
                    msg = "Противник вышел из комнаты" if action == "phone_left" else "Противник вышел из игры"
                    self.notify(msg)
                    if self.phase == "battle":
                        self.phase = "placement"
                        self.show_page("multiplayer")
                elif action == "phone_shot" and self.phase == "battle" and self.turn == "phone":
                    r, c = data
                    res, _, misses = self.player.receive_shot(r, c)
                    all_sunk = self.player.is_all_sunk
                    self.relay.send_to_phone({"action": "shot_result", "r": r, "c": c, "res": res, "surrounding": misses, "all_sunk": all_sunk})
                    if all_sunk:
                        self.relay.send_to_phone({"action": "game_over", "winner": "phone"})
                        self.phase = "finished"
                        messagebox.showinfo("Итог", "Поражение. Ваш флот уничтожен.")
                        self.stop_room()
                    else:
                        self.turn = "phone" if res in ("hit", "sunk") else "player"
                    self.refresh_all()
                elif action == "defense_result" and self.phase == "battle":
                    r, c = int(data["r"]), int(data["c"])
                    res = data.get("res", "miss")
                    self.enemy.grid[r][c] = CELL_MISS if res == "miss" else CELL_HIT if res == "hit" else CELL_SUNK
                    if res == "sunk":
                        self.enemy_sunk_count += 1
                    for mr, mc in data.get("surrounding", []):
                        self.enemy.grid[mr][mc] = CELL_MISS
                    if data.get("all_sunk", False):
                        self.relay.send_to_phone({"action": "game_over", "winner": "pc"})
                        self.phase = "finished"
                        messagebox.showinfo("Итог", "Победа! Флот противника уничтожен.")
                        self.stop_room()
                    else:
                        self.turn = "player" if res in ("hit", "sunk") else "phone"
                    self.refresh_all()
        except queue.Empty:
            pass

        self.root.after(50, self._tick)

    def _on_close(self):
        if self.room_locked:
            self._save_session()
        self.relay.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SeaBattleLiteApp().run()
