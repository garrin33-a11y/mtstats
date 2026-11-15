/* Страница одного танка. */
(function () {
  const params = new URLSearchParams(location.search);
  const tankName = params.get('tank') || '';
  let current = null;

  function wn8Class(value) {
    if (value == null) return '';
    if (value >= 2900) return 'wn8-super';
    if (value >= 2100) return 'wn8-great';
    if (value >= 1500) return 'wn8-good';
    if (value >= 900) return 'wn8-avg';
    return 'wn8-low';
  }

  function renderHero(data) {
    const tank = data.tank || {};
    const summary = data.summary;
    document.getElementById('tankName').textContent = tank.name || tankName;

    const parts = [];
    if (tank.nation) parts.push(MT.escapeHtml(tank.nation));
    if (tank.tier) parts.push(`${tank.tier} уровень`);
    if (tank.tank_class) parts.push(MT.classRu(tank.tank_class));
    parts.push(`${MT.fmt(summary.battles)} ${MT.plural(summary.battles, ['бой', 'боя', 'боёв'])}`);
    parts.push(`побед ${MT.fmt1(summary.winrate)}%`);
    parts.push(`средний урон ${MT.fmt(summary.damage_avg)}`);
    document.getElementById('tankMeta').innerHTML = parts.join(' · ');

    const heroIcon = document.getElementById('heroIcon');
    if (tank.vehicle) {
      heroIcon.innerHTML = `<img src="/api/icon/${encodeURIComponent(tank.vehicle)}" alt="">`;
    } else {
      heroIcon.innerHTML = '';
    }

    const wn8 = summary.wn8;
    const value = document.getElementById('wn8Value');
    value.textContent = wn8 == null ? '—' : MT.fmt(wn8);
    value.className = 'wn8-value ' + wn8Class(wn8);
  }

  function renderKpis(data) {
    const s = data.summary;
    const cards = [
      MT.kpiCard('Бои', MT.fmt(s.battles), `${s.wins} побед · ${s.losses} поражений`,
        '#f0a233'),
      MT.kpiCard('% побед', MT.pct(s.winrate), `выживаемость ${MT.pct(s.survival_rate)}`,
        s.winrate >= 50 ? '#4caf7d' : '#e0605c'),
      MT.kpiCard('Средний урон', MT.fmt(s.damage_avg), `всего ${MT.compact(s.damage_total)}`,
        '#f0a233'),
      MT.kpiCard('Засвет / помощь', `${MT.fmt1(s.spot_avg)} / ${MT.fmt(s.assist_avg)}`,
        `танкование ${MT.fmt(s.blocked_avg)}`, '#5aa9e6'),
      MT.kpiCard('Эффективность <span class="info" data-tip="' + MT.escapeHtml(MT.RATING_TIP) + '">i</span>',
        MT.fmt1(s.rating_avg), 'боевой рейтинг 0–100'),
      MT.kpiCard('Опыт', MT.fmt(s.xp_avg), `всего ${MT.compact(s.xp_total)}`, '#e07a5f'),
      MT.kpiCard('Фарм', MT.compact(s.net_total), `кредитов ${MT.compact(s.credits_total)}`,
        s.net_total >= 0 ? '#4caf7d' : '#e0605c'),
      MT.kpiCard('Фраги', MT.fmt1(s.kills_avg), `всего ${MT.fmt(s.kills_total)}`),
    ];
    document.getElementById('kpis').innerHTML = cards.join('');
  }

  function renderCharts(data) {
    const series = data.battle_series || [];
    if (!series.length) {
      ['chartDamage', 'chartSpot', 'chartBlocked', 'chartCredits', 'chartXp', 'chartWinrate']
        .forEach((id) => { const node = document.getElementById(id); if (node) node.innerHTML = '<div class="empty">Нет боёв за период</div>'; });
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

  async function load(query) {
    try {
      const payload = await MT.api('/api/tank', { ...query, tank: tankName });
      current = payload;
      document.getElementById('banner').hidden = true;
      renderHero(payload);
      renderKpis(payload);
      renderCharts(payload);
      document.getElementById('mapsTable').innerHTML = MT.mapTable(payload.by_map);
      document.getElementById('mapsHint').textContent = `${payload.by_map.length} карт`;
      document.getElementById('logTable').innerHTML = MT.battleTable(payload.battles);
      document.getElementById('logHint').textContent =
        `${MT.fmt(payload.battles_total)} ${MT.plural(payload.battles_total, ['бой', 'боя', 'боёв'])}`;
      const request = payload.request;
      document.getElementById('rangeLabel').textContent = request.from
        ? `${request.label}: ${MT.ruDate(request.from)} — ${MT.ruDate(request.to)}`
        : `${request.label}: все реплеи`;
      document.title = `${payload.tank.name} — MTstats`;
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
    } catch (error) { /* не критично */ }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!tankName) {
      document.getElementById('banner').hidden = false;
      document.getElementById('banner').textContent = 'Танк не указан. Вернитесь в каталог.';
      return;
    }
    const control = MT.periodControl((query) => load(query));
    loadStatus();
    load(control.query());
  });
})();
