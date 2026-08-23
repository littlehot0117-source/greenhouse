import http.server
import socketserver
import json
import os
import urllib.parse
import mimetypes
import socket
from datetime import datetime

import database
import report_generator

PORT = int(os.environ.get("PORT", 8000))
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(PROJECT_DIR, "web")

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


class GreenhouseAPIRequestHandler(http.server.BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # 覆寫日誌，在終端機輸出簡潔的連線訊息
        print(f"[{self.log_date_time_string()}] {self.command} {self.path} - {args[1]}")

    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_error_response(self, message, status=400):
        self.send_json_response({"success": False, "error": message}, status)

    def do_OPTIONS(self):
        # 支援 CORS (跨來源資源共用)，方便開發測試
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # --- API 路由分發 ---
        if path == "/api/greenhouses":
            try:
                data = database.get_greenhouses()
                self.send_json_response(data)
            except Exception as e:
                self.send_error_response(str(e), 500)
                
        elif path == "/api/items":
            try:
                data = database.get_items()
                self.send_json_response(data)
            except Exception as e:
                self.send_error_response(str(e), 500)
                
        elif path == "/api/transactions":
            try:
                gh_id = query_params.get('greenhouse_id', [None])[0]
                item_id = query_params.get('item_id', [None])[0]
                tx_type = query_params.get('transaction_type', [None])[0]
                start_date = query_params.get('start_date', [None])[0]
                end_date = query_params.get('end_date', [None])[0]
                limit = int(query_params.get('limit', [100])[0])
                
                data = database.get_transactions(
                    greenhouse_id=int(gh_id) if gh_id else None,
                    item_id=int(item_id) if item_id else None,
                    transaction_type=tx_type,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit
                )
                self.send_json_response(data)
            except Exception as e:
                self.send_error_response(str(e), 500)
                
        elif path == "/api/stock":
            try:
                gh_id = query_params.get('greenhouse_id', [None])[0]
                if not gh_id:
                    self.send_error_response("缺少 greenhouse_id 參數")
                    return
                data = database.get_greenhouse_stock(int(gh_id))
                self.send_json_response(data)
            except Exception as e:
                self.send_error_response(str(e), 500)
                
        elif path == "/api/report":
            try:
                year = query_params.get('year', [None])[0]
                month = query_params.get('month', [None])[0]
                if not year or not month:
                    self.send_error_response("缺少 year 或 month 參數")
                    return
                data = database.get_monthly_report_data(year, month)
                self.send_json_response(data)
            except Exception as e:
                self.send_error_response(str(e), 500)
                
        elif path == "/api/report/download":
            try:
                year = query_params.get('year', [None])[0]
                month = query_params.get('month', [None])[0]
                if not year or not month:
                    self.send_error_response("缺少 year 或 month 參數")
                    return
                
                # 產出 Excel
                file_path = report_generator.generate_monthly_report(year, month)
                
                if os.path.exists(file_path):
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    # 設定下載檔名 (編碼避免中文亂碼)
                    encoded_filename = urllib.parse.quote(os.path.basename(file_path))
                    self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{encoded_filename}")
                    self.send_header('Content-Length', os.path.getsize(file_path))
                    self.end_headers()
                    
                    with open(file_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_error_response("產出 Excel 報表失敗", 500)
            except Exception as e:
                self.send_error_response(str(e), 500)

        # --- 靜態檔案服務 ---
        else:
            # 去除前導斜線，並將 root `/` 指向 index.html
            local_path = path.lstrip('/')
            if local_path == "" or local_path == "index.html":
                file_to_serve = os.path.join(WEB_DIR, "index.html")
            else:
                # 限制只能存取 web 檔案夾底下的檔案，防路徑穿越漏洞
                safe_path = os.path.abspath(os.path.join(WEB_DIR, local_path))
                if safe_path.startswith(WEB_DIR) and os.path.isfile(safe_path):
                    file_to_serve = safe_path
                else:
                    file_to_serve = None

            if file_to_serve and os.path.exists(file_to_serve):
                self.send_response(200)
                mime_type, _ = mimetypes.guess_type(file_to_serve)
                self.send_header('Content-Type', mime_type or 'application/octet-stream')
                self.send_header('Content-Length', os.path.getsize(file_to_serve))
                self.end_headers()
                with open(file_to_serve, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                # 若靜態檔案不存在，返回 404
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write("<h3>頁面不存在 404 Not Found</h3>".encode('utf-8'))

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        # 讀取請求內文
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            payload = json.loads(post_data) if post_data else {}
        except json.JSONDecodeError:
            self.send_error_response("請求格式非有效 JSON")
            return

        if path == "/api/greenhouses":
            name = payload.get('name')
            if not name:
                self.send_error_response("溫室名稱不能為空")
                return
            res = database.add_greenhouse(name)
            self.send_json_response(res)
            
        elif path == "/api/items":
            name = payload.get('name')
            sku = payload.get('sku')
            unit = payload.get('unit')
            description = payload.get('description')
            category = payload.get('category', '物品類')
            
            if not name or not unit:
                self.send_error_response("品項名稱與單位不能為空")
                return
            res = database.add_item(name, sku, unit, description, category)
            self.send_json_response(res)
            
        elif path == "/api/transactions":
            gh_id = payload.get('greenhouse_id')
            item_id = payload.get('item_id')
            tx_type = payload.get('transaction_type')
            quantity = payload.get('quantity')
            operator = payload.get('operator')
            note = payload.get('note')
            created_at = payload.get('created_at') # 格式 YYYY-MM-DD HH:MM:SS
            
            if not gh_id or not item_id or not tx_type or quantity is None or not operator:
                self.send_error_response("缺少必填的交易欄位")
                return
            if tx_type not in ['IN', 'OUT']:
                self.send_error_response("交易類型必須為 IN 或 OUT")
                return
            if quantity <= 0:
                self.send_error_response("登記數量必須大於 0")
                return
                
            res = database.add_transaction(
                greenhouse_id=int(gh_id),
                item_id=int(item_id),
                transaction_type=tx_type,
                quantity=float(quantity),
                operator=operator,
                note=note,
                created_at=created_at if created_at else None
            )
            self.send_json_response(res)
            
        else:
            self.send_error_response("無效的 API 端點", 404)

    def do_PUT(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            payload = json.loads(post_data) if post_data else {}
        except json.JSONDecodeError:
            self.send_error_response("請求格式非有效 JSON")
            return

        if path == "/api/items":
            item_id = query_params.get('id', [None])[0]
            if not item_id:
                self.send_error_response("缺少品項 id 參數")
                return
                
            name = payload.get('name')
            sku = payload.get('sku')
            unit = payload.get('unit')
            description = payload.get('description')
            category = payload.get('category', '物品類')
            
            if not name or not unit:
                self.send_error_response("品項名稱與單位不能為空")
                return
                
            res = database.update_item(int(item_id), name, sku, unit, description, category)
            self.send_json_response(res)
        elif path == "/api/transactions":
            tx_id = query_params.get('id', [None])[0]
            if not tx_id:
                self.send_error_response("缺少交易 id 參數")
                return
            gh_id = payload.get('greenhouse_id')
            item_id = payload.get('item_id')
            tx_type = payload.get('transaction_type')
            quantity = payload.get('quantity')
            operator = payload.get('operator')
            note = payload.get('note')
            created_at = payload.get('created_at')
            
            if not gh_id or not item_id or not tx_type or quantity is None or not operator or not created_at:
                self.send_error_response("缺少必填的交易修改欄位")
                return
            res = database.update_transaction(
                tx_id=int(tx_id),
                greenhouse_id=int(gh_id),
                item_id=int(item_id),
                transaction_type=tx_type,
                quantity=float(quantity),
                operator=operator,
                note=note,
                created_at=created_at
            )
            self.send_json_response(res)
        else:
            self.send_error_response("無效的 API 端點", 404)

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        if path == "/api/items":
            item_id = query_params.get('id', [None])[0]
            if not item_id:
                self.send_error_response("缺少品項 id 參數")
                return
            res = database.delete_item(int(item_id))
            self.send_json_response(res)
        elif path == "/api/transactions":
            tx_id = query_params.get('id', [None])[0]
            if not tx_id:
                self.send_error_response("缺少交易 id 參數")
                return
            res = database.delete_transaction(int(tx_id))
            self.send_json_response(res)
        else:
            self.send_error_response("無效的 API 端點", 404)

def run_server():
    # 啟動前先初始化資料庫
    database.init_db()
    
    # 註冊自訂 Mime Type 確保瀏覽器能正確解讀 HTML/CSS/JS
    mimetypes.add_type("text/html", ".html")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/javascript", ".js")
    
    handler = GreenhouseAPIRequestHandler
    # 使用 ThreadingHTTPServer 支援多執行緒，防止瀏覽器多次並行請求時伺服器卡住
    # 但為了與 Python 3.7+ 的 BaseHTTPServer 相容，可以使用內建模組
    # 在 Python 3.7 中，ThreadingHTTPServer 被引入 http.server
    try:
        server_class = http.server.ThreadingHTTPServer
    except AttributeError:
        server_class = socketserver.TCPServer
        # 允許連接埠重用
        server_class.allow_reuse_address = True
        
    with server_class(("", PORT), handler) as httpd:
        local_ip = get_local_ip()
        print("==================================================")
        print(f" 溫室智慧庫存管理系統已啟動！")
        print(f" 本地網頁存取網址: http://localhost:{PORT}")
        print(f" 手機/其他裝置存取網址: http://{local_ip}:{PORT}")
        print(" (注意：手機與電腦必須連接同一個 Wi-Fi 網路)")
        print("==================================================")
        print("請保持此視窗開啟以維持系統運作...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n伺服器正常關閉中...")

if __name__ == "__main__":
    run_server()
