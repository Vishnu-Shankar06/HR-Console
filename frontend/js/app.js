// Application State
const AppState = {
  currentTab: "dashboard",
  resumes: [],
  jobs: [],
  selectedJobId: null,
  selectedResumeDocId: null,
  activeMatchResults: null,
  inactivityThreshold: parseInt(localStorage.getItem("talentpulse_inactivity_threshold") || "30", 10) || 30,
  highlightPending: false,
  notificationsSeen: false,
  uploadedResumes: [],
  improveUploadedResumes: [],
  selectedExistingMatchDocIds: new Set(),
  selectedExistingImproveDocIds: new Set(),
  candidateActionStates: {},
  previewList: [],
  previewIndex: 0,
  currentPreviewPages: [],
  currentPreviewPageIndex: 0,
  candidatePersonalDetails: {},
  matchScope: "uploaded",
  allFollowups: [],
  selectedDocIds: new Set(),
  appliedImprovements: {},
  isImprovedPreviewMode: false,
  compareList: [],
  compareIndex: 0
};

// Modern SVG Eye Icon (replaces emojis with clean password-revealer style vector icon)
const SVG_EYE_ICON = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; display:inline-block;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;

// Helper: strictly resolves only currently selected / uploaded candidate resumes for improvement
function getSelectedImprovementDocIds() {
  const selectedDocIds = new Set();
  (AppState.improveUploadedResumes || []).forEach(r => {
    if (r.doc_id) selectedDocIds.add(r.doc_id);
  });
  AppState.selectedExistingImproveDocIds.forEach(id => selectedDocIds.add(id));
  if (selectedDocIds.size === 0 && AppState.selectedResumeDocId) {
    selectedDocIds.add(AppState.selectedResumeDocId);
  }
  return Array.from(selectedDocIds);
}

// Helper: resolves only candidates whose improvements have been successfully applied and downloaded
function getAppliedImprovementsList() {
  const applied = AppState.appliedImprovements || {};
  const batch = AppState.currentImprovementBatchDocIds || [];
  const list = [];
  const addedIds = new Set();
  if (batch.length > 0) {
    batch.forEach(id => {
      if (applied[id] && !addedIds.has(id)) {
        list.push(applied[id]);
        addedIds.add(id);
      }
    });
  }
  Object.keys(applied).forEach(id => {
    if (applied[id] && !addedIds.has(id)) {
      list.push(applied[id]);
      addedIds.add(id);
    }
  });
  return list;
}

// Theme Management
function initTheme() {
  const saved = localStorage.getItem("talentpulse_theme");
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = saved || (prefersDark ? "dark" : "light");
  applyTheme(theme);
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const sunIcon = document.getElementById("theme-icon-sun");
  const moonIcon = document.getElementById("theme-icon-moon");
  if (sunIcon && moonIcon) {
    if (theme === "dark") {
      sunIcon.style.display = "block";
      moonIcon.style.display = "none";
    } else {
      sunIcon.style.display = "none";
      moonIcon.style.display = "block";
    }
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem("talentpulse_theme", next);
  applyTheme(next);
}

// UI Notification Helper
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Modal Helper
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add("active");
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove("active");
  if (modalId === "resume-preview-modal") {
    AppState.isImprovedPreviewMode = false;
    const tabsBar = document.getElementById("preview-improved-tabs-bar");
    if (tabsBar) {
      tabsBar.style.display = "none";
      tabsBar.innerHTML = "";
    }
  }
  if (modalId === "version-compare-modal") {
    const tabsBar = document.getElementById("compare-improved-tabs-bar");
    if (tabsBar) {
      tabsBar.style.display = "none";
      tabsBar.innerHTML = "";
    }
  }
}

// ==========================================
// RESUME PREVIEW & SIDE NAVIGATION (< and >)
// ==========================================
function downloadCurrentPreviewDocument() {
  let docId = null;
  let filename = null;
  let versionId = null;
  if (AppState.previewList && AppState.previewList[AppState.previewIndex]) {
    const item = AppState.previewList[AppState.previewIndex];
    docId = item.doc_id || item.docId;
    filename = item.original_filename || `${docId}.docx`;
    versionId = item.version_id || item.versionId || null;
  } else if (window._currentImprovementData && window._currentImprovementData.doc_id) {
    docId = window._currentImprovementData.doc_id;
    filename = `${docId}.docx`;
  }
  if (!docId && !versionId) {
    showToast("No active document to download.", "warning");
    return;
  }

  const downloadUrl = versionId ? `/api/versions/${encodeURIComponent(versionId)}/file` : `/api/resumes/${encodeURIComponent(docId)}/file`;
  const a = document.createElement("a");
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  showToast(`Downloading resume for candidate ${docId || versionId}...`, "info");
}

function downloadCandidateResume(docId) {
  if (!docId) {
    showToast("No candidate document ID provided.", "warning");
    return;
  }
  const item = (AppState.resumes || []).find(r => r.doc_id === docId);
  const filename = (item && item.original_filename) ? item.original_filename : `${docId}.docx`;
  const downloadUrl = `/api/resumes/${encodeURIComponent(docId)}/file`;
  const a = document.createElement("a");
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  showToast(`Downloading original resume for candidate ${docId}...`, "info");
}

function getMatchScopedPreviewList(includeDocId = null) {
  const scoped = [];
  // First include active match search results if available
  if (AppState.activeMatchResults?.results?.length) {
    AppState.activeMatchResults.results.forEach(r => {
      scoped.push({
        doc_id: r.doc_id,
        full_name: r.full_name || r.candidate_name || r.candidate_label || r.doc_id,
        original_filename: r.original_filename || `${r.doc_id}.docx`
      });
    });
  }
  (AppState.uploadedResumes || []).filter(r => r.doc_id).forEach(r => {
    if (!scoped.some(x => x.doc_id === r.doc_id)) {
      scoped.push({
        doc_id: r.doc_id,
        full_name: r.full_name || r.candidate_name || r.filename || r.doc_id,
        original_filename: r.filename || `${r.doc_id}.docx`
      });
    }
  });
  AppState.selectedExistingMatchDocIds.forEach(id => {
    if (!scoped.some(x => x.doc_id === id)) {
      const r = (AppState.resumes || []).find(x => x.doc_id === id);
      scoped.push({
        doc_id: id,
        full_name: r ? (r.full_name || r.candidate_name || r.pii?.name || r.original_filename || id) : id,
        original_filename: r ? r.original_filename : `${id}.docx`
      });
    }
  });
  if (includeDocId && !scoped.some(x => x.doc_id === includeDocId)) {
    const r = (AppState.resumes || []).find(x => x.doc_id === includeDocId);
    scoped.push({
      doc_id: includeDocId,
      full_name: r ? (r.full_name || r.candidate_name || r.pii?.name || r.original_filename || includeDocId) : includeDocId,
      original_filename: r ? r.original_filename : `${includeDocId}.docx`
    });
  }
  return scoped;
}

function getImproveScopedPreviewList(includeDocId = null) {
  const scoped = [];
  const activeDocIds = Object.keys(AppState.improvementAnalysesByDocId || {});
  if (activeDocIds.length) {
    activeDocIds.forEach(id => {
      const a = AppState.improvementAnalysesByDocId[id];
      const r = (AppState.resumes || []).find(x => x.doc_id === id);
      scoped.push({
        doc_id: id,
        full_name: a?.candidate_personal_details?.name || r?.full_name || r?.candidate_name || id,
        original_filename: r?.original_filename || `${id}.docx`
      });
    });
  }
  (AppState.improveUploadedResumes || []).filter(r => r.doc_id).forEach(r => {
    if (!scoped.some(x => x.doc_id === r.doc_id)) {
      scoped.push({
        doc_id: r.doc_id,
        full_name: r.full_name || r.candidate_name || r.filename || r.doc_id,
        original_filename: r.filename || `${r.doc_id}.docx`
      });
    }
  });
  AppState.selectedExistingImproveDocIds.forEach(id => {
    if (!scoped.some(x => x.doc_id === id)) {
      const r = (AppState.resumes || []).find(x => x.doc_id === id);
      scoped.push({
        doc_id: id,
        full_name: r ? (r.full_name || r.candidate_name || r.pii?.name || r.original_filename || id) : id,
        original_filename: r ? r.original_filename : `${id}.docx`
      });
    }
  });
  if (includeDocId && !scoped.some(x => x.doc_id === includeDocId)) {
    const r = (AppState.resumes || []).find(x => x.doc_id === includeDocId);
    scoped.push({
      doc_id: includeDocId,
      full_name: r ? (r.full_name || r.candidate_name || r.pii?.name || r.original_filename || includeDocId) : includeDocId,
      original_filename: r ? r.original_filename : `${includeDocId}.docx`
    });
  }
  return scoped;
}

function openResumePreview(docId, candidateList = null, versionId = null) {
  if (!docId && !versionId) return;

  AppState.isImprovedPreviewMode = false;
  const tabsBar = document.getElementById("preview-improved-tabs-bar");
  if (tabsBar) {
    tabsBar.style.display = "none";
    tabsBar.innerHTML = "";
  }

  if (versionId) {
    const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId);
    const pii = docId ? AppState.candidatePersonalDetails[docId] : null;
    const fallbackName = pii?.name || resumeObj?.full_name || resumeObj?.candidate_name || docId || versionId;
    AppState.previewList = [{
      doc_id: docId || versionId,
      version_id: versionId,
      full_name: `${fallbackName} (Improved Resume)`,
      original_filename: `${fallbackName}_Improved.docx`
    }];
    AppState.previewIndex = 0;
    renderResumePreviewAtIndex(0);
    openModal("resume-preview-modal");
    return;
  }

  // Build scoped candidate list based on current workflow context
  let list = candidateList;
  if (!list || !list.length) {
    if (AppState.currentTab === "matching") {
      list = getMatchResultsPreviewList() || getMatchScopedPreviewList(docId);
    } else if (AppState.currentTab === "improvement") {
      list = getImproveScopedPreviewList(docId);
    } else if (AppState.currentTab === "followups" && AppState.allFollowups?.length) {
      list = AppState.allFollowups.map(f => ({
        doc_id: f.doc_id,
        full_name: f.full_name || f.candidate_name || f.doc_id,
        original_filename: f.doc_id
      }));
    } else if (AppState.currentTab === "library" && AppState.resumes?.length) {
      list = AppState.resumes.map(r => ({
        doc_id: r.doc_id,
        full_name: r.full_name || r.candidate_name || r.pii?.name || r.original_filename || r.doc_id,
        original_filename: r.original_filename
      }));
    }
  }

  if (!list || !list.length) {
    const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId);
    list = [{
      doc_id: docId,
      full_name: resumeObj ? (resumeObj.full_name || resumeObj.candidate_name || resumeObj.original_filename) : docId,
      original_filename: resumeObj ? resumeObj.original_filename : docId
    }];
  }

  let idx = list.findIndex(item => (item.doc_id === docId || item.docId === docId));
  if (idx === -1) {
    const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId);
    const fallbackName = resumeObj ? (resumeObj.full_name || resumeObj.candidate_name || resumeObj.original_filename) : docId;
    AppState.previewList = [{ doc_id: docId, full_name: fallbackName, original_filename: resumeObj?.original_filename || docId }];
    idx = 0;
  } else {
    AppState.previewList = list;
  }

  AppState.previewIndex = idx;
  renderResumePreviewAtIndex(idx);
  openModal("resume-preview-modal");
}

function navigateResumePreview(direction) {
  const nextIdx = AppState.previewIndex + direction;
  if (nextIdx >= 0 && nextIdx < AppState.previewList.length) {
    AppState.previewIndex = nextIdx;
    renderResumePreviewAtIndex(nextIdx);
    if (AppState.isImprovedPreviewMode) {
      renderImprovedTabsBar(nextIdx);
    }
  }
}

async function renderResumePreviewAtIndex(idx) {
  if (!AppState.previewList || !AppState.previewList[idx]) return;
  const item = AppState.previewList[idx];
  const docId = item.doc_id || item.docId;
  const versionId = item.version_id || item.versionId || null;
  const name = item.full_name || item.candidate_name || item.candidate_label || item.filename || docId;

  const nameEl = document.getElementById("preview-modal-candidate-name");
  const tagEl = document.getElementById("preview-modal-doc-tag");
  const counterEl = document.getElementById("preview-modal-counter");
  const prevBtn = document.getElementById("preview-btn-prev");
  const nextBtn = document.getElementById("preview-btn-next");
  const pageControls = document.getElementById("preview-doc-page-controls");
  const pageCounter = document.getElementById("preview-page-counter");
  const pagePrev = document.getElementById("preview-page-prev");
  const pageNext = document.getElementById("preview-page-next");
  const paperSheet = document.getElementById("preview-paper-sheet");
  const inappContainer = document.getElementById("preview-inapp-container");
  const frame = document.getElementById("preview-modal-frame");

  if (nameEl) nameEl.textContent = name;
  if (AppState.isImprovedPreviewMode) {
    if (counterEl) counterEl.textContent = `${item.view_label || ('View ' + (idx + 1))} of ${AppState.previewList.length}`;
    if (tagEl) tagEl.textContent = `${item.filename || item.original_filename || docId} • Improved`;
    renderImprovedTabsBar(idx);
  } else {
    if (tagEl) tagEl.textContent = versionId ? `Version: ${versionId}` : `ID: ${docId}`;
    if (counterEl) counterEl.textContent = `Candidate ${idx + 1} of ${AppState.previewList.length}`;
  }

  if (prevBtn) prevBtn.disabled = (idx <= 0);
  if (nextBtn) nextBtn.disabled = (idx >= AppState.previewList.length - 1);

  if (inappContainer) inappContainer.style.display = "block";
  if (frame) frame.style.display = "none";
  if (pageControls) pageControls.style.display = "none";

  if (paperSheet) {
    paperSheet.innerHTML = `
      <div style="text-align:center; padding:3rem 1rem; color:var(--text-muted);">
        <div class="spinner" style="margin:0 auto 1rem;"></div>
        <div>Loading authentic resume document...</div>
      </div>
    `;
  }

  if (docId) {
    API.recordResumeOpened(docId).catch(() => {});
  }

  AppState.currentPreviewPages = [];
  AppState.currentPreviewPageIndex = 0;

  try {
    const previewData = versionId ? await API.getVersionPreview(versionId) : await API.getResumePreview(docId);
    const isPdf = (previewData?.is_pdf === true) && !!(previewData?.pdf_stream_url);
    const isDocx = (previewData?.is_docx === true) ||
                   (previewData?.filename && previewData.filename.toLowerCase().endsWith(".docx")) ||
                   (previewData?.mime_type && previewData.mime_type.includes("wordprocessingml"));

    if (isPdf && frame) {
      // Display the actual PDF file natively without any synthetic alterations
      if (inappContainer) inappContainer.style.display = "none";
      frame.style.display = "block";
      frame.src = previewData.pdf_stream_url;
      if (pageControls) pageControls.style.display = "none";
      const contentBox = document.getElementById("preview-content-box");
      if (contentBox) contentBox.scrollTop = 0;
      return;
    }

    if (isDocx && window.docx && paperSheet) {
      try {
        if (frame) frame.style.display = "none";
        if (inappContainer) inappContainer.style.display = "block";
        if (pageControls) pageControls.style.display = "none";

        const fileUrl = previewData.docx_stream_url || previewData.stream_url || (versionId ? `/api/versions/${encodeURIComponent(versionId)}/file` : `/api/resumes/${encodeURIComponent(docId)}/stream`);
        const resp = await fetch(fileUrl);
        if (!resp.ok) throw new Error(`HTTP ${resp.status} loading original Word document`);
        const arrayBuffer = await resp.arrayBuffer();

        paperSheet.innerHTML = "";
        await window.docx.renderAsync(arrayBuffer, paperSheet, null, {
          className: "docx",
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          breakPages: true,
          useBase64URL: true
        });

        // Query both .docx-wrapper > section.docx and .docx-viewer-wrapper > section.docx-viewer or section.docx
        const pageSections = paperSheet.querySelectorAll(".docx-wrapper > section.docx, .docx-viewer-wrapper > section.docx-viewer, section.docx, section.docx-viewer");
        if (pageSections.length > 1) {
          AppState.currentDocxPagesCount = pageSections.length;
          AppState.currentDocxPageIndex = 0;

          pageSections.forEach((sec, sIdx) => {
            sec.setAttribute("data-page-index", sIdx);
            sec.id = `preview-docx-page-${sIdx}`;
            if (sIdx < pageSections.length - 1) {
              const cutDiv = document.createElement("div");
              cutDiv.className = "docx-page-cut-divider";
              cutDiv.innerHTML = `
                <div class="page-cut-line"></div>
                <div class="page-cut-badge">
                  <span class="page-cut-scissors">✂</span>
                  <span class="page-cut-text">PAGE CUT &bull; NEXT PAGE (${sIdx + 2})</span>
                </div>
                <div class="page-cut-line"></div>
              `;
              sec.after(cutDiv);
            }
          });

          if (pageControls) pageControls.style.display = "flex";
          if (pageCounter) pageCounter.textContent = `Page 1 of ${pageSections.length}`;
          if (pagePrev) {
            pagePrev.disabled = true;
            pagePrev.style.display = "inline-flex";
          }
          if (pageNext) {
            pageNext.disabled = false;
            pageNext.style.display = "inline-flex";
          }

          if (inappContainer) {
            inappContainer.onscroll = () => {
              const containerTop = inappContainer.scrollTop + 120;
              let currentSec = 0;
              pageSections.forEach((sec, sIdx) => {
                if (sec.offsetTop <= containerTop) {
                  currentSec = sIdx;
                }
              });
              if (currentSec !== AppState.currentDocxPageIndex) {
                AppState.currentDocxPageIndex = currentSec;
                if (pageCounter) pageCounter.textContent = `Page ${currentSec + 1} of ${pageSections.length}`;
                if (pagePrev) pagePrev.disabled = (currentSec <= 0);
                if (pageNext) pageNext.disabled = (currentSec >= pageSections.length - 1);
              }
            };
          }
        } else {
          AppState.currentDocxPagesCount = 1;
          AppState.currentDocxPageIndex = 0;
          if (pageControls) pageControls.style.display = "none";
        }

        if (inappContainer) inappContainer.scrollTop = 0;
        const contentBox = document.getElementById("preview-content-box");
        if (contentBox) contentBox.scrollTop = 0;
        return;
      } catch (docxErr) {
        console.warn("Native DOCX rendering failed, falling back to server-rendered pages:", docxErr);
      }
    }

    // Fallback for text resumes
    if (frame) frame.style.display = "none";
    if (inappContainer) inappContainer.style.display = "block";

    if (previewData && previewData.success && previewData.pages && previewData.pages.length > 0) {
      AppState.currentDocxPagesCount = 0;
      AppState.currentPreviewPages = previewData.pages;
      AppState.currentPreviewPageIndex = 0;

      renderDocumentPage(0);

      if (pageControls) {
        pageControls.style.display = "flex";
        const total = Math.max(1, previewData.total_pages || AppState.currentPreviewPages.length || 1);
        if (pageCounter) pageCounter.textContent = `Page 1 of ${total}`;
        if (pagePrev) pagePrev.disabled = true;
        if (pageNext) pageNext.disabled = (total <= 1);
      }
    } else {
      if (paperSheet) {
        paperSheet.innerHTML = `
          <div style="padding:2.5rem 1.5rem; text-align:center; color:var(--text-muted);">
            <div style="font-weight:600; margin-bottom:0.25rem;">Resume document preview unavailable</div>
            <div style="font-size:0.8rem; color:var(--text-dim);">${escapeHtml(previewData?.error || "Document content could not be displayed")}</div>
          </div>
        `;
      }
    }
  } catch (err) {
    if (paperSheet) {
      paperSheet.innerHTML = `
        <div style="padding:2.5rem 1.5rem; text-align:center; color:var(--danger);">
          <div>Failed to load document preview: ${escapeHtml(err.message)}</div>
        </div>
      `;
    }
  }
}

/**
 * Retained as clean helper for page cuts
 */
function applyPageCutsToDocxPreview(container) {
  // Page cuts applied directly during render
}

function renderDocumentPage(pageIndex) {
  const paperSheet = document.getElementById("preview-paper-sheet");
  const inappContainer = document.getElementById("preview-inapp-container");
  if (!paperSheet || !AppState.currentPreviewPages || !AppState.currentPreviewPages[pageIndex]) return;

  paperSheet.innerHTML = AppState.currentPreviewPages[pageIndex];
  if (inappContainer) inappContainer.scrollTop = 0;
  const contentBox = document.getElementById("preview-content-box");
  if (contentBox) contentBox.scrollTop = 0;
}

function changeDocumentPage(direction) {
  if (AppState.currentDocxPagesCount && AppState.currentDocxPagesCount > 1) {
    const nextIdx = AppState.currentDocxPageIndex + direction;
    if (nextIdx >= 0 && nextIdx < AppState.currentDocxPagesCount) {
      AppState.currentDocxPageIndex = nextIdx;
      const targetSec = document.getElementById(`preview-docx-page-${nextIdx}`);
      const inappContainer = document.getElementById("preview-inapp-container");
      if (targetSec && inappContainer) {
        targetSec.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      const pageCounter = document.getElementById("preview-page-counter");
      const pagePrev = document.getElementById("preview-page-prev");
      const pageNext = document.getElementById("preview-page-next");
      if (pageCounter) pageCounter.textContent = `Page ${nextIdx + 1} of ${AppState.currentDocxPagesCount}`;
      if (pagePrev) pagePrev.disabled = (nextIdx <= 0);
      if (pageNext) pageNext.disabled = (nextIdx >= AppState.currentDocxPagesCount - 1);
    }
    return;
  }

  if (!AppState.currentPreviewPages || !AppState.currentPreviewPages.length) return;
  const newIndex = AppState.currentPreviewPageIndex + direction;
  if (newIndex >= 0 && newIndex < AppState.currentPreviewPages.length) {
    AppState.currentPreviewPageIndex = newIndex;
    renderDocumentPage(newIndex);

    const pageCounter = document.getElementById("preview-page-counter");
    const pagePrev = document.getElementById("preview-page-prev");
    const pageNext = document.getElementById("preview-page-next");

    if (pageCounter) pageCounter.textContent = `Page ${newIndex + 1} of ${AppState.currentPreviewPages.length}`;
    if (pagePrev) pagePrev.disabled = (newIndex <= 0);
    if (pageNext) pageNext.disabled = (newIndex >= AppState.currentPreviewPages.length - 1);
  }
}

// Format Date Helper
function formatDate(isoStr) {
  if (!isoStr) return "N/A";
  const d = new Date(isoStr);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// Format Date & Time Helper (e.g. Oct 14, 2026, 11:20 AM)
function formatDateTime(isoStr) {
  if (!isoStr) return "N/A";
  const d = new Date(isoStr);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) +
         " " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Navigation Tab Switcher
function switchTab(tabId) {
  AppState.currentTab = tabId;
  document.querySelectorAll(".nav-tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-pane").forEach(pane => {
    pane.classList.toggle("active", pane.id === `tab-${tabId}`);
  });

  if (tabId === "notifications") {
    // When user views notifications, the popup badge disappears, but all content stays inside!
    AppState.notificationsSeen = true;
    const notifBadge = document.getElementById("badge-notifications-count");
    if (notifBadge) {
      notifBadge.style.display = "none";
      notifBadge.textContent = "0";
    }
  }

  if (tabId === "dashboard") loadDashboard();
  else if (tabId === "matching") initMatchingTab();
  else if (tabId === "improvement") initImprovementTab();
  else if (tabId === "followups") loadFollowups();
  else if (tabId === "library") loadLibrary();
  else if (tabId === "notifications") loadNotifications();
}

function goToPendingFollowups() {
  AppState.highlightPending = true;
  const statusFilter = document.getElementById("followups-status-filter");
  if (statusFilter) statusFilter.value = "pending_review";
  switchTab("followups");
}

// Initializer
document.addEventListener("DOMContentLoaded", async () => {
  // Initialize light/dark theme
  initTheme();

  // Initialize inactivity input with persisted value
  const inactInput = document.getElementById("inactivity-threshold-input");
  if (inactInput) {
    inactInput.value = AppState.inactivityThreshold;
  }

  // Setup Navigation Tabs
  document.querySelectorAll(".nav-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      AppState.highlightPending = false;
      switchTab(btn.dataset.tab);
    });
  });

  // Setup Global Modal Close buttons
  document.querySelectorAll(".modal-close-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      btn.closest(".modal-overlay").classList.remove("active");
    });
  });

  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        overlay.classList.remove("active");
      }
    });
  });

  // Prevent default browser drag-and-drop navigation / page reload when dropping files
  window.addEventListener("dragover", (e) => {
    e.preventDefault();
  }, false);

  window.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      if (AppState.currentTab === "improvement") {
        handleImprovementFilesUpload(e.dataTransfer.files);
      } else if (AppState.currentTab === "matching") {
        handleFilesUpload(e.dataTransfer.files);
      } else {
        switchTab("improvement");
        handleImprovementFilesUpload(e.dataTransfer.files);
      }
    }
  }, false);

  // Load initial data
  await refreshDataCaches();
  loadDashboard();
  checkIKMStatus();
});

async function refreshDataCaches() {
  try {
    const [resumes, jobs, followups] = await Promise.all([
      API.getResumes(),
      API.getJobs(),
      API.getFollowups().catch(() => [])
    ]);
    AppState.resumes = resumes || [];
    AppState.jobs = jobs || [];
    AppState.allFollowups = followups || [];
    updateTabBadges();
    renderMatchExistingResumes();
    renderImproveExistingResumes();
    updateMatchSelectedCountBadge();
    updateImproveSelectedCountBadge();
    if (AppState.currentTab === "matching") {
      renderUploadedFilesList();
    }
  } catch (err) {
    console.error("Cache refresh error:", err);
  }
}

async function updateTabBadges() {
  const libBadge = document.getElementById("badge-library-count");
  if (libBadge) libBadge.textContent = AppState.resumes.length;
  try {
    const notifs = await API.getNotifications(true);
    const notifBadge = document.getElementById("badge-notifications-count");
    if (notifBadge) {
      if (AppState.notificationsSeen || !notifs.length) {
        notifBadge.style.display = "none";
        notifBadge.textContent = "0";
      } else {
        notifBadge.style.display = "inline-flex";
        notifBadge.textContent = notifs.length;
      }
    }
  } catch (e) {}
}

// ==========================================
// 1. DASHBOARD WORKFLOW
// ==========================================
async function loadDashboard() {
  try {
    const summary = await API.getDashboardSummary();
    
    document.getElementById("stat-total-resumes").textContent = summary.total_resumes;
    document.getElementById("stat-awaiting-review").textContent = summary.awaiting_review;
    document.getElementById("stat-followups-due").textContent = summary.follow_ups_due;
    document.getElementById("stat-active-jobs").textContent = summary.active_jobs;

    // Follow-ups tab badge
    const fuBadge = document.getElementById("badge-followups-count");
    if (fuBadge) fuBadge.textContent = summary.follow_ups_due;

    // 1. Render Follow-ups Status Pie / Donut Chart
    renderDashboardFollowupsPieChart(summary.followup_status_distribution || {});

    // 2. Render Recent Activity Logs Table
    renderDashboardActivityLogs(summary.recent_activity || []);

  } catch (err) {
    console.warn("Failed to load dashboard statistics:", err);
    showToast("Failed to load dashboard statistics", "error");
  }
}

function renderDashboardActivityLogs(activities) {
  const actBody = document.getElementById("dashboard-activity-body");
  if (!actBody) return;
  actBody.innerHTML = "";

  if (!activities || !activities.length) {
    actBody.innerHTML = "<tr><td colspan='4' class='text-dim text-center' style='padding:2rem;'>No recorded candidate actions yet.</td></tr>";
    return;
  }

  const actionBadgeMap = {
    "upload_resume": { label: "Uploaded", cls: "badge-ready" },
    "uploaded": { label: "Uploaded", cls: "badge-ready" },
    "reviewed": { label: "Reviewed", cls: "badge-ready" },
    "shortlisted": { label: "Shortlisted", cls: "badge-primary" },
    "contacted": { label: "Contacted", cls: "badge-primary" },
    "snooze": { label: "Snoozed", cls: "badge-warning" },
    "hired": { label: "Hired", cls: "badge-ready" },
    "rejected": { label: "Rejected", cls: "badge-danger" },
    "remark_added": { label: "Remark", cls: "badge-ready" }
  };

  activities.slice(0, 8).forEach(act => {
    const tr = document.createElement("tr");
    const badgeInfo = actionBadgeMap[act.action_type] || { label: (act.action_type || "Action").replace("_", " "), cls: "badge-ready" };
    const candName = act.candidate_name || (act.doc_id ? `Candidate ${act.doc_id}` : "System");
    const hasDoc = Boolean(act.doc_id && act.doc_id !== "System");

    tr.innerHTML = `
      <td>
        <div style="display:flex; flex-direction:column; gap:2px;">
          ${hasDoc 
            ? `<button type="button" class="doc-id-link" onclick="openCandidateRemarksModal('${act.doc_id}')" style="text-align:left; font-weight:600; color:var(--primary); font-size:0.84rem;" title="Click to view candidate remarks">${escapeHtml(candName)}</button>
               <span style="font-size:0.72rem; color:var(--text-dim); font-family:monospace;">${escapeHtml(act.doc_id)}</span>`
            : `<strong style="font-size:0.84rem;">${escapeHtml(candName)}</strong>`}
        </div>
      </td>
      <td>
        <span class="file-status-badge ${badgeInfo.cls}" style="font-size:0.74rem;">${escapeHtml(badgeInfo.label)}</span>
      </td>
      <td style="font-size:0.82rem; color:var(--text-muted); max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(act.notes || '')}">
        ${escapeHtml(act.notes || "Recorded recruitment event")}
      </td>
      <td style="font-size:0.75rem; color:var(--text-dim); white-space:nowrap;">
        ${formatDate(act.timestamp)}
      </td>
    `;
    actBody.appendChild(tr);
  });
}

function renderDashboardFollowupsPieChart(distribution) {
  const svg = document.getElementById("dashboard-followups-svg");
  const legend = document.getElementById("dashboard-followups-legend");
  const centerVal = document.getElementById("donut-center-val");
  const centerLbl = document.getElementById("donut-center-lbl");
  const totalBadge = document.getElementById("piechart-total-badge");
  if (!svg || !legend) return;

  const entries = Object.entries(distribution || {}).filter(([_, count]) => count > 0);
  const total = entries.reduce((sum, [_, count]) => sum + count, 0);

  if (totalBadge) totalBadge.textContent = `${total} Total`;
  if (centerVal) centerVal.textContent = total;
  if (centerLbl) centerLbl.textContent = "FOLLOW-UPS";

  if (total === 0) {
    svg.innerHTML = `
      <circle cx="100" cy="100" r="70" fill="transparent" stroke="var(--border-subtle)" stroke-width="24" stroke-dasharray="439.82 439.82" />
    `;
    legend.innerHTML = `
      <div style="text-align:center; padding:1.5rem 0.5rem; color:var(--text-muted); font-size:0.82rem;">
        No active follow-ups or overdue reviews in the pipeline.
      </div>
    `;
    return;
  }

  // Curated color map
  const colorMap = {
    "Overdue": "#ef4444",
    "Pending Review": "#f59e0b",
    "Shortlisted": "#6366f1",
    "Contacted": "#06b6d4",
    "Snoozed": "#8b5cf6",
    "Hired": "#10b981",
    "Rejected": "#dc2626",
    "Stale Inactive": "#64748b"
  };
  const fallbackColors = ["#3b82f6", "#ec4899", "#14b8a6", "#f97316", "#84cc16"];

  const radius = 70;
  const circumference = 2 * Math.PI * radius; // ~439.82
  let cumulativeOffset = 0;

  svg.innerHTML = "";
  legend.innerHTML = "";

  entries.forEach(([status, count], idx) => {
    const fraction = count / total;
    const strokeDash = fraction * circumference;
    const strokeOffset = cumulativeOffset * circumference;
    const color = colorMap[status] || fallbackColors[idx % fallbackColors.length];
    const pct = Math.round(fraction * 100);

    // SVG Circle Segment
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", "100");
    circle.setAttribute("cy", "100");
    circle.setAttribute("r", radius);
    circle.setAttribute("class", "donut-segment");
    circle.setAttribute("stroke", color);
    circle.setAttribute("stroke-dasharray", `${strokeDash} ${circumference}`);
    circle.setAttribute("stroke-dashoffset", `-${strokeOffset}`);
    circle.setAttribute("data-status", status);
    circle.setAttribute("data-count", count);
    circle.setAttribute("data-pct", pct);

    // Tooltip
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${status}: ${count} (${pct}%)`;
    circle.appendChild(title);

    svg.appendChild(circle);

    // Legend Item
    const item = document.createElement("div");
    item.className = "donut-legend-item";
    item.id = `donut-legend-${idx}`;
    item.innerHTML = `
      <div class="donut-legend-left">
        <span class="donut-legend-dot" style="background:${color};"></span>
        <span style="font-weight:600; color:var(--text-main); font-size:0.8rem;">${status}</span>
      </div>
      <div>
        <span class="donut-legend-count">${count}</span>
        <span class="donut-legend-pct">(${pct}%)</span>
      </div>
    `;

    // Interactivity
    const activate = () => {
      circle.style.strokeWidth = "32";
      circle.style.opacity = "1";
      item.classList.add("active");
      if (centerVal) centerVal.textContent = count;
      if (centerLbl) centerLbl.textContent = status.toUpperCase();
    };
    const deactivate = () => {
      circle.style.strokeWidth = "26";
      circle.style.opacity = "";
      item.classList.remove("active");
      if (centerVal) centerVal.textContent = total;
      if (centerLbl) centerLbl.textContent = "FOLLOW-UPS";
    };

    circle.addEventListener("mouseenter", activate);
    circle.addEventListener("mouseleave", deactivate);
    item.addEventListener("mouseenter", activate);
    item.addEventListener("mouseleave", deactivate);
    item.addEventListener("click", () => switchTab("followups"));

    legend.appendChild(item);

    cumulativeOffset += fraction;
  });
}

// ==========================================
// 2. CANDIDATE MATCHING WORKFLOW
// ==========================================
function initMatchingTab() {
  loadUploadedResumesFromStorage();
  renderJobSelector();
  setupUploadDropzone();
  setupShortlistValidation();
  renderMatchExistingResumes();
  renderUploadedFilesList();
  validateMatchForm();
}

function renderMatchExistingResumes() {
  const container = document.getElementById("match-existing-list");
  const countEl = document.getElementById("match-selected-count");
  const selectAllCb = document.getElementById("match-select-all-existing");
  const searchInput = document.getElementById("match-existing-search");
  if (!container) return;

  const query = (searchInput?.value || "").toLowerCase().trim();
  const allResumes = AppState.resumes || [];

  if (!AppState.resumes || !AppState.resumes.length) {
    API.getResumes().then(res => {
      if (res && res.length) {
        AppState.resumes = res;
        renderMatchExistingResumes();
      }
    }).catch(() => {});
  }

  const filtered = allResumes.filter(r => {
    if (!query) return true;
    const name = (r.full_name || r.candidate_name || r.pii?.name || "").toLowerCase();
    const docId = (r.doc_id || "").toLowerCase();
    const filename = (r.original_filename || "").toLowerCase();
    return name.includes(query) || docId.includes(query) || filename.includes(query);
  });

  if (countEl) countEl.textContent = AppState.selectedExistingMatchDocIds.size;

  if (selectAllCb) {
    if (filtered.length > 0) {
      const allSelected = filtered.every(r => AppState.selectedExistingMatchDocIds.has(r.doc_id));
      const someSelected = filtered.some(r => AppState.selectedExistingMatchDocIds.has(r.doc_id));
      selectAllCb.checked = allSelected;
      selectAllCb.indeterminate = someSelected && !allSelected;
    } else {
      selectAllCb.checked = false;
      selectAllCb.indeterminate = false;
    }
  }

  if (!filtered.length) {
    container.innerHTML = `<div style="font-size:0.78rem; color:var(--text-dim); text-align:center; padding:0.75rem;">No resumes found matching "${escapeHtml(query)}"</div>`;
    return;
  }

  container.innerHTML = "";
  filtered.forEach(r => {
    const isSelected = AppState.selectedExistingMatchDocIds.has(r.doc_id);
    const displayName = r.full_name || r.candidate_name || r.pii?.name || r.original_filename || r.doc_id;
    const itemEl = document.createElement("div");
    itemEl.className = `existing-resume-item ${isSelected ? "selected" : ""}`;
    itemEl.innerHTML = `
      <input type="checkbox" ${isSelected ? "checked" : ""} onchange="toggleMatchExistingResume('${r.doc_id}', this.checked)" style="cursor:pointer;" onclick="event.stopPropagation()">
      <div style="flex:1; min-width:0; overflow:hidden;" onclick="toggleMatchExistingResume('${r.doc_id}', ${!isSelected})">
        <div style="font-weight:600; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
          ${escapeHtml(displayName)}
        </div>
        <div style="font-size:0.72rem; color:var(--text-dim); display:flex; gap:0.5rem;">
          <span>ID: ${r.doc_id}</span>
          <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">(${escapeHtml(r.original_filename)})</span>
        </div>
      </div>
      <button type="button" class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); openResumePreview('${r.doc_id}', getMatchScopedPreviewList('${r.doc_id}'))" style="padding:0.2rem 0.5rem; font-size:0.72rem;">Preview</button>
    `;
    container.appendChild(itemEl);
  });
}

function toggleExpandExistingMatch() {
  const container = document.getElementById("match-existing-container") || document.getElementById("match-existing-collapsible");
  const chevron = document.getElementById("match-expand-chevron") || document.getElementById("match-existing-chevron");
  if (!container) return;
  const isHidden = container.style.display === "none" || !container.style.display;
  container.style.display = isHidden ? "block" : "none";
  if (chevron) chevron.textContent = isHidden ? "▲" : "▼";
  if (isHidden) {
    renderMatchExistingResumes();
  }
}

function updateMatchSelectedCountBadge() {
  const count = AppState.selectedExistingMatchDocIds.size;
  const badge = document.getElementById("match-selected-count-badge");
  if (badge) {
    badge.textContent = count;
  }
  const countEl = document.getElementById("match-selected-count");
  if (countEl) {
    countEl.textContent = count;
  }
}

function filterMatchExistingResumes() {
  renderMatchExistingResumes();
}

function toggleMatchExistingResume(docId, checked) {
  if (checked) {
    AppState.selectedExistingMatchDocIds.add(docId);
  } else {
    AppState.selectedExistingMatchDocIds.delete(docId);
  }
  renderMatchExistingResumes();
  updateMatchSelectedCountBadge();
  validateMatchForm();
}

function toggleSelectAllMatchExisting(checked) {
  const searchInput = document.getElementById("match-existing-search");
  const query = (searchInput?.value || "").toLowerCase().trim();
  const allResumes = AppState.resumes || [];

  const filtered = allResumes.filter(r => {
    if (!query) return true;
    const name = (r.full_name || r.candidate_name || r.pii?.name || "").toLowerCase();
    const docId = (r.doc_id || "").toLowerCase();
    const filename = (r.original_filename || "").toLowerCase();
    return name.includes(query) || docId.includes(query) || filename.includes(query);
  });

  filtered.forEach(r => {
    if (checked) {
      AppState.selectedExistingMatchDocIds.add(r.doc_id);
    } else {
      AppState.selectedExistingMatchDocIds.delete(r.doc_id);
    }
  });

  renderMatchExistingResumes();
  updateMatchSelectedCountBadge();
  validateMatchForm();
}

function renderUploadedFilesList() {
  const listContainer = document.getElementById("match-upload-progress");
  const countPill = document.getElementById("match-uploaded-count-pill");
  const clearBtn = document.getElementById("btn-clear-all-uploads");

  const uploadedCount = AppState.uploadedResumes.length;

  if (countPill) {
    if (uploadedCount > 0) {
      countPill.style.display = "inline-flex";
      countPill.textContent = `${uploadedCount} File${uploadedCount === 1 ? "" : "s"}`;
    } else {
      countPill.style.display = "none";
    }
  }

  if (clearBtn) {
    clearBtn.style.display = uploadedCount > 0 ? "inline-flex" : "none";
  }

  if (!listContainer) return;

  if (uploadedCount === 0) {
    listContainer.innerHTML = `
      <div style="font-size:0.8rem; color:var(--text-dim); padding:0.6rem 0.2rem; text-align:center; background:rgba(255,255,255,0.015); border:1px dashed var(--border-subtle); border-radius:var(--radius-sm);">
        No resumes uploaded for this search yet. Drop or choose resume files above.
      </div>
    `;
    return;
  }

  listContainer.innerHTML = "";
  AppState.uploadedResumes.forEach((item, idx) => {
    const row = document.createElement("div");
    row.className = "upload-file-item";
    const escapedFilename = (item.filename || "Resume").replace(/'/g, "\\'");
    const displayName = item.full_name || item.candidate_name || item.filename || "Candidate Resume";

    row.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.65rem; min-width:0; flex:1; margin-right:0.75rem;">
        <div style="min-width:0; overflow:hidden;">
          <div style="font-weight:600; color:#fff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(item.filename)}">
            ${escapeHtml(displayName)}
          </div>
          <div style="display:flex; align-items:center; gap:0.4rem; font-size:0.75rem; color:var(--text-muted); margin-top:2px;">
            ${item.doc_id ? `<span class="candidate-doc-tag" style="margin:0;">ID: ${item.doc_id}</span>` : ""}
            <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">(${escapeHtml(item.filename)})</span>
            ${item.error ? `<span style="color:var(--danger); font-size:0.75rem;">${item.error}</span>` : ""}
          </div>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:0.5rem; flex-shrink:0;">
        <button type="button" class="btn btn-secondary btn-sm" onclick="openResumePreview('${item.doc_id || ''}', getMatchScopedPreviewList('${item.doc_id || ''}'))" ${!item.doc_id ? 'disabled' : ''} title="Preview Resume" style="font-size:0.75rem; padding:0.25rem 0.6rem; border-radius:var(--radius-sm);">
          Preview
        </button>
        <button type="button" class="btn btn-danger btn-sm" onclick="removeUploadedResume('${item.doc_id || ''}', '${escapedFilename}', ${idx})" title="Remove this uploaded resume" style="font-size:0.75rem; padding:0.25rem 0.6rem; border-radius:var(--radius-sm); display:inline-flex; align-items:center; gap:0.25rem;">
          Remove
        </button>
      </div>
    `;
    listContainer.appendChild(row);
  });
}

function renderJobSelector() {
  const jobSelect = document.getElementById("match-job-select");
  const delBtn = document.getElementById("btn-delete-selected-job");
  if (!jobSelect) return;
  jobSelect.innerHTML = "<option value=''>-- Select Saved Job Description --</option>";
  AppState.jobs.forEach(job => {
    const opt = document.createElement("option");
    opt.value = job.job_id;
    opt.textContent = `${job.title} (${job.job_id})`;
    if (AppState.selectedJobId === job.job_id) opt.selected = true;
    jobSelect.appendChild(opt);
  });

  if (delBtn) {
    delBtn.style.display = AppState.selectedJobId ? "inline-flex" : "none";
  }

  jobSelect.onchange = (e) => {
    AppState.selectedJobId = e.target.value;
    const selected = AppState.jobs.find(j => j.job_id === e.target.value);
    const textArea = document.getElementById("match-jd-textarea");
    if (selected && textArea) {
      textArea.value = selected.preview_snippet;
    }
    if (delBtn) {
      delBtn.style.display = AppState.selectedJobId ? "inline-flex" : "none";
    }
    validateMatchForm();
  };
}

async function deleteCurrentlySelectedJob() {
  if (!AppState.selectedJobId) return;
  const job = AppState.jobs.find(j => j.job_id === AppState.selectedJobId);
  const title = job ? job.title : AppState.selectedJobId;
  showConfirmModal(
    "Delete Job Opening",
    `Are you sure you want to delete "${title}" (${AppState.selectedJobId})?`,
    async () => {
      try {
        await API.deleteJob(AppState.selectedJobId);
        showToast("Job opening deleted successfully", "success");
        AppState.selectedJobId = null;
        const textArea = document.getElementById("match-jd-textarea");
        if (textArea) textArea.value = "";
        await refreshDataCaches();
        renderJobSelector();
        initImprovementTab();
        const statJobs = document.getElementById("stat-active-jobs");
        if (statJobs) statJobs.textContent = AppState.jobs.length;
      } catch (err) {
        showToast(`Failed to delete job: ${err.message}`, "error");
      }
    }
  );
}

function setupUploadDropzone() {
  const dropzone = document.getElementById("match-dropzone");
  const fileInput = document.getElementById("match-file-input");
  const listContainer = document.getElementById("match-upload-progress");

  if (!dropzone || !fileInput) return;

  dropzone.onclick = () => fileInput.click();

  dropzone.ondragover = (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  };

  dropzone.ondragleave = () => dropzone.classList.remove("dragover");

  dropzone.ondrop = (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files?.length) {
      handleFilesUpload(e.dataTransfer.files);
    }
  };

  fileInput.onchange = () => {
    if (fileInput.files?.length) {
      handleFilesUpload(fileInput.files);
    }
  };
}

function loadUploadedResumesFromStorage() {
  try {
    const raw = sessionStorage.getItem("hr_uploaded_resumes");
    if (raw) {
      AppState.uploadedResumes = JSON.parse(raw);
    }
  } catch (e) {
    AppState.uploadedResumes = [];
  }
}

function saveUploadedResumesToStorage() {
  try {
    sessionStorage.setItem("hr_uploaded_resumes", JSON.stringify(AppState.uploadedResumes));
  } catch (e) {
    console.warn("Storage save error", e);
  }
}


function removeUploadedResume(docId, filename, index) {
  const displayName = filename || docId || "uploaded resume";
  // Scoped exclusively to Find Candidates tab temporary display list.
  // Must NOT delete from IKM/DMS, must NOT delete from Resume Library, must NOT call deleteResume API.
  if (docId) {
    AppState.uploadedResumes = AppState.uploadedResumes.filter(r => r.doc_id !== docId);
  } else if (typeof index === "number") {
    AppState.uploadedResumes.splice(index, 1);
  }
  saveUploadedResumesToStorage();
  showToast(`Resume "${displayName}" removed from search list`, "info");
  renderUploadedFilesList();
  validateMatchForm();
}

function clearAllUploadedResumes() {
  // Clear Find Candidates uploaded resumes from screen display
  AppState.uploadedResumes = [];
  saveUploadedResumesToStorage();

  // Clear candidate selections from existing dropdown and search criteria
  AppState.selectedExistingMatchDocIds.clear();
  AppState.activeMatchResults = null;

  const fileInput = document.getElementById("match-file-input");
  if (fileInput) fileInput.value = "";

  const resultsContainer = document.getElementById("match-results-container");
  if (resultsContainer) resultsContainer.innerHTML = "";

  const jobSelect = document.getElementById("match-job-select");
  if (jobSelect) jobSelect.value = "";

  const jobDesc = document.getElementById("match-job-desc");
  if (jobDesc) jobDesc.value = "";

  renderUploadedFilesList();
  updateMatchSelectedCountBadge();
  renderMatchExistingResumes();
  showToast("Candidate selection cleared from search.", "info");
  validateMatchForm();
}

async function handleFilesUpload(fileList) {
  if (!fileList || !fileList.length) return;
  showToast(`Uploading ${fileList.length} resume(s)...`, "info");

  const progressContainer = document.getElementById("match-upload-progress");
  if (progressContainer) {
    progressContainer.innerHTML = `
      <div class="upload-loading-card" style="margin-top:0.5rem; margin-bottom:0.75rem;">
        <div class="spinner"></div>
        <div style="font-weight:700; font-size:0.92rem; color:var(--text-main);">Uploading & Indexing ${fileList.length} Resume(s)...</div>
        <div style="font-size:0.78rem; color:var(--text-muted);">Extracting metadata & storing in IKM Platform</div>
      </div>
    `;
  }

  const formData = new FormData();
  for (let i = 0; i < fileList.length; i++) {
    formData.append("files", fileList[i]);
  }

  try {
    const res = await API.uploadResumes(formData);
    showToast(`Processed ${res.successful_count} file(s) successfully!`, "success");

    res.results.forEach(item => {
      const existingIdx = AppState.uploadedResumes.findIndex(r =>
        (item.doc_id && r.doc_id === item.doc_id) || (item.filename && r.filename === item.filename)
      );
      if (existingIdx >= 0) {
        AppState.uploadedResumes[existingIdx] = item;
      } else {
        AppState.uploadedResumes.push(item);
      }
    });

    saveUploadedResumesToStorage();

    // Automatically select "Only Uploaded Resumes" scope so it won't run library files
    const scopeRadio = document.getElementById("scope-uploaded-only");
    if (scopeRadio) scopeRadio.checked = true;
    AppState.matchScope = "uploaded";

    // Auto-adjust shortlist count to match number of uploaded candidates
    const readyCount = AppState.uploadedResumes.filter(r => r.doc_id && r.status === "ready").length;
    const input = document.getElementById("match-top-n-input");
    if (input && readyCount > 0) {
      input.value = Math.min(readyCount, 10);
    }

    await refreshDataCaches();
    renderUploadedFilesList();
    validateMatchForm();
  } catch (err) {
    showToast(`Upload failed: ${err.message}`, "error");
    renderUploadedFilesList();
  }
}

function setupShortlistValidation() {
  const input = document.getElementById("match-top-n-input");
  const jdText = document.getElementById("match-jd-textarea");

  if (input) {
    input.addEventListener("input", validateMatchForm);
  }
  if (jdText) {
    jdText.addEventListener("input", validateMatchForm);
  }
}

function validateMatchForm() {
  const input = document.getElementById("match-top-n-input");
  const jdText = document.getElementById("match-jd-textarea");
  const btn = document.getElementById("btn-run-match");
  const validationError = document.getElementById("match-validation-error");

  const countVal = parseInt(input?.value, 10);
  const hasValidCount = !isNaN(countVal) && countVal > 0 && countVal <= 100;
  const hasJD = (jdText?.value && jdText.value.trim().length >= 10) || !!AppState.selectedJobId;

  const totalSelectedCount = AppState.selectedExistingMatchDocIds.size + AppState.uploadedResumes.filter(r => r.doc_id).length;
  const hasResumes = totalSelectedCount > 0 || (AppState.resumes && AppState.resumes.length > 0);

  if (validationError) {
    if (isNaN(countVal) || countVal <= 0) {
      validationError.textContent = "Please enter a valid positive integer greater than 0.";
    } else if (countVal > 100) {
      validationError.textContent = "Maximum candidate count limit is 100.";
    } else if (!hasResumes) {
      validationError.textContent = "Please select existing resumes or upload candidate files.";
    } else {
      validationError.textContent = "";
    }
  }

  if (btn) {
    btn.disabled = !(hasValidCount && hasJD && hasResumes);
  }
}

// Trigger Candidate Matching
async function runCandidateMatching() {
  const input = document.getElementById("match-top-n-input");
  const jdText = document.getElementById("match-jd-textarea");
  const btn = document.getElementById("btn-run-match");
  const container = document.getElementById("match-results-container");
  const loadingIndicator = document.getElementById("match-loading-indicator");

  const requestedCount = parseInt(input.value, 10) || 5;
  const text = jdText.value.trim();

  // Combine selected existing resumes and uploaded resumes
  const targetDocIds = new Set();
  AppState.selectedExistingMatchDocIds.forEach(id => targetDocIds.add(id));
  AppState.uploadedResumes.forEach(r => {
    if (r.doc_id) targetDocIds.add(r.doc_id);
  });

  const docIdArray = Array.from(targetDocIds);

  btn.disabled = true;
  btn.textContent = "Screening...";
  if (loadingIndicator) loadingIndicator.style.display = "flex";
  container.innerHTML = "";

  try {
    const result = await API.matchCandidates(
      requestedCount,
      AppState.selectedJobId,
      AppState.selectedJobId ? null : text,
      docIdArray.length > 0 ? docIdArray : null
    );

    AppState.activeMatchResults = result;
    if (loadingIndicator) loadingIndicator.style.display = "none";
    renderMatchResults(result, docIdArray.length > 0 ? docIdArray.length : null);
    showToast(`Evaluated ${result.returned_count} candidate match(es)!`, "success");

    // Automatically scroll smoothly to results so the user doesn't have to scroll down manually!
    container.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    if (loadingIndicator) loadingIndicator.style.display = "none";
    container.innerHTML = `<div class='card' style='border-color:var(--danger); color:var(--danger);'>Error: ${err.message}</div>`;
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Show Results";
  }
}

function getMatchResultsPreviewList() {
  if (AppState.activeMatchResults?.results?.length) {
    return AppState.activeMatchResults.results.map(r => ({
      doc_id: r.doc_id,
      full_name: r.full_name || r.candidate_name || r.candidate_label || r.doc_id,
      original_filename: r.doc_id
    }));
  }
  return null;
}

function renderMatchResults(data, evaluatedUploadedCount = null) {
  const container = document.getElementById("match-results-container");
  container.innerHTML = "";

  // Notice banner for fewer than requested
  if (data.notice) {
    const notice = document.createElement("div");
    notice.className = "results-count-notice";
    notice.innerHTML = `<strong>ℹ️ Candidate Availability Notice:</strong> ${data.notice}`;
    container.appendChild(notice);
  }

  if (!data.results?.length) {
    container.innerHTML += "<div class='card text-center text-dim' style='padding:2rem;'>No eligible candidates matched the criteria.</div>";
    return;
  }

  const matchPreviewList = getMatchResultsPreviewList();

  data.results.forEach(cand => {
    const card = document.createElement("div");
    card.id = `candidate-card-${cand.doc_id}`;
    card.className = `candidate-card ${cand.rank === 1 ? "rank-1" : ""}`;

    const scoreClass = cand.internal_match_score >= 80 ? "score-high" : (cand.internal_match_score >= 60 ? "score-medium" : "score-moderate");

    // Display candidate's FULL NAME prominently
    const displayName = cand.full_name || cand.candidate_name || cand.candidate_label || cand.doc_id;
    const currentStatus = AppState.candidateActionStates[cand.doc_id] || cand.current_status || "pending_review";

    card.innerHTML = `
      <div class="candidate-header">
        <div class="candidate-meta">
          <div class="rank-badge">#${cand.rank}</div>
          <div>
            <div class="candidate-id-title">${escapeHtml(displayName)}</div>
            <div class="candidate-doc-tag">Document Reference: ${cand.doc_id}</div>
          </div>
        </div>
        <div class="score-pill-container">
          <div class="score-pill">
            <span class="score-number ${scoreClass}">${cand.internal_match_score}<span style="font-size:0.9rem; color:var(--text-dim);">/100</span></span>
            <span class="score-label">Internal Match Score</span>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="showScoreBreakdownModal('${cand.doc_id}')">Breakdown</button>
        </div>
      </div>

      <div class="evidence-section">
        <div class="evidence-block-title">Verified Match Evidence</div>
        <div class="tags-row">
          ${cand.matched_requirements.map(m => `<span class="tag-matched" title="${escapeHtml(m.evidence)}">${escapeHtml(m.requirement)}</span>`).join("")}
          ${cand.gaps.map(g => `<span class="tag-gap" title="${escapeHtml(g.recommendation)}">Missing: ${escapeHtml(g.requirement)}</span>`).join("")}
        </div>
        <div class="explanation-text">${escapeHtml(cand.explanation)}</div>
      </div>

      <div class="candidate-actions">
        <div class="actions-group">
          <button class="btn btn-secondary btn-sm" onclick="openResumePreview('${cand.doc_id}', getMatchResultsPreviewList())">Preview</button>
          <button class="btn btn-secondary btn-sm" onclick="launchImprovementForCandidate('${cand.doc_id}')">Improve Resume</button>
        </div>
        <div class="actions-group" id="actions-group-${cand.doc_id}" style="display:flex; align-items:center; gap:0.45rem;">
          <span class="file-status-badge badge-${currentStatus}" id="cand-status-badge-${cand.doc_id}" style="font-size:0.75rem; text-transform:capitalize;">${currentStatus.replace('_', ' ')}</span>
          <button type="button" class="btn btn-secondary btn-sm" onclick="viewCandidateDetailsModal('${cand.doc_id}')" title="View candidate and contact details" style="padding:0.3rem 0.55rem; display:inline-flex; align-items:center; justify-content:center;">${SVG_EYE_ICON}</button>
          <button type="button" class="btn btn-primary btn-sm" onclick="openActionModal('${cand.doc_id}')" title="Record recruiter action & notes">Action</button>
        </div>
      </div>
    `;

    container.appendChild(card);
  });
}

async function toggleCandidateAction(docId, actionType, buttonEl) {
  if (actionType === "remark") {
    openCandidateRemarksModal(docId);
    return;
  }

  if (actionType === "snooze") {
    openActionModal(docId, "snooze");
    return;
  }

  const currentStatus = AppState.candidateActionStates[docId] || 
    (AppState.resumes?.find(r => r.doc_id === docId)?.latest_status) ||
    "pending_review";

  let targetStatus = "pending_review";
  let backendActionType = "reset";
  let notes = "";

  if (actionType === "shortlist") {
    if (currentStatus === "shortlisted") {
      targetStatus = "pending_review";
      backendActionType = "reset";
      notes = "Candidate removed from shortlist";
    } else {
      targetStatus = "shortlisted";
      backendActionType = "shortlisted";
      notes = "Candidate shortlisted";
    }
  } else if (actionType === "contacted") {
    if (currentStatus === "contacted") {
      targetStatus = "pending_review";
      backendActionType = "reset";
      notes = "Candidate contacted status cleared";
    } else {
      targetStatus = "contacted";
      backendActionType = "contacted";
      notes = "Candidate contacted";
    }
  } else if (actionType === "reviewed") {
    if (currentStatus === "reviewed") {
      targetStatus = "pending_review";
      backendActionType = "reset";
      notes = "Reviewed status cleared";
    } else {
      targetStatus = "reviewed";
      backendActionType = "reviewed";
      notes = "Candidate marked as reviewed";
    }
  } else if (actionType === "hired") {
    if (currentStatus === "hired") {
      targetStatus = "pending_review";
      backendActionType = "reset";
      notes = "Hired status reverted";
    } else {
      targetStatus = "hired";
      backendActionType = "hired";
      notes = "Candidate hired";
    }
  }

  try {
    await API.recordAction(docId, backendActionType, targetStatus, notes);
    AppState.candidateActionStates[docId] = targetStatus;

    const group = document.getElementById(`actions-group-${docId}`);
    if (group) {
      const btnShortlist = group.querySelector(".btn-action-shortlist");
      const btnContacted = group.querySelector(".btn-action-contacted");
      const btnReviewed = group.querySelector(".btn-action-reviewed");
      const btnSnooze = group.querySelector(".btn-action-snooze");
      const btnHired = group.querySelector(".btn-action-hired");

      if (btnShortlist) btnShortlist.classList.toggle("active-shortlisted", targetStatus === "shortlisted");
      if (btnContacted) btnContacted.classList.toggle("active-contacted", targetStatus === "contacted");
      if (btnReviewed) btnReviewed.classList.toggle("active-reviewed", targetStatus === "reviewed");
      if (btnSnooze) btnSnooze.classList.toggle("active-snoozed", targetStatus === "in_progress" || targetStatus === "snooze");
      if (btnHired) btnHired.classList.toggle("active-hired", targetStatus === "hired");
    }

    showToast(targetStatus === "pending_review" ? `Cleared ${actionType} for candidate ${docId}` : `Candidate marked as ${actionType.toUpperCase()}`, "success");
    await refreshDataCaches();
    if (AppState.currentTab === "followups") await loadFollowups();
    if (AppState.currentTab === "library") await loadLibrary();
    await loadDashboard();
  } catch (err) {
    showToast(`Failed to update candidate status: ${err.message}`, "error");
  }
}

function showScoreBreakdownModal(docId) {
  let cand = AppState.activeMatchResults?.results?.find(r => String(r.doc_id) === String(docId) || r.doc_id === docId);
  if (!cand && AppState.activeMatchResults?.results?.length) {
    cand = AppState.activeMatchResults.results.find(r => r.candidate_label === docId || r.candidate_name === docId || r.full_name === docId);
  }
  if (!cand) {
    console.warn("Candidate not found for breakdown modal:", docId);
    showToast("Candidate details could not be found for score breakdown", "warning");
    return;
  }

  const content = document.getElementById("score-modal-content");
  if (!content) return;

  let b = cand.score_breakdown || {};
  if (typeof b === "string") {
    try { b = JSON.parse(b); } catch (e) { b = {}; }
  }

  const mand = b.mandatory_requirements || {};
  const tech = b.technical_skills || {};
  const exp = b.experience_and_projects || {};
  const edu = b.education_credentials || {};
  const ev = b.evidence_quality || {};

  const getWeightedPoints = (item, defaultWeight) => {
    if (item && item.score_weighted !== undefined && item.score_weighted !== null && !isNaN(Number(item.score_weighted))) {
      return Number(item.score_weighted);
    }
    const raw = Number(item?.score);
    if (!isNaN(raw)) {
      return Math.round(raw * defaultWeight * 10) / 10;
    }
    return 0;
  };

  const mandPts = getWeightedPoints(mand, 0.35);
  const techPts = getWeightedPoints(tech, 0.25);
  const expPts = getWeightedPoints(exp, 0.20);
  const eduPts = getWeightedPoints(edu, 0.10);
  const evPts = getWeightedPoints(ev, 0.10);

  let overallScore = 0;
  if (cand.internal_match_score !== undefined && cand.internal_match_score !== null && !isNaN(cand.internal_match_score)) {
    overallScore = cand.internal_match_score;
  } else if (cand.score !== undefined && cand.score !== null && !isNaN(cand.score)) {
    overallScore = Math.round(cand.score);
  } else {
    // Graceful calculation from component points if overall score was not serialized
    overallScore = Math.round(mandPts + techPts + expPts + eduPts + evPts);
  }

  const displayName = cand.full_name || cand.candidate_name || cand.candidate_label || cand.doc_id;

  content.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.3rem;">
      <h3 style="font-family:var(--font-heading); font-size:1.1rem; font-weight:700; margin:0;">${escapeHtml(displayName)} — Score Breakdown</h3>
      <div style="font-family:var(--font-heading); font-size:1.45rem; font-weight:800; color:var(--primary);">${overallScore} <span style="font-size:0.9rem; color:var(--text-dim); font-weight:600;">/ 100</span></div>
    </div>
    <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:0.55rem;">
      Diagnostic evaluation across core requirements, technical skills, experience depth, education, and documented evidence.
    </div>

    <div style="display:flex; flex-direction:column; gap:0.4rem;">
      <!-- 1. Mandatory Requirements -->
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); padding:0.5rem 0.75rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center; font-weight:700; margin-bottom:0.15rem;">
          <span style="color:#f8fafc; font-size:0.88rem;">Mandatory Requirements</span>
          <span style="color:var(--success); font-size:0.98rem; font-weight:800;">${mandPts.toFixed(1)} / 35</span>
        </div>
        <div style="font-size:0.76rem; color:var(--text-muted); line-height:1.35;">
          ${escapeHtml(mand.justification || `Matched ${mand.matched_count || 0} of ${mand.total_count || 1} core prerequisites.`)}
        </div>
        ${mand.missing && mand.missing.length ? `
          <div style="font-size:0.72rem; color:#fca5a5; margin-top:0.15rem;">
            <strong>Unsatisfied Mandatory:</strong> ${mand.missing.map(m => escapeHtml(typeof m === 'object' ? (m.requirement || JSON.stringify(m)) : m)).join(", ")}
          </div>
        ` : ''}
      </div>

      <!-- 2. Technical Skills -->
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); padding:0.5rem 0.75rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center; font-weight:700; margin-bottom:0.15rem;">
          <span style="color:#f8fafc; font-size:0.88rem;">Technical Skills</span>
          <span style="color:var(--accent-cyan); font-size:0.98rem; font-weight:800;">${techPts.toFixed(1)} / 25</span>
        </div>
        <div style="font-size:0.76rem; color:var(--text-muted); line-height:1.35;">
          ${escapeHtml(tech.justification || `Evaluated ${tech.matched_count || 0} of ${tech.total_count || 0} skills with project grounding.`)}
        </div>
        ${tech.missing && tech.missing.length ? `
          <div style="font-size:0.72rem; color:var(--warning); margin-top:0.15rem;">
            <strong>Missing Skills:</strong> ${tech.missing.map(m => escapeHtml(typeof m === 'object' ? (m.skill || JSON.stringify(m)) : m)).join(", ")}
          </div>
        ` : ''}
      </div>

      <!-- 3. Experience & Projects -->
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); padding:0.5rem 0.75rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center; font-weight:700; margin-bottom:0.15rem;">
          <span style="color:#f8fafc; font-size:0.88rem;">Experience &amp; Projects</span>
          <span style="color:#c084fc; font-size:0.98rem; font-weight:800;">${expPts.toFixed(1)} / 20</span>
        </div>
        <div style="font-size:0.76rem; color:var(--text-muted); line-height:1.35;">
          ${escapeHtml(exp.justification || `${exp.evaluated_items || 0} relevant career deliverables and artifacts evaluated.`)}
        </div>
      </div>

      <!-- 4. Education -->
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); padding:0.5rem 0.75rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center; font-weight:700; margin-bottom:0.15rem;">
          <span style="color:#f8fafc; font-size:0.88rem;">Education</span>
          <span style="color:var(--warning); font-size:0.98rem; font-weight:800;">${eduPts.toFixed(1)} / 10</span>
        </div>
        <div style="font-size:0.76rem; color:var(--text-muted); line-height:1.35;">
          ${escapeHtml(edu.justification || `Documented Degree: ${edu.qualification || 'Not specified'}.`)}
        </div>
      </div>

      <!-- 5. Evidence Quality -->
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); padding:0.5rem 0.75rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center; font-weight:700; margin-bottom:0.15rem;">
          <span style="color:#f8fafc; font-size:0.88rem;">Evidence Quality</span>
          <span style="color:var(--success); font-size:0.98rem; font-weight:800;">${evPts.toFixed(1)} / 10</span>
        </div>
        <div style="font-size:0.76rem; color:var(--text-muted); line-height:1.35;">
          ${escapeHtml(ev.justification || (ev.has_concrete_evidence ? 'Verified text evidence and verifiable achievements present.' : 'Basic evidence recorded.'))}
        </div>
      </div>
    </div>
  `;

  openModal("score-breakdown-modal");
}
window.showScoreBreakdownModal = showScoreBreakdownModal;

function viewOriginalResume(docId) {
  openResumePreview(docId);
}

async function recordCandidateQuickAction(docId, actionType) {
  try {
    await API.recordAction(docId, actionType, actionType, `Action '${actionType}' marked from candidate matching view.`);
    showToast(`Marked ${docId} as ${actionType}`, "success");
    await refreshDataCaches();
    if (AppState.currentTab === "followups") await loadFollowups();
    if (AppState.currentTab === "library") await loadLibrary();
    await loadDashboard();
  } catch (err) {
    showToast(`Failed to record action: ${err.message}`, "error");
  }
}

async function quickMarkHired(docId) {
  try {
    await API.recordAction(docId, "hired", "hired", "Candidate marked as Hired via recruiter action.");
    showToast(`Candidate ${docId} successfully marked as Hired`, "success");
    await refreshDataCaches();
    if (AppState.currentTab === "followups") await loadFollowups();
    if (AppState.currentTab === "library") await loadLibrary();
    await loadDashboard();
  } catch (err) {
    showToast(`Error recording Hired action: ${err.message}`, "error");
  }
}

// ==========================================
// 3. RESUME IMPROVEMENT WORKFLOW
// ==========================================
// ==========================================
// 3. RESUME IMPROVEMENT WORKFLOW
// ==========================================
function initImprovementTab() {
  const resumeSelect = document.getElementById("improve-resume-select");
  const jobSelect = document.getElementById("improve-job-select");

  if (resumeSelect) {
    resumeSelect.innerHTML = "<option value=''>-- Select Candidate Resume --</option>";
    AppState.resumes.forEach(r => {
      const opt = document.createElement("option");
      opt.value = r.doc_id;
      const name = r.full_name || r.candidate_name || r.pii?.name || r.original_filename;
      opt.textContent = `${name} (${r.doc_id})`;
      if (AppState.selectedResumeDocId === r.doc_id) opt.selected = true;
      resumeSelect.appendChild(opt);
    });
  }

  if (jobSelect) {
    jobSelect.innerHTML = "<option value=''>-- Select Target Job Description --</option>";
    AppState.jobs.forEach(j => {
      const opt = document.createElement("option");
      opt.value = j.job_id;
      opt.textContent = `${j.title} (${j.job_id})`;
      jobSelect.appendChild(opt);
    });
  }

  renderImproveExistingResumes();
  renderImproveUploadedFilesList();
  setupImprovementDropzone();
}

function onImproveJobSelected() {
  const jobSelect = document.getElementById("improve-job-select");
  const customJd = document.getElementById("improve-custom-jd");
  if (!jobSelect) return;
  const jobId = jobSelect.value;
  if (jobId) {
    const selected = (AppState.jobs || []).find(j => j.job_id === jobId);
    if (selected && customJd && !customJd.value.trim()) {
      customJd.value = selected.preview_snippet || selected.raw_text || "";
    }
  }
}

function renderImproveExistingResumes() {
  const container = document.getElementById("improve-existing-list");
  const searchInput = document.getElementById("improve-existing-search");
  const selectedNameEl = document.getElementById("improve-selected-name");
  const selectAllCb = document.getElementById("improve-select-all-existing");
  if (!container) return;

  const query = (searchInput?.value || "").toLowerCase().trim();
  const allResumes = AppState.resumes || [];

  if (!AppState.resumes || !AppState.resumes.length) {
    API.getResumes().then(res => {
      if (res && res.length) {
        AppState.resumes = res;
        renderImproveExistingResumes();
      }
    }).catch(() => {});
  }

  const filtered = allResumes.filter(r => {
    if (!query) return true;
    const name = (r.full_name || r.candidate_name || r.pii?.name || "").toLowerCase();
    const docId = (r.doc_id || "").toLowerCase();
    const filename = (r.original_filename || "").toLowerCase();
    return name.includes(query) || docId.includes(query) || filename.includes(query);
  });

  const selectedResume = allResumes.find(r => r.doc_id === AppState.selectedResumeDocId);
  const selectedCount = AppState.selectedExistingImproveDocIds.size;
  if (selectedNameEl) {
    selectedNameEl.textContent = selectedCount > 0 ? `${selectedCount} Selected` : "None Selected";
  }
  const countEl = document.getElementById("improve-selected-count");
  if (countEl) {
    countEl.textContent = selectedCount;
  }

  if (selectAllCb) {
    if (filtered.length > 0) {
      const allSelected = filtered.every(r => AppState.selectedExistingImproveDocIds.has(r.doc_id));
      const someSelected = filtered.some(r => AppState.selectedExistingImproveDocIds.has(r.doc_id));
      selectAllCb.checked = allSelected;
      selectAllCb.indeterminate = someSelected && !allSelected;
    } else {
      selectAllCb.checked = false;
      selectAllCb.indeterminate = false;
    }
  }

  if (!filtered.length) {
    container.innerHTML = `<div style="font-size:0.78rem; color:var(--text-dim); text-align:center; padding:0.75rem;">No resumes found matching "${escapeHtml(query)}"</div>`;
    return;
  }

  container.innerHTML = "";
  filtered.forEach(r => {
    const isChecked = AppState.selectedExistingImproveDocIds.has(r.doc_id);
    const isCurrentActive = AppState.selectedResumeDocId === r.doc_id;
    const displayName = r.full_name || r.candidate_name || r.pii?.name || r.original_filename || r.doc_id;
    const itemEl = document.createElement("div");
    itemEl.className = `existing-resume-item ${isCurrentActive || isChecked ? "selected" : ""}`;
    itemEl.innerHTML = `
      <input type="checkbox" ${isChecked ? "checked" : ""} onchange="toggleImproveExistingResume('${r.doc_id}', this.checked)" style="cursor:pointer;" onclick="event.stopPropagation()">
      <div style="flex:1; min-width:0; overflow:hidden;" onclick="toggleImproveExistingResume('${r.doc_id}', ${!isChecked})">
        <div style="font-weight:600; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
          ${escapeHtml(displayName)}
        </div>
        <div style="font-size:0.72rem; color:var(--text-dim); display:flex; gap:0.5rem;">
          <span>ID: ${r.doc_id}</span>
          <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">(${escapeHtml(r.original_filename)})</span>
        </div>
      </div>
      <button type="button" class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); openResumePreview('${r.doc_id}', getImproveScopedPreviewList('${r.doc_id}'))" style="padding:0.2rem 0.5rem; font-size:0.72rem;">Preview</button>
    `;
    container.appendChild(itemEl);
  });
}

function toggleExpandExistingImprove() {
  const container = document.getElementById("improve-existing-container") || document.getElementById("improve-existing-collapsible");
  const chevron = document.getElementById("improve-expand-chevron") || document.getElementById("improve-existing-chevron");
  if (!container) return;
  const isHidden = container.style.display === "none" || !container.style.display;
  container.style.display = isHidden ? "block" : "none";
  if (chevron) chevron.textContent = isHidden ? "▲" : "▼";
  if (isHidden) {
    renderImproveExistingResumes();
  }
}

function updateImproveSelectedCountBadge() {
  const badge = document.getElementById("improve-selected-count-badge");
  const count = AppState.selectedExistingImproveDocIds.size;
  if (badge) {
    badge.textContent = count;
  }
  const countEl = document.getElementById("improve-selected-count");
  if (countEl) {
    countEl.textContent = count;
  }
  const selectedNameEl = document.getElementById("improve-selected-name");
  if (selectedNameEl) {
    selectedNameEl.textContent = count > 0 ? `${count} Selected` : "None Selected";
  }
}

function filterImproveExistingResumes() {
  renderImproveExistingResumes();
}

function selectResumeForImprovement(docId) {
  AppState.selectedResumeDocId = docId;
  AppState.selectedExistingImproveDocIds.add(docId);
  const sel = document.getElementById("improve-resume-select");
  if (sel) sel.value = docId;
  renderImproveExistingResumes();
  updateImproveSelectedCountBadge();
  onImproveResumeSelected();
}

function toggleImproveExistingResume(docId, checked) {
  if (checked) {
    AppState.selectedExistingImproveDocIds.add(docId);
    AppState.selectedResumeDocId = docId;
  } else {
    AppState.selectedExistingImproveDocIds.delete(docId);
    if (AppState.selectedResumeDocId === docId) {
      AppState.selectedResumeDocId = Array.from(AppState.selectedExistingImproveDocIds)[0] || null;
    }
  }
  const sel = document.getElementById("improve-resume-select");
  if (sel) sel.value = AppState.selectedResumeDocId || "";
  renderImproveExistingResumes();
  updateImproveSelectedCountBadge();
  renderImproveCandidatePersonalDetails();
}

function toggleSelectAllImproveExisting(checked) {
  const searchInput = document.getElementById("improve-existing-search");
  const query = (searchInput?.value || "").toLowerCase().trim();
  const allResumes = AppState.resumes || [];

  const filtered = allResumes.filter(r => {
    if (!query) return true;
    const name = (r.full_name || r.candidate_name || r.pii?.name || "").toLowerCase();
    const docId = (r.doc_id || "").toLowerCase();
    const filename = (r.original_filename || "").toLowerCase();
    return name.includes(query) || docId.includes(query) || filename.includes(query);
  });

  filtered.forEach(r => {
    if (checked) {
      AppState.selectedExistingImproveDocIds.add(r.doc_id);
    } else {
      AppState.selectedExistingImproveDocIds.delete(r.doc_id);
    }
  });

  if (checked && filtered.length > 0) {
    AppState.selectedResumeDocId = filtered[0].doc_id;
  } else if (!checked) {
    AppState.selectedResumeDocId = null;
  }

  const sel = document.getElementById("improve-resume-select");
  if (sel) sel.value = AppState.selectedResumeDocId || "";

  renderImproveExistingResumes();
  updateImproveSelectedCountBadge();
  renderImproveCandidatePersonalDetails();
}

function renderImproveUploadedFilesList() {
  const listContainer = document.getElementById("improve-uploaded-list");
  if (!listContainer) return;

  if (!AppState.improveUploadedResumes || !AppState.improveUploadedResumes.length) {
    listContainer.innerHTML = "";
    return;
  }

  listContainer.innerHTML = "";
  AppState.improveUploadedResumes.forEach((item, idx) => {
    const row = document.createElement("div");
    row.className = "upload-file-item";
    const displayName = item.full_name || item.candidate_name || item.filename || "Uploaded Resume";

    row.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.65rem; min-width:0; flex:1; margin-right:0.75rem;">
        <div style="min-width:0; overflow:hidden;" onclick="selectResumeForImprovement('${item.doc_id}')" style="cursor:pointer;">
          <div style="font-weight:600; color:var(--text-main); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
            ${escapeHtml(displayName)}
          </div>
          <div style="display:flex; align-items:center; gap:0.4rem; font-size:0.72rem; color:var(--text-muted); margin-top:2px;">
            ${item.doc_id ? `<span class="candidate-doc-tag" style="margin:0;">ID: ${item.doc_id}</span>` : ""}
            <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">(${escapeHtml(item.filename)})</span>
          </div>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:0.5rem; flex-shrink:0;">
        <button type="button" class="btn btn-secondary btn-sm" onclick="openResumePreview('${item.doc_id || ''}', getImproveScopedPreviewList('${item.doc_id || ''}'))" ${!item.doc_id ? 'disabled' : ''} style="font-size:0.75rem; padding:0.25rem 0.6rem;">
          Preview
        </button>
        <button type="button" class="btn btn-danger btn-sm" onclick="removeImproveUploadedResume(${idx})" style="font-size:0.75rem; padding:0.25rem 0.6rem; border-radius:var(--radius-sm);">
          Remove
        </button>
      </div>
    `;
    listContainer.appendChild(row);
  });
}

function removeImproveUploadedResume(idx) {
  if (AppState.improveUploadedResumes && AppState.improveUploadedResumes[idx]) {
    const item = AppState.improveUploadedResumes[idx];
    if (AppState.selectedResumeDocId === item.doc_id) {
      AppState.selectedResumeDocId = null;
    }
    if (item.doc_id) {
      AppState.selectedExistingImproveDocIds.delete(item.doc_id);
    }
    AppState.improveUploadedResumes.splice(idx, 1);
    renderImproveUploadedFilesList();
    renderImproveExistingResumes();
    updateImproveSelectedCountBadge();
    renderImproveCandidatePersonalDetails();
  }
}

async function handleImprovementFilesUpload(fileList) {
  if (!fileList || !fileList.length) return;
  showToast(`Uploading ${fileList.length} resume(s)...`, "info");

  const listContainer = document.getElementById("improve-uploaded-files-list");
  if (listContainer) {
    listContainer.innerHTML = `
      <div class="upload-loading-card" style="margin-top:0.5rem; margin-bottom:0.75rem;">
        <div class="spinner"></div>
        <div style="font-weight:700; font-size:0.92rem; color:var(--text-main);">Uploading & Indexing ${fileList.length} Resume(s)...</div>
        <div style="font-size:0.78rem; color:var(--text-muted);">Extracting metadata & storing in IKM Platform</div>
      </div>
    `;
  }

  // Fresh upload replaces previous batch selections to keep queue count accurate
  AppState.improveUploadedResumes = [];
  AppState.selectedExistingImproveDocIds.clear();
  AppState.selectedResumeDocId = null;
  AppState.appliedImprovements = {};

  const formData = new FormData();
  for (let i = 0; i < fileList.length; i++) {
    formData.append("files", fileList[i]);
  }

  try {
    const res = await API.uploadResumes(formData);
    showToast(`Uploaded ${res.successful_count} file(s) successfully!`, "success");

    (res.results || []).forEach(item => {
      if (item.doc_id) {
        AppState.improveUploadedResumes.push(item);
        AppState.selectedExistingImproveDocIds.add(item.doc_id);
      }
    });

    if (res.results && res.results.length > 0 && res.results[0].doc_id) {
      AppState.selectedResumeDocId = res.results[0].doc_id;
      const sel = document.getElementById("improve-resume-select");
      if (sel) sel.value = res.results[0].doc_id;
    }

    await refreshDataCaches();
    initImprovementTab();
    renderImproveUploadedFilesList();
    updateImproveSelectedCountBadge();
    renderImproveCandidatePersonalDetails();
  } catch (err) {
    showToast(`Upload failed: ${err.message}`, "error");
    renderImproveUploadedFilesList();
  }
}

function onImproveResumeSelected() {
  const sel = document.getElementById("improve-resume-select");
  if (!sel) return;
  const docId = sel.value;
  AppState.selectedResumeDocId = docId;

  if (docId) {
    AppState.selectedExistingImproveDocIds.add(docId);
    API.recordResumeOpened(docId).catch(() => {});
    fetchAndPopulateCandidatePII(docId);
  } else {
    renderImproveCandidatePersonalDetails();
  }
  updateImproveSelectedCountBadge();
}

function setupImprovementDropzone() {
  const dropzone = document.getElementById("improve-dropzone");
  const fileInput = document.getElementById("improve-resume-file-input");
  if (!dropzone || !fileInput) return;

  dropzone.onclick = () => fileInput.click();

  dropzone.ondragover = (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  };

  dropzone.ondragleave = () => dropzone.classList.remove("dragover");

  dropzone.ondrop = (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files?.length) {
      handleImprovementFilesUpload(e.dataTransfer.files);
    }
  };

  fileInput.onchange = () => {
    if (fileInput.files?.length) {
      handleImprovementFilesUpload(fileInput.files);
    }
  };
}

async function launchImprovementForCandidate(docId) {
  // Clear prior multi-resume state for a clean single-candidate improvement session
  AppState.improveUploadedResumes = [];
  AppState.selectedExistingImproveDocIds.clear();
  AppState.selectedResumeDocId = docId;
  AppState.selectedExistingImproveDocIds.add(docId);
  AppState.currentImprovementBatchDocIds = [docId];
  AppState.activeImprovementDocId = docId;
  AppState.appliedImprovements = {};

  // Retrieve current job description from Find Candidates (Matching tab)
  const matchJobSelect = document.getElementById("match-job-select");
  const matchJdTextarea = document.getElementById("match-jd-textarea");
  const selectedJobId = (matchJobSelect && matchJobSelect.value) || AppState.selectedJobId || "";
  const customJdText = (matchJdTextarea && matchJdTextarea.value) ? matchJdTextarea.value.trim() : "";

  switchTab("improvement");

  const sel = document.getElementById("improve-resume-select");
  if (sel) sel.value = docId;

  // Apply the same job description automatically (selected job opening or custom written JD)
  const improveJobSelect = document.getElementById("improve-job-select");
  const improveCustomJd = document.getElementById("improve-custom-jd");

  if (selectedJobId && improveJobSelect) {
    improveJobSelect.value = selectedJobId;
  }
  if (customJdText && improveCustomJd) {
    improveCustomJd.value = customJdText;
  } else if (selectedJobId && improveCustomJd && !improveCustomJd.value.trim()) {
    const jobObj = (AppState.jobs || []).find(j => j.job_id === selectedJobId);
    if (jobObj && (jobObj.preview_snippet || jobObj.raw_text)) {
      improveCustomJd.value = jobObj.preview_snippet || jobObj.raw_text;
    }
  }

  renderImproveExistingResumes();
  renderImproveUploadedFilesList();
  updateImproveSelectedCountBadge();
  await fetchAndPopulateCandidatePII(docId);

  // Requirement 3: Automatically initiate improvement, apply changes, download and preview
  const hasJd = (selectedJobId && improveJobSelect && improveJobSelect.value) ||
                (improveCustomJd && improveCustomJd.value.trim().length >= 10);

  if (hasJd) {
    showToast("Starting automatic resume improvement workflow...", "info");
    setTimeout(() => {
      runResumeImprovementAnalysis();
    }, 250);
  } else {
    showToast("Please select or enter a Job Description to start improving candidate's resume.", "warning");
    if (improveJobSelect) improveJobSelect.focus();
  }
}

// Candidate Personal & Contact Information (Dynamic Multi-Card)
async function fetchAndPopulateCandidatePII(docId) {
  if (!docId) return;
  try {
    const pii = await API.getResumePII(docId);
    const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId);
    let linksVal = pii.links || "";
    if (!linksVal && (pii.linkedin || pii.github || pii.portfolio)) {
      linksVal = [pii.linkedin, pii.github, pii.portfolio].filter(Boolean).join(" | ");
    }
    AppState.candidatePersonalDetails[docId] = {
      name: pii.name || resumeObj?.full_name || resumeObj?.candidate_name || "",
      role: pii.title || pii.role || resumeObj?.profile?.title || resumeObj?.profile?.role || "",
      phone: pii.phone || "",
      email: pii.email || "",
      location: pii.location || pii.address || "",
      links: linksVal
    };
  } catch (err) {
    console.warn(`Could not load PII for ${docId}:`, err);
    const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId);
    AppState.candidatePersonalDetails[docId] = {
      name: resumeObj?.full_name || resumeObj?.candidate_name || resumeObj?.pii?.name || "",
      role: resumeObj?.profile?.title || resumeObj?.profile?.role || "",
      phone: resumeObj?.pii?.phone || "",
      email: resumeObj?.pii?.email || "",
      location: resumeObj?.pii?.location || resumeObj?.pii?.address || "",
      links: resumeObj?.pii?.links || ""
    };
  }
  renderImproveCandidatePersonalDetails(docId);
}

async function renderImproveCandidatePersonalDetails(targetDocId = null) {
  const container = document.getElementById("active-candidate-personal-details-area") || 
                    document.getElementById("improve-personal-details-container");
  if (!container) return;

  const docIdList = getSelectedImprovementDocIds();
  const docId = targetDocId || AppState.activeImprovementDocId || docIdList[0];

  if (!docId) {
    container.innerHTML = "";
    return;
  }

  // Preload missing or fresh PII if not loaded yet
  if (!AppState.candidatePersonalDetails[docId]) {
    const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId) ||
                      (AppState.improveUploadedResumes || []).find(r => r.doc_id === docId);
    AppState.candidatePersonalDetails[docId] = {
      name: resumeObj?.full_name || resumeObj?.candidate_name || resumeObj?.pii?.name || "",
      role: resumeObj?.profile?.title || resumeObj?.profile?.role || "",
      phone: resumeObj?.pii?.phone || "",
      email: resumeObj?.pii?.email || "",
      location: resumeObj?.pii?.location || resumeObj?.pii?.address || "",
      links: resumeObj?.pii?.links || ""
    };

    API.getResumePII(docId).then(pii => {
      if (pii) {
        let linksVal = pii.links || "";
        if (!linksVal && (pii.linkedin || pii.github || pii.portfolio)) {
          linksVal = [pii.linkedin, pii.github, pii.portfolio].filter(Boolean).join(" | ");
        }
        AppState.candidatePersonalDetails[docId] = {
          name: pii.name || AppState.candidatePersonalDetails[docId].name,
          role: pii.title || pii.role || AppState.candidatePersonalDetails[docId].role,
          phone: pii.phone || AppState.candidatePersonalDetails[docId].phone,
          email: pii.email || AppState.candidatePersonalDetails[docId].email,
          location: pii.location || pii.address || AppState.candidatePersonalDetails[docId].location,
          links: linksVal || AppState.candidatePersonalDetails[docId].links
        };
        renderImproveCandidatePersonalDetails(docId);
      }
    }).catch(() => {});
  }

  const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId) ||
                    (AppState.improveUploadedResumes || []).find(r => r.doc_id === docId);
  const filename = resumeObj?.original_filename || resumeObj?.filename || `${docId}.docx`;
  const details = AppState.candidatePersonalDetails[docId] || {};

  const fields = [
    { key: "name", label: "Full Name", placeholder: "e.g. Alex Morgan", val: details.name || "", required: true },
    { key: "role", label: "Professional Title / Role", placeholder: "e.g. Senior Software Engineer", val: details.role || "", required: true },
    { key: "phone", label: "Phone Number", placeholder: "e.g. +1 555-0199", val: details.phone || "", required: true },
    { key: "email", label: "Email Address", placeholder: "e.g. candidate@example.com", val: details.email || "", required: true },
    { key: "location", label: "Address / Location (Optional)", placeholder: "e.g. San Francisco, CA (Optional)", val: details.location || "", required: false },
    { key: "links", label: "Portfolio / LinkedIn Links (Optional)", placeholder: "e.g. linkedin.com/in/profile (Optional)", val: details.links || "", required: false }
  ];

  container.innerHTML = `
    <div class="card" id="cand-pii-card-${docId}" style="margin-bottom:1.25rem; background:var(--bg-surface-subtle); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:1.2rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.85rem; padding-bottom:0.6rem; border-bottom:1px solid var(--border-subtle); flex-wrap:wrap; gap:0.5rem;">
        <div>
          <h3 style="font-family: var(--font-heading); font-size: 1.05rem; margin-bottom: 0.2rem; color:var(--text-main);">
            Candidate Personal &amp; Contact Information
          </h3>
          <p style="font-size: 0.8rem; color: var(--text-muted); margin:0;">
            Automatically populated for active candidate. Missing required fields are highlighted for verification.
          </p>
        </div>
        <div style="display:flex; align-items:center; gap:0.6rem;">
          <span class="candidate-doc-tag" style="margin:0;">ID: ${docId}</span>
          <button type="button" class="btn btn-secondary btn-sm" onclick="openResumePreview('${docId}')" style="padding:0.25rem 0.65rem; font-size:0.75rem; display:inline-flex; align-items:center; gap:0.35rem;">
            ${SVG_EYE_ICON} Preview Original
          </button>
        </div>
      </div>

      <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.85rem;">
        <span style="font-weight:700; font-size:0.95rem; color:var(--text-main);">Active Candidate Resume &mdash; <span style="color:var(--primary); font-family:var(--font-mono);">${escapeHtml(filename)}</span></span>
      </div>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.85rem;">
        ${fields.map(f => {
          const isMissing = f.required && (!f.val || f.val.trim() === "");
          return `
            <div class="form-group ${isMissing ? 'field-missing' : ''}" id="fg-${docId}-${f.key}" style="margin-bottom:0;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;">
                <label class="form-label" for="inp-${docId}-${f.key}" style="margin-bottom:0; font-size:0.78rem;">${f.label}</label>
                ${isMissing ? `<span class="missing-tag" id="tag-${docId}-${f.key}">Missing</span>` : ''}
              </div>
              <input type="text" id="inp-${docId}-${f.key}" 
                class="form-control ${isMissing ? 'input-missing' : ''}" 
                style="font-size:0.82rem; padding:0.4rem 0.65rem;"
                value="${escapeHtml(f.val)}" 
                placeholder="${isMissing ? 'Required — enter ' + f.label.toLowerCase() : f.placeholder}"
                oninput="onPersonalDetailsInputChange('${docId}', '${f.key}', this)">
            </div>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function onPersonalDetailsInputChange(docId, field, inputEl) {
  if (!AppState.candidatePersonalDetails[docId]) {
    AppState.candidatePersonalDetails[docId] = {};
  }
  const val = inputEl.value;
  AppState.candidatePersonalDetails[docId][field] = val;

  const fg = document.getElementById(`fg-${docId}-${field}`);
  const tag = document.getElementById(`tag-${docId}-${field}`);

  // Optional fields never trigger missing badge
  if (field === "location" || field === "links") {
    inputEl.classList.remove("input-missing");
    if (fg) fg.classList.remove("field-missing");
    if (tag) tag.remove();
    return;
  }

  if (val && val.trim().length > 0) {
    inputEl.classList.remove("input-missing");
    if (fg) fg.classList.remove("field-missing");
    if (tag) tag.remove();
  } else {
    inputEl.classList.add("input-missing");
    if (fg) {
      fg.classList.add("field-missing");
      if (!fg.querySelector(".missing-tag")) {
        const labelRow = fg.querySelector("div");
        if (labelRow) {
          const newTag = document.createElement("span");
          newTag.className = "missing-tag";
          newTag.id = `tag-${docId}-${field}`;
          newTag.textContent = "Missing";
          labelRow.appendChild(newTag);
        }
      }
    }
  }
}

async function runResumeImprovementAnalysis() {
  if (window._isImprovementWorkflowRunning) {
    showToast("Resume improvement workflow is already in progress, please wait...", "info");
    return;
  }

  const docIdArray = getSelectedImprovementDocIds();
  if (!docIdArray.length) {
    showToast("Please select at least one candidate resume to improve", "warning");
    return;
  }

  const jobSelect = document.getElementById("improve-job-select");
  const jobId = jobSelect?.value || null;
  const customJd = document.getElementById("improve-custom-jd")?.value.trim() || null;
  const btnStart = document.getElementById("btn-start-improvement");
  const btnContinue = document.getElementById("btn-continue-improvement");
  const loadingIndicator = document.getElementById("improve-loading-indicator");
  const container = document.getElementById("improvement-results-area");

  if (!jobId && (!customJd || customJd.length < 10)) {
    showToast("Please choose a saved job opening or enter custom job requirements", "warning");
    return;
  }

  const targetRole = (jobId && jobSelect && jobSelect.options[jobSelect.selectedIndex]?.text) || "Senior Technical Professional";

  window._isImprovementWorkflowRunning = true;
  if (btnStart) btnStart.disabled = true;
  if (btnContinue) btnContinue.disabled = true;
  if (loadingIndicator) loadingIndicator.style.display = "flex";
  if (container) container.innerHTML = "";

  AppState.improvementAnalysesByDocId = {};
  AppState.currentImprovementBatchDocIds = [...docIdArray];
  AppState.appliedImprovements = {};

  const successfulResults = [];
  const failedResults = [];

  try {
    const total = docIdArray.length;
    for (let i = 0; i < total; i++) {
      const docId = docIdArray[i];
      let personalDetails = AppState.candidatePersonalDetails[docId] || null;
      if (!personalDetails) {
        await fetchAndPopulateCandidatePII(docId);
        personalDetails = AppState.candidatePersonalDetails[docId] || null;
      }
      const candidateInfo = (AppState.resumes || []).find(r => r.doc_id === docId);
      const candDisplayName = personalDetails?.name || candidateInfo?.full_name || candidateInfo?.candidate_name || docId;

      if (loadingIndicator) {
        const titleEl = loadingIndicator.querySelector("div:nth-child(2)");
        const descEl = loadingIndicator.querySelector("div:nth-child(3)");
        if (titleEl) {
          titleEl.textContent = total > 1
            ? `Processing Candidate ${i + 1} of ${total}: ${candDisplayName}...`
            : `Improving Resume for ${candDisplayName}...`;
        }
        if (descEl) {
          descEl.textContent = "AI analysis, targeted edits, Word DOCX generation, and IKM persistence";
        }
      }

      try {
        // Step 1: AI Improvement Analysis
        const analysis = await API.analyzeImprovement(docId, jobId, jobId ? null : customJd, personalDetails);
        AppState.improvementAnalysesByDocId[docId] = analysis;
        window._currentImprovementData = analysis;

        // Step 2: Auto-approve changes and build payload for Word generation
        const approvedChanges = [];
        (analysis.changes || []).forEach(c => {
          approvedChanges.push({
            ...c,
            status: "accepted"
          });
        });

        const summary = analysis.change_summary || `Target-aligned optimization for ${targetRole}`;
        const content = analysis.improved_resume_text || analysis.original_text_preview || "";

        // Step 3: Automatically apply changes and generate improved Word DOCX
        const genRes = await API.generateWordResume(docId, content, summary, targetRole, personalDetails, approvedChanges);
        if (genRes && genRes.version_id) {
          if (!window._lastSavedVersionIdByDoc) window._lastSavedVersionIdByDoc = {};
          window._lastSavedVersionIdByDoc[docId] = genRes.version_id;
          if (genRes.library_doc_id) {
            if (!window._lastSavedLibraryDocIdByDoc) window._lastSavedLibraryDocIdByDoc = {};
            window._lastSavedLibraryDocIdByDoc[docId] = genRes.library_doc_id;
          }

          const appliedEntry = {
            doc_id: docId,
            library_doc_id: genRes.library_doc_id || null,
            version_id: genRes.version_id,
            filename: genRes.filename || `${docId}_Improved.docx`,
            full_name: candDisplayName,
            download_url: genRes.download_url,
            timestamp: Date.now()
          };
          AppState.appliedImprovements[docId] = appliedEntry;
          successfulResults.push(appliedEntry);
        } else {
          throw new Error("Failed to generate or persist improved DOCX.");
        }
      } catch (candErr) {
        console.error(`Improvement error for candidate ${docId}:`, candErr);
        failedResults.push({ docId, name: candDisplayName, error: candErr.message });
        showToast(`Failed for ${candDisplayName}: ${candErr.message}`, "error");
      }
    }

    AppState.activeImprovementDocId = successfulResults[0]?.doc_id || docIdArray[0];
    renderImprovementWorkspace(docIdArray);

    // Refresh library and data caches
    await refreshDataCaches();
    if (typeof loadLibrary === "function") {
      loadLibrary().catch(() => {});
    }

    if (successfulResults.length > 0) {
      showToast(
        successfulResults.length > 1
          ? `Successfully improved and applied ${successfulResults.length} resumes! Initiating downloads...`
          : `Resume improved and applied successfully! Downloading...`,
        "success"
      );

      // Step 4: Automatically initiate download for every successfully applied resume
      for (let idx = 0; idx < successfulResults.length; idx++) {
        const item = successfulResults[idx];
        if (item.download_url) {
          if (idx > 0) {
            await new Promise(r => setTimeout(r, 350));
          }
          const a = document.createElement("a");
          a.href = item.download_url;
          a.download = item.filename || `${item.doc_id}_Improved_Resume.docx`;
          document.body.appendChild(a);
          a.click();
          a.remove();
        }
      }

      // Step 5: Automatically open the existing preview interface for the improved resume(s)
      setTimeout(() => {
        openImprovedResumePreview(successfulResults[0].doc_id);
      }, 500);
    }

    if (failedResults.length > 0) {
      showToast(`${failedResults.length} candidate file(s) failed during improvement run.`, "warning");
    }
  } catch (err) {
    if (container) {
      container.innerHTML = `<div class='card' style='border-color:var(--danger); color:var(--danger); margin-top:1rem;'>${escapeHtml(err.message)}</div>`;
    }
    showToast(err.message, "error");
  } finally {
    window._isImprovementWorkflowRunning = false;
    if (btnStart) btnStart.disabled = false;
    if (btnContinue) btnContinue.disabled = false;
    if (loadingIndicator) loadingIndicator.style.display = "none";
  }
}

function renderImprovementWorkspace(docIdArray = null) {
  const container = document.getElementById("improvement-results-area");
  if (!container) return;

  if (docIdArray && Array.isArray(docIdArray) && docIdArray.length > 0) {
    AppState.currentImprovementBatchDocIds = [...docIdArray];
  }
  const docIds = (AppState.currentImprovementBatchDocIds && AppState.currentImprovementBatchDocIds.length > 0)
    ? AppState.currentImprovementBatchDocIds
    : (docIdArray || Object.keys(AppState.improvementAnalysesByDocId || {}));
  if (!docIds.length) return;

  if (!AppState.activeImprovementDocId || !docIds.includes(AppState.activeImprovementDocId)) {
    AppState.activeImprovementDocId = docIds[0];
  }

  const candidateCardsHtml = docIds.map((id, idx) => {
    const analysis = AppState.improvementAnalysesByDocId[id];
    const pii = AppState.candidatePersonalDetails[id];
    const resumeObj = (AppState.resumes || []).find(r => r.doc_id === id);
    const name = pii?.name || resumeObj?.full_name || resumeObj?.candidate_name || `Candidate ${id}`;
    const score = analysis?.internal_match_score ?? "-";
    const isActive = id === AppState.activeImprovementDocId;
    const filename = resumeObj?.filename || `${id}.docx`;

    return `
      <div class="card" style="margin-bottom:0; padding:0.9rem; border:1.5px solid ${isActive ? 'var(--primary)' : 'var(--border-subtle)'}; background:${isActive ? 'rgba(37, 99, 235, 0.08)' : 'var(--bg-surface)'}; display:flex; flex-direction:column; justify-content:space-between; gap:0.6rem; border-radius:var(--radius-md);">
        <div>
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.4rem; margin-bottom:0.3rem;">
            <div style="font-weight:700; font-size:0.95rem; color:var(--text-main); display:flex; align-items:center; gap:0.4rem;">
              <span>${escapeHtml(name)}</span>
              ${isActive ? '<span class="file-status-badge badge-ready" style="font-size:0.68rem; background:var(--primary); color:#fff;">Active</span>' : ''}
            </div>
            <span class="file-status-badge badge-ready" style="font-size:0.75rem; font-weight:700;">${score} pts</span>
          </div>
          <div style="font-size:0.75rem; color:var(--text-muted); display:flex; gap:0.4rem; flex-wrap:wrap;">
            <span>ID: <strong>${escapeHtml(id)}</strong></span> &bull;
            <span>File: ${escapeHtml(filename)}</span>
          </div>
        </div>

        <div style="display:flex; gap:0.45rem; flex-wrap:wrap; margin-top:0.3rem; border-top:1px solid var(--border-subtle); padding-top:0.6rem;">
          <button type="button" class="btn ${isActive ? 'btn-primary' : 'btn-secondary'} btn-sm" onclick="switchImprovementCandidate('${id}')" style="flex:1; min-width:110px; font-weight:600; font-size:0.75rem;">
            ${isActive ? 'Editing Now' : 'Edit Resume'}
          </button>
          <button type="button" class="btn btn-secondary btn-sm" onclick="openResumePreview('${id}')" title="Preview Original" style="padding:0.25rem 0.55rem; display:inline-flex; align-items:center; justify-content:center;">
            ${SVG_EYE_ICON}
          </button>
          <button type="button" class="btn btn-primary btn-sm btn-cand-download" onclick="downloadImprovedWordResume('${id}')" title="Download ${escapeHtml(name)}'s Word Resume" style="font-size:0.75rem; font-weight:700; display:inline-flex; align-items:center; gap:0.3rem;">
            Download Word
          </button>
        </div>
      </div>
    `;
  }).join("");

  // Only show queue banner when MULTIPLE resumes (more than 1) are present
  const queueBannerHtml = docIds.length > 1 ? `
    <div class="card" id="improvement-queue-banner" style="margin-bottom:1.25rem; padding:1.1rem; border:1px solid var(--border-subtle); background:var(--bg-surface-subtle);">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.75rem; margin-bottom:0.85rem;">
        <div>
          <div style="display:flex; align-items:center; gap:0.5rem;">
            <h3 style="font-family:var(--font-heading); font-size:1.15rem; font-weight:800; margin:0; color:var(--text-main);">
              Improvement Queue: ${docIds.length} Candidate Resumes Ready
            </h3>
            <span class="file-status-badge badge-ready" style="font-size:0.72rem;">Multi-Resume Mode</span>
          </div>
          <p style="font-size:0.8rem; color:var(--text-muted); margin:0.2rem 0 0 0;">
            Review each candidate's tailored optimizations, edit content, and download individual or batch Word resumes.
          </p>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" onclick="downloadAllImprovedResumes()" style="font-weight:700; display:inline-flex; align-items:center; gap:0.4rem;">
          Download All ${docIds.length} Resumes (.docx)
        </button>
      </div>

      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:0.75rem;">
        ${candidateCardsHtml}
      </div>
    </div>
  ` : '';

  container.innerHTML = `
    ${queueBannerHtml}
    <!-- Candidate Personal & Contact Information strictly below the Improvement Queue and only for active resume -->
    <div id="active-candidate-personal-details-area"></div>
    <div id="active-candidate-analysis-area"></div>
  `;

  // Render personal details for the single active resume being worked on
  renderImproveCandidatePersonalDetails(AppState.activeImprovementDocId);

  const activeAnalysis = AppState.improvementAnalysesByDocId[AppState.activeImprovementDocId];
  if (activeAnalysis) {
    const targetArea = document.getElementById("active-candidate-analysis-area");
    renderImprovementAnalysis(activeAnalysis, targetArea);
    loadVersionHistory(AppState.activeImprovementDocId);
  }
}

function switchImprovementCandidate(newDocId) {
  if (!newDocId || newDocId === AppState.activeImprovementDocId) return;

  // Persist current change summary into memory
  if (AppState.activeImprovementDocId && AppState.improvementAnalysesByDocId[AppState.activeImprovementDocId]) {
    const summaryInput = document.getElementById("version-change-summary");
    if (summaryInput) {
      AppState.improvementAnalysesByDocId[AppState.activeImprovementDocId].change_summary = summaryInput.value;
    }
  }

  AppState.activeImprovementDocId = newDocId;
  const docIds = (AppState.currentImprovementBatchDocIds && AppState.currentImprovementBatchDocIds.length > 0)
    ? AppState.currentImprovementBatchDocIds
    : Object.keys(AppState.improvementAnalysesByDocId || {});
  renderImprovementWorkspace(docIds);

  if (docIds.length > 1) {
    // When multiple files are selected, jump back down to Accept All Changes and Proceed to Download
    setTimeout(() => {
      const acceptBtn = document.getElementById("btn-accept-all-bottom");
      if (acceptBtn) {
        acceptBtn.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 100);
  } else {
    // Automatically scroll up smoothly to the active candidate section when single resume
    const scrollTarget = document.getElementById("active-candidate-personal-details-area") ||
                         document.getElementById("active-candidate-analysis-area") ||
                         document.getElementById("improvement-results-area");
    if (scrollTarget) {
      scrollTarget.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
}

async function downloadAllImprovedResumes() {
  const docIds = (AppState.currentImprovementBatchDocIds && AppState.currentImprovementBatchDocIds.length > 0)
    ? AppState.currentImprovementBatchDocIds
    : Object.keys(AppState.improvementAnalysesByDocId || {});
  if (!docIds.length) return;
  showToast(`Preparing downloads for ${docIds.length} candidate resumes...`, "info");
  for (let i = 0; i < docIds.length; i++) {
    const id = docIds[i];
    await downloadImprovedWordResume(id, false);
    await new Promise(r => setTimeout(r, 600));
  }
  showToast(`✓ All ${docIds.length} candidate Word resumes downloaded!`, "success");
}

function renderImprovementAnalysis(data, containerEl = null) {
  window._currentImprovementData = data;
  window._candidateDecisions = {};

  const pii = AppState.candidatePersonalDetails[data.doc_id];
  const resumeObj = (AppState.resumes || []).find(r => r.doc_id === data.doc_id);
  const candName = pii?.name || data.candidate_personal_details?.name || resumeObj?.full_name || resumeObj?.candidate_name || data.doc_id;

  // Normalize changes list from structured response or suggested rewrites fallback
  const changes = data.changes && data.changes.length ? data.changes : (data.suggested_rewrites || []).map((s, idx) => ({
    id: `chg-${idx + 1}`,
    section: s.section || "general",
    target_element_id: `paragraph_${idx + 1}`,
    original_text: s.current_evidence || "",
    proposed_text: s.suggested_text || "",
    reason: s.rationale || "Emphasizes verified job requirements",
    supporting_evidence: [{ source: "candidate_resume", text: s.current_evidence || "Verified candidate experience" }],
    requires_user_confirmation: Boolean(s.requires_user_confirmation),
    status: "pending"
  }));
  data.changes = changes;
  changes.forEach(c => {
    window._candidateDecisions[c.id] = c.status || "pending";
  });

  // Categorize actual changes for the summary breakdown
  const summaryCat = {
    summary: [],
    experience: [],
    skills: [],
    other: []
  };

  changes.forEach(c => {
    const sec = (c.section || "").toLowerCase();
    if (sec.includes("summary") || sec.includes("profile") || sec.includes("objective")) {
      summaryCat.summary.push(c);
    } else if (sec.includes("experience") || sec.includes("work") || sec.includes("employment") || sec.includes("history")) {
      summaryCat.experience.push(c);
    } else if (sec.includes("skill") || sec.includes("competenc") || sec.includes("technolog")) {
      summaryCat.skills.push(c);
    } else {
      summaryCat.other.push(c);
    }
  });

  if (data.candidate_personal_details) {
    const pd = data.candidate_personal_details;
    const docId = data.doc_id;
    const keys = ["name", "role", "phone", "email", "location", "links"];
    keys.forEach(k => {
      const inp = document.getElementById(`inp-${docId}-${k}`) || document.getElementById(`improve-cand-${k}`);
      if (inp && pd[k] && !inp.value) inp.value = pd[k];
    });
  }

  const container = containerEl || document.getElementById("active-candidate-analysis-area") || document.getElementById("improvement-results-area");
  if (!container) return;

  container.innerHTML = `
    <!-- Top Alignment & Score Recalculator Banner -->
    <div class="improvement-score-banner" style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:1.25rem; margin-bottom:1.25rem;">
      <div style="flex:1;">
        <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.35rem;">
          <span style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.04em; color:var(--text-dim); font-weight:700;">Target Role Alignment</span>
          <span class="file-status-badge badge-ready" style="font-size:0.7rem;">${data.document_type === 'docx' ? 'DOCX (In-place layout preserved)' : 'PDF / Text Format'}</span>
        </div>
        <h2 style="font-family:var(--font-heading); font-size:1.5rem; font-weight:700; margin-bottom:0.25rem;">${escapeHtml(data.job_title)}</h2>
        <div style="font-size:0.85rem; color:var(--text-muted);">
          Active Candidate: <strong style="color:var(--primary); font-size:1.02rem;">${escapeHtml(candName)}</strong> (${escapeHtml(data.doc_id)})
        </div>
      </div>

      <!-- Recalculated Score Display -->
      <div style="text-align:right; min-width:180px;">
        <div style="display:flex; align-items:baseline; justify-content:flex-end; gap:0.4rem;">
          <div style="font-family:var(--font-heading); font-size:2.2rem; font-weight:800; color:${data.internal_match_score >= 80 ? 'var(--success)' : 'var(--primary)'};">
            <span id="recalculated-score">${data.internal_match_score}</span><span style="font-size:1.1rem; color:var(--text-dim);">/100</span>
          </div>
          <span id="recalculated-delta" style="display:none; font-size:0.75rem; font-weight:700; padding:2px 6px; border-radius:var(--radius-sm); color:#fff; background:var(--success);">+0 pts</span>
        </div>
        <div style="font-size:0.72rem; color:var(--text-dim); text-transform:uppercase; font-weight:600;">Internal Alignment Score</div>
        <div style="font-size:0.74rem; color:var(--text-muted); margin-top:2px;">Original: ${data.internal_match_score} pts</div>
      </div>
    </div>

    <!-- Honest Score Feedback Explanation -->
    <div id="score-recalculation-box" style="background:var(--bg-surface-subtle); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:0.75rem 1rem; margin-bottom:1.25rem; font-size:0.82rem; color:var(--text-main);">
      <strong style="color:var(--primary);">Dynamic Score Impact:</strong>
      <span id="score-recalculation-explanation">Review suggested changes below. Accepting verified modifications genuinely recalculates the candidate match score.</span>
    </div>

    <!-- 2.1 Categorized Resume Changes Summary (Ground Truth Evidence) -->
    <div class="card" style="margin-bottom:1.25rem; border:1px solid var(--border-subtle); background:var(--bg-surface-subtle); padding:1rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.6rem;">
        <h4 style="font-family:var(--font-heading); font-size:0.95rem; font-weight:700; margin:0; color:var(--text-main);">
          Resume Changes Summary (${changes.length} Modifications Grounded in Evidence)
        </h4>
        <span class="file-status-badge badge-ready" style="font-size:0.72rem;">✓ Fact-Grounded / No Fabrication</span>
      </div>
      <p style="font-size:0.78rem; color:var(--text-muted); margin-bottom:0.75rem;">
        Summary of actual differences between the original candidate document and recommended target role optimizations:
      </p>
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap:0.65rem;">
        <div style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:0.65rem 0.8rem; font-size:0.8rem;">
          <div style="font-weight:700; color:var(--text-main); margin-bottom:3px;">Professional Summary</div>
          <div style="color:var(--text-dim); font-size:0.74rem;">${summaryCat.summary.length ? `${summaryCat.summary.length} section(s) updated to match target role requirements.` : 'Original summary retained without modification.'}</div>
        </div>
        <div style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:0.65rem 0.8rem; font-size:0.8rem;">
          <div style="font-weight:700; color:var(--text-main); margin-bottom:3px;">Skills Reorganization</div>
          <div style="color:var(--text-dim); font-size:0.74rem;">${summaryCat.skills.length ? `${summaryCat.skills.length} core competencies reorganized and prioritized.` : 'Existing verified skill sets retained.'}</div>
        </div>
        <div style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:0.65rem 0.8rem; font-size:0.8rem;">
          <div style="font-weight:700; color:var(--text-main); margin-bottom:3px;">Work Experience Descriptions</div>
          <div style="color:var(--text-dim); font-size:0.74rem;">${summaryCat.experience.length ? `${summaryCat.experience.length} bullet description(s) improved with impact STAR verbs.` : 'Work experience statements preserved.'}</div>
        </div>
        <div style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:0.65rem 0.8rem; font-size:0.8rem;">
          <div style="font-weight:700; color:var(--text-main); margin-bottom:3px;">Formatting &amp; Wording</div>
          <div style="color:var(--text-dim); font-size:0.74rem;">${summaryCat.other.length ? `${summaryCat.other.length} phrasing and layout refinements applied.` : 'Original document layout preserved.'}</div>
        </div>
      </div>
    </div>

    <!-- Review Decision Actions Bar -->
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.6rem; margin-bottom:1rem; border-bottom:1px solid var(--border-subtle); padding-bottom:0.75rem;">
      <div>
        <h3 style="font-family:var(--font-heading); font-size:1.1rem; font-weight:700; margin:0;">Side-by-Side Recruiter Review (${changes.length} suggestions)</h3>
        <p style="font-size:0.78rem; color:var(--text-muted); margin:0;">Accept, reject, or edit proposed modifications before applying them to the Word document.</p>
      </div>
      <div style="display:flex; gap:0.4rem;">
        <button type="button" class="btn btn-primary btn-sm" onclick="bulkDecideAllChanges('accepted')">✓ Accept All Eligible</button>
        <button type="button" class="btn btn-secondary btn-sm" onclick="bulkDecideAllChanges('rejected')">✕ Reject All</button>
        <button type="button" class="btn btn-secondary btn-sm" onclick="bulkDecideAllChanges('pending')">Reset Decisions</button>
      </div>
    </div>

    <!-- Side-by-Side Comparison Cards -->
    <div id="structured-changes-container" style="display:flex; flex-direction:column; gap:1rem; margin-bottom:1.5rem;">
      ${changes.map(c => `
        <div class="card change-card" id="card-change-${c.id}" style="border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:1rem; transition:all 0.15s ease;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.75rem;">
            <div style="display:flex; align-items:center; gap:0.5rem;">
              <span class="badge" style="font-size:0.72rem; text-transform:uppercase; font-weight:700; background:var(--bg-surface-subtle); border:1px solid var(--border-subtle); color:var(--text-main);">${escapeHtml(c.section.replace('_', ' '))}</span>
              <span style="font-size:0.74rem; font-family:monospace; color:var(--text-dim);">${escapeHtml(c.target_element_id || 'paragraph')}</span>
            </div>
            <div>
              ${c.requires_user_confirmation
                ? '<span class="confirmation-badge" style="font-size:0.72rem;">Candidate Confirmation Required</span>'
                : '<span class="file-status-badge badge-ready" style="font-size:0.72rem;">✓ Verified Candidate Evidence</span>'}
            </div>
          </div>

          <!-- Side-by-Side Before & After Grid -->
          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:0.85rem; margin-bottom:0.85rem;">
            <!-- Left: Original Resume Content -->
            <div>
              <div style="font-size:0.72rem; text-transform:uppercase; font-weight:700; color:var(--text-dim); margin-bottom:0.35rem;">Original Resume Content</div>
              <div style="background:var(--bg-surface-subtle); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:0.75rem; font-size:0.82rem; line-height:1.45; color:var(--text-muted); min-height:85px;">
                ${escapeHtml(c.original_text || '(Empty or new section)')}
              </div>
            </div>

            <!-- Right: Proposed Revision (Editable) -->
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.35rem;">
                <span style="font-size:0.72rem; text-transform:uppercase; font-weight:700; color:var(--primary);">Proposed AI Revision</span>
                <span style="font-size:0.7rem; color:var(--text-dim);">Editable</span>
              </div>
              <textarea id="proposed-text-${c.id}" class="form-control" style="font-size:0.82rem; line-height:1.45; min-height:85px; font-family:inherit;" oninput="onProposedTextEdited('${c.id}')">${escapeHtml(c.proposed_text)}</textarea>
            </div>
          </div>

          <!-- Decision Action Buttons -->
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
            <div id="decision-status-label-${c.id}" style="font-size:0.78rem; font-weight:600; color:var(--text-dim);">Decision: Pending Review</div>
            <div style="display:flex; gap:0.4rem;">
              <button type="button" id="btn-accept-${c.id}" class="btn btn-secondary btn-sm" onclick="setChangeDecision('${c.id}', 'accepted')" style="font-size:0.78rem;">✓ Accept</button>
              <button type="button" id="btn-reject-${c.id}" class="btn btn-secondary btn-sm" onclick="setChangeDecision('${c.id}', 'rejected')" style="font-size:0.78rem;">✕ Reject</button>
            </div>
          </div>
        </div>
      `).join("")}
    </div>

    <!-- Big Prominent Accept All Changes Action at Bottom of Changes List -->
    <div style="margin: 1.5rem 0 2rem 0; padding: 1.25rem 1.5rem; background: var(--bg-surface-subtle); border: 2px dashed var(--primary-border); border-radius: var(--radius-md); text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.04);">
      <div style="font-size:0.88rem; color:var(--text-muted); margin-bottom:0.75rem;">
        Approve all proposed enhancements across skills, experience, and formatting to reach the target <strong>90-95 alignment score</strong>.
      </div>
      <div style="display:inline-flex; align-items:center; justify-content:center; gap:0.75rem; flex-wrap:wrap;">
        <button type="button" class="btn btn-primary" id="btn-accept-all-bottom" onclick="bulkAcceptAllAndProceed()" style="padding: 0.95rem 2.8rem; font-size: 1.15rem; font-weight: 800; border-radius: var(--radius-md); box-shadow: 0 4px 20px rgba(79, 70, 229, 0.4); display: inline-flex; align-items: center; gap: 0.65rem; cursor: pointer; transition: all 0.2s ease;">
          <span style="font-size:1.35rem;">✓</span> Accept All Changes and Proceed
        </button>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          id="btn-preview-improved-resume"
          onclick="previewCurrentImprovedResume('${data.doc_id}')"
          ${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? '' : 'disabled'}
          style="padding:0.6rem 1.15rem; font-size:0.85rem; font-weight:700; border-radius:var(--radius-md); display:inline-flex; align-items:center; gap:0.35rem; cursor:${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? 'pointer' : 'not-allowed'}; opacity:${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? '1' : '0.5'};"
          title="${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? 'Preview Improved Resume' : 'Preview available after clicking Accept All Changes and Proceed'}"
        >
          Preview
        </button>
      </div>
    </div>

    <!-- 2.2 Recruiter Action Controls Bar (Centered: Compare Versions, Word Editor, Download) -->
    <div class="card" style="margin-top:1.5rem; margin-bottom:1rem; border:1px solid var(--border-subtle); padding:1.25rem; display:flex; justify-content:center; align-items:center;">
      <div style="display:flex; align-items:center; justify-content:center; gap:1rem; flex-wrap:wrap;">
        <button
          type="button"
          class="btn btn-secondary"
          id="btn-compare-versions"
          onclick="openVersionComparisonModal('${data.doc_id}')"
          ${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? '' : 'disabled'}
          style="font-weight:600; font-size:1rem; padding:0.75rem 1.6rem; border-radius:var(--radius-md); cursor:${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? 'pointer' : 'not-allowed'}; opacity:${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? '1' : '0.5'};"
          title="${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? 'Compare Original vs Improved' : 'Compare available after clicking Accept All Changes and Proceed'}"
        >
          Compare Versions
        </button>
        <button type="button" class="btn btn-primary" id="btn-open-wordcraft-editor" onclick="openWordCraftEditorModal('${data.doc_id}')" style="font-weight:600; font-size:1rem; padding:0.75rem 1.6rem; border-radius:var(--radius-md); background:linear-gradient(135deg, #2563eb, #1d4ed8); border:1px solid #3b82f6; color:#fff; box-shadow:0 2px 6px rgba(37,99,235,0.35);" title="Open full MS Word-compatible WordCraft editor">
          Word Editor
        </button>
        <button
          type="button"
          class="btn btn-secondary"
          id="btn-download-improved"
          onclick="handleImprovementDownloadClick('${data.doc_id}')"
          ${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? '' : 'disabled'}
          style="font-weight:600; font-size:1rem; padding:0.75rem 1.6rem; border-radius:var(--radius-md); cursor:${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? 'pointer' : 'not-allowed'}; opacity:${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? '1' : '0.5'}; transition: all 0.25s ease;"
          title="${Boolean(AppState.appliedImprovements && AppState.appliedImprovements[data.doc_id]) ? 'Download Improved Resume' : 'Download available after clicking Accept All Changes and Proceed'}"
        >
          Download
        </button>
      </div>
    </div>

    <!-- Hidden state inputs for revised document and summary -->
    <input type="hidden" id="version-change-summary" value="${data.change_summary ? data.change_summary.replace(/"/g, '&quot;') : 'Target-aligned resume optimization with verified STAR metrics.'}">
    <textarea id="version-revised-content" style="display:none;">${escapeHtml(data.improved_resume_text || data.original_text_preview || '')}</textarea>
  `;

  // Auto-apply personal details
  applyPersonalDetailsToDraft(false);
}

function applyPersonalDetailsToDraft(showToastNotice = false) {
  const docId = AppState.activeImprovementDocId || window._currentImprovementData?.doc_id;
  if (!docId) return;

  const details = AppState.candidatePersonalDetails[docId] || window._currentImprovementData?.candidate_personal_details || {};
  const keys = ["name", "role", "phone", "email", "location", "links"];
  keys.forEach(k => {
    const inp = document.getElementById(`inp-${docId}-${k}`) || document.getElementById(`improve-cand-${k}`);
    if (inp && details[k] && !inp.value) {
      inp.value = details[k];
    }
  });

  if (showToastNotice) {
    showToast("Candidate contact details updated.", "info");
  }
}

async function openResumeInLocalWord(docId) {
  const targetDocId = docId ||
    AppState.previewList?.[AppState.previewIndex]?.doc_id ||
    AppState.selectedResumeDocId ||
    window._currentImprovementData?.doc_id;
  if (!targetDocId) {
    showToast("Please select a candidate resume first", "warning");
    return;
  }
  openWordCraftEditorModal(targetDocId);
}

let _currentCompareViewMode = "preview";
let _currentComparePreviewDoc = "revised"; // "revised" or "original"

function setCompareViewMode(mode) {
  _currentCompareViewMode = (mode === "side-by-side" || mode === "split") ? "side-by-side" : "preview";
  const grid = document.getElementById("compare-grid-container");
  const origPanel = document.getElementById("compare-original-panel");
  const revPanel = document.getElementById("compare-revised-panel");
  const btnSide = document.getElementById("btn-compare-mode-side") || document.getElementById("btn-compare-view-split");
  const btnPrev = document.getElementById("btn-compare-mode-preview") || document.getElementById("btn-compare-view-preview");
  const docSelector = document.getElementById("compare-doc-selector");

  if (!grid || !origPanel || !revPanel) return;

  if (_currentCompareViewMode === "side-by-side") {
    grid.classList.remove("mode-preview");
    origPanel.style.display = "";
    revPanel.style.display = "";
    if (btnSide) {
      btnSide.className = "btn btn-primary btn-sm";
    }
    if (btnPrev) {
      btnPrev.className = "btn btn-secondary btn-sm";
    }
    if (docSelector) docSelector.style.display = "none";
  } else {
    grid.classList.add("mode-preview");
    if (btnSide) {
      btnSide.className = "btn btn-secondary btn-sm";
    }
    if (btnPrev) {
      btnPrev.className = "btn btn-primary btn-sm";
    }
    if (docSelector) docSelector.style.display = "inline-flex";
    setComparePreviewDoc(_currentComparePreviewDoc);
  }
}

function setComparePreviewDoc(docType) {
  _currentComparePreviewDoc = docType;
  const origPanel = document.getElementById("compare-original-panel");
  const revPanel = document.getElementById("compare-revised-panel");
  const btnRevised = document.getElementById("btn-compare-doc-revised");
  const btnOrig = document.getElementById("btn-compare-doc-original");

  if (!origPanel || !revPanel) return;

  if (_currentCompareViewMode === "preview") {
    if (docType === "revised") {
      origPanel.style.display = "none";
      revPanel.style.display = "";
      if (btnRevised) btnRevised.className = "btn btn-primary btn-sm";
      if (btnOrig) btnOrig.className = "btn btn-secondary btn-sm";
    } else {
      origPanel.style.display = "";
      revPanel.style.display = "none";
      if (btnRevised) btnRevised.className = "btn btn-secondary btn-sm";
      if (btnOrig) btnOrig.className = "btn btn-primary btn-sm";
    }
  }
}

function toggleComparePreviewDoc() {
  setComparePreviewDoc(_currentComparePreviewDoc === "revised" ? "original" : "revised");
}

function renderComparisonChangesBar(changes) {
  const countEl = document.getElementById("compare-changes-count");
  const pillsEl = document.getElementById("compare-changes-pills");
  if (!pillsEl) return;

  const validChanges = (changes || []).filter(c => c && (c.original_text || c.proposed_text));
  if (countEl) {
    countEl.textContent = `${validChanges.length} Changes Made`;
  }

  if (validChanges.length === 0) {
    pillsEl.innerHTML = `<span style="font-size:0.78rem; color:var(--text-muted);">No specific text replacements detected.</span>`;
    return;
  }

  pillsEl.innerHTML = validChanges.map((c, idx) => {
    const label = c.section || c.category || `Change #${idx + 1}`;
    const cleanLabel = escapeHtml(label.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase()));
    return `
      <button type="button" class="compare-change-pill" data-change-id="${c.id}" onclick="jumpToCompareChange('${c.id}')" title="${escapeHtml(c.explanation || 'Click to locate change in documents')}">
        <span style="font-weight:700;">#${idx + 1}</span> ${cleanLabel}
      </button>
    `;
  }).join("");
}

function jumpToCompareChange(changeId) {
  const origMark = document.getElementById(`compare-orig-${changeId}`);
  const revMark = document.getElementById(`compare-rev-${changeId}`);
  const origBody = document.getElementById("compare-original-body");
  const revBody = document.getElementById("compare-revised-body");

  // Activate pill
  document.querySelectorAll(".compare-change-pill").forEach(p => {
    p.classList.toggle("active", p.dataset.changeId === String(changeId));
  });

  if (origMark && origBody) {
    origMark.scrollIntoView({ behavior: "smooth", block: "center" });
    origMark.classList.add("compare-highlight-pulse");
    setTimeout(() => origMark.classList.remove("compare-highlight-pulse"), 2500);
  }
  if (revMark && revBody) {
    revMark.scrollIntoView({ behavior: "smooth", block: "center" });
    revMark.classList.add("compare-highlight-pulse");
    setTimeout(() => revMark.classList.remove("compare-highlight-pulse"), 2500);
  }
}

function highlightTextInElement(container, rawText, markerClass, markId) {
  if (!container || !rawText || typeof rawText !== "string") return false;
  const targetText = rawText.trim();
  if (!targetText || targetText.length < 3) return false;

  // 1. Direct text node search
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
  let node;
  const nodesToProcess = [];
  while ((node = walker.nextNode())) {
    if (node.parentElement && (node.parentElement.tagName === "MARK" || node.parentElement.tagName === "SCRIPT" || node.parentElement.tagName === "STYLE")) {
      continue;
    }
    nodesToProcess.push(node);
  }

  for (const textNode of nodesToProcess) {
    const val = textNode.nodeValue;
    const idx = val.indexOf(targetText);
    if (idx !== -1) {
      const parent = textNode.parentNode;
      const before = val.substring(0, idx);
      const matched = val.substring(idx, idx + targetText.length);
      const after = val.substring(idx + targetText.length);

      const mark = document.createElement("mark");
      mark.className = markerClass;
      if (markId) mark.id = markId;
      mark.dataset.changeId = markId ? markId.replace(/compare-(orig|rev)-/, "") : "";
      mark.textContent = matched;

      const frag = document.createDocumentFragment();
      if (before) frag.appendChild(document.createTextNode(before));
      frag.appendChild(mark);
      if (after) frag.appendChild(document.createTextNode(after));

      parent.replaceChild(frag, textNode);
      return true;
    }
  }

  // 2. Normalized block search (in case of extra spaces, newlines, or multiple spans)
  const blocks = container.querySelectorAll("p, div, li, tr, span");
  const normalizedTarget = targetText.replace(/\s+/g, " ").trim();
  for (const block of blocks) {
    if (block.querySelector("mark")) continue;
    const blockText = (block.textContent || "").replace(/\s+/g, " ");
    if (blockText.includes(normalizedTarget) && normalizedTarget.length > 5) {
      const prefix = targetText.slice(0, Math.min(35, targetText.length)).trim();
      const walker2 = document.createTreeWalker(block, NodeFilter.SHOW_TEXT, null, false);
      let tNode;
      while ((tNode = walker2.nextNode())) {
        const tVal = tNode.nodeValue;
        const pIdx = tVal.indexOf(prefix);
        if (pIdx !== -1) {
          const parent = tNode.parentNode;
          const mark = document.createElement("mark");
          mark.className = markerClass;
          if (markId) mark.id = markId;
          mark.dataset.changeId = markId ? markId.replace(/compare-(orig|rev)-/, "") : "";
          mark.textContent = tVal.substring(pIdx, Math.min(tVal.length, pIdx + targetText.length));

          const before = tVal.substring(0, pIdx);
          const after = tVal.substring(pIdx + mark.textContent.length);
          const frag = document.createDocumentFragment();
          if (before) frag.appendChild(document.createTextNode(before));
          frag.appendChild(mark);
          if (after) frag.appendChild(document.createTextNode(after));
          parent.replaceChild(frag, tNode);
          return true;
        }
      }
    }
  }

  // 3. Fallback for distinct sentence segment
  const firstSentence = targetText.split(/[.\n]/)[0]?.trim();
  if (firstSentence && firstSentence.length >= 10 && firstSentence !== targetText) {
    for (const textNode of nodesToProcess) {
      if (!textNode.parentNode) continue;
      const val = textNode.nodeValue;
      const idx = val.indexOf(firstSentence);
      if (idx !== -1) {
        const parent = textNode.parentNode;
        const before = val.substring(0, idx);
        const matched = val.substring(idx, idx + firstSentence.length);
        const after = val.substring(idx + firstSentence.length);

        const mark = document.createElement("mark");
        mark.className = markerClass;
        if (markId) mark.id = markId;
        mark.dataset.changeId = markId ? markId.replace(/compare-(orig|rev)-/, "") : "";
        mark.textContent = matched;

        const frag = document.createDocumentFragment();
        if (before) frag.appendChild(document.createTextNode(before));
        frag.appendChild(mark);
        if (after) frag.appendChild(document.createTextNode(after));

        parent.replaceChild(frag, textNode);
        return true;
      }
    }
  }

  return false;
}

AppState.compareOriginalPages = [];
AppState.compareRevisedPages = [];
AppState.comparePageIndex = 0;
AppState.compareTotalPages = 1;

function downloadCurrentCompareDocument() {
  let docId = null;
  let filename = null;
  let versionId = null;
  if (AppState.compareList && AppState.compareList[AppState.compareIndex]) {
    const item = AppState.compareList[AppState.compareIndex];
    docId = item.doc_id;
    filename = item.original_filename || `${docId}.docx`;
    versionId = item.version_id || null;
  } else if (window._currentImprovementData && window._currentImprovementData.doc_id) {
    docId = window._currentImprovementData.doc_id;
    filename = `${docId}.docx`;
  }
  if (!docId && !versionId) {
    showToast("No active document to download.", "warning");
    return;
  }

  const downloadUrl = versionId ? `/api/versions/${encodeURIComponent(versionId)}/file` : `/api/resumes/${encodeURIComponent(docId)}/file`;
  const a = document.createElement("a");
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function renderCompareTabsBar(activeIdx) {
  const tabsBar = document.getElementById("compare-improved-tabs-bar");
  if (!tabsBar) return;
  if (!AppState.compareList || AppState.compareList.length === 0) {
    tabsBar.style.display = "none";
    tabsBar.innerHTML = "";
    return;
  }

  tabsBar.style.display = "flex";
  tabsBar.innerHTML = AppState.compareList.map((item, idx) => {
    const isActive = idx === activeIdx;
    const viewLabel = item.view_label || `View ${idx + 1}`;
    const filename = item.filename || item.original_filename || `Resume_${idx + 1}.docx`;
    return `
      <button
        type="button"
        class="preview-improved-tab-btn ${isActive ? 'active' : ''}"
        onclick="switchImprovedCompareIndex(${idx})"
        title="Compare improved resume: ${escapeHtml(filename)}"
      >
        <span class="tab-view-num">${escapeHtml(viewLabel)} &mdash;</span>
        <span class="tab-filename" style="max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(filename)}</span>
      </button>
    `;
  }).join("");
}

async function switchImprovedCompareIndex(newIdx) {
  if (!AppState.compareList || newIdx < 0 || newIdx >= AppState.compareList.length) return;
  AppState.compareIndex = newIdx;
  renderCompareTabsBar(newIdx);
  await renderVersionComparisonAtIndex(newIdx);
}

async function openVersionComparisonModal(targetDocId = null) {
  const currentDocId = targetDocId || AppState.activeImprovementDocId || window._currentImprovementData?.doc_id;
  const appliedList = getAppliedImprovementsList();

  if (!appliedList || appliedList.length === 0) {
    showToast("Compare Versions is available only after changes are applied via 'Accept All Changes and Proceed'.", "warning");
    return;
  }

  AppState.compareList = appliedList.map((entry, index) => {
    const viewLabel = `View ${index + 1}`;
    const displayFilename = entry.filename || `${entry.doc_id}_Improved.docx`;
    return {
      doc_id: entry.doc_id,
      library_doc_id: entry.library_doc_id || null,
      version_id: entry.version_id,
      full_name: entry.full_name || displayFilename,
      original_filename: displayFilename,
      filename: displayFilename,
      view_label: viewLabel
    };
  });

  let initialIdx = 0;
  if (currentDocId) {
    const foundIdx = AppState.compareList.findIndex(item => item.doc_id === currentDocId);
    if (foundIdx !== -1) initialIdx = foundIdx;
  }

  AppState.compareIndex = initialIdx;
  renderCompareTabsBar(initialIdx);
  openModal("version-compare-modal");
  await renderVersionComparisonAtIndex(initialIdx);
}

async function renderVersionComparisonAtIndex(idx) {
  if (!AppState.compareList || !AppState.compareList[idx]) return;
  const item = AppState.compareList[idx];
  const docId = item.doc_id;
  const versionId = item.version_id || AppState.appliedImprovements?.[docId]?.version_id || window._lastSavedVersionIdByDoc?.[docId];
  const displayFilename = item.filename || `${docId}_Improved.docx`;

  let data = AppState.improvementAnalysesByDocId?.[docId] || window._currentImprovementData;
  if (!data || data.doc_id !== docId) {
    if (AppState.improvementAnalysesByDocId?.[docId]) {
      data = AppState.improvementAnalysesByDocId[docId];
    } else {
      data = {
        doc_id: docId,
        original_text_preview: "Original candidate resume",
        improved_resume_text: "Target-aligned resume optimization",
        changes: []
      };
    }
  }

  const origBadge = document.getElementById("compare-original-badge");
  const revBadge = document.getElementById("compare-revised-badge");
  const origBody = document.getElementById("compare-original-body");
  const revBody = document.getElementById("compare-revised-body");

  // Automatically display side-by-side (Left: Original, Right: Improved) without clutter
  setCompareViewMode("side-by-side");

  const origResumeObj = (AppState.resumes || []).find(r => r.doc_id === docId);
  const origFilename = origResumeObj?.original_filename || `${docId}.docx`;

  if (origBadge) origBadge.textContent = `${origFilename} (Original Document)`;
  if (revBadge) revBadge.textContent = `${item.view_label || ('View ' + (idx + 1))} — ${displayFilename} (Improved Document)`;

  if (origBody) {
    origBody.innerHTML = `
      <div style="text-align:center; padding:3rem 1rem; color:var(--text-muted);">
        <div class="spinner" style="margin:0 auto 1rem;"></div>
        <div>Loading original candidate file...</div>
      </div>
    `;
    origBody.scrollTop = 0;
  }
  if (revBody) {
    revBody.innerHTML = `
      <div style="text-align:center; padding:3rem 1rem; color:var(--text-muted);">
        <div class="spinner" style="margin:0 auto 1rem;"></div>
        <div>Loading improved document format...</div>
      </div>
    `;
    revBody.scrollTop = 0;
  }

  // Populate changes bar if present
  const allChanges = data.changes || [];
  renderComparisonChangesBar(allChanges);

  try {
    // 1. Fetch and render actual original document
    let origLoaded = false;
    try {
      const origPreview = await API.getResumePreview(docId);
      const isPdf = !!(origPreview && origPreview.is_pdf && origPreview.pdf_stream_url);
      const isOrigDocx = (origPreview?.is_docx === true) ||
                         (origPreview?.filename && origPreview.filename.toLowerCase().endsWith(".docx")) ||
                         (origPreview?.mime_type && origPreview.mime_type.includes("wordprocessingml"));

      if (isPdf) {
        origBody.innerHTML = `
          <iframe src="${origPreview.pdf_stream_url}" style="width:100%; height:100%; min-height:680px; border:none; border-radius:4px; background:#fff;"></iframe>
        `;
        AppState.compareOriginalPages = [];
        origLoaded = true;
      } else if (isOrigDocx && window.docx) {
        try {
          const origUrl = origPreview.docx_stream_url || origPreview.stream_url || `/api/resumes/${encodeURIComponent(docId)}/stream`;
          const origResp = await fetch(origUrl);
          if (!origResp.ok) throw new Error(`HTTP ${origResp.status} loading original candidate Word document`);
          const origBuffer = await origResp.arrayBuffer();
          origBody.innerHTML = "";
          await window.docx.renderAsync(origBuffer, origBody, null, {
            className: "docx",
            inWrapper: true,
            ignoreWidth: false,
            ignoreHeight: false,
            breakPages: true,
            useBase64URL: true
          });
          AppState.compareOriginalPages = [];
          origLoaded = true;
        } catch (docxErr) {
          console.warn("Original docx render fallback:", docxErr);
          const fallbackContent = (origPreview && origPreview.pages && origPreview.pages.length > 0)
            ? origPreview.pages[0]
            : `<div class="compare-doc-page">${data.original_text_preview || 'Original candidate resume'}</div>`;
          origBody.innerHTML = `<div class="compare-doc-page">${fallbackContent}</div>`;
          origLoaded = true;
        }
      } else {
        AppState.compareOriginalPages = (origPreview && origPreview.pages && origPreview.pages.length > 0)
          ? origPreview.pages
          : [`<div class="compare-doc-page">${data.original_text_preview || 'Original candidate resume'}</div>`];
        origBody.innerHTML = AppState.compareOriginalPages[0] || "";
        origLoaded = true;
      }
    } catch (e) {
      console.warn("Error fetching original preview:", e);
      origBody.innerHTML = `<div class="compare-doc-page">${escapeHtml(data.original_text_preview || 'Original candidate resume')}</div>`;
    }
    origBody.scrollTop = 0;

    // 2. Fetch and render actual improved Word document (.docx) using versionId
    const revisedHtml = data.improved_resume_text || data.original_text_preview || "";
    let revLoaded = false;
    if (versionId && window.docx) {
      try {
        const revUrl = `/api/versions/${encodeURIComponent(versionId)}/file`;
        const revResp = await fetch(revUrl);
        if (revResp.ok) {
          const revBuffer = await revResp.arrayBuffer();
          revBody.innerHTML = "";
          await window.docx.renderAsync(revBuffer, revBody, null, {
            className: "docx",
            inWrapper: true,
            ignoreWidth: false,
            ignoreHeight: false,
            breakPages: true,
            useBase64URL: true
          });
          revLoaded = true;
        }
      } catch (revDocxErr) {
        console.warn("Revised docx render fallback:", revDocxErr);
      }
    }
    if (!revLoaded) {
      revBody.innerHTML = `<div class="compare-doc-page">${revisedHtml}</div>`;
    }
    revBody.scrollTop = 0;

    // Fit previews smoothly to available column width
    fitCompareDocxPanels();

    // 3. Apply visual difference markers: Red in Original, Green in Revised
    setTimeout(() => {
      allChanges.forEach(c => {
        if (c.original_text) {
          highlightTextInElement(origBody, c.original_text, "compare-highlight-del", `compare-orig-${c.id}`);
        }
        if (c.proposed_text) {
          highlightTextInElement(revBody, c.proposed_text, "compare-highlight-add", `compare-rev-${c.id}`);
        }
      });
      fitCompareDocxPanels();
      // Setup synchronized scrolling
      setupCompareSyncScroll();
    }, 150);

    const pageControls = document.getElementById("compare-page-controls");
    if (pageControls) pageControls.style.display = "none";
  } catch (err) {
    console.error("renderVersionComparisonAtIndex error:", err);
    if (origBody && !origBody.textContent.trim()) origBody.innerHTML = `<div class="compare-doc-page">${escapeHtml(data.original_text_preview || 'Original candidate resume')}</div>`;
    if (revBody && !revBody.textContent.trim()) revBody.innerHTML = `<div class="compare-doc-page">${escapeHtml(data.improved_resume_text || data.original_text_preview || 'Improved candidate resume')}</div>`;
  }
}

function renderCompareDocumentPages(pageIdx, isPdfOrig = false) {
  const origBody = document.getElementById("compare-original-body");
  const revBody = document.getElementById("compare-revised-body");
  const origPages = AppState.compareOriginalPages || [];
  const revPages = AppState.compareRevisedPages || [];
  const total = AppState.compareTotalPages || 1;

  if (origBody && !isPdfOrig && origPages[pageIdx]) {
    origBody.innerHTML = `<div class="compare-doc-page">${origPages[pageIdx]}</div>`;
    origBody.scrollTop = 0;
  }
  if (revBody && revPages[pageIdx]) {
    revBody.innerHTML = `<div class="compare-doc-page">${revPages[pageIdx]}</div>`;
    revBody.scrollTop = 0;
  }

  const pageControls = document.getElementById("compare-page-controls");
  const pageCounter = document.getElementById("compare-page-counter");
  const pagePrev = document.getElementById("compare-page-prev");
  const pageNext = document.getElementById("compare-page-next");

  if (pageControls) {
    pageControls.style.display = total > 1 ? "flex" : "none";
    if (pageCounter) pageCounter.textContent = `Page ${pageIdx + 1} of ${total}`;
    if (pagePrev) pagePrev.disabled = (pageIdx <= 0);
    if (pageNext) pageNext.disabled = (pageIdx >= total - 1 || total <= 1);
  }
}

function navigateComparePages(direction) {
  const total = AppState.compareTotalPages || 1;
  const nextIdx = AppState.comparePageIndex + direction;
  if (nextIdx >= 0 && nextIdx < total) {
    AppState.comparePageIndex = nextIdx;
    renderCompareDocumentPages(nextIdx, !AppState.compareOriginalPages.length);
  }
}

function fitCompareDocxPanels() {
  const origBody = document.getElementById("compare-original-body");
  const revBody = document.getElementById("compare-revised-body");

  [origBody, revBody].forEach(body => {
    if (!body) return;
    const availableWidth = body.clientWidth - 32;
    if (availableWidth <= 100) return;

    const sections = body.querySelectorAll(".docx-wrapper > section.docx, .docx-viewer-wrapper > section.docx-viewer, section.docx, section.docx-viewer, .compare-doc-page");
    sections.forEach(sec => {
      let naturalWidth = parseFloat(sec.dataset.naturalWidth);
      if (!naturalWidth || isNaN(naturalWidth)) {
        naturalWidth = sec.offsetWidth || 816;
        if (naturalWidth < 600) naturalWidth = 816;
        sec.dataset.naturalWidth = naturalWidth;
      }

      const targetScale = Math.min(1.0, availableWidth / naturalWidth);
      if (targetScale < 0.99) {
        sec.style.zoom = targetScale;
      } else {
        sec.style.zoom = "1";
      }
    });
  });
}


window.addEventListener("resize", () => {
  if (document.getElementById("version-compare-modal")?.classList.contains("active")) {
    fitCompareDocxPanels();
  }
});

function setupCompareSyncScroll() {
  const origEl = document.getElementById("compare-original-body");
  const revEl = document.getElementById("compare-revised-body");
  if (!origEl || !revEl) return;

  let activeScroller = null;
  let scrollTimer = null;

  function sync(source, target) {
    if (activeScroller && activeScroller !== source) return;
    activeScroller = source;

    if (scrollTimer) clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => {
      activeScroller = null;
    }, 50);

    requestAnimationFrame(() => {
      const sourceMax = source.scrollHeight - source.clientHeight;
      const targetMax = target.scrollHeight - target.clientHeight;
      if (sourceMax > 0 && targetMax > 0) {
        const ratio = source.scrollTop / sourceMax;
        target.scrollTop = Math.round(ratio * targetMax);
      } else {
        target.scrollTop = source.scrollTop;
      }
    });
  }

  origEl.onscroll = () => sync(origEl, revEl);
  revEl.onscroll = () => sync(revEl, origEl);
}

// ==========================================
// WORDCRAFT FULL WORD PROCESSOR INTEGRATION
// ==========================================
window._currentWordCraftDocId = null;

async function openCandidateFolder(docId) {
  const targetDocId = docId || window._currentWordCraftDocId || AppState.activeImprovementDocId || window._currentImprovementData?.doc_id;
  if (!targetDocId) {
    showToast("Please select a candidate resume first.", "warning");
    return;
  }
  try {
    showToast("Opening candidate folder in Windows Explorer...", "info");
    const res = await API.openFolder(targetDocId);
    if (res && res.message) {
      showToast(res.message, "success");
    } else {
      showToast("Opened candidate folder in Windows Explorer.", "success");
    }
  } catch (err) {
    showToast(`Could not open folder: ${err.message}`, "error");
  }
}

function openWordCraftEditorModal(docId) {
  const targetDocId = docId || AppState.activeImprovementDocId || (window._currentImprovementData ? window._currentImprovementData.doc_id : null) || AppState.selectedResumeDocId;
  window._currentWordCraftDocId = targetDocId;

  // Update candidate name / doc details in header
  const subtitleEl = document.getElementById("wordcraft-modal-subtitle");
  let candName = "Candidate Resume";
  const resDoc = AppState.resumes?.find(r => r.doc_id === targetDocId) || AppState.previewList?.find(r => r.doc_id === targetDocId);
  if (resDoc && (resDoc.candidate_name || resDoc.full_name)) {
    candName = resDoc.candidate_name || resDoc.full_name;
  } else if (window._currentImprovementData && window._currentImprovementData.candidate_name) {
    candName = window._currentImprovementData.candidate_name;
  }
  if (subtitleEl) {
    subtitleEl.textContent = `Document: ${candName} (.docx) · Full Word Processor (Ribbon, Tables, Styles, Layout, Track Changes)`;
  }

  // Load WordCraft iframe pointing to the selected candidate's document
  const versionId = window._lastSavedVersionIdByDoc?.[targetDocId] || window._currentImprovementData?.version_id;
  let docUrl = "";
  if (versionId) {
    docUrl = `/api/versions/${encodeURIComponent(versionId)}/file`;
  } else if (targetDocId) {
    docUrl = `/api/resumes/${encodeURIComponent(targetDocId)}/stream`;
  }
  const safeFilename = `${candName.replace(/[^a-zA-Z0-9_-]/g, '_')}_resume.docx`;
  const targetSrc = docUrl 
    ? `/static/wordcraft/index.html?doc_url=${encodeURIComponent(docUrl)}&filename=${encodeURIComponent(safeFilename)}&t=${Date.now()}`
    : `/static/wordcraft/index.html`;

  const iframe = document.getElementById("wordcraft-iframe");
  if (iframe) {
    iframe.src = targetSrc;
    setTimeout(() => {
      try {
        if (iframe.contentWindow && docUrl) {
          iframe.contentWindow.postMessage({ type: 'LOAD_DOCX', url: docUrl, filename: safeFilename }, '*');
        }
      } catch (e) {}
    }, 1500);
  }

  openModal("wordcraft-editor-modal");
}

function closeWordCraftEditorModal() {
  closeModal("wordcraft-editor-modal");
}

async function getWordCraftEditedBlob() {
  const iframe = document.getElementById("wordcraft-iframe");
  if (!iframe || !iframe.contentWindow) return null;

  // 1. Direct access if already captured
  if (iframe.contentWindow._lastExportedDocxBlob) {
    return iframe.contentWindow._lastExportedDocxBlob;
  }

  // 2. Trigger save in WordCraft canvas
  try {
    iframe.contentWindow.postMessage({ type: "TRIGGER_SAVE" }, "*");
  } catch (e) {}

  // Wait briefly for WordCraft export handler to run
  await new Promise(r => setTimeout(r, 600));
  if (iframe.contentWindow._lastExportedDocxBlob) {
    return iframe.contentWindow._lastExportedDocxBlob;
  }

  // 3. Fallback: fetch currently loaded file stream
  const targetDocId = window._currentWordCraftDocId || AppState.activeImprovementDocId;
  const versionId = window._lastSavedVersionIdByDoc?.[targetDocId] || window._currentImprovementData?.version_id;
  const url = versionId ? `/api/versions/${encodeURIComponent(versionId)}/file` : (targetDocId ? `/api/resumes/${encodeURIComponent(targetDocId)}/stream` : null);
  if (url) {
    try {
      const resp = await fetch(url);
      if (resp.ok) return await resp.blob();
    } catch (e) {}
  }
  return null;
}

async function saveWordCraftDocument() {
  const docId = window._currentWordCraftDocId || AppState.activeImprovementDocId;
  if (!docId) {
    showToast("No active document selected to save", "warning");
    return;
  }

  const btn = document.getElementById("wordcraft-save-btn");
  const origText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "Saving...";
  }

  try {
    const blob = await getWordCraftEditedBlob();
    if (!blob) {
      showToast("Could not retrieve document from editor", "error");
      return;
    }

    const res = await API.saveEditorDocx(docId, blob, "Direct edits saved via WordCraft Editor");
    if (res && res.version_id) {
      if (!window._lastSavedVersionIdByDoc) window._lastSavedVersionIdByDoc = {};
      window._lastSavedVersionIdByDoc[docId] = res.version_id;
      if (window._currentImprovementData) {
        window._currentImprovementData.version_id = res.version_id;
      }
      showToast(`Document changes saved successfully as revision ${res.version_id}!`, "success");
      loadVersionHistory(docId);
      await refreshDataCaches();
    }
  } catch (err) {
    showToast(`Error saving editor changes: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  }
}

async function saveWordCraftToLibrary() {
  const docId = window._currentWordCraftDocId || AppState.activeImprovementDocId;
  if (!docId) {
    showToast("No active document selected", "warning");
    return;
  }

  const btn = document.getElementById("wordcraft-save-library-btn");
  const origText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "Saving to Library...";
  }

  try {
    const blob = await getWordCraftEditedBlob();
    const res = await API.saveEditorToLibrary(docId, blob, `Saved from WordCraft editor based on ${docId}`);
    if (res && res.doc_id) {
      showToast(`Saved as new document ${res.doc_id} in Resume Library & IKM!`, "success");
      await loadLibrary();
      await refreshDataCaches();
    }
  } catch (err) {
    showToast(`Error saving to Library: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  }
}

async function downloadWordCraftDocument() {
  const docId = window._currentWordCraftDocId || AppState.activeImprovementDocId;
  if (!docId) {
    showToast("No active document selected to download", "warning");
    return;
  }

  showToast("Preparing document download...", "info");
  const blob = await getWordCraftEditedBlob();
  if (blob) {
    const iframe = document.getElementById("wordcraft-iframe");
    const fn = (iframe && iframe.contentWindow && iframe.contentWindow._lastExportedFilename) || `${docId}_edited_resume.docx`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fn;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    showToast("Downloaded latest edited Word (.docx) file!", "success");
    return;
  }

  // If a saved version exists, download the latest saved revision
  const versionId = window._lastSavedVersionIdByDoc?.[docId] || window._currentImprovementData?.version_id;
  if (versionId) {
    const a = document.createElement("a");
    a.href = `/api/versions/${encodeURIComponent(versionId)}/file`;
    a.download = `${docId}_${versionId}.docx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    showToast("Downloaded latest saved Word revision!", "success");
    return;
  }

  // Fallback to streaming original candidate docx
  const a = document.createElement("a");
  a.href = `/api/resumes/${encodeURIComponent(docId)}/stream`;
  a.download = `${docId}_resume.docx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function reloadWordCraftFrame() {
  const iframe = document.getElementById("wordcraft-iframe");
  if (iframe) {
    iframe.src = "/static/wordcraft/index.html?t=" + Date.now();
  }
}

function loadWordCraftSample() {
  const iframe = document.getElementById("wordcraft-iframe");
  if (iframe) {
    iframe.src = "/static/wordcraft/index.html?sample";
  }
}

function loadWordCraftBlank() {
  const iframe = document.getElementById("wordcraft-iframe");
  if (iframe) {
    iframe.src = "/static/wordcraft/index.html";
  }
}

function onProposedTextEdited(changeId) {
  if (!window._currentImprovementData?.changes) return;
  const c = window._currentImprovementData.changes.find(item => item.id === changeId);
  if (c) {
    const val = document.getElementById(`proposed-text-${changeId}`)?.value.trim() || "";
    c.proposed_text = val;
    // If currently accepted, re-trigger score calculation
    if (window._candidateDecisions?.[changeId] === "accepted") {
      setChangeDecision(changeId, "accepted");
    }
  }
}

async function setChangeDecision(changeId, decision) {
  if (!window._currentImprovementData) return;
  window._candidateDecisions[changeId] = decision;

  const card = document.getElementById(`card-change-${changeId}`);
  const statusLabel = document.getElementById(`decision-status-label-${changeId}`);
  const btnAccept = document.getElementById(`btn-accept-${changeId}`);
  const btnReject = document.getElementById(`btn-reject-${changeId}`);

  if (card) {
    if (decision === 'accepted') {
      card.style.borderColor = 'var(--success)';
      card.style.background = 'rgba(16, 185, 129, 0.05)';
      card.style.opacity = '1';
      if (statusLabel) {
        statusLabel.textContent = "Decision: ✓ Accepted";
        statusLabel.style.color = "var(--success)";
      }
      if (btnAccept) {
        btnAccept.className = "btn btn-primary btn-sm";
      }
      if (btnReject) {
        btnReject.className = "btn btn-secondary btn-sm";
      }
    } else if (decision === 'rejected') {
      card.style.borderColor = 'var(--border-subtle)';
      card.style.background = 'transparent';
      card.style.opacity = '0.65';
      if (statusLabel) {
        statusLabel.textContent = "Decision: ✕ Rejected";
        statusLabel.style.color = "var(--danger)";
      }
      if (btnAccept) {
        btnAccept.className = "btn btn-secondary btn-sm";
      }
      if (btnReject) {
        btnReject.className = "btn btn-danger btn-sm";
      }
    } else {
      card.style.borderColor = 'var(--border-subtle)';
      card.style.background = 'transparent';
      card.style.opacity = '1';
      if (statusLabel) {
        statusLabel.textContent = "Decision: Pending Review";
        statusLabel.style.color = "var(--text-dim)";
      }
      if (btnAccept) btnAccept.className = "btn btn-secondary btn-sm";
      if (btnReject) btnReject.className = "btn btn-secondary btn-sm";
    }
  }

  // Update synchronized full text preview
  updateDraftPreviewFromDecisions();

  // Recalculate score honestly
  await triggerRecalculateScore();
}

async function bulkDecideAllChanges(decision, forceAll = false) {
  if (!window._currentImprovementData?.changes) return;
  const changes = window._currentImprovementData.changes;

  for (const c of changes) {
    // If accepting all, skip any marked as user-confirmation required unless explicitly confirmed or forceAll is true
    if (decision === 'accepted' && c.requires_user_confirmation && !forceAll) {
      continue;
    }
    window._candidateDecisions[c.id] = decision;

    const card = document.getElementById(`card-change-${c.id}`);
    const statusLabel = document.getElementById(`decision-status-label-${c.id}`);
    const btnAccept = document.getElementById(`btn-accept-${c.id}`);
    const btnReject = document.getElementById(`btn-reject-${c.id}`);

    if (card) {
      if (decision === 'accepted') {
        card.style.borderColor = 'var(--success)';
        card.style.background = 'rgba(16, 185, 129, 0.05)';
        card.style.opacity = '1';
        if (statusLabel) {
          statusLabel.textContent = "Decision: ✓ Accepted";
          statusLabel.style.color = "var(--success)";
        }
        if (btnAccept) btnAccept.className = "btn btn-primary btn-sm";
        if (btnReject) btnReject.className = "btn btn-secondary btn-sm";
      } else if (decision === 'rejected') {
        card.style.borderColor = 'var(--border-subtle)';
        card.style.background = 'transparent';
        card.style.opacity = '0.65';
        if (statusLabel) {
          statusLabel.textContent = "Decision: ✕ Rejected";
          statusLabel.style.color = "var(--danger)";
        }
        if (btnAccept) btnAccept.className = "btn btn-secondary btn-sm";
        if (btnReject) btnReject.className = "btn btn-danger btn-sm";
      } else {
        card.style.borderColor = 'var(--border-subtle)';
        card.style.background = 'transparent';
        card.style.opacity = '1';
        if (statusLabel) {
          statusLabel.textContent = "Decision: Pending Review";
          statusLabel.style.color = "var(--text-dim)";
        }
        if (btnAccept) btnAccept.className = "btn btn-secondary btn-sm";
        if (btnReject) btnReject.className = "btn btn-secondary btn-sm";
      }
    }
  }

  updateDraftPreviewFromDecisions();
  await triggerRecalculateScore();
  showToast(decision === 'accepted' ? (forceAll ? "✓ All changes accepted (including confirmation-required)" : "Accepted all eligible verified changes") : `Changes updated to ${decision}`, "info");
}

async function bulkAcceptAllAndProceed() {
  const docId = AppState.activeImprovementDocId || window._currentImprovementData?.doc_id;
  if (!docId) {
    showToast("Please select a candidate resume first", "warning");
    return;
  }

  const btn = document.getElementById("btn-accept-all-bottom");
  const origBtnContent = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-spinner"></span> Applying & Persisting Changes...`;
  }

  try {
    // 1. Accept all changes
    await bulkDecideAllChanges('accepted', true);
    showToast("Applying verified changes and updating document...", "info");

    // 2. Persist to IKM without directly triggering file download
    const res = await downloadImprovedWordResume(docId, true, false);
    if (!res) return;

    // 3. Multi-file queue scrolling:
    // Maintain scrollback to queue banner when navigating between files,
    // EXCEPT when the current file is the LAST file in the selected batch!
    const docIds = (AppState.currentImprovementBatchDocIds && AppState.currentImprovementBatchDocIds.length > 0)
      ? AppState.currentImprovementBatchDocIds
      : Object.keys(AppState.improvementAnalysesByDocId || {});
    if (docIds.length > 1) {
      const currentIndex = docIds.indexOf(docId);
      const isLastFile = (currentIndex !== -1 && currentIndex === docIds.length - 1);
      if (!isLastFile) {
        setTimeout(() => {
          const queueEl = document.getElementById("improvement-queue-banner");
          if (queueEl) {
            queueEl.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }, 250);
      }
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origBtnContent;
    }
  }
}

async function bulkAcceptAllAndProceedToDownload() {
  return bulkAcceptAllAndProceed();
}

function handleImprovementDownloadClick(targetDocId = null) {
  const currentDocId = targetDocId || AppState.activeImprovementDocId || window._currentImprovementData?.doc_id;
  const batchDocIds = (AppState.currentImprovementBatchDocIds && AppState.currentImprovementBatchDocIds.length > 0)
    ? AppState.currentImprovementBatchDocIds
    : Object.keys(AppState.improvementAnalysesByDocId || {});

  // When multiple resumes are selected in the workflow:
  if (batchDocIds.length > 1) {
    renderMultiDownloadModal();
    openModal("multi-download-modal");
  } else {
    // Single resume selected: download improved DOCX directly
    downloadSingleAppliedDocx(currentDocId);
  }
}

function renderMultiDownloadModal() {
  const container = document.getElementById("multi-download-candidates-list");
  if (!container) return;

  const appliedEntries = Object.values(AppState.appliedImprovements || {});
  const batchDocIds = AppState.currentImprovementBatchDocIds || [];
  const relevantEntries = batchDocIds.length > 0
    ? appliedEntries.filter(e => batchDocIds.includes(e.doc_id))
    : appliedEntries;

  if (relevantEntries.length === 0) {
    container.innerHTML = `
      <div style="text-align:center; padding:2rem 1rem; color:var(--text-muted);">
        No candidates have successfully applied improvements yet.<br>Click <strong>Accept All Changes and Proceed</strong> on candidates first.
      </div>
    `;
    return;
  }

  container.innerHTML = relevantEntries.map((entry, index) => {
    const candName = escapeHtml(entry.full_name || entry.candidate_name || `Candidate ${index + 1}`);
    const filename = escapeHtml(entry.filename || `${entry.doc_id}_Improved.docx`);
    return `
      <div style="display:flex; align-items:center; justify-content:space-between; padding:0.9rem 1.15rem; background:var(--bg-surface-subtle); border:1px solid var(--border-subtle); border-radius:var(--radius-md); gap:1rem;">
        <div style="min-width:0; flex:1;">
          <div style="font-weight:700; font-size:0.96rem; color:var(--text-main); margin-bottom:0.25rem;">${candName}</div>
          <div style="font-size:0.8rem; color:var(--text-muted); text-overflow:ellipsis; overflow:hidden; white-space:nowrap;" title="${filename}">${filename}</div>
        </div>
        <button type="button" class="btn btn-primary btn-sm" onclick="downloadSingleAppliedDocx('${entry.doc_id}')" style="display:inline-flex; align-items:center; gap:0.4rem; font-weight:600; padding:0.45rem 0.95rem; flex-shrink:0;">
          <span style="font-size:0.9rem;">⬇</span> Download
        </button>
      </div>
    `;
  }).join("");
}

function downloadSingleAppliedDocx(docId) {
  const entry = AppState.appliedImprovements?.[docId];
  if (!entry) {
    showToast("Please apply changes first before downloading", "warning");
    return;
  }
  const downloadUrl = entry.download_url || (entry.version_id ? `/api/versions/${encodeURIComponent(entry.version_id)}/file` : `/api/improvements/export/word/${encodeURIComponent(docId)}`);
  const filename = entry.filename || `${docId}_Improved.docx`;
  const a = document.createElement("a");
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  showToast(`Downloading improved resume: ${filename}`, "success");
}

function previewCurrentImprovedResume(targetDocId = null) {
  const currentDocId = targetDocId || AppState.activeImprovementDocId || window._currentImprovementData?.doc_id;
  const appliedList = getAppliedImprovementsList();
  if (!appliedList || appliedList.length === 0) {
    showToast("Preview is available only after changes are applied via 'Accept All Changes and Proceed'.", "warning");
    return;
  }
  openImprovedResumePreview(currentDocId);
}

function openImprovedResumePreview(preferredDocId = null) {
  const appliedList = getAppliedImprovementsList();
  if (!appliedList || appliedList.length === 0) {
    showToast("No resume improvements have been applied yet. Click 'Accept All Changes and Proceed' first.", "warning");
    return;
  }

  AppState.isImprovedPreviewMode = true;
  AppState.previewList = appliedList.map((entry, index) => {
    const viewLabel = `View ${index + 1}`;
    const displayFilename = entry.filename || `${entry.doc_id}_Improved.docx`;
    return {
      doc_id: entry.library_doc_id || entry.doc_id,
      original_doc_id: entry.doc_id,
      version_id: entry.version_id,
      full_name: entry.full_name || displayFilename,
      original_filename: displayFilename,
      filename: displayFilename,
      view_label: viewLabel,
      is_improved: true
    };
  });

  let initialIdx = 0;
  if (preferredDocId) {
    const foundIdx = AppState.previewList.findIndex(item =>
      item.original_doc_id === preferredDocId || item.doc_id === preferredDocId
    );
    if (foundIdx !== -1) initialIdx = foundIdx;
  }

  AppState.previewIndex = initialIdx;
  renderImprovedTabsBar(initialIdx);
  renderResumePreviewAtIndex(initialIdx);
  openModal("resume-preview-modal");
}

function renderImprovedTabsBar(activeIdx) {
  const tabsBar = document.getElementById("preview-improved-tabs-bar");
  if (!tabsBar) return;
  if (!AppState.isImprovedPreviewMode || !AppState.previewList || AppState.previewList.length === 0) {
    tabsBar.style.display = "none";
    tabsBar.innerHTML = "";
    return;
  }

  tabsBar.style.display = "flex";
  tabsBar.innerHTML = AppState.previewList.map((item, idx) => {
    const isActive = idx === activeIdx;
    const viewLabel = item.view_label || `View ${idx + 1}`;
    const filename = item.filename || item.original_filename || `Resume_${idx + 1}.docx`;
    return `
      <button
        type="button"
        class="preview-improved-tab-btn ${isActive ? 'active' : ''}"
        onclick="switchImprovedPreviewIndex(${idx})"
        title="View improved resume: ${escapeHtml(filename)}"
      >
        <span class="tab-view-num">${escapeHtml(viewLabel)} &mdash;</span>
        <span class="tab-filename" style="max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(filename)}</span>
      </button>
    `;
  }).join("");
}

function switchImprovedPreviewIndex(newIdx) {
  if (!AppState.previewList || newIdx < 0 || newIdx >= AppState.previewList.length) return;
  AppState.previewIndex = newIdx;
  renderResumePreviewAtIndex(newIdx);
  renderImprovedTabsBar(newIdx);
}

async function bulkAcceptAllAndScrollDown() {
  return bulkAcceptAllAndProceedToDownload();
}

function updateDraftPreviewFromDecisions() {
  const textarea = document.getElementById("version-revised-content");
  if (!textarea || !window._currentImprovementData) return;

  const data = window._currentImprovementData;
  let text = data.improved_resume_text || data.original_text_preview || "";

  // Apply accepted changes to draft text
  (data.changes || []).forEach(c => {
    if (window._candidateDecisions?.[c.id] === 'accepted') {
      const orig = (c.original_text || "").trim();
      const prop = (document.getElementById(`proposed-text-${c.id}`)?.value || c.proposed_text || "").trim();
      if (orig && prop && text.includes(orig)) {
        text = text.replace(orig, prop);
      }
    }
  });

  textarea.value = text;
}

async function triggerRecalculateScore() {
  if (!window._currentImprovementData) return;
  const data = window._currentImprovementData;

  const acceptedChanges = [];
  (data.changes || []).forEach(c => {
    if (window._candidateDecisions?.[c.id] === 'accepted') {
      const editedText = document.getElementById(`proposed-text-${c.id}`)?.value.trim() || c.proposed_text;
      acceptedChanges.push({
        ...c,
        proposed_text: editedText,
        status: 'accepted'
      });
    }
  });

  const docId = data.doc_id;
  const jobId = data.job_id;
  const customJd = document.getElementById("improve-custom-jd")?.value.trim() || null;

  try {
    const res = await API.recalculateScore(docId, acceptedChanges, jobId, customJd);
    const scoreEl = document.getElementById("recalculated-score");
    const deltaEl = document.getElementById("recalculated-delta");
    const explEl = document.getElementById("score-recalculation-explanation");
    if (scoreEl) scoreEl.textContent = res.revised_score;
    if (deltaEl) {
      if (res.score_difference > 0) {
        deltaEl.style.display = "inline-block";
        deltaEl.textContent = `+${res.score_difference} pts`;
      } else {
        deltaEl.style.display = "none";
      }
    }
    if (explEl) explEl.textContent = res.explanation;
  } catch (err) {
    console.error("Score recalculation request failed:", err);
  }
}

async function saveRevisedVersionDraft(docId) {
  const summaryInput = document.getElementById("version-change-summary");
  const contentInput = document.getElementById("version-revised-content");

  const summaryVal = (summaryInput?.value || "").trim() || window._currentImprovementData?.change_summary || "Target-aligned resume optimization with verified STAR metrics.";
  const contentVal = (contentInput?.value || "").trim() || window._currentImprovementData?.improved_resume_text || window._currentImprovementData?.original_text_preview || "";

  if (!summaryVal && !contentVal) {
    showToast("Please provide both change summary and content", "warning");
    return;
  }

  const piiFromState = AppState.candidatePersonalDetails[docId] || {};
  const personalDetails = {
    name: document.getElementById(`inp-${docId}-name`)?.value.trim() || document.getElementById("improve-cand-name")?.value.trim() || piiFromState.name || "",
    role: document.getElementById(`inp-${docId}-role`)?.value.trim() || document.getElementById("improve-cand-role")?.value.trim() || piiFromState.role || "",
    phone: document.getElementById(`inp-${docId}-phone`)?.value.trim() || document.getElementById("improve-cand-phone")?.value.trim() || piiFromState.phone || "",
    email: document.getElementById(`inp-${docId}-email`)?.value.trim() || document.getElementById("improve-cand-email")?.value.trim() || piiFromState.email || "",
    location: document.getElementById(`inp-${docId}-location`)?.value.trim() || document.getElementById("improve-cand-location")?.value.trim() || piiFromState.location || "",
    links: document.getElementById(`inp-${docId}-links`)?.value.trim() || document.getElementById("improve-cand-links")?.value.trim() || piiFromState.links || ""
  };

  const approvedChanges = [];
  (window._currentImprovementData?.changes || []).forEach(c => {
    if (window._candidateDecisions?.[c.id] === 'accepted') {
      const edited = document.getElementById(`proposed-text-${c.id}`)?.value.trim() || c.proposed_text;
      approvedChanges.push({
        ...c,
        proposed_text: edited,
        status: 'accepted'
      });
    }
  });

  try {
    const res = await API.saveDraft(docId, summaryVal, contentVal, personalDetails, approvedChanges);
    if (res && res.actual_score !== undefined) {
      const scoreEl = document.getElementById("recalculated-score");
      const deltaEl = document.getElementById("recalculated-delta");
      const explEl = document.getElementById("score-recalculation-explanation");
      if (scoreEl) scoreEl.textContent = res.actual_score;
      if (deltaEl) {
        if (res.score_delta > 0) {
          deltaEl.style.display = "inline-block";
          deltaEl.textContent = `+${res.score_delta} pts`;
        } else {
          deltaEl.style.display = "none";
        }
      }
      if (explEl && res.score_explanation) explEl.textContent = res.score_explanation;
    }
    showToast(`Draft saved successfully as ${res.doc_id} in Resume Library & IKM!`, "success");
    loadVersionHistory(docId);
    await loadLibrary();
    await refreshDataCaches();
  } catch (err) {
    showToast(`Error saving draft: ${err.message}`, "error");
  }
}

async function downloadImprovedWordResume(docId, showToastNotice = true, shouldDownload = true) {
  if (!docId) {
    showToast("Please select a candidate resume first", "warning");
    return;
  }

  // Prevent rapid double-clicks causing database concurrency conflicts
  if (window._isDownloadingWord) {
    showToast("Word document generation is in progress, please wait a moment...", "info");
    return;
  }

  const summaryInput = document.getElementById("version-change-summary");
  const contentInput = document.getElementById("version-revised-content");
  const jobSelect = document.getElementById("improve-job-select");

  const summary = summaryInput ? summaryInput.value.trim() : "Updated Professional Word Resume";
  const content = contentInput ? contentInput.value.trim() : "";
  const targetRole = (jobSelect && jobSelect.options[jobSelect.selectedIndex]?.text) || "Senior Technical Professional";

  const btn = document.getElementById("btn-accept-all-bottom") || document.getElementById("btn-agent-download-word");
  const origBtnText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = shouldDownload
      ? `<span class="btn-spinner"></span> Generating & Downloading Resume...`
      : `<span class="btn-spinner"></span> Applying & Persisting Changes...`;
  }

  window._isDownloadingWord = true;

  try {
    const piiFromState = AppState.candidatePersonalDetails[docId] || {};
    const personalDetails = {
      name: document.getElementById(`inp-${docId}-name`)?.value.trim() || document.getElementById("improve-cand-name")?.value.trim() || piiFromState.name || "",
      role: document.getElementById(`inp-${docId}-role`)?.value.trim() || document.getElementById("improve-cand-role")?.value.trim() || piiFromState.role || "",
      phone: document.getElementById(`inp-${docId}-phone`)?.value.trim() || document.getElementById("improve-cand-phone")?.value.trim() || piiFromState.phone || "",
      email: document.getElementById(`inp-${docId}-email`)?.value.trim() || document.getElementById("improve-cand-email")?.value.trim() || piiFromState.email || "",
      location: document.getElementById(`inp-${docId}-location`)?.value.trim() || document.getElementById("improve-cand-location")?.value.trim() || piiFromState.location || "",
      links: document.getElementById(`inp-${docId}-links`)?.value.trim() || document.getElementById("improve-cand-links")?.value.trim() || piiFromState.links || ""
    };

    const approvedChanges = [];
    (window._currentImprovementData?.changes || []).forEach(c => {
      if (window._candidateDecisions?.[c.id] === 'accepted') {
        const edited = document.getElementById(`proposed-text-${c.id}`)?.value.trim() || c.proposed_text;
        approvedChanges.push({
          ...c,
          proposed_text: edited,
          status: 'accepted'
        });
      }
    });

    const res = await API.generateWordResume(docId, content, summary, targetRole, personalDetails, approvedChanges);
    if (res && res.actual_score !== undefined) {
      const scoreEl = document.getElementById("recalculated-score");
      const deltaEl = document.getElementById("recalculated-delta");
      const explEl = document.getElementById("score-recalculation-explanation");
      if (scoreEl) scoreEl.textContent = res.actual_score;
      if (deltaEl) {
        if (res.score_delta > 0) {
          deltaEl.style.display = "inline-block";
          deltaEl.textContent = `+${res.score_delta} pts`;
        } else {
          deltaEl.style.display = "none";
        }
      }
      if (explEl && res.score_explanation) explEl.textContent = res.score_explanation;
    }

    if (res && res.version_id) {
      if (!window._lastSavedVersionIdByDoc) window._lastSavedVersionIdByDoc = {};
      window._lastSavedVersionIdByDoc[docId] = res.version_id;
      if (res.library_doc_id) {
        if (!window._lastSavedLibraryDocIdByDoc) window._lastSavedLibraryDocIdByDoc = {};
        window._lastSavedLibraryDocIdByDoc[docId] = res.library_doc_id;
      }
      if (window._currentImprovementData) {
        window._currentImprovementData.version_id = res.version_id;
      }

      // Record applied status for this specific file
      const candidateInfo = (AppState.resumes || []).find(r => r.doc_id === docId);
      const pii = AppState.candidatePersonalDetails?.[docId];
      const fullName = pii?.name || candidateInfo?.full_name || candidateInfo?.candidate_name || res.filename || docId;

      if (!AppState.appliedImprovements) AppState.appliedImprovements = {};
      AppState.appliedImprovements[docId] = {
        doc_id: docId,
        library_doc_id: res.library_doc_id || null,
        version_id: res.version_id,
        filename: res.filename || `${docId}_Improved.docx`,
        full_name: fullName,
        download_url: res.download_url,
        timestamp: Date.now()
      };

      // Enable the preview button immediately if on current active candidate
      const previewBtn = document.getElementById("btn-preview-improved-resume");
      if (previewBtn && (AppState.activeImprovementDocId === docId || !AppState.activeImprovementDocId)) {
        previewBtn.disabled = false;
        previewBtn.style.opacity = "1";
        previewBtn.style.cursor = "pointer";
        previewBtn.title = "Preview Improved Resume";
      }

      // Enable the compare button immediately if on current active candidate
      const compareBtn = document.getElementById("btn-compare-versions");
      if (compareBtn && (AppState.activeImprovementDocId === docId || !AppState.activeImprovementDocId)) {
        compareBtn.disabled = false;
        compareBtn.style.opacity = "1";
        compareBtn.style.cursor = "pointer";
        compareBtn.title = "Compare Original vs Improved";
      }

      // Enable the download button immediately if on current active candidate and glow
      const downloadBtn = document.getElementById("btn-download-improved");
      if (downloadBtn && (AppState.activeImprovementDocId === docId || !AppState.activeImprovementDocId)) {
        downloadBtn.disabled = false;
        downloadBtn.style.opacity = "1";
        downloadBtn.style.cursor = "pointer";
        downloadBtn.title = "Download Improved Resume";

        // Briefly highlight/glow download button for approximately 0.5-1s
        downloadBtn.classList.remove("btn-download-glow");
        void downloadBtn.offsetWidth; // trigger reflow
        downloadBtn.classList.add("btn-download-glow");
        setTimeout(() => {
          downloadBtn.classList.remove("btn-download-glow");
        }, 850);
      }
    }

    if (shouldDownload) {
      const a = document.createElement("a");
      a.href = res.download_url;
      a.download = res.filename || `${docId}_Improved_Resume.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();

      if (showToastNotice) {
        showToast("Downloaded improved Word (.docx) resume with layout preserved!", "success");
      }
    } else if (showToastNotice) {
      showToast("✓ All changes successfully applied and persisted! You can now Preview, Compare, or Download.", "success");
    }
    loadVersionHistory(docId);
    await refreshDataCaches();
    if (typeof loadLibrary === "function") {
      loadLibrary().catch(() => {});
    }
    return res;
  } catch (err) {
    showToast(`Error generating Word resume: ${err.message}`, "error");
    return null;
  } finally {
    window._isDownloadingWord = false;
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origBtnText;
    }
  }
}

function quickDownloadWordForSelectedResume() {
  const docId = AppState.selectedResumeDocId;
  if (!docId) {
    showToast("Please select a resume first", "warning");
    return;
  }
  downloadImprovedWordResume(docId);
}

async function loadVersionHistory(docId) {
  const historyList = document.getElementById("improvement-version-history");
  if (!historyList) return;

  try {
    const versions = await API.getVersionHistory(docId);
    if (!versions.length) {
      historyList.innerHTML = "<p class='text-dim text-center' style='padding:1rem;'>No revisions saved yet. Original resume is preserved intact.</p>";
      return;
    }
    historyList.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:0.8rem;">
        ${versions.map(v => `
          <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:8px; padding:0.9rem; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <strong>${v.version_id}</strong>
              <div style="font-size:0.78rem; color:var(--text-muted);">${v.change_summary}</div>
              <div style="font-size:0.72rem; color:var(--text-dim); margin-top:2px;">Created by ${v.created_by} on ${formatDate(v.created_at)}</div>
            </div>
            <a href="/api/versions/${v.version_id}/file" download class="btn btn-secondary btn-sm">Download Word (.docx)</a>
          </div>
        `).join("")}
      </div>
    `;
  } catch (err) {
    historyList.innerHTML = "<p class='text-dim'>Failed to load version history.</p>";
  }
}

// ==========================================
// 4. FOLLOW-UPS WORKFLOW
// ==========================================
function applyInactivityThreshold() {
  const input = document.getElementById("inactivity-threshold-input");
  const errorEl = document.getElementById("inactivity-validation-msg");
  if (!input) return;

  const valStr = input.value.trim();
  const valNum = Number(valStr);

  if (!valStr || isNaN(valNum) || !Number.isInteger(valNum) || valNum < 1 || valNum > 365) {
    if (errorEl) {
      errorEl.textContent = "Please enter a valid whole number between 1 and 365 days.";
      errorEl.style.display = "block";
    }
    input.focus();
    return;
  }

  if (errorEl) {
    errorEl.textContent = "";
    errorEl.style.display = "none";
  }

  AppState.inactivityThreshold = valNum;
  localStorage.setItem("talentpulse_inactivity_threshold", String(valNum));
  loadFollowups();
}

async function loadFollowups() {
  const inactInput = document.getElementById("inactivity-threshold-input");
  if (inactInput) {
    inactInput.value = AppState.inactivityThreshold;
  }
  const days = AppState.inactivityThreshold;

  const tbody = document.getElementById("followups-table-body");
  if (!tbody) return;
  tbody.innerHTML = "<tr><td colspan='7' class='text-center text-muted'>Scanning recruiter workflow states...</td></tr>";

  try {
    const followups = await API.getFollowups(days);
    AppState.allFollowups = followups || [];

    const pendingOrDue = (AppState.allFollowups).filter(f => (f.is_overdue || f.status === 'pending_review' || f.is_stale) && f.status !== 'hired').length;
    const fuBadge = document.getElementById("badge-followups-count");
    if (fuBadge) fuBadge.textContent = pendingOrDue;

    filterFollowups();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='7' class='text-danger'>Error: ${err.message}</td></tr>`;
  }
}

function filterFollowups() {
  const tbody = document.getElementById("followups-table-body");
  if (!tbody) return;

  const searchTerm = (document.getElementById("followups-search-input")?.value || "").toLowerCase().trim();
  const statusFilter = (document.getElementById("followups-status-filter")?.value || "").trim().toLowerCase();
  const sortOrder = (document.getElementById("followups-sort-select")?.value || "").trim();
  const days = AppState.inactivityThreshold;

  const all = AppState.allFollowups || [];
  let filtered = all.filter(item => {
    // 1. Status Filter
    if (statusFilter && item.status.toLowerCase() !== statusFilter) {
      return false;
    }

    // 2. Search Text
    if (!searchTerm) return true;
    const searchTarget = [
      item.doc_id,
      item.full_name,
      item.candidate_name,
      item.candidate_label,
      item.status,
      item.assigned_to,
      item.last_action_type,
      item.notes,
      item.suggested_action
    ].filter(Boolean).join(" ").toLowerCase();

    return searchTarget.includes(searchTerm);
  });

  // Alphabetical sort by full name
  if (sortOrder === "name_asc") {
    filtered.sort((a, b) => {
      const nameA = (a.full_name || a.candidate_name || a.candidate_label || a.doc_id || "").toLowerCase();
      const nameB = (b.full_name || b.candidate_name || b.candidate_label || b.doc_id || "").toLowerCase();
      return nameA.localeCompare(nameB);
    });
  } else if (sortOrder === "name_desc") {
    filtered.sort((a, b) => {
      const nameA = (a.full_name || a.candidate_name || a.candidate_label || a.doc_id || "").toLowerCase();
      const nameB = (b.full_name || b.candidate_name || b.candidate_label || b.doc_id || "").toLowerCase();
      return nameB.localeCompare(nameA);
    });
  }

  renderFollowupsRows(filtered, days);
}

function renderFollowupsRows(followups, days) {
  const tbody = document.getElementById("followups-table-body");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!followups.length) {
    const statusFilter = document.getElementById("followups-status-filter")?.value;
    const msg = statusFilter 
      ? `No candidates found with status "${statusFilter}".` 
      : "No candidates matching the current filter criteria.";
    tbody.innerHTML = `<tr><td colspan='7' class='text-center text-dim' style='padding:2rem;'>${msg}</td></tr>`;
    return;
  }

  followups.forEach(item => {
    const tr = document.createElement("tr");

    // Determine status badge class and text
    let statusBadgeHtml = "";
    if (item.status === "hired") {
      statusBadgeHtml = `<span class="file-status-badge badge-hired">HIRED</span>`;
    } else if (item.is_overdue) {
      statusBadgeHtml = `
        <span class="file-status-badge badge-failed">${escapeHtml(item.status.toUpperCase())}</span>
        <span style="color:var(--danger); font-size:0.72rem; display:block; font-weight:700;">OVERDUE</span>
      `;
    } else if (item.status === "shortlisted" || item.status === "reviewed") {
      statusBadgeHtml = `<span class="file-status-badge badge-ready">${escapeHtml(item.status.toUpperCase())}</span>`;
    } else {
      statusBadgeHtml = `<span class="file-status-badge badge-processing">${escapeHtml(item.status.toUpperCase())}</span>`;
    }

    const displayName = item.full_name || item.candidate_name || item.candidate_label || "N/A";

    tr.innerHTML = `
      <td><button type="button" class="doc-id-link" onclick="openCandidateRemarksModal('${item.doc_id}')" title="Click to view remarks and activity history for ${item.doc_id}"><strong>${item.doc_id}</strong></button></td>
      <td><strong>${escapeHtml(displayName)}</strong></td>
      <td>
        ${statusBadgeHtml}
        ${item.email_sent ? `<span class="file-status-badge badge-ready" style="font-size:0.68rem; margin-top:3px; display:inline-block;" title="Escalation email sent to ${item.email_sent_to}">✓ Emailed</span>` : ''}
      </td>
      <td>
        <span style="font-weight:600; color:${item.status === 'hired' ? 'var(--success)' : (item.days_inactive >= 90 ? 'var(--danger)' : (item.days_inactive >= days ? 'var(--warning)' : 'var(--text-main)'))};">
          ${item.days_inactive} days
        </span>
        ${item.status !== 'hired' && item.days_inactive >= days ? `<span style="font-size:0.7rem; color:var(--warning); display:block;">(Inactive &gt; ${days}d)</span>` : ''}
        ${item.status !== 'hired' && item.days_inactive >= 90 ? '<span style="font-size:0.7rem; color:var(--danger); display:block;">(3+ months)</span>' : ''}
      </td>
      <td>
        <div style="font-weight:600; font-size:0.82rem; color:var(--text-main);">${formatDateTime(item.last_opened_at || item.last_action_at)}</div>
        <div style="font-size:0.72rem; color:var(--text-dim);">${item.last_action_type || 'Active'} by ${item.assigned_to || 'admin'}</div>
      </td>
      <td>${formatDate(item.next_action_at)}</td>
      <td>
        <div style="display:flex; flex-wrap:wrap; gap:0.35rem; align-items:center;">
          <button class="btn btn-secondary btn-sm" onclick="viewCandidateDetailsModal('${item.doc_id}')" title="View candidate and contact details" style="padding:0.3rem 0.55rem; display:inline-flex; align-items:center; justify-content:center;">${SVG_EYE_ICON}</button>
          <button class="btn btn-secondary btn-sm" onclick="openActionModal('${item.doc_id}')" title="Record recruiter action & notes">Action</button>
          <button class="btn btn-secondary btn-sm" onclick="openEscalationEmailModal('${item.doc_id}', ${item.days_inactive})" title="Send escalation email with resume attached">Email</button>
          <button class="btn btn-danger btn-sm" onclick="confirmDeleteResume('${item.doc_id}', '${escapeHtml(displayName)}')" title="Permanently delete this candidate">Delete</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function submitHireActionFromModal() {
  const docId = document.getElementById("action-modal-doc-id").value;
  const notes = document.getElementById("action-notes-input").value.trim() || "Candidate marked as Hired via recruiter action box.";
  try {
    await API.recordAction(docId, "hired", "hired", notes);
    showToast(`Candidate ${docId} successfully marked as Hired`, "success");
    closeModal("record-action-modal");
    await refreshDataCaches();
    await loadFollowups();
    if (AppState.currentTab === "library") await loadLibrary();
    await loadDashboard();
  } catch (err) {
    showToast(`Error recording Hired action: ${err.message}`, "error");
  }
}

async function openCandidateRemarksModal(docId) {
  API.recordResumeOpened(docId).catch(() => {});
  const modal = document.getElementById("candidate-remarks-modal");
  const banner = document.getElementById("remarks-candidate-banner");
  const listContainer = document.getElementById("remarks-history-list");
  const docIdInput = document.getElementById("remark-modal-doc-id");
  const remarkText = document.getElementById("new-remark-textarea");
  const statusSelect = document.getElementById("new-remark-status");

  if (docIdInput) docIdInput.value = docId;
  if (remarkText) remarkText.value = "";
  if (statusSelect) statusSelect.value = "";

  const candidate = (AppState.allFollowups || []).find(f => f.doc_id === docId) || 
                    (AppState.resumes || []).find(r => r.doc_id === docId);

  const filename = candidate?.original_filename || candidate?.candidate_label || docId;
  const currentStatus = candidate?.status || candidate?.latest_status || "pending_review";
  const statusBadge = currentStatus === "hired" 
    ? '<span class="file-status-badge badge-hired">HIRED</span>'
    : `<span class="file-status-badge badge-processing">${currentStatus.replace('_', ' ').toUpperCase()}</span>`;

  if (banner) {
    banner.innerHTML = `
      <div>
        <div style="font-size:0.8rem; color:var(--text-dim); text-transform:uppercase;">Candidate Record</div>
        <strong style="font-size:1.05rem; color:var(--text-main);">${docId}</strong>
        <span style="font-size:0.84rem; color:var(--text-muted); margin-left:8px;">(${filename})</span>
      </div>
      <div>
        ${statusBadge}
      </div>
    `;
  }

  if (listContainer) {
    listContainer.innerHTML = "<div class='text-center text-muted' style='padding:1.5rem;'>Loading candidate remarks & action history...</div>";
  }

  openModal("candidate-remarks-modal");

  try {
    const actions = await API.getResumeActions(docId);
    renderCandidateRemarksList(actions, currentStatus);
  } catch (err) {
    if (listContainer) {
      listContainer.innerHTML = `<div class='text-danger' style='padding:1rem;'>Failed to load remarks: ${err.message}</div>`;
    }
  }
}

function renderCandidateRemarksList(actions, currentStatus) {
  const listContainer = document.getElementById("remarks-history-list");
  if (!listContainer) return;

  if (!actions || !actions.length) {
    listContainer.innerHTML = `
      <div style="text-align:center; padding:1.8rem; color:var(--text-dim); background:rgba(255,255,255,0.015); border-radius:6px;">
        No recruiter remarks recorded yet. Add the first observation or note above!
      </div>
    `;
    return;
  }

  listContainer.innerHTML = actions.map(act => {
    const timeStr = act.action_at ? formatDateTime(act.action_at) : "Recently";
    const statusLabel = (act.status || "reviewed").toUpperCase();
    const actionTypeLabel = (act.action_type || "action").replace("_", " ").toUpperCase();
    const isHired = act.status === "hired" || act.action_type === "hired";
    const badgeStyle = isHired 
      ? 'background:rgba(16,185,129,0.2); color:#10b981; border:1px solid rgba(16,185,129,0.4); font-size:0.7rem; font-weight:700;'
      : 'font-size:0.7rem;';

    return `
      <div class="remark-item">
        <div class="remark-header">
          <div>
            <span class="remark-author">${act.owner_id || 'Recruiter'}</span>
            <span class="file-status-badge ${isHired ? 'badge-hired' : 'badge-processing'}" style="${badgeStyle}; margin-left:6px;">${actionTypeLabel} (${statusLabel})</span>
          </div>
          <span class="remark-time">${timeStr}</span>
        </div>
        <div class="remark-content">${escapeHtml(act.notes || "No additional remarks")}</div>
        ${act.next_action_at ? `<div style="margin-top:0.35rem; font-size:0.74rem; color:#fde68a;">Next action scheduled: ${formatDate(act.next_action_at)}</div>` : ''}
      </div>
    `;
  }).join("");
}

async function submitCandidateRemark() {
  const docId = document.getElementById("remark-modal-doc-id")?.value;
  const textarea = document.getElementById("new-remark-textarea");
  const statusSelect = document.getElementById("new-remark-status");
  const notes = textarea ? textarea.value.trim() : "";
  const status = statusSelect ? statusSelect.value : "";

  if (!docId) {
    showToast("No candidate selected", "error");
    return;
  }
  if (!notes) {
    showToast("Please enter a remark or recruiter note", "warning");
    return;
  }

  try {
    await API.addResumeRemark(docId, notes, status || undefined);
    showToast(`Remark saved for candidate ${docId}!`, "success");
    if (textarea) textarea.value = "";
    if (statusSelect) statusSelect.value = "";

    // Refresh remarks list
    const updatedActions = await API.getResumeActions(docId);
    renderCandidateRemarksList(updatedActions, status);

    // Refresh background data
    await refreshDataCaches();
    if (AppState.currentTab === "followups") loadFollowups();
    if (AppState.currentTab === "library") loadLibrary();
    loadDashboard();
  } catch (err) {
    showToast(`Failed to save remark: ${err.message}`, "error");
  }
}

function openActionModal(docId, defaultAction = "reviewed") {
  API.recordResumeOpened(docId).catch(() => {});
  document.getElementById("action-modal-doc-id").value = docId;
  const select = document.getElementById("action-type-select");
  if (select) {
    select.value = defaultAction;
  }
  const snoozeDaysInput = document.getElementById("snooze-days-input");
  if (snoozeDaysInput) {
    snoozeDaysInput.value = "7";
  }
  const notesInput = document.getElementById("action-notes-input");
  if (notesInput) {
    notesInput.value = "";
  }
  onActionTypeChange();
  openModal("record-action-modal");
}

function onActionTypeChange() {
  const select = document.getElementById("action-type-select");
  const snoozeGroup = document.getElementById("snooze-duration-group");
  const hiredBanner = document.getElementById("action-hired-banner");
  if (!select) return;
  if (snoozeGroup) snoozeGroup.style.display = select.value === "snooze" ? "block" : "none";
  if (hiredBanner) hiredBanner.style.display = select.value === "hired" ? "block" : "none";
}

async function submitRecordAction() {
  const rawDocId = document.getElementById("action-modal-doc-id").value;
  const actionType = document.getElementById("action-type-select").value;
  const rawNotes = document.getElementById("action-notes-input").value.trim();
  const notes = rawNotes || (actionType === "hired" ? "Candidate marked as Hired via recruiter action box." : `Action '${actionType}' recorded by recruiter.`);

  let nextActionAt = null;
  let statusVal = actionType;
  if (actionType === "snooze") {
    const snoozeDaysInput = document.getElementById("snooze-days-input");
    const snoozeDays = parseInt(snoozeDaysInput?.value, 10);
    if (!snoozeDays || snoozeDays < 1) {
      showToast("Please enter a valid positive number of snooze days (minimum 1)", "warning");
      return;
    }
    statusVal = "in_progress";
    const nextDate = new Date();
    nextDate.setDate(nextDate.getDate() + snoozeDays);
    nextActionAt = nextDate.toISOString();
  } else if (actionType === "hired") {
    statusVal = "hired";
  } else if (actionType === "reviewed") {
    statusVal = "reviewed";
  } else if (actionType === "contacted") {
    statusVal = "contacted";
  } else if (actionType === "shortlist" || actionType === "shortlisted") {
    statusVal = "shortlisted";
  }

  const docIds = rawDocId.split(",").map(s => s.trim()).filter(Boolean);

  try {
    for (const docId of docIds) {
      await API.recordAction(docId, actionType, statusVal, notes, nextActionAt);
      AppState.candidateActionStates[docId] = statusVal;

      const statusBadge = document.getElementById(`cand-status-badge-${docId}`);
      if (statusBadge) {
        statusBadge.className = `file-status-badge badge-${statusVal}`;
        statusBadge.textContent = statusVal.replace('_', ' ');
      }

      const group = document.getElementById(`actions-group-${docId}`);
      if (group) {
        const btnShortlist = group.querySelector(".btn-action-shortlist");
        const btnContacted = group.querySelector(".btn-action-contacted");
        const btnReviewed = group.querySelector(".btn-action-reviewed");
        const btnSnooze = group.querySelector(".btn-action-snooze");
        const btnHired = group.querySelector(".btn-action-hired");

        if (btnShortlist) btnShortlist.classList.toggle("active-shortlisted", statusVal === "shortlisted");
        if (btnContacted) btnContacted.classList.toggle("active-contacted", statusVal === "contacted");
        if (btnReviewed) btnReviewed.classList.toggle("active-reviewed", statusVal === "reviewed");
        if (btnSnooze) btnSnooze.classList.toggle("active-snoozed", statusVal === "in_progress" || statusVal === "snooze");
        if (btnHired) btnHired.classList.toggle("active-hired", statusVal === "hired");
      }
    }
    showToast(docIds.length > 1 ? `Recorded action "${actionType}" for ${docIds.length} candidate(s)` : (actionType === "hired" ? `Candidate ${docIds[0]} successfully marked as Hired` : `Recorded action "${actionType}" for ${docIds[0]}`), "success");
    closeModal("record-action-modal");
    await refreshDataCaches();
    await loadFollowups();
    await loadLibrary();
    await loadDashboard();
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

// ==========================================
// 5. RESUME LIBRARY WORKFLOW (MULTI-SELECT & BULK ACTIONS)
// ==========================================
function updateBulkToolbar() {
  const toolbar = document.getElementById("lib-bulk-toolbar");
  const countEl = document.getElementById("lib-selected-count");
  const selectAll = document.getElementById("lib-select-all");
  const count = AppState.selectedDocIds.size;

  if (countEl) countEl.textContent = count;

  if (toolbar) {
    toolbar.style.display = count > 0 ? "flex" : "none";
  }

  const allRowCheckboxes = document.querySelectorAll(".lib-row-checkbox");
  if (selectAll && allRowCheckboxes.length > 0) {
    const allChecked = Array.from(allRowCheckboxes).every(cb => cb.checked);
    const someChecked = Array.from(allRowCheckboxes).some(cb => cb.checked);
    selectAll.checked = allChecked;
    selectAll.indeterminate = someChecked && !allChecked;
  } else if (selectAll) {
    selectAll.checked = false;
    selectAll.indeterminate = false;
  }
}

function toggleSelectResume(docId, checked) {
  if (checked) {
    AppState.selectedDocIds.add(docId);
  } else {
    AppState.selectedDocIds.delete(docId);
  }

  const row = document.querySelector(`tr[data-doc-id="${docId}"]`);
  if (row) {
    row.classList.toggle("selected", checked);
  }

  updateBulkToolbar();
}

function toggleSelectAllResumes(checked) {
  const checkboxes = document.querySelectorAll(".lib-row-checkbox");
  checkboxes.forEach(cb => {
    cb.checked = checked;
    const docId = cb.value;
    if (checked) {
      AppState.selectedDocIds.add(docId);
    } else {
      AppState.selectedDocIds.delete(docId);
    }
    const row = document.querySelector(`tr[data-doc-id="${docId}"]`);
    if (row) {
      row.classList.toggle("selected", checked);
    }
  });

  updateBulkToolbar();
}

function clearResumeSelection() {
  AppState.selectedDocIds.clear();
  document.querySelectorAll(".lib-row-checkbox").forEach(cb => {
    cb.checked = false;
  });
  document.querySelectorAll("#library-table-body tr").forEach(tr => {
    tr.classList.remove("selected");
  });
  const selectAll = document.getElementById("lib-select-all");
  if (selectAll) {
    selectAll.checked = false;
    selectAll.indeterminate = false;
  }
  updateBulkToolbar();
}

// Bulk Toolbar Actions: Preview, Improve Resume, Action, Delete Selected, Clear Selection
function bulkPreviewSelectedResumes() {
  const selected = Array.from(AppState.selectedDocIds);
  if (!selected.length) {
    showToast("Please select at least one candidate resume to preview", "warning");
    return;
  }
  const list = selected.map(id => {
    const r = (AppState.resumes || []).find(x => x.doc_id === id);
    return {
      doc_id: id,
      full_name: r?.full_name || r?.candidate_name || r?.pii?.name || r?.original_filename || id,
      original_filename: r?.original_filename || id
    };
  });
  openResumePreview(list[0].doc_id, list);
}

function bulkImproveSelectedResumes() {
  const selected = Array.from(AppState.selectedDocIds);
  if (!selected.length) {
    showToast("Please select at least one candidate resume to improve", "warning");
    return;
  }
  AppState.selectedExistingImproveDocIds = new Set(selected);
  AppState.selectedResumeDocId = selected[0];
  switchTab("improvement");
  const sel = document.getElementById("improve-resume-select");
  if (sel) sel.value = selected[0];
  renderImproveExistingResumes();
  updateImproveSelectedCountBadge();
  renderImproveCandidatePersonalDetails();
  showToast(`Loaded ${selected.length} resume(s) into Improve Resume`, "info");
}

function bulkActionSelectedResumes() {
  const selected = Array.from(AppState.selectedDocIds);
  if (!selected.length) {
    showToast("Please select at least one candidate resume for action", "warning");
    return;
  }
  openActionModal(selected.join(","));
}

function confirmBulkDeleteResumes() {
  openBulkDeleteModal();
}

function openBulkDeleteModal() {
  const count = AppState.selectedDocIds.size;
  if (count === 0) {
    showToast("No resumes selected for deletion.", "warning");
    return;
  }
  const countEl = document.getElementById("bulk-delete-count-display");
  if (countEl) countEl.textContent = count;
  const btn = document.getElementById("btn-confirm-bulk-delete");
  if (btn) {
    btn.disabled = false;
    btn.textContent = `Delete Selected Resumes (${count})`;
  }
  openModal("bulk-delete-modal");
}

async function executeBulkDelete() {
  const docIds = Array.from(AppState.selectedDocIds);
  if (docIds.length === 0) return;

  const btn = document.getElementById("btn-confirm-bulk-delete");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Deleting selected resumes...";
  }

  try {
    const result = await API.bulkDeleteResumes(docIds);
    closeModal("bulk-delete-modal");

    if (result.success) {
      showToast(result.message, "success");
    } else {
      showToast(result.message, "error");
    }

    clearResumeSelection();
    await refreshDataCaches();
    await loadLibrary();
    if (AppState.currentTab === "followups") await loadFollowups();
    if (AppState.currentTab === "notifications") await loadNotifications();
    await loadDashboard();
  } catch (err) {
    showToast(`Bulk deletion error: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Delete Selected Resumes";
    }
  }
}

async function loadLibrary() {
  const query = document.getElementById("lib-search-input")?.value || "";
  const status = document.getElementById("lib-status-filter")?.value || "";
  const tbody = document.getElementById("library-table-body");
  if (!tbody) return;

  tbody.innerHTML = "<tr><td colspan='7' class='text-center text-muted'>Loading library records...</td></tr>";

  try {
    const list = await API.getResumes(query, status);
    AppState.resumes = list;
    tbody.innerHTML = "";

    if (!list.length) {
      tbody.innerHTML = "<tr><td colspan='7' class='text-center text-dim'>No resumes found matching filter.</td></tr>";
      updateBulkToolbar();
      return;
    }

    list.forEach(item => {
      const tr = document.createElement("tr");
      tr.setAttribute("data-doc-id", item.doc_id);
      const isSelected = AppState.selectedDocIds.has(item.doc_id);
      if (isSelected) tr.classList.add("selected");

      const followupMatch = (AppState.allFollowups || []).find(f => f.doc_id === item.doc_id);
      let recStatus = (followupMatch?.status || item.latest_status || item.status || "pending_review").toLowerCase();
      if (recStatus === "ready" || recStatus === "uploaded") {
        recStatus = "pending_review";
      }

      let statusBadge = "";
      if (recStatus === "hired") {
        statusBadge = `<span class="file-status-badge badge-hired">HIRED</span>`;
      } else if (recStatus === "shortlisted" || recStatus === "reviewed") {
        statusBadge = `<span class="file-status-badge badge-ready">${escapeHtml(recStatus.toUpperCase())}</span>`;
      } else if (recStatus === "contacted") {
        statusBadge = `<span class="file-status-badge badge-ready" style="background:var(--primary-subtle); color:var(--primary); border-color:var(--primary-border);">CONTACTED</span>`;
      } else if (recStatus === "rejected") {
        statusBadge = `<span class="file-status-badge badge-failed">REJECTED</span>`;
      } else {
        statusBadge = `<span class="file-status-badge badge-processing">${escapeHtml(recStatus.replace('_', ' ').toUpperCase())}</span>`;
      }

      const displayName = item.full_name || item.candidate_name || item.pii?.name || item.original_filename || item.doc_id;

      tr.innerHTML = `
        <td style="width:40px; text-align:center;">
          <input type="checkbox" class="lib-row-checkbox" value="${item.doc_id}" ${isSelected ? "checked" : ""} onchange="toggleSelectResume('${item.doc_id}', this.checked)">
        </td>
        <td><button type="button" class="doc-id-link" onclick="openCandidateRemarksModal('${item.doc_id}')" title="View candidate remarks and activity"><strong>${item.doc_id}</strong></button></td>
        <td><strong>${escapeHtml(displayName)}</strong></td>
        <td class="filename-cell" title="${escapeHtml(item.original_filename)}">${escapeHtml(item.original_filename)}</td>
        <td>${statusBadge}</td>
        <td>${formatDate(item.uploaded_at)}</td>
        <td>
          <div style="display:flex; gap:0.4rem; align-items:center;">
            <button class="btn btn-secondary btn-sm" onclick="viewCandidateDetailsModal('${item.doc_id}')" title="View candidate and contact details" style="padding:0.3rem 0.6rem; display:inline-flex; align-items:center; justify-content:center;">${SVG_EYE_ICON}</button>
            <button class="btn btn-danger btn-sm" onclick="confirmDeleteResume('${item.doc_id}', '${escapeHtml(displayName)}')">Delete</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });

    updateBulkToolbar();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='7' class='text-danger'>Error: ${err.message}</td></tr>`;
  }
}

function confirmDeleteResume(docId, filename) {
  showConfirmModal(
    "Delete Candidate Resume",
    `Are you sure you want to permanently delete candidate ${docId} ("${filename}")? All profile data, version history, and stored files will be removed.`,
    async () => {
      try {
        await API.deleteResume(docId);
        showToast(`Resume ${docId} deleted successfully`, "success");
        await refreshDataCaches();
        loadLibrary();
        if (AppState.currentTab === "followups") loadFollowups();
        if (AppState.currentTab === "notifications") loadNotifications();
        const statRes = document.getElementById("stat-total-resumes");
        if (statRes) statRes.textContent = AppState.resumes.length;
      } catch (err) {
        showToast(`Failed to delete resume: ${err.message}`, "error");
      }
    }
  );
}

async function viewCandidateDetailsModal(docId) {
  const content = document.getElementById("pii-modal-content");
  if (!content) return;
  content.innerHTML = "<div class='text-center text-muted' style='padding:1.5rem;'>Retrieving candidate details...</div>";
  openModal("candidate-pii-modal");

  try {
    const pii = await API.getResumePII(docId);
    const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId);

    const displayName = pii.name || resumeObj?.full_name || resumeObj?.candidate_name || `Candidate ${docId}`;
    const filename = pii.filename || resumeObj?.original_filename || `${docId}.docx`;
    const uploadedAt = pii.uploaded_at || resumeObj?.uploaded_at;
    const skills = (pii.skills && pii.skills.length > 0) ? pii.skills : (resumeObj?.profile?.skills || []);

    let expDisplay = "Not available";
    if (pii.experience_display && typeof pii.experience_display === "string" && pii.experience_display.trim() !== "" && !pii.experience_display.includes("[object")) {
      expDisplay = pii.experience_display;
    } else if (typeof pii.experience_years === "number" && !isNaN(pii.experience_years) && pii.experience_years > 0) {
      expDisplay = `${pii.experience_years} yrs`;
    } else if (resumeObj?.profile?.experience_display && typeof resumeObj.profile.experience_display === "string" && !resumeObj.profile.experience_display.includes("[object")) {
      expDisplay = resumeObj.profile.experience_display;
    } else if (typeof resumeObj?.profile?.experience_years === "number" && !isNaN(resumeObj.profile.experience_years) && resumeObj.profile.experience_years > 0) {
      expDisplay = `${resumeObj.profile.experience_years} yrs`;
    }

    if (expDisplay.includes("[object") || expDisplay.includes("NaN") || expDisplay.includes("null") || expDisplay.includes("undefined")) {
      expDisplay = "Not available";
    }

    content.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:1.2rem; border-bottom:1px solid var(--border-subtle); padding-bottom:0.8rem;">
        <div>
          <h3 style="font-family:var(--font-heading); font-size:1.25rem; font-weight:700; color:var(--text-main); margin-bottom:0.25rem;">
            ${escapeHtml(displayName)}
          </h3>
          <span style="font-size:0.8rem; color:var(--text-dim); font-family:var(--font-mono);">${docId}</span>
          ${pii.title ? `<div style="font-size:0.84rem; color:var(--primary); font-weight:600; margin-top:0.2rem;">${escapeHtml(pii.title)}</div>` : ''}
        </div>
        <button type="button" class="btn btn-secondary btn-sm" onclick="closeModal('candidate-pii-modal'); openResumePreview('${docId}', (AppState.resumes || []))">
          Preview
        </button>
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; font-size:0.88rem; margin-bottom:1.2rem;">
        <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:8px; padding:0.9rem;">
          <h4 style="font-size:0.82rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-dim); margin-bottom:0.6rem;">Contact Information</h4>
          <div style="display:flex; flex-direction:column; gap:0.45rem;">
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">Email:</strong> <span style="color:var(--text-main);">${escapeHtml(pii.email || "N/A")}</span></div>
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">Phone:</strong> <span style="color:var(--text-main);">${escapeHtml(pii.phone || "N/A")}</span></div>
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">Location:</strong> <span style="color:var(--text-main);">${escapeHtml(pii.location || pii.address || "N/A")}</span></div>
            ${pii.links ? `<div><strong style="color:var(--text-dim); font-size:0.8rem;">Links:</strong> <span style="color:var(--text-main); word-break:break-all;">${escapeHtml(pii.links)}</span></div>` : ''}
          </div>
        </div>

        <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:8px; padding:0.9rem;">
          <h4 style="font-size:0.82rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-dim); margin-bottom:0.6rem;">Document Details</h4>
          <div style="display:flex; flex-direction:column; gap:0.45rem;">
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">File:</strong> <span style="color:var(--text-main); word-break:break-all;">${escapeHtml(filename)}</span></div>
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">Uploaded:</strong> <span style="color:var(--text-main);">${formatDate(uploadedAt)}</span></div>
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">Experience:</strong> <span style="color:var(--text-main);">${escapeHtml(expDisplay)}</span></div>
          </div>
        </div>
      </div>

      ${skills.length ? `
        <div style="background:rgba(255,255,255,0.02); border:1px solid var(--border-subtle); border-radius:8px; padding:0.9rem; margin-bottom:0.8rem;">
          <h4 style="font-size:0.82rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-dim); margin-bottom:0.6rem;">Extracted Skills</h4>
          <div style="display:flex; flex-wrap:wrap; gap:0.35rem;">
            ${skills.map(s => `<span class="tag-matched" style="font-size:0.75rem; padding:2px 8px;">${escapeHtml(s)}</span>`).join("")}
          </div>
        </div>
      ` : ''}

      <div style="font-size:0.72rem; color:var(--text-dim); text-align:right;">
        Authorized Access Verified &bull; Decrypted for Recruiter View
      </div>
    `;
  } catch (err) {
    content.innerHTML = `<div style="color:var(--danger); padding:1rem;">Error retrieving details: ${escapeHtml(err.message)}</div>`;
  }
}

const viewPIIModal = viewCandidateDetailsModal;

// ==========================================
// 6. MODAL & CONFIRMATION DIALOG HELPERS
// ==========================================
let pendingConfirmAction = null;

function showConfirmModal(title, message, onConfirm) {
  const titleEl = document.getElementById("confirm-modal-title");
  const msgEl = document.getElementById("confirm-modal-message");
  const btnEl = document.getElementById("btn-confirm-action");

  if (titleEl) titleEl.textContent = title;
  if (msgEl) msgEl.textContent = message;

  pendingConfirmAction = onConfirm;

  if (btnEl) {
    btnEl.onclick = async () => {
      closeModal("confirm-modal");
      if (pendingConfirmAction) {
        await pendingConfirmAction();
        pendingConfirmAction = null;
      }
    };
  }

  openModal("confirm-modal");
}

// ==========================================
// 7. ACTIVE JOB OPENINGS MANAGEMENT
// ==========================================
function openManageJobsModal() {
  const titleInput = document.getElementById("new-job-title-input");
  const textInput = document.getElementById("new-job-text-input");
  if (titleInput) titleInput.value = "";
  if (textInput) textInput.value = "";
  renderManageJobsList();
  openModal("manage-jobs-modal");
}

function renderManageJobsList() {
  const container = document.getElementById("manage-jobs-list");
  if (!container) return;

  if (!AppState.jobs.length) {
    container.innerHTML = "<p class='text-dim text-center' style='padding:1rem;'>No active job openings found. Create one above!</p>";
    return;
  }

  container.innerHTML = AppState.jobs.map(j => `
    <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 0.9rem 1.1rem; display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
      <div style="flex: 1;">
        <div style="font-weight: 700; font-size: 0.95rem; color: #fff;">${j.title}</div>
        <div style="font-size: 0.76rem; color: var(--accent-cyan); margin: 0.15rem 0;">ID: ${j.job_id} • Created: ${formatDate(j.created_at)}</div>
        <div style="font-size: 0.8rem; color: var(--text-muted);">${j.preview_snippet || ""}</div>
      </div>
      <div>
        <button class="btn btn-danger btn-sm" onclick="deleteJobOpening('${j.job_id}', '${j.title.replace(/'/g, "\\'")}')">Delete</button>
      </div>
    </div>
  `).join("");
}

async function createNewJobOpening() {
  const titleInput = document.getElementById("new-job-title-input");
  const textInput = document.getElementById("new-job-text-input");

  const title = titleInput?.value.trim();
  const text = textInput?.value.trim();

  if (!title || !text || text.length < 10) {
    showToast("Please provide a title and job requirements description (at least 10 characters)", "warning");
    return;
  }

  try {
    const newJob = await API.createJob(title, text);
    showToast(`Job opening "${newJob.title}" created successfully!`, "success");
    titleInput.value = "";
    textInput.value = "";
    await refreshDataCaches();
    renderManageJobsList();
    renderJobSelector();
    initImprovementTab();
    const statJobs = document.getElementById("stat-active-jobs");
    if (statJobs) statJobs.textContent = AppState.jobs.length;
  } catch (err) {
    showToast(`Failed to create job: ${err.message}`, "error");
  }
}

function deleteJobOpening(jobId, jobTitle) {
  showConfirmModal(
    "Delete Job Opening",
    `Are you sure you want to permanently delete job opening "${jobTitle || jobId}" (${jobId})?`,
    async () => {
      try {
        await API.deleteJob(jobId);
        showToast("Job opening deleted successfully", "success");
        if (AppState.selectedJobId === jobId) {
          AppState.selectedJobId = null;
          const textArea = document.getElementById("match-jd-textarea");
          if (textArea) textArea.value = "";
        }
        await refreshDataCaches();
        renderManageJobsList();
        renderJobSelector();
        initImprovementTab();
        const statJobs = document.getElementById("stat-active-jobs");
        if (statJobs) statJobs.textContent = AppState.jobs.length;
      } catch (err) {
        showToast(`Failed to delete job: ${err.message}`, "error");
      }
    }
  );
}

// ==========================================
// 8. NOTIFICATIONS & EMAIL
// ==========================================
async function loadNotifications() {
  const container = document.getElementById("notifications-list-container");
  if (!container) return;

  container.innerHTML = "<div class='text-center text-muted' style='padding:2rem;'>Checking dormancy thresholds and review SLAs...</div>";

  try {
    const notifs = await API.getNotifications(false);
    
    // Update badge count: if user has seen notifications, keep badge hidden
    const unread = notifs.filter(n => !n.is_read);
    const badge = document.getElementById("badge-notifications-count");
    if (badge) {
      if (AppState.notificationsSeen || !unread.length) {
        badge.style.display = "none";
        badge.textContent = "0";
      } else {
        badge.style.display = "inline-flex";
        badge.textContent = unread.length;
      }
    }

    if (!notifs.length) {
      container.innerHTML = `
        <div class="card" style="text-align:center; padding:2.5rem 1.5rem;">
          <h3 style="font-family:var(--font-heading); margin-bottom:0.35rem;">No Active Escalations</h3>
          <p style="font-size:0.86rem; color:var(--text-muted); max-width:480px; margin:0 auto;">
            All candidate follow-ups are within active service SLAs. No records currently exceed the inactivity threshold.
          </p>
        </div>
      `;
      return;
    }

    container.innerHTML = notifs.map(n => {
      const cand = (AppState.resumes || []).find(r => r.doc_id === n.doc_id);
      const candFullName = cand?.candidate_name || cand?.full_name || cand?.pii?.name || `Candidate ${n.doc_id}`;
      return `
      <div class="card" style="border-left: 3px solid ${n.days_inactive >= 90 || n.severity === 'danger' ? 'var(--danger)' : 'var(--warning)'};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; margin-bottom:0.5rem; flex-wrap:wrap;">
          <div>
            <div style="display:flex; align-items:center; gap:0.5rem;">
              <span class="file-status-badge ${n.days_inactive >= 90 ? 'badge-failed' : 'badge-processing'}">
                ${n.days_inactive >= 90 ? '3+ Months Inactive' : 'Inactivity Notice'}
              </span>
              <strong style="font-size:0.95rem; color:var(--text-main);">${escapeHtml(candFullName)} &bull; ${escapeHtml(n.title)}</strong>
              ${!n.is_read ? '<span class="file-status-badge badge-ready" style="font-size:0.68rem; padding:1px 5px;">NEW</span>' : ''}
            </div>
            <div style="font-size:0.8rem; color:var(--text-dim); margin-top:0.25rem;">
              Candidate: <strong style="color:var(--text-main);">${escapeHtml(candFullName)}</strong> <span style="font-size:0.75rem; color:var(--text-muted);">(${n.doc_id})</span> &bull; Inactive for <strong>${n.days_inactive} days</strong> &bull; Alert generated ${formatDate(n.created_at)}
            </div>
          </div>
          <div style="text-align:right;">
            ${n.email_sent ? `
              <span class="file-status-badge badge-ready">
                Emailed to ${escapeHtml(n.email_sent_to)}
              </span>
              <div style="font-size:0.7rem; color:var(--text-dim); margin-top:2px;">
                ${formatDateTime(n.email_sent_at)}
              </div>
            ` : `
              <button class="btn btn-primary btn-sm" onclick="openEscalationEmailModal('${n.doc_id}', ${n.days_inactive})">
                Dispatch Email Notice
              </button>
            `}
          </div>
        </div>

        <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.75rem; line-height:1.5;">
          ${escapeHtml(n.message)}
        </p>

        <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid var(--border-subtle); padding-top:0.65rem; font-size:0.8rem; flex-wrap:wrap; gap:0.5rem;">
          <div style="color:var(--text-dim);">
            <span>Attachment: <strong>Original Resume (DMS)</strong></span>
            ${n.email_attachment_filename ? ` &bull; Attached: <strong>${escapeHtml(n.email_attachment_filename)}</strong>` : ''}
          </div>
          <div style="display:flex; gap:0.4rem; align-items:center;">
            <button class="btn btn-secondary btn-sm" onclick="viewCandidateDetailsModal('${n.doc_id}')" title="View candidate and contact details" style="padding:0.3rem 0.55rem; display:inline-flex; align-items:center; justify-content:center;">${SVG_EYE_ICON}</button>
            <button class="btn btn-secondary btn-sm" onclick="downloadCandidateResume('${n.doc_id}')" title="Download Candidate Resume">Download Resume</button>
            <button class="btn btn-secondary btn-sm" onclick="launchImprovementForCandidate('${n.doc_id}')">Improve Resume</button>
            ${!n.is_read ? `<button class="btn btn-secondary btn-sm" onclick="markNotificationAsRead('${n.id}')">Mark Read</button>` : ''}
            <button class="btn btn-danger btn-sm" onclick="confirmDeleteResume('${n.doc_id}', 'Candidate ${n.doc_id}')">Delete</button>
          </div>
        </div>
      </div>
    `;
    }).join("");
  } catch (err) {
    container.innerHTML = `<div class="card" style="color:var(--danger);">Error loading notifications: ${err.message}</div>`;
  }
}

function openEscalationEmailModal(docId, daysInactive, reason = null) {
  document.getElementById("email-modal-doc-id").value = docId;
  document.getElementById("email-modal-recipient").value = "damayanthi.u@riscrm.com";
  
  const cand = (AppState.resumes || []).find(r => r.doc_id === docId);
  const candFullName = cand?.candidate_name || cand?.full_name || cand?.pii?.name || `Candidate ${docId}`;

  const days = daysInactive || 90;
  const reasonText = reason || `Candidate ${candFullName} (ID: ${docId}) has not had any recruiter action recorded for ${days} days (over 3 months review SLA). Please review the attached original resume for leadership decision or candidate re-engagement.`;
  document.getElementById("email-modal-reason").value = reasonText;
  
  openModal("escalation-email-modal");
}

async function submitEscalationEmail() {
  const docId = document.getElementById("email-modal-doc-id").value;
  const recipient = document.getElementById("email-modal-recipient").value.trim() || "damayanthi.u@riscrm.com";
  const reason = document.getElementById("email-modal-reason").value.trim();
  const btn = document.getElementById("btn-send-escalation-email");

  if (!docId) {
    showToast("Invalid candidate document ID", "error");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Attaching Resume & Dispatching...";

  try {
    const res = await API.sendEscalationEmail(docId, recipient, reason);
    closeModal("escalation-email-modal");
    if (res.delivered_via_smtp) {
      showToast(`Delivered live email to ${res.recipient} with resume "${res.attachment_filename}" attached!`, "success");
    } else {
      showToast(res.message || `Email archived locally. Configure SMTP in .env to send real emails to inboxes.`, "warning");
    }
    
    // Refresh views
    await refreshDataCaches();
    if (AppState.currentTab === "notifications") loadNotifications();
    if (AppState.currentTab === "followups") loadFollowups();
  } catch (err) {
    showToast(`Failed to dispatch email: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Send Email with Resume Attached";
  }
}

async function markNotificationAsRead(id) {
  try {
    await API.markNotificationRead(id);
    showToast("Notification marked as read", "info");
    loadNotifications();
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

// ==========================================
// 9. IKM / RAG BUILDER MANAGEMENT
// ==========================================
let ikmChatHistory = [];

async function checkIKMStatus() {
  const badgeDot = document.getElementById("header-ikm-dot");
  const badgeText = document.getElementById("header-ikm-text");
  const badge = document.getElementById("header-ikm-badge");
  if (!badge) return;

  try {
    const status = await API.getIKMStatus();
    if (status.authenticated) {
      if (badgeDot) badgeDot.style.background = "#10b981";
      if (badgeText) badgeText.textContent = "IKM RAG: Connected";
      badge.style.borderColor = "rgba(16, 185, 129, 0.4)";
      badge.style.color = "#6ee7b7";
    } else if (status.account_locked || (status.auth_error && (status.auth_error.includes("423") || status.auth_error.includes("locked")))) {
      if (badgeDot) badgeDot.style.background = "#f59e0b";
      if (badgeText) badgeText.textContent = "IKM: Account Locked (Remote)";
      badge.style.borderColor = "rgba(245, 158, 11, 0.4)";
      badge.style.color = "#fde68a";
    } else if (status.online) {
      if (badgeDot) badgeDot.style.background = "#f59e0b";
      if (badgeText) badgeText.textContent = "IKM RAG: Password Needed (.env)";
      badge.style.borderColor = "rgba(245, 158, 11, 0.4)";
      badge.style.color = "#fde68a";
    } else {
      if (badgeDot) badgeDot.style.background = "#94a3b8";
      if (badgeText) badgeText.textContent = "IKM: Local Engine";
      badge.style.borderColor = "rgba(148, 163, 184, 0.3)";
      badge.style.color = "#cbd5e1";
    }
    return status;
  } catch (err) {
    if (badgeText) badgeText.textContent = "IKM: Local Engine";
  }
}

async function openIKMModal() {
  openModal("ikm-rag-modal");
  const statusEl = document.getElementById("ikm-modal-status-text");
  const authEl = document.getElementById("ikm-modal-auth-text");
  const urlEl = document.getElementById("ikm-modal-url");
  const userEl = document.getElementById("ikm-modal-user");
  const guardEl = document.getElementById("ikm-modal-guard-text");
  const serviceEl = document.getElementById("ikm-modal-service");
  const passAlert = document.getElementById("ikm-password-alert");

  if (statusEl) statusEl.textContent = "Testing...";
  if (authEl) authEl.textContent = "Evaluating...";

  try {
    const st = await API.getIKMStatus();
    if (urlEl && st.base_url) urlEl.textContent = st.base_url;
    if (userEl && st.username) userEl.textContent = `user: ${st.username}`;
    if (serviceEl && st.service) serviceEl.textContent = `${st.service} v1.0.0`;
    if (guardEl && st.prompt_guard) guardEl.textContent = `Active (${st.prompt_guard})`;

    const userInput = document.getElementById("ikm-test-user-input");
    if (userInput && st.username && (!userInput.value || userInput.value === "resume-screening")) {
      userInput.value = st.username;
    }

    if (st.online) {
      if (statusEl) {
        statusEl.textContent = "Online";
        statusEl.style.color = "#10b981";
      }
    } else {
      if (statusEl) {
        statusEl.textContent = "Offline (Local Engine Active)";
        statusEl.style.color = "#94a3b8";
      }
    }

    if (st.authenticated) {
      if (authEl) {
        authEl.textContent = "Authenticated ✓";
        authEl.style.color = "#10b981";
      }
      if (passAlert) passAlert.style.display = "none";
    } else if (st.account_locked || (st.auth_error && (st.auth_error.includes("423") || st.auth_error.includes("locked")))) {
      if (authEl) {
        authEl.textContent = "Account Locked (Remote)";
        authEl.style.color = "#f59e0b";
      }
      if (passAlert) {
        passAlert.style.display = "block";
        passAlert.style.background = "rgba(245, 158, 11, 0.1)";
        passAlert.style.borderColor = "rgba(245, 158, 11, 0.3)";
        passAlert.innerHTML = `<strong>Remote Status:</strong> The IKM server at <code>${escapeHtml(st.base_url || '16.113.145.53:8088')}</code> has locked user <code>${escapeHtml(st.username || 'user')}</code> (HTTP 423 Rate Limit). Your <code>.env</code> password is configured and loaded. High-precision local parsing engine is actively handling all resume workflows without interruption.`;
      }
    } else {
      if (authEl) {
        authEl.textContent = "Credentials Needed";
        authEl.style.color = "#f59e0b";
      }
      if (passAlert) passAlert.style.display = "block";
    }
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = "Local Only";
      statusEl.style.color = "#94a3b8";
    }
    if (authEl) {
      authEl.textContent = "Built-in Active";
      authEl.style.color = "#10b981";
    }
  }
}

function switchIKMTab(tabName) {
  const tabs = ['test', 'search', 'chat'];
  tabs.forEach(t => {
    const panel = document.getElementById(`ikm-tab-${t}-panel`);
    const btn = document.getElementById(`btn-ikm-tab-${t}`);
    if (panel) panel.style.display = (t === tabName) ? "block" : "none";
    if (btn) {
      if (t === tabName) {
        btn.classList.add("btn-primary");
        btn.classList.remove("btn-secondary");
      } else {
        btn.classList.add("btn-secondary");
        btn.classList.remove("btn-primary");
      }
    }
  });
}

function toggleIKMEnvPass(checkbox) {
  const passInput = document.getElementById("ikm-test-pass-input");
  if (!passInput) return;
  if (checkbox.checked) {
    passInput.disabled = true;
    passInput.value = "••••••••••••••••••••";
    passInput.placeholder = "Loaded from .env";
  } else {
    passInput.disabled = false;
    passInput.value = "";
    passInput.placeholder = "Enter custom password to test";
    passInput.focus();
  }
}

async function runIKMAuthTest() {
  const user = document.getElementById("ikm-test-user-input")?.value.trim();
  const useEnv = document.getElementById("ikm-use-env-pass-check")?.checked ?? true;
  const rawPass = document.getElementById("ikm-test-pass-input")?.value.trim();
  
  // If useEnv is checked, or if password input has placeholder dots/is blank, pass is null (uses .env)
  const pass = useEnv ? null : ((!rawPass || rawPass.split("").every(c => c === "•" || c === "*")) ? null : rawPass);
  const resultEl = document.getElementById("ikm-auth-test-result");
  if (!resultEl) return;

  resultEl.style.display = "block";
  resultEl.style.background = "rgba(255, 255, 255, 0.05)";
  resultEl.style.color = "var(--text-muted)";
  resultEl.textContent = useEnv ? "Testing authentication with configured credentials in .env..." : "Testing authentication with custom credentials...";

  try {
    const res = await API.testIKMAuth(user, pass);
    if (res.success) {
      resultEl.style.background = "rgba(16, 185, 129, 0.15)";
      resultEl.style.color = "#6ee7b7";
      resultEl.textContent = `✓ ${res.message} (Token issued)`;
      showToast("RAG Builder authentication succeeded!", "success");
      checkIKMStatus();
    } else if (res.status_code === 423 || (res.message && res.message.includes("423"))) {
      resultEl.style.background = "rgba(245, 158, 11, 0.15)";
      resultEl.style.color = "#fde68a";
      resultEl.textContent = `ℹ️ ${res.message}`;
      showToast("Remote rate limit active (local parser running seamlessly)", "info");
      checkIKMStatus();
    } else {
      resultEl.style.background = "rgba(239, 68, 68, 0.15)";
      resultEl.style.color = "#fca5a5";
      resultEl.textContent = `✕ ${res.message || "Authentication rejected."} (Status: ${res.status_code || 401})`;
    }
  } catch (err) {
    resultEl.style.background = "rgba(239, 68, 68, 0.15)";
    resultEl.style.color = "#fca5a5";
    resultEl.textContent = `Error: ${err.message}`;
  }
}

async function runIKMSearch() {
  const query = document.getElementById("ikm-search-query-input")?.value.trim();
  const listEl = document.getElementById("ikm-search-results-list");
  if (!query || !listEl) return;

  listEl.innerHTML = "<div class='text-muted' style='text-align:center; padding:1rem;'>Executing hybrid RAG retrieval across resume corpus...</div>";

  try {
    const res = await API.retrieveIKM(query, 5);
    const results = res.results || [];
    if (!results.length) {
      listEl.innerHTML = "<div class='text-dim' style='text-align:center; padding:1rem;'>No matching candidate documents retrieved for query.</div>";
      return;
    }

    listEl.innerHTML = results.map(r => `
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:6px; padding:0.75rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;">
          <strong style="color:var(--accent-cyan); font-size:0.88rem;">${r.doc_id || "Candidate"}</strong>
          <span class="file-status-badge badge-ready" style="font-size:0.72rem;">Score: ${Math.round((r.relevance_score || 0) * 100)}%</span>
        </div>
        <p style="font-size:0.8rem; color:var(--text-muted); margin:0;">${r.content || JSON.stringify(r.profile || "")}</p>
      </div>
    `).join("");
  } catch (err) {
    listEl.innerHTML = `<div class='text-danger' style='padding:1rem;'>Error: ${err.message}</div>`;
  }
}

async function runIKMChat() {
  const inputEl = document.getElementById("ikm-chat-query-input");
  const query = inputEl?.value.trim();
  const box = document.getElementById("ikm-chat-messages");
  if (!query || !box) return;

  inputEl.value = "";

  // Append user message
  const userMsg = document.createElement("div");
  userMsg.style.cssText = "align-self: flex-end; background: rgba(99, 102, 241, 0.25); color: #e0e7ff; padding: 0.5rem 0.8rem; border-radius: 8px; font-size: 0.82rem; max-width: 80%;";
  userMsg.textContent = query;
  box.appendChild(userMsg);
  box.scrollTop = box.scrollHeight;

  // Add loading AI placeholder
  const aiMsg = document.createElement("div");
  aiMsg.style.cssText = "align-self: flex-start; background: rgba(255, 255, 255, 0.05); color: #cbd5e1; padding: 0.5rem 0.8rem; border-radius: 8px; font-size: 0.82rem; max-width: 85%;";
  aiMsg.textContent = "Thinking with RAG knowledge...";
  box.appendChild(aiMsg);
  box.scrollTop = box.scrollHeight;

  try {
    ikmChatHistory.push({ role: "user", content: query });
    const res = await API.chatIKM(query, ikmChatHistory);
    const reply = res.response || res.message || res.answer || JSON.stringify(res);
    aiMsg.textContent = reply;
    ikmChatHistory.push({ role: "assistant", content: reply });
  } catch (err) {
    aiMsg.textContent = `Error: ${err.message}`;
    aiMsg.style.color = "var(--danger)";
  }
  box.scrollTop = box.scrollHeight;
}

// Global window bindings for resilient inline HTML onclick execution
window.openResumePreview = openResumePreview;
window.navigateResumePreview = navigateResumePreview;
window.changeDocumentPage = changeDocumentPage;
window.openVersionComparisonModal = openVersionComparisonModal;
window.viewCandidateDetailsModal = viewCandidateDetailsModal;
window.viewPIIModal = viewCandidateDetailsModal;
window.getMatchResultsPreviewList = getMatchResultsPreviewList;
window.getMatchScopedPreviewList = getMatchScopedPreviewList;
window.getImproveScopedPreviewList = getImproveScopedPreviewList;
window.switchImprovementCandidate = switchImprovementCandidate;
window.downloadCurrentPreviewDocument = downloadCurrentPreviewDocument;
window.fitCompareDocxPanels = fitCompareDocxPanels;
window.bulkAcceptAllAndProceed = bulkAcceptAllAndProceed;
window.bulkAcceptAllAndProceedToDownload = bulkAcceptAllAndProceedToDownload;
window.bulkAcceptAllAndScrollDown = bulkAcceptAllAndScrollDown;
window.handleImprovementDownloadClick = handleImprovementDownloadClick;
window.renderMultiDownloadModal = renderMultiDownloadModal;
window.downloadSingleAppliedDocx = downloadSingleAppliedDocx;
window.previewCurrentImprovedResume = previewCurrentImprovedResume;
window.switchImprovedPreviewIndex = switchImprovedPreviewIndex;
window.openImprovedResumePreview = openImprovedResumePreview;
window.onImproveJobSelected = onImproveJobSelected;
window.AppState = AppState;
window.getAppliedImprovementsList = getAppliedImprovementsList;
window.closeModal = closeModal;
window.downloadCurrentCompareDocument = downloadCurrentCompareDocument;
window.switchImprovedCompareIndex = switchImprovedCompareIndex;
window.renderCompareTabsBar = renderCompareTabsBar;
