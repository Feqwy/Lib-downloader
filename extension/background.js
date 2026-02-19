chrome.runtime.onInstalled.addListener(() => {
  console.log('Расширение Lib Downloader установлено');
});

// Перехват сетевых запросов для захвата заголовка Authorization
const targetUrls = [
  "*://hapi.hentaicdn.org/api/*", // Shlib
  "*://api.cdnlibs.org/api/*",    // Mangalib
  "*://api.cdnlibs.org/api/*"    // RanobeLib (if different API)
];

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    const authHeader = details.requestHeaders.find(
      (h) => h.name.toLowerCase() === "authorization"
    );

    if (authHeader && authHeader.value) {
      // Удалить префикс "Bearer ", если присутствует
      let token = authHeader.value;
      if (token.startsWith('Bearer ') || token.startsWith('bearer ')) {
        token = token.substring(7);
      }
      // Пропустить XSRF токены
      if (!token.includes('XSRF') && !token.toLowerCase().includes('xsrf') && token.length > 20) {
        chrome.storage.local.set({ 'captured_token': token });
        console.log('[Захват токена] Токен авторизации перехвачен из сетевого запроса');
      }
    }
  },
  { urls: targetUrls },
  ["requestHeaders"]
);

// Обработка сообщений между content script и popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // В основном обрабатывается в popup.js и content.js
  // Background script может использоваться для межвкладочного общения при необходимости
  return true;
});
