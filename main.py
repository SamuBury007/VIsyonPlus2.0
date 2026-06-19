#!/usr/bin/env python3

"""
VixSrc M3U8 Extractor v5 - Con supporto SOCKS5 e HTTP proxy
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
import socket
import socks

app = Flask(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# URL per scaricare proxy HTTP e SOCKS
PROXY_URLS = [
    "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/socks4.txt",
    "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/socks5.txt"
]

def fetch_all_proxies():
    """Scarica proxy da tutte le fonti"""
    all_proxies = []
    
    for url in PROXY_URLS:
        try:
            print(f"[*] Scaricando da: {url}")
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                proxies = [line.strip() for line in response.text.split('\n') if line.strip()]
                # Determina il tipo in base all'URL
                if "socks4" in url:
                    proxies = [f"socks4://{p}" for p in proxies]
                elif "socks5" in url:
                    proxies = [f"socks5://{p}" for p in proxies]
                else:
                    proxies = [f"http://{p}" for p in proxies]
                all_proxies.extend(proxies)
                print(f"[+] Aggiunti {len(proxies)} proxy da {url}")
        except Exception as e:
            print(f"[-] Errore scaricamento {url}: {e}")
    
    return all_proxies

def test_proxy_quick(proxy_url):
    """Test veloce di un proxy"""
    try:
        # Pulisci l'URL del proxy
        proxy_url_clean = proxy_url.replace("http://", "").replace("https://", "").replace("socks4://", "").replace("socks5://", "")
        
        # Se è SOCKS, testa direttamente la connessione
        if "socks" in proxy_url:
            parts = proxy_url_clean.split(":")
            if len(parts) == 2:
                ip, port = parts[0], int(parts[1])
                try:
                    sock = socks.socksocket()
                    sock.set_proxy(socks.SOCKS5 if "socks5" in proxy_url else socks.SOCKS4, ip, port)
                    sock.settimeout(3)
                    sock.connect(("httpbin.org", 80))
                    sock.close()
                    return True, 0.5
                except:
                    return False, None
        
        # Per HTTP, testa con requests
        proxies = {
            "http": proxy_url,
            "https": proxy_url.replace("http://", "https://") if "http://" in proxy_url else proxy_url
        }
        response = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=3)
        if response.status_code == 200:
            return True, response.elapsed.total_seconds()
        return False, None
    except:
        return False, None

def get_working_proxy():
    """Trova il miglior proxy funzionante"""
    print("[*] Scaricando lista proxy...")
    all_proxies = fetch_all_proxies()
    
    if not all_proxies:
        print("[-] Nessun proxy scaricato, uso fallback")
        # Fallback con proxy noti che potrebbero funzionare
        all_proxies = [
            "http://34.43.46.91:80",
            "http://159.65.221.25:80",
            "http://142.93.202.130:3128",
            "http://104.154.186.48:80",
            "socks5://51.222.40.207:1080"
        ]
    
    # Mescola per varietà
    random.shuffle(all_proxies)
    
    print(f"[*] Testando proxy (primi 20)...")
    
    for proxy in all_proxies[:20]:
        is_working, latency = test_proxy_quick(proxy)
        if is_working:
            print(f"[+] Proxy funzionante: {proxy} (latenza: {latency:.2f}s)")
            return proxy
    
    print("[-] Nessun proxy funzionante trovato")
    return None

async def extract_playlist_url(movie_url):
    """Estrae la playlist usando Playwright con proxy"""
    playlist_urls = []
    
    from playwright.async_api import async_playwright
    
    proxy_url = get_working_proxy()
    proxy_config = None
    
    if proxy_url:
        print(f"[*] Utilizzo proxy: {proxy_url}")
        # Configura proxy per Playwright
        if proxy_url.startswith("http"):
            proxy_parts = proxy_url.replace("http://", "").replace("https://", "").split(":")
            if len(proxy_parts) == 2:
                proxy_config = {
                    "server": f"http://{proxy_parts[0]}:{proxy_parts[1]}"
                }
        elif "socks5" in proxy_url:
            proxy_parts = proxy_url.replace("socks5://", "").split(":")
            if len(proxy_parts) == 2:
                proxy_config = {
                    "server": f"socks5://{proxy_parts[0]}:{proxy_parts[1]}"
                }
    
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
                '--disable-gpu',
                '--disable-extensions',
                '--disable-component-extensions-with-background-pages',
                '--disable-default-apps',
                '--mute-audio',
                '--no-default-browser-check',
                '--no-first-run',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
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
            
            # Script anti-detect
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['it-IT', 'it', 'en-US', 'en'] });
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
            
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
            
            # Naviga con più tentativi
            for attempt in range(3):
                try:
                    await page.goto(movie_url, wait_until="domcontentloaded", timeout=45000)
                    break
                except Exception as e:
                    print(f"   Tentativo {attempt+1} fallito: {e}")
                    await asyncio.sleep(2)
            
            # Aspetta e scorri
            for i in range(15):
                await asyncio.sleep(1)
                if playlist_urls:
                    print(f"   [+] Trovati {len(playlist_urls)} link")
                    break
                if i % 3 == 0:
                    await page.evaluate(f"window.scrollBy(0, {100 + i*50})")
            
            # Estrai via JS
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
            except:
                pass
            
            await browser.close()
            
        except Exception as e:
            print(f"[-] Errore Playwright: {e}")
    
    return playlist_urls

# Il resto del codice (get_best_playlist, Flask routes, HTML) rimane identico
# ... (copiare dal codice precedente)
