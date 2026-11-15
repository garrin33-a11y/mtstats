/* Страница одной карты. */
(function () {
  const params = new URLSearchParams(location.search);
  const mapName = params.get('map') || '';

  function mapIconUrl(mapId, kind, name) {
    if (!mapId) return '';
    const params = [];
    if (kind) params.push('kind=' + kind);
    if (name) params.push('name=' + encodeURIComponent(name));
    return '/api/mapicon/' + encodeURIComponent(mapId) + '.png' + (params.length ? '?' + params.join('&') : '');
  }

  function renderHero(data) {
    const map = data.map || {};
    const summary = data.summary;

    document.getElementById('mapName').textContent = map.name || mapName;
    const parts = [];
    parts.push(`${MT.fmt(summary.battles)} ${MT.plural(summary.battles, ['бой', 'боя', 'боёв'])}`);
    parts.push(`${MT.fmt(summary.wins)} побед`);
    parts.push(`средний урон ${MT.fmt(summary.damage_avg)}`);
    parts.push(`лучший бой ${MT.fmt(summary.best_damage)}`);
    document.getElementById('mapMeta').textContent = parts.join(' · ');

    const box = document.getElementById('heroImage');
    if (map.map_id) {
      box.innerHTML = `<img src="${mapIconUrl(map.map_id, '', map.name)}" alt="${MT.escapeHtml(map.name)}">`;
    } else {
      box.innerHTML = '';
    }

    const value = document.getElementById('winrateValue');
    value.textContent = MT.fmt1(summary.winrate) + '%';
    value.style.color = summary.winrate >= 50 ? 'var(--green)' : 'var(--danger)';
  }

  function renderKpis(data) {
    const s = data.summary;
    document.getElementById('kpis').innerHTML = [
      MT.kpiCard('Бои', MT.fmt(s.battles), `${s.wins} побед · ${s.losses} поражений`, ''),
      MT.kpiCard('% побед', MT.pct(s.winrate), `выживаемость ${MT.pct(s.survival_rate)}`, ''),
      MT.kpiCard('Средний урон', MT.fmt(s.damage_avg), `всего ${MT.compact(s.damage_total)}`, ''),
      MT.kpiCard('Засвет / помощь', `${MT.fmt1(s.spot_avg)} / ${MT.fmt(s.assist_avg)}`,
        `танкование ${MT.fmt(s.blocked_avg)}`, ''),
      MT.kpiCard('Опыт', MT.fmt(s.xp_avg), `всего ${MT.compact(s.xp_total)}`, ''),
      MT.kpiCard('Фарм', s.net_total === null ? '—' : MT.compact(s.net_total),
        `кредитов ${MT.compact(s.credits_total)}`, ''),
      MT.kpiCard('Рейтинг <span class="info" data-tip="' + MT.escapeHtml(MT.RATING_TIP) + '">i</span>',
        MT.fmt1(s.rating_avg), 'боевой рейтинг 0–100'),
      MT.kpiCard('Фраги', MT.fmt1(s.kills_avg), `всего ${MT.fmt(s.kills_total)}`, ''),
    ].join('');
  }

  function renderCharts(data) {
    const series = data.battle_series || [];
    if (!series.length) {
      ['chartDamage', 'chartSpot', 'chartBlocked', 'chartCredits', 'chartXp', 'chartWinrate']
        .forEach((id) => {
          const node = document.getElementById(id);
          if (node) node.innerHTML = '<div class="empty">Нет боёв за период</div>';
        });
      return;
    }
    const granularity = MT.pickGranularity(data.request, series);
    MT.applyChartHints(granularity);
    MT.battleCharts(series, data.summary, {
      damage: document.getElementById('chartDamage'),
      spot: document.getElementById('chartSpot'),
      blocked: document.getElementById('chartBlocked'),
      credits: document.getElementById('chartCredits'),
      xp: document.getElementById('chartXp'),
      winrate: document.getElementById('chartWinrate'),
    }, { granularity });
  }

  const SPAWN_LABELS = { top: 'Верхний', bottom: 'Нижний', left: 'Левый', right: 'Правый' };
  const SPAWN_HINTS = {
    vertical: 'респы снизу и сверху карты',
    horizontal: 'респы слева и справа',
  };

  function renderSpawns(data) {
    const rows = data.by_spawn || [];
    const html = ['<thead><tr><th class="left">Респ</th><th>Бои</th><th>Победы</th>',
      '<th>Ср. урон</th><th>Ср. опыт</th><th>Выжил</th><th>Рейтинг</th></tr></thead><tbody>'];
    if (!rows.length) {
      html.push('<tr><td class="empty-row" colspan="7">Нет данных о респаунах</td></tr>');
    }
    rows.forEach((row) => {
      html.push(`<tr>
        <td class="left"><b>${SPAWN_LABELS[row.spawn] || row.spawn}</b></td>
        <td>${MT.fmt(row.battles)}</td>
        <td class="${row.winrate >= 50 ? 'win' : 'loss'}">${MT.fmt1(row.winrate)}%</td>
        <td>${MT.fmt(row.damage_avg)}</td>
        <td>${MT.fmt(row.xp_avg)}</td>
        <td>${MT.fmt1(row.survival_rate)}%</td>
        <td>${MT.fmt1(row.rating)}</td>
      </tr>`);
    });
    html.push('</tbody>');
    document.getElementById('spawnTable').innerHTML = html.join('');
    const axis = rows.some((row) => row.spawn === 'top' || row.spawn === 'bottom') ? 'vertical' : 'horizontal';
    document.getElementById('spawnHint').textContent = rows.length
      ? SPAWN_HINTS[axis]
      : 'для этой карты нет описания баз в клиенте';
  }

  function renderTanks(data) {
    const rows = data.by_tank || [];
    const html = ['<thead><tr><th class="left">Танк</th><th>Бои</th><th>Победы</th>',
      '<th>Ср. урон</th><th>Ср. опыт</th><th>Рейтинг</th></tr></thead><tbody>'];
    if (!rows.length) html.push('<tr><td class="empty-row" colspan="6">Нет боёв</td></tr>');
    rows.forEach((row) => {
      html.push(`<tr>
        <td class="left"><a class="map-link" href="/tank?tank=${encodeURIComponent(row.tank)}">${MT.escapeHtml(row.tank)}</a></td>
        <td>${MT.fmt(row.battles)}</td>
        <td class="${row.winrate >= 50 ? 'win' : 'loss'}">${MT.fmt1(row.winrate)}%</td>
        <td>${MT.fmt(row.damage_avg)}</td>
        <td>${MT.fmt(row.xp_avg)}</td>
        <td>${MT.fmt1(row.rating)}</td>
      </tr>`);
    });
    html.push('</tbody>');
    document.getElementById('tanksTable').innerHTML = html.join('');
    document.getElementById('tanksHint').textContent =
      `${rows.length} ${MT.plural(rows.length, ['танк', 'танка', 'танков'])}`;
  }

  async function load(query) {
    try {
      const payload = await MT.api('/api/map', { ...query, map: mapName });
      document.getElementById('banner').hidden = true;
      renderHero(payload);
      renderKpis(payload);
      renderSpawns(payload);
      renderCharts(payload);
      renderTanks(payload);
      document.getElementById('logTable').innerHTML = MT.battleTable(payload.battles);
      document.getElementById('logHint').textContent =
        `${MT.fmt(payload.battles_total)} ${MT.plural(payload.battles_total, ['бой', 'боя', 'боёв'])}`;
      const request = payload.request;
      document.getElementById('rangeLabel').textContent = request.from
        ? `${request.label}: ${MT.ruDate(request.from)} — ${MT.ruDate(request.to)}`
        : `${request.label}: все реплеи`;
      document.title = `${payload.map.name} — MTstats`;
    } catch (error) {
      const banner = document.getElementById('banner');
      banner.hidden = false;
      banner.textContent = 'Не удалось загрузить данные: ' + error.message;
    }
  }

  async function loadStatus() {
    try {
      const status = await MT.api('/api/status');
      document.getElementById('playerName').textContent = status.player || 'Игрок';
      document.getElementById('dbInfo').textContent =
        `${MT.fmt(status.battles)} боёв в базе · ${MT.ruDate(status.date_min)} … ${MT.ruDate(status.date_max)}`;
      const noFarm = Number(status.no_farm || 0);
      document.getElementById('footInfo').textContent = noFarm
        ? `Из них ${MT.fmt(noFarm)} — восстановлены с сайта: нет данных о расходах`
        : '';
    } catch (error) { /* не критично */ }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!mapName) {
      const banner = document.getElementById('banner');
      banner.hidden = false;
      banner.textContent = 'Карта не указана. Вернитесь к списку карт.';
      return;
    }
    const control = MT.periodControl((query) => load(query));
    loadStatus();
    load(control.query());
  });
})();
