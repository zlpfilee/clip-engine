/**
 * ClipEngine — Dashboard Frontend Logic
 */

const API = '';

// ─── State ───────────────────────────────────────────────────────────────
let state = {
  selectedSource: null,
  selectedChannel: 'anime',
  clips: [],
  selectedClips: new Set(),
  currentFilter: 'all',
  // Yeni: Çoklu klip tanımlama sistemi
  definedClips: [],
  nextClipId: 1,
};

// ─── Navigation ──────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', (e) => {
    e.preventDefault();
    const section = item.dataset.section;
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.getElementById(`section-${section}`).classList.add('active');
    if (section === 'dashboard') loadDashboard();
    if (section === 'library') loadLibrary();
    if (section === 'upload') loadReadyClips();
    if (section === 'create') loadSources();
  });
});

// ─── Dashboard ───────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const [statsRes, clipsRes] = await Promise.all([
      fetch(`${API}/api/stats`), fetch(`${API}/api/clips`)
    ]);
    const stats = await statsRes.json();
    const { clips } = await clipsRes.json();

    document.getElementById('statProcessed').textContent = stats.total_processed;
    document.getElementById('statUploaded').textContent = stats.total_uploaded;
    document.getElementById('statToday').textContent = stats.today_clips;
    document.getElementById('statReady').textContent = stats.ready_clips;

    const total = Math.max(stats.total_clips, 1);
    const bc = stats.by_channel;
    document.getElementById('barAnime').style.width = `${(bc.anime / total) * 100}%`;
    document.getElementById('barFilm').style.width = `${(bc.film / total) * 100}%`;
    document.getElementById('barDizi').style.width = `${(bc.dizi / total) * 100}%`;
    document.getElementById('countAnime').textContent = bc.anime;
    document.getElementById('countFilm').textContent = bc.film;
    document.getElementById('countDizi').textContent = bc.dizi;

    const recentList = document.getElementById('recentClipsList');
    if (clips.length === 0) {
      recentList.innerHTML = `<div class="empty-state"><span class="material-icons-round">video_library</span><p>Henüz klip işlenmedi</p></div>`;
    } else {
      recentList.innerHTML = clips.slice(-5).reverse().map(c => `
        <div class="clip-item" onclick="previewClip('${c.clip_id}')">
          <span class="clip-channel-tag ${c.channel}">${c.channel}</span>
          <span class="clip-title">${c.title}</span>
          <span class="clip-time">${formatDate(c.created_at)}</span>
        </div>
      `).join('');
    }
  } catch (err) {
    console.error('Dashboard yüklenemedi:', err);
  }
}

// ─── Sources ─────────────────────────────────────────────────────────────
async function loadSources() {
  const list = document.getElementById('sourceList');
  list.innerHTML = '<div class="loading-spinner"><span class="material-icons-round spin">autorenew</span></div>';

  try {
    const res = await fetch(`${API}/api/sources`);
    const { sources } = await res.json();

    if (sources.length === 0) {
      list.innerHTML = '<div class="empty-state"><p>Kaynak video yok. Yukarıdan yükleyin.</p></div>';
      return;
    }

    list.innerHTML = sources.map(s => {
      const isMp4 = s.filename.toLowerCase().endsWith('.mp4');
      return `
      <div class="source-item ${state.selectedSource === s.filename ? 'selected' : ''}" 
           onclick="selectSource('${s.filename}', this)">
        ${s.thumbnail 
            ? `<div class="source-thumb"><img src="${s.thumbnail}" alt="Thumbnail" loading="lazy"></div>`
            : `<div class="source-thumb placeholder"><span class="material-icons-round">movie</span></div>`
        }
        <div class="source-info">
          <span class="source-name">${s.filename}</span>
          <span class="source-meta">${s.size_mb}MB${s.duration ? ' • ' + formatDuration(s.duration) : ''}</span>
        </div>
        ${isMp4 
            ? `<span class="source-preview-badge" onclick="event.stopPropagation(); previewSource('${s.filename}')"><span class="material-icons-round" style="font-size:13px">play_circle</span> Önizleme</span>` 
            : ''
        }
      </div>`;
    }).join('');
  } catch (err) {
    list.innerHTML = '<div class="empty-state"><p>Kaynak listesi yüklenemedi</p></div>';
  }
}

function selectSource(filename, el) {
  state.selectedSource = filename;
  document.querySelectorAll('.source-item').forEach(i => i.classList.remove('selected'));
  el.classList.add('selected');
  // updateProcessBtn(); (Omitted since it's handled by Wizard flow now)
  // Load into interactive video player (Step 2)
  if (window.loadSourceVideo) window.loadSourceVideo(filename);
  // Load thumbnail for region selector (Step 3)
  if (window.loadRegionFrame) window.loadRegionFrame(filename);
}

// ─── File Upload ─────────────────────────────────────────────────────────
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');

uploadZone.addEventListener('click', () => fileInput.click());
uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener('change', () => {
  if (fileInput.files.length) uploadFile(fileInput.files[0]);
});

async function uploadFile(file) {
  showToast(`"${file.name}" yükleniyor...`, 'info');
  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API}/api/upload-source`, { method: 'POST', body: formData });
    const data = await res.json();
    showToast(`"${data.filename}" yüklendi! (${data.size_mb}MB)`, 'success');
    loadSources();
    state.selectedSource = data.filename;
    // updateProcessBtn();
  } catch (err) {
    showToast('Yükleme hatası: ' + err.message, 'error');
  }
}

// ─── Universal Download Logic ────────────────────────────────────────────────
document.querySelectorAll('.download-start-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
        const platform = btn.dataset.platform; // yt, kick, twitch
        let urlInput, qualityInput;
        
        if (platform === 'yt') {
            urlInput = document.getElementById('ytUrl');
            qualityInput = document.getElementById('ytQuality');
        } else if (platform === 'kick') {
            urlInput = document.getElementById('kickUrl');
            qualityInput = document.getElementById('kickQuality');
        } else if (platform === 'twitch') {
            urlInput = document.getElementById('twitchUrl');
            qualityInput = document.getElementById('twitchQuality');
        }

        const url = urlInput.value;
        const quality = qualityInput.value;
        const format = "mp4"; // Backend daima MP4 olarak indirir

        if (!url) {
            showToast("Lütfen URL'yi girin!", 'error');
            return;
        }

        const progressContainer = document.getElementById('dlProgressContainer');
        const dlProgressText = document.getElementById('dlProgressText');
        const dlPercentText = document.getElementById('dlPercentText');
        const dlProgressFill = document.getElementById('dlProgressFill');
        const dlSizeText = document.getElementById('dlSizeText');
        const dlSpeedText = document.getElementById('dlSpeedText');
        const dlEtaText = document.getElementById('dlEtaText');

        // Disable all download buttons during download
        document.querySelectorAll('.download-start-btn').forEach(b => b.disabled = true);
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="material-icons-round spin" style="font-size: 18px;">autorenew</span> Başlatılıyor...';
        
        // Reset UI
        progressContainer.style.display = 'block';
        dlProgressText.textContent = 'İndirme sırasına alınıyor...';
        dlPercentText.textContent = '%0';
        dlProgressFill.style.width = '0%';
        dlSizeText.textContent = '--';
        dlSpeedText.textContent = '--';
        dlEtaText.textContent = '--';

        try {
            const payload = { url, quality, format };
            
            const res = await fetch(`${API}/api/download/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'İndirme başlatılamadı');

            const { job_id } = data;
            const evtSource = new EventSource(`${API}/api/download/stream/${job_id}`);

            evtSource.onmessage = async (event) => {
                const jobData = JSON.parse(event.data);
                
                if (jobData.message) dlProgressText.textContent = jobData.message;
                if (jobData.percent !== undefined) {
                    dlProgressFill.style.width = `${jobData.percent}%`;
                    dlPercentText.textContent = `%${jobData.percent}`;
                }
                if (jobData.size) dlSizeText.textContent = jobData.size;
                if (jobData.speed) dlSpeedText.textContent = jobData.speed;
                if (jobData.eta) dlEtaText.textContent = jobData.eta;

                if (jobData.status === 'completed') {
                    evtSource.close();
                    showToast('Medya başarıyla indirildi!', 'success');
                    
                    document.querySelectorAll('.download-start-btn').forEach(b => b.disabled = false);
                    btn.innerHTML = originalText;
                    urlInput.value = '';
                    
                    await loadSources();
                    state.selectedSource = jobData.filename;
                    // updateProcessBtn();
                    
                    setTimeout(() => {
                        progressContainer.style.display = 'none';
                    }, 4000);
                } else if (jobData.status === 'error') {
                    evtSource.close();
                    document.querySelectorAll('.download-start-btn').forEach(b => b.disabled = false);
                    btn.innerHTML = originalText;
                    showToast(jobData.message || 'Bilinmeyen hata', 'error');
                    dlProgressText.textContent = 'Hata oluştu!';
                    dlProgressText.style.color = '#f44336';
                }
            };

            evtSource.onerror = () => {
                evtSource.close();
                document.querySelectorAll('.download-start-btn').forEach(b => b.disabled = false);
                btn.innerHTML = originalText;
            };
            
        } catch (err) {
            showToast('Hata: ' + err.message, 'error');
            dlProgressText.textContent = 'Hata: ' + err.message;
            document.querySelectorAll('.download-start-btn').forEach(b => b.disabled = false);
            btn.innerHTML = originalText;
        }
    });
});

// ─── Channel Selection ──────────────────────────────────────────────────
document.getElementById('processBtn')?.addEventListener('click', async () => {
  if (state.definedClips.length === 0) {
      showToast('İşlenecek klip yok!', 'error');
      return;
  }

  // Check if all clips have layout applied
  const allLayoutsDone = state.definedClips.every(c => c.layout_filename);
  if (!allLayoutsDone) {
      showToast('Önce tüm kliplere düzen uygulamalısınız (Adım 3)', 'error');
      return;
  }

  const btn = document.getElementById('processBtn');
  const originalBtnText = btn.innerHTML;
  const progress = document.getElementById('progressContainer');
  const progressFill = document.getElementById('progressFill');
  const progressText = document.getElementById('progressText');

  btn.disabled = true;
  progress.classList.remove('hidden');
  
  // 1. Gather all decoration layers from frontend state
  const text_layers = window.layerState ? window.layerState.textLayers.map(l => ({
      text: l.text,
      y_percent: l.y_percent,
      color: l.color,
      font_size: l.font_size || 48,
      duration: l.duration,
      start_time: l.duration === 'custom' ? l.start_time || null : null,
      end_time: l.duration === 'custom' ? l.end_time || null : null,
  })).filter(l => l.text.trim() !== '') : [];

  const image_layers = window.layerState ? window.layerState.imageLayers.map(l => ({
      filename: l.filename,
      y_percent: l.y_percent,
      scale: l.scale,
      opacity: l.opacity,
      dvd_bounce: l.dvd_bounce
  })) : [];

  const hashtags = document.getElementById('hashtagInput').value.split(/\s+/).filter(h => h.startsWith('#'));
  const checkedLangs = Array.from(document.querySelectorAll('input[name="subtitleLang"]:checked')).map(cb => cb.value);
  
  let successCount = 0;

  // 2. Loop through each defined clip and process sequentially
  for (let i = 0; i < state.definedClips.length; i++) {
      const clip = state.definedClips[i];
      progressFill.style.width = '10%';
      progressText.textContent = `[${i+1}/${state.definedClips.length}] "${clip.name}" işleniyor...`;

          const body = {
              source_filename: state.selectedSource,
              start_time: clip.start_time,
              end_time: clip.end_time,
              channel: state.selectedChannel,
              title: clip.name,
              description: document.getElementById('clipDescription')?.value || '',
              hook_text: document.getElementById('hookText')?.value || null,
              crop_mode: document.getElementById('cropMode').value,
              margin_v: parseInt(document.getElementById('subtitleMarginV').value) || 80,
              add_subtitles: false,
              subtitle_languages: ["en"],
              hashtags: hashtags,
              text_layers: text_layers,
              image_layers: image_layers,
              preview_layout_filename: clip.layout_filename,
              split_settings: null
          };

      try {
          // Start job for this clip
          const res = await fetch(`${API}/api/process`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
          });

          if (!res.ok) {
              const err = await res.json();
              let errMsg = 'İşleme hatası';
              if (err.detail) {
                  if (Array.isArray(err.detail)) {
                      errMsg = err.detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', ');
                  } else {
                      errMsg = err.detail;
                  }
              }
              throw new Error(errMsg);
          }

          const { job_id } = await res.json();
          
          // Wait for SSE stream to complete for this clip
          await new Promise((resolve, reject) => {
              const evtSource = new EventSource(`${API}/api/process/stream/${job_id}`);
              
              evtSource.onmessage = (event) => {
                  const data = JSON.parse(event.data);
                  
                  // İlerleme yüzdesini klibin kendi payı + genel ilerleme olarak hesapla
                  const basePct = (i / state.definedClips.length) * 100;
                  const clipPct = (data.progress || 5) / state.definedClips.length;
                  progressFill.style.width = Math.max(basePct + clipPct, 5) + '%';
                  
                  progressText.textContent = `[${i+1}/${state.definedClips.length}] ${clip.name}: ${data.step || 'İşleniyor...'}`;
                  
                  if (data.status === 'done') {
                      evtSource.close();
                      resolve();
                  } else if (data.status === 'error') {
                      evtSource.close();
                      reject(new Error(data.error || 'Bilinmeyen hata'));
                  }
              };

              evtSource.onerror = () => {
                  evtSource.close();
                  reject(new Error('SSE bağlantısı koptu'));
              };
          });
          
          successCount++;
          showToast(`"${clip.name}" başarıyla tamamlandı!`, 'success');
          
      } catch (err) {
          console.error(`Clip ${clip.name} failed:`, err);
          showToast(`Hata ("${clip.name}"): ${err.message}`, 'error');
      }
  }

  // All clips done
  progressFill.style.width = '100%';
  if (successCount === state.definedClips.length) {
      progressText.textContent = `✓ Tüm klipler tamamlandı! (${successCount} klip)`;
  } else {
      progressText.textContent = `⚠️ Tamamlandı (${successCount}/${state.definedClips.length} başarılı)`;
      progressFill.style.background = 'var(--accent-orange)';
  }

  setTimeout(() => {
      progress.classList.add('hidden');
      progressFill.style.width = '0%';
      progressFill.style.background = 'var(--primary)';
      btn.disabled = false;
      btn.innerHTML = originalBtnText;
      
      // Reset clips state
      state.definedClips = [];
      state.nextClipId = 1;
      if (window.renderClipCards) window.renderClipCards();
      
      // Form'u resetle
      document.getElementById('clipTitle').value = '';
      document.getElementById('clipDescription').value = '';
      document.getElementById('hookText').value = '';
      
      window.nextWizardStep(1); // En başa dön
  }, 4000);
});

// ─── Library ─────────────────────────────────────────────────────────────
async function loadLibrary() {
  const grid = document.getElementById('libraryGrid');
  try {
    const res = await fetch(`${API}/api/clips`);
    const { clips } = await res.json();
    state.clips = clips;
    renderLibrary();
  } catch (err) {
    grid.innerHTML = '<div class="empty-state"><p>Kütüphane yüklenemedi</p></div>';
  }
}

function renderLibrary() {
  const grid = document.getElementById('libraryGrid');
  let filtered = state.clips;
  if (state.currentFilter !== 'all') {
    filtered = filtered.filter(c => c.channel === state.currentFilter);
  }

  if (filtered.length === 0) {
    grid.innerHTML = `<div class="empty-state"><span class="material-icons-round">video_library</span><p>Henüz klip yok</p></div>`;
    return;
  }

  grid.innerHTML = filtered.map(c => `
    <div class="library-card">
      <div class="library-card-thumb" onclick="previewClip('${c.clip_id}')">
        <span class="material-icons-round">play_circle</span>
      </div>
      <div class="library-card-body">
        <h4>${c.title}</h4>
        <div class="library-card-meta">
          <span class="clip-channel-tag ${c.channel}">${c.channel}</span>
          <span class="clip-time">${formatDate(c.created_at)}</span>
        </div>
        <div class="library-card-actions">
          <button class="btn btn-outline" onclick="previewClip('${c.clip_id}')">
            <span class="material-icons-round" style="font-size:14px">visibility</span> Önizle
          </button>
          <button class="btn btn-danger" onclick="deleteClip('${c.clip_id}')">
            <span class="material-icons-round" style="font-size:14px">delete</span> Sil
          </button>
        </div>
      </div>
    </div>
  `).join('');
}

document.querySelectorAll('.filter-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    state.currentFilter = tab.dataset.filter;
    renderLibrary();
  });
});

// ─── Upload / Share ──────────────────────────────────────────────────────
async function loadReadyClips() {
  const list = document.getElementById('readyClipsList');
  try {
    const res = await fetch(`${API}/api/clips`);
    const { clips } = await res.json();
    const ready = clips.filter(c => c.status === 'ready');

    if (ready.length === 0) {
      list.innerHTML = '<div class="empty-state"><span class="material-icons-round">pending_actions</span><p>Paylaşıma hazır klip yok</p></div>';
      return;
    }

    list.innerHTML = ready.map(c => `
      <label class="ready-clip-item ${state.selectedClips.has(c.clip_id) ? 'selected' : ''}">
        <input type="checkbox" ${state.selectedClips.has(c.clip_id) ? 'checked' : ''} 
               onchange="toggleClipSelection('${c.clip_id}', this)">
        <span class="clip-channel-tag ${c.channel}">${c.channel}</span>
        <span class="clip-title">${c.title}</span>
        <span class="clip-time">${formatDate(c.created_at)}</span>
      </label>
    `).join('');

    updateUploadBtn();
  } catch (err) {
    list.innerHTML = '<div class="empty-state"><p>Yüklenemedi</p></div>';
  }
}

function toggleClipSelection(clipId, checkbox) {
  if (checkbox.checked) state.selectedClips.add(clipId);
  else state.selectedClips.delete(clipId);
  checkbox.closest('.ready-clip-item').classList.toggle('selected', checkbox.checked);
  updateUploadBtn();
}

function updateUploadBtn() {
  document.getElementById('uploadBtn').disabled = state.selectedClips.size === 0;
}

document.getElementById('uploadBtn').addEventListener('click', async () => {
  const platforms = [];
  if (document.getElementById('uploadYT').checked) platforms.push('youtube');
  if (document.getElementById('uploadTT').checked) platforms.push('tiktok');
  if (document.getElementById('uploadIG').checked) platforms.push('instagram');

  if (platforms.length === 0) {
    showToast('En az bir platform seçin', 'error');
    return;
  }

  for (const clipId of state.selectedClips) {
    const clip = state.clips.find(c => c.clip_id === clipId);
    if (!clip) continue;

    showToast(`"${clip.title}" yükleniyor...`, 'info');

    try {
      const res = await fetch(`${API}/api/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clip_id: clipId,
          platforms,
          title: clip.title,
          description: clip.description,
          hashtags: clip.hashtags,
        }),
      });

      const result = await res.json();
      const successes = Object.entries(result.results)
        .filter(([, v]) => !v.error).map(([k]) => k);
      const errors = Object.entries(result.results)
        .filter(([, v]) => v.error).map(([k, v]) => `${k}: ${v.error}`);

      if (successes.length) showToast(`${successes.join(', ')} başarılı!`, 'success');
      if (errors.length) showToast(errors.join('n'), 'error');
    } catch (err) {
      showToast('Upload hatası: ' + err.message, 'error');
    }
  }

  state.selectedClips.clear();
  loadReadyClips();
});

// ─── Preview Modal ───────────────────────────────────────────────────────
function previewClip(clipId) {
  const modal = document.getElementById('previewModal');
  const video = document.getElementById('previewVideo');
  video.pause();
  video.removeAttribute('src');
  video.load();
  modal.classList.remove('source-mode');
  video.src = `${API}/api/clips/${clipId}/preview`;
  modal.classList.remove('hidden');
}

function previewSource(filename) {
  const modal = document.getElementById('previewModal');
  const video = document.getElementById('previewVideo');
  video.pause();
  video.removeAttribute('src');
  video.load();
  modal.classList.add('source-mode');
  video.src = `${API}/api/sources/${encodeURIComponent(filename)}/stream`;
  modal.classList.remove('hidden');
}

document.getElementById('closeModal').addEventListener('click', () => {
  const modal = document.getElementById('previewModal');
  const video = document.getElementById('previewVideo');
  video.pause();
  modal.classList.add('hidden');
  modal.classList.remove('source-mode');
});

document.getElementById('previewModal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) {
    const video = document.getElementById('previewVideo');
    video.pause();
    if (video.src) {
        video.removeAttribute('src');
        video.load();
    }
    e.currentTarget.classList.add('hidden');
    e.currentTarget.classList.remove('source-mode');
  }
});

// ─── Delete Clip ─────────────────────────────────────────────────────────
async function deleteClip(clipId) {
  if (!confirm('Bu klibi silmek istediğinize emin misiniz?')) return;

  try {
    await fetch(`${API}/api/clips/${clipId}`, { method: 'DELETE' });
    showToast('Klip silindi', 'success');
    loadLibrary();
  } catch (err) {
    showToast('Silme hatası', 'error');
  }
}

// ─── Platform Status ─────────────────────────────────────────────────────
async function checkPlatformStatus() {
  try {
    const res = await fetch(`${API}/api/platforms/status`);
    const status = await res.json();

    const ytDot = document.getElementById('ytStatus');
    const ttDot = document.getElementById('ttStatus');
    const igDot = document.getElementById('igStatus');

    if (status.youtube?.authenticated) { ytDot.classList.add('connected'); document.getElementById('ytStatusText').textContent = status.youtube.channel_name || 'Bağlı'; }
    if (status.tiktok?.authenticated) { ttDot.classList.add('connected'); document.getElementById('ttStatusText').textContent = 'Bağlı'; }
    if (status.instagram?.authenticated) { igDot.classList.add('connected'); document.getElementById('igStatusText').textContent = 'Bağlı'; }
  } catch (err) {
    console.log('Platform durumu kontrol edilemedi');
  }
}

// ─── System Status ───────────────────────────────────────────────────────
async function checkSystemStatus() {
  try {
    const res = await fetch(`${API}/api/system/status`);
    const status = await res.json();
  } catch (err) {
    console.log('Sistem durumu kontrol edilemedi');
  }
}

// ─── Toast ───────────────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const icons = { success: 'check_circle', error: 'error', info: 'info' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span class="material-icons-round">${icons[type]}</span>${message}`;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 4000);
}

// ─── Helpers ─────────────────────────────────────────────────────────────
function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

// ─── Init ────────────────────────────────────────────────────────────────
document.getElementById('currentDate').textContent = new Date().toLocaleDateString('tr-TR', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
});

loadDashboard();
checkPlatformStatus();
checkSystemStatus();

// ─── WIZARD LOGIC ────────────────────────────────────────────────────────
window.currentWizardStep = 1;

window.nextWizardStep = function(step) {
    if (step > 1 && !state.selectedSource) {
        showToast('Lütfen önce bir kaynak video seçin.', 'error');
        return;
    }
    
    // Update Nav
    document.querySelectorAll('.wizard-step').forEach(el => {
        const s = parseInt(el.dataset.step);
        el.classList.toggle('active', s === step);
    });
    
    // Step 4'te 3 kolonlu yapı, Step 2 ve 1'de tek kolonlu (dev video) yapı
    const layoutContainer = document.querySelector('.create-layout');
    if (layoutContainer) {
        layoutContainer.classList.toggle('has-middle-col', step === 4);
    }
    
    // Update Panels
    document.querySelectorAll('.wizard-panel').forEach(el => {
        el.style.display = 'none';
        el.classList.remove('active');
    });
    const activePanel = document.getElementById(`wizard-step-${step}`);
    if(activePanel) {
        activePanel.style.display = 'block';
        activePanel.classList.add('active');
    }
    
    // Show/Hide Right Side Columns based on step
    const layerControls = document.getElementById('layerControlsCol');
    const phoneCol = document.querySelector('.create-phone-col');
    const previewCol = document.querySelector('.create-preview-col');
    const layoutContainer = document.querySelector('.create-layout');
    
    if (layoutContainer) {
        if (step === 1) {
            if(previewCol) previewCol.style.display = 'block';
            if(layerControls) layerControls.style.display = 'none';
            if(phoneCol) phoneCol.style.display = 'none';
            layoutContainer.style.gridTemplateColumns = 'minmax(0, 1fr) 340px';
        } else if (step === 2) {
            if(previewCol) previewCol.style.display = 'block';
            if(layerControls) layerControls.style.display = 'none';
            if(phoneCol) phoneCol.style.display = 'flex';
            layoutContainer.style.gridTemplateColumns = 'minmax(0, 1fr) 280px 340px';
            document.getElementById('draggableSubtitle').style.display = 'none';
        // Ensure source video is loaded in the interactive player
        if (state.selectedSource && window.loadSourceVideo) {
            const vid = document.getElementById('sourcePreviewVideo');
            if (vid && !vid.src) window.loadSourceVideo(state.selectedSource);
        }
        // Kamera bölgesi frame'ini yükle
        if (state.selectedSource && window.loadRegionFrame) {
            window.loadRegionFrame(state.selectedSource);
        }
        // Klip listesini güncelle
        if (window.renderClipCards) window.renderClipCards();
        } else if (step === 3) {
            if(previewCol) previewCol.style.display = 'block';
            if(layerControls) layerControls.style.display = 'none';
            if(phoneCol) phoneCol.style.display = 'flex';
            layoutContainer.style.gridTemplateColumns = 'minmax(0, 1fr) 280px 340px';
            document.getElementById('draggableSubtitle').style.display = 'none';
            // Layout klip seçicisini doldur
            if (window.populateLayoutClipSelect) window.populateLayoutClipSelect();
        } else if (step === 4) {
            if(previewCol) previewCol.style.display = 'none';
            if(layerControls) layerControls.style.display = 'flex';
            if(phoneCol) phoneCol.style.display = 'flex';
            // settingsCol (child 1) gets 1fr, controlsCol (child 2) gets 300px, phoneCol (child 3) gets 280px
            layoutContainer.style.gridTemplateColumns = 'minmax(0, 1fr) 300px 280px';
            
            // Enable Render button when reaching step 4
            const processBtn = document.getElementById('processBtn');
            if (processBtn) processBtn.disabled = false;
        }
    }
    
    window.currentWizardStep = step;
};

// Nav click events
document.querySelectorAll('.wizard-step').forEach(btn => {
    btn.addEventListener('click', () => {
        window.nextWizardStep(parseInt(btn.dataset.step));
    });
});

window.updateLayoutUI = function() {
    const mode = document.getElementById('cropMode').value;
    const splitSettings = document.getElementById('splitLayoutSettings');
    if (mode === 'split') {
        splitSettings.style.display = 'block';
    } else {
        splitSettings.style.display = 'none';
        
        // Temizle
        const existingCam = document.getElementById('previewCamOverlay');
        if (existingCam) existingCam.remove();
        const existingGame = document.getElementById('previewGameOverlay');
        if (existingGame) existingGame.remove();
        
        // Arkaplanı sıfırla
        const previewArea = document.querySelector('#phonePreview .preview-video-area');
        if (previewArea) previewArea.style.background = '';
    }
};


// ─── MULTI-CLIP MANAGEMENT (Step 2) ──────────────────────────────────────

// Telefon önizlemesinde video göster
function showPhonePreview(videoUrl) {
    const phoneVideo = document.getElementById('phonePreviewVideo');
    const phonePlaceholder = document.getElementById('previewVideoContent');
    if (phoneVideo) {
        if (phoneVideo.src) {
            phoneVideo.removeAttribute('src');
            phoneVideo.load();
        }
        phoneVideo.src = `${API}${videoUrl}`;
        phoneVideo.style.display = 'block';
        phoneVideo.load();
        phoneVideo.play().catch(e => console.log("Video autoplay blocked:", e));
        if (phonePlaceholder) phonePlaceholder.style.display = 'none';
    }
}

// Klip kartlarını render et
window.renderClipCards = function() {
    const container = document.getElementById('clipCardsList');
    const badge = document.getElementById('clipCountBadge');
    const step2NextBtn = document.getElementById('btnStep2Next');
    if (!container) return;
    
    badge.textContent = state.definedClips.length;
    step2NextBtn.disabled = state.definedClips.length === 0;
    
    if (state.definedClips.length === 0) {
        container.innerHTML = `
            <div id="emptyClipsText" style="text-align: center; color: var(--text-muted); font-size: 13px; padding: 20px 0;">
                <span class="material-icons-round" style="font-size: 32px; display: block; margin-bottom: 8px; opacity: 0.4;">movie_filter</span>
                Henüz klip tanımlanmadı. Yukarıdan süre seç ve "Kes ve Listeye Ekle" butonuna bas.
            </div>`;
        return;
    }
    
    container.innerHTML = state.definedClips.map(clip => {
        const statusIcon = clip.status === 'trimmed' ? 'check_circle' : clip.status === 'trimming' ? 'autorenew' : 'pending';
        const statusColor = clip.status === 'trimmed' ? 'var(--accent-green)' : clip.status === 'trimming' ? 'var(--accent-orange)' : 'var(--text-muted)';
        const statusText = clip.status === 'trimmed' ? 'Kesildi ✓' : clip.status === 'trimming' ? 'Kesiliyor...' : 'Bekliyor';
        const spinClass = clip.status === 'trimming' ? 'spin' : '';
        const camInfo = clip.camera_filename ? ' + Kamera ✓' : '';
        
        return `
            <div class="clip-card-item" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px; position: relative;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <strong style="font-size: 14px; color: var(--text-primary);">${clip.name}</strong>
                    <div style="display: flex; gap: 6px; align-items: center;">
                        <span class="material-icons-round ${spinClass}" style="font-size: 16px; color: ${statusColor};">${statusIcon}</span>
                        <span style="font-size: 12px; color: ${statusColor};">${statusText}${camInfo}</span>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 12px; color: var(--text-muted);">⏱️ ${clip.start_time} → ${clip.end_time}</span>
                    <div style="display: flex; gap: 6px;">
                        ${clip.trimmed_filename ? `<button class="btn btn-sm" onclick="showPhonePreview('/media/preview_temp/${clip.trimmed_filename}')" style="font-size: 11px; padding: 3px 8px;"><span class="material-icons-round" style="font-size:14px">play_circle</span> Oynat</button>` : ''}
                        <button class="btn btn-sm" onclick="removeClip(${clip.id})" style="font-size: 11px; padding: 3px 8px; background: rgba(239,68,68,0.15); color: var(--accent-red);"><span class="material-icons-round" style="font-size:14px">delete</span></button>
                    </div>
                </div>
            </div>`;
    }).join('');
};

// Klip sil
window.removeClip = function(id) {
    state.definedClips = state.definedClips.filter(c => c.id !== id);
    window.renderClipCards();
};

// "Kes ve Listeye Ekle" butonu
document.getElementById('btnAddClipToList')?.addEventListener('click', async () => {
    if (!state.selectedSource) {
        showToast('Önce bir kaynak video seçmelisin!', 'error');
        return;
    }
    
    const startTimeStr = document.getElementById('startTime').value;
    const endTimeStr = document.getElementById('endTime').value;
    const clipName = document.getElementById('activeClipName').value.trim() || `Klip ${state.nextClipId}`;
    
    const startTimeSec = window.parseTime ? window.parseTime(startTimeStr) : null;
    const endTimeSec = window.parseTime ? window.parseTime(endTimeStr) : null;
    
    if (startTimeSec === null || endTimeSec === null) {
        showToast('Başlangıç ve bitiş zamanını gir!', 'error');
        return;
    }
    
    const btn = document.getElementById('btnAddClipToList');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons-round spin">autorenew</span> Kesiliyor...';
    
    // Klip objesini oluştur
    const clip = {
        id: state.nextClipId++,
        name: clipName,
        start_time: startTimeSec,
        end_time: endTimeSec,
        trimmed_filename: null,
        camera_filename: null,
        layout_filename: null,
        status: 'trimming'
    };
    state.definedClips.push(clip);
    window.renderClipCards();
    
    try {
        // 1. Ana videoyu kes
        const res = await fetch(`${API}/api/preview/trim`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_filename: state.selectedSource,
                start_time: startTimeSec,
                end_time: endTimeSec
            })
        });
        
        if (!res.ok) {
            const errData = await res.json();
            let errMsg = 'Kesim başarısız.';
            if (errData.detail) {
                if (Array.isArray(errData.detail)) {
                    errMsg = errData.detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', ');
                } else {
                    errMsg = errData.detail;
                }
            }
            throw new Error(errMsg);
        }
        
        const data = await res.json();
        clip.trimmed_filename = data.filename;
        clip.status = 'trimmed';
        
        clip.status = 'trimmed';
        window.renderClipCards();
        
        // Telefonda kesilmiş klibi göster
        showPhonePreview(`/media/preview_temp/${clip.trimmed_filename}`);
        
        showToast(`"${clipName}" başarıyla kesildi!`, 'success');
        
        // Input'ları temizle (bir sonraki klip için)
        document.getElementById('startTime').value = '';
        document.getElementById('endTime').value = '';
        document.getElementById('activeClipName').value = '';
        
    } catch (err) {
        clip.status = 'error';
        window.renderClipCards();
        showToast(`Hata: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
});

// Step 2 → Step 3 geçiş butonu
document.getElementById('btnStep2Next')?.addEventListener('click', () => {
    if (state.definedClips.length === 0) {
        showToast('En az bir klip kesilmeli!', 'error');
        return;
    }
    window.nextWizardStep(3);
});

// ─── STEP 3: LAYOUT MANAGEMENT ──────────────────────────────────────────

// Layout klip seçicisini doldur
window.populateLayoutClipSelect = function() {
    const select = document.getElementById('layoutClipSelect');
    if (!select) return;
    
    select.innerHTML = '<option value="" disabled selected>Klip seçin...</option>';
    state.definedClips.filter(c => c.status === 'trimmed').forEach(clip => {
        const layoutDone = clip.layout_filename ? ' ✓' : '';
        const opt = document.createElement('option');
        opt.value = clip.id;
        opt.textContent = `${clip.name} (${clip.start_time} → ${clip.end_time})${layoutDone}`;
        select.appendChild(opt);
    });
    
    // Layout durumunu göster
    const statusList = document.getElementById('layoutStatusList');
    if (statusList) {
        statusList.innerHTML = state.definedClips.map(clip => {
            const done = !!clip.layout_filename;
            return `<div style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:rgba(255,255,255,0.03); border-radius:6px; border: 1px solid rgba(255,255,255,0.06);">
                <span style="font-size:13px;">${clip.name}</span>
                <span style="font-size:12px; color:${done ? 'var(--accent-green)' : 'var(--text-muted)'};">${done ? '✓' : '⏳'}</span>
            </div>`;
        }).join('');
    }
    
    // Dropdown değiştiğinde o klibin kesilmiş halini göster ve kamera seçim ekranına o frame'i al
    select.onchange = function() {
        const clipId = parseInt(select.value);
        const clip = state.definedClips.find(c => c.id === clipId);
        if (clip && clip.trimmed_filename) {
            showPhonePreview(`/media/preview_temp/${clip.trimmed_filename}`);
            
            const phoneVid = document.getElementById('phonePreviewVideo');
            const regionFrame = document.getElementById('regionSelectorFrame');
            const regionNoFrame = document.getElementById('regionNoFrame');
            
            const extractFrame = () => {
                if (!phoneVid || !regionFrame) return;
                try {
                    const canvas = document.createElement('canvas');
                    canvas.width = phoneVid.videoWidth;
                    canvas.height = phoneVid.videoHeight;
                    canvas.getContext('2d').drawImage(phoneVid, 0, 0, canvas.width, canvas.height);
                    regionFrame.src = canvas.toDataURL('image/jpeg');
                    regionFrame.style.display = 'block';
                    if (regionNoFrame) regionNoFrame.style.display = 'none';
                } catch(e) { console.error('Canvas frame grab error:', e); }
            };

            if (phoneVid) {
                if (phoneVid.readyState >= 2) {
                    // Try waiting another tick if it's ready but dimensions are somehow 0
                    setTimeout(extractFrame, 100); 
                } else {
                    phoneVid.addEventListener('loadeddata', extractFrame, { once: true });
                }
            }
        }
    };
    
    // Tüm klipler layout'lu ise ileri butonu aç
    const allDone = state.definedClips.every(c => c.layout_filename);
    const nextBtn = document.getElementById('btnNextFromLayout');
    if (nextBtn) nextBtn.disabled = !allDone;
};

// "Düzeni Uygula" butonu (Step 3)
document.getElementById('btnApplyLayout')?.addEventListener('click', async () => {
    const select = document.getElementById('layoutClipSelect');
    const clipId = parseInt(select?.value);
    const clip = state.definedClips.find(c => c.id === clipId);
    
    if (!clip || !clip.trimmed_filename) {
        showToast('Lütfen bir klip seçin!', 'error');
        return;
    }
    
    const btn = document.getElementById('btnApplyLayout');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons-round spin">autorenew</span> Düzenleniyor...';
    
    const mode = document.getElementById('cropMode').value;
    const payload = {
        trimmed_filename: clip.trimmed_filename,
        crop_mode: mode
    };
    
    if (mode === 'split') {
        payload.split_settings = {
            camX: parseInt(document.getElementById('camX').value) || 0,
            camY: parseInt(document.getElementById('camY').value) || 0,
            camW: parseInt(document.getElementById('camW').value) || 25,
            autoTracking: document.getElementById('autoTracking')?.checked || false,
            blackBg: document.getElementById('splitBlackBg')?.checked || false
        };
    }
    
    try {
        const res = await fetch(`${API}/api/preview/layout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || 'Düzen uygulanamadı.');
        }
        
        const data = await res.json();
        clip.layout_filename = data.filename;
        state.previewLayoutFilename = data.filename;
        
        showPhonePreview(data.url);
        showToast(`"${clip.name}" düzeni uygulandı!`, 'success');
        
        // Listeyi güncelle
        window.populateLayoutClipSelect();
        
    } catch (err) {
        showToast(`Hata: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
});

// Step 3 → Step 4
document.getElementById('btnNextFromLayout')?.addEventListener('click', () => {
    window.nextWizardStep(4);
});


// ─── INTERACTIVE SOURCE VIDEO PLAYER & TIMELINE (Step 2) ──────────────────
(function initSourceVideoPlayer() {
    const player = document.getElementById('sourceVideoPlayer');
    const video = document.getElementById('sourcePreviewVideo');
    const btnPlayPause = document.getElementById('btnPlayPause');
    const curTimeDisp = document.getElementById('currentTimeDisplay');
    const durDisp = document.getElementById('durationDisplay');
    const tlContainer = document.getElementById('timelineContainer');
    const tlBar = document.getElementById('timelineBar');
    const tlProgress = document.getElementById('timelineProgress');
    const tlScrubber = document.getElementById('timelineScrubber');
    const startMarker = document.getElementById('startMarker');
    const endMarker = document.getElementById('endMarker');
    const tlSelection = document.getElementById('timelineSelection');
    const btnMarkStart = document.getElementById('btnMarkStart');
    const btnMarkEnd = document.getElementById('btnMarkEnd');
    const startInput = document.getElementById('startTime');
    const endInput = document.getElementById('endTime');
    const btnPreviewCut = document.getElementById('btnPreviewOriginalCut');

    if (!player || !video) return;

    let isScrubbing = false;
    let mStart = null, mEnd = null; // marked seconds

    // ── Format helpers ──
    function fmtShort(s) {
        if (!isFinite(s) || s < 0) return '0:00';
        const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
        return h > 0 ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}` : `${m}:${String(sec).padStart(2,'0')}`;
    }
    function fmtFull(s) {
        if (!isFinite(s) || s < 0) return '00:00:00';
        const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
        return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
    }
    window.parseTime = function(str) {
        if (!str) return null;
        const p = str.replace(',','.').split(':').map(Number);
        if (p.some(isNaN)) return null;
        if (p.length === 3) return p[0]*3600 + p[1]*60 + p[2];
        if (p.length === 2) return p[0]*60 + p[1];
        return p[0] || null;
    };
    const parseTime = window.parseTime;

    // ── Load video ──
    window.loadSourceVideo = function(filename) {
        // Önceki bağlantıyı zorla kapat (tarayıcı bağlantı limitine takılmamak için)
        if (video.src) {
            video.removeAttribute('src');
            video.load();
        }
        const url = `${API}/api/sources/${encodeURIComponent(filename)}/stream`;
        video.src = url;
        video.load();
        player.style.display = 'block';
        mStart = null; mEnd = null;
        startMarker.style.display = 'none';
        endMarker.style.display = 'none';
        tlSelection.style.display = 'none';
        tlProgress.style.width = '0%';
        tlScrubber.style.left = '0%';
        curTimeDisp.textContent = '0:00';
        durDisp.textContent = '0:00';
        video.playbackRate = 1;
        document.querySelectorAll('.speed-btn').forEach(b => b.classList.toggle('active', b.dataset.speed === '1'));
    };

    // ── Play / Pause ──
    btnPlayPause.addEventListener('click', () => {
        if (video.paused || video.ended) video.play(); else video.pause();
    });
    video.addEventListener('click', () => {
        if (video.paused || video.ended) video.play(); else video.pause();
    });
    video.addEventListener('play', () => {
        btnPlayPause.querySelector('.material-icons-round').textContent = 'pause';
    });
    video.addEventListener('pause', () => {
        btnPlayPause.querySelector('.material-icons-round').textContent = 'play_arrow';
    });

    // ── Metadata ──
    video.addEventListener('loadedmetadata', () => {
        durDisp.textContent = fmtShort(video.duration);
        // Restore markers from existing input values
        const st = parseTime(startInput.value), et = parseTime(endInput.value);
        if (st !== null && video.duration) { mStart = st; startMarker.style.left = (st/video.duration*100)+'%'; startMarker.style.display = 'block'; }
        if (et !== null && video.duration) { mEnd = et; endMarker.style.left = (et/video.duration*100)+'%'; endMarker.style.display = 'block'; }
        updateSelection();
    });

    // ── Time update ──
    video.addEventListener('timeupdate', () => { if (!isScrubbing) updateTL(); });
    function updateTL() {
        if (!video.duration) return;
        const pct = (video.currentTime / video.duration) * 100;
        tlProgress.style.width = pct + '%';
        tlScrubber.style.left = pct + '%';
        curTimeDisp.textContent = fmtShort(video.currentTime);
    }

    // ── Timeline scrubbing ──
    function scrubTo(e) {
        const rect = tlBar.getBoundingClientRect();
        let pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        video.currentTime = pct * video.duration;
        tlProgress.style.width = (pct*100) + '%';
        tlScrubber.style.left = (pct*100) + '%';
        curTimeDisp.textContent = fmtShort(video.currentTime);
    }
    tlContainer.addEventListener('mousedown', (e) => {
        if (!video.duration) return;
        isScrubbing = true;
        tlScrubber.classList.add('dragging');
        video.pause();
        scrubTo(e);
    });
    document.addEventListener('mousemove', (e) => { if (isScrubbing) scrubTo(e); });
    document.addEventListener('mouseup', () => {
        if (isScrubbing) { isScrubbing = false; tlScrubber.classList.remove('dragging'); }
    });

    // ── Speed controls ──
    document.querySelectorAll('.speed-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            video.playbackRate = parseFloat(btn.dataset.speed);
            document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    // ── Mark Start / End ──
    function updateSelection() {
        if (mStart !== null && mEnd !== null && mEnd > mStart && video.duration) {
            const sp = (mStart/video.duration)*100, ep = (mEnd/video.duration)*100;
            tlSelection.style.left = sp + '%';
            tlSelection.style.width = (ep - sp) + '%';
            tlSelection.style.display = 'block';
        } else {
            tlSelection.style.display = 'none';
        }
    }

    btnMarkStart.addEventListener('click', () => {
        if (!video.duration) return;
        mStart = video.currentTime;
        startInput.value = fmtFull(mStart);
        startInput.dispatchEvent(new Event('input'));
        startMarker.style.left = (mStart/video.duration*100) + '%';
        startMarker.style.display = 'block';
        updateSelection();
        showToast(`Başlangıç: ${fmtFull(mStart)}`, 'success');
    });

    btnMarkEnd.addEventListener('click', () => {
        if (!video.duration) return;
        mEnd = video.currentTime;
        endInput.value = fmtFull(mEnd);
        endInput.dispatchEvent(new Event('input'));
        endMarker.style.left = (mEnd/video.duration*100) + '%';
        endMarker.style.display = 'block';
        updateSelection();
        showToast(`Bitiş: ${fmtFull(mEnd)}`, 'success');
    });

    // Sync markers when inputs change manually
    startInput.addEventListener('input', () => {
        const s = parseTime(startInput.value);
        if (s !== null && video.duration) {
            mStart = s; startMarker.style.left = (s/video.duration*100)+'%'; startMarker.style.display = 'block'; updateSelection();
        }
    });
    endInput.addEventListener('input', () => {
        const s = parseTime(endInput.value);
        if (s !== null && video.duration) {
            mEnd = s; endMarker.style.left = (s/video.duration*100)+'%'; endMarker.style.display = 'block'; updateSelection();
        }
    });

    // ── Preview cut button ──
    if (btnPreviewCut) {
        btnPreviewCut.addEventListener('click', () => {
            if (!video.duration) { showToast('Önce kaynak video seçin', 'error'); return; }
            const st = parseTime(startInput.value);
            if (st === null) { showToast('Başlangıç zamanı girilmedi', 'error'); return; }
            video.currentTime = st;
            video.play();
            showToast('Seçilen kısım oynatılıyor...', 'info');
            // Auto-pause at end time
            const et = parseTime(endInput.value);
            if (et !== null && et > st) {
                const checkEnd = () => {
                    if (video.currentTime >= et) { video.pause(); video.removeEventListener('timeupdate', checkEnd); }
                };
                video.addEventListener('timeupdate', checkEnd);
            }
        });
    }
})();

// ─── VISUAL CAMERA REGION SELECTOR (Step 3) ───────────────────────────────
(function initRegionSelector() {
    const regionSelector = document.getElementById('regionSelector');
    const regionFrame = document.getElementById('regionSelectorFrame');
    const regionNoFrame = document.getElementById('regionNoFrame');
    const selRect = document.getElementById('camSelectionRect');
    const btnReset = document.getElementById('btnResetRegion');
    const camX = document.getElementById('camX');
    const camY = document.getElementById('camY');
    const camW = document.getElementById('camW');

    if (!regionSelector) return;

    let isDrawing = false, drawStartX = 0, drawStartY = 0;

    // ── Load thumbnail (or exact video frame) ──
    window.loadRegionFrame = function(filename) {
        const vid = document.getElementById('sourcePreviewVideo');
        if (vid && vid.readyState >= 2) {
            try {
                const canvas = document.createElement('canvas');
                canvas.width = vid.videoWidth;
                canvas.height = vid.videoHeight;
                canvas.getContext('2d').drawImage(vid, 0, 0, canvas.width, canvas.height);
                regionFrame.onload = () => { regionFrame.style.display = 'block'; regionNoFrame.style.display = 'none'; };
                regionFrame.src = canvas.toDataURL('image/jpeg');
                return;
            } catch (e) { console.error('Canvas frame grab error:', e); }
        }
        // Fallback
        const thumb = `/media/sources/.thumbnails/${filename}.jpg`;
        regionFrame.onerror = () => { regionFrame.style.display = 'none'; regionNoFrame.style.display = 'flex'; };
        regionFrame.onload = () => { regionFrame.style.display = 'block'; regionNoFrame.style.display = 'none'; };
        regionFrame.src = thumb;
    };

    // ── Mouse drawing ──
    regionSelector.addEventListener('mousedown', (e) => {
        if (regionFrame.style.display === 'none') return;
        isDrawing = true;
        const rect = regionSelector.getBoundingClientRect();
        drawStartX = e.clientX - rect.left;
        drawStartY = e.clientY - rect.top;
        selRect.style.left = drawStartX + 'px';
        selRect.style.top = drawStartY + 'px';
        selRect.style.width = '0';
        selRect.style.height = '0';
        selRect.style.display = 'block';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDrawing) return;
        const rect = regionSelector.getBoundingClientRect();
        const curX = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
        const curY = Math.max(0, Math.min(e.clientY - rect.top, rect.height));
        selRect.style.left = Math.min(drawStartX, curX) + 'px';
        selRect.style.top = Math.min(drawStartY, curY) + 'px';
        selRect.style.width = Math.abs(curX - drawStartX) + 'px';
        selRect.style.height = Math.abs(curY - drawStartY) + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (!isDrawing) return;
        isDrawing = false;
        // Calculate percentages relative to the selector area
        const sRect = regionSelector.getBoundingClientRect();
        const cRect = selRect.getBoundingClientRect();
        const xPct = Math.round(((cRect.left - sRect.left) / sRect.width) * 100);
        const yPct = Math.round(((cRect.top - sRect.top) / sRect.height) * 100);
        const wPct = Math.round((cRect.width / sRect.width) * 100);
        if (wPct > 3) { // minimum threshold
            camX.value = Math.max(0, Math.min(100, xPct));
            camY.value = Math.max(0, Math.min(100, yPct));
            camW.value = Math.max(10, Math.min(100, wPct));
            showToast(`Kamera alanı seçildi: X=${xPct}% Y=${yPct}% W=${wPct}%`, 'success');
        }
    });

    // ── Reset ──
    btnReset.addEventListener('click', () => {
        selRect.style.display = 'none';
        camX.value = 0; camY.value = 0; camW.value = 25;
        showToast('Kamera seçimi sıfırlandı', 'info');
    });
})();

// ─── Preview Drag System & Text Overlay ──────────────────────────────
(function initPreviewSystem() {
  const phonePreview = document.getElementById('phonePreview');
  const subtitle = document.getElementById('draggableSubtitle');
  const textOverlay = document.getElementById('draggableTextOverlay');
  const marginVInput = document.getElementById('subtitleMarginV');
  const marginVDisplay = document.getElementById('marginVValue');
  const posLabel = document.getElementById('positionLabel');
  const textOverlayYInput = document.getElementById('textOverlayY');
  const textOverlayYDisplay = document.getElementById('textOverlayYValue');
  const cropSelect = document.getElementById('cropMode');
  const guideTop = document.getElementById('guideTop');
  const guideCenter = document.getElementById('guideCenter');
  const guideBottom = document.getElementById('guideBottom');

  // Text overlay controls
  const enableToggle = document.getElementById('enableTextOverlay');
  const overlayFields = document.getElementById('textOverlayFields');
  const overlayTextInput = document.getElementById('overlayTextInput');
  const overlayDurationSelect = document.getElementById('overlayDuration');
  const overlayCustomDuration = document.getElementById('overlayCustomDuration');
  const textOverlayContent = document.getElementById('textOverlayContent');

  if (!phonePreview || !subtitle) return;

  const REAL_HEIGHT = 1920;

  // ── Generic drag factory ──
  function makeDraggable(element, options) {
    let isDragging = false;
    let startY = 0;
    let startTop = 0;

    element.addEventListener('mousedown', (e) => {
      e.preventDefault();
      isDragging = true;
      startY = e.clientY;
      startTop = parseInt(element.style.top) || 0;
      element.classList.add('dragging');
      phonePreview.classList.add('dragging');
      document.body.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      e.preventDefault();
      const newTop = startTop + (e.clientY - startY);
      element.style.top = newTop + 'px';
      constrain(element, options);
    });

    document.addEventListener('mouseup', () => {
      if (!isDragging) return;
      isDragging = false;
      element.classList.remove('dragging');
      phonePreview.classList.remove('dragging');
      document.body.style.cursor = '';
    });

    // Touch support
    element.addEventListener('touchstart', (e) => {
      isDragging = true;
      startY = e.touches[0].clientY;
      startTop = parseInt(element.style.top) || 0;
      element.classList.add('dragging');
      phonePreview.classList.add('dragging');
    }, { passive: true });

    document.addEventListener('touchmove', (e) => {
      if (!isDragging) return;
      const newTop = startTop + (e.touches[0].clientY - startY);
      element.style.top = newTop + 'px';
      constrain(element, options);
    }, { passive: true });

    document.addEventListener('touchend', () => {
      if (!isDragging) return;
      isDragging = false;
      element.classList.remove('dragging');
      phonePreview.classList.remove('dragging');
    });
  }

  function constrain(element, options) {
    const previewH = phonePreview.offsetHeight;
    const elH = element.offsetHeight;
    let top = parseInt(element.style.top) || 0;

    const minTop = options.minPct ? previewH * options.minPct : 0;
    const maxTop = previewH - elH - 2;

    top = Math.max(minTop, Math.min(maxTop, top));
    element.style.top = top + 'px';

    if (options.onUpdate) options.onUpdate(top);
  }

  // ── Crop mode ──
  function updateCropMode() {
    phonePreview.setAttribute('data-crop', cropSelect.value);
    updateGuidePositions();
    constrain(subtitle, subtitleOpts);
    
    // Update all dynamic layers
    if (window.layerState && window.layerState.textLayers) {
      window.layerState.textLayers.forEach(layer => {
        const el = document.getElementById(`draggableTextOverlay_${layer.id}`);
        if (el) {
          constrain(el, {
            minPct: 0,
            onUpdate: (topPx) => {
              const elH = el.offsetHeight;
              const pct = Math.round(((topPx + elH / 2) / phonePreview.offsetHeight) * 100);
              layer.y_percent = pct;
              const disp = document.querySelector(`.layer-y-display[data-id="${layer.id}"]`);
              if (disp) disp.textContent = pct;
            }
          });
        }
      });
    }

    if (window.layerState && window.layerState.imageLayers) {
      window.layerState.imageLayers.forEach(layer => {
        const el = document.getElementById(`draggableImageOverlay_${layer.id}`);
        if (el) {
          constrain(el, {
            minPct: 0,
            onUpdate: (topPx) => {
              const elH = el.offsetHeight;
              const pct = Math.round(((topPx + elH / 2) / phonePreview.offsetHeight) * 100);
              layer.y_percent = pct;
              const disp = document.querySelector(`.image-layer-y-display[data-id="${layer.id}"]`);
              if (disp) disp.textContent = pct;
            }
          });
        }
      });
    }
  }

  function updateGuidePositions() {
    const previewH = phonePreview.offsetHeight;
    const mode = cropSelect.value;

    let videoTopPct, videoBottomPct;
    if (mode === 'crop') {
      videoTopPct = 0.05;
      videoBottomPct = 0.90;
    } else {
      videoTopPct = 0.265625;
      videoBottomPct = 0.734375;
    }

    guideTop.style.top = (previewH * videoTopPct) + 'px';
    guideCenter.style.top = (previewH * 0.5) + 'px';
    guideBottom.style.top = (previewH * videoBottomPct) + 'px';
  }

  cropSelect.addEventListener('change', updateCropMode);

  // ── Subtitle drag ──
  function updateSubtitleReadout(topPx) {
    const previewH = phonePreview.offsetHeight;
    const subtitleH = subtitle.offsetHeight;
    const mode = cropSelect.value;

    // Calculate MarginV: distance from bottom of screen to bottom of subtitle
    const bottomDist = previewH - topPx - subtitleH;
    const marginV = Math.round((bottomDist / previewH) * REAL_HEIGHT);
    const clamped = Math.max(0, Math.min(900, marginV));

    marginVInput.value = clamped;
    marginVDisplay.textContent = clamped;

    // Determine label based on position
    let videoTopPct, videoBottomPct;
    if (mode === 'crop') {
      videoTopPct = 0.05;
      videoBottomPct = 0.90;
    } else {
      videoTopPct = 0.265625;
      videoBottomPct = 0.734375;
    }

    const center = topPx + subtitleH / 2;
    const videoTopPx = previewH * videoTopPct;
    const videoBottomPx = previewH * videoBottomPct;

    if (center < videoTopPx) {
      posLabel.textContent = 'Üstte (Video Dışı)';
      posLabel.style.color = 'var(--accent-orange)';
    } else if (center > videoBottomPx) {
      posLabel.textContent = 'Altta (Video Dışı)';
      posLabel.style.color = 'var(--accent-blue)';
    } else {
      posLabel.textContent = 'İçinde (Videoda)';
      posLabel.style.color = 'var(--accent-green)';
    }
  }

  const subtitleOpts = {
    minPct: 0,
    onUpdate: updateSubtitleReadout
  };

  makeDraggable(subtitle, subtitleOpts);

  // ── Dynamic Layers System (Text & Image) ──
  window.layerState = {
    textLayers: [],
    imageLayers: [],
    nextId: 1,
    nextImgId: 1
  };

  const addTextLayerBtn = document.getElementById('addTextLayerBtn');
  const textLayersList = document.getElementById('textLayersList');
  const emptyLayersText = document.getElementById('emptyLayersText');
  const dynamicTextLayersContainer = document.getElementById('dynamicTextLayersContainer');

  addTextLayerBtn.addEventListener('click', () => {
    const layerId = window.layerState.nextId++;
    const layer = {
      id: layerId,
      text: 'Yeni Yazı',
      y_percent: 50,
      color: 'white',
      font_size: 48,
      duration: 'full',
      start_time: '',
      end_time: ''
    };
    window.layerState.textLayers.push(layer);
    renderLayers();
  });

  function renderLayers() {
    // Clear lists
    textLayersList.innerHTML = '';
    dynamicTextLayersContainer.innerHTML = '';

    if (window.layerState.textLayers.length === 0) {
      if (emptyLayersText) textLayersList.appendChild(emptyLayersText);
      return;
    }

    window.layerState.textLayers.forEach((layer, index) => {
      // 1. Render Settings Card
      const card = document.createElement('div');
      card.className = 'layer-card';
      card.style.cssText = 'background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 12px; position: relative;';
      
      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong style="font-size:12px; color:var(--text-secondary);">Katman ${index + 1}</strong>
            <button class="btn-icon layer-delete-btn" data-id="${layer.id}" style="color:var(--accent-red); background:none; border:none; cursor:pointer;"><span class="material-icons-round" style="font-size:16px;">delete</span></button>
        </div>
        <textarea class="input layer-text-input" data-id="${layer.id}" placeholder="Yazı içeriği..." style="padding:6px 10px; font-size:12px; margin-bottom:8px; min-height:60px; resize:vertical; font-family:inherit;">${layer.text}</textarea>
        
        <div style="display:flex; gap:8px; margin-bottom:8px;">
            <select class="input layer-color-select" data-id="${layer.id}" style="flex:1; padding:5px 8px; font-size:12px;">
                <option value="white" ${layer.color==='white'?'selected':''}>Beyaz</option>
                <option value="yellow" ${layer.color==='yellow'?'selected':''}>Sarı</option>
                <option value="red" ${layer.color==='red'?'selected':''}>Kırmızı</option>
                <option value="green" ${layer.color==='green'?'selected':''}>Yeşil</option>
                <option value="cyan" ${layer.color==='cyan'?'selected':''}>Turkuaz</option>
            </select>
            <select class="input layer-duration-select" data-id="${layer.id}" style="flex:1; padding:5px 8px; font-size:12px;">
                <option value="full" ${layer.duration==='full'?'selected':''}>Tüm Video</option>
                <option value="custom" ${layer.duration==='custom'?'selected':''}>Özel Süre</option>
            </select>
        </div>
        
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
            <label style="font-size:11px; color:var(--text-muted); white-space:nowrap;">Boyut</label>
            <input type="range" class="layer-fontsize-range" data-id="${layer.id}" min="16" max="96" step="2" value="${layer.font_size}" style="flex:1;">
            <span style="font-size:11px; font-weight:bold; min-width:28px; text-align:right;" class="layer-fontsize-val" data-id="${layer.id}">${layer.font_size}</span>
        </div>
        
        <div class="form-row layer-custom-time ${layer.duration==='custom'?'':'hidden'}" data-id="${layer.id}" style="gap:6px; margin-bottom:8px;">
            <div class="form-group" style="margin-bottom:0">
                <input type="text" class="input layer-start-input" data-id="${layer.id}" value="${layer.start_time}" placeholder="0:00" style="padding:5px 8px; font-size:12px;">
            </div>
            <div class="form-group" style="margin-bottom:0">
                <input type="text" class="input layer-end-input" data-id="${layer.id}" value="${layer.end_time}" placeholder="0:15" style="padding:5px 8px; font-size:12px;">
            </div>
        </div>
        
        <div class="readout-row" style="margin-top:6px; font-size:11px;">
            <span>Y Pozisyon:</span>
            <strong class="layer-y-display" data-id="${layer.id}">${layer.y_percent}</strong><span>%</span>
        </div>
      `;
      textLayersList.appendChild(card);

      // 2. Render Draggable Element on Phone
      const dragEl = document.createElement('div');
      dragEl.className = 'draggable-element draggable-text-overlay';
      dragEl.id = `draggableTextOverlay_${layer.id}`;
      // Önizleme font boyutu: 1080px -> phonePreview genişliğine ölçekle
      const phoneW = phonePreview.offsetWidth;
      const previewFontSize = Math.max(8, Math.round(layer.font_size * (phoneW / 1080)));
      dragEl.innerHTML = `
        <div class="drag-handle"><span class="material-icons-round">drag_indicator</span></div>
        <div class="text-overlay-content layer-content-display" data-id="${layer.id}" style="color:${layer.color}; font-size:${previewFontSize}px; white-space: pre-wrap; text-align: center;">${layer.text}</div>
      `;
      dynamicTextLayersContainer.appendChild(dragEl);

      // Set initial position based on y_percent (merkeze hizala)
      const previewH = phonePreview.offsetHeight;
      const elH = dragEl.offsetHeight;
      dragEl.style.top = Math.max(0, (previewH * layer.y_percent / 100) - elH / 2) + 'px';

      // Make draggable
      const opts = {
        minPct: 0,
        onUpdate: (topPx) => {
          const dragElH = dragEl.offsetHeight;
          const pct = Math.round(((topPx + dragElH / 2) / phonePreview.offsetHeight) * 100);
          layer.y_percent = pct;
          const disp = card.querySelector(`.layer-y-display[data-id="${layer.id}"]`);
          if (disp) disp.textContent = pct;
        }
      };
      makeDraggable(dragEl, opts);
    });

    // Attach Events
    attachLayerEvents();
  }

  function attachLayerEvents() {
    document.querySelectorAll('.layer-delete-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        window.layerState.textLayers = window.layerState.textLayers.filter(l => l.id !== id);
        renderLayers();
      });
    });

    document.querySelectorAll('.layer-text-input').forEach(input => {
      input.addEventListener('input', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        const layer = window.layerState.textLayers.find(l => l.id === id);
        if (layer) {
            layer.text = e.currentTarget.value;
            const display = document.querySelector(`.layer-content-display[data-id="${id}"]`);
            if (display) display.textContent = layer.text || '...';
        }
      });
    });

    document.querySelectorAll('.layer-color-select').forEach(select => {
      select.addEventListener('change', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        const layer = window.layerState.textLayers.find(l => l.id === id);
        if (layer) {
            layer.color = e.currentTarget.value;
            const display = document.querySelector(`.layer-content-display[data-id="${id}"]`);
            if (display) display.style.color = layer.color;
        }
      });
    });

    document.querySelectorAll('.layer-duration-select').forEach(select => {
      select.addEventListener('change', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        const layer = window.layerState.textLayers.find(l => l.id === id);
        if (layer) {
            layer.duration = e.currentTarget.value;
            const customTimeRow = document.querySelector(`.layer-custom-time[data-id="${id}"]`);
            if (customTimeRow) customTimeRow.classList.toggle('hidden', layer.duration !== 'custom');
        }
      });
    });

    document.querySelectorAll('.layer-start-input, .layer-end-input').forEach(input => {
      input.addEventListener('input', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        const layer = window.layerState.textLayers.find(l => l.id === id);
        if (layer) {
            if (e.currentTarget.classList.contains('layer-start-input')) layer.start_time = e.currentTarget.value;
            if (e.currentTarget.classList.contains('layer-end-input')) layer.end_time = e.currentTarget.value;
        }
      });
    });

    // Font boyutu slider
    document.querySelectorAll('.layer-fontsize-range').forEach(input => {
      input.addEventListener('input', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        const layer = window.layerState.textLayers.find(l => l.id === id);
        if (layer) {
            layer.font_size = parseInt(e.currentTarget.value);
            const valDisplay = document.querySelector(`.layer-fontsize-val[data-id="${id}"]`);
            if (valDisplay) valDisplay.textContent = layer.font_size;
            // Önizleme font boyutunu güncelle
            const display = document.querySelector(`.layer-content-display[data-id="${id}"]`);
            if (display) {
                const phoneW = phonePreview.offsetWidth;
                const previewFS = Math.max(8, Math.round(layer.font_size * (phoneW / 1080)));
                display.style.fontSize = previewFS + 'px';
            }
        }
      });
    });
  }

  // ── Dynamic Image Layers System ──
  const addImageLayerBtn = document.getElementById('addImageLayerBtn');
  const uploadAssetInput = document.getElementById('uploadAssetInput');
  const imageLayersList = document.getElementById('imageLayersList');
  const emptyImageLayersText = document.getElementById('emptyImageLayersText');
  const dynamicImageLayersContainer = document.getElementById('dynamicImageLayersContainer');

  addImageLayerBtn.addEventListener('click', () => {
    uploadAssetInput.click();
  });

  uploadAssetInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const btn = document.getElementById('addImageLayerBtn');
      btn.textContent = "Yükleniyor...";
      btn.disabled = true;

      const res = await fetch('/api/upload-asset', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.success) {
        const layerId = window.layerState.nextImgId++;
        const layer = {
          id: layerId,
          filename: data.filename,
          url: `/media/assets/${data.filename}`,
          y_percent: 50,
          scale: 0.5,
          opacity: 1.0,
          dvd_bounce: false
        };
        window.layerState.imageLayers.push(layer);
        renderImageLayers();
        showToast('Görsel yüklendi', 'success');
      } else {
        showToast('Görsel yüklenemedi', 'error');
      }
    } catch (err) {
      showToast('Yükleme hatası', 'error');
    } finally {
      const btn = document.getElementById('addImageLayerBtn');
      btn.textContent = "+ Ekle";
      btn.disabled = false;
      uploadAssetInput.value = "";
    }
  });

  function renderImageLayers() {
    imageLayersList.innerHTML = '';
    dynamicImageLayersContainer.innerHTML = '';

    if (window.layerState.imageLayers.length === 0) {
      if (emptyImageLayersText) imageLayersList.appendChild(emptyImageLayersText);
      return;
    }

    window.layerState.imageLayers.forEach((layer, index) => {
      // 1. Render Settings Card
      const card = document.createElement('div');
      card.className = 'layer-card';
      card.style.cssText = 'background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 12px; position: relative;';
      
      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong style="font-size:12px; color:var(--text-secondary);">Görsel ${index + 1}</strong>
            <button class="btn-icon img-layer-delete-btn" data-id="${layer.id}" style="color:var(--accent-red); background:none; border:none; cursor:pointer;"><span class="material-icons-round" style="font-size:16px;">delete</span></button>
        </div>
        
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
            <img src="${layer.url}" style="width:40px; height:40px; object-fit:contain; border-radius:4px; background:rgba(0,0,0,0.2);">
            <div style="flex:1;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <label style="font-size:11px; color:var(--text-muted);">Ölçek (Scale)</label>
                    <span style="font-size:11px; font-weight:bold;" class="img-scale-val" data-id="${layer.id}">${layer.scale.toFixed(1)}</span>
                </div>
                <input type="range" class="img-scale-range" data-id="${layer.id}" min="0.1" max="2.0" step="0.1" value="${layer.scale}" style="width:100%;">
            </div>
        </div>

        <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
            <div style="flex:1;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <label style="font-size:11px; color:var(--text-muted);">Saydamlık (Opacity)</label>
                    <span style="font-size:11px; font-weight:bold;" class="img-opacity-val" data-id="${layer.id}">${layer.opacity.toFixed(1)}</span>
                </div>
                <input type="range" class="img-opacity-range" data-id="${layer.id}" min="0.1" max="1.0" step="0.1" value="${layer.opacity}" style="width:100%;">
            </div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <label style="font-size:12px;">Hareket: <span class="dvd-mode-label" data-id="${layer.id}" style="font-weight:700; color:${layer.dvd_bounce ? 'var(--accent-orange)' : 'var(--accent-green)'}">${layer.dvd_bounce ? 'DVD Bounce' : 'Sabit'}</span></label>
            <label class="mini-toggle">
                <input type="checkbox" class="img-dvd-toggle" data-id="${layer.id}" ${layer.dvd_bounce ? 'checked' : ''}>
                <span class="mini-toggle-track"></span>
            </label>
        </div>
        
        <div class="readout-row" style="margin-top:6px; font-size:11px;">
            <span>Y Pozisyon:</span>
            <strong class="image-layer-y-display" data-id="${layer.id}">${layer.y_percent}</strong><span>%</span>
        </div>
      `;
      imageLayersList.appendChild(card);

      // 2. Render Draggable Element on Phone
      const dragEl = document.createElement('div');
      dragEl.className = 'draggable-element draggable-image-overlay';
      dragEl.id = `draggableImageOverlay_${layer.id}`;
      
      const bounceClass = layer.dvd_bounce ? 'dvd-bounce-preview' : '';
      
      // Görsel boyutu: scale * phone genişliğine oranla (backend'deki scale * 1080'e denk)
      const imgPhoneW = phonePreview.offsetWidth;
      const imgPreviewWidth = Math.round(layer.scale * imgPhoneW);
      
      dragEl.innerHTML = `
        <div class="drag-handle"><span class="material-icons-round">drag_indicator</span></div>
        <img src="${layer.url}" class="image-layer-content-display ${bounceClass}" data-id="${layer.id}" style="width:${imgPreviewWidth}px; opacity:${layer.opacity}; object-fit:contain; pointer-events:none;">
      `;
      dynamicImageLayersContainer.appendChild(dragEl);

      // Set initial position based on y_percent (merkeze hizala)
      const previewH = phonePreview.offsetHeight;
      const imgElH = dragEl.offsetHeight;
      dragEl.style.top = Math.max(0, (previewH * layer.y_percent / 100) - imgElH / 2) + 'px';

      // Make draggable
      const opts = {
        minPct: 0,
        onUpdate: (topPx) => {
          const imgDragElH = dragEl.offsetHeight;
          const pct = Math.round(((topPx + imgDragElH / 2) / phonePreview.offsetHeight) * 100);
          layer.y_percent = pct;
          const disp = card.querySelector(`.image-layer-y-display[data-id="${layer.id}"]`);
          if (disp) disp.textContent = pct;
        }
      };
      makeDraggable(dragEl, opts);
    });

    // Attach Events
    attachImageLayerEvents();
  }

  function attachImageLayerEvents() {
    document.querySelectorAll('.img-layer-delete-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        window.layerState.imageLayers = window.layerState.imageLayers.filter(l => l.id !== id);
        renderImageLayers();
      });
    });

    document.querySelectorAll('.img-scale-range').forEach(input => {
      input.addEventListener('input', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        const layer = window.layerState.imageLayers.find(l => l.id === id);
        if (layer) {
            layer.scale = parseFloat(e.currentTarget.value);
            document.querySelector(`.img-scale-val[data-id="${id}"]`).textContent = layer.scale.toFixed(1);
            const img = document.querySelector(`.image-layer-content-display[data-id="${id}"]`);
            // Video genişliğine oranla ölçekle (phone preview genişliği = 1080px temsili)
            if (img) img.style.width = Math.round(layer.scale * phonePreview.offsetWidth) + 'px';
        }
      });
    });

    document.querySelectorAll('.img-opacity-range').forEach(input => {
      input.addEventListener('input', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        const layer = window.layerState.imageLayers.find(l => l.id === id);
        if (layer) {
            layer.opacity = parseFloat(e.currentTarget.value);
            document.querySelector(`.img-opacity-val[data-id="${id}"]`).textContent = layer.opacity.toFixed(1);
            const img = document.querySelector(`.image-layer-content-display[data-id="${id}"]`);
            if (img) img.style.opacity = layer.opacity;
        }
      });
    });

    document.querySelectorAll('.img-dvd-toggle').forEach(input => {
      input.addEventListener('change', (e) => {
        const id = parseInt(e.currentTarget.dataset.id);
        const layer = window.layerState.imageLayers.find(l => l.id === id);
        if (layer) {
            layer.dvd_bounce = e.currentTarget.checked;
            const img = document.querySelector(`.image-layer-content-display[data-id="${id}"]`);
            if (img) img.classList.toggle('dvd-bounce-preview', layer.dvd_bounce);
            // Update mode label
            const label = document.querySelector(`.dvd-mode-label[data-id="${id}"]`);
            if (label) {
              label.textContent = layer.dvd_bounce ? 'DVD Bounce' : 'Sabit';
              label.style.color = layer.dvd_bounce ? 'var(--accent-orange)' : 'var(--accent-green)';
            }
        }
      });
    });
  }

  // ── Initialize ──
  function setInitialPosition() {
    const previewH = phonePreview.offsetHeight;
    const subtitleH = subtitle.offsetHeight;
    const bottomOffset = (80 / REAL_HEIGHT) * previewH;
    subtitle.style.top = (previewH - subtitleH - bottomOffset) + 'px';
    updateCropMode();
  }

  requestAnimationFrame(() => {
    requestAnimationFrame(setInitialPosition);
  });

  let resizeTimeout;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      updateGuidePositions();
      constrain(subtitle, subtitleOpts);
      
      if (window.layerState && window.layerState.textLayers) {
        window.layerState.textLayers.forEach(layer => {
          const el = document.getElementById(`draggableTextOverlay_${layer.id}`);
          if (el) {
            constrain(el, {
              minPct: 0,
              onUpdate: (topPx) => {
                const elH = el.offsetHeight;
                const pct = Math.round(((topPx + elH / 2) / phonePreview.offsetHeight) * 100);
                layer.y_percent = pct;
                const disp = document.querySelector(`.layer-y-display[data-id="${layer.id}"]`);
                if (disp) disp.textContent = pct;
              }
            });
          }
        });
      }
      if (window.layerState && window.layerState.imageLayers) {
        window.layerState.imageLayers.forEach(layer => {
          const el = document.getElementById(`draggableImageOverlay_${layer.id}`);
          if (el) {
            constrain(el, {
              minPct: 0,
              onUpdate: (topPx) => {
                const elH = el.offsetHeight;
                const pct = Math.round(((topPx + elH / 2) / phonePreview.offsetHeight) * 100);
                layer.y_percent = pct;
                const disp = document.querySelector(`.image-layer-y-display[data-id="${layer.id}"]`);
                if (disp) disp.textContent = pct;
              }
            });
          }
        });
      }
    }, 100);
  });
})();
window.adjustTime = function(inputId, secondsToAdd) {
    const input = document.getElementById(inputId);
    if (!input || !input.value) return;
    let currentSeconds = null;
    const p = input.value.replace(',', '.').split(':').map(Number);
    if (p.some(isNaN)) return;
    if (p.length === 3) currentSeconds = p[0] * 3600 + p[1] * 60 + p[2];
    else if (p.length === 2) currentSeconds = p[0] * 60 + p[1];
    else currentSeconds = p[0];
    if (currentSeconds === null) return;
    let newSeconds = Math.max(0, currentSeconds + secondsToAdd);
    const h = Math.floor(newSeconds / 3600);
    const m = Math.floor((newSeconds % 3600) / 60);
    const sec = Math.floor(newSeconds % 60);
    const ms = (newSeconds % 1).toFixed(1).substring(2);
    let formatted = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    if (ms !== '0') formatted += `.${ms}`;
    input.value = formatted;
    input.dispatchEvent(new Event('input'));
};
