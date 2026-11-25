# -*- coding: utf-8 -*-
"""
game_logic.py - Основная игровая логика морского боя.
Поддерживает настраиваемые размеры поля, различные конфигурации флота,
проверку правил расстановки (включая диагональный зазор) и туман войны.
"""

import random
from typing import List, Tuple, Set, Dict, Optional

# Буквы для разметки столбцов (классические русские обозначения: А, Б, В, Г, Д, Е, Ж, З, И, К)
LETTERS = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К", "Л", "М", "Н", "О"]

# Состояния клетки
CELL_EMPTY = 0      # Пустая вода
CELL_SHIP = 1       # Сегмент корабля (не поврежден)
CELL_MISS = 2       # Промах (вода, в которую стреляли)
CELL_HIT = 3        # Попадание (подбитый сегмент)
CELL_SUNK = 4       # Потопленный сегмент


class Ship:
    def __init__(self, size: int, cells: List[Tuple[int, int]], orientation: str = 'H'):
        self.size = size
        self.cells = list(cells)  # [(row, col), ...]
        self.hits: Set[Tuple[int, int]] = set()
        self.orientation = orientation  # 'H' или 'V'

    @property
    def is_sunk(self) -> bool:
        return len(self.hits) >= self.size

    def hit(self, r: int, c: int) -> bool:
        if (r, c) in self.cells:
            self.hits.add((r, c))
            return True
        return False

    def get_surrounding_cells(self, board_size: int) -> Set[Tuple[int, int]]:
        """Возвращает все клетки вокруг корабля (включая диагонали), не входящие в сам корабль."""
        surrounding = set()
        for r, c in self.cells:
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < board_size and 0 <= nc < board_size:
                        if (nr, nc) not in self.cells:
                            surrounding.add((nr, nc))
        return surrounding

    def to_dict(self) -> dict:
        return {
            "size": self.size,
            "cells": self.cells,
            "hits": list(self.hits),
            "is_sunk": self.is_sunk,
            "orientation": self.orientation
        }


class Board:
    def __init__(self, size: int = 10, fleet_config: Optional[Dict[int, int]] = None):
        self.size = size
        # По умолчанию классический флот: 1x4, 2x3, 3x2, 4x1
        if fleet_config is None:
            if size == 8:
                self.fleet_config = {3: 1, 2: 2, 1: 3}
            elif size == 12:
                self.fleet_config = {5: 1, 4: 1, 3: 2, 2: 3, 1: 4}
            else:
                self.fleet_config = {4: 1, 3: 2, 2: 3, 1: 4}
        else:
            self.fleet_config = dict(fleet_config)

        self.grid: List[List[int]] = [[CELL_EMPTY for _ in range(size)] for _ in range(size)]
        self.ships: List[Ship] = []
        self.shots_history: List[Tuple[int, int, str]] = []  # [(r, c, result)]

    def reset(self):
        self.grid = [[CELL_EMPTY for _ in range(self.size)] for _ in range(self.size)]
        self.ships.clear()
        self.shots_history.clear()

    def get_cell(self, r: int, c: int) -> int:
        if 0 <= r < self.size and 0 <= c < self.size:
            return self.grid[r][c]
        return -1

    def can_place_ship(self, r: int, c: int, size: int, orientation: str) -> bool:
        """
        Проверяет, можно ли поставить корабль заданной длины с координатой носа (r, c).
        Правило: корабль не должен выходить за пределы и не должен касаться других кораблей
        (даже углами/диагоналями) - минимум 1 клетка зазора.
        """
        cells = []
        for i in range(size):
            cr = r if orientation == 'H' else r + i
            cc = c + i if orientation == 'H' else c
            if not (0 <= cr < self.size and 0 <= cc < self.size):
                return False
            cells.append((cr, cc))

        # Проверяем занятость клеток и соседних клеток
        for cr, cc in cells:
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < self.size and 0 <= nc < self.size:
                        # Если клетка занята кораблем (но не нашим будущим)
                        if self.grid[nr][nc] == CELL_SHIP:
                            return False
        return True

    def place_ship(self, r: int, c: int, size: int, orientation: str) -> Optional[Ship]:
        if not self.can_place_ship(r, c, size, orientation):
            return None

        cells = []
        for i in range(size):
            cr = r if orientation == 'H' else r + i
            cc = c + i if orientation == 'H' else c
            cells.append((cr, cc))
            self.grid[cr][cc] = CELL_SHIP

        ship = Ship(size, cells, orientation)
        self.ships.append(ship)
        return ship

    def remove_ship_at(self, r: int, c: int) -> Optional[Ship]:
        """Удаляет корабль, занимающий клетку (r, c)."""
        target_ship = None
        for s in self.ships:
            if (r, c) in s.cells:
                target_ship = s
                break
        if target_ship:
            for cr, cc in target_ship.cells:
                self.grid[cr][cc] = CELL_EMPTY
            self.ships.remove(target_ship)
            return target_ship
        return None

    def auto_place_all(self, max_attempts: int = 500) -> bool:
        """Случайным образом расставляет все корабли согласно fleet_config."""
        for attempt in range(max_attempts):
            self.reset()
            # Формируем список кораблей от больших к маленьким
            needed_ships = []
            for size in sorted(self.fleet_config.keys(), reverse=True):
                for _ in range(self.fleet_config[size]):
                    needed_ships.append(size)

            success = True
            for size in needed_ships:
                placed = False
                # Пробуем случайно найти позицию
                for _ in range(200):
                    orientation = random.choice(['H', 'V'])
                    r = random.randint(0, self.size - 1)
                    c = random.randint(0, self.size - 1)
                    if self.can_place_ship(r, c, size, orientation):
                        self.place_ship(r, c, size, orientation)
                        placed = True
                        break
                if not placed:
                    success = False
                    break

            if success and len(self.ships) == sum(self.fleet_config.values()):
                return True

        return False

    def is_fleet_complete(self) -> bool:
        """Проверяет, расставлены ли все корабли из конфигурации."""
        counts = {}
        for s in self.ships:
            counts[s.size] = counts.get(s.size, 0) + 1
        for size, needed in self.fleet_config.items():
            if counts.get(size, 0) != needed:
                return False
        return True

    def get_remaining_to_place(self) -> Dict[int, int]:
        """Возвращает сколько кораблей каждого размера еще нужно расставить."""
        placed_counts = {}
        for s in self.ships:
            placed_counts[s.size] = placed_counts.get(s.size, 0) + 1

        remaining = {}
        for size, needed in self.fleet_config.items():
            remaining[size] = max(0, needed - placed_counts.get(size, 0))
        return remaining

    def receive_shot(self, r: int, c: int) -> Tuple[str, Optional[Ship], List[Tuple[int, int]]]:
        """
        Принимает выстрел по клетке (r, c).
        Возвращает:
          result: 'invalid', 'already_shot', 'miss', 'hit', 'sunk'
          ship: объект потопленного корабля (если 'sunk'), иначе None
          surrounding_misses: список клеток вокруг потопленного корабля, отмеченных как промах
        """
        if not (0 <= r < self.size and 0 <= c < self.size):
            return 'invalid', None, []

        current_val = self.grid[r][c]
        if current_val in (CELL_MISS, CELL_HIT, CELL_SUNK):
            return 'already_shot', None, []

        surrounding_misses = []

        if current_val == CELL_EMPTY:
            self.grid[r][c] = CELL_MISS
            self.shots_history.append((r, c, 'miss'))
            return 'miss', None, []

        if current_val == CELL_SHIP:
            # Ищем корабль
            hit_ship = None
            for s in self.ships:
                if s.hit(r, c):
                    hit_ship = s
                    break

            if hit_ship and hit_ship.is_sunk:
                # Отмечаем все клетки корабля как потопленные
                for cr, cc in hit_ship.cells:
                    self.grid[cr][cc] = CELL_SUNK

                # Окружающие клетки автоматически становятся промахами
                surrounding = hit_ship.get_surrounding_cells(self.size)
                for sr, sc in surrounding:
                    if self.grid[sr][sc] == CELL_EMPTY:
                        self.grid[sr][sc] = CELL_MISS
                        surrounding_misses.append((sr, sc))

                self.shots_history.append((r, c, 'sunk'))
                return 'sunk', hit_ship, surrounding_misses
            else:
                self.grid[r][c] = CELL_HIT
                self.shots_history.append((r, c, 'hit'))
                return 'hit', None, []

        return 'invalid', None, []

    @property
    def is_all_sunk(self) -> bool:
        if not self.ships:
            return False
        return all(s.is_sunk for s in self.ships)

    def get_view(self, hide_ships: bool = False) -> List[List[int]]:
        """
        Возвращает матрицу поля.
        Если hide_ships=True (Туман войны для соперника):
        клетки CELL_SHIP маскируются под CELL_EMPTY.
        """
        view = []
        for r in range(self.size):
            row = []
            for c in range(self.size):
                val = self.grid[r][c]
                if hide_ships and val == CELL_SHIP:
                    row.append(CELL_EMPTY)
                else:
                    row.append(val)
            view.append(row)
        return view

    def count_alive_ships(self) -> int:
        return sum(1 for s in self.ships if not s.is_sunk)

    def count_alive_by_size(self) -> Dict[int, int]:
        alive = {}
        for s in self.ships:
            if not s.is_sunk:
                alive[s.size] = alive.get(s.size, 0) + 1
        return alive

    @staticmethod
    def coord_to_str(r: int, c: int) -> str:
        """Переводит (3, 2) в человекочитаемый 'В-4'."""
        letter = LETTERS[c] if c < len(LETTERS) else str(c + 1)
        return f"{letter}-{r + 1}"
