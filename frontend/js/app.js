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
  selectedDocIds: new Set()
};

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
}

// ==========================================
// RESUME PREVIEW & SIDE NAVIGATION (< and >)
// ==========================================
function openResumePreview(docId, candidateList = null) {
  if (!docId) return;

  // Derive candidate list context if not explicitly provided
  let list = candidateList;
  if (!list || !list.length) {
    if (AppState.currentTab === "matching" && AppState.activeMatchResults?.results?.length) {
      list = AppState.activeMatchResults.results.map(r => ({
        doc_id: r.doc_id,
        full_name: r.full_name || r.candidate_name || r.candidate_label || r.doc_id,
        original_filename: r.doc_id
      }));
    } else if (AppState.currentTab === "matching" && AppState.uploadedResumes.length) {
      list = AppState.uploadedResumes.filter(r => r.doc_id).map(r => ({
        doc_id: r.doc_id,
        full_name: r.full_name || r.candidate_name || r.filename || r.doc_id,
        original_filename: r.filename
      }));
    } else if (AppState.resumes?.length) {
      list = AppState.resumes.map(r => ({
        doc_id: r.doc_id,
        full_name: r.full_name || r.candidate_name || r.pii?.name || r.original_filename || r.doc_id,
        original_filename: r.original_filename
      }));
    } else {
      list = [{ doc_id: docId, full_name: docId, original_filename: docId }];
    }
  }

  AppState.previewList = list;
  let idx = list.findIndex(item => (item.doc_id === docId || item.docId === docId));
  if (idx === -1) {
    const resumeObj = AppState.resumes.find(r => r.doc_id === docId);
    const fallbackName = resumeObj ? (resumeObj.full_name || resumeObj.candidate_name || resumeObj.original_filename) : docId;
    AppState.previewList = [{ doc_id: docId, full_name: fallbackName, original_filename: docId }, ...list];
    idx = 0;
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
  }
}

async function renderResumePreviewAtIndex(idx) {
  if (!AppState.previewList || !AppState.previewList[idx]) return;
  const item = AppState.previewList[idx];
  const docId = item.doc_id || item.docId;
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
  if (tagEl) tagEl.textContent = `ID: ${docId}`;
  if (counterEl) counterEl.textContent = `${idx + 1} of ${AppState.previewList.length}`;

  if (prevBtn) prevBtn.disabled = (idx <= 0);
  if (nextBtn) nextBtn.disabled = (idx >= AppState.previewList.length - 1);

  if (inappContainer) inappContainer.style.display = "block";
  if (frame) frame.style.display = "none";
  if (pageControls) pageControls.style.display = "none";

  if (paperSheet) {
    paperSheet.innerHTML = `
      <div style="text-align:center; padding:3rem 1rem; color:var(--text-muted);">
        <div class="spinner" style="margin:0 auto 1rem;"></div>
        <div>Loading resume document...</div>
      </div>
    `;
  }

  API.recordResumeOpened(docId).catch(() => {});

  AppState.currentPreviewPages = [];
  AppState.currentPreviewPageIndex = 0;

  try {
    const previewData = await API.getResumePreview(docId);
    if (previewData && previewData.success && previewData.pages && previewData.pages.length > 0) {
      AppState.currentPreviewPages = previewData.pages;
      AppState.currentPreviewPageIndex = 0;

      renderDocumentPage(0);

      if (previewData.total_pages > 1 && pageControls) {
        pageControls.style.display = "flex";
        if (pageCounter) pageCounter.textContent = `Page 1 of ${previewData.total_pages}`;
        if (pagePrev) pagePrev.disabled = true;
        if (pageNext) pageNext.disabled = false;
      } else if (pageControls) {
        pageControls.style.display = "none";
      }
    } else {
      if (paperSheet) {
        paperSheet.innerHTML = `
          <div style="padding:2.5rem 1.5rem; text-align:center; color:var(--text-muted);">
            <div style="font-size:2rem; margin-bottom:0.5rem;">📄</div>
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
          <div style="font-size:2rem; margin-bottom:0.5rem;">⚠️</div>
          <div>Failed to load document preview: ${escapeHtml(err.message)}</div>
        </div>
      `;
    }
  }
}

function renderDocumentPage(pageIndex) {
  const paperSheet = document.getElementById("preview-paper-sheet");
  const inappContainer = document.getElementById("preview-inapp-container");
  if (!paperSheet || !AppState.currentPreviewPages || !AppState.currentPreviewPages[pageIndex]) return;

  paperSheet.innerHTML = AppState.currentPreviewPages[pageIndex];
  if (inappContainer) inappContainer.scrollTop = 0;
}

function changeDocumentPage(direction) {
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

  // Load initial data
  await refreshDataCaches();
  loadDashboard();
  checkIKMStatus();
});

async function refreshDataCaches() {
  try {
    AppState.resumes = await API.getResumes();
    AppState.jobs = await API.getJobs();
    try {
      AppState.allFollowups = await API.getFollowups() || [];
    } catch (_) {}
    updateTabBadges();
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
    const summary = await API.getDashboardSummary();
    const fuBadge = document.getElementById("badge-followups-count");
    if (fuBadge) {
      fuBadge.textContent = summary.follow_ups_due;
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

    // Follow-ups badge
    const fuBadge = document.getElementById("badge-followups-count");
    if (fuBadge) fuBadge.textContent = summary.follow_ups_due;

    // Top Skills Badges
    const skillsContainer = document.getElementById("dashboard-skills-cloud");
    if (skillsContainer) {
      skillsContainer.innerHTML = "";
      Object.entries(summary.top_skills_distribution || {}).forEach(([skill, count]) => {
        const tag = document.createElement("span");
        tag.className = "tag-matched";
        tag.style.fontSize = "0.82rem";
        tag.textContent = `${skill} (${count})`;
        skillsContainer.appendChild(tag);
      });
      if (!Object.keys(summary.top_skills_distribution || {}).length) {
        skillsContainer.innerHTML = "<p class='text-dim'>No candidate skills registered yet.</p>";
      }
    }

    // Recent Activity Table
    const actBody = document.getElementById("dashboard-activity-body");
    if (actBody) {
      actBody.innerHTML = "";
      (summary.recent_activity || []).slice(0, 6).forEach(act => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${act.doc_id && act.doc_id !== "System" ? `<button type="button" class="doc-id-link" onclick="openCandidateRemarksModal('${act.doc_id}')" title="Click to view remarks for ${act.doc_id}"><strong>${act.doc_id}</strong> <span style="font-size:0.75rem;">💬</span></button>` : `<strong>${act.doc_id || "System"}</strong>`}</td>
          <td><span class="file-status-badge badge-ready">${act.action_type}</span></td>
          <td>${act.notes || "Recorded action"}</td>
          <td>${act.owner_id}</td>
          <td>${formatDate(act.timestamp)}</td>
        `;
        actBody.appendChild(tr);
      });
      if (!summary.recent_activity?.length) {
        actBody.innerHTML = "<tr><td colspan='5' class='text-dim text-center'>No recorded actions yet.</td></tr>";
      }
    }
  } catch (err) {
    showToast("Failed to load dashboard statistics", "error");
  }
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
      <button type="button" class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); openResumePreview('${r.doc_id}')" style="padding:0.2rem 0.5rem; font-size:0.72rem;">Preview</button>
    `;
    container.appendChild(itemEl);
  });
}

function toggleExpandExistingMatch() {
  const container = document.getElementById("match-existing-collapsible");
  const chevron = document.getElementById("match-existing-chevron");
  if (!container) return;
  const isHidden = container.style.display === "none" || !container.style.display;
  container.style.display = isHidden ? "block" : "none";
  if (chevron) chevron.textContent = isHidden ? "▲" : "▼";
}

function updateMatchSelectedCountBadge() {
  const badge = document.getElementById("match-selected-count-badge");
  if (!badge) return;
  const count = AppState.selectedExistingMatchDocIds.size;
  badge.textContent = `${count} selected`;
  badge.style.display = count > 0 ? "inline-block" : "none";
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

  // Keep in sync with actual existing resumes in database
  if (AppState.resumes && AppState.resumes.length) {
    const existingDocIds = new Set(AppState.resumes.map(r => r.doc_id));
    AppState.uploadedResumes = AppState.uploadedResumes.filter(item => {
      return !item.doc_id || existingDocIds.has(item.doc_id);
    });
    saveUploadedResumesToStorage();
  }

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
        <span style="font-size:1.15rem; flex-shrink:0;">📄</span>
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
        <button type="button" class="btn btn-secondary btn-sm" onclick="openResumePreview('${item.doc_id || ''}')" ${!item.doc_id ? 'disabled' : ''} title="Preview Resume" style="font-size:0.75rem; padding:0.25rem 0.6rem; border-radius:var(--radius-sm);">
          Preview
        </button>
        <button type="button" class="btn btn-danger btn-sm" onclick="removeUploadedResume('${item.doc_id || ''}', '${escapedFilename}', ${idx})" title="Remove this uploaded resume" style="font-size:0.75rem; padding:0.25rem 0.6rem; border-radius:var(--radius-sm); display:inline-flex; align-items:center; gap:0.25rem;">
          🗑️ Remove
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
  showConfirmModal(
    "Remove Uploaded Resume",
    `Are you sure you want to remove and delete "${displayName}"? It will be removed from this candidate search and permanently deleted from the database.`,
    async () => {
      try {
        if (docId) {
          await API.deleteResume(docId);
        }
        if (docId) {
          AppState.uploadedResumes = AppState.uploadedResumes.filter(r => r.doc_id !== docId);
        } else if (typeof index === "number") {
          AppState.uploadedResumes.splice(index, 1);
        }
        saveUploadedResumesToStorage();
        showToast(`Resume "${displayName}" removed successfully`, "success");
        await refreshDataCaches();
        renderUploadedFilesList();
        validateMatchForm();
      } catch (err) {
        showToast(`Failed to remove resume: ${err.message}`, "error");
      }
    }
  );
}

function clearAllUploadedResumes() {
  if (!AppState.uploadedResumes.length) return;
  showConfirmModal(
    "Clear All Uploaded Resumes",
    `Are you sure you want to remove all ${AppState.uploadedResumes.length} uploaded resume(s)? They will be permanently removed from this search and database.`,
    async () => {
      try {
        for (const item of AppState.uploadedResumes) {
          if (item.doc_id) {
            try { await API.deleteResume(item.doc_id); } catch (e) { console.warn(e); }
          }
        }
        AppState.uploadedResumes = [];
        saveUploadedResumesToStorage();
        showToast("All uploaded resumes removed", "info");
        await refreshDataCaches();
        renderUploadedFilesList();
        validateMatchForm();
      } catch (err) {
        showToast(`Failed to clear resumes: ${err.message}`, "error");
      }
    }
  );
}

async function handleFilesUpload(fileList) {
  showToast(`Uploading ${fileList.length} resume(s)...`, "info");

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

  // Scope indicator banner
  if (evaluatedUploadedCount !== null) {
    const scopeBanner = document.createElement("div");
    scopeBanner.style.cssText = "display:flex; align-items:center; gap:0.6rem; padding:0.7rem 1.1rem; margin-bottom:1.2rem; background:rgba(6,182,212,0.1); border:1px solid rgba(6,182,212,0.3); border-radius:var(--radius-sm); color:var(--accent-cyan); font-size:0.86rem;";
    scopeBanner.innerHTML = `
      <span style="font-size:1.2rem;">🎯</span>
      <div>
        <strong>Search Scope: Selected Resumes</strong> &mdash; Evaluated <strong>${evaluatedUploadedCount}</strong> chosen candidate resume(s).
      </div>
    `;
    container.appendChild(scopeBanner);
  } else {
    const scopeBanner = document.createElement("div");
    scopeBanner.style.cssText = "display:flex; align-items:center; gap:0.6rem; padding:0.7rem 1.1rem; margin-bottom:1.2rem; background:rgba(99,102,241,0.1); border:1px solid rgba(99,102,241,0.25); border-radius:var(--radius-sm); color:var(--text-main); font-size:0.86rem;";
    scopeBanner.innerHTML = `
      <span style="font-size:1.2rem;">📚</span>
      <div>
        <strong>Search Scope: Entire Resume Library</strong> &mdash; Evaluated across all candidate resumes in the database.
      </div>
    `;
    container.appendChild(scopeBanner);
  }

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
        <div class="actions-group" id="actions-group-${cand.doc_id}">
          <button type="button" class="btn btn-secondary btn-sm" onclick="viewCandidateDetailsModal('${cand.doc_id}')" title="View candidate and contact details" style="padding:0.25rem 0.55rem; font-size:0.95rem; line-height:1;">👁️</button>
          <button type="button" class="btn btn-secondary btn-sm candidate-action-btn btn-action-shortlist ${currentStatus === 'shortlisted' ? 'active-shortlisted' : ''}" 
            onclick="toggleCandidateAction('${cand.doc_id}', 'shortlist', this)">Shortlist</button>
          <button type="button" class="btn btn-secondary btn-sm candidate-action-btn btn-action-snooze ${currentStatus === 'in_progress' || currentStatus === 'snooze' ? 'active-snoozed' : ''}" 
            onclick="toggleCandidateAction('${cand.doc_id}', 'snooze', this)">Snooze</button>
          <button type="button" class="btn btn-secondary btn-sm candidate-action-btn btn-action-remark" 
            onclick="toggleCandidateAction('${cand.doc_id}', 'remark', this)">Remark</button>
          <button type="button" class="btn btn-secondary btn-sm candidate-action-btn btn-action-hired ${currentStatus === 'hired' ? 'active-hired' : ''}" 
            onclick="toggleCandidateAction('${cand.doc_id}', 'hired', this)" title="Mark candidate as Hired">Hired</button>
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
  } else if (actionType === "snooze") {
    if (currentStatus === "in_progress" || currentStatus === "snooze") {
      targetStatus = "pending_review";
      backendActionType = "reset";
      notes = "Candidate un-snoozed and returned to review";
    } else {
      targetStatus = "in_progress";
      backendActionType = "snooze";
      notes = "Candidate snoozed for 7 days";
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
      const btnSnooze = group.querySelector(".btn-action-snooze");
      const btnHired = group.querySelector(".btn-action-hired");

      if (btnShortlist) btnShortlist.classList.toggle("active-shortlisted", targetStatus === "shortlisted");
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
  const cand = AppState.activeMatchResults?.results?.find(r => r.doc_id === docId);
  if (!cand) return;

  const content = document.getElementById("score-modal-content");
  const b = cand.score_breakdown;

  content.innerHTML = `
    <h3 style="margin-bottom:1rem; font-family:var(--font-heading);">${cand.candidate_label} — Internal Score Breakdown</h3>
    <div style="font-size:0.84rem; color:var(--text-muted); margin-bottom:1.2rem;">
      Score is computed across 5 weighted dimensions based on documented evidence.
    </div>

    <div style="display:flex; flex-direction:column; gap:0.9rem;">
      <div style="background:rgba(255,255,255,0.03); padding:0.8rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; font-weight:600;">
          <span>1. Mandatory Requirements (Weight 35%)</span>
          <span style="color:var(--success);">${b.mandatory_requirements.score} / ${b.mandatory_requirements.max} pts</span>
        </div>
        <div style="font-size:0.78rem; color:var(--text-dim); margin-top:0.2rem;">
          Matched ${b.mandatory_requirements.matched_count} of ${b.mandatory_requirements.total_count} core requirements
        </div>
      </div>

      <div style="background:rgba(255,255,255,0.03); padding:0.8rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; font-weight:600;">
          <span>2. Technical / Role Skills (Weight 25%)</span>
          <span style="color:var(--accent-cyan);">${b.technical_skills.score} / ${b.technical_skills.max} pts</span>
        </div>
        <div style="font-size:0.78rem; color:var(--text-dim); margin-top:0.2rem;">
          Coverage: ${b.technical_skills.matched_count} of ${b.technical_skills.total_count} skills evidenced
        </div>
      </div>

      <div style="background:rgba(255,255,255,0.03); padding:0.8rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; font-weight:600;">
          <span>3. Relevant Experience & Projects (Weight 20%)</span>
          <span style="color:#c084fc;">${b.experience_and_projects.score} / ${b.experience_and_projects.max} pts</span>
        </div>
        <div style="font-size:0.78rem; color:var(--text-dim); margin-top:0.2rem;">
          ${b.experience_and_projects.evaluated_items} relevant project & experience artifacts
        </div>
      </div>

      <div style="background:rgba(255,255,255,0.03); padding:0.8rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; font-weight:600;">
          <span>4. Education / Qualifications (Weight 10%)</span>
          <span style="color:var(--warning);">${b.education_credentials.score} / ${b.education_credentials.max} pts</span>
        </div>
        <div style="font-size:0.78rem; color:var(--text-dim); margin-top:0.2rem;">
          Documented Degree: ${b.education_credentials.qualification}
        </div>
      </div>

      <div style="background:rgba(255,255,255,0.03); padding:0.8rem; border-radius:8px;">
        <div style="display:flex; justify-content:space-between; font-weight:600;">
          <span>5. Evidence Quality & Specificity (Weight 10%)</span>
          <span style="color:var(--success);">${b.evidence_quality.score} / ${b.evidence_quality.max} pts</span>
        </div>
        <div style="font-size:0.78rem; color:var(--text-dim); margin-top:0.2rem;">
          ${b.evidence_quality.has_concrete_evidence ? "Verified text evidence present" : "Basic evidence"}
        </div>
      </div>
    </div>
  `;

  openModal("score-breakdown-modal");
}

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

function renderImproveExistingResumes() {
  const container = document.getElementById("improve-existing-list");
  const searchInput = document.getElementById("improve-existing-search");
  const selectedNameEl = document.getElementById("improve-selected-name");
  const selectAllCb = document.getElementById("improve-select-all-existing");
  if (!container) return;

  const query = (searchInput?.value || "").toLowerCase().trim();
  const allResumes = AppState.resumes || [];

  const filtered = allResumes.filter(r => {
    if (!query) return true;
    const name = (r.full_name || r.candidate_name || r.pii?.name || "").toLowerCase();
    const docId = (r.doc_id || "").toLowerCase();
    const filename = (r.original_filename || "").toLowerCase();
    return name.includes(query) || docId.includes(query) || filename.includes(query);
  });

  const selectedResume = allResumes.find(r => r.doc_id === AppState.selectedResumeDocId);
  if (selectedNameEl) {
    selectedNameEl.textContent = selectedResume 
      ? (selectedResume.full_name || selectedResume.candidate_name || selectedResume.doc_id)
      : (AppState.selectedExistingImproveDocIds.size > 0 ? `${AppState.selectedExistingImproveDocIds.size} Selected` : "None Selected");
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
      <div style="flex:1; min-width:0; overflow:hidden;" onclick="selectResumeForImprovement('${r.doc_id}')">
        <div style="font-weight:600; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
          ${escapeHtml(displayName)}
        </div>
        <div style="font-size:0.72rem; color:var(--text-dim); display:flex; gap:0.5rem;">
          <span>ID: ${r.doc_id}</span>
          <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">(${escapeHtml(r.original_filename)})</span>
        </div>
      </div>
      <button type="button" class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); openResumePreview('${r.doc_id}')" style="padding:0.2rem 0.5rem; font-size:0.72rem;">Preview</button>
    `;
    container.appendChild(itemEl);
  });
}

function toggleExpandExistingImprove() {
  const container = document.getElementById("improve-existing-collapsible");
  const chevron = document.getElementById("improve-existing-chevron");
  if (!container) return;
  const isHidden = container.style.display === "none" || !container.style.display;
  container.style.display = isHidden ? "block" : "none";
  if (chevron) chevron.textContent = isHidden ? "▲" : "▼";
}

function updateImproveSelectedCountBadge() {
  const badge = document.getElementById("improve-selected-count-badge");
  if (!badge) return;
  const count = AppState.selectedExistingImproveDocIds.size + (AppState.improveUploadedResumes ? AppState.improveUploadedResumes.length : 0);
  badge.textContent = `${count} selected`;
  badge.style.display = count > 0 ? "inline-block" : "none";
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
  const allResumes = AppState.resumes || [];
  allResumes.forEach(r => {
    if (checked) {
      AppState.selectedExistingImproveDocIds.add(r.doc_id);
    } else {
      AppState.selectedExistingImproveDocIds.delete(r.doc_id);
    }
  });
  if (checked && allResumes.length > 0) {
    AppState.selectedResumeDocId = allResumes[0].doc_id;
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
        <span style="font-size:1.15rem; flex-shrink:0;">📄</span>
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
        <button type="button" class="btn btn-secondary btn-sm" onclick="openResumePreview('${item.doc_id || ''}')" ${!item.doc_id ? 'disabled' : ''} style="font-size:0.75rem; padding:0.25rem 0.6rem;">
          Preview
        </button>
        <button type="button" class="btn btn-danger btn-sm" onclick="removeImproveUploadedResume(${idx})" style="font-size:0.75rem; padding:0.25rem 0.6rem; border-radius:var(--radius-sm);">
          🗑️ Remove
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

function launchImprovementForCandidate(docId) {
  AppState.selectedResumeDocId = docId;
  AppState.selectedExistingImproveDocIds.add(docId);
  switchTab("improvement");
  const sel = document.getElementById("improve-resume-select");
  if (sel) sel.value = docId;
  renderImproveExistingResumes();
  updateImproveSelectedCountBadge();
  fetchAndPopulateCandidatePII(docId);
}

// Candidate Personal & Contact Information (Dynamic Multi-Card)
async function fetchAndPopulateCandidatePII(docId) {
  if (!docId) return;
  if (!AppState.candidatePersonalDetails[docId]) {
    try {
      const pii = await API.getResumePII(docId);
      const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId);
      AppState.candidatePersonalDetails[docId] = {
        name: pii.name || resumeObj?.full_name || resumeObj?.candidate_name || "",
        role: pii.role || resumeObj?.profile?.role || "",
        phone: pii.phone || "",
        email: pii.email || "",
        location: pii.address || pii.location || "",
        links: pii.links || ""
      };
    } catch (err) {
      console.warn(`Could not load PII for ${docId}:`, err);
      const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId);
      AppState.candidatePersonalDetails[docId] = {
        name: resumeObj?.full_name || resumeObj?.candidate_name || resumeObj?.pii?.name || "",
        role: resumeObj?.profile?.role || "",
        phone: resumeObj?.pii?.phone || "",
        email: resumeObj?.pii?.email || "",
        location: resumeObj?.pii?.address || resumeObj?.pii?.location || "",
        links: resumeObj?.pii?.links || ""
      };
    }
  }
  renderImproveCandidatePersonalDetails();
}

async function renderImproveCandidatePersonalDetails() {
  const container = document.getElementById("improve-personal-details-container");
  if (!container) return;

  // Aggregate all selected resumes
  const selectedDocIds = new Set();
  AppState.selectedExistingImproveDocIds.forEach(id => selectedDocIds.add(id));
  (AppState.improveUploadedResumes || []).forEach(r => {
    if (r.doc_id) selectedDocIds.add(r.doc_id);
  });
  if (AppState.selectedResumeDocId) {
    selectedDocIds.add(AppState.selectedResumeDocId);
  }

  const docIdList = Array.from(selectedDocIds);

  if (!docIdList.length) {
    container.innerHTML = `
      <div class="card" style="padding:1.5rem; text-align:center; color:var(--text-muted); background:var(--bg-surface-subtle); border:1px dashed var(--border-subtle); border-radius:var(--radius-md);">
        <div style="font-size:1.6rem; margin-bottom:0.4rem;">📋</div>
        <div style="font-size:0.9rem; font-weight:600; color:var(--text-main); margin-bottom:0.25rem;">No Resumes Selected</div>
        <div style="font-size:0.8rem;">Select one or more resumes above or upload new files to view and verify candidate contact details.</div>
      </div>
    `;
    return;
  }

  // Preload missing PII in background
  docIdList.forEach(docId => {
    if (!AppState.candidatePersonalDetails[docId]) {
      const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId) ||
                        (AppState.improveUploadedResumes || []).find(r => r.doc_id === docId);
      AppState.candidatePersonalDetails[docId] = {
        name: resumeObj?.full_name || resumeObj?.candidate_name || resumeObj?.pii?.name || "",
        role: resumeObj?.profile?.role || "",
        phone: resumeObj?.pii?.phone || "",
        email: resumeObj?.pii?.email || "",
        location: resumeObj?.pii?.address || resumeObj?.pii?.location || "",
        links: resumeObj?.pii?.links || ""
      };

      API.getResumePII(docId).then(pii => {
        if (pii) {
          AppState.candidatePersonalDetails[docId] = {
            name: pii.name || AppState.candidatePersonalDetails[docId].name,
            role: pii.role || AppState.candidatePersonalDetails[docId].role,
            phone: pii.phone || AppState.candidatePersonalDetails[docId].phone,
            email: pii.email || AppState.candidatePersonalDetails[docId].email,
            location: pii.address || pii.location || AppState.candidatePersonalDetails[docId].location,
            links: pii.links || AppState.candidatePersonalDetails[docId].links
          };
          renderImproveCandidatePersonalDetails();
        }
      }).catch(() => {});
    }
  });

  // Build separate card for every selected resume
  let html = `<div style="display:flex; flex-direction:column; gap:1.25rem;">`;

  docIdList.forEach((docId, index) => {
    const resumeObj = (AppState.resumes || []).find(r => r.doc_id === docId) ||
                      (AppState.improveUploadedResumes || []).find(r => r.doc_id === docId);
    const filename = resumeObj?.original_filename || resumeObj?.filename || `${docId}.docx`;
    const details = AppState.candidatePersonalDetails[docId] || {};

    const fields = [
      { key: "name", label: "Full Name", placeholder: "e.g. Alex Morgan", val: details.name || "" },
      { key: "role", label: "Professional Title / Role", placeholder: "e.g. Senior Software Engineer", val: details.role || "" },
      { key: "phone", label: "Phone Number", placeholder: "e.g. +1 555-0199", val: details.phone || "" },
      { key: "email", label: "Email Address", placeholder: "e.g. candidate@example.com", val: details.email || "" },
      { key: "location", label: "Address / Location", placeholder: "e.g. San Francisco, CA", val: details.location || "" },
      { key: "links", label: "Portfolio / LinkedIn Links", placeholder: "e.g. linkedin.com/in/profile", val: details.links || "" }
    ];

    html += `
      <div class="card" id="cand-pii-card-${docId}" style="margin-bottom:0; background:var(--bg-surface-subtle); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:1.2rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; padding-bottom:0.6rem; border-bottom:1px solid var(--border-subtle); flex-wrap:wrap; gap:0.5rem;">
          <div style="display:flex; align-items:center; gap:0.6rem;">
            <span style="font-size:1.2rem;">📄</span>
            <div>
              <span style="font-weight:700; font-size:0.95rem; color:var(--text-main);">Resume ${index + 1} &mdash; <span style="color:var(--primary); font-family:var(--font-mono);">${escapeHtml(filename)}</span></span>
              <span class="candidate-doc-tag" style="margin-left:0.5rem;">ID: ${docId}</span>
            </div>
          </div>
          <button type="button" class="btn btn-secondary btn-sm" onclick="openResumePreview('${docId}')" style="padding:0.25rem 0.65rem; font-size:0.75rem;">
            👁️ Preview
          </button>
        </div>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.85rem;">
          ${fields.map(f => {
            const isMissing = !f.val || f.val.trim() === "";
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
  });

  html += `</div>`;
  container.innerHTML = html;
}

function onPersonalDetailsInputChange(docId, field, inputEl) {
  if (!AppState.candidatePersonalDetails[docId]) {
    AppState.candidatePersonalDetails[docId] = {};
  }
  const val = inputEl.value;
  AppState.candidatePersonalDetails[docId][field] = val;

  const fg = document.getElementById(`fg-${docId}-${field}`);
  const tag = document.getElementById(`tag-${docId}-${field}`);

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
  const selectedDocIds = new Set();
  AppState.selectedExistingImproveDocIds.forEach(id => selectedDocIds.add(id));
  (AppState.improveUploadedResumes || []).forEach(r => {
    if (r.doc_id) selectedDocIds.add(r.doc_id);
  });
  if (AppState.selectedResumeDocId) {
    selectedDocIds.add(AppState.selectedResumeDocId);
  }

  const docIdArray = Array.from(selectedDocIds);
  if (!docIdArray.length) {
    showToast("Please select at least one candidate resume to improve", "warning");
    return;
  }

  const primaryDocId = docIdArray[0];
  const jobId = document.getElementById("improve-job-select")?.value || null;
  const customJd = document.getElementById("improve-custom-jd")?.value.trim() || null;
  const btnStart = document.getElementById("btn-start-improvement");
  const btnContinue = document.getElementById("btn-continue-improvement");
  const loadingIndicator = document.getElementById("improve-loading-indicator");
  const container = document.getElementById("improvement-results-area");

  if (!jobId && (!customJd || customJd.length < 10)) {
    showToast("Please choose a saved job opening or enter custom job requirements", "warning");
    return;
  }

  // Prevent duplicate submissions and show loading indicator
  if (btnStart) btnStart.disabled = true;
  if (btnContinue) btnContinue.disabled = true;
  if (loadingIndicator) loadingIndicator.style.display = "flex";
  if (container) container.innerHTML = "";

  const personalDetails = AppState.candidatePersonalDetails[primaryDocId] || null;

  try {
    const analysis = await API.analyzeImprovement(primaryDocId, jobId, jobId ? null : customJd, personalDetails);
    renderImprovementAnalysis(analysis);
    showToast("Resume improvement recommendations generated!", "success");
    loadVersionHistory(primaryDocId);

    // Automatic scroll down smoothly to results section
    if (container) {
      container.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (err) {
    if (container) {
      container.innerHTML = `<div class='card' style='border-color:var(--danger); color:var(--danger); margin-top:1rem;'>${escapeHtml(err.message)}</div>`;
    }
    showToast(err.message, "error");
  } finally {
    if (btnStart) btnStart.disabled = false;
    if (btnContinue) btnContinue.disabled = false;
    if (loadingIndicator) loadingIndicator.style.display = "none";
  }
}

function renderImprovementAnalysis(data) {
  window._currentImprovementData = data;
  window._candidateDecisions = {};

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

  if (data.candidate_personal_details) {
    const pd = data.candidate_personal_details;
    const n = document.getElementById("improve-cand-name");
    const r = document.getElementById("improve-cand-role");
    const p = document.getElementById("improve-cand-phone");
    const e = document.getElementById("improve-cand-email");
    const l = document.getElementById("improve-cand-location");
    const lk = document.getElementById("improve-cand-links");
    if (n && pd.name && !n.value) n.value = pd.name;
    if (r && pd.role && !r.value) r.value = pd.role;
    if (p && pd.phone && !p.value) p.value = pd.phone;
    if (e && pd.email && !e.value) e.value = pd.email;
    if (l && pd.location && !l.value) l.value = pd.location;
    if (lk && pd.links && !lk.value) lk.value = pd.links;
  }

  const container = document.getElementById("improvement-results-area");
  container.innerHTML = `
    <!-- Top Alignment & Score Recalculator Banner -->
    <div class="improvement-score-banner" style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:1.25rem; margin-bottom:1.25rem;">
      <div style="flex:1;">
        <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.35rem;">
          <span style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.04em; color:var(--text-dim); font-weight:700;">Target Role Alignment</span>
          <span class="file-status-badge badge-ready" style="font-size:0.7rem;">${data.document_type === 'docx' ? 'DOCX (In-place layout preserved)' : 'PDF / Text Format'}</span>
        </div>
        <h2 style="font-family:var(--font-heading); font-size:1.5rem; font-weight:700; margin-bottom:0.25rem;">${escapeHtml(data.job_title)}</h2>
        <div style="font-size:0.8rem; color:var(--text-muted);">
          Candidate: <strong>${escapeHtml(data.doc_id)}</strong> | Model: <strong>${escapeHtml(data.llm_model || 'Groq Cloud LPU')}</strong>
        </div>
        <div style="font-size:0.78rem; color:var(--accent-blue); margin-top:0.35rem;">
          ℹ️ ${escapeHtml(data.ikm_evidence_status || 'Verified candidate evidence from repository')}
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
                ? '<span class="confirmation-badge" style="font-size:0.72rem;">⚠️ Candidate Confirmation Required</span>'
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

          <!-- Rationale & Evidence -->
          <div style="background:var(--bg-surface-subtle); border-radius:var(--radius-sm); padding:0.6rem 0.75rem; font-size:0.78rem; margin-bottom:0.75rem; color:var(--text-muted);">
            <div><strong>Rationale:</strong> ${escapeHtml(c.reason || 'Aligns candidate experience with target job profile')}</div>
            ${c.supporting_evidence && c.supporting_evidence.length ? `
              <div style="margin-top:0.25rem;"><strong>Supporting Evidence:</strong> ${c.supporting_evidence.map(e => escapeHtml(e.text)).join(" | ")}</div>
            ` : ''}
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

    <!-- Requirements Gaps & Unmet Criteria -->
    <div class="card" style="margin-bottom:1.5rem; border:1px solid var(--border-subtle);">
      <h4 style="font-family:var(--font-heading); font-size:0.95rem; margin-bottom:0.6rem; color:var(--danger);">
        ⚠️ Requirements Gaps & Missing Evidence (${(data.gaps || []).length + (data.not_demonstrated || []).length})
      </h4>
      <p style="font-size:0.78rem; color:var(--text-muted); margin-bottom:0.75rem;">
        These criteria from the target job description are not currently evidenced by the candidate's verified record. Honest screening preserves integrity by not hallucinating fake qualifications.
      </p>
      <div style="display:flex; flex-direction:column; gap:0.45rem;">
        ${(data.gaps && data.gaps.length ? data.gaps : (data.not_demonstrated || [])).map(g => `
          <div style="background:var(--bg-surface-subtle); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:0.6rem 0.75rem; font-size:0.82rem;">
            <strong style="color:var(--text-main);">${escapeHtml(g.requirement)}</strong>
            <div style="color:#fca5a5; font-size:0.76rem; margin-top:2px;">${escapeHtml(g.status === 'not_demonstrated' ? 'No supporting evidence found in candidate record.' : (g.recommendation || 'Gaps noted for recruiter review'))}</div>
          </div>
        `).join("")}
      </div>
    </div>

    <!-- Word-Like Document Editor & Export -->
    <div class="card" style="margin-top:1.5rem;">
      <h3 style="font-family:var(--font-heading); font-size:1.05rem; margin-bottom:0.4rem;">Approved Resume Revision & Export</h3>
      <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:0.85rem;">
        Edit paragraphs, apply formatting, and insert images before exporting to Microsoft Word (.docx).
      </p>
      <div class="form-group">
        <label class="form-label" style="font-size:0.78rem;">Version Change Summary</label>
        <input type="text" id="version-change-summary" class="form-control" value="${data.change_summary ? data.change_summary.replace(/"/g, '&quot;') : 'Target-aligned resume optimization with verified STAR metrics.'}">
      </div>

      <!-- Word Editor Ribbon Toolbar -->
      <div class="word-editor-toolbar">
        <button type="button" class="word-toolbar-btn" onclick="formatEditorDoc('bold')" title="Bold (Ctrl+B)"><b>B</b></button>
        <button type="button" class="word-toolbar-btn" onclick="formatEditorDoc('italic')" title="Italic (Ctrl+I)"><i>I</i></button>
        <button type="button" class="word-toolbar-btn" onclick="formatEditorDoc('underline')" title="Underline (Ctrl+U)"><u>U</u></button>
        <div class="word-toolbar-divider"></div>
        <select class="word-toolbar-select" onchange="formatEditorHeading(this.value)">
          <option value="p">Paragraph</option>
          <option value="h1">Heading 1</option>
          <option value="h2">Heading 2</option>
          <option value="h3">Heading 3</option>
        </select>
        <div class="word-toolbar-divider"></div>
        <button type="button" class="word-toolbar-btn" onclick="formatEditorDoc('justifyLeft')" title="Align Left">&#9664;</button>
        <button type="button" class="word-toolbar-btn" onclick="formatEditorDoc('justifyCenter')" title="Center">&#9646;</button>
        <button type="button" class="word-toolbar-btn" onclick="formatEditorDoc('justifyRight')" title="Align Right">&#9654;</button>
        <div class="word-toolbar-divider"></div>
        <button type="button" class="word-toolbar-btn" onclick="formatEditorDoc('insertUnorderedList')" title="Bullet List">&bull; List</button>
        <button type="button" class="word-toolbar-btn" onclick="formatEditorDoc('insertOrderedList')" title="Numbered List">1. List</button>
        <div class="word-toolbar-divider"></div>
        <button type="button" class="word-toolbar-btn" onclick="document.getElementById('word-image-upload-input').click()" title="Insert Image into Document">
          📷 Insert Image
        </button>
        <input type="file" id="word-image-upload-input" accept="image/*" style="display:none;" onchange="insertImageIntoWordEditor(this)">
        <button type="button" class="word-toolbar-btn" onclick="formatEditorDoc('removeFormat')" title="Clear Formatting">✕ Clear</button>
      </div>

      <!-- Word Editor Paper Canvas -->
      <div class="word-editor-paper-container">
        <div id="word-editor-canvas" class="word-editor-canvas" contenteditable="true" oninput="syncEditorToTextarea()">
          ${formatInitialCanvasContent(data.improved_resume_text || data.original_text_preview || '')}
        </div>
      </div>
      <textarea id="version-revised-content" style="display:none;">${escapeHtml(data.improved_resume_text || data.original_text_preview || '')}</textarea>

      <!-- Action Buttons -->
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.6rem; margin-top:1.1rem;">
        <button type="button" class="btn btn-secondary" id="btn-compare-versions" onclick="openVersionComparisonModal()">
          🔄 Compare Versions
        </button>
        <div style="display:flex; gap:0.6rem; flex-wrap:wrap;">
          <button type="button" class="btn btn-secondary" id="btn-open-local-word" onclick="openResumeInLocalWord('${data.doc_id}')">
            🖥️ Open in Local Word
          </button>
          <button type="button" class="btn btn-primary" id="btn-agent-download-word" onclick="downloadImprovedWordResume('${data.doc_id}')">
            📥 Download Approved Word (.docx)
          </button>
        </div>
      </div>
    </div>
  `;

  // Auto-apply personal details
  applyPersonalDetailsToDraft(false);
}

function formatEditorDoc(command, value = null) {
  document.execCommand(command, false, value);
  syncEditorToTextarea();
}

function formatEditorHeading(tag) {
  if (tag === 'p') {
    document.execCommand('formatBlock', false, '<p>');
  } else {
    document.execCommand('formatBlock', false, `<${tag}>`);
  }
  syncEditorToTextarea();
}

function insertImageIntoWordEditor(input) {
  if (!input.files || !input.files[0]) return;
  const file = input.files[0];
  const reader = new FileReader();
  reader.onload = function(e) {
    const dataUrl = e.target.result;
    document.execCommand('insertImage', false, dataUrl);
    syncEditorToTextarea();
    showToast(`Inserted image "${file.name}" into document`, "success");
  };
  reader.readAsDataURL(file);
  input.value = "";
}

function syncEditorToTextarea() {
  const canvas = document.getElementById("word-editor-canvas");
  const textarea = document.getElementById("version-revised-content");
  if (canvas) {
    canvas.dataset.userEdited = "true";
  }
  if (canvas && textarea) {
    textarea.value = canvas.innerHTML;
  }
}

function formatInitialCanvasContent(text) {
  if (!text) return "<p>Enter candidate resume content...</p>";
  if (text.includes("<p>") || text.includes("<div>")) {
    return text;
  }
  const lines = text.split("\n");
  let html = "";
  lines.forEach(line => {
    const l = line.trim();
    if (!l) {
      html += "<p><br></p>";
    } else if (l.startsWith("### ")) {
      html += `<h3>${escapeHtml(l.replace("### ", ""))}</h3>`;
    } else if (l.startsWith("## ")) {
      html += `<h2>${escapeHtml(l.replace("## ", ""))}</h2>`;
    } else if (l.startsWith("# ")) {
      html += `<h1>${escapeHtml(l.replace("# ", ""))}</h1>`;
    } else if (l.startsWith("- ") || l.startsWith("* ")) {
      html += `<ul><li>${escapeHtml(l.replace(/^[\-*]\s+/, ""))}</li></ul>`;
    } else {
      html += `<p>${escapeHtml(l)}</p>`;
    }
  });
  return html;
}

async function openResumeInLocalWord(docId) {
  if (!docId) return;
  try {
    showToast("Launching Microsoft Word locally...", "info");
    const res = await API.openInWord(docId);
    showToast(res.message || "Document opened in Microsoft Word!", "success");
  } catch (err) {
    showToast(`Could not open local Word: ${err.message}`, "error");
  }
}

function openVersionComparisonModal() {
  if (!window._currentImprovementData) {
    showToast("No active resume revision to compare.", "warning");
    return;
  }

  const data = window._currentImprovementData;
  const origBody = document.getElementById("compare-original-body");
  const revBody = document.getElementById("compare-revised-body");
  const origBadge = document.getElementById("compare-original-badge");
  const revBadge = document.getElementById("compare-revised-badge");

  if (origBadge) origBadge.textContent = `${data.doc_id} (Original)`;
  if (revBadge) revBadge.textContent = `Optimized Revision`;

  // Get raw texts
  const originalText = data.original_text_preview || "Original resume text.";
  const canvas = document.getElementById("word-editor-canvas");
  const revisedText = canvas ? canvas.innerText : (data.improved_resume_text || originalText);

  const origLines = originalText.split("\n").filter(l => l.trim().length > 0);
  const revLines = revisedText.split("\n").filter(l => l.trim().length > 0);

  // Side-by-side diff
  const origHtml = origLines.map(line => {
    const isPresent = revLines.some(rl => rl.trim() === line.trim());
    if (!isPresent) {
      return `<div style="margin-bottom:0.4rem;"><span class="diff-removed">${escapeHtml(line)}</span></div>`;
    }
    return `<div style="margin-bottom:0.4rem;">${escapeHtml(line)}</div>`;
  }).join("");

  const revHtml = revLines.map(line => {
    const wasPresent = origLines.some(ol => ol.trim() === line.trim());
    if (!wasPresent) {
      return `<div style="margin-bottom:0.4rem;"><span class="diff-added">${escapeHtml(line)}</span></div>`;
    }
    return `<div style="margin-bottom:0.4rem;">${escapeHtml(line)}</div>`;
  }).join("");

  if (origBody) origBody.innerHTML = origHtml || "<p class='text-dim'>Original resume text</p>";
  if (revBody) revBody.innerHTML = revHtml || "<p class='text-dim'>Revised resume text</p>";

  openModal("version-compare-modal");
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

async function bulkDecideAllChanges(decision) {
  if (!window._currentImprovementData?.changes) return;
  const changes = window._currentImprovementData.changes;

  for (const c of changes) {
    // If accepting all, skip any marked as user-confirmation required unless explicitly confirmed
    if (decision === 'accepted' && c.requires_user_confirmation) {
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
  showToast(decision === 'accepted' ? "Accepted all eligible verified changes" : `Changes updated to ${decision}`, "info");
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

  if (!summaryInput.value.trim() || !contentInput.value.trim()) {
    showToast("Please provide both change summary and content", "warning");
    return;
  }

  const personalDetails = {
    name: document.getElementById("improve-cand-name")?.value.trim(),
    role: document.getElementById("improve-cand-role")?.value.trim(),
    phone: document.getElementById("improve-cand-phone")?.value.trim(),
    email: document.getElementById("improve-cand-email")?.value.trim(),
    location: document.getElementById("improve-cand-location")?.value.trim(),
    links: document.getElementById("improve-cand-links")?.value.trim()
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
    const editorCanvas = document.getElementById("word-editor-canvas");
    const contentToSave = (editorCanvas && editorCanvas.innerHTML.trim()) ? editorCanvas.innerHTML.trim() : (contentInput ? contentInput.value.trim() : "");
    const res = await API.saveRevisedVersion(docId, summaryInput.value.trim(), contentToSave, true, personalDetails, approvedChanges);
    showToast(`Saved version ${res.version_id} successfully as Microsoft Word (.docx)!`, "success");
    loadVersionHistory(docId);
  } catch (err) {
    showToast(`Error saving version: ${err.message}`, "error");
  }
}

async function downloadImprovedWordResume(docId) {
  if (!docId) {
    showToast("Please select a candidate resume first", "warning");
    return;
  }
  const summaryInput = document.getElementById("version-change-summary");
  const contentInput = document.getElementById("version-revised-content");
  const editorCanvas = document.getElementById("word-editor-canvas");
  const jobSelect = document.getElementById("improve-job-select");

  const summary = summaryInput ? summaryInput.value.trim() : "Updated Professional Word Resume";
  let content = "";
  if (editorCanvas && editorCanvas.innerHTML.trim()) {
    content = editorCanvas.innerHTML.trim();
  } else if (contentInput) {
    content = contentInput.value.trim();
  }
  const targetRole = (jobSelect && jobSelect.options[jobSelect.selectedIndex]?.text) || "Senior Technical Professional";

  const btn = document.getElementById("btn-agent-download-word");
  const origBtnText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "⏳ Generating Word (.docx)...";
  }

  try {
    const personalDetails = {
      name: document.getElementById("improve-cand-name")?.value.trim(),
      role: document.getElementById("improve-cand-role")?.value.trim(),
      phone: document.getElementById("improve-cand-phone")?.value.trim(),
      email: document.getElementById("improve-cand-email")?.value.trim(),
      location: document.getElementById("improve-cand-location")?.value.trim(),
      links: document.getElementById("improve-cand-links")?.value.trim()
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

    const a = document.createElement("a");
    a.href = res.download_url;
    a.download = res.filename || `${docId}_Improved_Resume.docx`;
    document.body.appendChild(a);
    a.click();
    a.remove();

    showToast("Downloaded improved Word (.docx) resume with layout preserved!", "success");
    loadVersionHistory(docId);
    await refreshDataCaches();
  } catch (err) {
    showToast(`Error generating Word resume: ${err.message}`, "error");
  } finally {
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
            <a href="/api/versions/${v.version_id}/file" download class="btn btn-secondary btn-sm">📥 Download Word (.docx)</a>
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
          <button class="btn btn-secondary btn-sm" onclick="viewCandidateDetailsModal('${item.doc_id}')" title="View candidate and contact details" style="padding:0.25rem 0.5rem; font-size:0.95rem; line-height:1;">👁️</button>
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
        <span style="font-size:1.6rem; display:block; margin-bottom:0.4rem;">📝</span>
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
            <span class="remark-author">👤 ${act.owner_id || 'Recruiter'}</span>
            <span class="file-status-badge ${isHired ? 'badge-hired' : 'badge-processing'}" style="${badgeStyle}; margin-left:6px;">${actionTypeLabel} (${statusLabel})</span>
          </div>
          <span class="remark-time">🕒 ${timeStr}</span>
        </div>
        <div class="remark-content">${escapeHtml(act.notes || "No additional remarks")}</div>
        ${act.next_action_at ? `<div style="margin-top:0.35rem; font-size:0.74rem; color:#fde68a;">📅 Next action scheduled: ${formatDate(act.next_action_at)}</div>` : ''}
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

function openActionModal(docId) {
  API.recordResumeOpened(docId).catch(() => {});
  document.getElementById("action-modal-doc-id").value = docId;
  const select = document.getElementById("action-type-select");
  if (select) {
    select.value = "reviewed";
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
    statusVal = "in_progress";
    const snoozeDays = parseInt(document.getElementById("snooze-days-input")?.value, 10) || 7;
    const nextDate = new Date();
    nextDate.setDate(nextDate.getDate() + snoozeDays);
    nextActionAt = nextDate.toISOString();
  } else if (actionType === "hired") {
    statusVal = "hired";
  } else if (actionType === "reviewed") {
    statusVal = "reviewed";
  }

  const docIds = rawDocId.split(",").map(s => s.trim()).filter(Boolean);

  try {
    for (const docId of docIds) {
      await API.recordAction(docId, actionType, statusVal, notes, nextActionAt);
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
            <button class="btn btn-secondary btn-sm" onclick="openResumePreview('${item.doc_id}')">Preview</button>
            <button class="btn btn-secondary btn-sm" onclick="viewCandidateDetailsModal('${item.doc_id}')" title="View candidate and contact details" style="padding:0.25rem 0.5rem; font-size:0.95rem; line-height:1;">👁️</button>
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
    const skills = resumeObj?.profile?.skills || [];
    const experience = resumeObj?.profile?.experience_years || resumeObj?.profile?.experience || null;
    const displayName = pii.name || resumeObj?.full_name || resumeObj?.candidate_name || docId;

    content.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:1.2rem; border-bottom:1px solid var(--border-subtle); padding-bottom:0.8rem;">
        <div>
          <h3 style="font-family:var(--font-heading); font-size:1.25rem; font-weight:700; color:var(--text-main); margin-bottom:0.25rem;">
            ${escapeHtml(displayName)}
          </h3>
          <span style="font-size:0.8rem; color:var(--text-dim); font-family:var(--font-mono);">${docId}</span>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" onclick="closeModal('candidate-pii-modal'); openResumePreview('${docId}')">
          Preview
        </button>
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; font-size:0.88rem; margin-bottom:1.2rem;">
        <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:8px; padding:0.9rem;">
          <h4 style="font-size:0.82rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-dim); margin-bottom:0.6rem;">Contact Information</h4>
          <div style="display:flex; flex-direction:column; gap:0.45rem;">
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">Email:</strong> <span style="color:var(--text-main);">${escapeHtml(pii.email || "N/A")}</span></div>
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">Phone:</strong> <span style="color:var(--text-main);">${escapeHtml(pii.phone || "N/A")}</span></div>
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">Location:</strong> <span style="color:var(--text-main);">${escapeHtml(pii.address || "N/A")}</span></div>
          </div>
        </div>

        <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:8px; padding:0.9rem;">
          <h4 style="font-size:0.82rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-dim); margin-bottom:0.6rem;">Document Details</h4>
          <div style="display:flex; flex-direction:column; gap:0.45rem;">
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">File:</strong> <span style="color:var(--text-main); word-break:break-all;">${escapeHtml(resumeObj?.original_filename || "N/A")}</span></div>
            <div><strong style="color:var(--text-dim); font-size:0.8rem;">Uploaded:</strong> <span style="color:var(--text-main);">${formatDate(resumeObj?.uploaded_at)}</span></div>
            ${experience ? `<div><strong style="color:var(--text-dim); font-size:0.8rem;">Experience:</strong> <span style="color:var(--text-main);">${escapeHtml(String(experience))} yrs</span></div>` : ''}
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
        🔒 Authorized Access Verified &bull; Decrypted for Recruiter View
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
        <button class="btn btn-danger btn-sm" onclick="deleteJobOpening('${j.job_id}', '${j.title.replace(/'/g, "\\'")}')">🗑️ Delete</button>
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

    container.innerHTML = notifs.map(n => `
      <div class="card" style="border-left: 3px solid ${n.days_inactive >= 90 || n.severity === 'danger' ? 'var(--danger)' : 'var(--warning)'};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; margin-bottom:0.5rem; flex-wrap:wrap;">
          <div>
            <div style="display:flex; align-items:center; gap:0.5rem;">
              <span class="file-status-badge ${n.days_inactive >= 90 ? 'badge-failed' : 'badge-processing'}">
                ${n.days_inactive >= 90 ? '3+ Months Inactive' : 'Inactivity Notice'}
              </span>
              <strong style="font-size:0.95rem; color:var(--text-main);">${escapeHtml(n.title)}</strong>
              ${!n.is_read ? '<span class="file-status-badge badge-ready" style="font-size:0.68rem; padding:1px 5px;">NEW</span>' : ''}
            </div>
            <div style="font-size:0.8rem; color:var(--text-dim); margin-top:0.25rem;">
              Candidate: <strong>${n.doc_id}</strong> &bull; Inactive for <strong>${n.days_inactive} days</strong> &bull; Alert generated ${formatDate(n.created_at)}
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
            <button class="btn btn-secondary btn-sm" onclick="viewCandidateDetailsModal('${n.doc_id}')" title="View candidate and contact details" style="padding:0.25rem 0.5rem; font-size:0.95rem; line-height:1;">👁️</button>
            <button class="btn btn-secondary btn-sm" onclick="viewOriginalResume('${n.doc_id}')">Original Resume</button>
            <button class="btn btn-secondary btn-sm" onclick="launchImprovementForCandidate('${n.doc_id}')">Improve Resume</button>
            ${!n.is_read ? `<button class="btn btn-secondary btn-sm" onclick="markNotificationAsRead('${n.id}')">Mark Read</button>` : ''}
            <button class="btn btn-danger btn-sm" onclick="confirmDeleteResume('${n.doc_id}', 'Candidate ${n.doc_id}')">Delete</button>
          </div>
        </div>
      </div>
    `).join("");
  } catch (err) {
    container.innerHTML = `<div class="card" style="color:var(--danger);">Error loading notifications: ${err.message}</div>`;
  }
}

function openEscalationEmailModal(docId, daysInactive, reason = null) {
  document.getElementById("email-modal-doc-id").value = docId;
  document.getElementById("email-modal-recipient").value = "damayanthi.u@riscrm.com";
  
  const days = daysInactive || 90;
  const reasonText = reason || `Candidate ${docId} has not had any recruiter action recorded for ${days} days (over 3 months review SLA). Please review the attached original resume for leadership decision or candidate re-engagement.`;
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
    btn.textContent = "📧 Send Email with Resume Attached";
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
        statusEl.textContent = "Online 🟢";
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

