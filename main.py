#!/usr/bin/env python3
"""
VixSrc M3U8 Extractor v8 - Proxy Diretti + Playwright
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
import base64

app = Flask(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# 🔑 Proxy con autenticazione
PROXIES = [
    {"ip": "31.59.20.176", "port": "6754", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
    {"ip": "92.113.242.158", "port": "6742", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
    {"ip": "23.95.150.145", "port": "6114", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
    {"ip": "38.154.203.95", "port": "5863", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
    {"ip": "198.105.121.200", "port": "6462", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
    {"ip": "64.137.96.74", "port": "6641", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
    {"ip": "38.154.185.97", "port": "6370", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
    {"ip": "142.111.67.146", "port": "5611", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
    {"ip": "191.96.254.138", "port": "6185", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
    {"ip": "2.57.20.2", "port": "6983", "user": "ehsmnoqu", "pass": "23aljm7zs2y7"},
]

def get_proxy_url(proxy):
    """Costruisce l'URL del proxy con autenticazione"""
    return f"http://{proxy['user']}:{proxy['pass']}@{proxy['ip']}:{proxy['port']}"

def test_proxy(proxy):
    """Testa se un proxy funziona"""
    try:
        proxy_url = get_proxy_url(proxy)
        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
        
        response = requests.get(
            "http://httpbin.org/ip",
            proxies=proxies,
            timeout=5,
            headers={'User-Agent': USER_AGENT}
        )
        
        if response.status_code == 200:
            print(f"[+] Proxy funzionante: {proxy['ip']}:{proxy['port']}")
            return True
        return False
    except Exception as e:
        return False

def get_working_proxy():
    """Trova un proxy funzionante"""
    # Mescola per varietà
    shuffled = PROXIES.copy()
    random.shuffle(shuffled)
    
    print(f"[*] Testando {len(shuffled)} proxy...")
    
    for proxy in shuffled:
        if test_proxy(proxy):
            return proxy
    
    print("[-] Nessun proxy funzionante trovato")
    return None

def extract_playlist_from_html(html):
    """Estrae i link playlist dall'HTML"""
    urls = []
    
    if not html:
        return urls
    
    # Pattern per link completi
    patterns = [
        # Link con tutti i parametri
        r'https?://vixsrc\.to/playlist/\d+\?[^"\'\\s<>]+',
        r'https?://vixsrc\.to/playlist/[^"\'\\s<>]+',
        # Link relativi
        r'vixsrc\.to/playlist/\d+\?[^"\'\\s<>]+',
        r'vixsrc\.to/playlist/[^"\'\\s<>]+',
        # Link in JSON
        r'["\'](https?://vixsrc\.to/playlist/[^"\'\\s<>]+)["\']',
        r'["\'](vixsrc\.to/playlist/[^"\'\\s<>]+)["\']',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html)
        for match in matches:
            if match.startswith('vixsrc.to'):
                match = 'https://' + match
            if match.startswith('//'):
                match = 'https:' + match
            if '/playlist/' in match and match not in urls:
                urls.append(match)
    
    # Pattern specifico con tutti i parametri
    specific_pattern = r'https?://vixsrc\.to/playlist/\d+\?type=video&rendition=\d+p&token=[^"\'\\s<>]+&expires=\d+&edge=[^"\'\\s<>]+'
    specific_matches = re.findall(specific_pattern, html)
    for match in specific_matches:
        if match not in urls:
            urls.append(match)
    
    # Cerca nei tag video
    tag_patterns = [
        r'<source[^>]+src=["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'<video[^>]+src=["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'file["\']?\s*[:=]\s*["\']([^"\'\\s]+\.m3u8[^"\'\\s]*)["\']',
        r'src["\']?\s*[:=]\s*["\']([^"\'\\s]+\.m3u8[^"\'\\s]*)["\']',
    ]
    
    for pattern in tag_patterns:
        matches = re.findall(pattern, html)
        for match in matches:
            if match.startswith('//'):
                match = 'https:' + match
            elif match.startswith('/'):
                match = 'https://vixsrc.to' + match
            if ('vixsrc.to/playlist/' in match or '.m3u8' in match) and match not in urls:
                urls.append(match)
    
    # Cerca nel JavaScript
    js_patterns = [
        r'playlist["\']?\s*[:=]\s*["\']([^"\'\\s]+\.m3u8[^"\'\\s]*)["\']',
        r'videoUrl["\']?\s*[:=]\s*["\']([^"\'\\s]+)["\']',
        r'hlsUrl["\']?\s*[:=]\s*["\']([^"\'\\s]+)["\']',
    ]
    
    for pattern in js_patterns:
        matches = re.findall(pattern, html)
        for match in matches:
            if match.startswith('//'):
                match = 'https:' + match
            elif match.startswith('/'):
                match = 'https://vixsrc.to' + match
            if ('vixsrc.to/playlist/' in match or '.m3u8' in match) and match not in urls:
                urls.append(match)
    
    return list(set(urls))

def get_page_with_proxy(movie_url):
    """Scarica la pagina usando un proxy"""
    proxy = get_working_proxy()
    
    if not proxy:
        print("[-] Nessun proxy disponibile, provo senza proxy")
        try:
            response = requests.get(movie_url, headers={'User-Agent': USER_AGENT}, timeout=30)
            if response.status_code == 200:
                return response.text
        except:
            pass
        return None
    
    proxy_url = get_proxy_url(proxy)
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }
    
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://vixsrc.to/',
        'Connection': 'keep-alive'
    }
    
    try:
        print(f"[*] Scaricando con proxy: {proxy['ip']}:{proxy['port']}")
        response = requests.get(movie_url, proxies=proxies, headers=headers, timeout=60)
        
        if response.status_code == 200:
            print(f"[+] Pagina scaricata ({len(response.text)} bytes)")
            return response.text
        else:
            print(f"[-] Errore: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"[-] Errore con proxy: {e}")
        return None

async def extract_playlist_with_playwright(movie_url):
    """Usa Playwright come fallback"""
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            page = await browser.new_page(user_agent=USER_AGENT)
            
            urls = []
            
            async def handle_request(request):
                url = request.url
                if "/playlist/" in url and "vixsrc.to" in url:
                    if url not in urls:
                        urls.append(url)
                        print(f"[+] PLAYLIST: {url}")
            
            page.on("request", handle_request)
            
            await page.goto(movie_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(5)
            
            await browser.close()
            return urls
            
    except Exception as e:
        print(f"[-] Playwright fallito: {e}")
        return []

async def get_best_playlist(movie_url):
    """Trova la playlist migliore"""
    
    print(f"\n[*] Elaborazione: {movie_url}")
    
    # Prima prova con i proxy diretti
    html = get_page_with_proxy(movie_url)
    urls = []
    
    if html:
        urls = extract_playlist_from_html(html)
        print(f"[+] Trovati {len(urls)} link playlist")
    
    # Se non troviamo nulla, prova con Playwright
    if not urls:
        print("[*] Nessun link trovato, provo con Playwright...")
        urls = await extract_playlist_with_playwright(movie_url)
        print(f"[+] Trovati {len(urls)} link con Playwright")
    
    if not urls:
        return None
    
    # Filtra playlist valide
    valid_playlists = []
    for u in urls:
        if 'vixsrc.to/playlist/' in u:
            if '?' in u or '.m3u8' in u:
                valid_playlists.append(u)
    
    if not valid_playlists:
        valid_playlists = urls
    
    print(f"\n[*] Playlist valide: {len(valid_playlists)}")
    for u in valid_playlists[:5]:
        print(f"   - {u[:100]}...")
    
    # Dai priorità alla qualità
    _1080p = [u for u in valid_playlists if "rendition=1080" in u or "1080p" in u]
    if _1080p:
        print("[+] Scelto: 1080p")
        return _1080p[0]
    
    _720p = [u for u in valid_playlists if "rendition=720" in u or "720p" in u]
    if _720p:
        print("[+] Scelto: 720p")
        return _720p[0]
    
    _m3u8 = [u for u in valid_playlists if ".m3u8" in u]
    if _m3u8:
        print("[+] Scelto: primo .m3u8")
        return _m3u8[0]
    
    if valid_playlists:
        print("[+] Scelto: primo disponibile")
        return valid_playlists[0]
    
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
            return jsonify({
                'success': False, 
                'error': 'Nessun link playlist trovato. Verifica che l\'URL sia corretto.'
            })
    except Exception as e:
        print(f"[-] Errore API: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ============================================================
# HTML UI
# ============================================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>VixSrc Extractor v8</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #141414; color: #fff; padding: 20px; min-height: 100vh; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: #E50914; margin-bottom: 5px; font-size: 2em; }
        .subtitle { color: #aaa; margin-bottom: 20px; }
        .card { background: #1a1a1a; padding: 30px; border-radius: 10px; border: 1px solid #333; }
        input[type="text"] { width: 100%; padding: 15px; background: #262626;
                             border: 1px solid #333; border-radius: 6px; color: #fff;
                             font-size: 1em; margin-bottom: 15px; transition: all 0.3s; }
        input[type="text"]:focus { outline: none; border-color: #E50914; }
        button { background: #E50914; color: #fff; border: none; padding: 15px 30px;
                 border-radius: 6px; font-size: 1em; font-weight: 700; cursor: pointer;
                 width: 100%; transition: all 0.3s; }
        button:hover { background: #ff1925; transform: scale(1.02); }
        button:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .loader { display: none; margin: 20px 0; text-align: center; color: #aaa; }
        .loader.active { display: block; }
        .spinner { display: inline-block; width: 24px; height: 24px; border: 3px solid rgba(255,255,255,0.1);
                    border-top: 3px solid #E50914; border-radius: 50%;
                    animation: spin 0.8s linear infinite; margin-right: 12px; vertical-align: middle; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .result { margin-top: 20px; padding: 15px; border-radius: 6px; display: none; }
        .result.success { border: 1px solid #2ecc71; background: rgba(46, 204, 113, 0.1);
                          color: #2ecc71; display: block; }
        .result.error { border: 1px solid #e74c3c; background: rgba(231, 76, 60, 0.1);
                        color: #e74c3c; display: block; }
        .player-container { margin-top: 20px; display: none; background: #000; border-radius: 6px; overflow: hidden; }
        .player-container.active { display: block; }
        video { width: 100%; display: block; max-height: 500px; background: #000; }
        .debug-info { margin-top: 10px; padding: 10px; background: #222; border-radius: 4px; font-size: 0.8em; color: #888; display: none; word-break: break-all; }
        .debug-info.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 VixSrc Extractor</h1>
        <p class="subtitle">Inserisci l'URL del film e guardalo subito</p>
        
        <div class="card">
            <input type="text" id="url-input" placeholder="https://vixsrc.to/movie/786892/" />
            <button id="extract-btn" onclick="extract()">▶ Avvia Stream</button>
            
            <div class="loader" id="loader">
                <span class="spinner"></span> Estrazione in corso...
            </div>
            
            <div class="result" id="result"></div>
            <div class="debug-info" id="debug-info"></div>
        </div>
        
        <div class="player-container" id="player-container">
            <video id="video" controls playsinline></video>
        </div>
    </div>
    
    <script>
        let hlsInstance = null;
        
        async function extract() {
            const url = document.getElementById('url-input').value.trim();
            if (!url) {
                showResult('Inserisci un URL valido', 'error');
                return;
            }
            
            const btn = document.getElementById('extract-btn');
            btn.disabled = true;
            btn.textContent = '⏳ Estrazione in corso...';
            
            document.getElementById('loader').classList.add('active');
            document.getElementById('result').className = 'result';
            document.getElementById('player-container').classList.remove('active');
            document.getElementById('debug-info').classList.remove('show');
            
            if (hlsInstance) {
                hlsInstance.destroy();
                hlsInstance = null;
            }
            
            try {
                const resp = await fetch('/extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                
                const data = await resp.json();
                document.getElementById('loader').classList.remove('active');
                btn.disabled = false;
                btn.textContent = '▶ Avvia Stream';
                
                if (data.success) {
                    showResult('✅ Stream trovato!', 'success');
                    startVideo(data.url);
                } else {
                    showResult('❌ ' + data.error, 'error');
                }
            } catch (err) {
                document.getElementById('loader').classList.remove('active');
                btn.disabled = false;
                btn.textContent = '▶ Avvia Stream';
                showResult('❌ Errore: ' + err.message, 'error');
            }
        }
        
        function startVideo(url) {
            const video = document.getElementById('video');
            const container = document.getElementById('player-container');
            container.classList.add('active');
            
            const debug = document.getElementById('debug-info');
            debug.textContent = 'URL: ' + url;
            debug.classList.add('show');
            
            if (!url.includes('/playlist/')) {
                showResult('❌ URL non valido', 'error');
                return;
            }
            
            if (Hls.isSupported()) {
                if (hlsInstance) hlsInstance.destroy();
                hlsInstance = new Hls({ maxBufferLength: 30 });
                hlsInstance.loadSource(url);
                hlsInstance.attachMedia(video);
                hlsInstance.on(Hls.Events.MANIFEST_PARSED, function() {
                    video.play().catch(() => {});
                });
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = url;
                video.addEventListener('loadedmetadata', function() {
                    video.play().catch(() => {});
                });
            } else {
                showResult('❌ Browser non supporta HLS', 'error');
            }
        }
        
        function showResult(msg, type) {
            const res = document.getElementById('result');
            res.className = `result ${type}`;
            res.innerHTML = msg;
        }
        
        document.getElementById('url-input').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                extract();
            }
        });
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    
    print(f"""
╔══════════════════════════════════════════════╗
║      VixSrc Extractor v8 - Proxy Diretti     ║
║      Porta: {port}                            ║
║      Proxy disponibili: {len(PROXIES)}          ║
╚══════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=False)
