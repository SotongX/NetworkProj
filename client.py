import json
import shlex
import socket
import sys
import threading

DEFAULT_HOST = "127.0.0.1"
PORT = 8888

def send_request(sock, request, payload=None):
    message = {"request": request, "payload": payload or {}}
    sock.sendall((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))

def receiver(sock, stop_event):
    reader = sock.makefile("rb")
    try:
        for line in reader:
            message = json.loads(line.decode("utf-8"))
            print(f"\n[{message.get('status')} {message.get('phrase')}] {message.get('request')}")
            payload = message.get("payload", {})
            if payload:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            print("> ", end="", flush=True)
    except (ConnectionResetError, BrokenPipeError, OSError, json.JSONDecodeError):
        pass
    finally:
        stop_event.set()

def main():
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, PORT))
    stop_event = threading.Event()
    threading.Thread(target=receiver, args=(sock, stop_event), daemon=True).start()

    print("Collaborative Bucket List")
    print("Commands:")
    print("/register USERNAME PASSWORD")
    print("/auth USERNAME PASSWORD")
    print('/add "ITEM" "OPTIONAL DESCRIPTION"')
    print('/add "ITEM"')
    print("/list")
    print("/view ID")
    print('/edit ID "NEW TITLE" "NEW DESCRIPTION"')
    print("/remove ID")
    print("/clear")
    print("/users")
    print("/quit")

    try:
        while not stop_event.is_set():
            text = input("> ").strip()
            if not text:
                continue

            try:
                parts = shlex.split(text)
            except ValueError:
                print("Invalid command syntax")
                continue

            command = parts[0].lower()

            if command == "/register" and len(parts) == 3:
                send_request(sock, "REGISTER", {"username": parts[1], "password": parts[2]})

            elif command == "/auth" and len(parts) == 3:
                send_request(sock, "AUTH", {"username": parts[1], "password": parts[2]})

            elif command == "/add" and 2 <= len(parts) <= 3:
                payload = {"title": parts[1]}
                if len(parts) == 3:
                    payload["description"] = parts[2]
                send_request(sock, "ADD", payload)

            elif command == "/list" and len(parts) == 1:
                send_request(sock, "LIST")

            elif command == "/view" and len(parts) == 2:
                try:
                    send_request(sock, "VIEW", {"id": int(parts[1])})
                except ValueError:
                    print("ID must be a number")

            elif command == "/edit" and len(parts) == 4:
                try:
                    send_request(sock, "EDIT", {"id": int(parts[1]), "title": parts[2], "description": parts[3]})
                except ValueError:
                    print("ID must be a number")

            elif command == "/remove" and len(parts) == 2:
                try:
                    send_request(sock, "REMOVE", {"id": int(parts[1])})
                except ValueError:
                    print("ID must be a number")

            elif command == "/clear" and len(parts) == 1:
                send_request(sock, "CLEAR")

            elif command == "/users" and len(parts) == 1:
                send_request(sock, "USERS")

            elif command == "/quit" and len(parts) == 1:
                send_request(sock, "QUIT")
                break

            else:
                print("Invalid command or arguments")

    except (KeyboardInterrupt, EOFError):
        try:
            send_request(sock, "QUIT")
        except OSError:
            pass
    finally:
        sock.close()

if __name__ == "__main__":
    main()
