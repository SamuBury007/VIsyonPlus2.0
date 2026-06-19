#!/usr/bin/env python3
"""
VixSrc M3U8 Extractor v9 - Playwright + Proxy (Ibrido)
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

# Proxy con autenticazione (formato: ip:port:username:password)
PROXY_LIST = [
    "31.59.20.176:6754:ehsmnoqu:23aljm7zs2y7",
    "92.113.242.158:6742:ehsmnoqu:23aljm7zs2y7",
    "23.95.150.145:6114:ehsmnoqu:23aljm7zs2y7",
    "38.154.203.95:5863:ehsmnoqu:23aljm7zs2y7",
    "198.105.121.200:6462:ehsmnoqu:23aljm7zs2y7",
    "64.137.96.74:6641:ehsmnoqu:23aljm7zs2y7",
    "38.154.185.97:6370:ehsmnoqu:23aljm7zs2y7",
    "142.111.67.146:5611:ehsmnoqu:23aljm7zs2y7",
    "191.96.254.138:6185:ehsmnoqu:23aljm7zs2y7",
    "2.57.20.2:6983:ehsmnoqu:23aljm7zs2y7",
]

# Fallback: proxy pubblici (se quelli autenticati non funzionano)
PUBLIC_PROXIES = [
    "34.43.46.91:80",
    "159.65.221.25:80",
    "142.93.202.130:3128",
    "104.154.186.48:80",
    "12.50.107.219:80",
]

def parse_proxy(proxy_str):
    """Parsa una stringa proxy nel formato IP:PORT:USER:PASS o IP:PORT"""
    parts = proxy_str.split(":")
    if len(parts) == 4:
        ip, port, username, password = parts
        return {
            "server": f"http://{ip}:{port}",
            "username": username,
            "password": password
        }
    elif len(parts) == 2:
        ip, port = parts
        return {
            "server": f"http://{ip}:{port}"
        }
    return None

def test_proxy_quick(proxy_str):
    """Testa rapidamente un proxy"""
    try:
        proxy_config = parse_proxy(proxy_str)
        if not proxy_config:
            return False
        
        server = proxy_config.get("server")
        if not server:
            return False
        
        # Costruisci i proxies per requests
        if "username" in proxy_config and "password" in proxy_config:
            auth = f"{proxy_config['username']}:{proxy_config['password']}@"
            server_with_auth = server.replace("http://", f"http://{auth}")
            proxies = {"http": server_with_auth, "https": server_with_auth.replace("http://", "https://")}
        else:
            proxies = {"http": server, "https": server.replace("http://", "https://")}
        
        response = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=3)
        return response.status_code == 200
    except:
        return False

def get_working_proxy():
    """Trova un proxy funzionante"""
    # Prima prova quelli autenticati
    for proxy in PROXY_LIST:
        print(f"[*] Testando proxy autenticato: {proxy[:30]}...")
        if test_proxy_quick(proxy):
            print(f"[+] Proxy funzionante: {proxy[:30]}...")
            return proxy
    
    # Poi prova quelli pubblici
    for proxy in PUBLIC_PROXIES:
        print(f"[*] Testando proxy pubblico: {proxy}")
        if test_proxy_quick(proxy):
            print(f"[+] Proxy funzionante: {proxy}")
            return proxy
    
    print("[-] Nessun proxy funzionante trovato")
    return None

async def extract_playlist_url(movie_url):
    """
    Usa Playwright per catturare le richieste a /playlist/
    """
    playlist_urls = []
    
    from playwright.async_api import async_playwright
    
    # Ottieni un proxy funzionante
    proxy_str = get_working_proxy()
    proxy_config = None
    
    if proxy_str:
        proxy_config = parse_proxy(proxy_str)
        if proxy_config:
            print(f"[*] Utilizzo proxy: {proxy_config['server']}")
    
    async with async_playwright() as p:
        # Configura il browser
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
                '--disable-gpu',
                '--disable-extensions',
                '--disable-component-extensions-with-background-pages',
                '--disable-default-apps',
                '--mute-audio',
                '--no-default-browser-check',
                '--no-first-run',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-ipc-flooding-protection'
            ]
        }
        
        if proxy_config:
            launch_args['proxy'] = proxy_config
        
        try:
            browser = await p.chromium.launch(**launch_args)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
                bypass_csp=True,
                extra_http_headers={
                    'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive'
                }
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
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
            
            # Intercetta le richieste
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
            print("[*] In attesa di richieste a /playlist/...")
            
            try:
                # Naviga
                await page.goto(movie_url, wait_until="networkidle", timeout=45000)
            except Exception as e:
                print(f"[-] Timeout, continuo comunque...")
            
            # Aspetta e scorri
            for i in range(20):
                await asyncio.sleep(1)
                if playlist_urls:
                    print(f"   [+] Trovati {len(playlist_urls)} link")
                    break
                if i % 3 == 0:
                    await page.evaluate(f"window.scrollBy(0, {100 + i*50})")
            
            # Estrai via JavaScript
            try:
                print("[*] Estrazione JavaScript...")
                js_result = await page.evaluate("""
                    () => {
                        const results = [];
                        
                        // Cerca in tutti gli script
                        document.querySelectorAll('script').forEach(s => {
                            const text = s.textContent || '';
                            const matches = text.match(/https?:\\/\\/[^'"\\s]*\\/playlist\\/[^'"\\s]*/g);
                            if (matches) results.push(...matches);
                            const matches2 = text.match(/vixsrc\\.to\\/playlist\\/[^'"\\s,&]*/g);
                            if (matches2) results.push(...matches2.map(u => 'https://' + u));
                        });
                        
                        // Cerca nel DOM
                        document.querySelectorAll('*').forEach(el => {
                            if (el.src && el.src.includes('/playlist/')) results.push(el.src);
                            if (el.href && el.href.includes('/playlist/')) results.push(el.href);
                            if (el.data && typeof el.data === 'string' && el.data.includes('/playlist/')) results.push(el.data);
                        });
                        
                        // Cerca nel localStorage
                        try {
                            for (let key in localStorage) {
                                const val = localStorage[key] || '';
                                if (val.includes('/playlist/')) {
                                    const matches = val.match(/https?:\\/\\/[^'"\\s]*\\/playlist\\/[^'"\\s]*/g);
                                    if (matches) results.push(...matches);
                                }
                            }
                        } catch(e) {}
                        
                        return [...new Set(results)];
                    }
                """)
                
                for url in js_result:
                    if url.startswith("//"):
                        url = "https:" + url
                    elif url.startswith("/"):
                        url = "https://vixsrc.to" + url
                    if url not in playlist_urls and ("/playlist/" in url):
                        playlist_urls.append(url)
                        print(f"[+] Da JS: {url}")
                        
            except Exception as e:
                print(f"[-] JS extraction: {e}")
            
            await browser.close()
            
        except Exception as e:
            print(f"[-] Errore Playwright: {e}")
            return []
    
    return playlist_urls

async def get_best_playlist(movie_url):
    """Trova la playlist migliore"""
    urls = await extract_playlist_url(movie_url)
    
    if not urls:
        return None
    
    print(f"\n[*] Trovati {len(urls)} link playlist:")
    for u in urls:
        print(f"   - {u[:100]}...")
    
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
            return jsonify({
                'success': False, 
                'error': 'Nessun link playlist trovato. Il sito potrebbe bloccare le connessioni dal server cloud.'
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============================================================
# HTML UI (dal tuo codice originale)
# ============================================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>VixSrc Premium TV Player</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #141414; color: #fff; line-height: 1.6; overflow-x: hidden; }
        
        .container { max-width: 1000px; margin: 40px auto; padding: 0 20px; transition: opacity 0.3s; }
        body.fullscreen-active .container { display: none !important; }

        h1 { color: #E50914; font-size: 2.2em; letter-spacing: 1px; text-transform: uppercase; text-align: center; margin-bottom: 5px; font-weight: 800; }
        .subtitle { color: #aaa; margin-bottom: 30px; text-align: center; font-size: 0.95em; }
        .card { background: #181818; border-radius: 12px; padding: 30px; border: 1px solid #282828; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        label { display: block; margin-bottom: 10px; color: #8c8c8c; font-size: 0.9em; text-transform: uppercase; letter-spacing: 0.5px; }
        
        input[type="text"] { width: 100%; padding: 16px; background: #262626;
                             border: 1px solid #333; border-radius: 6px; color: #fff;
                             font-size: 1em; margin-bottom: 20px; transition: all 0.3s ease; }
        input[type="text"]:focus { outline: none; border-color: #E50914; background: #333; box-shadow: 0 0 0 3px rgba(229, 9, 20, 0.2); }
        
        button.btn-extract { background: #E50914; color: #fff; border: none; padding: 16px 30px;
                 border-radius: 6px; font-size: 1.05em; font-weight: 700; cursor: pointer; width: 100%; transition: all 0.2s; box-shadow: 0 4px 12px rgba(229, 9, 20, 0.3); }
        button.btn-extract:hover { background: #fc1925; transform: translateY(-1px); }
        
        .loader { display: none; margin: 25px 0; text-align: center; color: #aaa; font-size: 0.95em; }
        .loader.active { display: block; }
        .spinner { display: inline-block; width: 24px; height: 24px; border: 3px solid rgba(255,255,255,0.1);
                    border-top: 3px solid #E50914; border-radius: 50%;
                    animation: spin 0.8s linear infinite; margin-right: 12px; vertical-align: middle; }
        @keyframes spin { to { transform: rotate(360deg); } }
        
        .result { margin-top: 20px; padding: 15px; background: #222; border-radius: 6px;
                  border: 1px solid #333; word-break: break-all; display: none; text-align: center; font-size: 0.95em; }
        .result.success { border-color: rgba(46, 204, 113, 0.4); background: rgba(46, 204, 113, 0.1); color: #2ecc71; display: block; }
        .result.error { border-color: rgba(231, 76, 60, 0.4); background: rgba(231, 76, 60, 0.1); color: #e74c3c; display: block; }
        
        .player-container {
            position: relative;
            width: 100%;
            background: #000;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 35px;
            display: none;
            box-shadow: 0 20px 40px rgba(0,0,0,0.9);
            aspect-ratio: 16/9;
        }
        .player-container.active { display: block; }
        
        body.fullscreen-active .player-container {
            position: fixed !important;
            top: 0 !important; left: 0 !important;
            width: 100vw !important; height: 100vh !important;
            max-width: 100vw !important; max-height: 100vh !important;
            margin: 0 !important; border-radius: 0 !important;
            z-index: 999999 !important;
            aspect-ratio: auto !important;
        }
        
        video { width: 100%; height: 100%; object-fit: contain; display: block; }
        
        .video-buffering {
            position: absolute; top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            width: 65px; height: 65px;
            border: 5px solid rgba(255,255,255,0.1);
            border-top: 5px solid #E50914;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            z-index: 5;
            display: none;
            pointer-events: none;
        }
        
        .video-controls {
            position: absolute;
            bottom: 0; left: 0; right: 0;
            background: linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.6) 50%, rgba(0,0,0,0) 100%);
            opacity: 0;
            transition: opacity 0.4s cubic-bezier(0.25, 1, 0.5, 1);
            padding: 35px;
            display: flex;
            flex-direction: column;
            gap: 15px;
            z-index: 10;
        }
        .player-container:hover .video-controls,
        .player-container.show-controls .video-controls { opacity: 1; }
        
        .progress-area { height: 5px; width: 100%; background: rgba(255,255,255,0.2); cursor: pointer; position: relative; border-radius: 4px; transition: height 0.1s; }
        .progress-area:hover { height: 8px; }
        .progress-bar { height: 100%; width: 0%; background: #E50914; position: relative; border-radius: 4px; }
        .progress-bar::after {
            content: ''; position: absolute; right: -6px; top: 50%; transform: translateY(-50%);
            width: 14px; height: 14px; background: #E50914; border-radius: 50%; opacity: 0; transition: opacity 0.1s;
            box-shadow: 0 0 8px rgba(229,9,20,0.8);
        }
        .progress-area:hover .progress-bar::after { opacity: 1; }
        
        .control-buttons { display: flex; justify-content: space-between; align-items: center; color: #fff; }
        .controls-left, .controls-right { display: flex; align-items: center; gap: 25px; }
        
        .control-btn { background: none; border: none; color: #fff; font-size: 1.6em; cursor: pointer; display: flex; align-items: center; justify-content: center; opacity: 0.8; transition: all 0.2s; }
        .control-btn:hover { opacity: 1; transform: scale(1.1); color: #E50914; outline: none; }
        
        .volume-container { display: flex; align-items: center; gap: 10px; }
        .volume-slider { width: 0; height: 4px; -webkit-appearance: none; background: rgba(255,255,255,0.3); border-radius: 4px; transition: width 0.2s; cursor: pointer; }
        .volume-container:hover .volume-slider { width: 80px; }
        .volume-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; border-radius: 50%; background: #E50914; }
        
        .time-display { font-size: 0.95em; color: #e0e0e0; font-weight: 500; }
        
        .osd-alert {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) scale(0.8);
            background: rgba(0,0,0,0.75); padding: 20px 30px; border-radius: 30px; font-size: 2em; font-weight: bold;
            opacity: 0; pointer-events: none; transition: all 0.2s ease; z-index: 15; color: #fff;
        }
        .osd-alert.show { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    </style>
</head>
<body>
    <div class="container">
        <h1>VixSrc TV Extractor</h1>
        <p class="subtitle">Interfaccia fluida ottimizzata per simulatori e telecomandi Smart TV</p>

        <div class="card">
            <label for="url-input">Incolla URL Video</label>
            <input type="text" id="url-input" placeholder="https://vixsrc.to/movie/786892/" />

            <button class="btn-extract" onclick="extract()">Avvia Stream</button>

            <div class="loader" id="loader">
                <span class="spinner"></span> Analisi dei flussi in corso...
            </div>

            <div class="result" id="result"></div>
        </div>
    </div>
    
    <div class="player-container" id="player-container" tabindex="0">
        <div class="video-buffering" id="video-buffering"></div>
        <div class="osd-alert" id="osd-alert"></div>
        
        <video id="video" playsinline preload="auto"></video>
        
        <div class="video-controls">
            <div class="progress-area" id="progress-area">
                <div class="progress-bar" id="progress-bar"></div>
            </div>
            
            <div class="control-buttons">
                <div class="controls-left">
                    <button class="control-btn" id="play-pause-btn">▶</button>
                    
                    <div class="volume-container">
                        <button class="control-btn" id="volume-btn">🔊</button>
                        <input type="range" class="volume-slider" id="volume-slider" min="0" max="1" step="0.1" value="1">
                    </div>
                    
                    <div class="time-display">
                        <span id="current-time">0:00</span> / <span id="duration-time">0:00</span>
                    </div>
                </div>
                
                <div class="controls-right">
                    <button class="control-btn" id="fullscreen-btn">⛶</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const video = document.getElementById('video');
        const playerContainer = document.getElementById('player-container');
        const playPauseBtn = document.getElementById('play-pause-btn');
        const volumeBtn = document.getElementById('volume-btn');
        const volumeSlider = document.getElementById('volume-slider');
        const progressBar = document.getElementById('progress-bar');
        const progressArea = document.getElementById('progress-area');
        const currentTimeEl = document.getElementById('current-time');
        const durationTimeEl = document.getElementById('duration-time');
        const fullscreenBtn = document.getElementById('fullscreen-btn');
        const bufferingSpinner = document.getElementById('video-buffering');
        const osdAlert = document.getElementById('osd-alert');
        
        let hls = null;
        let controlsTimeout = null;

        async function extract() {
            const url = document.getElementById('url-input').value.trim();
            if (!url) {
                showResult('Inserisci un URL valido', 'error');
                return;
            }

            document.getElementById('loader').classList.add('active');
            document.getElementById('result').className = 'result';
            playerContainer.classList.remove('active');
            document.body.classList.remove('fullscreen-active');
            if(hls) { hls.destroy(); video.src = ""; }

            try {
                const resp = await fetch('/extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });

                const data = await resp.json();
                document.getElementById('loader').classList.remove('active');

                if (data.success) {
                    showResult('Stream agganciato!', 'success');
                    startVideo(data.url);
                } else {
                    showResult('Errore: ' + data.error, 'error');
                }
            } catch (err) {
                document.getElementById('loader').classList.remove('active');
                showResult('Errore di connessione: ' + err.message, 'error');
            }
        }

        function showResult(msg, type) {
            const res = document.getElementById('result');
            res.className = `result ${type}`;
            res.innerHTML = msg;
        }

        function startVideo(m3u8Url) {
            playerContainer.classList.add('active');
            playerContainer.focus();
            
            togglePseudoFullscreen(true);

            const hlsConfig = {
                maxBufferLength: 30,
                maxMaxBufferLength: 60,
                enableWorker: true,
                lowLatencyMode: false
            };

            if (Hls.isSupported()) {
                if(hls) hls.destroy();
                hls = new Hls(hlsConfig);
                hls.loadSource(m3u8Url);
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, function() {
                    video.play().catch(() => {});
                });
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = m3u8Url;
                video.addEventListener('loadedmetadata', function() {
                    video.play().catch(() => {});
                });
            }
        }

        video.addEventListener('waiting', () => bufferingSpinner.style.display = 'block');
        video.addEventListener('playing', () => bufferingSpinner.style.display = 'none');

        function togglePlay() {
            if (video.paused) {
                video.play();
                triggerOSD('▶ PLAY');
            } else {
                video.pause();
                triggerOSD('⏸ PAUSA');
            }
            showControlsTemporarily();
        }
        
        playPauseBtn.addEventListener('click', togglePlay);
        video.addEventListener('click', togglePlay);
        video.addEventListener('play', () => playPauseBtn.textContent = '⏸');
        video.addEventListener('pause', () => playPauseBtn.textContent = '▶');

        function formatTime(seconds) {
            if (isNaN(seconds)) return "0:00";
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            const sStr = s < 10 ? '0' + s : s;
            if (h > 0) {
                const mStr = m < 10 ? '0' + m : m;
                return `${h}:${mStr}:${sStr}`;
            }
            return `${m}:${sStr}`;
        }

        video.addEventListener('timeupdate', () => {
            const current = video.currentTime;
            const duration = video.duration;
            if(duration) {
                const pct = (current / duration) * 100;
                progressBar.style.width = `${pct}%`;
                currentTimeEl.textContent = formatTime(current);
            }
        });

        video.addEventListener('loadedmetadata', () => {
            durationTimeEl.textContent = formatTime(video.duration);
        });

        progressArea.addEventListener('click', (e) => {
            const width = progressArea.clientWidth;
            const clickX = e.offsetX;
            const duration = video.duration;
            if(duration) {
                video.currentTime = (clickX / width) * duration;
            }
        });

        volumeSlider.addEventListener('input', (e) => {
            video.volume = e.target.value;
        });

        function togglePseudoFullscreen(forceTrue = false) {
            const isActive = document.body.classList.contains('fullscreen-active');
            if (isActive && !forceTrue) {
                document.body.classList.remove('fullscreen-active');
                if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
            } else {
                document.body.classList.add('fullscreen-active');
                if (playerContainer.requestFullscreen) {
                    playerContainer.requestFullscreen().catch(() => {});
                }
            }
            showControlsTemporarily();
        }

        fullscreenBtn.addEventListener('click', () => togglePseudoFullscreen());

        function showControlsTemporarily() {
            playerContainer.classList.add('show-controls');
            clearTimeout(controlsTimeout);
            controlsTimeout = setTimeout(() => {
                if (!video.paused) playerContainer.classList.remove('show-controls');
            }, 3500);
        }

        playerContainer.addEventListener('mousemove', showControlsTemporarily);

        function triggerOSD(text) {
            osdAlert.textContent = text;
            osdAlert.classList.add('show');
            setTimeout(() => osdAlert.classList.remove('show'), 800);
        }

        window.addEventListener('keydown', function(e) {
            if (!playerContainer.classList.contains('active')) return;
            
            showControlsTemporarily();
            let handled = false;

            switch(e.keyCode) {
                case 39: 
                    video.currentTime = Math.min(video.duration, video.currentTime + 15);
                    triggerOSD('+15s ⏩');
                    handled = true;
                    break;
                case 37: 
                    video.currentTime = Math.max(0, video.currentTime - 15);
                    triggerOSD('-15s ⏪');
                    handled = true;
                    break;
                case 13: 
                case 32:
                    togglePlay();
                    handled = true;
                    break;
                case 415: 
                case 19:  
                case 10252: 
                    togglePlay();
                    handled = true;
                    break;
                case 27:   
                case 10009: 
                    if (document.body.classList.contains('fullscreen-active')) {
                        togglePseudoFullscreen(false);
                        handled = true;
                    }
                    break;
            }

            if (handled) {
                e.preventDefault();
            }
        });
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
║      VixSrc TV Extractor v9                  ║
║      Porta: {port}                            ║
║      Proxy disponibili: {len(PROXY_LIST)}      ║
╚══════════════════════════════════════════════╝
        """)
        app.run(host='0.0.0.0', port=port, debug=False)
