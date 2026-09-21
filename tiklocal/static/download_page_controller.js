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
    toast.className = `download-toast ${type}`;
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
    const className = job.status === 'running' || job.status === 'queued'
      ? 'is-running'
      : (job.status === 'failed' ? 'is-failed' : '');
    const time = formatTime(job.finished_at || job.created_at);
    const sourceAction = `<a class="download-action" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer"><i data-feather="external-link"></i><span>Visit Source</span></a>`;
    const menu = !isActive ? `
      <div class="download-job-menu">
        <button class="download-icon-btn" type="button" data-action="menu" data-job-id="${escapeHtml(job.id)}" aria-label="More actions" aria-expanded="false"><i data-feather="more-horizontal"></i></button>
        <div class="download-job-menu-panel" hidden>
          <button class="download-menu-action" type="button" data-action="delete" data-job-id="${escapeHtml(job.id)}">Remove Record</button>
        </div>
      </div>` : '';

    let actions = '';
    if (isActive) {
      actions = `${sourceAction}<button class="download-action" type="button" data-action="cancel" data-job-id="${escapeHtml(job.id)}">Cancel</button>`;
    } else if (job.status === 'success' && firstFile) {
      actions = `
        <a class="download-action" href="${buildMediaHref(firstFile)}"><i data-feather="eye"></i><span>View Media</span></a>
        ${sourceAction}${menu}`;
    } else {
      actions = `
        ${(job.status === 'failed' || job.status === 'canceled') ? `<button class="download-action is-retry" type="button" data-action="retry" data-job-id="${escapeHtml(job.id)}"><i data-feather="rotate-ccw"></i><span>${job.failure_stage === 'index' ? 'Register Again' : 'Download Again'}</span></button>` : ''}
        ${sourceAction}${menu}`;
    }

    return `
      <article class="download-job ${className}" data-job-id="${escapeHtml(job.id)}">
        <div class="download-job-mark" aria-hidden="true">${escapeHtml(platformMark(job.url))}</div>
        <div class="download-job-main">
          <div class="download-job-top">
            <div class="download-job-identity"><span class="download-job-domain">${escapeHtml(safeHostname(job.url))}</span><span class="download-job-status">${escapeHtml(job.engine === 'gallery-dl' ? 'Images' : 'Video')}</span></div>
            ${time ? `<span class="download-job-time">${escapeHtml(time)}</span>` : ''}
          </div>
          <p class="download-job-copy">${escapeHtml(statusCopy(job))}</p>
          ${progress !== null && isActive ? `<div class="download-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress.toFixed(0)}"><div class="download-progress-bar" style="width:${progress.toFixed(1)}%"></div></div>` : ''}
          ${files.length > 1 ? `<div class="download-job-meta"><span>${files.length} items</span></div>` : ''}
          ${job.error_message ? `<p class="download-error">${escapeHtml(job.error_message)}</p>` : ''}
          <div class="download-job-actions">${actions}</div>
        </div>
      </article>`;
  }

  function emptyHistory() {
    return `
      <div class="download-empty">
        <div class="download-empty-icon"><i data-feather="download-cloud"></i></div>
        <div class="download-empty-title">No download history yet</div>
        <div class="download-empty-copy">Paste a link to add new media directly to your local library.</div>
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
    status.classList.remove('is-error');
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
      status.classList.add('is-error');
      return false;
    }
  }

  function selectEngine(engine) {
    selectedEngine = engine === 'gallery-dl' ? 'gallery-dl' : 'yt-dlp';
    const switchElement = document.getElementById('media-switch');
    switchElement.dataset.value = selectedEngine;
    switchElement.querySelectorAll('[data-engine]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.engine === selectedEngine));
    });
    const alert = document.getElementById('download-inline-alert');
    const unavailable = selectedEngine === 'gallery-dl' && !dependencyMeta.gallery_dl_available;
    alert.hidden = !unavailable;
    if (unavailable) document.getElementById('download-inline-alert-copy').textContent = 'The image download component is not ready';
  }

  function closeJobMenus(except = null) {
    document.querySelectorAll('.download-job-menu-panel').forEach((panel) => {
      if (panel === except) return;
      panel.hidden = true;
      panel.parentElement.querySelector('[data-action="menu"]')?.setAttribute('aria-expanded', 'false');
    });
  }

  function confirmClear({ title = 'Clear download history?', copy = 'Local media files will be kept.' } = {}) {
    const mask = document.getElementById('download-confirm');
    const titleElement = document.getElementById('download-confirm-title');
    const copyElement = document.getElementById('download-confirm-copy');
    titleElement.textContent = title;
    copyElement.textContent = copy;
    mask.hidden = false;
    document.body.style.overflow = 'hidden';
    const cancel = mask.querySelector('[data-confirm-cancel]');
    const accept = mask.querySelector('[data-confirm-accept]');
    cancel.focus();
    return new Promise((resolve) => {
      const finish = (result) => {
        mask.hidden = true;
        document.body.style.overflow = '';
        cancel.removeEventListener('click', onCancel);
        accept.removeEventListener('click', onAccept);
        mask.removeEventListener('click', onMaskClick);
        mask.removeEventListener('keydown', onKeydown);
        resolve(result);
      };
      const onCancel = () => finish(false);
      const onAccept = () => finish(true);
      const onMaskClick = (event) => { if (event.target === mask) finish(false); };
      const onKeydown = (event) => { if (event.key === 'Escape') finish(false); };
      cancel.addEventListener('click', onCancel);
      accept.addEventListener('click', onAccept);
      mask.addEventListener('click', onMaskClick);
      mask.addEventListener('keydown', onKeydown);
    });
  }

  async function handleJobAction(button) {
    const action = button.dataset.action;
    const jobId = button.dataset.jobId;
    if (!action || !jobId) return;
    if (action === 'menu') {
      const panel = button.parentElement.querySelector('.download-job-menu-panel');
      const willOpen = panel.hidden;
      closeJobMenus(panel);
      panel.hidden = !willOpen;
      button.setAttribute('aria-expanded', String(willOpen));
      return;
    }
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
        submitButton.textContent = 'Start Download';
        urlInput.focus();
      }
    });

    document.querySelector('.download-stack')?.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-action]');
      if (button) handleJobAction(button);
    });
    document.addEventListener('click', (event) => {
      if (!event.target.closest('.download-job-menu')) closeJobMenus();
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
