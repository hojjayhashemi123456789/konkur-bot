# ==============================================================================
# 🌐 KEEP-ALIVE & ANTI-SLEEP SERVER (ضد خاموشی ۲۴ ساعته برای رندر و هاست‌های ابری)
# ==============================================================================
import time
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

HTML_STATUS_PAGE = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>ربات انتخاب رشته کنکور - وضعیت ۲۴ ساعته</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; text-align: center; padding-top: 60px; margin: 0; }
        .card { background: #1e293b; max-width: 520px; margin: 0 auto; padding: 30px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid #334155; }
        .status-badge { display: inline-block; background: #10b981; color: white; padding: 6px 16px; border-radius: 20px; font-weight: bold; margin-bottom: 20px; font-size: 14px; }
        h1 { color: #38bdf8; font-size: 22px; margin-bottom: 12px; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.6; }
        .tag { font-family: monospace; background: #334155; padding: 2px 6px; border-radius: 4px; color: #f1f5f9; }
    </style>
</head>
<body>
    <div class="card">
        <div class="status-badge">● ۲۴ ساعته آنلاین و فعال (Active 24/7)</div>
        <h1>ربات تلگرام انتخاب رشته کنکور</h1>
        <p>وب‌سرور پایدارساز و سیستم ضد خاموشی خودکار (<span class="tag">Keep-Alive</span>) با موفقیت در حال اجرا است.</p>
        <p style="margin-top: 15px; font-size: 12px; color: #64748b;">Render Sleep Preventer & Health Monitor Active</p>
    </div>
</body>
</html>"""

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_STATUS_PAGE.strip().encode("utf-8"))

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_keep_alive_server(port):
    try:
        server_address = ("0.0.0.0", port)
        httpd = HTTPServer(server_address, KeepAliveHandler)
        print(f"🌐 [Keep-Alive] وب‌سرور پایش روی پورت {port} فعال شد.")
        httpd.serve_forever()
    except Exception as e:
        print(f"⚠️ [Keep-Alive] وب‌سرور: {e}")

def auto_pinger_loop():
    time.sleep(30)
    while True:
        url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("APP_URL")
        now_str = time.strftime("%H:%M:%S")
        if url:
            try:
                if not url.startswith("http"):
                    url = "https://" + url
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (RenderKeepAlive/1.0)"}
                )
                with urllib.request.urlopen(req, timeout=20) as response:
                    if response.status == 200:
                        print(f"💓 [Keep-Alive] پینگ خودکار موفق به {url} در {now_str}")
            except Exception as e:
                print(f"⚠️ [Keep-Alive] وضعیت پینگ: {e}")
        time.sleep(600)

def start_keep_alive():
    port = int(os.environ.get("PORT", 10000))
    t1 = threading.Thread(target=run_keep_alive_server, args=(port,), daemon=True)
    t1.start()
    t2 = threading.Thread(target=auto_pinger_loop, daemon=True)
    t2.start()
