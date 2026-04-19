#!/usr/bin/env python3
"""
Simple SSE (Server-Sent Events) test server for testing the C client.

Usage:
    python3 test_server.py [port]

Default port is 5344.
"""

import asyncio
import sys
import random
import json
from datetime import datetime

async def sse_handler(request):
    """Handle SSE connection"""
    from aiohttp import web
    
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        }
    )
    await response.prepare(request)
    
    client_id = random.randint(1000, 9999)
    print(f"[{datetime.now()}] Client {client_id} connected")
    
    counter = 0
    try:
        while True:
            counter += 1
            
            # Send different types of events
            if counter % 5 == 0:
                # Special event type
                data = json.dumps({
                    "type": "heartbeat",
                    "client_id": client_id,
                    "counter": counter,
                    "timestamp": datetime.now().isoformat()
                })
                await response.write(f"event: heartbeat\n".encode())
                await response.write(f"id: msg-{counter}\n".encode())
                await response.write(f"data: {data}\n\n".encode())
            else:
                # Regular message event
                data = json.dumps({
                    "message": f"Hello from server! Count: {counter}",
                    "client_id": client_id,
                    "random": random.randint(1, 100)
                })
                await response.write(f"event: message\n".encode())
                await response.write(f"id: msg-{counter}\n".encode())
                await response.write(f"data: {data}\n\n".encode())
            
            await response.drain()
            
            # Random delay between 0.5 and 2 seconds
            await asyncio.sleep(random.uniform(0.5, 2.0))
            
    except asyncio.CancelledError:
        print(f"[{datetime.now()}] Client {client_id} disconnected")
        raise
    except Exception as e:
        print(f"[{datetime.now()}] Client {client_id} error: {e}")
    
    return response


async def index_handler(request):
    """Serve a simple HTML page with SSE client"""
    from aiohttp import web
    
    html = """<!DOCTYPE html>
<html>
<head>
    <title>SSE Test</title>
    <style>
        body { font-family: monospace; margin: 20px; }
        #events { border: 1px solid #ccc; padding: 10px; height: 400px; overflow-y: scroll; }
        .event { margin: 5px 0; padding: 5px; background: #f0f0f0; }
        .heartbeat { background: #e0f0e0; }
    </style>
</head>
<body>
    <h1>SSE Test Client</h1>
    <div id="events"></div>
    <script>
        const events = document.getElementById('events');
        const evtSource = new EventSource('/stream');
        
        evtSource.addEventListener('message', function(e) {
            const div = document.createElement('div');
            div.className = 'event';
            div.textContent = 'Message: ' + e.data;
            events.insertBefore(div, events.firstChild);
        });
        
        evtSource.addEventListener('heartbeat', function(e) {
            const div = document.createElement('div');
            div.className = 'event heartbeat';
            div.textContent = 'Heartbeat: ' + e.data;
            events.insertBefore(div, events.firstChild);
        });
        
        evtSource.onerror = function(e) {
            console.log('Error:', e);
        };
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')


async def main():
    try:
        from aiohttp import web
    except ImportError:
        print("Error: aiohttp is required. Install with: pip install aiohttp")
        sys.exit(1)
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5344
    
    app = web.Application()
    app.router.add_get('/', index_handler)
    app.router.add_get('/stream', sse_handler)
    
    print(f"SSE Test Server running on http://127.0.0.1:{port}")
    print(f"Endpoints:")
    print(f"  - http://127.0.0.1:{port}/       (Web UI)")
    print(f"  - http://127.0.0.1:{port}/stream (SSE stream)")
    print(f"\nPress Ctrl+C to stop")
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', port)
    await site.start()
    
    # Run forever
    while True:
        await asyncio.sleep(3600)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")
