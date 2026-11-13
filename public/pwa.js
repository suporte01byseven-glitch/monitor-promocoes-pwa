(() => {
  const installButton = document.getElementById('installApp');
  const offlineNotice = document.getElementById('offlineNotice');
  let installPrompt = null;

  function updateConnectionState() {
    if (offlineNotice) offlineNotice.classList.toggle('hidden', navigator.onLine);
  }

  window.addEventListener('online', updateConnectionState);
  window.addEventListener('offline', updateConnectionState);
  updateConnectionState();

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    if (installButton) installButton.classList.remove('hidden');
  });

  installButton?.addEventListener('click', async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null;
    installButton.classList.add('hidden');
  });

  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    installButton?.classList.add('hidden');
  });

  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' })
        .catch(error => console.error('Falha ao registrar o service worker:', error));
    });
  }
})();
