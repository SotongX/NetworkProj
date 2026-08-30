import json

STATUS_PHRASES = {
    200: "OK",
    201: "CREATED",
    202: "ACCEPTED",
    204: "NO_CONTENT",
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "UNPROCESSABLE_ENTITY",
    500: "INTERNAL_SERVER_ERROR",
}

def response(status, request, payload=None):
    return {
        "status": status,
        "phrase": STATUS_PHRASES[status],
        "request": request,
        "payload": payload or {}
    }

def encode(message):
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")

def decode(line):
    return json.loads(line.decode("utf-8"))
