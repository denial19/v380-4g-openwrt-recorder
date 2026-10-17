import os
import time
import getpass
import secrets
import socket
import struct
from Crypto.Cipher import AES

DEVICE_ID = int(os.environ['V380_DEVICE_ID'])
RELAY_IP = "127.0.0.1"
PORT = 8800

password = getpass.getpass("Пароль камеры: ")
if not password:
    raise SystemExit("Пустой пароль. Проверка отменена.")

try:
    raw_password = password.encode("ascii")
except UnicodeEncodeError:
    raise SystemExit("Нужен пароль из ASCII-символов.")

if len(raw_password) > 48:
    raise SystemExit("Пароль длиннее 48 байт.")

alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
random_key = bytes(secrets.choice(alphabet) for _ in range(16))

padded = raw_password.ljust(48, b"\x00")
encrypted = AES.new(
    b"macrovideo+*#!^@", AES.MODE_ECB
).encrypt(padded)
encrypted = AES.new(
    random_key, AES.MODE_ECB
).encrypt(encrypted)

credential = random_key + encrypted

packet = bytearray(520)
struct.pack_into("<I", packet, 0, 1167)
struct.pack_into("<I", packet, 4, 1022)
packet[8] = 2
struct.pack_into("<I", packet, 9, 1)
struct.pack_into("<I", packet, 13, DEVICE_ID)

name = f"{DEVICE_ID}.nvdvr.net".encode("ascii")
packet[17:17+len(name)] = name

struct.pack_into("<I", packet, 67, PORT)

username = str(DEVICE_ID).encode("ascii")
packet[71:71+len(username)] = username
packet[103:167] = credential

print(f"Подключение к {RELAY_IP}:{PORT} ...")

try:
    with socket.create_connection(
        (RELAY_IP, PORT), timeout=6
    ) as sock:
        sock.settimeout(8)
        sock.sendall(packet)

        received = bytearray()
        while len(received) < 256:
            try:
                chunk = sock.recv(256 - len(received))
            except socket.timeout:
                break
            if not chunk:
                break
            received.extend(chunk)

    print("Получено байт:", len(received))

    if len(received) < 8:
        print("Авторизация не подтверждена: нет полного ответа")
    else:
        cmd, status = struct.unpack_from("<II", received)

        print("Команда ответа:", cmd)
        print("Код авторизации:", status)

        codes = {
            1001: "Успешная авторизация",
            1011: "Логин или версия протокола отклонены",
            1012: "Неверный пароль",
            1018: "Неверный ID камеры"
        }

        print("Результат:", codes.get(status, "Неизвестный код"))

        if cmd == 1168 and status == 1001 and len(received) >= 21:
            print("Версия устройства:", received[12])
            print("Билет сеанса получен, значение скрыто")

            ticket, session = struct.unpack_from("<II", received, 13)

            request = bytearray(256)
            struct.pack_into("<II", request, 0, 301, 1022)

            host = f"{DEVICE_ID}.nvdvr.net".encode("ascii")
            request[8:8+len(host)] = host

            struct.pack_into(
                "<IIIII", request, 58,
                PORT, DEVICE_ID, ticket, session, 0
            )

            request[78] = 20
            struct.pack_into("<I", request, 79, 1)


            print("[STREAM] Отправляем команду 301 ...")
            try:
                with socket.create_connection(
                    (RELAY_IP, PORT), timeout=6
                ) as s:
                    s.settimeout(6)
                    s.sendall(request)

                    response = bytearray()
                    while len(response) < 16:
                        part = s.recv(16 - len(response))
                        if not part:
                            break
                        response.extend(part)

                    if len(response) < 16:
                        print("[STREAM] Неполный ответ 401")
                    else:
                        s.settimeout(2)

                        while len(response) < 412:
                            try:
                                part = s.recv(412-len(response))
                            except socket.timeout:
                                break
                            if not part:
                                break
                            response.extend(part)

                        cmd, a, b, c = struct.unpack_from(
                            "<Iiii", response
                        )
                        print("[STREAM] Ответ:", cmd, a, b, c)

                        if cmd == 401 and b == 4:
                            cmd303 = bytearray(256)
                            struct.pack_into(
                                "<IH", cmd303, 0, 303, 0x3001
                            )
                            s.sendall(cmd303)
                            print("[STREAM] Команда 303 отправлена")

                            s.settimeout(2)
                            filename = (
                                "/mnt/usb2/V380/recordings/"
                                + time.strftime(
                                    "capture_%Y%m%d_%H%M%S.bin"
                                )
                            )

                            total = 0
                            deadline = time.monotonic() + 25

                            with open(filename, "wb") as out:
                                while (
                                    time.monotonic() < deadline
                                    and total < 12000000
                                ):
                                    try:
                                        data = s.recv(32768)
                                    except socket.timeout:
                                        continue

                                    if not data:
                                        print("[STREAM] Сервер закрыл соединение")
                                        break

                                    out.write(data)
                                    total += len(data)

                            print("[STREAM] Получено байт:", total)
                            print("[STREAM] Файл:", filename)

                            from v380_hevc_decode import decode_capture
                            decode_capture(filename, ticket)
                        else:
                            print("[STREAM] Потоковый сеанс не подтверждён")

            except OSError as e:
                print("[STREAM] Ошибка:",
                      type(e).__name__, str(e))
            except OSError as e:
                print("[STREAM] Ошибка:",
                      type(e).__name__, str(e))

except OSError as e:
    print("Ошибка:", type(e).__name__, str(e))
