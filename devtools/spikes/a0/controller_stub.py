"""A0 spike: unix-socket stand-in for the live Controller with a policy gate (autonomy=manual refuses merge)."""
import json, os, socket, sys, time

SOCK, LOG = sys.argv[1], sys.argv[2]
if os.path.exists(SOCK):
    os.unlink(SOCK)
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(SOCK)
srv.listen(4)
while True:
    conn, _ = srv.accept()
    req = json.loads(conn.makefile().readline())
    if req["tool"] == "zplan_status":
        out = {"ok": True, "status": "idle", "token": "PING-7731"}
    elif req["tool"] == "zplan_merge":
        out = {"ok": False, "refused": "autonomy manual: merge needs the owner"}
    else:
        out = {"ok": False, "refused": "unknown tool"}
    with open(LOG, "a") as f:
        f.write(json.dumps({"t": time.time(), "req": req, "out": out}) + "\n")
    conn.sendall((json.dumps(out) + "\n").encode())
    conn.close()
