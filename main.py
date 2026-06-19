#!/usr/bin/env python3

"""
VixSrc M3U8 Extractor v5 - Ottimizzato per Smart TV Samsung (Tizen) & Telecomando
Con supporto proxy HTTP
"""

import os
import re
import sys
import json
import asyncio
import requests
from urllib.parse import urlparse, parse_qs, urlencode
from flask import Flask, request, jsonify, render_template_string
import random
import time

app = Flask(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# URL per scaricare proxy HTTP
PROXY_LIST_URL = "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/http.txt"

def fetch_proxies():
    """Scarica proxy HTTP da GitHub"""
    try:
        print("[*] Scaricando proxy da GitHub...")
        response = requests.get(PROXY_LIST_URL, timeout=10)
        if response.status_code == 200:
            proxies = [line.strip() for line in response.text.split('\n') if line.strip()]
            print(f"[+] Scaricati {len(proxies)} proxy")
            return proxies
        return []
    except Exception as e:
        print(f"[-] Errore: {e}")
        return []

def test_proxy(proxy):
    """Testa proxy velocemente"""
    try:
        proxies = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
        start = time.time()
        response = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=5)
        if response.status_code == 200:
            elapsed = time.time() - start
            print(f"   ✅ Proxy {proxy} funziona ({elapsed:.2f}s)")
            return True
        return False
    except:
        return False

def get_best_proxy():
    """Trova il miglior proxy HTTP"""
    # Prima prova alcuni proxy che potrebbero funzionare
    hardcoded_proxies = [
        "34.43.46.91:80",
        "159.65.221.25:80",
        "142.93.202.130:3128",
        "104.154.186.48:80",
        "12.50.107.219:80",
        "174.138.119.88:80"
    ]
    
    print("[*] Testando proxy hardcoded...")
    for proxy in hardcoded_proxies:
        if test_proxy(proxy):
            return proxy
    
    # Se non funzionano, scarica nuovi proxy
    proxies = fetch_proxies()
    if not proxies:
        print("[-] Nessun proxy disponibile")
        return None
    
    random.shuffle(proxies)
    print("[*] Testando proxy scaricati...")
    
    for proxy in proxies[:15]:
        if test_proxy(proxy):
            return proxy
    
    print("[-] Nessun proxy funzionante trovato")
    return None

async def extract_playlist_url(movie_url):
    """
    Usa Playwright per estrarre i link M3U8
    """
    playlist_urls = []
    
    from playwright.async_api import async_playwright
    
    # Ottieni proxy
    proxy_str = get_best_proxy()
    proxy_config = None
    
    if proxy_str:
        parts = proxy_str.split(":")
        if len(parts) == 2:
            proxy_config = {
                "server": f"http://{parts[0]}:{parts[1]}"
            }
            print(f"[*] Usando proxy: {proxy_config['server']}")
    else:
        print("[*] Nessun proxy disponibile, provo senza proxy")
    
    async with async_playwright() as p:
        launch_args = {
            'headless': True,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu'
            ]
        }
        
        if proxy_config:
            launch_args['proxy'] = proxy_config
        
        try:
            browser = await p.chromium.launch(**launch_args)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
                bypass_csp=True
            )
            page = await context.new_page()
            
            # Script anti-detection
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['it-IT', 'it', 'en-US', 'en']
                });
            """)
            
            # Intercetta richieste
            async def handle_request(request):
                url = request.url
                if "/playlist/" in url and "vixsrc.to" in url:
                    if url not in playlist_urls:
                        playlist_urls.append(url)
                        print(f"[+] PLAYLIST: {url}")
            
            async def handle_response(response):
                url = response.url
                if "/playlist/" in url and "vixsrc.to" in url:
                    if url not in playlist_urls:
                        playlist_urls.append(url)
                        print(f"[+] PLAYLIST (resp): {url}")
            
            page.on("request", handle_request)
            page.on("response", handle_response)
            
            print(f"[*] Caricamento: {movie_url}")
            
            # Naviga
            try:
                await page.goto(movie_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"[-] Timeout: {e}")
            
            # Aspetta e cerca
            for i in range(15):
                await asyncio.sleep(1)
                if playlist_urls:
                    print(f"   [+] Trovati {len(playlist_urls)} link")
                    break
                if i % 3 == 0:
                    await page.evaluate(f"window.scrollBy(0, {100 + i*50})")
            
            # Estrai via JavaScript
            try:
                js_result = await page.evaluate("""
                    () => {
                        const results = [];
                        document.querySelectorAll('script').forEach(s => {
                            const text = s.textContent || '';
                            const matches = text.match(/https?:\\/\\/[^'"\\s]*\\/playlist\\/[^'"\\s]*/g);
                            if (matches) results.push(...matches);
                        });
                        document.querySelectorAll('*').forEach(el => {
                            if (el.src && el.src.includes('/playlist/')) results.push(el.src);
                            if (el.href && el.href.includes('/playlist/')) results.push(el.href);
                        });
                        return [...new Set(results)];
                    }
                """)
                for url in js_result:
                    if url not in playlist_urls and "/playlist/" in url:
                        playlist_urls.append(url)
                        print(f"[+] Da JS: {url}")
            except Exception as e:
                print(f"[-] JS extraction: {e}")
            
            await browser.close()
            
        except Exception as e:
            print(f"[-] Errore Playwright: {e}")
    
    return playlist_urls

async def get_best_playlist(movie_url):
    """Trova la playlist migliore"""
    urls = await extract_playlist_url(movie_url)
    
    if not urls:
        return None
    
    print(f"\n[*] Trovati {len(urls)} link playlist:")
    for u in urls:
        print(f"   - {u}")
    
    vixsrc_playlists = [u for u in urls if "vixsrc.to/playlist/" in u]
    
    if vixsrc_playlists:
        _1080p = [u for u in vixsrc_playlists if "1080p" in u or "1080" in u]
        if _1080p:
            return _1080p[0]
        _720p = [u for u in vixsrc_playlists if "720p" in u or "720" in u]
        if _720p:
            return _720p[0]
        return vixsrc_playlists[0]
    
    if urls:
        return urls[0]
    
    return None

# ============================================================
# Flask Routes
# ============================================================

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
            return jsonify({
                'success': True,
                'url': playlist_url,
            })
        else:
            return jsonify({'success': False, 'error': 'Nessun link playlist trovato. Il sito potrebbe bloccare le connessioni dal server cloud.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============================================================
# HTML UI (versione ridotta per testing)
# ============================================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>VixSrc Extractor</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #141414; color: #fff; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: #E50914; margin-bottom: 20px; }
        input[type="text"] { width: 100%; padding: 15px; background: #262626;
                             border: 1px solid #333; border-radius: 6px; color: #fff;
                             font-size: 1em; margin-bottom: 15px; }
        button { background: #E50914; color: #fff; border: none; padding: 15px 30px;
                 border-radius: 6px; font-size: 1em; font-weight: 700; cursor: pointer;
                 width: 100%; }
        .result { margin-top: 20px; padding: 15px; background: #222; border-radius: 6px;
                  display: none; }
        .result.success { border-color: #2ecc71; background: rgba(46, 204, 113, 0.1);
                          color: #2ecc71; display: block; }
        .result.error { border-color: #e74c3c; background: rgba(231, 76, 60, 0.1);
                        color: #e74c3c; display: block; }
        .loader { display: none; margin: 20px 0; text-align: center; color: #aaa; }
        .loader.active { display: block; }
        .spinner { display: inline-block; width: 24px; height: 24px; border: 3px solid rgba(255,255,255,0.1);
                    border-top: 3px solid #E50914; border-radius: 50%;
                    animation: spin 0.8s linear infinite; margin-right: 12px; vertical-align: middle; }
        @keyframes spin { to { transform: rotate(360deg); } }
        video { width: 100%; margin-top: 20px; background: #000; border-radius: 6px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>VixSrc TV Extractor</h1>
        <p style="color: #aaa; margin-bottom: 20px;">Inserisci l'URL del film su vixsrc.to</p>
        
        <input type="text" id="url-input" placeholder="https://vixsrc.to/movie/786892/" />
        <button onclick="extract()">Avvia Stream</button>
        
        <div class="loader" id="loader">
            <span class="spinner"></span> Analisi in corso...
        </div>
        
        <div class="result" id="result"></div>
        
        <video id="video" controls playsinline style="display:none;"></video>
    </div>
    
    <script>
        async function extract() {
            const url = document.getElementById('url-input').value.trim();
            if (!url) {
                showResult('Inserisci un URL valido', 'error');
                return;
            }
            
            document.getElementById('loader').classList.add('active');
            document.getElementById('result').className = 'result';
            document.getElementById('video').style.display = 'none';
            
            try {
                const resp = await fetch('/extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                
                const data = await resp.json();
                document.getElementById('loader').classList.remove('active');
                
                if (data.success) {
                    showResult('Stream trovato!', 'success');
                    const video = document.getElementById('video');
                    video.style.display = 'block';
                    video.src = data.url;
                    video.play().catch(() => {});
                } else {
                    showResult('Errore: ' + data.error, 'error');
                }
            } catch (err) {
                document.getElementById('loader').classList.remove('active');
                showResult('Errore: ' + err.message, 'error');
            }
        }
        
        function showResult(msg, type) {
            const res = document.getElementById('result');
            res.className = `result ${type}`;
            res.innerHTML = msg;
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    if len(sys.argv) > 1:
        async def main():
            movie_url = sys.argv[1]
            print(f"[*] Estrazione da: {movie_url}")
            url = await get_best_playlist(movie_url)
            if url:
                print(f"\n[+] Link playlist: {url}")
            else:
                print("\n[-] Nessuna playlist trovata")
        asyncio.run(main())
    else:
        port = int(os.environ.get("PORT", 8080))
        print(f"""
╔══════════════════════════════════════════════╗
║      VixSrc TV Extractor v5                  ║
║      Port: {port}                             ║
╚══════════════════════════════════════════════╝
        """)
        app.run(host='0.0.0.0', port=port, debug=False)
