(() => {
  const themeButtons = Array.from(document.querySelectorAll('[data-theme-preference]'));
  const refreshButton = document.getElementById('refresh-library');
  const clearCacheButton = document.getElementById('clear-cache');
  const resetButton = document.getElementById('reset-recommendations');
  const credentialMask = document.getElementById('credential-mask');
  const pairingMask = document.getElementById('pairing-mask');
  const pairingServerUrl = document.getElementById('pairing-server-url');
  const pairingResult = document.getElementById('pairing-result');
  const pairingQr = document.getElementById('pairing-qr');
  const pairingLink = document.getElementById('pairing-link');
  const pairingExpiry = document.getElementById('pairing-expiry');
  const copyPairingButton = document.getElementById('copy-radio-pairing');
  const openRadioLink = document.getElementById('open-radio-link');
  const radioDeviceList = document.getElementById('radio-device-list');
  let pairingTimer = 0;

  function currentThemePreference() {
    const saved = localStorage.getItem('theme');
    return ['light', 'dark', 'system'].includes(saved) ? saved : 'system';
  }

  function syncThemeButtons(preference = currentThemePreference()) {
    themeButtons.forEach((button) => {
      const active = button.dataset.themePreference === preference;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }

  function setThemePreference(preference) {
    if (window.themeManager?.setPreference) {
      window.themeManager.setPreference(preference);
    } else {
      localStorage.setItem('theme', preference);
      const resolved = preference === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : preference;
      document.body.setAttribute('data-theme', resolved);
    }
    syncThemeButtons(preference);
  }


  async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok || payload.success === false) {
      const message = typeof payload.error === 'object' ? payload.error?.message : payload.error;
      throw new Error(message || 'Request failed');
    }
    return payload;
  }

  async function requestForm(url, formData) {
    const response = await fetch(url, { method: 'POST', body: formData });
    const payload = await response.json();
    if (!response.ok || payload.success === false) throw new Error(payload.error || 'Request failed');
    return payload;
  }

  function formatSyncTime(value) {
    if (!value) return 'No scan completed yet';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'A scan completed recently';
    return `Last scanned: ${date.toLocaleString('en')}`;
  }

  async function loadStats() {
    try {
      const payload = await requestJson('/api/library/stats');
      const videos = Number(payload.videos || 0);
      const images = Number(payload.images || 0);
      document.getElementById('media-total').textContent = Number(payload.indexed_total || videos + images);
      document.getElementById('videos-count').textContent = videos;
      document.getElementById('images-count').textContent = images;
      document.getElementById('cache-size').textContent = `${Number(payload.cache_mb || 0)} MB`;
      document.getElementById('index-sync-copy').textContent = formatSyncTime(payload.last_synced_at);
      document.getElementById('index-sync-state').classList.remove('is-error');
    } catch (error) {
      document.getElementById('index-sync-copy').textContent = 'Index status is unavailable';
      document.getElementById('index-sync-state').classList.add('is-error');
    }
  }

  function formatDeviceTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Pairing time unknown' : `Paired ${date.toLocaleString('en')}`;
  }

  function renderRadioDevices(devices = []) {
    radioDeviceList.replaceChildren();
    if (!devices.length) {
      const row = document.createElement('div');
      row.className = 'settings-row';
      row.innerHTML = '<span class="setting-icon"><i data-feather="radio"></i></span><div class="settings-row-main"><div class="settings-row-title">No Radio clients yet</div><div class="settings-row-copy">Enter this server address and access password in TikLocal Radio to pair.</div></div>';
      radioDeviceList.appendChild(row);
      feather.replace();
      return;
    }

    devices.forEach((device) => {
      const row = document.createElement('div');
      row.className = 'settings-row';
      const icon = document.createElement('span');
      icon.className = 'setting-icon';
      icon.innerHTML = '<i data-feather="smartphone"></i>';
      const main = document.createElement('div');
      main.className = 'settings-row-main';
      const title = document.createElement('div');
      title.className = 'settings-row-title';
      title.textContent = device.name || 'TikLocal Radio';
      const copy = document.createElement('div');
      copy.className = `settings-row-copy radio-device-state${device.active ? '' : ' is-expired'}`;
      copy.textContent = `${device.active ? 'Token active' : 'Invalidated by password change'} · ${formatDeviceTime(device.created_at)}`;
      const revoke = document.createElement('button');
      revoke.className = 'settings-action is-danger';
      revoke.type = 'button';
      revoke.textContent = 'Revoke';
      revoke.addEventListener('click', () => {
        confirmAction(
          'Revoke this Radio client?',
          `${device.name || 'This device'} will lose media access and must pair again with the access password.`,
          'Revoke Client',
          'danger',
          () => {
            runButton(revoke, 'Revoking…', async () => {
              await requestJson(`/api/radio/devices/${encodeURIComponent(device.id)}`, { method: 'DELETE' });
              await loadRadioDevices();
              TikLocalUI.toast('Radio client revoked');
            }).catch(() => TikLocalUI.toast('Failed to revoke the client. Please try again later.', 'error'));
          },
        );
      });
      main.append(title, copy);
      row.append(icon, main, revoke);
      radioDeviceList.appendChild(row);
    });
    feather.replace();
  }

  async function loadRadioDevices() {
    try {
      const payload = await requestJson('/api/radio/devices');
      renderRadioDevices(payload.data?.devices || []);
    } catch (_) {
      radioDeviceList.querySelector('.settings-row-copy').textContent = 'Paired devices are unavailable.';
    }
  }

  async function confirmAction(title, copy, actionLabel, tone, onConfirm) {
    if (await TikLocalUI.confirm({ title, message: copy, confirmLabel: actionLabel, tone })) onConfirm();
  }

  async function runButton(button, busyLabel, task) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = busyLabel;
    try { await task(); } finally { button.disabled = false; button.textContent = original; }
  }

  function renderCredentials(files = []) {
    const list = document.getElementById('credential-list');
    document.getElementById('credential-summary').textContent = files.length ? `${files.length} credential files saved and matched to websites automatically.` : 'None added. Public content can still be downloaded.';
    if (!files.length) {
      list.innerHTML = '<div class="credential-empty">No credentials saved</div>';
    } else {
      list.innerHTML = files.map((name) => `
        <div class="credential-item"><span class="credential-mark"><i data-feather="key"></i></span><span class="credential-name"></span></div>`).join('');
      list.querySelectorAll('.credential-name').forEach((element, index) => { element.textContent = files[index]; });
    }
    feather.replace();
  }

  async function loadDownloadSettings() {
    try {
      const [probePayload, configPayload, cookiePayload] = await Promise.all([
        requestJson('/api/download/probe', { method: 'POST' }),
        requestJson('/api/download/config'),
        requestJson('/api/download/cookies'),
      ]);
      const probe = probePayload.data || {};
      const missing = [!probe.yt_dlp_available ? 'video' : '', !probe.gallery_dl_available ? 'image' : '', !probe.ffmpeg_available ? 'media merging' : ''].filter(Boolean);
      document.getElementById('download-dependency-copy').textContent = missing.length ? `${missing.join(', ')} components are not ready.` : 'Image and video downloads are ready.';
      const configured = Number(configPayload.data?.effective?.max_concurrent ?? 2);
      const shown = [1, 2, 4].includes(configured) ? configured : 2;
      document.querySelectorAll('[data-concurrency]').forEach((button) => button.classList.toggle('is-active', Number(button.dataset.concurrency) === shown));
      renderCredentials(cookiePayload.data?.files || []);
    } catch (_) {
      document.getElementById('download-dependency-copy').textContent = 'Download status is unavailable.';
      document.getElementById('credential-summary').textContent = 'Credentials are unavailable.';
    }
  }

  function openCredentials() {
    credentialMask.hidden = false;
    document.body.style.overflow = 'hidden';
    document.getElementById('close-credentials').focus();
  }

  function closeCredentials() {
    credentialMask.hidden = true;
    document.body.style.overflow = '';
    document.getElementById('manage-credentials').focus();
  }

  function updatePairingWarning() {
    let warning = '';
    try {
      const hostname = new URL(pairingServerUrl.value).hostname;
      if (['localhost', '127.0.0.1', '::1'].includes(hostname)) {
        warning = 'This address only reaches the current computer. Use a LAN IP, .local hostname, or HTTPS address your phone can reach.';
      }
    } catch (_) {
      warning = 'Enter a complete http:// or https:// address.';
    }
    document.getElementById('pairing-warning').textContent = warning;
  }

  function stopPairingTimer() {
    if (pairingTimer) window.clearInterval(pairingTimer);
    pairingTimer = 0;
  }

  function startPairingTimer(expiresIn) {
    stopPairingTimer();
    const deadline = Date.now() + Math.max(0, Number(expiresIn || 0)) * 1000;
    const render = () => {
      const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      const minutes = Math.floor(seconds / 60);
      pairingExpiry.textContent = seconds
        ? `This single-use link expires in ${minutes}:${String(seconds % 60).padStart(2, '0')}.`
        : 'This link has expired. Generate a new one.';
      copyPairingButton.disabled = !seconds;
      openRadioLink.setAttribute('aria-disabled', String(!seconds));
      if (!seconds) stopPairingTimer();
    };
    render();
    pairingTimer = window.setInterval(render, 1000);
  }

  function openRadioPairing() {
    pairingServerUrl.value = window.location.origin;
    pairingResult.hidden = true;
    copyPairingButton.hidden = true;
    openRadioLink.hidden = true;
    pairingLink.value = '';
    pairingQr.removeAttribute('src');
    stopPairingTimer();
    updatePairingWarning();
    pairingMask.hidden = false;
    document.body.style.overflow = 'hidden';
    pairingServerUrl.focus();
  }

  function closeRadioPairing() {
    stopPairingTimer();
    pairingMask.hidden = true;
    document.body.style.overflow = '';
    document.getElementById('open-radio-pairing').focus();
  }

  async function copyPairingLink() {
    try {
      await navigator.clipboard.writeText(pairingLink.value);
    } catch (_) {
      pairingLink.focus();
      pairingLink.select();
      document.execCommand('copy');
    }
    TikLocalUI.toast('Pairing link copied');
  }

  themeButtons.forEach((button) => button.addEventListener('click', () => setThemePreference(button.dataset.themePreference)));
  window.addEventListener('tiklocal:theme-changed', (event) => syncThemeButtons(event.detail?.preference));
  syncThemeButtons();

  refreshButton.addEventListener('click', () => {
    confirmAction('Rescan the media library?', 'The scan will reconcile files added, moved, or deleted while TikLocal was running.', 'Start Scan', 'primary', () => {
      runButton(refreshButton, 'Scanning…', async () => {
        const payload = await requestJson('/api/library/sync', { method: 'POST' });
        await loadStats();
        TikLocalUI.toast(`Scan complete. Indexed ${Number(payload.data?.indexed || 0)} media items.`);
      }).catch(() => TikLocalUI.toast('Scan failed. Please try again later.', 'error'));
    });
  });

  clearCacheButton.addEventListener('click', () => {
    confirmAction('Clear the thumbnail cache?', 'Original media will be kept. Thumbnails regenerate as needed while browsing.', 'Clear Cache', 'warning', () => {
      runButton(clearCacheButton, 'Clearing…', async () => {
        const payload = await requestJson('/api/cache/clear', { method: 'POST' });
        await loadStats();
        TikLocalUI.toast(`Freed ${Number(payload.freed_mb || 0)} MB`);
      }).catch(() => TikLocalUI.toast('Cleanup failed. Please try again later.', 'error'));
    });
  });

  resetButton.addEventListener('click', () => {
    confirmAction('Reset recommendation history?', 'Views, skips, completions, and resume points will be cleared. Favorites and collections remain unchanged.', 'Reset History', 'danger', () => {
      runButton(resetButton, 'Resetting…', async () => {
        await requestJson('/api/activity', { method: 'DELETE' });
        TikLocalUI.toast('Recommendation history reset');
      }).catch(() => TikLocalUI.toast('Reset failed. Please try again later.', 'error'));
    });
  });

  document.getElementById('download-levels').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-concurrency]');
    if (!button) return;
    const maxConcurrent = Number(button.dataset.concurrency);
    try {
      await requestJson('/api/download/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_concurrent: maxConcurrent }),
      });
      document.querySelectorAll('[data-concurrency]').forEach((item) => item.classList.toggle('is-active', item === button));
      TikLocalUI.toast(`Concurrent downloads set to ${maxConcurrent}`);
    } catch (_) { TikLocalUI.toast('Failed to save download settings', 'error'); }
  });

  document.getElementById('manage-credentials').addEventListener('click', openCredentials);
  document.getElementById('close-credentials').addEventListener('click', closeCredentials);
  credentialMask.addEventListener('click', (event) => { if (event.target === credentialMask) closeCredentials(); });
  credentialMask.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeCredentials(); });
  document.getElementById('open-radio-pairing').addEventListener('click', openRadioPairing);
  document.getElementById('close-radio-pairing').addEventListener('click', closeRadioPairing);
  pairingMask.addEventListener('click', (event) => { if (event.target === pairingMask) closeRadioPairing(); });
  pairingMask.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeRadioPairing(); });
  pairingServerUrl.addEventListener('input', updatePairingWarning);
  copyPairingButton.addEventListener('click', () => void copyPairingLink());
  document.getElementById('generate-radio-pairing').addEventListener('click', (event) => {
    runButton(event.currentTarget, 'Generating…', async () => {
      const payload = await requestJson('/api/radio/pairing-grants', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_url: pairingServerUrl.value }),
      });
      const data = payload.data || {};
      pairingLink.value = data.pairing_uri || '';
      pairingQr.src = data.qr_data_uri || '';
      pairingResult.hidden = false;
      copyPairingButton.hidden = false;
      openRadioLink.hidden = false;
      openRadioLink.href = pairingLink.value;
      openRadioLink.setAttribute('aria-disabled', 'false');
      startPairingTimer(data.expires_in);
    }).catch((error) => TikLocalUI.toast(error.message || 'Failed to generate pairing link', 'error'));
  });
  document.getElementById('upload-credential').addEventListener('click', (event) => {
    const input = document.getElementById('credential-file');
    const file = input.files?.[0];
    if (!file) { TikLocalUI.toast('Select a credential file first', 'error'); return; }
    runButton(event.currentTarget, 'Uploading…', async () => {
      const formData = new FormData();
      formData.append('file', file);
      await requestForm('/api/download/cookies/upload', formData);
      input.value = '';
      const payload = await requestJson('/api/download/cookies');
      renderCredentials(payload.data?.files || []);
      TikLocalUI.toast('Credentials updated');
    }).catch(() => TikLocalUI.toast('Failed to upload credentials', 'error'));
  });

  function formatBytes(bytes) {
    const mb = Number(bytes || 0) / 1048576;
    return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(1)} MB`;
  }

  function renderTrash(items, retentionDays) {
    const list = document.getElementById('trash-list');
    const total = items.reduce((sum, item) => sum + Number(item.size || 0), 0);
    document.getElementById('trash-summary').textContent = items.length
      ? `${items.length} ${items.length === 1 ? 'item' : 'items'} · ${formatBytes(total)}. Kept for ${retentionDays} days, then removed.`
      : `Deleted media stays here for ${retentionDays} days.`;
    document.getElementById('empty-trash').hidden = !items.length;
    list.querySelectorAll('.trash-item').forEach((row) => row.remove());
    items.forEach((item) => {
      const days = Math.max(0, retentionDays - Math.floor((Date.now() - new Date(item.deleted_at)) / 86400000));
      const row = document.createElement('div');
      row.className = 'settings-row trash-item';
      row.innerHTML = `<span class="setting-icon"><i data-feather="${/\.(jpe?g|png|gif|webp|bmp)$/i.test(item.name) ? 'image' : 'film'}"></i></span><div class="settings-row-main"><div class="settings-row-title trash-name"></div><div class="settings-row-copy"></div></div>`;
      row.querySelector('.trash-name').textContent = item.name;
      row.querySelector('.settings-row-copy').textContent = `${formatBytes(item.size)} · ${days} days left`;
      const restore = document.createElement('button');
      restore.className = 'settings-action';
      restore.type = 'button';
      restore.textContent = 'Restore';
      restore.addEventListener('click', () => {
        runButton(restore, 'Restoring…', async () => {
          const data = await requestJson(`/api/trash/${encodeURIComponent(item.id)}/restore`, { method: 'POST' });
          await Promise.all([loadTrash(), loadStats()]);
          TikLocalUI.toast(`Restored ${item.name}`, 'success', { label: 'Open', run: () => { location.href = data.url; } });
        }).catch((error) => TikLocalUI.toast(error.message || 'Restore failed. Please try again.', 'error'));
      });
      const purge = document.createElement('button');
      purge.className = 'settings-action is-danger';
      purge.type = 'button';
      purge.textContent = 'Delete';
      purge.addEventListener('click', () => {
        confirmAction(`Delete ${item.name} permanently?`, 'The file is removed from disk and cannot be restored.', 'Delete', 'danger', () => {
          runButton(purge, 'Deleting…', async () => {
            await requestJson(`/api/trash/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
            await loadTrash();
          }).catch(() => TikLocalUI.toast('Delete failed. Please try again.', 'error'));
        });
      });
      row.querySelector('.settings-row-main').after(restore, purge);
      list.appendChild(row);
    });
    feather.replace();
  }

  async function loadTrash() {
    try {
      const data = await requestJson('/api/trash');
      renderTrash(data.items || [], data.retention_days || 30);
    } catch (_) {
      document.getElementById('trash-summary').textContent = 'Trash is unavailable.';
    }
  }

  document.getElementById('empty-trash').addEventListener('click', (event) => {
    const button = event.currentTarget;
    confirmAction('Empty the trash?', 'Every file in the trash is removed from disk and cannot be restored.', 'Empty Trash', 'danger', () => {
      runButton(button, 'Emptying…', async () => {
        const data = await requestJson('/api/trash', { method: 'DELETE' });
        await loadTrash();
        TikLocalUI.toast(`Deleted ${data.purged} items permanently`);
      }).catch(() => TikLocalUI.toast('Failed to empty the trash. Please try again.', 'error'));
    });
  });

  loadStats();
  loadRadioDevices();
  loadTrash();
  loadDownloadSettings();
})();
