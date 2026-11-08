#!/usr/bin/env python3
"""
cv-plus PDF renderer via Chrome DevTools Protocol.
Chrome's CLI --print-to-pdf ignores CSS @page size and hard-defaults to US Letter,
so we drive Page.printToPDF directly to force A4.

Usage: cdp_pdf.py [--header=repeat|first-page] [--contact=<file.json>] <input.html> <output.pdf>
Stdlib only (socket websocket client) — no pip deps.

Contact header (repeat mode): read from --contact=<file.json> with keys
name, location, phone, email, linkedin — or from env vars CV_NAME, CV_LOCATION,
CV_PHONE, CV_EMAIL, CV_LINKEDIN. Missing fields are left out.
Chrome path: env CHROME_PATH, else the default macOS location.
"""
import sys, os, json, socket, base64, hashlib, subprocess, time, urllib.request, urllib.parse, struct, html

CHROME = os.environ.get("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PORT = 9223  # dedicated debug port for cv-plus renders

def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr); sys.exit(1)

def ws_connect(url):
    u = urllib.parse.urlparse(url)
    s = socket.create_connection((u.hostname, u.port), timeout=15)
    key = base64.b64encode(os.urandom(16)).decode()
    path = u.path + ("?" + u.query if u.query else "")
    req = (f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
           f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    s.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += s.recv(4096)
    if b"101" not in resp.split(b"\r\n")[0]:
        die(f"websocket handshake failed: {resp[:120]}")
    return s

def ws_send(s, obj):
    data = json.dumps(obj).encode()
    header = bytearray([0x81])  # FIN + text
    mask = os.urandom(4)
    n = len(data)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126); header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127); header += struct.pack(">Q", n)
    header += mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    s.sendall(bytes(header) + masked)

def _recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            die("websocket closed mid-frame")
        buf += chunk
    return buf

def ws_recv(s):
    b0, b1 = _recv_exact(s, 2)
    length = b1 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(s, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(s, 8))[0]
    return _recv_exact(s, length).decode(errors="replace")

def load_contact(path):
    c = {}
    if path:
        with open(path) as f:
            c = json.load(f)
    for k in ("name", "location", "phone", "email", "linkedin"):
        c.setdefault(k, os.environ.get("CV_" + k.upper(), ""))
    return c

def header_html(c):
    e = lambda v: html.escape(v or "")
    line1 = " - ".join(x for x in (e(c["location"]), ("Tel: " + e(c["phone"])) if c["phone"] else "") if x)
    parts2 = []
    if c["email"]:
        parts2.append(e(c["email"]))
    if c["linkedin"]:
        parts2.append(f'<a href="{e(c["linkedin"])}" style="color:#000;">LinkedIn</a>')
    line2 = " &bull; ".join(parts2)
    return (
        '<div style="width:100%; text-align:center; font-family:Helvetica,Arial,sans-serif; '
        'color:#000; margin:0 20mm; -webkit-print-color-adjust:exact;">'
        f'<div style="font-size:14pt; font-weight:bold; margin-bottom:2pt;">{e(c["name"])}</div>'
        + (f'<div style="font-size:10.5pt; line-height:1.35;">{line1}</div>' if line1 else "")
        + (f'<div style="font-size:10.5pt; line-height:1.35;">{line2}</div>' if line2 else "")
        + '</div>'
    )

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if len(args) != 2:
        die("usage: cdp_pdf.py [--header=repeat|first-page] [--contact=<file.json>] <input.html> <output.pdf>")
    inp, outp = args
    header_mode = "repeat"
    contact_path = None
    for f in flags:
        if f.startswith("--header="):
            header_mode = f.split("=", 1)[1]
        elif f.startswith("--contact="):
            contact_path = f.split("=", 1)[1]
    if header_mode not in ("repeat", "first-page"):
        die("--header must be 'repeat' or 'first-page'")
    if not os.path.isfile(inp):
        die(f"input HTML not found: {inp}")
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)

    file_url = "file://" + urllib.parse.quote(os.path.abspath(inp))
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={PORT}",
         "--no-first-run", "--no-default-browser-check", file_url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]; break
            except Exception:
                pass
            time.sleep(0.2)
        if not ws_url:
            die("could not reach Chrome DevTools endpoint")

        s = ws_connect(ws_url)
        ws_send(s, {"id": 1, "method": "Page.enable"})
        time.sleep(1.2)  # let fonts/layout settle

        # Repeating name/contact header (appears on every page). Name 14pt, details 10.5pt.
        header_tpl = header_html(load_contact(contact_path))
        footer_tpl = '<div style="font-size:1px;">&nbsp;</div>'  # suppress Chrome's default footer

        # A4 = 8.27 x 11.69 in. Generous margins so it breathes:
        # top 1.30" (header band + gap), bottom 0.75", sides 0.80" (~20mm).
        # header_mode "first-page": the contact block lives in the HTML body (page 1 only),
        # so Chrome's repeating print header is switched off and the top margin tightened.
        # Parse-safety measure for channels A and B: a duplicate contact block on every page
        # lands in the text layer mid-document and confuses ATS section detection.
        # "repeat" is the default (channel C).
        params = {
            "paperWidth": 8.27, "paperHeight": 11.69,
            "marginTop": 1.30 if header_mode == "repeat" else 0.75,
            "marginBottom": 0.75,
            "marginLeft": 0.80, "marginRight": 0.80,
            "printBackground": True, "preferCSSPageSize": False,
            "displayHeaderFooter": header_mode == "repeat",
        }
        if header_mode == "repeat":
            params["headerTemplate"] = header_tpl
            params["footerTemplate"] = footer_tpl
        ws_send(s, {"id": 2, "method": "Page.printToPDF", "params": params})
        pdf_b64 = None
        for _ in range(200):
            msg = json.loads(ws_recv(s))
            if msg.get("id") == 2:
                if "error" in msg:
                    die(f"printToPDF failed: {msg['error']}")
                pdf_b64 = msg["result"]["data"]; break
        if not pdf_b64:
            die("no PDF returned")
        with open(outp, "wb") as f:
            f.write(base64.b64decode(pdf_b64))
        print(f"OK: {outp}")
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

if __name__ == "__main__":
    main()
