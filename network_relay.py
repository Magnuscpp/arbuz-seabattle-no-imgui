# -*- coding: utf-8 -*-
"""
network_relay.py - Сетевой менеджер мультиплеера через открытый облачный MQTT брокер.
Позволяет играть между ПК и мобильным телефоном без использования локальных IP-адресов.
Телефон открывает веб-страницу на GitHub Pages, сканируя QR-код с кодом комнаты.
"""

import json
import random
import string
import threading
import time
from typing import Callable, Optional, Tuple
from PIL import Image
import paho.mqtt.client as mqtt
import qrcode

# Открытые публичные брокеры с поддержкой WSS для браузеров (GitHub Pages)
PRIMARY_BROKER = "broker.hivemq.com"
PRIMARY_PORT = 1883
PRIMARY_WSS_PORT = 8884

FALLBACK_BROKER = "broker.emqx.io"
FALLBACK_PORT = 1883
FALLBACK_WSS_PORT = 8084


def generate_room_code(length: int = 5) -> str:
    """Генерирует короткий легко читаемый код комнаты из цифр и заглавных латинских букв."""
    chars = string.ascii_uppercase + string.digits
    # Исключаем похожие символы (0, O, 1, I) для удобства ручного ввода
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    return ''.join(random.choices(chars, k=length))


class NetworkRelay:
    def __init__(self, github_pages_url: str = "https://magnuscpp.github.io/arbuz-seabattle/"):
        self.github_pages_url = github_pages_url.rstrip('/') + '/'
        self.room_code = generate_room_code()
        self.client: Optional[mqtt.Client] = None
        self.is_connected = False
        self.is_phone_connected = False
        self.last_phone_seen = 0.0
        self.last_phone_seen = 0.0

        # Коллбеки для GUI
        self.on_phone_connected: Optional[Callable[[], None]] = None
        self.on_phone_disconnected: Optional[Callable[[], None]] = None
        self.on_phone_ready: Optional[Callable[[dict], None]] = None
        self.on_phone_shot: Optional[Callable[[int, int], None]] = None
        self.on_defense_result: Optional[Callable[[dict], None]] = None
        self.on_phone_restart: Optional[Callable[[], None]] = None
        self.on_phone_left: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        self._lock = threading.Lock()

    def set_github_pages_url(self, url: str):
        cleaned = (url or "").strip()
        if cleaned:
            self.github_pages_url = cleaned.rstrip('/') + '/'

    def get_join_url(self) -> str:
        """Возвращает готовую ссылку для подключения телефона к текущей комнате."""
        return f"{self.github_pages_url}?room={self.room_code}"

    def generate_qr_texture_data(self, box_size: int = 6, border: int = 2) -> Tuple[int, int, list]:
        """
        Генерирует QR-код для ссылки подключения и возвращает (width, height, normalized_rgba_floats)
        для загрузки в текстуру Dear PyGui.
        """
        url = self.get_join_url()
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        width, height = img.size
        # Dear PyGui требует список float [0.0 .. 1.0] RGBA
        raw_bytes = img.tobytes()
        float_data = [b / 255.0 for b in raw_bytes]
        return width, height, float_data

    def start(self, new_room_code: Optional[str] = None):
        """Подключается к MQTT брокеру и подписывается на сообщения от телефона."""
        if new_room_code:
            self.room_code = new_room_code

        self.stop()

        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect

            # Подключаемся с таймаутом
            try:
                self.client.connect(PRIMARY_BROKER, PRIMARY_PORT, 20)
            except Exception:
                # Резервный брокер
                self.client.connect(FALLBACK_BROKER, FALLBACK_PORT, 20)

            self.client.loop_start()
        except Exception as e:
            print(f"[NetworkRelay] Ошибка подключения к брокеру: {e}")
            if self.on_error:
                self.on_error(str(e))

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.is_connected = True
            # Канал входящих сообщений от телефона для этой комнаты
            topic = f"seabattle/rooms/{self.room_code}/pc"
            client.subscribe(topic, qos=1)
            # Отправляем сообщение о готовности хоста
            self.send_to_phone({"action": "host_ready", "room": self.room_code})
        else:
            self.is_connected = False

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.is_connected = False

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            action = payload.get("action")
            self.last_phone_seen = time.monotonic()

            if action == "phone_join":
                self.is_phone_connected = True
                # Отвечаем подтверждением и параметрами комнаты
                self.send_to_phone({"action": "join_accepted", "room": self.room_code})
                if self.on_phone_connected:
                    self.on_phone_connected()

            elif action == "heartbeat":
                if not self.is_phone_connected:
                    self.is_phone_connected = True
                    if self.on_phone_connected:
                        self.on_phone_connected()

            elif action == "phone_leave":
                self.is_phone_connected = False
                self.last_phone_seen = 0.0
                if self.on_phone_left:
                    self.on_phone_left()

            elif action == "ping":
                self.send_to_phone({"action": "pong"})

            elif action == "ready":
                if self.on_phone_ready:
                    self.on_phone_ready(payload)

            elif action == "shot":
                r = payload.get("r", 0)
                c = payload.get("c", 0)
                if self.on_phone_shot:
                    self.on_phone_shot(r, c)

            elif action == "defense_result":
                if self.on_defense_result:
                    self.on_defense_result(payload)

            elif action == "restart":
                if self.on_phone_restart:
                    self.on_phone_restart()

        except Exception as e:
            print(f"[NetworkRelay] Ошибка обработки сообщения: {e}")

    def send_to_phone(self, data: dict):
        """Отправляет JSON данные на телефон через топик комнаты."""
        if not self.client:
            return
        topic = f"seabattle/rooms/{self.room_code}/phone"
        try:
            msg = json.dumps(data)
            self.client.publish(topic, msg, qos=1)
        except Exception as e:
            print(f"[NetworkRelay] Ошибка отправки: {e}")

    def stop(self):
        """Останавливает сетевой клиент."""
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
            self.client = None
        self.is_connected = False
        self.is_phone_connected = False
        self.last_phone_seen = 0.0
