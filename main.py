#!/usr/bin/env python3
"""
VixSrc M3U8 Extractor v6 - Con ScraperAPI (Senza Playwright)
Funziona su Render.com
"""

import os
import re
import sys
import json
import asyncio
import requests
from urllib.parse import urlparse, parse_qs, urlencode
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# 🔑 LEGGI LA CHIAVE DALLE VARIABILI D'AMBIENTE
SCRAPERAPI_KEY = os.environ.get("SCRAPERAPI_KEY", "")

def extract_playlist_from_html(html):
    """Estrae i link playlist dall'HTML"""
    urls = []
    
    # Pattern per link completi
    patterns = [
        r'https?://vixsrc\.to/playlist/\d+\?[^"\'\\s<>]+',
        r'https?://vixsrc\.to/playlist/[^"\'\\s<>]+',
        r'vixsrc\.to/playlist/\d+\?[^"\'\\s<>]+',
        r'vixsrc\.to/playlist/[^"\'\\s<>]+',
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
    
    # Pattern specifico con parametri
    specific_pattern = r'https?://vixsrc\.to/playlist/\d+\?type=video&rendition=\d+p&token=[^"\'\\s<>]+&expires=\d+&edge=[^"\'\\s<>]+'
    specific_matches = re.findall(specific_pattern, html)
    for match in specific_matches:
        if match not in urls:
            urls.append(match)
    
    # Cerca nei tag
    tag_patterns = [
        r'<source[^>]+src=["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'<video[^>]+src=["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'file["\']?\s*[:=]\s*["\']([^"\'\\s]+\.m3u8[^"\'\\s]*)["\']',
        r'source["\']?\s*[:=]\s*["\']([^"\'\\s]+\.m3u8[^"\'\\s]*)["\']',
    ]
    
    for pattern in tag_patterns:
        matches = re.findall(pattern, html)
        for match in matches:
            if match.startswith('//'):
                match = 'https:' + match
            if match.startswith('/'):
                match = 'https://vixsrc.to' + match
            if ('vixsrc.to/playlist/' in match or '.m3u8' in match) and match not in urls:
                urls.append(match)
    
    return list(set(urls))

async def get_playlist_with_scraperapi(movie_url):
    """Usa ScraperAPI per ottenere l'HTML"""
    try:
        if not SCRAPERAPI_KEY:
            print("[-] ERRORE: SCRAPERAPI_KEY non configurata!")
            print("[*] Imposta la variabile d'ambiente SCRAPERAPI_KEY su Render")
            return []
        
        print(f"[*] Richiesta a ScraperAPI per: {movie_url}")
        
        # Se è già una playlist, restituiscila
        if '/playlist/' in movie_url and ('type=video' in movie_url or '.m3u8' in movie_url):
            print("[+] URL già una playlist valida!")
            return [movie_url]
        
        params = {
            'api_key': SCRAPERAPI_KEY,
            'url': movie_url,
            'render': 'true',
            'country_code': 'it',
            'wait_for': 8000,
            'keep_headers': 'true',
            'premium': 'true'
        }
        
        api_url = 'https://api.scraperapi.com/?' + urlencode(params)
        
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://vixsrc.to/',
            'Upgrade-Insecure-Requests': '1'
        }
        
        print("[*] Attendere... L'estrazione potrebbe richiedere fino a 30 secondi")
        response = requests.get(api_url, headers=headers, timeout=90)
        
        if response.status_code == 200:
            html = response.text
            print(f"[+] HTML ricevuto ({len(html)} bytes)")
            
            # Salva HTML per debug
            try:
                with open('/tmp/debug.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print("[*] HTML salvato in /tmp/debug.html")
            except:
                pass
            
            # Estrai i link
            urls = extract_playlist_from_html(html)
            print(f"[+] Trovati {len(urls)} link playlist")
            
            if urls:
                for i, url in enumerate(urls[:5], 1):
                    print(f"   {i}. {url[:100]}...")
            
            return urls
        else:
            print(f"[-] Errore ScraperAPI: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"[-] Errore: {e}")
        return []

async def get_best_playlist(movie_url):
    """Trova la playlist migliore"""
    urls = await get_playlist_with_scraperapi(movie_url)
    
    if not urls:
        return None
    
    print(f"\n[*] Trovati {len(urls)} link playlist totali")
    
    # Filtra playlist valide
    valid_playlists = [u for u in urls if 'vixsrc.to/playlist/' in u and ('?' in u or '.m3u8' in u)]
    
    if not valid_playlists:
        valid_playlists = urls
    
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
    <title>VixSrc Extractor</title>
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
                <span class="spinner"></span> Estrazione in corso... attendere fino a 30 secondi
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
                showResult('❌ Errore di connessione: ' + err.message, 'error');
            }
        }
        
        function startVideo(url) {
            const video = document.getElementById('video');
            const container = document.getElementById('player-container');
            container.classList.add('active');
            
            const debug = document.getElementById('debug-info');
            debug.textContent = 'URL: ' + url;
            debug.classList.add('show');
            
            if (!url.includes('/playlist/') || !url.includes('.m3u8')) {
                showResult('❌ URL non valido: non è una playlist M3U8', 'error');
                return;
            }
            
            if (Hls.isSupported()) {
                if (hlsInstance) hlsInstance.destroy();
                hlsInstance = new Hls({ maxBufferLength: 30, maxMaxBufferLength: 60 });
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
                showResult('❌ Il tuo browser non supporta HLS', 'error');
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
    port = int(os.environ.get("PORT", 8080))
    
    print(f"""
╔══════════════════════════════════════════════╗
║      VixSrc Extractor v6 - ScraperAPI       ║
║      Porta: {port}                            ║
╚══════════════════════════════════════════════╝
    """)
    
    if not SCRAPERAPI_KEY:
        print("⚠️  ATTENZIONE: SCRAPERAPI_KEY non configurata!")
        print("   Registrati su https://www.scraperapi.com/")
        print("   e aggiungi la variabile d'ambiente SCRAPERAPI_KEY su Render\n")
    else:
        print(f"✅ SCRAPERAPI_KEY configurata: {SCRAPERAPI_KEY[:8]}...")
    
    app.run(host='0.0.0.0', port=port, debug=False)
