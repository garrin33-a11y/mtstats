/* Логика интерфейса MTstats. */
(function () {
  const state = {
    period: 'month',
    from: null,
    to: null,
    limit: 400,
    data: null,
    sort: {
      tanks: { key: 'battles', dir: -1 },
      maps: { key: 'battles', dir: -1 },
      log: { key: 'played_at', dir: -1 },
    },
  };

  const numberFmt = new Intl.NumberFormat('ru-RU');
  const oneFmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });

  const fmt = (value) => numberFmt.format(Math.round(value || 0));
  const fmt1 = (value) => oneFmt.format(value || 0);
  const pct = (value) => fmt1(value) + '%';

  function compact(value) {
    const abs = Math.abs(value || 0);
    if (abs >= 1e9) return fmt1(value / 1e9) + ' млрд';
    if (abs >= 1e6) return fmt1(value / 1e6) + ' млн';
    if (abs >= 1e4) return fmt1(value / 1e3) + ' тыс';
    return fmt(value);
  }

  /* Формат оси подбирается по масштабу данных, чтобы «0» и «10 тыс» не соседствовали. */
  function axisFormat(maxAbs) {
    if (maxAbs >= 1e6) return (value) => fmt1(value / 1e6) + ' млн';
    if (maxAbs >= 1e4) return (value) => fmt1(value / 1e3) + ' тыс';
    return (value) => fmt(value);
  }

  function maxAbs(values) {
    return values.reduce((acc, value) => (typeof value === 'number' && isFinite(value)
      ? Math.max(acc, Math.abs(value)) : acc), 0);
  }

  function ruDate(iso) {
    if (!iso) return '—';
    const parts = String(iso).split('-');
    if (parts.length !== 3) return iso;
    return `${parts[2]}.${parts[1]}.${parts[0]}`;
  }

  /* Русские окончания: plural(5, ['бой','боя','боёв']) -> 'боёв'. */
  function plural(count, forms) {
    const abs = Math.abs(count) % 100;
    const last = abs % 10;
    if (abs > 10 && abs < 20) return forms[2];
    if (last > 1 && last < 5) return forms[1];
    if (last === 1) return forms[0];
    return forms[2];
  }

  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  const $ = (id) => document.getElementById(id);

  function showBanner(message, kind) {
    const banner = $('banner');
    if (!message) {
      banner.hidden = true;
      return;
    }
    banner.hidden = false;
    banner.textContent = message;
    banner.style.background = kind === 'ok' ? 'rgba(76,175,125,0.12)' : '';
    banner.style.borderColor = kind === 'ok' ? 'rgba(76,175,125,0.45)' : '';
    banner.style.color = kind === 'ok' ? '#9fe3c2' : '';
  }

  function resultClass(result) {
    if (result === 'Победа') return 'win';
    if (result === 'Поражение') return 'loss';
    return 'draw';
  }

  /* ---------------- запрос данных ---------------- */
  async function loadData() {
    const params = new URLSearchParams({ period: state.period, limit: String(state.limit) });
    if (state.period === 'custom') {
      if (state.from) params.set('from', state.from);
      if (state.to) params.set('to', state.to);
    }
    const response = await fetch('/api/data?' + params.toString(), { cache: 'no-store' });
    const payload = await response.json();
    if (!response.ok || payload.error) throw new Error(payload.error || 'Ошибка сервера');
    state.data = payload;
    return payload;
  }

  async function loadStatus() {
    const response = await fetch('/api/status', { cache: 'no-store' });
    return response.json();
  }

  /* ---------------- KPI ---------------- */
  function renderKpis(data) {
    const s = data.summary;
    const cards = [
      {
        label: 'Бои', value: fmt(s.battles), color: '#f0a233',
        meta: `${s.wins} побед · ${s.losses} поражений · ${s.draws} ничьих`,
      },
      {
        label: '% побед', value: pct(s.winrate), color: s.winrate >= 50 ? '#4caf7d' : '#e0605c',
        meta: `${s.wins} побед из ${fmt(s.battles)}`,
      },
      {
        label: 'Средний урон', value: fmt(s.damage_avg), color: '#f0a233',
        meta: `всего ${compact(s.damage_total)}`,
      },
      {
        label: 'Засвет / помощь', value: `${fmt1(s.spot_avg)} / ${fmt(s.assist_avg)}`, color: '#5aa9e6',
        meta: `засветов всего ${fmt(s.spot_total)}`,
      },
      {
        label: 'Танкование', value: fmt(s.blocked_avg), color: '#63c9b4',
        meta: `всего ${compact(s.blocked_total)} · получено ${fmt(s.received_avg)}`,
      },
      {
        label: 'Фарм',
        value: s.net_total === null ? '—' : compact(s.net_total),
        color: s.net_total === null ? '#8b98a8' : (s.net_total >= 0 ? '#4caf7d' : '#e0605c'),
        meta: `кредитов ${compact(s.credits_total)}`,
      },
      {
        label: 'Опыт', value: fmt(s.xp_avg), color: '#e07a5f',
        meta: `всего ${compact(s.xp_total)} · выживаемость ${pct(s.survival_rate)}`,
      },
      {
        label: `Эффективность <span class="info" data-tip="${escapeHtml(MT.RATING_TIP)}">i</span>`,
        value: fmt1(s.rating_avg),
        meta: s.best_battle
          ? `лучший бой ${fmt(s.best_battle.damage)} на ${escapeHtml(s.best_battle.tank)}`
          : 'нет данных',
      },
    ];

    $('kpis').innerHTML = cards.map((card) => `
      <div class="kpi" style="--kpi-color:${card.color}">
        <div class="label">${card.label}</div>
        <div class="value">${card.value}</div>
        <div class="meta">${card.meta}</div>
      </div>`).join('');
  }

  /* ---------------- графики ---------------- */
  function renderCharts(data) {
    const series = data.battle_series || [];
    if (!series.length) {
      ['chartDamage', 'chartSpot', 'chartBlocked', 'chartCredits', 'chartXp', 'chartWinrate', 'chartRating', 'chartKills']
        .forEach((id) => { const node = $(id); if (node) node.innerHTML = '<div class="empty">Нет боёв за выбранный период</div>'; });
      return;
    }
    const granularity = MT.pickGranularity(data.request, series);
    MT.applyChartHints(granularity);
    MT.battleCharts(series, data.summary, {
      damage: $('chartDamage'),
      spot: $('chartSpot'),
      blocked: $('chartBlocked'),
      credits: $('chartCredits'),
      xp: $('chartXp'),
      winrate: $('chartWinrate'),
      rating: $('chartRating'),
      kills: $('chartKills'),
    }, { granularity });
  }

  /* ---------------- таблицы ---------------- */
  function sortRows(rows, key, dir) {
    return rows.slice().sort((a, b) => {
      const av = a[key];
      const bv = b[key];
      if (typeof av === 'string' || typeof bv === 'string') {
        return dir * String(av || '').localeCompare(String(bv || ''), 'ru');
      }
      return dir * ((av || 0) - (bv || 0));
    });
  }

  function renderTanks(data) {
    const rows = sortRows(data.by_tank || [], state.sort.tanks.key, state.sort.tanks.dir);
    const head = [
      ['tank', 'Танк'], ['battles', 'Бои'], ['winrate', '% побед'], ['damage_avg', 'Ср. урон'],
      ['assist_avg', 'Помощь'], ['xp_avg', 'Ср. опыт'], ['rating', 'Рейтинг'], ['net', 'Фарм'],
    ];
    const html = ['<thead><tr>'];
    head.forEach(([key, label], index) => {
      const active = state.sort.tanks.key === key ? (state.sort.tanks.dir < 0 ? ' ↓' : ' ↑') : '';
      html.push(`<th data-key="${key}" class="${index === 0 ? 'left' : ''}">${label}${active}</th>`);
    });
    html.push('</tr></thead><tbody>');
    if (!rows.length) {
      html.push('<tr><td class="empty-row" colspan="8">Нет боёв за период</td></tr>');
    }
    rows.forEach((row) => {
      const netClass = row.net >= 0 ? 'pos' : 'neg';
      const href = '/tank?tank=' + encodeURIComponent(row.tank);
      html.push(`<tr>
        <td class="left"><a class="tank-link" href="${href}"><div class="tank-cell">${escapeHtml(row.tank)}<small>${escapeHtml(row.nation)}</small></div></a></td>
        <td>${fmt(row.battles)}</td>
        <td class="${row.winrate >= 50 ? 'win' : 'loss'}">${fmt1(row.winrate)}%</td>
        <td>${fmt(row.damage_avg)}</td>
        <td>${fmt(row.assist_avg)}</td>
        <td>${fmt(row.xp_avg)}</td>
        <td>${fmt1(row.rating)}</td>
        <td class="${row.net === null ? '' : netClass}">${row.net === null ? '—' : compact(row.net)}</td>
      </tr>`);
    });
    html.push('</tbody>');
    $('tanksTable').innerHTML = html.join('');
    $('tanksHint').textContent = `${rows.length} ${plural(rows.length, ['танк', 'танка', 'танков'])}`;

    $('tanksTable').querySelectorAll('th').forEach((th) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const key = th.dataset.key;
        if (state.sort.tanks.key === key) state.sort.tanks.dir *= -1;
        else state.sort.tanks = { key: key, dir: key === 'tank' ? 1 : -1 };
        renderTanks(state.data);
      });
    });
  }

  function renderMaps(data) {
    const rows = sortRows(data.by_map || [], state.sort.maps.key, state.sort.maps.dir);
    const html = ['<thead><tr>',
      `<th data-key="map" class="left">Карта${state.sort.maps.key === 'map' ? (state.sort.maps.dir < 0 ? ' ↓' : ' ↑') : ''}</th>`,
      `<th data-key="battles">Бои${state.sort.maps.key === 'battles' ? (state.sort.maps.dir < 0 ? ' ↓' : ' ↑') : ''}</th>`,
      `<th data-key="winrate">% побед${state.sort.maps.key === 'winrate' ? (state.sort.maps.dir < 0 ? ' ↓' : ' ↑') : ''}</th>`,
      `<th data-key="damage_avg">Ср. урон${state.sort.maps.key === 'damage_avg' ? (state.sort.maps.dir < 0 ? ' ↓' : ' ↑') : ''}</th>`,
      `<th data-key="rating">Рейтинг${state.sort.maps.key === 'rating' ? (state.sort.maps.dir < 0 ? ' ↓' : ' ↑') : ''}</th>`,
      '</tr></thead><tbody>'];
    if (!rows.length) {
      html.push('<tr><td class="empty-row" colspan="5">Нет боёв за период</td></tr>');
    }
    rows.forEach((row) => {
      html.push(`<tr>
        <td class="left">${escapeHtml(row.map)}</td>
        <td>${fmt(row.battles)}</td>
        <td class="${row.winrate >= 50 ? 'win' : 'loss'}">${fmt1(row.winrate)}%</td>
        <td>${fmt(row.damage_avg)}</td>
        <td>${fmt1(row.rating)}</td>
      </tr>`);
    });
    html.push('</tbody>');
    $('mapsTable').innerHTML = html.join('');
    $('mapsHint').textContent = `${rows.length} ${plural(rows.length, ['карта', 'карты', 'карт'])}`;

    $('mapsTable').querySelectorAll('th').forEach((th) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const key = th.dataset.key;
        if (state.sort.maps.key === key) state.sort.maps.dir *= -1;
        else state.sort.maps = { key: key, dir: key === 'map' ? 1 : -1 };
        renderMaps(state.data);
      });
    });
  }

  function renderLog(data) {
    const rows = sortRows(data.battles || [], state.sort.log.key, state.sort.log.dir);
    const columns = [
      ['played_at', 'Дата'], ['map', 'Карта'], ['tank', 'Танк'], ['result', 'Результат'],
      ['damage', 'Урон'], ['spot', 'Засвет'], ['assist', 'Помощь'], ['blocked', 'Танк.'],
      ['net', 'Фарм'], ['xp', 'Опыт'], ['rating', 'Рейтинг'],
    ];
    const html = ['<thead><tr>'];
    columns.forEach(([key, label], index) => {
      const active = state.sort.log.key === key ? (state.sort.log.dir < 0 ? ' ↓' : ' ↑') : '';
      html.push(`<th data-key="${key}" class="${index < 3 ? 'left' : ''}">${label}${active}</th>`);
    });
    html.push('</tr></thead><tbody>');
    if (!rows.length) {
      html.push('<tr><td class="empty-row" colspan="11">Нет боёв за период</td></tr>');
    }
    rows.forEach((row) => {
      const netClass = row.net >= 0 ? 'pos' : 'neg';
      const time = row.played_at ? row.played_at.slice(5, 16).replace(' ', ' · ') : '';
      html.push(`<tr>
        <td class="left">${escapeHtml(time)}</td>
        <td class="left">${escapeHtml(row.map)}</td>
        <td class="left">${escapeHtml(row.tank)}</td>
        <td class="${resultClass(row.result)}">${escapeHtml(row.result)}</td>
        <td>${fmt(row.damage)}</td>
        <td>${row.spot === null ? '—' : fmt(row.spot)}</td>
        <td>${row.assist === null ? '—' : fmt(row.assist)}</td>
        <td>${row.blocked === null ? '—' : fmt(row.blocked)}</td>
        <td class="${row.net === null ? '' : netClass}">${row.net === null ? '—' : compact(row.net)}</td>
        <td>${fmt(row.xp)}</td>
        <td>${fmt(row.rating)}</td>
      </tr>`);
    });
    html.push('</tbody>');
    $('logTable').innerHTML = html.join('');
    const shown = (data.battles || []).length;
    $('logHint').textContent = shown < data.battles_total
      ? `показано ${shown} из ${fmt(data.battles_total)}`
      : `${fmt(data.battles_total)} ${plural(data.battles_total, ['бой', 'боя', 'боёв'])}`;

    $('logTable').querySelectorAll('th').forEach((th) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const key = th.dataset.key;
        if (state.sort.log.key === key) state.sort.log.dir *= -1;
        else state.sort.log = { key: key, dir: key === 'played_at' ? -1 : -1 };
        renderLog(state.data);
      });
    });
  }

  /* ---------------- обвязка ---------------- */
  function updateFooter(data, status) {
    const db = data.db || {};
    $('dbInfo').textContent = `${fmt(db.battles)} ${plural(db.battles || 0, ['бой', 'боя', 'боёв'])} в базе · ${ruDate(db.date_min)} … ${ruDate(db.date_max)}` +
      (db.last_import ? ` · обновлено ${db.last_import.slice(0, 16)}` : '');
    $('playerName').textContent = status && status.player ? status.player : 'Игрок';
    if (status) {
      const unread = Number(status.unread || 0);
      const noResults = Number(status.unread_no_results || 0);
      const fromMod = Number(status.from_mod || 0);
      const tail = unread
        ? ` · не прочитано файлов: ${unread}` + (noResults ? ` (без блока результатов: ${noResults})` : '')
        : '';
      const modPart = fromMod ? ` · из JSON мода: ${fmt(fromMod)}` : '';
      $('footVersion').textContent =
        `Папок: ${status.folders ? status.folders.length : 0} реплеев` +
        ((status.json_folders || []).length ? ` + ${status.json_folders.length} JSON` : '') +
        ` · последний импорт: ${status.last_import || '—'}` + modPart + tail;
    }
    const label = data.request && data.request.label ? data.request.label : '';
    const range = data.request && data.request.from
      ? `${ruDate(data.request.from)} — ${ruDate(data.request.to)}`
      : 'все доступные реплеи';
    $('rangeLabel').textContent = `${label}: ${range}`;
    const csv = $('csvLink');
    const params = new URLSearchParams({ period: state.period });
    if (state.period === 'custom') {
      if (state.from) params.set('from', state.from);
      if (state.to) params.set('to', state.to);
    }
    csv.href = '/api/export.csv?' + params.toString();
  }

  function setActiveTab(period) {
    document.querySelectorAll('#tabs button').forEach((button) => {
      button.classList.toggle('active', button.dataset.period === period);
    });
  }

  async function refreshAll() {
    try {
      syncUrl();
      const [data, status] = await Promise.all([loadData(), loadStatus().catch(() => null)]);
      showBanner('');
      renderKpis(data);
      renderCharts(data);
      renderTanks(data);
      renderMaps(data);
      renderLog(data);
      updateFooter(data, status);
    } catch (error) {
      showBanner('Не удалось загрузить данные: ' + error.message);
    }
  }

  function bindEvents() {
    document.querySelectorAll('#tabs button').forEach((button) => {
      button.addEventListener('click', () => {
        state.period = button.dataset.period;
        setActiveTab(state.period);
        refreshAll();
      });
    });

    $('applyBtn').addEventListener('click', () => {
      const from = $('dateFrom').value;
      const to = $('dateTo').value;
      if (!from && !to) {
        showBanner('Укажите хотя бы одну дату для своего периода');
        return;
      }
      state.period = 'custom';
      state.from = from || to;
      state.to = to || from;
      setActiveTab('custom');
      showBanner('');
      refreshAll();
    });

    $('refreshBtn').addEventListener('click', async () => {
      const button = $('refreshBtn');
      button.disabled = true;
      const original = button.textContent;
      button.textContent = 'Читаю реплеи…';
      try {
        const response = await fetch('/api/refresh', { method: 'POST' });
        const payload = await response.json();
        if (payload.error) throw new Error(payload.error);
        const info = payload.import || {};
        const skippedResults = Number(info.failed_no_results || 0);
        showBanner(
          `Импорт: новых ${info.imported || 0}, обновлено ${info.updated || 0}, ` +
          `без изменений ${info.skipped || 0}, ошибок ${info.failed || 0}` +
          (skippedResults ? ` (${skippedResults} — в реплее нет блока результатов)` : ''),
          'ok',
        );
        await refreshAll();
      } catch (error) {
        showBanner('Ошибка импорта: ' + error.message);
      } finally {
        button.disabled = false;
        button.textContent = original;
      }
    });
  }

  function syncUrl() {
    const params = new URLSearchParams();
    params.set('period', state.period);
    if (state.period === 'custom') {
      if (state.from) params.set('from', state.from);
      if (state.to) params.set('to', state.to);
    }
    try {
      history.replaceState(null, '', location.pathname + '?' + params.toString());
    } catch (error) {
      /* file:// или старый браузер — не критично */
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const url = new URLSearchParams(location.search);
    if (url.get('period')) state.period = url.get('period');
    if (url.get('from')) state.from = url.get('from');
    if (url.get('to')) state.to = url.get('to');
    setActiveTab(state.period);
    if (state.from) $('dateFrom').value = state.from;
    if (state.to) $('dateTo').value = state.to;

    bindEvents();
    loadStatus().then((status) => {
      if (status && status.date_min && !state.from) {
        $('dateFrom').value = status.date_max;
        $('dateTo').value = status.date_max;
      }
    }).catch(() => {});
    syncUrl();
    refreshAll();
  });
})();
