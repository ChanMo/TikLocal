(() => {
  const ACTIVE_STATUSES = new Set(['queued', 'running']);
  const IMAGE_EXTENSIONS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']);
  let pollTimer = null;
  let lastJobsSignature = '';
  let dependencyMeta = { yt_dlp_available: false, gallery_dl_available: false, ffmpeg_available: false };
  let selectedEngine = 'yt-dlp';

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function notify(message, type = 'info') {
    const wrap = document.getElementById('toast-wrap');
    if (!wrap) return;
    const toast = document.createElement('div');
    toast.className = `alert ${type === 'error' ? 'alert-error' : 'alert-success'} alert-soft text-xs`;
    toast.textContent = message;
    wrap.appendChild(toast);
    window.setTimeout(() => toast.remove(), 2800);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.error || `Request failed (${response.status})`);
    }
    return payload.data || {};
  }

  function safeHostname(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, '') || 'External link';
    } catch (_) {
      return 'External link';
    }
  }

  function platformMark(url) {
    const hostname = safeHostname(url);
    const knownMarks = [
      ['instagram', 'IG'], ['youtube', 'YT'], ['youtu.be', 'YT'],
      ['tiktok', 'TT'], ['x.com', 'X'], ['twitter', 'X'],
      ['pinterest', 'P'],
    ];
    const match = knownMarks.find(([part]) => hostname.includes(part));
    return match ? match[1] : hostname.slice(0, 2).toUpperCase();
  }

  function formatTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const today = new Date();
    if (date.toDateString() === today.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function buildMediaHref(file) {
    const value = String(file || '').trim();
    const dot = value.lastIndexOf('.');
    const extension = dot >= 0 ? value.slice(dot).toLowerCase() : '';
    if (IMAGE_EXTENSIONS.has(extension)) return `/image?uri=${encodeURIComponent(value)}`;
    return `/detail/${encodeURIComponent(value)}`;
  }

  function outputFiles(job) {
    const files = Array.isArray(job.output_files_rel)
      ? job.output_files_rel.filter((item) => String(item || '').trim())
      : [];
    if (!files.length && job.output_path_rel) files.push(job.output_path_rel);
    return files;
  }

  function statusCopy(job) {
    const fileCount = Number.isInteger(job.file_count) ? job.file_count : outputFiles(job).length;
    const labels = {
      queued: 'Waiting to start',
      running: typeof job.progress_percent === 'number' ? `${Math.round(job.progress_percent)}% complete` : 'Downloading',
      success: fileCount > 0 ? `Saved ${fileCount} files` : 'Saved to the media library',
      failed: 'Download failed',
      canceled: 'Canceled',
    };
    return labels[job.status] || 'Unknown status';
  }

  function renderJob(job) {
    const files = outputFiles(job);
    const firstFile = files[0] || '';
    const isActive = ACTIVE_STATUSES.has(job.status);
    const progress = typeof job.progress_percent === 'number'
      ? Math.max(0, Math.min(100, job.progress_percent))
      : null;
    const time = formatTime(job.finished_at || job.created_at);
    const accent = job.status === 'failed' ? 'border-error/40' : 'border-base-300';
    const sourceAction = `<a class="btn btn-ghost btn-xs gap-1" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer"><i data-feather="external-link" class="size-3.5"></i><span>Visit Source</span></a>`;

    // daisyUI's dropdown opens on focus, so the menu needs no open/close script.
    const menu = !isActive ? `
      <div class="dropdown dropdown-end dropdown-top">
        <button tabindex="0" class="btn btn-ghost btn-xs btn-circle" type="button" aria-label="More actions"><i data-feather="more-horizontal" class="size-3.5"></i></button>
        <ul tabindex="0" class="dropdown-content menu z-10 w-44 rounded-box border border-base-300 bg-base-100 p-1 shadow-lg">
          <li><button type="button" data-action="delete" data-job-id="${escapeHtml(job.id)}">Remove Record</button></li>
        </ul>
      </div>` : '';

    let actions = '';
    if (isActive) {
      actions = `${sourceAction}<button class="btn btn-ghost btn-xs" type="button" data-action="cancel" data-job-id="${escapeHtml(job.id)}">Cancel</button>`;
    } else if (job.status === 'success' && firstFile) {
      actions = `
        <a class="btn btn-ghost btn-xs gap-1" href="${buildMediaHref(firstFile)}"><i data-feather="eye" class="size-3.5"></i><span>View Media</span></a>
        ${sourceAction}${menu}`;
    } else {
      actions = `
        ${(job.status === 'failed' || job.status === 'canceled') ? `<button class="btn btn-ghost btn-xs gap-1" type="button" data-action="retry" data-job-id="${escapeHtml(job.id)}"><i data-feather="rotate-ccw" class="size-3.5"></i><span>${job.failure_stage === 'index' ? 'Register Again' : 'Download Again'}</span></button>` : ''}
        ${sourceAction}${menu}`;
    }

    return `
      <article class="card card-sm border ${accent} bg-base-100" data-job-id="${escapeHtml(job.id)}">
        <div class="card-body flex-row items-start gap-3 p-3">
          <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-base-200 text-[11px] font-bold opacity-70" aria-hidden="true">${escapeHtml(platformMark(job.url))}</div>
          <div class="min-w-0 flex-1">
            <div class="flex items-baseline justify-between gap-2">
              <div class="flex min-w-0 items-center gap-2">
                <span class="truncate text-sm font-semibold">${escapeHtml(safeHostname(job.url))}</span>
                <span class="badge badge-ghost badge-xs shrink-0">${escapeHtml(job.engine === 'gallery-dl' ? 'Images' : 'Video')}</span>
              </div>
              ${time ? `<span class="shrink-0 text-[10px] opacity-45">${escapeHtml(time)}</span>` : ''}
            </div>
            <p class="mt-1 text-xs opacity-60">${escapeHtml(statusCopy(job))}</p>
            ${progress !== null && isActive ? `<progress class="progress progress-primary mt-2 h-1.5 w-full" value="${progress.toFixed(1)}" max="100" aria-label="Download progress"></progress>` : ''}
            ${files.length > 1 ? `<div class="mt-1 text-[10px] opacity-45">${files.length} items</div>` : ''}
            ${job.error_message ? `<p class="mt-1 text-xs text-error">${escapeHtml(job.error_message)}</p>` : ''}
            <div class="mt-2 flex flex-wrap items-center gap-1">${actions}</div>
          </div>
        </div>
      </article>`;
  }

  function emptyHistory() {
    return `
      <div class="flex flex-col items-center gap-1.5 py-10 text-center">
        <i data-feather="download-cloud" class="size-6 opacity-35"></i>
        <div class="text-sm font-semibold opacity-70">No download history yet</div>
        <div class="text-xs opacity-50">Paste a link to add new media directly to your local library.</div>
      </div>`;
  }

  function jobsSignature(jobs) {
    return jobs.map((job) => [
      job.id, job.status, job.progress_percent, job.finished_at,
      job.file_count, job.error_message,
    ].join(':')).join('|');
  }

  function renderJobs(jobs, { force = false } = {}) {
    const signature = jobsSignature(jobs);
    if (!force && signature === lastJobsSignature) return;
    lastJobsSignature = signature;

    const activeJobs = jobs.filter((job) => ACTIVE_STATUSES.has(job.status));
    const historyJobs = jobs.filter((job) => !ACTIVE_STATUSES.has(job.status));
    const activeSection = document.getElementById('active-section');
    const activeList = document.getElementById('active-list');
    const historyList = document.getElementById('history-list');
    const historyFooter = document.getElementById('history-footer');

    activeSection.hidden = activeJobs.length === 0;
    document.getElementById('active-count').textContent = activeJobs.length ? `${activeJobs.length} items` : '';
    activeList.innerHTML = activeJobs.map(renderJob).join('');
    document.getElementById('history-count').textContent = historyJobs.length ? `${historyJobs.length} items` : '';
    historyList.innerHTML = historyJobs.length ? historyJobs.map(renderJob).join('') : emptyHistory();
    historyFooter.hidden = historyJobs.length === 0;
    window.feather?.replace();
    schedulePolling(activeJobs.length > 0);
  }

  async function refreshJobs({ force = false } = {}) {
    try {
      const data = await api('/api/download/jobs?limit=80');
      const jobs = data.jobs || [];
      renderJobs(jobs, { force });
    } catch (error) {
      notify(error.message, 'error');
      schedulePolling(false);
    }
  }

  function schedulePolling(hasActiveJobs) {
    if (pollTimer) window.clearTimeout(pollTimer);
    const delay = document.hidden ? 15000 : (hasActiveJobs ? 2200 : 12000);
    pollTimer = window.setTimeout(() => refreshJobs(), delay);
  }

  async function refreshSetup() {
    try {
      dependencyMeta = await api('/api/download/probe', { method: 'POST' });
    } catch (_) {}
  }

  function updateDetectedSite(input) {
    const value = input.value.trim();
    const status = document.getElementById('download-detected');
    status.classList.remove('text-error');
    if (!value) {
      status.textContent = '';
      return true;
    }
    try {
      const url = new URL(value);
      if (!['http:', 'https:'].includes(url.protocol)) throw new Error();
      status.textContent = `Recognized · ${safeHostname(value)}`;
      return true;
    } catch (_) {
      status.textContent = 'Enter a complete HTTP or HTTPS URL';
      status.classList.add('text-error');
      return false;
    }
  }

  function selectEngine(engine) {
    selectedEngine = engine === 'gallery-dl' ? 'gallery-dl' : 'yt-dlp';
    const switchElement = document.getElementById('media-switch');
    switchElement.dataset.value = selectedEngine;
    switchElement.querySelectorAll('[data-engine]').forEach((button) => {
      const active = button.dataset.engine === selectedEngine;
      button.setAttribute('aria-pressed', String(active));
      button.classList.toggle('btn-active', active);
    });
    const alert = document.getElementById('download-inline-alert');
    const unavailable = selectedEngine === 'gallery-dl' && !dependencyMeta.gallery_dl_available;
    alert.hidden = !unavailable;
    if (unavailable) document.getElementById('download-inline-alert-copy').textContent = 'The image download component is not ready';
  }

  function confirmClear({ title = 'Clear download history?', copy = 'Local media files will be kept.' } = {}) {
    const dialog = document.getElementById('download-confirm');
    document.getElementById('download-confirm-title').textContent = title;
    document.getElementById('download-confirm-copy').textContent = copy;
    const cancel = dialog.querySelector('[data-confirm-cancel]');
    const accept = dialog.querySelector('[data-confirm-accept]');

    return new Promise((resolve) => {
      const finish = (result) => {
        cancel.removeEventListener('click', onCancel);
        accept.removeEventListener('click', onAccept);
        dialog.removeEventListener('close', onClose);
        if (dialog.open) dialog.close();
        resolve(result);
      };
      const onCancel = () => finish(false);
      const onAccept = () => finish(true);
      // Covers Escape and the backdrop, both handled by the browser.
      const onClose = () => finish(false);
      cancel.addEventListener('click', onCancel);
      accept.addEventListener('click', onAccept);
      dialog.addEventListener('close', onClose);
      dialog.showModal();
      cancel.focus();
    });
  }

  async function handleJobAction(button) {
    const action = button.dataset.action;
    const jobId = button.dataset.jobId;
    if (!action || !jobId) return;
    // A daisyUI dropdown stays open while it holds focus.
    document.activeElement?.blur();
    if (action === 'delete' && !await confirmClear()) return;
    button.disabled = true;
    try {
      if (action === 'cancel') await api(`/api/download/jobs/${jobId}/cancel`, { method: 'POST' });
      if (action === 'retry') {
        await api(`/api/download/jobs/${jobId}/retry`, { method: 'POST' });
        notify('Retry submitted');
      }
      if (action === 'delete') await api(`/api/download/jobs/${jobId}`, { method: 'DELETE' });
      lastJobsSignature = '';
      await refreshJobs({ force: true });
    } catch (error) {
      notify(error.message, 'error');
      button.disabled = false;
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const form = document.getElementById('download-form');
    const urlInput = document.getElementById('download-url');
    const submitButton = document.getElementById('download-submit');
    urlInput?.addEventListener('input', () => {
      updateDetectedSite(urlInput);
    });
    document.getElementById('media-switch')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-engine]');
      if (button) selectEngine(button.dataset.engine);
    });

    form?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const url = urlInput.value.trim();
      if (!url) return;
      if (!updateDetectedSite(urlInput)) return;
      if (selectedEngine === 'gallery-dl' && !dependencyMeta.gallery_dl_available) {
        notify('The image download component is not installed.', 'error');
        return;
      }
      submitButton.disabled = true;
      submitButton.textContent = 'Adding…';
      try {
        const payload = { url, save_mode: 'root', engine: selectedEngine, cookie_mode: 'auto' };
        await api('/api/download/jobs', { method: 'POST', body: JSON.stringify(payload) });
        urlInput.value = '';
        updateDetectedSite(urlInput);
        notify('Added to the download queue');
        lastJobsSignature = '';
        await refreshJobs({ force: true });
      } catch (error) {
        notify(error.message, 'error');
      } finally {
        submitButton.disabled = false;
        submitButton.textContent = 'Download';
        urlInput.focus();
      }
    });

    document.getElementById('download-stack')?.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-action]');
      if (button) handleJobAction(button);
    });
    document.getElementById('clear-history-btn')?.addEventListener('click', async () => {
      if (!await confirmClear({ title: 'Clear all download history?', copy: 'Active jobs and local media files will be kept.' })) return;
      try {
        const data = await api('/api/download/jobs/clear', { method: 'POST' });
        notify(`Cleared ${data.deleted || 0} records`);
        lastJobsSignature = '';
        await refreshJobs({ force: true });
      } catch (error) {
        notify(error.message, 'error');
      }
    });

    document.addEventListener('visibilitychange', () => schedulePolling(
      !document.getElementById('active-section').hidden,
    ));

    await Promise.all([refreshSetup(), refreshJobs({ force: true })]);
    selectEngine(selectedEngine);
    urlInput?.focus({ preventScroll: true });
  });
})();
