"""Serve Video Studio on this computer only.

    python3 -I serve.py            # http://127.0.0.1:4321
    python3 -I serve.py --port 8000

Read-only and local: it binds to 127.0.0.1, answers GET and HEAD only, serves files from this folder and nothing
outside it (no "..", no absolute paths, no symlinks out, no hidden files), never lists directories, and rejects
requests whose Host header is not localhost, so a web page you visit can't use DNS rebinding to read your files.
Standard library only.
"""
import argparse, http.server, mimetypes, os, posixpath, urllib.parse

ROOT = os.path.dirname(os.path.realpath(__file__))
ALLOWED_EXT = {'.html', '.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.wav', '.mp3', '.m4a', '.ogg',
               '.mp4', '.webm', '.mov', '.txt', '.md', '.woff2'}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' blob: data:; media-src 'self' blob: data:; "
       "connect-src 'self' blob: data: https://cdn.jsdelivr.net https://storage.googleapis.com; "
       "worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def resolve(url_path):
    """Map a URL path to a file inside ROOT, or None."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(url_path).path)
    if '\x00' in path or '\\' in path:
        return None
    parts = [p for p in posixpath.normpath('/' + path).split('/') if p]
    if any(p.startswith('.') for p in parts) or (parts and parts[0] == 'tools'):
        return None
    full = os.path.realpath(os.path.join(ROOT, *parts)) if parts else os.path.join(ROOT, 'index.html')
    if os.path.isdir(full):
        full = os.path.join(full, 'index.html')
    if os.path.commonpath([full, ROOT]) != ROOT or full == os.path.realpath(__file__):
        return None
    if os.path.splitext(full)[1].lower() not in ALLOWED_EXT or not os.path.isfile(full):
        return None
    return full


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'VideoStudio'
    sys_version = ''

    def _host_ok(self):
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0].strip('[]').lower()
        return host in ('127.0.0.1', 'localhost', '::1')

    def _send(self, head_only):
        if not self._host_ok():
            return self.send_error(403, 'Host not allowed')
        full = resolve(self.path)
        if not full:
            return self.send_error(404)
        size = os.path.getsize(full)
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        rng = self.headers.get('Range', '')
        start, end = 0, size - 1
        if rng.startswith('bytes=') and ',' not in rng:
            a, _, b = rng[6:].partition('-')
            try:
                if a:
                    start, end = int(a), min(int(b), size - 1) if b else size - 1
                elif b:
                    start = max(0, size - int(b))
            except ValueError:
                return self.send_error(416)
            if start > end or start >= size:
                return self.send_error(416)
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        else:
            self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', CSP)
        self.end_headers()
        if head_only:
            return
        with open(full, 'rb') as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_GET(self):
        self._send(False)

    def do_HEAD(self):
        self._send(True)

    def _deny(self):
        self.send_error(405)

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _deny

    def log_message(self, fmt, *args):  # method and status only: no paths or query strings in the log
        print(f'{self.command} {args[1] if len(args) > 1 else ""}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--port', type=int, default=4321)
    port = ap.parse_args().port
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Video Studio: http://127.0.0.1:{port}  (Ctrl+C to stop; only this computer can reach it)')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
