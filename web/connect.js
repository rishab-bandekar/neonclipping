/* NeonClipping website: shows the normal NeonClipping interface, but every request goes to the NeonClipping engine on
   the visitor's own computer (http://127.0.0.1:8770). Downloads, speech models and rendering never touch this website.
   build_web.py writes the site settings {api, css, js} into <script type="application/json" id="nc-site">. */
(function () {
  'use strict';
  var SITE = {};
  try { SITE = JSON.parse(document.getElementById('nc-site').textContent); } catch (e) {}
  var KEY_ENGINE = 'nc-engine', KEY_TOKEN = 'nc-token', HEADER = 'X-NeonClipping-Token';
  var LOOPBACK = /^http:\/\/(127\.0\.0\.1|localhost):(\d{2,5})$/;   // never let a link point the page at another server

  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function save(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }

  // 1. Pairing link from the engine's /open: #engine=http://127.0.0.1:8770&pair=TOKEN. The part after # never
  //    reaches this website's server. Remove it from the address bar straight away.
  var hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get('pair')) {
    save(KEY_TOKEN, hash.get('pair'));
    if (LOOPBACK.test(hash.get('engine') || '')) save(KEY_ENGINE, hash.get('engine'));
    history.replaceState(null, '', location.pathname + location.search);
  }
  var engine = LOOPBACK.test(load(KEY_ENGINE) || '') ? load(KEY_ENGINE) : 'http://127.0.0.1:8770';
  var nativeFetch = window.fetch.bind(window);

  function isEngine(url) {
    try { return new URL(url, document.baseURI).origin === engine; } catch (e) { return false; }
  }

  // 2. Every request the interface makes to the engine carries the pairing token.
  window.fetch = function (input, init) {
    var raw = input instanceof Request ? input.url : String(input);
    if (!isEngine(raw)) return nativeFetch(input, init);
    var request = input instanceof Request ? new Request(input, init) : new Request(new URL(raw, document.baseURI).href, init);
    request.headers.set(HEADER, load(KEY_TOKEN) || '');
    return nativeFetch(request).then(function (r) {
      if (r.status === 401 && mounted) panel('pair', 'This browser is no longer paired with NeonClipping.');
      return r;
    });
  };

  // 3. <a download> cannot save a file that lives on another address, so fetch it and save it from here.
  function download(a) {
    var url = new URL(a.getAttribute('href') || a.href, document.baseURI);
    if (url.origin !== engine) return false;
    var name = a.getAttribute('download') || url.pathname.split('/').pop();
    window.fetch(url.href).then(function (r) {
      if (!r.ok) throw Error(r.status);
      return r.blob();
    }).then(function (blob) {
      var link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = name;
      document.body.appendChild(link);
      HTMLAnchorElement.prototype.click.call(link);
      setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 60000);
    }).catch(function () {                       // very large file or blocked fetch: let the engine send it as a download
      url.searchParams.set('dl', '1');
      url.searchParams.set('name', name);
      var frame = document.createElement('iframe');
      frame.hidden = true;
      frame.src = url.href;
      document.body.appendChild(frame);
      setTimeout(function () { frame.remove(); }, 120000);
    });
    return true;
  }
  document.addEventListener('click', function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('a[download]') : null;
    if (a && !ev.defaultPrevented && download(a)) ev.preventDefault();
  }, true);
  var nativeClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (!this.isConnected && this.hasAttribute('download') && !/^(blob|data):/.test(this.href) && download(this)) return;
    return nativeClick.call(this);
  };

  // 4. Status screens shown until the engine answers.
  var mounted = false, retry = null;
  var MESSAGES = {
    checking: '<h1>Connecting to NeonClipping…</h1><p>Looking for the NeonClipping app on this computer.</p>' +
      '<p class="nc-small">If your browser asks whether this site may connect to apps or devices on this computer, choose <b>Allow</b>.</p>',
    missing: '<h1>NeonClipping is not running on this computer</h1>' +
      '<p>This website is only the screen. The clipping itself (downloads, speech recognition, rendering) runs on your own computer and graphics card, so the app has to be installed once.</p>' +
      '<ol><li><b>Windows:</b> <a href="' + location.origin + '/NeonClipping-Setup.bat" download>download NeonClipping-Setup.bat</a> and double-click it. It installs Python, FFmpeg and NeonClipping, then opens this page connected.</li>' +
      '<li><b>Mac / Linux:</b> run <code>curl -fsSL ' + location.origin + '/install.sh | bash</code> in a terminal.</li>' +
      '<li><b>Already installed?</b> Start it from the <i>NeonClipping</i> desktop shortcut. This page connects by itself.</li></ol>' +
      '<p class="nc-small">If your browser asked whether this site may connect to apps or devices on this computer, choose <b>Allow</b>. If you chose Block, allow it again from the lock icon next to the address.</p>' +
      '<p class="nc-small">NeonClipping on another port? <input id="nc-engine" value="' + engine + '"> <button id="nc-use">Use</button></p>',
    pair: '<h1>Pair this browser</h1>' +
      '<p>NeonClipping is running, but this browser is not paired with it yet.</p>' +
      '<p>Start NeonClipping from its desktop shortcut and it opens this page already paired, or open <a href="' + engine + '/pair" target="_blank" rel="noopener">' + engine + '/pair</a> on this computer, copy the code and paste it here:</p>' +
      '<p><input id="nc-code" placeholder="Pairing code" autocomplete="off"> <button id="nc-pair">Pair</button></p>',
    old: '<h1>Please update NeonClipping</h1><p>The NeonClipping app on this computer is older than this website. Press <b>Update now</b> in the app, or run <a href="' + location.origin + '/NeonClipping-Setup.bat" download>NeonClipping-Setup.bat</a> again.</p>'
  };

  function panel(kind, note) {
    var box = document.getElementById('nc-connect');
    if (!box) {
      box = document.createElement('div');
      box.id = 'nc-connect';
      document.body.appendChild(box);
    }
    box.className = mounted ? 'nc-overlay' : '';
    box.innerHTML = '<div class="nc-card">' + (note ? '<p class="nc-note">' + note + '</p>' : '') + MESSAGES[kind] +
      (kind === 'checking' ? '' : '<p><button id="nc-retry">Try again</button></p>') + '</div>';
    bind('nc-retry', function () { start(); });
    bind('nc-use', function () {
      var value = document.getElementById('nc-engine').value.trim().replace(/\/+$/, '');
      if (!LOOPBACK.test(value)) { alert('Use an address like http://127.0.0.1:8770'); return; }
      save(KEY_ENGINE, value);
      location.reload();
    });
    bind('nc-pair', function () {
      var code = document.getElementById('nc-code').value.trim();
      if (code) { save(KEY_TOKEN, code); if (mounted) location.reload(); else start(); }
    });
    clearTimeout(retry);
    if (kind === 'missing' && !mounted) retry = setTimeout(start, 4000);   // connect as soon as the app is started
  }

  function bind(id, fn) { var el = document.getElementById(id); if (el) el.onclick = fn; }

  function start() {
    if (!mounted) panel('checking');
    // 15 s: long enough to answer a browser permission prompt. A stopped app fails at once (connection refused).
    var timeout = new Promise(function (_, reject) { setTimeout(function () { reject(Error('timeout')); }, 15000); });
    Promise.race([window.fetch(engine + '/remote/hello'), timeout]).then(function (r) { return r.json(); }).then(function (j) {
      if (!j || typeof j.api !== 'number') return panel('missing');
      if (j.api < (SITE.api || 1)) return panel('old');
      if (!j.paired) return panel('pair');
      mount();
    }).catch(function () { panel('missing'); });
  }

  // 5. Show the real interface: relative addresses now point at the engine, the files themselves come from here.
  function mount() {
    if (mounted) return;
    mounted = true;
    clearTimeout(retry);
    var here = location.origin + location.pathname.replace(/[^/]*$/, '');
    var base = document.createElement('base');
    base.href = engine + '/';
    document.head.insertBefore(base, document.head.firstChild);
    (SITE.css || []).forEach(function (href) {
      var link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = here + href;
      document.head.appendChild(link);
    });
    var app = document.getElementById('nc-app');
    document.body.replaceChildren(document.importNode(app.content, true));
    var brand = document.querySelector('a.brand');
    if (brand) brand.href = here;                 // the logo reloads this website, not the app on the computer
    (SITE.js || []).forEach(function (src) {
      var script = document.createElement('script');
      script.src = here + src;
      script.async = false;                       // keep the original order
      document.body.appendChild(script);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
