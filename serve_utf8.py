import http.server
import socketserver

class Handler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        # Принудительно отдаем .md и .txt как UTF-8
        if path.endswith(('.md', '.txt', '.json', '.py', '.sh')):
            return 'text/plain; charset=utf-8'
        return super().guess_type(path)

PORT = 8888
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving at port {PORT}")
    httpd.serve_forever()
