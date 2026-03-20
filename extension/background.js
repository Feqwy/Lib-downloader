chrome.runtime.onInstalled.addListener(() => {
  console.log('Расширение Lib Downloader установлено');
});

// Перехват сетевых запросов для захвата заголовка Authorization
const targetUrls = [
  "*://hapi.hentaicdn.org/api/*",     // Shlib, HentaiLib
  "*://api.cdnlibs.org/api/*",        // Mangalib, RanobeLib
  "*://mangalib.me/api/*",            // Mangalib прямой доступ
  "*://ranobelib.me/api/*",           // RanobeLib прямой доступ
  "*://hentailib.me/api/*",           // HentaiLib прямой доступ
  "*://v2.shlib.life/api/*",          // Shlib прямой доступ
];

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    console.log('[webRequest] Перехвачен запрос:', details.url);
    console.log('[webRequest] Domain:', details.url.split('/')[2]);

    const authHeader = details.requestHeaders.find(
      (h) => h.name.toLowerCase() === "authorization"
    );

    if (authHeader && authHeader.value) {
      console.log('[webRequest] Найден Authorization заголовок');
      // Удалить префикс "Bearer ", если присутствует
      let token = authHeader.value;
      if (token.startsWith('Bearer ') || token.startsWith('bearer ')) {
        token = token.substring(7);
        console.log('[webRequest] Удалён префикс Bearer');
      }
      // Пропустить XSRF токены
      if (!token.includes('XSRF') && !token.toLowerCase().includes('xsrf') && token.length > 20) {
        chrome.storage.local.set({ 'captured_token': token });
        console.log('[Захват токена] Токен авторизации перехвачен из сетевого запроса:', token.substring(0, 20) + '...');
      } else {
        console.log('[webRequest] Токен пропущен (XSRF или слишком короткий), длина:', token.length);
      }
    } else {
      console.log('[webRequest] Authorization заголовок не найден в запросе');
      console.log('[webRequest] Все заголовки:', details.requestHeaders.map(h => h.name).join(', '));
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
