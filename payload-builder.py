#!/usr/bin/env python3
"""
Payload Builder — web UI for generating feature routing override payloads.

Reads active aliases from docker-compose.yml and renders a form to produce
the Base64-encoded JSON payload for the x-hs-request-id header.

Usage:
    python payload-builder.py
    # open http://localhost:8888
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import re
import os

COMPOSE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docker-compose.yml")
PORT = 8888


def get_aliases():
    """Parse active (non-commented) aliases from docker-compose.yml."""
    aliases = []
    try:
        with open(COMPOSE_PATH) as f:
            lines = f.readlines()
        in_aliases = False
        aliases_indent = 0
        for line in lines:
            if line.strip().startswith("#"):
                continue
            if re.search(r"^\s+aliases:\s*$", line):
                in_aliases = True
                aliases_indent = len(line) - len(line.lstrip())
                continue
            if in_aliases:
                m = re.match(r"^(\s+)-\s+(\S+)", line)
                if m and len(m.group(1)) > aliases_indent:
                    alias = m.group(2).split("#")[0].strip()
                    aliases.append(alias)
                elif line.strip():
                    if (len(line) - len(line.lstrip())) <= aliases_indent:
                        in_aliases = False
    except Exception as e:
        print(f"[PAYLOAD-BUILDER] Could not read docker-compose.yml: {e}")
    return aliases


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Feature Routing Payload Builder</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 820px; margin: 40px auto; padding: 0 24px;
      color: #1a1a1a; background: #fafafa;
    }
    h1 { font-size: 1.35rem; margin: 0 0 4px; }
    .subtitle { color: #666; font-size: 0.875rem; margin: 0 0 28px; }
    .subtitle code {
      background: #eef; padding: 1px 5px; border-radius: 3px;
      font-size: 0.85rem; color: #44c;
    }

    .col-headers {
      display: grid; grid-template-columns: 1fr 1fr 32px;
      gap: 10px; margin-bottom: 6px;
    }
    .col-header { font-size: 0.75rem; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: .04em; }

    #rows { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
    .row { display: grid; grid-template-columns: 1fr 1fr 32px; gap: 10px; align-items: center; }

    select, input[type=text] {
      width: 100%; padding: 7px 10px;
      border: 1px solid #d0d0d0; border-radius: 5px;
      font-size: 0.875rem; background: white;
    }
    select:focus, input[type=text]:focus {
      outline: none; border-color: #1a73e8; box-shadow: 0 0 0 2px rgba(26,115,232,.15);
    }

    button { cursor: pointer; border: none; border-radius: 5px; font-size: 0.875rem; }
    .btn-remove {
      width: 32px; height: 32px; background: #fee2e2; color: #b91c1c;
      font-size: 1rem; line-height: 1;
    }
    .btn-remove:hover { background: #fecaca; }
    .btn-add {
      padding: 7px 14px; background: white; border: 1px solid #d0d0d0; color: #333;
    }
    .btn-add:hover { background: #f5f5f5; }
    .btn-build {
      padding: 8px 20px; background: #1a73e8; color: white; font-weight: 500;
    }
    .btn-build:hover { background: #1558b0; }

    .actions { display: flex; gap: 10px; margin-bottom: 28px; }

    .output {
      display: none; background: white; border: 1px solid #d0d0d0;
      border-radius: 8px; padding: 20px;
    }
    .output h2 { margin: 0 0 16px; font-size: 1rem; }
    .output-block { margin-bottom: 16px; }
    .output-block:last-child { margin-bottom: 0; }
    .output-block label {
      display: block; font-size: 0.75rem; font-weight: 600;
      color: #888; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 5px;
    }
    .value-row {
      display: flex; gap: 8px; align-items: stretch;
      background: #f6f8fa; border: 1px solid #d0d0d0;
      border-radius: 5px; padding: 8px 10px;
    }
    .value-row span {
      flex: 1; font-family: monospace; font-size: 0.82rem;
      word-break: break-all; line-height: 1.5;
    }
    .btn-copy {
      flex-shrink: 0; padding: 2px 10px; background: white;
      border: 1px solid #d0d0d0; font-size: 0.78rem; color: #444;
      align-self: flex-start;
    }
    .btn-copy:hover { background: #f0f0f0; }
    .btn-copy.copied { background: #d1fae5; border-color: #6ee7b7; color: #065f46; }
  </style>
</head>
<body>
  <h1>Feature Routing Payload Builder</h1>
  <p class="subtitle">Builds the Base64-encoded JSON payload for <code>x-hs-request-id</code></p>

  <div class="col-headers">
    <span class="col-header">From (current host)</span>
    <span class="col-header">To (target host)</span>
    <span></span>
  </div>
  <div id="rows"></div>

  <div class="actions">
    <button class="btn-add" onclick="addRow()">+ Add entry</button>
    <button class="btn-build" onclick="build()">Build payload</button>
  </div>

  <div class="output" id="output">
    <h2>Generated payload</h2>
    <div class="output-block">
      <label>JSON</label>
      <div class="value-row"><span id="out-json"></span><button class="btn-copy" onclick="copy(this,'out-json')">Copy</button></div>
    </div>
    <div class="output-block">
      <label>Base64</label>
      <div class="value-row"><span id="out-b64"></span><button class="btn-copy" onclick="copy(this,'out-b64')">Copy</button></div>
    </div>
    <div class="output-block">
      <label>x-hs-request-id header value</label>
      <div class="value-row"><span id="out-header"></span><button class="btn-copy" onclick="copy(this,'out-header')">Copy</button></div>
    </div>
  </div>

  <script>
    const ALIASES = __ALIASES__;

    function aliasOptions(selected) {
      return '<option value="">— select alias —</option>' +
        ALIASES.map(a =>
          `<option value="${a}"${a === selected ? ' selected' : ''}>${a}</option>`
        ).join('');
    }

    function addRow(key = '', value = '') {
      const container = document.getElementById('rows');
      const row = document.createElement('div');
      row.className = 'row';

      const sel = document.createElement('select');
      sel.innerHTML = aliasOptions(key);

      const inp = document.createElement('input');
      inp.type = 'text';
      inp.placeholder = 'target hostname';
      inp.value = value;

      const btn = document.createElement('button');
      btn.className = 'btn-remove';
      btn.textContent = '✕';
      btn.title = 'Remove';
      btn.onclick = () => row.remove();

      row.append(sel, inp, btn);
      container.appendChild(row);
    }

    function build() {
      const rows = document.querySelectorAll('#rows .row');
      const obj = {};
      for (const row of rows) {
        const key = row.querySelector('select').value;
        const val = row.querySelector('input').value.trim();
        if (key && val) obj[key] = val;
      }
      if (!Object.keys(obj).length) {
        alert('Add at least one complete entry (both from and to must be filled).');
        return;
      }
      const jsonStr = JSON.stringify(obj);
      const b64 = btoa(jsonStr);
      const header = `1234-0000-0001::${b64}`;

      document.getElementById('out-json').textContent = jsonStr;
      document.getElementById('out-b64').textContent = b64;
      document.getElementById('out-header').textContent = header;
      document.getElementById('output').style.display = 'block';
    }

    function copy(btn, id) {
      navigator.clipboard.writeText(document.getElementById(id).textContent).then(() => {
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1500);
      });
    }

    addRow();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        aliases = get_aliases()
        body = HTML.replace("__ALIASES__", json.dumps(aliases)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[PAYLOAD-BUILDER] {args[0]} {args[1]}")


if __name__ == "__main__":
    print(f"[PAYLOAD-BUILDER] Listening on http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
