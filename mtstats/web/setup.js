/* Первый запуск: выбор папки с реплеями. */
(function () {
  const input = document.getElementById('folderInput');
  const detected = document.getElementById('detected');
  const error = document.getElementById('setupError');
  const progress = document.getElementById('setupProgress');
  const progressText = document.getElementById('progressText');
  const connectBtn = document.getElementById('connectBtn');
  const browseBtn = document.getElementById('browseBtn');

  function showError(message) {
    error.hidden = !message;
    error.textContent = message || '';
  }

  function pick(folder) {
    input.value = folder;
    showError('');
    input.focus();
  }

  async function loadStatus() {
    try {
      const response = await fetch('/api/setup/status', { cache: 'no-store' });
      const status = await response.json();
      if (status.browse_available) browseBtn.hidden = false;

      const folders = status.detected || [];
      if (folders.length) {
        detected.innerHTML = '<div class="detected-label">Нашли автоматически:</div>' +
          folders.map((folder) => `<button class="detected-item" data-folder="${encodeURIComponent(folder)}">
            <span class="detected-icon">📁</span>
            <span class="detected-path">${folder}</span>
          </button>`).join('');
        detected.querySelectorAll('.detected-item').forEach((button) => {
          button.addEventListener('click', () => pick(decodeURIComponent(button.dataset.folder)));
        });
        if (!input.value) input.value = folders[0];
      } else {
        detected.innerHTML = '';
      }
    } catch (err) {
      /* не критично */
    }
  }

  async function connect() {
    const folder = input.value.trim();
    if (!folder) {
      showError('Укажите папку с реплеями');
      return;
    }
    showError('');
    connectBtn.disabled = true;
    progress.hidden = false;
    progressText.textContent = 'Читаю файлы…';

    try {
      const response = await fetch('/api/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder }),
      });
      const payload = await response.json();
      if (!response.ok || payload.error) throw new Error(payload.error || 'Не получилось');

      const info = payload.import || {};
      if (!info.battles) {
        throw new Error('В этой папке не нашлось ни одного реплея. Проверьте путь и включите сохранение реплеев в игре.');
      }
      progressText.textContent = `Готово: ${info.battles} боёв в базе`;
      window.location.href = '/';
    } catch (err) {
      progress.hidden = true;
      connectBtn.disabled = false;
      showError(err.message);
    }
  }

  browseBtn.addEventListener('click', async () => {
    browseBtn.disabled = true;
    try {
      const response = await fetch('/api/browse', { method: 'POST' });
      const payload = await response.json();
      if (payload.path) pick(payload.path);
    } catch (err) {
      showError('Не удалось открыть проводник — введите путь вручную');
    } finally {
      browseBtn.disabled = false;
    }
  });

  connectBtn.addEventListener('click', connect);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') connect();
  });

  loadStatus();
})();
