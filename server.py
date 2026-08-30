import hashlib
import json
import re
import socket
import threading
from protocol import encode, decode, response

HOST = "0.0.0.0"
PORT = 8888
ACCOUNT_FILE = "accounts.json"

clients = {}
accounts = {}
bucket_list = []
next_item_id = 1
lock = threading.Lock()

def load_accounts():
    global accounts
    try:
        with open(ACCOUNT_FILE, "r", encoding="utf-8") as file:
            accounts = json.load(file)
    except FileNotFoundError:
        accounts = {}

def save_accounts():
    with open(ACCOUNT_FILE, "w", encoding="utf-8") as file:
        json.dump(accounts, file, ensure_ascii=False, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def valid_username(username):
    return bool(re.fullmatch(r"[A-Za-z0-9_]{3,20}", username))

def valid_password(password):
    return len(password) >= 4

def send(conn, message):
    conn.sendall(encode(message))

def broadcast(message, exclude=None):
    with lock:
        connections = list(clients.keys())
    for conn in connections:
        if conn is not exclude:
            try:
                send(conn, message)
            except OSError:
                pass

def parse_add(command_text):
    match = re.fullmatch(r'/add\s+"([^"]+)"(?:\s+"([^"]*)")?', command_text, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2)
    match = re.fullmatch(r'/add\s+(\S+)(?:\s+"([^"]*)")?', command_text, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2)
    return None, None

def handle_client(conn, address):
    global next_item_id
    username = None
    print(f"[CONNECT] {address[0]}:{address[1]}")
    try:
        reader = conn.makefile("rb")
        for line in reader:
            request = {}
            try:
                request = decode(line)
                command = str(request.get("request", "")).upper()
                payload = request.get("payload", {})

                if command == "REGISTER":
                    name = str(payload.get("username", "")).strip()
                    password = str(payload.get("password", ""))
                    if not valid_username(name):
                        send(conn, response(400, command, {"message": "Username must be 3-20 characters using letters, numbers, or underscore"}))
                        continue
                    if not valid_password(password):
                        send(conn, response(400, command, {"message": "Password must contain at least 4 characters"}))
                        continue
                    with lock:
                        if name in accounts:
                            send(conn, response(409, command, {"message": "Username already exists"}))
                            continue
                        accounts[name] = hash_password(password)
                        save_accounts()
                    send(conn, response(201, command, {"message": "Account created", "username": name}))

                elif command == "AUTH":
                    if username is not None:
                        send(conn, response(409, command, {"message": "Already authenticated"}))
                        continue
                    name = str(payload.get("username", "")).strip()
                    password = str(payload.get("password", ""))
                    with lock:
                        stored_hash = accounts.get(name)
                    if stored_hash is None:
                        send(conn, response(404, command, {"message": "Account not found"}))
                        continue
                    if hash_password(password) != stored_hash:
                        send(conn, response(401, command, {"message": "Wrong password"}))
                        continue
                    with lock:
                        if name in clients.values():
                            send(conn, response(409, command, {"message": "Account is already logged in"}))
                            continue
                        clients[conn] = name
                        username = name
                    send(conn, response(200, command, {"message": "Authentication successful", "username": username}))
                    broadcast(response(200, "USER_JOINED", {"username": username}), exclude=conn)

                elif command == "LIST":
                    if username is None:
                        send(conn, response(401, command, {"message": "Authenticate first"}))
                        continue
                    with lock:
                        items = list(bucket_list)
                    send(conn, response(200, command, {"items": items}))

                elif command == "VIEW":
                    if username is None:
                        send(conn, response(401, command, {"message": "Authenticate first"}))
                        continue
                    try:
                        item_id = int(payload.get("id"))
                    except (TypeError, ValueError):
                        send(conn, response(400, command, {"message": "Invalid item ID"}))
                        continue
                    with lock:
                        item = next((item for item in bucket_list if item["id"] == item_id), None)
                    if item is None:
                        send(conn, response(404, command, {"message": "Bucket-list item not found"}))
                    else:
                        send(conn, response(200, command, {"item": item}))

                elif command == "ADD":
                    if username is None:
                        send(conn, response(401, command, {"message": "Authenticate first"}))
                        continue
                    title = str(payload.get("title", "")).strip()
                    description = payload.get("description")
                    if not title:
                        send(conn, response(400, command, {"message": "Item title is required"}))
                        continue
                    if description is not None:
                        description = str(description).strip()
                        if description == "":
                            description = None
                    with lock:
                        item = {
                            "id": next_item_id,
                            "title": title,
                            "description": description,
                            "added_by": username
                        }
                        next_item_id += 1
                        bucket_list.append(item)
                    send(conn, response(201, command, {"item": item}))
                    broadcast(response(200, "ITEM_ADDED", {"item": item}), exclude=conn)

                elif command == "REMOVE":
                    if username is None:
                        send(conn, response(401, command, {"message": "Authenticate first"}))
                        continue
                    try:
                        item_id = int(payload.get("id"))
                    except (TypeError, ValueError):
                        send(conn, response(400, command, {"message": "Invalid item ID"}))
                        continue
                    with lock:
                        item = next((item for item in bucket_list if item["id"] == item_id), None)
                        if item is None:
                            send(conn, response(404, command, {"message": "Bucket-list item not found"}))
                            continue
                        bucket_list.remove(item)
                    send(conn, response(200, command, {"message": "Item removed", "item": item}))
                    broadcast(response(200, "ITEM_REMOVED", {"item": item}), exclude=conn)

                elif command == "EDIT":
                    if username is None:
                        send(conn, response(401, command, {"message": "Authenticate first"}))
                        continue
                    try:
                        item_id = int(payload.get("id"))
                    except (TypeError, ValueError):
                        send(conn, response(400, command, {"message": "Invalid item ID"}))
                        continue
                    new_title = payload.get("title")
                    new_description = payload.get("description")
                    with lock:
                        item = next((item for item in bucket_list if item["id"] == item_id), None)
                        if item is None:
                            send(conn, response(404, command, {"message": "Bucket-list item not found"}))
                            continue
                        if new_title is not None:
                            new_title = str(new_title).strip()
                            if not new_title:
                                send(conn, response(400, command, {"message": "Title cannot be empty"}))
                                continue
                            item["title"] = new_title
                        if new_description is not None:
                            new_description = str(new_description).strip()
                            item["description"] = new_description if new_description else None
                        updated = dict(item)
                    send(conn, response(200, command, {"message": "Item updated", "item": updated}))
                    broadcast(response(200, "ITEM_UPDATED", {"item": updated}), exclude=conn)

                elif command == "USERS":
                    if username is None:
                        send(conn, response(401, command, {"message": "Authenticate first"}))
                        continue
                    with lock:
                        users = list(clients.values())
                    send(conn, response(200, command, {"users": users}))

                elif command == "CLEAR":
                    if username is None:
                        send(conn, response(401, command, {"message": "Authenticate first"}))
                        continue
                    with lock:
                        removed = list(bucket_list)
                        bucket_list.clear()
                    send(conn, response(200, command, {"message": "Bucket list cleared", "removed": removed}))
                    broadcast(response(200, "LIST_CLEARED", {"by": username}), exclude=conn)

                elif command == "QUIT":
                    send(conn, response(200, command, {"message": "Goodbye"}))
                    break

                else:
                    send(conn, response(400, command or "UNKNOWN", {"message": "Unknown request"}))

            except (json.JSONDecodeError, UnicodeDecodeError):
                send(conn, response(400, "UNKNOWN", {"message": "Invalid JSON message"}))
            except Exception as exc:
                send(conn, response(500, request.get("request", "UNKNOWN"), {"message": str(exc)}))

    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        with lock:
            old_username = clients.pop(conn, None)
        try:
            conn.close()
        except OSError:
            pass
        if old_username:
            broadcast(response(200, "USER_LEFT", {"username": old_username}))
            print(f"[DISCONNECT] {old_username}")
        else:
            print(f"[DISCONNECT] {address[0]}:{address[1]}")

def main():
    load_accounts()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    print(f"Bucket List Server running on {HOST}:{PORT}")
    try:
        while True:
            conn, address = server.accept()
            threading.Thread(target=handle_client, args=(conn, address), daemon=True).start()
    except KeyboardInterrupt:
        print("\nServer stopped")
    finally:
        server.close()

if __name__ == "__main__":
    main()
