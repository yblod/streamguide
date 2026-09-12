// Startseite: Was kann ich heute Abend schauen?
import { api } from '../api.js';
import { h, hrow, section, empty, skeletons, fmtDate, card } from '../ui.js';

export async function render(root) {
  const head = h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, 'Heute Abend 🍿'), h('div', { class: 'sub' }, 'Aus deiner Watchlist, deinen Serien und den Angeboten deiner Anbieter.')),
    h('div', { class: 'row' },
      h('a', { class: 'btn', href: '#/discover' }, '🧭 Entdecken'),
      h('a', { class: 'btn', href: '#/abos' }, '💳 Abos')));
  const body = h('div', {}, skeletons(6));
  root.append(head, body);

  const load = async () => {
    try {
      const d = await api.home();
      body.innerHTML = '';
      const reload = () => load();
      const stats = h('div', { class: 'stats', style: { marginBottom: '20px' } },
        stat(d.counts.available, 'Watchlist verfügbar', '#/watchlist?only=available'),
        stat(d.counts.watchlist, 'Filme auf der Watchlist', '#/watchlist'),
        stat(d.counts.watching, 'Serien verfolgt', '#/series'),
        stat(d.new_seasons.length, 'Neue Staffeln', '#/series'));
      body.append(stats);
      if (d.newly_available.length) body.append(section('🆕 Jetzt bei deinen Anbietern verfügbar', hrow(d.newly_available, { onChange: reload })));
      if (d.new_seasons.length) body.append(section('🎉 Neue Staffeln & Folgen bei deinen Anbietern', hrow(d.new_seasons, { onChange: reload })));
      body.append(section('🔖 Aus deiner Watchlist – jetzt streambar',
        d.available_watchlist.length ? hrow(d.available_watchlist, { onChange: reload })
          : empty(d.counts.watchlist ? 'Nichts aus deiner Watchlist ist gerade bei deinen Anbietern.' : 'Deine Watchlist ist leer. Importiere sie in den Einstellungen oder füge Titel über die Suche hinzu.', '🔖'),
        h('a', { class: 'btn sm', href: '#/watchlist' }, 'Alle')));
      if (d.continue_watching.length) body.append(section('📺 Serien bei deinen Anbietern: weiterschauen oder anfangen', hrow(d.continue_watching, { onChange: reload }), h('a', { class: 'btn sm', href: '#/series' }, 'Alle')));
      if (d.from_people?.length) body.append(section('🎭 Neu von deinen Schauspielern', hrow(d.from_people, { onChange: reload, showPeople: true }), h('a', { class: 'btn sm', href: '#/people' }, 'Alle')));
      if (d.upcoming.length) body.append(section('📅 Demnächst neue Folgen',
        h('div', { class: 'chips' }, ...d.upcoming.map((t) => h('span', { class: 'chip', onClick: () => card(t).click() }, `${t.title} · ${fmtDate(t.next_episode_air)}`)))));
      body.append(section('🔥 Beliebt bei deinen Anbietern', d.popular.length ? hrow(d.popular, { onChange: reload }) : empty('Keine Daten – ist der TMDB-Schlüssel hinterlegt?'),
        h('a', { class: 'btn sm', href: '#/discover' }, 'Mehr')));
      const fy = section('✨ Für dich (Beta)', h('div', { class: 'muted small' }, h('span', { class: 'spinner' })));
      body.append(fy);
      try {
        const r = await api.forYou();
        fy.lastChild.replaceWith(r.results.length ? hrow(r.results, { onChange: reload }) : empty('Bewerte ein paar Titel mit 8+ Punkten, dann gibt es hier Vorschläge.', '✨'));
      } catch (e) { fy.lastChild.replaceWith(empty(e.message)); }
    } catch (e) {
      body.innerHTML = '';
      body.append(h('div', { class: 'glass panel' }, h('h2', {}, e.status === 428 ? 'TMDB-Schlüssel fehlt' : 'Fehler'), h('p', { class: 'muted' }, e.message),
        h('a', { class: 'btn primary', href: '#/settings' }, 'Zu den Einstellungen')));
    }
  };
  await load();
  const onJob = () => load();
  window.addEventListener('job-finished', onJob);
  return { destroy: () => window.removeEventListener('job-finished', onJob) };
}

function stat(n, label, href) {
  return h('a', { class: 'glass stat', href }, h('div', { class: 'n' }, n), h('div', { class: 'l' }, label));
}
