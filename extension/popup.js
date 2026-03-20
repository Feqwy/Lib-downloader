document.addEventListener('DOMContentLoaded', () => {
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const sendBtn = document.getElementById('sendBtn');
  const statusEl = document.getElementById('status');
  const slugCountEl = document.getElementById('slugCount');
  const serverUrlEl = document.getElementById('serverUrl');
  const domainEl = document.getElementById('domain');
  const modeEl = document.getElementById('mode');
  const localPathEl = document.getElementById('localPath');
  const pathGroup = document.getElementById('pathGroup');
  const tokenEl = document.getElementById('token');
  const tokenGroup = document.getElementById('tokenGroup');
  const extractTokenBtn = document.getElementById('extractTokenBtn');
  const resultsSection = document.getElementById('resultsSection');
  const resultsEl = document.getElementById('results');
  const toggleSettings = document.getElementById('toggleSettings');
  const settingsContent = document.getElementById('settingsContent');
  const clearResults = document.getElementById('clearResults');
  const resetBtn = document.getElementById('resetBtn');
  const serverStatusEl = document.getElementById('serverStatus');
  const serverUrlDisplayEl = document.getElementById('serverUrlDisplay');

  let currentTab = null;
  let isCollecting = false;
  let slugCount = 0;
  let settingsCollapsed = false;
  let serverStatusInterval = null;

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      currentTab = tabs[0];
      updateDomainFromUrl(tabs[0].url);
      checkTokenVisibility();
    }
  });

  toggleSettings.addEventListener('click', () => {
    settingsCollapsed = !settingsCollapsed;
    if (settingsCollapsed) {
      settingsContent.classList.add('collapsed');
      toggleSettings.querySelector('.chevron').classList.add('rotated');
    } else {
      settingsContent.classList.remove('collapsed');
      toggleSettings.querySelector('.chevron').classList.remove('rotated');
    }
  });

  clearResults.addEventListener('click', () => {
    resultsSection.style.display = 'none';
    resultsEl.innerHTML = '';
    chrome.storage.local.set({ lastResults: null });
  });

  function updateDomainFromUrl(url) {
    if (url.includes('v2.shlib.life')) {
      domainEl.value = 'v2.shlib.life';
    } else if (url.includes('mangalib.org')) {
      domainEl.value = 'mangalib.org';
    } else if (url.includes('ranobelib.me')) {
      domainEl.value = 'ranobelib.me';
    } else if (url.includes('hentailib.me')) {
      domainEl.value = 'hentailib.me';
    } else if (url.includes('mangalib.me')) {
      domainEl.value = 'mangalib.me';
    }
    checkTokenVisibility();
  }

  function checkTokenVisibility() {
    if (domainEl.value === 'v2.shlib.life' || domainEl.value === 'hentailib.me' || domainEl.value === 'mangalib.me' || domainEl.value === 'mangalib.org' || domainEl.value === 'ranobelib.me') {
      tokenGroup.style.display = 'block';
    } else {
      tokenGroup.style.display = 'none';
    }
  }

  modeEl.addEventListener('change', () => {
    if (modeEl.value === 'check_local') {
      pathGroup.style.display = 'block';
    } else {
      pathGroup.style.display = 'none';
    }
  });

  domainEl.addEventListener('change', checkTokenVisibility);

  extractTokenBtn.addEventListener('click', async () => {
    if (!currentTab) return;

    extractTokenBtn.disabled = true;
    extractTokenBtn.textContent = 'Извлечение...';

    try {
      let storageData = await chrome.storage.local.get(['captured_token']);
      let capturedToken = storageData.captured_token;

      if (capturedToken) {
        tokenEl.value = capturedToken;
        chrome.storage.local.set({ extractedToken: capturedToken });
        showNotification('Токен найден в сетевых запросах!', 'success');
        extractTokenBtn.disabled = false;
        extractTokenBtn.textContent = 'Взять';
        return;
      }

      const isShlib = currentTab.url && (currentTab.url.includes('shlib.life') || currentTab.url.includes('hentailib.me'));

      if (isShlib) {
        showNotification('Автоматическая перезагрузка страницы для захвата токена...', 'info');
      } else {
        showNotification('Перезагрузка страницы для захвата токена...', 'info');
      }

      await chrome.storage.local.remove(['captured_token']);
      await chrome.tabs.reload(currentTab.id);

      let attempts = 0;
      const maxAttempts = 10;
      const checkInterval = 1000;

      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, checkInterval));

        storageData = await chrome.storage.local.get(['captured_token']);
        capturedToken = storageData.captured_token;

        if (capturedToken) {
          tokenEl.value = capturedToken;
          chrome.storage.local.set({ extractedToken: capturedToken });
          showNotification('Токен успешно захвачен!', 'success');
          extractTokenBtn.disabled = false;
          extractTokenBtn.textContent = 'Взять';
          return;
        }

        attempts++;
        extractTokenBtn.textContent = `Ожидание... (${attempts}/${maxAttempts})`;
      }

      chrome.storage.local.get(['extractedToken'], (result) => {
        if (result.extractedToken) {
          tokenEl.value = result.extractedToken;
          showNotification('Используется ранее извлечённый токен', 'info');
        } else {
          showNotification('Токен не захвачен. Убедитесь, что вы вошли в систему.', 'error');
        }
      });

    } catch (error) {
      console.error('Ошибка извлечения токена:', error);
      showNotification('Ошибка при извлечении токена. Попробуйте снова.', 'error');
    } finally {
      extractTokenBtn.disabled = false;
      extractTokenBtn.textContent = 'Взять';
    }
  });

  function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 10px 14px;
      background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
      color: white;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      z-index: 10000;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      animation: slideIn 0.3s ease-out;
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
      notification.style.animation = 'slideOut 0.3s ease-out';
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }

  startBtn.addEventListener('click', async () => {
    if (!currentTab) return;

    const url = currentTab.url || '';
    const isSupported = url.includes('mangalib.me') ||
                       url.includes('mangalib.org') ||
                       url.includes('v2.shlib.life') ||
                       url.includes('ranobelib.me') ||
                       url.includes('hentailib.me');

    if (!isSupported) {
      showNotification('Ошибка: Перейдите на поддерживаемую страницу (mangalib.me, ranobelib.me, hentailib.me и т.д.)', 'error');
      return;
    }

    try {
      try {
        await chrome.tabs.sendMessage(currentTab.id, { type: 'ping' });
      } catch (e) {
        await chrome.scripting.executeScript({
          target: { tabId: currentTab.id },
          files: ['content.js']
        });
        await new Promise(resolve => setTimeout(resolve, 500));
      }

      await chrome.tabs.sendMessage(currentTab.id, { type: 'startCollection' });
      isCollecting = true;
      startBtn.disabled = true;
      stopBtn.disabled = false;
      statusEl.textContent = 'Сбор...';
      statusEl.className = 'status-value collecting';
    } catch (error) {
      console.error('Ошибка запуска сбора:', error);
      showNotification('Ошибка: Не удалось запустить сбор. Попробуйте обновить страницу.', 'error');
    }
  });

  stopBtn.addEventListener('click', async () => {
    if (!currentTab) return;

    try {
      await chrome.tabs.sendMessage(currentTab.id, { type: 'stopCollection' });
      isCollecting = false;
      startBtn.disabled = false;
      stopBtn.disabled = true;
      statusEl.textContent = 'Остановлено';
      statusEl.className = 'status-value stopped';
    } catch (error) {
      console.error('Ошибка остановки сбора:', error);
    }
  });

  resetBtn.addEventListener('click', async () => {
    if (!currentTab) return;

    if (!confirm('Вы уверены, что хотите сбросить все собранные slug? Это действие нельзя отменить.')) {
      return;
    }

    try {
      await chrome.tabs.sendMessage(currentTab.id, { type: 'clearSlugs' });
      slugCount = 0;
      slugCountEl.textContent = '0';
      sendBtn.disabled = true;
      statusEl.textContent = 'Сброшено';
      statusEl.className = 'status-value ready';
      showNotification('Slug успешно сброшены', 'success');
    } catch (error) {
      console.error('Ошибка сброса slug:', error);
      chrome.storage.local.set({ collectedSlugs: [] }, () => {
        slugCount = 0;
        slugCountEl.textContent = '0';
        sendBtn.disabled = true;
        showNotification('Slug сброшены из хранилища', 'info');
      });
    }
  });

  // Проверка статуса сервера
  async function checkServerStatus() {
    const serverUrl = serverUrlEl.value.trim() || 'http://localhost:8080';
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);
      
      const response = await fetch(`${serverUrl}/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slugs: [], mode: 'server_only' }),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (response.ok || response.status === 400) {
        // Сервер отвечает - он работает
        serverStatusEl.textContent = 'Онлайн';
        serverStatusEl.className = 'status-value online';
        serverUrlDisplayEl.textContent = serverUrl;
        return true;
      } else {
        throw new Error(`Status: ${response.status}`);
      }
    } catch (error) {
      serverStatusEl.textContent = 'Офлайн';
      serverStatusEl.className = 'status-value offline';
      serverUrlDisplayEl.textContent = serverUrl;
      return false;
    }
  }

  // Запуск периодической проверки сервера
  function startServerStatusPolling() {
    checkServerStatus(); // Немедленная проверка
    serverStatusInterval = setInterval(checkServerStatus, 10000); // Проверка каждые 10 секунд
  }

  // Остановка периодической проверки
  function stopServerStatusPolling() {
    if (serverStatusInterval) {
      clearInterval(serverStatusInterval);
      serverStatusInterval = null;
    }
  }

  sendBtn.addEventListener('click', async () => {
    if (!currentTab || slugCount === 0) return;

    try {
      const response = await chrome.tabs.sendMessage(currentTab.id, { type: 'getSlugs' });
      const slugs = response.slugs;

      if (!slugs || slugs.length === 0) {
        showNotification('Нет собранных slug. Запустите сбор сначала.', 'error');
        return;
      }

      sendBtn.disabled = true;
      sendBtn.textContent = 'Отправка...';
      statusEl.textContent = 'Отправка на сервер...';
      statusEl.className = 'status-value collecting';

      const serverUrl = serverUrlEl.value.trim() || 'http://localhost:8080';
      const domain = domainEl.value;
      const mode = modeEl.value;
      const localPath = mode === 'check_local' ? localPathEl.value.trim() : '';

      const storageData = await chrome.storage.local.get(['captured_token', 'extractedToken']);
      let token = tokenEl.value.trim() || storageData.captured_token || storageData.extractedToken || null;

      if (!token) {
        console.log('[Popup] Токен не найден, отправка без токена (доступен только обычный контент)');
      }

      if (token && !token.toLowerCase().startsWith('bearer ')) {
        token = `Bearer ${token}`;
      }

      const requestBody = {
        slugs: slugs,
        mode: mode,
        domain: domain
      };

      if (localPath) {
        requestBody.path = localPath;
      }

      if (token) {
        requestBody.token = token;
      }

      const fetchResponse = await fetch(`${serverUrl}/check`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });

      if (!fetchResponse.ok) {
        const errorData = await fetchResponse.json().catch(() => ({ error: 'Неизвестная ошибка' }));
        throw new Error(errorData.error || `Ошибка сервера: ${fetchResponse.status}`);
      }

      const results = await fetchResponse.json();

      displayResults(results);
      statusEl.textContent = 'Успешно отправлено!';
      statusEl.className = 'status-value success';
      showNotification(`Успешно отправлено ${slugs.length} slug на сервер`, 'success');

    } catch (error) {
      console.error('Ошибка отправки на сервер:', error);
      statusEl.textContent = `Ошибка: ${error.message}`;
      statusEl.className = 'status-value error';
      showNotification(`Ошибка: ${error.message}`, 'error');
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = 'Отправить на сервер';
    }
  });

  function displayResults(results) {
    resultsSection.style.display = 'block';

    if (!results || results.length === 0) {
      resultsEl.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 20px;">Нет результатов.</p>';
      chrome.storage.local.set({ lastResults: null });
      return;
    }

    chrome.storage.local.set({ lastResults: results });

    const total = results.length;
    const isOk = (s) => {
      if (!s) return false;
      return s === 'OK' || s === 'API OK' || s === 'Актуально';
    };
    const isMissing = (s) => {
      if (!s) return false;
      return s === 'Missing' || s.startsWith('Не хватает');
    };
    const isError = (s) => {
      if (!s) return false;
      return s.includes('404') || s.includes('Error') || s.includes('Ошибка');
    };

    const okCount = results.filter(r => isOk(r.status)).length;
    const missingCount = results.filter(r => isMissing(r.status)).length;
    const errorCount = results.filter(r => isError(r.status) && !isMissing(r.status)).length;

    let html = `
      <div class="summary">
        <strong>Всего:</strong> <span>${total}</span>
        <span class="ok">OK: ${okCount}</span>
        <span class="missing">Отсутствует: ${missingCount}</span>
        <span class="error">Ошибки: ${errorCount}</span>
      </div>
      <div class="results-list">
    `;

    results.forEach(result => {
      const statusClass = isOk(result.status) ? 'ok' :
                         isMissing(result.status) ? 'missing' : 'error';
      html += `
        <div class="result-item ${statusClass}">
          <div class="result-slug">${result.slug}</div>
          <div class="result-status">${result.status}</div>
          <div class="result-info">
            Локально: ${result.local_count || 'Н/Д'} | Сервер: ${result.server_count || 0}
            ${result.missing && result.missing.length > 0 ? ` | Отсутствует: ${result.missing.join(', ')}` : ''}
          </div>
        </div>
      `;
    });

    html += '</div>';
    resultsEl.innerHTML = html;
  }

  function loadPersistedResults() {
    chrome.storage.local.get(['lastResults'], (result) => {
      if (result.lastResults && Array.isArray(result.lastResults) && result.lastResults.length > 0) {
        displayResults(result.lastResults);
      }
    });
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'slugCount') {
      slugCount = message.count;
      slugCountEl.textContent = slugCount;
      sendBtn.disabled = slugCount === 0;

      if (message.isCollecting && !isCollecting) {
        isCollecting = true;
        startBtn.disabled = true;
        stopBtn.disabled = false;
        statusEl.textContent = 'Сбор...';
        statusEl.className = 'status-value collecting';
      }
    } else if (message.type === 'collectionComplete') {
      isCollecting = false;
      startBtn.disabled = false;
      stopBtn.disabled = true;
      statusEl.textContent = 'Сбор завершён';
      statusEl.className = 'status-value success';
      showNotification('Сбор завершён!', 'success');
    }
  });

  chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
    if (tabs[0]) {
      try {
        const response = await chrome.tabs.sendMessage(tabs[0].id, { type: 'getStatus' });
        if (response) {
          slugCount = response.count || 0;
          slugCountEl.textContent = slugCount;
          sendBtn.disabled = slugCount === 0;

          if (response.isCollecting) {
            isCollecting = true;
            startBtn.disabled = true;
            stopBtn.disabled = false;
            statusEl.textContent = 'Сбор...';
            statusEl.className = 'status-value collecting';
          }
        }
      } catch (error) {
        chrome.storage.local.get(['collectedSlugs'], (result) => {
          if (result.collectedSlugs && Array.isArray(result.collectedSlugs)) {
            slugCount = result.collectedSlugs.length;
            slugCountEl.textContent = slugCount;
            sendBtn.disabled = slugCount === 0;
          }
        });
      }
    }

    loadPersistedResults();
  });

  chrome.storage.local.get(['extractedToken', 'serverUrl', 'domain'], (result) => {
    if (result.extractedToken) {
      tokenEl.value = result.extractedToken;
    }
    if (result.serverUrl) {
      serverUrlEl.value = result.serverUrl;
    }
    if (result.domain) {
      domainEl.value = result.domain;
      checkTokenVisibility();
    }
  });

  serverUrlEl.addEventListener('change', () => {
    chrome.storage.local.set({ serverUrl: serverUrlEl.value });
    checkServerStatus(); // Немедленная проверка при изменении
  });

  domainEl.addEventListener('change', () => {
    chrome.storage.local.set({ domain: domainEl.value });
    checkTokenVisibility();
  });

  // Инициализация проверки статуса сервера
  startServerStatusPolling();
});
