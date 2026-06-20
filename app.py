#!/usr/bin/env python3
"""
VixSrc M3U8 Extractor v6 - Con proxy relay per streaming
"""

import os
import sys
import asyncio
from flask import Flask, request, jsonify, render_template_string, Response, stream_with_context
import requests as req_lib

app = Flask(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# === WEBSHARE CONFIG ===
PROXY_HOST = os.environ.get("WEBSHARE_HOST", "p.webshare.io")
PROXY_PORT = os.environ.get("WEBSHARE_PORT", "80")
PROXY_USER = os.environ.get("WEBSHARE_USER", "")
PROXY_PASS = os.environ.get("WEBSHARE_PASS", "")

def get_proxy_config():
    """Config proxy per Playwright"""
    if PROXY_USER and PROXY_PASS:
        return {
            "server": f"http://{PROXY_HOST}:{PROXY_PORT}",
            "username": PROXY_USER,
            "password": PROXY_PASS,
        }
    return None

def get_requests_proxies():
    """Config proxy per requests"""
    if PROXY_USER and PROXY_PASS:
        proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
        return {"http": proxy_url, "https": proxy_url}
    return None


async def extract_playlist_url(movie_url):
    playlist_urls = []

    from playwright.async_api import async_playwright

    proxy = get_proxy_config()

    async with async_playwright() as p:
        launch_args = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        }
        if proxy:
            launch_args["proxy"] = proxy
            print(f"[*] Proxy attivo: {proxy['server']}")
        else:
            print("[!] Nessun proxy configurato")

        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        async def handle_request(req):
            url = req.url
            if "/playlist/" in url and "vixsrc.to" in url:
                if url not in playlist_urls:
                    playlist_urls.append(url)
                    print(f"[+] PLAYLIST: {url}")
            if "playlist" in url and "m3u8" in url:
                if url not in playlist_urls:
                    playlist_urls.append(url)
                    print(f"[+] M3U8: {url}")

        async def handle_response(resp):
            url = resp.url
            if "/playlist/" in url and "vixsrc.to" in url:
                if url not in playlist_urls:
                    playlist_urls.append(url)
                    print(f"[+] PLAYLIST (resp): {url}")

        page.on("request", handle_request)
        page.on("response", handle_response)

        print(f"[*] Caricamento: {movie_url}")
        try:
            await page.goto(movie_url, wait_until="networkidle", timeout=30000)
            for i in range(15):
                await asyncio.sleep(1)
                if playlist_urls:
                    print(f"   [+] Trovati {len(playlist_urls)} link")
        except Exception as e:
            print(f"[-] Timeout/errore goto: {e}")
            await asyncio.sleep(5)

        try:
            js_result = await page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('script').forEach(s => {
                        const text = s.textContent || '';
                        const m1 = text.match(/https?:\\/\\/[^'"\\s]*\\/playlist\\/[^'"\\s]*/g);
                        if (m1) results.push(...m1);
                        const m2 = text.match(/vixsrc\\.to\\/playlist\\/[^'"\\s,&]*/g);
                        if (m2) results.push(...m2.map(u => 'https://' + u));
                    });
                    document.querySelectorAll('*').forEach(el => {
                        if (el.src && el.src.includes('/playlist/')) results.push(el.src);
                        if (el.href && el.href.includes('/playlist/')) results.push(el.href);
                    });
                    return [...new Set(results)];
                }
            """)
            for url in js_result:
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    url = "https://vixsrc.to" + url
                if url not in playlist_urls and "/playlist/" in url:
                    playlist_urls.append(url)
                    print(f"[+] Da JS: {url}")
        except Exception as e:
            print(f"[-] JS extraction: {e}")

        await browser.close()

    return playlist_urls


async def get_best_playlist(movie_url):
    urls = await extract_playlist_url(movie_url)
    if not urls:
        return None

    vixsrc = [u for u in urls if "vixsrc.to/playlist/" in u]
    pool = vixsrc if vixsrc else urls

    for q in ["1080p", "1080", "720p", "720"]:
        match = [u for u in pool if q in u]
        if match:
            return match[0]

    return pool[0]


# ============================================================
# Flask Routes
# ============================================================

@app.route('/check-ip')
def check_ip():
    async def get_ip():
        proxy = get_proxy_config()
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy=proxy,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            page = await browser.new_page()
            await page.goto("https://api.ipify.org?format=json")
            content = await page.inner_text("body")
            await browser.close()
            return content

    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(get_ip())
    loop.close()

    proxy = get_proxy_config()
    return jsonify({
        "ip_visto_da_vixsrc": result,
        "proxy_attivo": proxy is not None,
        "proxy_server": proxy["server"] if proxy else None,
        "WEBSHARE_USER_impostato": bool(PROXY_USER),
        "WEBSHARE_PASS_impostato": bool(PROXY_PASS),
    })


@app.route('/proxy')
def proxy_stream():
    """
    Relay trasparente: scarica il contenuto (m3u8 o segmenti ts)
    usando lo stesso IP Webshare con cui è stato generato il token.
    """
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({'error': 'url mancante'}), 400

    proxies = get_requests_proxies()

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://vixsrc.to/",
        "Origin": "https://vixsrc.to",
    }

    try:
        r = req_lib.get(
            target_url,
            headers=headers,
            proxies=proxies,
            stream=True,
            timeout=30
        )

        # Se è un file m3u8, riscriviamo gli URL interni per passare dal relay
        content_type = r.headers.get('Content-Type', '')
        if 'mpegurl' in content_type or target_url.endswith('.m3u8'):
            content = r.text
            # Riscrivi ogni URL assoluto http(s)://... → /proxy?url=...
            import re
            def rewrite(line):
                line = line.strip()
                if line.startswith('http://') or line.startswith('https://'):
                    return f"/proxy?url={line}"
                return line
            rewritten = "\n".join(rewrite(l) for l in content.splitlines())
            return Response(rewritten, content_type='application/vnd.apple.mpegurl')

        # Altrimenti stream diretto (segmenti .ts, ecc.)
        return Response(
            stream_with_context(r.iter_content(chunk_size=65536)),
            content_type=r.headers.get('Content-Type', 'application/octet-stream'),
            status=r.status_code,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/extract', methods=['POST'])
def api_extract():
    data = request.get_json()
    movie_url = data.get('url', '')

    if not movie_url:
        return jsonify({'success': False, 'error': 'URL richiesto'})

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        playlist_url = loop.run_until_complete(get_best_playlist(movie_url))
        loop.close()

        if playlist_url:
            # Restituisce l'URL proxato invece del link diretto
            base = request.host_url.rstrip('/')
            proxied_url = f"{base}/proxy?url={playlist_url}"
            return jsonify({'success': True, 'url': proxied_url, 'original': playlist_url})
        else:
            return jsonify({'success': False, 'error': 'Nessun link playlist trovato.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# HTML UI
# ============================================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>VixSrc Playlist Extractor</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #0f0f0f; color: #e0e0e0; line-height: 1.6; }
        .container { max-width: 800px; margin: 50px auto; padding: 0 20px; }
        h1 { color: #00d4aa; font-size: 1.8em; margin-bottom: 6px; }
        .subtitle { color: #888; margin-bottom: 30px; }
        .card { background: #1a1a2e; border-radius: 12px; padding: 30px; border: 1px solid #2a2a4a; }
        label { display: block; margin-bottom: 8px; color: #aaa; font-size: 0.9em; }
        input[type="text"] { width: 100%; padding: 12px 16px; background: #0f0f1a;
                             border: 1px solid #333; border-radius: 8px; color: #fff;
                             font-size: 1em; margin-bottom: 15px; }
        input[type="text"]:focus { outline: none; border-color: #00d4aa; }
        button.main-btn { background: #00d4aa; color: #000; border: none; padding: 12px 24px;
                 border-radius: 8px; font-size: 1em; font-weight: 600; cursor: pointer; }
        button.main-btn:hover { background: #00f0c0; }
        .result { margin-top: 20px; padding: 15px; background: #0f0f1a; border-radius: 8px;
                  border: 1px solid #2a2a4a; word-break: break-all; display: none; }
        .result.success { border-color: #00d4aa; display: block; }
        .result.error { border-color: #ff4444; display: block; }
        .result code { color: #00d4aa; font-size: 0.85em; }
        .loader { display: none; margin: 15px 0; color: #888; }
        .loader.active { display: block; }
        .spinner { display: inline-block; width: 18px; height: 18px; border: 3px solid #333;
                    border-top: 3px solid #00d4aa; border-radius: 50%;
                    animation: spin 0.8s linear infinite; margin-right: 8px; vertical-align: middle; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .copy-btn { background: #333; color: #fff; border: none; padding: 6px 14px;
                    border-radius: 4px; cursor: pointer; font-size: 0.85em; margin-left: 8px; }
        .copy-btn:hover { background: #444; }
        .note { color: #666; font-size: 0.82em; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 VixSrc Playlist Extractor</h1>
        <p class="subtitle">Incolla il link del film, ottieni il link M3U8 da usare in VLC</p>
        <div class="card">
            <label for="url-input">URL del film su vixsrc.to</label>
            <input type="text" id="url-input" placeholder="https://vixsrc.to/movie/786892/" />
            <button class="main-btn" onclick="extract()">▶ Estrai Link Playlist</button>
            <div class="loader" id="loader">
                <span class="spinner"></span> Estrazione in corso (20-30 secondi)...
            </div>
            <div class="result" id="result"></div>
        </div>
    </div>
    <script>
        async function extract() {
            const url = document.getElementById('url-input').value.trim();
            if (!url) { showResult(false, 'Inserisci un URL valido'); return; }
            document.getElementById('loader').classList.add('active');
            document.getElementById('result').className = 'result';
            try {
                const resp = await fetch('/extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });
                const data = await resp.json();
                document.getElementById('loader').classList.remove('active');
                if (data.success) {
                    document.getElementById('result').className = 'result success';
                    document.getElementById('result').innerHTML =
                        '<strong>✅ Playlist trovata!</strong><br><br>' +
                        '<span style="color:#888;">Copia e incolla in VLC (Ctrl+N):</span><br><br>' +
                        '<code id="playlisturl">' + data.url + '</code>' +
                        '<button class="copy-btn" onclick="copyUrl()">📋 Copia</button><br><br>' +
                        '<span class="note">In VLC: Ctrl+N → incolla URL → Play</span>';
                } else {
                    showResult(false, data.error);
                }
            } catch (err) {
                document.getElementById('loader').classList.remove('active');
                showResult(false, err.message);
            }
        }
        function showResult(success, msg) {
            const el = document.getElementById('result');
            el.className = 'result ' + (success ? 'success' : 'error');
            el.innerHTML = msg;
        }
        function copyUrl() {
            const url = document.getElementById('playlisturl').textContent;
            navigator.clipboard.writeText(url).then(() => {
                const btn = document.querySelector('.copy-btn');
                btn.textContent = '✅ Copiato!';
                setTimeout(() => btn.textContent = '📋 Copia', 2000);
            });
        }
        document.getElementById('url-input').addEventListener('keydown', e => {
            if (e.key === 'Enter') extract();
        });
    </script>
</body>
</html>
'''


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    if len(sys.argv) > 1:
        async def main():
            url = await get_best_playlist(sys.argv[1])
            print(f"\n[+] {url}" if url else "\n[-] Nessuna playlist trovata")
        asyncio.run(main())
    else:
        app.run(host='0.0.0.0', port=port, debug=False)
