// Einstellungen: TMDB-Schlüssel, aktive Abos, Importe (IMDb-CSV, TMDB-Konto, Titelliste), Wartung.
import { api, IMG } from '../api.js';
import { h, toast, fmtDate } from '../ui.js';
import { watchJobs } from '../app.js';

export async function render(root, params) {
  let st;
  try { st = await api.status(); } catch (e) { root.append(h('div', { class: 'glass panel' }, h('p', {}, e.message))); return {}; }

  const head = h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Einstellungen ⚙️'), h('div', { class: 'sub' }, params.welcome ? 'Willkommen! Hinterlege zuerst deinen TMDB-API-Schlüssel.' : 'Anbieter, Datenquellen und Importe.')));
  root.append(head);
  if (params.tmdb === 'connected') toast('TMDB-Konto verbunden', 'ok');

  // ---------- TMDB-Schlüssel ----------
  const keyInput = h('input', { type: 'password', placeholder: st.has_key ? `Hinterlegt (${st.key_masked}) – zum Ändern neu eingeben` : 'API Key (v3) oder Read Access Token (v4)', style: { width: '100%' } });
  const keyPanel = h('div', { class: 'glass panel' },
    h('h2', {}, '🔑 TMDB-API-Schlüssel'),
    h('p', { class: 'muted small' }, 'Kostenlos unter ', h('a', { href: 'https://www.themoviedb.org/settings/api', target: '_blank', rel: 'noopener', style: { color: 'var(--accent)' } }, 'themoviedb.org → Einstellungen → API'), ' (in deinem Konto „gogoweb“). Der Schlüssel bleibt lokal in der Datenbank.'),
    h('div', { class: 'row', style: { marginTop: '10px' } }, h('div', { class: 'grow' }, keyInput),
      h('button', { class: 'btn primary', onClick: async () => {
        const key = keyInput.value.trim();
        if (!key) return toast('Bitte Schlüssel eingeben', 'err');
        try { await api.settings({ tmdb_api_key: key }); toast('Schlüssel gespeichert, Anbieter geladen', 'ok'); history.replaceState(null, '', '#/settings'); root.innerHTML = ''; render(root, {}); }
        catch (e) { toast(e.message, 'err'); }
      } }, 'Speichern')),
    st.has_key ? h('p', { class: 'small', style: { color: 'var(--ok)' } }, '✓ Schlüssel aktiv') : h('p', { class: 'small', style: { color: 'var(--warn)' } }, 'Noch kein Schlüssel – ohne ihn funktionieren Suche, Entdecken und Importe nicht.'),
  );

  // ---------- Aktive Abos ----------
  const provList = h('div', { class: 'prov-list' });
  const provSearch = h('input', { type: 'search', placeholder: 'Anbieter suchen (z. B. Disney, Paramount, WOW, Joyn) …', style: { width: '100%' } });
  let providers = [];
  const drawProviders = () => {
    provList.innerHTML = '';
    const q = provSearch.value.trim().toLowerCase();
    const list = providers.filter((p) => p.active || (q && p.name.toLowerCase().includes(q)));
    if (!list.length) provList.append(h('span', { class: 'muted small' }, q ? 'Kein Anbieter gefunden.' : 'Keine aktiven Anbieter.'));
    for (const p of list) {
      provList.append(h('div', { class: `prov-item ${p.active ? 'on' : 'off'}`, onClick: async () => {
        try { await api.toggleProvider(p.id, !p.active); p.active = !p.active; drawProviders(); toast(`${p.name} ${p.active ? 'aktiviert' : 'deaktiviert'}`, 'ok'); }
        catch (e) { toast(e.message, 'err'); }
      } }, p.logo_path ? h('img', { src: IMG(p.logo_path, 'w92'), alt: '' }) : null, p.name, h('span', {}, p.active ? '✓' : '+')));
    }
  };
  provSearch.addEventListener('input', drawProviders);
  const provPanel = h('div', { class: 'glass panel' },
    h('h2', {}, '📡 Aktive Abos & Quellen'),
    h('p', { class: 'muted small' }, 'Titel gelten als „bei meinen Anbietern verfügbar“, wenn sie hier aktiv sind (Abo/Flatrate oder kostenlos). Zum Hinzufügen einfach suchen und anklicken.'),
    provSearch, h('div', { style: { height: '10px' } }), provList,
    h('label', { class: 'toggle small', style: { marginTop: '14px' } },
      h('input', { type: 'checkbox', checked: !!st.settings.count_all_free, onChange: async (e) => { await api.settings({ count_all_free: e.target.checked }); toast('Gespeichert', 'ok'); } }),
      h('span', { class: 'sw' }), 'Kostenlose Angebote aller Anbieter (z. B. Joyn, Pluto TV) als verfügbar zählen'),
  );
  if (st.has_key) {
    try { providers = await api.providers(); drawProviders(); } catch (e) { provList.append(h('span', { class: 'muted small' }, e.message)); }
  } else provList.append(h('span', { class: 'muted small' }, 'Zuerst TMDB-Schlüssel hinterlegen.'));

  // ---------- IMDb-Import ----------
  const imdbMode = h('select', {}, h('option', { value: 'ratings' }, 'Bewertungen (ratings.csv)'), h('option', { value: 'watchlist' }, 'Watchlist (WATCHLIST.csv)'));
  const fileInput = h('input', { type: 'file', accept: '.csv,text/csv', style: { display: 'none' } });
  const drop = h('div', { class: 'dropzone' }, '📄 CSV hierher ziehen oder klicken');
  drop.addEventListener('click', () => fileInput.click());
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  const upload = async (file) => {
    if (!file) return;
    const fd = new FormData(); fd.append('file', file); fd.append('mode', imdbMode.value);
    try { const r = await api.form('/import/imdb', fd); toast(`Import gestartet: ${r.rows} Zeilen`, 'ok'); watchJobs(); }
    catch (e) { toast(e.message, 'err'); }
  };
  drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); upload(e.dataTransfer.files[0]); });
  fileInput.addEventListener('change', () => { upload(fileInput.files[0]); fileInput.value = ''; });
  const imdbPanel = h('div', { class: 'glass panel' },
    h('h2', {}, '🎞 IMDb-Import (Konto gogo-27)'),
    h('p', { class: 'muted small' }, 'IMDb bietet keinen API-Zugriff auf dein Konto, aber einen CSV-Export: ',
      h('a', { href: 'https://www.imdb.com/list/ratings/', target: '_blank', rel: 'noopener', style: { color: 'var(--accent)' } }, 'Deine Bewertungen'), ' bzw. ',
      h('a', { href: 'https://www.imdb.com/list/watchlist/', target: '_blank', rel: 'noopener', style: { color: 'var(--accent)' } }, 'Watchlist'),
      ' → Menü „⋮“ → „Export“. Die CSV dann hier hochladen. Wiederholte Importe aktualisieren nur.'),
    h('div', { class: 'row', style: { margin: '10px 0' } }, h('label', { class: 'field' }, 'Was importieren?', imdbMode),
      h('label', { class: 'field' }, 'Bewertung ≤ … = „Kein Interesse“',
        h('select', { onChange: async (e) => { await api.settings({ dislike_threshold: +e.target.value }); toast('Gespeichert', 'ok'); } },
          ...[1, 2, 3, 4].map((n) => h('option', { value: n, selected: (st.settings.dislike_threshold ?? 1) === n }, n))))),
    drop, fileInput,
  );

  // ---------- Schauspieler-Import ----------
  const pFile = h('input', { type: 'file', accept: '.csv,text/csv', style: { display: 'none' } });
  const pDrop = h('div', { class: 'dropzone' }, '🎭 IMDb-Personenliste (CSV) hierher ziehen oder klicken');
  pDrop.addEventListener('click', () => pFile.click());
  pDrop.addEventListener('dragover', (e) => { e.preventDefault(); pDrop.classList.add('over'); });
  pDrop.addEventListener('dragleave', () => pDrop.classList.remove('over'));
  const pUpload = async (file) => {
    if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    try { const r = await api.form('/people/import', fd); toast(`Schauspieler-Import gestartet: ${r.rows} Personen`, 'ok'); watchJobs(); }
    catch (e) { toast(e.message, 'err'); }
  };
  pDrop.addEventListener('drop', (e) => { e.preventDefault(); pDrop.classList.remove('over'); pUpload(e.dataTransfer.files[0]); });
  pFile.addEventListener('change', () => { pUpload(pFile.files[0]); pFile.value = ''; });
  const peoplePanel = h('div', { class: 'glass panel' },
    h('h2', {}, '🎭 Schauspieler-Favoriten importieren'),
    h('p', { class: 'muted small' }, 'IMDb-Liste mit Personen (z. B. deine Favoriten) exportieren und die CSV hier hochladen. Die Personen werden über die IMDb-ID (nm…) TMDB zugeordnet und als Favoriten angelegt, inklusive Filmografie.'),
    pDrop, pFile,
  );

  // ---------- TMDB-Konto ----------
  const tmdbPanel = h('div', { class: 'glass panel' },
    h('h2', {}, '🎬 TMDB-Konto (gogoweb)'),
    st.tmdb_connected
      ? [h('p', { class: 'small', style: { color: 'var(--ok)' } }, `✓ Verbunden als ${st.tmdb_username || 'TMDB-Nutzer'}`),
        h('div', { class: 'row' },
          h('button', { class: 'btn primary', onClick: async () => { try { await api.post('/tmdb/sync'); toast('TMDB-Sync gestartet', 'ok'); watchJobs(); } catch (e) { toast(e.message, 'err'); } } }, '⇅ Watchlist & Bewertungen importieren'),
          h('button', { class: 'btn danger', onClick: async () => { await api.del('/tmdb/auth'); toast('Getrennt'); root.innerHTML = ''; render(root, {}); } }, 'Trennen')),
        h('p', { class: 'muted small', style: { marginTop: '12px' } }, 'TMDB ist die zentrale Quelle für Bewertungen und Watchlist: Änderungen in der App werden sofort zu TMDB übertragen, beim Sync gewinnt TMDB. IMDb hat keine Schreib-Schnittstelle.'),
        h('label', { class: 'toggle small', style: { marginTop: '8px' } },
          h('input', { type: 'checkbox', checked: st.settings.tmdb_mirror_ratings !== false, onChange: async (e) => { await api.settings({ tmdb_mirror_ratings: e.target.checked }); toast('Gespeichert', 'ok'); } }),
          h('span', { class: 'sw' }), 'Bewertungen zu TMDB spiegeln (auch „Kein Interesse“ = 1)'),
        h('label', { class: 'toggle small', style: { marginTop: '8px' } },
          h('input', { type: 'checkbox', checked: st.settings.tmdb_mirror_watchlist !== false, onChange: async (e) => { await api.settings({ tmdb_mirror_watchlist: e.target.checked }); toast('Gespeichert', 'ok'); } }),
          h('span', { class: 'sw' }), 'Watchlist-Änderungen zu TMDB spiegeln')]
      : [h('p', { class: 'muted small' }, 'Verbinde dein TMDB-Konto, um Watchlist und Bewertungen von dort zu importieren (und optional die Watchlist zu spiegeln). Eigene Bewertungen aus IMDb haben Vorrang.'),
        h('div', { class: 'row' },
          h('button', { class: 'btn primary', disabled: !st.has_key, onClick: async () => {
            try { const r = await api.post('/tmdb/auth/start'); window.open(r.approve_url, '_blank'); toast('Bitte im neuen Tab bestätigen', 'ok'); }
            catch (e) { toast(e.message, 'err'); }
          } }, 'Mit TMDB verbinden'),
          h('button', { class: 'btn', disabled: !st.has_key, title: 'Falls die Rückleitung nicht klappt: nach dem Bestätigen hier klicken', onClick: async () => {
            try { const r = await api.post('/tmdb/auth/finish'); toast(`Verbunden als ${r.username}`, 'ok'); root.innerHTML = ''; render(root, {}); } catch (e) { toast(e.message, 'err'); }
          } }, 'Verbindung abschließen'))],
  );

  // ---------- Titelliste (JustWatch) ----------
  const listText = h('textarea', { placeholder: 'Ein Titel pro Zeile, optional mit Jahr:\nThe Bear 2022\nOppenheimer (2023)\nSeverance' });
  const listStatus = h('select', {}, h('option', { value: 'watchlist' }, 'Watchlist'), h('option', { value: 'watching' }, 'Serie verfolgen'), h('option', { value: 'watched' }, 'Gesehen'));
  const listType = h('select', {}, h('option', { value: '' }, 'Film oder Serie (automatisch)'), h('option', { value: 'movie' }, 'nur Filme'), h('option', { value: 'tv' }, 'nur Serien'));
  const listPanel = h('div', { class: 'glass panel' },
    h('h2', {}, '📋 Titelliste importieren (z. B. aus JustWatch)'),
    h('p', { class: 'muted small' }, 'JustWatch hat keinen Export und keine offene Schnittstelle. Kopiere stattdessen die Titel deiner Watchlist bzw. deiner verfolgten Serien als Text hier hinein – sie werden über TMDB aufgelöst (Jahr hilft bei Mehrdeutigkeit).'),
    listText,
    h('div', { class: 'row', style: { marginTop: '10px' } }, listStatus, listType, h('span', { class: 'grow' }),
      h('button', { class: 'btn primary', disabled: !st.has_key, onClick: async () => {
        if (!listText.value.trim()) return toast('Liste ist leer', 'err');
        try { await api.post('/import/list', { text: listText.value, status: listStatus.value, media_type: listType.value || null }); toast('Listen-Import gestartet', 'ok'); watchJobs(); listText.value = ''; }
        catch (e) { toast(e.message, 'err'); }
      } }, 'Importieren')),
  );

  // ---------- Daten & Wartung ----------
  const s = st.stats;
  const cnt = (k) => Object.values(s[k] || {}).reduce((a, b) => a + b, 0);
  const jobLog = h('div', { class: 'log' });
  const loadJobs = async () => {
    try {
      const r = await api.jobs();
      jobLog.innerHTML = '';
      const all = [...r.running, ...r.recent.filter((j) => j.status !== 'running')];
      if (!all.length) jobLog.append(h('div', { class: 'muted' }, 'Noch keine Jobs.'));
      for (const j of all) {
        const row = h('div', {}, h('b', {}, `${j.kind}`), ` · ${j.status} · ${j.message || ''}`);
        if (j.kind.startsWith('import') && j.status !== 'running') {
          row.append(' ', h('a', { href: '#', style: { color: 'var(--accent)' }, onClick: async (e) => {
            e.preventDefault();
            const d = await api.job(j.id);
            const box = h('div', { class: 'log', style: { marginTop: '6px' } });
            const problems = d.log.filter((l) => !/^übersprungen \(TV Episode\)/.test(l.result));
            if (!problems.length) box.append(h('div', {}, 'Keine Auffälligkeiten.'));
            problems.forEach((l) => box.append(h('div', {}, `${l.title} (${l.ref}): ${l.result}`)));
            row.append(box);
          } }, 'Details'));
        }
        jobLog.append(row);
      }
    } catch { /* ignorieren */ }
  };
  const dataPanel = h('div', { class: 'glass panel' },
    h('h2', {}, '🗄 Daten & Wartung'),
    h('dl', { class: 'kv' },
      h('dt', {}, 'Gesehen'), h('dd', {}, `${cnt('watched')} (${s.watched?.movie || 0} Filme, ${s.watched?.tv || 0} Serien)`),
      h('dt', {}, 'Kein Interesse'), h('dd', {}, cnt('disliked')),
      h('dt', {}, 'Watchlist'), h('dd', {}, cnt('watchlist')),
      h('dt', {}, 'Verfolgte Serien'), h('dd', {}, cnt('watching')),
      h('dt', {}, 'Eigene Bewertungen'), h('dd', {}, `${s.ratings?.n || 0} · Ø ${s.ratings?.avg ? s.ratings.avg.toFixed(1) : '–'}`),
      h('dt', {}, 'IMDb-Bewertungen (Datensatz)'), h('dd', {}, `${(s.imdb_dataset?.n || 0).toLocaleString('de-DE')} Titel · Stand ${s.imdb_dataset_updated ? fmtDate(s.imdb_dataset_updated) : 'nie'}`),
      h('dt', {}, 'Titel im Cache'), h('dd', {}, s.titles_cached)),
    h('div', { class: 'row', style: { margin: '12px 0' } },
      h('button', { class: 'btn', onClick: async () => { try { await api.post('/imdb/dataset'); toast('IMDb-Datensatz wird geladen (~7 MB)', 'ok'); watchJobs(); } catch (e) { toast(e.message, 'err'); } } }, '↻ IMDb-Bewertungen aktualisieren'),
      h('button', { class: 'btn', disabled: !st.has_key, onClick: async () => { try { await api.post('/library/refresh'); toast('Bibliothek wird aktualisiert', 'ok'); watchJobs(); } catch (e) { toast(e.message, 'err'); } } }, '↻ Verfügbarkeiten aktualisieren'),
      h('button', { class: 'btn', disabled: !st.has_key, title: 'IMDb-ID, FSK und Anbieter für alle importierten Titel nachladen', onClick: async () => { try { await api.post('/library/refresh?everything=true'); toast('Details werden für alle Titel nachgeladen', 'ok'); watchJobs(); } catch (e) { toast(e.message, 'err'); } } }, '↻ Alle Titel vervollständigen'),
      h('button', { class: 'btn', disabled: !st.has_key, onClick: async () => { try { await api.post('/providers/refresh'); toast('Anbieterliste aktualisiert', 'ok'); providers = await api.providers(); drawProviders(); } catch (e) { toast(e.message, 'err'); } } }, '↻ Anbieterliste'),
      h('a', { class: 'btn', href: '/api/export', download: 'streamguide-export.json' }, '⬇ Bibliothek exportieren (JSON)')),
    h('p', { class: 'muted small' }, 'Der IMDb-Datensatz (offizielle title.ratings) wird beim Start automatisch aktualisiert, wenn er älter als 7 Tage ist. Version ', h('code', {}, st.version || '?'), '.'),
    h('h3', { style: { marginTop: '10px' } }, 'Letzte Jobs'), jobLog,
  );
  loadJobs();

  // ---------- Sicherung ----------
  const bakFile = h('input', { type: 'file', accept: '.zip,application/zip', style: { display: 'none' } });
  const bakDrop = h('div', { class: 'dropzone' }, '📦 Sicherung (ZIP) hierher ziehen oder klicken – ersetzt alle Daten');
  bakDrop.addEventListener('click', () => bakFile.click());
  bakDrop.addEventListener('dragover', (e) => { e.preventDefault(); bakDrop.classList.add('over'); });
  bakDrop.addEventListener('dragleave', () => bakDrop.classList.remove('over'));
  const bakUpload = async (file) => {
    if (!file) return;
    if (!confirm(`„${file.name}“ einspielen? Die aktuellen Daten (Watchlist, Bewertungen, Serien, Schauspieler, Einstellungen) werden durch die Sicherung ersetzt. Der IMDb-Datensatz bleibt erhalten.`)) return;
    const fd = new FormData(); fd.append('file', file);
    toast('Sicherung wird eingespielt …');
    try {
      const r = await api.form('/backup/restore', fd);
      const c = r.counts || {};
      toast(`Wiederhergestellt: ${c.user_titles ?? '?'} Einträge, ${c.user_people ?? '?'} Schauspieler`, 'ok');
      setTimeout(() => location.reload(), 1200);
    } catch (e) { toast(e.message, 'err'); }
  };
  bakDrop.addEventListener('drop', (e) => { e.preventDefault(); bakDrop.classList.remove('over'); bakUpload(e.dataTransfer.files[0]); });
  bakFile.addEventListener('change', () => { bakUpload(bakFile.files[0]); bakFile.value = ''; });
  const backupPanel = h('div', { class: 'glass panel' },
    h('h2', {}, '📦 Sicherung'),
    h('p', { class: 'muted small' }, 'Die Sicherung enthält die komplette Datenbank (Bibliothek, Serien-Fortschritt, Schauspieler, Anbieter, Einstellungen, TMDB-Verbindung) ohne den IMDb-Datensatz, der automatisch neu geladen wird. Zum Umzug von der PC-Version: dort ', h('code', {}, 'tools\\export_pc_data.py'), ' ausführen und die ZIP hier einspielen.'),
    h('div', { class: 'row', style: { margin: '10px 0' } },
      h('a', { class: 'btn primary', href: '/api/backup' }, '⬇ Sicherung herunterladen (ZIP)')),
    bakDrop, bakFile,
  );

  // ---------- Zugang ----------
  const a = st.auth || {};
  const accessPanel = h('div', { class: 'glass panel' },
    h('h2', {}, '🔒 Zugang'),
    a.enabled
      ? [h('p', { class: 'small', style: { color: 'var(--ok)' } }, `✓ Passwortschutz aktiv${a.lan_without_login ? ' · im Heimnetz ohne Login' : ''}`),
        h('p', { class: 'muted small' }, a.tunnel ? 'Diese Sitzung läuft über den Cloudflare-Tunnel.' : (a.lan ? 'Diese Sitzung kommt aus dem Heimnetz.' : 'Diese Sitzung ist per Passwort angemeldet.'),
          ' Passwort und Heimnetz-Regel werden in den Add-on-Optionen in Home Assistant gesetzt; ein neues Passwort meldet alle Geräte ab.'),
        a.logged_in ? h('div', { class: 'row' }, h('a', { class: 'btn', href: '/logout' }, 'Abmelden')) : null]
      : [h('p', { class: 'small', style: { color: 'var(--warn)' } }, 'Kein Passwort gesetzt – jeder, der die Adresse erreicht, kann die App benutzen.'),
        h('p', { class: 'muted small' }, 'In Home Assistant unter Add-on → Konfiguration ein Passwort eintragen, bevor die App über das Internet erreichbar gemacht wird.')],
  );

  root.append(h('div', { class: 'settings-grid' }, keyPanel, provPanel, imdbPanel, tmdbPanel, listPanel, peoplePanel, dataPanel, backupPanel, accessPanel));
  const onJob = () => loadJobs();
  window.addEventListener('job-finished', onJob);
  return { destroy: () => window.removeEventListener('job-finished', onJob) };
}
