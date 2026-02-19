(function() {
  'use strict';

  let isCollecting = false;
  let collectedSlugs = new Set();
  let scrollInterval = null;
  let lastHeight = 0;
  let stableCount = 0;
  const STABLE_THRESHOLD = 3; // Количество проверок с одинаковой высотой
  const SCROLL_DELAY = 500; // Задержка между прокрутками в мс
  const SCROLL_AMOUNT = 300; // Пикселей прокрутки за раз

  // Загрузка сохранённых slug из хранилища
  function loadPersistedSlugs() {
    chrome.storage.local.get(['collectedSlugs', 'isCollecting'], (result) => {
      if (result.collectedSlugs && Array.isArray(result.collectedSlugs)) {
        collectedSlugs = new Set(result.collectedSlugs);
        sendSlugCount();
      }
      if (result.isCollecting) {
        isCollecting = result.isCollecting;
        if (isCollecting) {
          startCollecting();
        }
      }
    });
  }

  // Сохранение slug в хранилище
  function saveSlugsToStorage() {
    chrome.storage.local.set({
      collectedSlugs: Array.from(collectedSlugs),
      isCollecting: isCollecting
    });
  }

  // Извлечение slug из URL
  function extractSlug(url) {
    try {
      // Обработка абсолютных и относительных URL
      let urlObj;
      try {
        urlObj = new URL(url);
      } catch (e) {
        // Если URL относительный, делаем его абсолютным
        urlObj = new URL(url, window.location.origin);
      }

      const pathParts = urlObj.pathname.split('/').filter(p => p); // Удаляем пустые части

      // Обработка ranobelib.me — использует /book/ вместо /manga/
      const isRanobelib = urlObj.hostname.includes('ranobelib.me') || url.includes('ranobelib.me');

      if (isRanobelib) {
        // Для ranobelib: /ru/book/235071--serdce-iz-roz -> 235071--serdce-iz-roz
        const bookIndex = pathParts.indexOf('book');
        if (bookIndex !== -1 && bookIndex < pathParts.length - 1) {
          // Получаем slug после 'book'
          const slug = pathParts[bookIndex + 1];
          // Удаляем параметры запроса, если они есть
          return slug.split('?')[0].split('#')[0];
        }
        // Также проверяем /ranobe/ как запасной вариант
        const ranobeIndex = pathParts.indexOf('ranobe');
        if (ranobeIndex !== -1 && ranobeIndex < pathParts.length - 1) {
          return pathParts[ranobeIndex + 1].split('?')[0].split('#')[0];
        }
      } else {
        // Для mangalib: /ru/manga/125967--vizir -> 125967--vizir
        const mangaIndex = pathParts.indexOf('manga');
        if (mangaIndex !== -1 && mangaIndex < pathParts.length - 1) {
          return pathParts[mangaIndex + 1].split('?')[0].split('#')[0];
        }
      }

      // Запасной вариант: пытаемся получить последнюю значимую часть
      const lastPart = pathParts[pathParts.length - 1];
      if (lastPart && lastPart !== 'manga' && lastPart !== 'ranobe' && lastPart !== 'book' && lastPart !== 'ru' && lastPart !== '') {
        return lastPart.split('?')[0].split('#')[0];
      }
    } catch (e) {
      console.error('Ошибка извлечения slug из URL:', url, e);
    }
    return null;
  }

  // Извлечение slug из всех ссылок на странице
  function extractSlugsFromPage() {
    const isRanobelib = window.location.href.includes('ranobelib.me');
    const slugs = new Set();

    // Получаем все ссылки на странице
    const allLinks = document.querySelectorAll('a[href]');
    let checkedCount = 0;
    let foundCount = 0;

    allLinks.forEach(link => {
      const href = link.getAttribute('href');
      if (!href) return;

      checkedCount++;

      try {
        // Преобразуем относительные URL в абсолютные
        const fullUrl = href.startsWith('http') ? href : new URL(href, window.location.origin).href;

        // Для ranobelib ищем /book/ в URL
        if (isRanobelib && fullUrl.includes('/book/')) {
          const slug = extractSlug(fullUrl);
          if (slug) {
            slugs.add(slug);
            foundCount++;
          }
        }
        // Для остальных сайтов ищем /manga/
        else if (!isRanobelib && fullUrl.includes('/manga/')) {
          const slug = extractSlug(fullUrl);
          if (slug) {
            slugs.add(slug);
            foundCount++;
          }
        }
      } catch (e) {
        // Пропускаем некорректные URL
        console.debug('[Lib Downloader] Пропуск некорректного URL:', href, e);
      }
    });

    if (foundCount > 0) {
      console.log(`[Lib Downloader] Найдено ${foundCount} slug'ов из ${checkedCount} ссылок`);
    }

    return slugs;
  }

  // Умная функция автопрокрутки
  function smartScroll() {
    if (!isCollecting) return;

    const currentHeight = document.documentElement.scrollHeight;
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const windowHeight = window.innerHeight;

    // Проверяем, достигли ли мы низа страницы
    if (scrollTop + windowHeight >= currentHeight - 100) {
      // Если высота не менялась несколько проверок, завершаем
      if (currentHeight === lastHeight) {
        stableCount++;
        if (stableCount >= STABLE_THRESHOLD) {
          stopCollecting();
          notifyCollectionComplete();
          return;
        }
      } else {
        stableCount = 0;
      }
      lastHeight = currentHeight;

      // Ждём загрузки контента, затем прокручиваем
      setTimeout(() => {
        window.scrollBy(0, SCROLL_AMOUNT);
      }, SCROLL_DELAY);
    } else {
      // Продолжаем прокрутку
      window.scrollBy(0, SCROLL_AMOUNT);
      stableCount = 0;
    }

    // Обновляем собранные slug периодически
    const newSlugs = extractSlugsFromPage();
    newSlugs.forEach(slug => collectedSlugs.add(slug));

    // Отправляем обновлённое количество в popup
    sendSlugCount();
  }

  // Начало сбора slug с автопрокруткой
  function startCollecting() {
    if (isCollecting) return;

    isCollecting = true;
    // Не очищаем при возобновлении — только при явном перезапуске
    if (!collectedSlugs.size) {
      collectedSlugs.clear();
    }
    lastHeight = 0;
    stableCount = 0;

    // Начальное извлечение
    const initialSlugs = extractSlugsFromPage();
    initialSlugs.forEach(slug => collectedSlugs.add(slug));

    // Запуск автопрокрутки
    scrollInterval = setInterval(smartScroll, SCROLL_DELAY);

    // Используем MutationObserver для обнаружения динамически добавленного контента
    observePageChanges();

    saveSlugsToStorage();
    sendSlugCount();
  }

  // Остановка сбора
  function stopCollecting() {
    isCollecting = false;
    if (scrollInterval) {
      clearInterval(scrollInterval);
      scrollInterval = null;
    }
    saveSlugsToStorage();
    sendSlugCount();
  }

  // Наблюдение за изменениями DOM для динамически загружаемого контента
  let observer = null;
  function observePageChanges() {
    if (observer) {
      observer.disconnect();
    }

    observer = new MutationObserver(() => {
      if (isCollecting) {
        const newSlugs = extractSlugsFromPage();
        const beforeCount = collectedSlugs.size;
        newSlugs.forEach(slug => collectedSlugs.add(slug));
        if (collectedSlugs.size > beforeCount) {
          sendSlugCount();
        }
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  // Отправка количества slug в popup
  function sendSlugCount() {
    saveSlugsToStorage(); // Сохраняем при каждом обновлении
    chrome.runtime.sendMessage({
      type: 'slugCount',
      count: collectedSlugs.size,
      isCollecting: isCollecting
    });
  }

  // Уведомление о завершении сбора
  function notifyCollectionComplete() {
    chrome.runtime.sendMessage({
      type: 'collectionComplete',
      count: collectedSlugs.size
    });
  }

  // Получение собранных slug
  function getCollectedSlugs() {
    return Array.from(collectedSlugs);
  }

  // Прослушка сообщений от popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.type === 'ping') {
      sendResponse({ success: true, ready: true });
    } else if (request.type === 'startCollection') {
      startCollecting();
      sendResponse({ success: true });
    } else if (request.type === 'stopCollection') {
      stopCollecting();
      sendResponse({ success: true });
    } else if (request.type === 'clearSlugs') {
      collectedSlugs.clear();
      saveSlugsToStorage();
      sendSlugCount();
      sendResponse({ success: true });
    } else if (request.type === 'getSlugs') {
      sendResponse({ slugs: getCollectedSlugs(), count: collectedSlugs.size });
    } else if (request.type === 'getStatus') {
      sendResponse({
        isCollecting: isCollecting,
        count: collectedSlugs.size
      });
    }
    return true; // Держим канал открытым для асинхронного ответа
  });

  // Инициализация: загрузка сохранённых данных и проверка необходимости сбора
  console.log('[Lib Downloader] Content script загружен на:', window.location.href);
  loadPersistedSlugs();

  // Также извлекаем slug при начальной загрузке
  setTimeout(() => {
    const initialSlugs = extractSlugsFromPage();
    const beforeCount = collectedSlugs.size;
    initialSlugs.forEach(slug => collectedSlugs.add(slug));
    if (collectedSlugs.size > beforeCount) {
      console.log('[Lib Downloader] Найдено', collectedSlugs.size - beforeCount, 'новых slug\'ов при загрузке страницы');
    }
    saveSlugsToStorage();
    sendSlugCount();
  }, 2000);

})();
