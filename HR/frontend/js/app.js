// Application State
const AppState = {
  currentTab: "dashboard",
  resumes: [],
  jobs: [],
  selectedJobId: null,
  selectedResumeDocId: null,
  activeMatchResults: null,
  inactivityThreshold: 30,
  highlightPending: false,
  notificationsSeen: false,
  uploadedResumes: [],
  matchScope: "uploaded",
  allFollowups: []
};

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
  renderUploadedFilesList();
  validateMatchForm();
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

function onMatchScopeChanged() {
  const scopeUploaded = document.getElementById("scope-uploaded-only");
  AppState.matchScope = (scopeUploaded && scopeUploaded.checked) ? "uploaded" : "all";
  validateMatchForm();
}

function renderUploadedFilesList() {
  const listContainer = document.getElementById("match-upload-progress");
  const countPill = document.getElementById("match-uploaded-count-pill");
  const clearBtn = document.getElementById("btn-clear-all-uploads");
  const scopeUploadedCount = document.getElementById("scope-uploaded-count");
  const scopeAllCount = document.getElementById("scope-all-count");

  // Keep in sync with actual existing resumes in database
  if (AppState.resumes && AppState.resumes.length) {
    const existingDocIds = new Set(AppState.resumes.map(r => r.doc_id));
    AppState.uploadedResumes = AppState.uploadedResumes.filter(item => {
      return !item.doc_id || existingDocIds.has(item.doc_id);
    });
    saveUploadedResumesToStorage();
  }

  const uploadedCount = AppState.uploadedResumes.length;
  const readyCount = AppState.uploadedResumes.filter(r => r.doc_id && r.status === "ready").length;

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

  if (scopeUploadedCount) {
    scopeUploadedCount.textContent = readyCount;
  }
  if (scopeAllCount) {
    scopeAllCount.textContent = AppState.resumes.length;
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
    let badgeClass = "badge-ready";
    if (item.status === "failed") badgeClass = "badge-failed";
    if (item.status === "duplicate") badgeClass = "badge-duplicate";

    const escapedFilename = (item.filename || "Resume").replace(/'/g, "\\'");

    row.innerHTML = `
      <div style="display:flex; align-items:center; gap:0.65rem; min-width:0; flex:1; margin-right:0.75rem;">
        <span style="font-size:1.15rem; flex-shrink:0;">📄</span>
        <div style="min-width:0; overflow:hidden;">
          <div style="font-weight:600; color:#fff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${item.filename}">
            ${item.filename}
          </div>
          <div style="display:flex; align-items:center; gap:0.4rem; font-size:0.75rem; color:var(--text-muted); margin-top:2px;">
            ${item.doc_id ? `<span class="candidate-doc-tag" style="margin:0;">ID: ${item.doc_id}</span>` : ""}
            ${item.error ? `<span style="color:var(--danger); font-size:0.75rem;">${item.error}</span>` : ""}
          </div>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:0.5rem; flex-shrink:0;">
        <span class="file-status-badge ${badgeClass}">${item.status.toUpperCase()}</span>
        <button type="button" class="btn btn-danger btn-sm" onclick="removeUploadedResume('${item.doc_id || ''}', '${escapedFilename}', ${idx})" title="Remove this uploaded resume" style="font-size:0.75rem; padding:0.25rem 0.6rem; border-radius:var(--radius-sm); display:inline-flex; align-items:center; gap:0.25rem;">
          🗑️ Remove
        </button>
      </div>
    `;
    listContainer.appendChild(row);
  });
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

  const scopeRadio = document.getElementById("scope-uploaded-only");
  const isUploadedScope = scopeRadio ? scopeRadio.checked : (AppState.matchScope === "uploaded");

  const readyUploadedCount = AppState.uploadedResumes.filter(r => r.doc_id && r.status === "ready").length;
  const hasResumes = isUploadedScope ? (readyUploadedCount > 0) : (AppState.resumes.length > 0);

  if (validationError) {
    if (isNaN(countVal) || countVal <= 0) {
      validationError.textContent = "Please enter a valid positive integer greater than 0.";
    } else if (countVal > 100) {
      validationError.textContent = "Maximum candidate count limit is 100.";
    } else if (isUploadedScope && readyUploadedCount === 0) {
      validationError.textContent = "No uploaded resumes ready. Please upload candidate resumes above or select 'Entire Resume Library'.";
    } else if (!isUploadedScope && AppState.resumes.length === 0) {
      validationError.textContent = "No processed resumes in database. Please upload resumes first.";
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

  const requestedCount = parseInt(input.value, 10);
  const text = jdText.value.trim();

  const scopeRadio = document.getElementById("scope-uploaded-only");
  const isUploadedScope = scopeRadio ? scopeRadio.checked : (AppState.matchScope === "uploaded");

  let targetDocIds = null;
  if (isUploadedScope) {
    targetDocIds = AppState.uploadedResumes
      .filter(r => r.doc_id && r.status === "ready")
      .map(r => r.doc_id);

    if (!targetDocIds.length) {
      showToast("No ready uploaded resumes available. Please upload resumes or select 'Entire Library'.", "warning");
      return;
    }
  }

  btn.disabled = true;
  btn.textContent = "Analyzing & Matching...";
  container.innerHTML = `<div class='text-center text-muted' style='padding:2rem;'>
    Processing candidate evidence ${isUploadedScope ? `for ${targetDocIds.length} uploaded resume(s)` : 'across entire library'}...
  </div>`;

  try {
    const result = await API.matchCandidates(
      requestedCount,
      AppState.selectedJobId,
      AppState.selectedJobId ? null : text,
      targetDocIds
    );

    AppState.activeMatchResults = result;
    renderMatchResults(result, isUploadedScope ? targetDocIds.length : null);
    showToast(`Evaluated ${result.returned_count} candidate match(es)!`, "success");
  } catch (err) {
    container.innerHTML = `<div class='card' style='border-color:var(--danger); color:var(--danger);'>Error: ${err.message}</div>`;
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Show Results";
  }
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
        <strong>Search Scope: Uploaded Resumes Only</strong> &mdash; Evaluated <strong>${evaluatedUploadedCount}</strong> uploaded candidate resume(s). Stored library records were excluded from this run.
      </div>
    `;
    container.appendChild(scopeBanner);
  } else {
    const scopeBanner = document.createElement("div");
    scopeBanner.style.cssText = "display:flex; align-items:center; gap:0.6rem; padding:0.7rem 1.1rem; margin-bottom:1.2rem; background:rgba(99,102,241,0.1); border:1px solid rgba(99,102,241,0.25); border-radius:var(--radius-sm); color:var(--text-main); font-size:0.86rem;";
    scopeBanner.innerHTML = `
      <span style="font-size:1.2rem;">📚</span>
      <div>
        <strong>Search Scope: Entire Resume Library</strong> &mdash; Evaluated across all candidate resumes stored in the database.
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

  data.results.forEach(cand => {
    const card = document.createElement("div");
    card.className = `candidate-card ${cand.rank === 1 ? "rank-1" : ""}`;

    const scoreClass = cand.internal_match_score >= 80 ? "score-high" : (cand.internal_match_score >= 60 ? "score-medium" : "score-moderate");

    card.innerHTML = `
      <div class="candidate-header">
        <div class="candidate-meta">
          <div class="rank-badge">#${cand.rank}</div>
          <div>
            <div class="candidate-id-title">${cand.candidate_label}</div>
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
          ${cand.matched_requirements.map(m => `<span class="tag-matched" title="${m.evidence}">✓ ${m.requirement}</span>`).join("")}
          ${cand.gaps.map(g => `<span class="tag-gap" title="${g.recommendation}">⚠️ ${g.requirement}</span>`).join("")}
        </div>
        <div class="explanation-text">${cand.explanation}</div>
      </div>

      <div class="candidate-actions">
        <div class="actions-group">
          <button class="btn btn-secondary btn-sm" onclick="viewOriginalResume('${cand.doc_id}')">📄 View Original Resume</button>
          <button class="btn btn-secondary btn-sm" onclick="launchImprovementForCandidate('${cand.doc_id}')">✏️ Improve Resume</button>
        </div>
        <div class="actions-group">
          <button class="btn btn-secondary btn-sm" onclick="recordCandidateQuickAction('${cand.doc_id}', 'shortlisted')">⭐ Shortlist</button>
          <button class="btn btn-secondary btn-sm" onclick="recordCandidateQuickAction('${cand.doc_id}', 'contacted')">✉️ Contact</button>
          <button class="btn btn-secondary btn-sm" onclick="recordCandidateQuickAction('${cand.doc_id}', 'reviewed')">✓ Reviewed</button>
          <button class="btn btn-sm" onclick="quickMarkHired('${cand.doc_id}')" style="background:rgba(16,185,129,0.18); color:#10b981; border:1px solid rgba(16,185,129,0.45); font-weight:600;" title="Mark candidate as Hired">🎉 Hire</button>
        </div>
      </div>
    `;

    container.appendChild(card);
  });
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
  API.recordResumeOpened(docId).catch(() => {});
  window.open(`/api/resumes/${docId}/file`, "_blank");
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
    showToast(`🎉 Candidate ${docId} successfully marked as HIRED!`, "success");
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
function initImprovementTab() {
  const resumeSelect = document.getElementById("improve-resume-select");
  const jobSelect = document.getElementById("improve-job-select");

  if (resumeSelect) {
    resumeSelect.innerHTML = "<option value=''>-- Select Candidate Resume --</option>";
    AppState.resumes.forEach(r => {
      const opt = document.createElement("option");
      opt.value = r.doc_id;
      opt.textContent = `${r.doc_id} — ${r.original_filename}`;
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

  setupImprovementDropzone();
  
  const cornerBtn = document.getElementById("btn-corner-download-word");
  if (cornerBtn) {
    cornerBtn.style.display = AppState.selectedResumeDocId ? "inline-block" : "none";
  }
}

function onImproveResumeSelected() {
  const sel = document.getElementById("improve-resume-select");
  if (!sel) return;
  const docId = sel.value;
  AppState.selectedResumeDocId = docId;
  const statusEl = document.getElementById("improve-upload-status");
  if (statusEl) statusEl.style.display = "none";
  
  const cornerBtn = document.getElementById("btn-corner-download-word");
  if (cornerBtn) {
    cornerBtn.style.display = docId ? "inline-block" : "none";
  }

  if (docId) {
    API.recordResumeOpened(docId).catch(() => {});
    loadVersionHistory(docId);
    fetchAndPopulateCandidatePII(docId);
  }
}

async function fetchAndPopulateCandidatePII(targetDocId = null) {
  const docId = targetDocId || document.getElementById("improve-resume-select")?.value;
  if (!docId) return;

  const nameInput = document.getElementById("improve-cand-name");
  const roleInput = document.getElementById("improve-cand-role");
  const phoneInput = document.getElementById("improve-cand-phone");
  const emailInput = document.getElementById("improve-cand-email");
  const locInput = document.getElementById("improve-cand-location");
  const linksInput = document.getElementById("improve-cand-links");

  const candidate = AppState.resumes.find(r => r.doc_id === docId);
  const rawFilename = candidate?.original_filename || "";

  function deriveNameFromFilename(fn) {
    if (!fn) return "Candidate Professional";
    let clean = fn.replace(/[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc|txt)$/i, "");
    clean = clean.replace(/[\-_]+/g, " ").trim();
    const invalidWords = new Set(["resume", "cv", "final", "resumee", "sfdc", "developer", "engineer", "vault", "qmsqdocs", "qa", "salesforce", "se"]);
    const words = clean.split(/\s+/).filter(w => !invalidWords.has(w.toLowerCase()));
    if (words.length) {
      return words.map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(" ");
    }
    return clean;
  }

  try {
    const pii = await API.getResumePII(docId);
    const invalidNames = new Set(["SUMMARY", "OBJECTIVE", "PROFILE", "RESUME", "CURRICULUM VITAE", "CV", "CANDIDATE", "PROFESSIONAL SUMMARY"]);
    
    let resolvedName = pii.name && !invalidNames.has(pii.name.toUpperCase()) ? pii.name : deriveNameFromFilename(rawFilename);
    if (nameInput) nameInput.value = resolvedName;

    // Role
    if (roleInput && !roleInput.value) {
      const jobSel = document.getElementById("improve-job-select");
      const jobText = (jobSel && jobSel.selectedIndex > 0) ? jobSel.options[jobSel.selectedIndex].text.split("(")[0].trim() : "";
      roleInput.value = jobText || "Technical Professional";
    }

    // Phone (filter out year ranges like 2023-2025)
    if (phoneInput) {
      if (pii.phone && !/^\d{4}\s*-\s*\d{4}$/.test(pii.phone.trim())) {
        phoneInput.value = pii.phone;
      } else if (!phoneInput.value) {
        phoneInput.value = "";
      }
    }

    // Email
    if (emailInput) {
      if (pii.email) emailInput.value = pii.email;
    }

    // Location
    if (locInput) {
      if (pii.address) locInput.value = pii.address;
    }

    // Auto-apply to draft if revised content is already open
    applyPersonalDetailsToDraft(false);
  } catch (err) {
    if (nameInput && !nameInput.value) {
      nameInput.value = deriveNameFromFilename(rawFilename);
    }
  }
}

function applyPersonalDetailsToDraft(notify = true) {
  const contentEl = document.getElementById("version-revised-content");
  if (!contentEl) return;

  const name = document.getElementById("improve-cand-name")?.value.trim() || "CANDIDATE PROFESSIONAL";
  const role = document.getElementById("improve-cand-role")?.value.trim();
  const phone = document.getElementById("improve-cand-phone")?.value.trim();
  const email = document.getElementById("improve-cand-email")?.value.trim();
  const loc = document.getElementById("improve-cand-location")?.value.trim();
  const links = document.getElementById("improve-cand-links")?.value.trim();

  const contactItems = [];
  if (phone) contactItems.push(phone.toLowerCase().startsWith("phone") ? phone : `Phone: ${phone}`);
  if (email) contactItems.push(email.toLowerCase().startsWith("email") ? email : `Email: ${email}`);
  if (loc) contactItems.push(loc.toLowerCase().startsWith("location") ? loc : `Location: ${loc}`);
  const contactLine = contactItems.join(" | ");

  const headerLines = [`# ${name.toUpperCase()}`];
  if (role) headerLines.push(role.toUpperCase());
  if (contactLine) headerLines.push(contactLine);
  if (links) headerLines.push(links);
  const newHeader = headerLines.join("\n") + "\n\n";

  let currentContent = contentEl.value;
  // Identify where resume body sections begin
  const sectionKeywords = ["## ", "PROFESSIONAL SUMMARY", "EXECUTIVE SUMMARY", "SUMMARY", "CAREER OBJECTIVE", "OBJECTIVE", "TECHNICAL SKILLS", "SKILLS", "EXPERIENCE", "WORK EXPERIENCE", "EDUCATION", "PROJECTS"];
  const lines = currentContent.split("\n");
  let bodyStartIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i].trim();
    if (sectionKeywords.some(kw => l.startsWith(kw) || l.toUpperCase().startsWith(kw))) {
      bodyStartIdx = i;
      break;
    }
  }

  if (bodyStartIdx !== -1) {
    contentEl.value = newHeader + lines.slice(bodyStartIdx).join("\n");
  } else {
    // If no explicit section headers found yet, replace top lines
    const firstSecIdx = currentContent.indexOf("\n## ");
    if (firstSecIdx !== -1) {
      contentEl.value = newHeader + currentContent.slice(firstSecIdx + 1);
    } else {
      contentEl.value = newHeader + currentContent;
    }
  }

  if (notify) {
    showToast("✨ Applied candidate personal details to resume draft!", "success");
  }
}

let _personalDetailsTimer = null;
function onPersonalDetailsInputChange() {
  clearTimeout(_personalDetailsTimer);
  _personalDetailsTimer = setTimeout(() => {
    applyPersonalDetailsToDraft(false);
  }, 400);
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
      handleImprovementFileUpload(e.dataTransfer.files);
    }
  };

  fileInput.onchange = () => {
    if (fileInput.files?.length) {
      handleImprovementFileUpload(fileInput.files);
    }
  };
}

async function handleImprovementFileUpload(fileList) {
  if (!fileList || !fileList.length) return;
  const file = fileList[0];
  const statusEl = document.getElementById("improve-upload-status");

  if (statusEl) {
    statusEl.style.display = "block";
    statusEl.innerHTML = `<span style="color:var(--accent-cyan);">⏳ Uploading & parsing "${file.name}"...</span>`;
  }

  const formData = new FormData();
  formData.append("files", file);

  try {
    const res = await API.uploadResumes(formData);
    const uploadedItem = res.results?.[0];

    if (!uploadedItem || uploadedItem.status === "failed") {
      throw new Error(uploadedItem?.error || "Failed to parse resume");
    }

    const docId = uploadedItem.doc_id;
    await refreshDataCaches();
    AppState.selectedResumeDocId = docId;
    initImprovementTab();

    const sel = document.getElementById("improve-resume-select");
    if (sel) sel.value = docId;

    const cornerBtn = document.getElementById("btn-corner-download-word");
    if (cornerBtn) cornerBtn.style.display = "inline-block";

    if (statusEl) {
      statusEl.style.display = "block";
      statusEl.innerHTML = `
        <span class="file-status-badge badge-ready">✓ Uploaded & Ready</span>
        <strong style="color:#fff; margin-left:6px;">${uploadedItem.filename}</strong> (ID: <strong>${docId}</strong>) selected!
      `;
    }

    loadVersionHistory(docId);
    fetchAndPopulateCandidatePII(docId);
    showToast(`Resume "${uploadedItem.filename}" uploaded & selected!`, "success");
  } catch (err) {
    if (statusEl) {
      statusEl.style.display = "block";
      statusEl.innerHTML = `<span style="color:var(--danger);">⚠️ Upload failed: ${err.message}</span>`;
    }
    showToast(`Upload failed: ${err.message}`, "error");
  }
}

function launchImprovementForCandidate(docId) {
  AppState.selectedResumeDocId = docId;
  switchTab("improvement");
  const sel = document.getElementById("improve-resume-select");
  if (sel) sel.value = docId;
  loadVersionHistory(docId);
  fetchAndPopulateCandidatePII(docId);
}

async function runResumeImprovementAnalysis() {
  const docId = document.getElementById("improve-resume-select").value;
  const jobId = document.getElementById("improve-job-select").value;
  const customJd = document.getElementById("improve-custom-jd").value.trim();
  const btn = document.getElementById("btn-analyze-improvement");
  const container = document.getElementById("improvement-results-area");

  if (!docId) {
    showToast("Please select a candidate resume", "warning");
    return;
  }
  if (!jobId && (!customJd || customJd.length < 10)) {
    showToast("Please choose a saved job or enter job description text", "warning");
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

  btn.disabled = true;
  btn.textContent = "Analyzing Gaps & Suggestions...";
  container.innerHTML = "<div class='text-center text-muted' style='padding:2rem;'>Comparing candidate profile evidence against job requirements...</div>";

  try {
    const analysis = await API.analyzeImprovement(docId, jobId || null, jobId ? null : customJd, personalDetails);
    renderImprovementAnalysis(analysis);
    showToast("Resume improvement recommendations generated!", "success");
    loadVersionHistory(docId);
  } catch (err) {
    container.innerHTML = `<div class='card' style='color:var(--danger);'>${err.message}</div>`;
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze Resume Alignment";
  }
}

function renderImprovementAnalysis(data) {
  window._currentImprovementData = data;
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
    <div class="improvement-score-banner">
      <div>
        <div style="font-size:0.8rem; text-transform:uppercase; letter-spacing:0.04em; color:var(--text-dim);">Target Role Alignment</div>
        <h2 style="font-family:var(--font-heading); font-size:1.6rem; font-weight:700;">${data.job_title}</h2>
        <div style="font-size:0.82rem; color:var(--text-muted); margin-top:0.3rem;">Evaluating Document: <strong>${data.doc_id}</strong></div>
      </div>
      <div style="text-align:right;">
        <div style="font-family:var(--font-heading); font-size:2.4rem; font-weight:800; color:${data.internal_match_score >= 80 ? 'var(--success)' : 'var(--warning)'};">
          ${data.internal_match_score}<span style="font-size:1.2rem; color:var(--text-dim);">/100</span>
        </div>
        <div style="font-size:0.75rem; color:var(--text-dim); text-transform:uppercase;">Internal Alignment Score</div>
      </div>
    </div>

    <div class="disclaimer-box">
      <strong>⚠️ Transparency Disclaimer:</strong> ${data.score_disclaimer}
    </div>

    <div class="grid-2" style="margin-bottom:1.6rem;">
      <div class="card">
        <h4 style="margin-bottom:0.8rem; color:var(--success);">✓ Demonstrated Requirements (${data.matched_requirements.length})</h4>
        <div style="display:flex; flex-direction:column; gap:0.5rem;">
          ${data.matched_requirements.map(m => `
            <div style="background:rgba(255,255,255,0.02); padding:0.6rem; border-radius:6px; font-size:0.84rem;">
              <strong>${m.requirement}</strong>
              <div style="color:var(--text-dim); font-size:0.78rem;">${m.evidence}</div>
            </div>
          `).join("")}
        </div>
      </div>

      <div class="card">
        <h4 style="margin-bottom:0.8rem; color:var(--danger);">⚠️ Gaps & Unverified Requirements (${data.not_demonstrated.length + data.partially_demonstrated.length})</h4>
        <div style="display:flex; flex-direction:column; gap:0.5rem;">
          ${data.not_demonstrated.map(g => `
            <div style="background:rgba(255,255,255,0.02); padding:0.6rem; border-radius:6px; font-size:0.84rem;">
              <strong>${g.requirement}</strong>
              <div style="color:#fca5a5; font-size:0.78rem;">${g.recommendation || "Not demonstrated in provided resume"}</div>
            </div>
          `).join("")}
          ${data.partially_demonstrated.map(p => `
            <div style="background:rgba(255,255,255,0.02); padding:0.6rem; border-radius:6px; font-size:0.84rem;">
              <strong>${p.requirement}</strong>
              <div style="color:#fde68a; font-size:0.78rem;">${p.reason}</div>
            </div>
          `).join("")}
        </div>
      </div>
    </div>

    <h3 style="font-family:var(--font-heading); margin-bottom:1rem;">Evidence-Grounded Rewrite Suggestions</h3>
    <div id="rewrites-container">
      ${data.suggested_rewrites.map((s, idx) => `
        <div class="suggestion-card">
          <div class="suggestion-header">
            <strong>Section: ${s.section}</strong>
            ${s.requires_user_confirmation ? '<span class="confirmation-badge">⚠️ User Confirmation Required</span>' : '<span class="file-status-badge badge-ready">Verified</span>'}
          </div>
          <div class="diff-box">
            <div class="diff-current">Current: "${s.current_evidence}"</div>
            <div class="diff-suggested">Suggested: "${s.suggested_text}"</div>
          </div>
          <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:0.8rem;">
            <strong>Rationale:</strong> ${s.rationale}
          </div>
          <div style="display:flex; gap:0.6rem;">
            <button class="btn btn-secondary btn-sm" onclick="applySuggestedRewrite('${data.doc_id}', ${idx})">Insert into Revised Draft</button>
          </div>
        </div>
      `).join("")}
    </div>

    <div class="card" style="margin-top:2rem;">
      <div style="background:rgba(99,102,241,0.08); border:1px solid rgba(99,102,241,0.25); border-radius:var(--radius-sm); padding:1rem 1.2rem; margin-bottom:1.2rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.8rem; margin-bottom:0.6rem;">
          <div style="display:flex; align-items:center; gap:0.6rem;">
            <span style="font-size:1.3rem;">⚡</span>
            <div>
              <strong style="color:#fff; font-size:1rem;">Grok LLM Optimized Resume Draft</strong>
              <span class="file-status-badge badge-ready" style="margin-left:8px; font-size:0.72rem;">${data.llm_model || 'Grok-2'}</span>
            </div>
          </div>
          <div style="display:flex; gap:0.5rem;">
            <button type="button" class="btn btn-secondary btn-sm" onclick="toggleResumeDraftView('improved')" style="font-size:0.75rem;">✨ Grok Improved Draft</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="toggleResumeDraftView('original')" style="font-size:0.75rem;">📄 Original Raw Text</button>
          </div>
        </div>
        <p style="font-size:0.84rem; color:var(--text-muted); margin-bottom:0.6rem;">
          ${data.change_summary || 'Candidate resume has been restructured with target role alignment, categorized competencies, and quantifiable metrics.'}
        </p>
        ${data.key_enhancements && data.key_enhancements.length ? `
          <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">
            ${data.key_enhancements.map(e => `<span style="font-size:0.72rem; padding:2px 8px; border-radius:4px; background:rgba(6,182,212,0.15); color:var(--accent-cyan); border:1px solid rgba(6,182,212,0.25);">✓ ${e}</span>`).join("")}
          </div>
        ` : ''}
      </div>

      <h3 style="font-family:var(--font-heading); margin-bottom:0.8rem;">Interactive Revised Resume Editor</h3>
      <div style="font-size:0.82rem; color:var(--text-muted); margin-bottom:1rem;">
        Review and edit the candidate's upgraded resume. All modifications, categorized skills, and STAR metrics will be preserved when downloading the Word document.
      </div>
      <div class="form-group">
        <label class="form-label">Version Change Summary</label>
        <input type="text" id="version-change-summary" class="form-control" placeholder="e.g. Aligned project terminology and verified requirements." value="${data.change_summary ? data.change_summary.replace(/"/g, '&quot;') : 'Target-aligned resume optimization with quantifiable STAR metrics and categorized competencies.'}">
      </div>
      <div class="form-group">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
          <label class="form-label" style="margin-bottom:0;">Revised Resume Content (Ready for Word Export)</label>
          <span style="font-size:0.75rem; color:var(--success);">✓ Substantive enhancements loaded</span>
        </div>
        <textarea id="version-revised-content" class="form-control" style="min-height:380px; font-family:monospace; font-size:0.86rem; line-height:1.5;">${data.improved_resume_text || data.original_text_preview}</textarea>
      </div>
      <div style="display:flex; justify-content:flex-end; gap:0.8rem; align-items:center;">
        <button class="btn btn-secondary" onclick="saveRevisedVersionDraft('${data.doc_id}')">💾 Save as Version in DMS</button>
        <button class="btn btn-primary" id="btn-agent-download-word" onclick="downloadImprovedWordResume('${data.doc_id}')">📥 Download as Word (.docx)</button>
      </div>
    </div>
  `;

  // Auto-apply personal details to the revised content editor
  applyPersonalDetailsToDraft(false);
}

function toggleResumeDraftView(viewMode) {
  const textarea = document.getElementById("version-revised-content");
  const data = window._currentImprovementData;
  if (!textarea || !data) return;
  if (viewMode === "original") {
    textarea.value = data.original_text_preview || "";
    showToast("Displaying original candidate text", "info");
  } else {
    textarea.value = data.improved_resume_text || data.original_text_preview || "";
    showToast("Displaying Grok AI improved resume draft", "success");
  }
}

function applySuggestedRewrite(docId, index) {
  const textarea = document.getElementById("version-revised-content");
  if (!textarea || !window._currentImprovementData) return;
  const suggestion = window._currentImprovementData.suggested_rewrites?.[index];
  if (!suggestion) return;

  const current = (suggestion.current_evidence || "").trim();
  const suggested = (suggestion.suggested_text || "").trim();

  if (current && textarea.value.includes(current)) {
    textarea.value = textarea.value.replace(current, suggested);
    showToast(`Replaced: "${current.slice(0, 32)}..." with suggested revision`, "success");
  } else {
    textarea.value += `\n\n[${suggestion.section.toUpperCase()} ENHANCEMENT]\n${suggested}\n`;
    showToast(`Appended suggested ${suggestion.section} rewrite to draft`, "info");
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

  try {
    const res = await API.saveRevisedVersion(docId, summaryInput.value.trim(), contentInput.value.trim(), true, personalDetails);
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
  const jobSelect = document.getElementById("improve-job-select");

  const summary = summaryInput ? summaryInput.value.trim() : "Updated Professional Word Resume";
  let content = contentInput ? contentInput.value.trim() : "";
  const targetRole = (jobSelect && jobSelect.options[jobSelect.selectedIndex]?.text) || "Senior Technical Professional";

  const btn = document.getElementById("btn-agent-download-word");
  const origBtnText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "⏳ Generating Word (.docx)...";
  }

  try {
    // If content is empty (e.g. clicked quick download before analysis), load draft from resume profile
    if (!content) {
      const resume = AppState.resumes.find(r => r.doc_id === docId);
      const filename = resume?.original_filename || docId;
      content = `CANDIDATE PROFILE - ${docId}\nDocument: ${filename}\nTarget Alignment: ${targetRole}\n\nKey Qualifications:\n- Technical and professional background aligned to target job profile.\n- Verified experience extracted from repository.`;
    }

    const personalDetails = {
      name: document.getElementById("improve-cand-name")?.value.trim(),
      role: document.getElementById("improve-cand-role")?.value.trim(),
      phone: document.getElementById("improve-cand-phone")?.value.trim(),
      email: document.getElementById("improve-cand-email")?.value.trim(),
      location: document.getElementById("improve-cand-location")?.value.trim(),
      links: document.getElementById("improve-cand-links")?.value.trim()
    };

    const res = await API.generateWordResume(docId, content, summary, targetRole, personalDetails);
    
    // Automatically trigger browser download of .docx
    const a = document.createElement("a");
    a.href = res.download_url;
    a.download = res.filename || `${docId}_Improved_Resume.docx`;
    document.body.appendChild(a);
    a.click();
    a.remove();

    showToast(`✨ Microsoft Word resume "${res.filename || 'Improved_Resume.docx'}" downloaded!`, "success");
    loadVersionHistory(docId);
    await refreshDataCaches();
  } catch (err) {
    showToast(`Error generating Word document: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origBtnText || "📥 Download as Word (.docx)";
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
// 4. FOLLOW-UPS & CANDIDATE DEVELOPMENT
// ==========================================
async function loadFollowups() {
  const slider = document.getElementById("inactivity-days-slider");
  const days = slider ? slider.value : AppState.inactivityThreshold;
  const badgeDays = document.getElementById("inactivity-days-label");
  if (badgeDays) badgeDays.textContent = `${days} Days`;

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
  const slider = document.getElementById("inactivity-days-slider");
  const days = slider ? parseInt(slider.value, 10) : AppState.inactivityThreshold;

  const all = AppState.allFollowups || [];
  const filtered = all.filter(item => {
    // 1. Status Filter
    if (statusFilter && item.status.toLowerCase() !== statusFilter) {
      return false;
    }

    // 2. Search Text
    if (!searchTerm) return true;
    const searchTarget = [
      item.doc_id,
      item.candidate_label,
      item.status,
      item.assigned_to,
      item.last_action_type,
      item.notes,
      item.suggested_action
    ].filter(Boolean).join(" ").toLowerCase();

    return searchTarget.includes(searchTerm);
  });

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
    if (AppState.highlightPending && item.status === "pending_review") {
      tr.className = "row-pending-glow";
    }

    // Determine status badge class and text
    let statusBadgeHtml = "";
    if (item.status === "hired") {
      statusBadgeHtml = `<span class="file-status-badge badge-hired" style="background:rgba(16,185,129,0.22); color:#10b981; border:1px solid rgba(16,185,129,0.45); font-weight:700;">🎉 HIRED</span>`;
    } else if (item.is_overdue) {
      statusBadgeHtml = `
        <span class="file-status-badge badge-failed">${item.status.toUpperCase()}</span>
        <span style="color:var(--danger); font-size:0.72rem; display:block; font-weight:700;">OVERDUE</span>
      `;
    } else if (item.status === "shortlisted" || item.status === "reviewed") {
      statusBadgeHtml = `<span class="file-status-badge badge-ready">${item.status.toUpperCase()}</span>`;
    } else {
      statusBadgeHtml = `<span class="file-status-badge badge-processing">${item.status.toUpperCase()}</span>`;
    }

    tr.innerHTML = `
      <td><button type="button" class="doc-id-link" onclick="openCandidateRemarksModal('${item.doc_id}')" title="Click to view remarks and activity history for ${item.doc_id}"><strong>${item.doc_id}</strong> <span style="font-size:0.75rem; opacity:0.85;">💬</span></button></td>
      <td>
        ${statusBadgeHtml}
        ${item.email_sent ? `<span class="file-status-badge badge-ready" style="font-size:0.68rem; margin-top:3px; display:inline-block;" title="Escalation email sent to ${item.email_sent_to}">✓ Emailed</span>` : ''}
      </td>
      <td>
        <span style="font-weight:600; color:${item.status === 'hired' ? 'var(--success)' : (item.days_inactive >= 90 ? 'var(--danger)' : (item.days_inactive >= days ? 'var(--warning)' : 'var(--text-main)'))};">
          ${item.days_inactive} days
        </span>
        ${item.status !== 'hired' && item.days_inactive >= days ? `<span style="font-size:0.7rem; color:var(--warning); display:block;">(Inactive &gt; ${days}d)</span>` : ''}
        ${item.status !== 'hired' && item.days_inactive >= 90 ? '<span style="font-size:0.7rem; color:#fca5a5; display:block;">(3+ months)</span>' : ''}
      </td>
      <td>
        <div style="font-weight:600; font-size:0.82rem; color:#e2e8f0;">${formatDateTime(item.last_opened_at || item.last_action_at)}</div>
        <div style="font-size:0.72rem; color:var(--text-dim);">${item.last_action_type || 'Active'} by ${item.assigned_to || 'admin'}</div>
      </td>
      <td>${formatDate(item.next_action_at)}</td>
      <td style="max-width:240px; font-size:0.8rem; color:${item.status === 'hired' ? '#6ee7b7' : '#cbd5e1'};">${item.suggested_action}</td>
      <td>
        <div style="display:flex; flex-wrap:wrap; gap:0.35rem;">
          <button class="btn btn-secondary btn-sm" onclick="openActionModal('${item.doc_id}')" title="Record recruiter action & notes">Action</button>
          <button class="btn btn-primary btn-sm" onclick="openDevPlanModal('${item.doc_id}')" title="Candidate development plan">Dev Plan</button>
          <button class="btn btn-secondary btn-sm" onclick="openEscalationEmailModal('${item.doc_id}', ${item.days_inactive})" title="Send escalation email with resume attached">📧 Email</button>
          <button class="btn btn-danger btn-sm" onclick="confirmDeleteResume('${item.doc_id}', '${item.candidate_label}')" title="Permanently delete this candidate">🗑️ Delete</button>
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
    showToast(`🎉 Candidate ${docId} successfully marked as HIRED!`, "success");
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
    ? '<span class="file-status-badge badge-hired" style="background:rgba(16,185,129,0.22); color:#10b981; border:1px solid rgba(16,185,129,0.45); font-weight:700;">🎉 HIRED</span>'
    : `<span class="file-status-badge badge-processing">${currentStatus.replace('_', ' ').toUpperCase()}</span>`;

  if (banner) {
    banner.innerHTML = `
      <div>
        <div style="font-size:0.8rem; color:var(--text-dim); text-transform:uppercase;">Candidate Record</div>
        <strong style="font-size:1.05rem; color:#fff;">${docId}</strong>
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
  const docId = document.getElementById("action-modal-doc-id").value;
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

  try {
    await API.recordAction(docId, actionType, statusVal, notes, nextActionAt);
    showToast(actionType === "hired" ? `🎉 Candidate ${docId} successfully marked as HIRED!` : `Recorded action "${actionType}" for ${docId}`, "success");
    closeModal("record-action-modal");
    await refreshDataCaches();
    await loadFollowups();
    await loadLibrary();
    await loadDashboard();
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function openDevPlanModal(docId) {
  API.recordResumeOpened(docId).catch(() => {});
  const container = document.getElementById("dev-plan-modal-content");
  container.innerHTML = "<div class='text-center text-muted'>Synthesizing candidate development pathway based on demonstrated gaps...</div>";
  openModal("candidate-dev-plan-modal");

  try {
    const plan = await API.generateDevelopmentPlan(docId);
    container.innerHTML = `
      <h3 style="font-family:var(--font-heading); margin-bottom:0.4rem;">Development Plan: Candidate ${plan.doc_id}</h3>
      <div style="font-size:0.82rem; color:var(--text-muted); margin-bottom:1.2rem;">Target Competency Profile: <strong>${plan.target_role}</strong></div>

      <h4 style="font-size:0.9rem; color:var(--warning); margin-bottom:0.6rem;">1. Practical Project Enhancements</h4>
      <div style="display:flex; flex-direction:column; gap:0.6rem; margin-bottom:1.2rem;">
        ${plan.practical_projects.map(p => `
          <div style="background:rgba(255,255,255,0.03); padding:0.75rem; border-radius:8px; font-size:0.84rem;">
            <strong>${p.title}</strong>
            <div style="color:var(--text-dim); font-size:0.78rem;">${p.description}</div>
          </div>
        `).join("")}
      </div>

      <h4 style="font-size:0.9rem; color:var(--accent-cyan); margin-bottom:0.6rem;">2. Recommended Learning Resources</h4>
      <div style="display:flex; flex-direction:column; gap:0.6rem; margin-bottom:1.2rem;">
        ${plan.learning_recommendations.map(l => `
          <div style="background:rgba(255,255,255,0.03); padding:0.75rem; border-radius:8px; font-size:0.84rem;">
            <strong>${l.topic}</strong>
            <div style="color:var(--text-dim); font-size:0.78rem;">${l.resource}</div>
          </div>
        `).join("")}
      </div>

      <h4 style="font-size:0.9rem; color:var(--primary); margin-bottom:0.6rem;">3. Candidate Outreach Message Draft</h4>
      <div class="form-group">
        <textarea id="dev-plan-message-draft" class="form-control" style="min-height:120px; font-size:0.84rem;">${plan.recruiter_message_draft}</textarea>
      </div>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <button class="btn btn-secondary btn-sm" onclick="copyDraftMessage()">📋 Copy Message Draft</button>
        <button class="btn btn-primary btn-sm" onclick="launchImprovementForCandidate('${plan.doc_id}'); closeModal('candidate-dev-plan-modal');">✏️ Launch Resume Improvement</button>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div style="color:var(--danger);">Error: ${err.message}</div>`;
  }
}

function copyDraftMessage() {
  const txt = document.getElementById("dev-plan-message-draft");
  if (txt) {
    navigator.clipboard.writeText(txt.value);
    showToast("Message draft copied to clipboard!", "success");
  }
}

// ==========================================
// 5. RESUME LIBRARY WORKFLOW
// ==========================================
async function loadLibrary() {
  const query = document.getElementById("lib-search-input")?.value || "";
  const status = document.getElementById("lib-status-filter")?.value || "";
  const tbody = document.getElementById("library-table-body");
  if (!tbody) return;

  tbody.innerHTML = "<tr><td colspan='6' class='text-center text-muted'>Loading library records...</td></tr>";

  try {
    const list = await API.getResumes(query, status);
    tbody.innerHTML = "";

    if (!list.length) {
      tbody.innerHTML = "<tr><td colspan='6' class='text-center text-dim'>No resumes found matching filter.</td></tr>";
      return;
    }

    list.forEach(item => {
      const skills = item.profile?.skills || [];
      const tr = document.createElement("tr");

      const followupMatch = (AppState.allFollowups || []).find(f => f.doc_id === item.doc_id);
      let recStatus = (followupMatch?.status || item.latest_status || item.status || "pending_review").toLowerCase();
      if (recStatus === "ready" || recStatus === "uploaded") {
        recStatus = "pending_review";
      }

      let statusBadge = "";
      if (recStatus === "hired") {
        statusBadge = `<span class="file-status-badge badge-hired" style="background:rgba(16,185,129,0.22); color:#10b981; border:1px solid rgba(16,185,129,0.45); font-weight:700;">🎉 HIRED</span>`;
      } else if (recStatus === "shortlisted" || recStatus === "reviewed") {
        statusBadge = `<span class="file-status-badge badge-ready">${recStatus.toUpperCase()}</span>`;
      } else if (recStatus === "contacted") {
        statusBadge = `<span class="file-status-badge badge-ready" style="background:rgba(99,102,241,0.18); color:#818cf8; border:1px solid rgba(99,102,241,0.4);">CONTACTED</span>`;
      } else if (recStatus === "rejected") {
        statusBadge = `<span class="file-status-badge badge-failed">REJECTED</span>`;
      } else {
        statusBadge = `<span class="file-status-badge badge-processing">${recStatus.replace('_', ' ').toUpperCase()}</span>`;
      }

      tr.innerHTML = `
        <td><button type="button" class="doc-id-link" onclick="openCandidateRemarksModal('${item.doc_id}')" title="Click to view remarks and activity history for ${item.doc_id}"><strong>${item.doc_id}</strong> <span style="font-size:0.75rem; opacity:0.85;">💬</span></button></td>
        <td>${item.original_filename}</td>
        <td>${statusBadge}</td>
        <td style="max-width:220px;">
          <div style="display:flex; flex-wrap:wrap; gap:4px;">
            ${skills.slice(0, 3).map(s => `<span class="tag-matched" style="font-size:0.72rem; padding:1px 5px;">${s}</span>`).join("")}
            ${skills.length > 3 ? `<span class="tag-matched" style="font-size:0.72rem; padding:1px 5px;">+${skills.length - 3}</span>` : ""}
          </div>
        </td>
        <td>${formatDate(item.uploaded_at)}</td>
        <td>
          <div style="display:flex; gap:0.4rem;">
            <button class="btn btn-secondary btn-sm" onclick="viewOriginalResume('${item.doc_id}')">Original</button>
            <button class="btn btn-secondary btn-sm" onclick="viewPIIModal('${item.doc_id}')">🔒 PII</button>
            <button class="btn btn-danger btn-sm" onclick="confirmDeleteResume('${item.doc_id}', '${item.original_filename}')">🗑️ Delete</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='6' class='text-danger'>Error: ${err.message}</td></tr>`;
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

async function viewPIIModal(docId) {
  const content = document.getElementById("pii-modal-content");
  content.innerHTML = "<div class='text-center text-muted'>Decrypting personal information via authenticated encryption service...</div>";
  openModal("candidate-pii-modal");

  try {
    const pii = await API.getResumePII(docId);
    content.innerHTML = `
      <h3 style="font-family:var(--font-heading); margin-bottom:1rem;">Authorized Candidate Identity</h3>
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:8px; padding:1.2rem;">
        <div style="display:grid; grid-template-columns:120px 1fr; gap:0.8rem; font-size:0.88rem;">
          <strong style="color:var(--text-dim);">Document ID:</strong> <span>${pii.doc_id}</span>
          <strong style="color:var(--text-dim);">Full Name:</strong> <span>${pii.name || "N/A"}</span>
          <strong style="color:var(--text-dim);">Email:</strong> <span>${pii.email || "N/A"}</span>
          <strong style="color:var(--text-dim);">Phone:</strong> <span>${pii.phone || "N/A"}</span>
          <strong style="color:var(--text-dim);">Location:</strong> <span>${pii.address || "N/A"}</span>
        </div>
      </div>
      <div style="font-size:0.75rem; color:var(--text-dim); margin-top:0.9rem;">
        🛡️ Access Logged: Field access was recorded in the security audit trail with actor signature.
      </div>
    `;
  } catch (err) {
    content.innerHTML = `<div style="color:var(--danger);">${err.message}</div>`;
  }
}

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
        <div class="card" style="text-align:center; padding:3rem 1.5rem;">
          <div style="font-size:2.5rem; margin-bottom:0.8rem;">🎉</div>
          <h3 style="font-family:var(--font-heading); margin-bottom:0.4rem;">All Resumes Are Active</h3>
          <p style="font-size:0.88rem; color:var(--text-muted); max-width:480px; margin:0 auto;">
            No candidates have exceeded review thresholds or remained unnoticed for 3+ months. All candidate pipelines are up to date!
          </p>
        </div>
      `;
      return;
    }

    container.innerHTML = notifs.map(n => `
      <div class="card" style="border-left: 4px solid ${n.days_inactive >= 90 || n.severity === 'danger' ? 'var(--danger)' : 'var(--warning)'}; background: ${n.is_read ? 'rgba(255,255,255,0.015)' : 'rgba(255,255,255,0.03)'};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; margin-bottom:0.6rem;">
          <div>
            <div style="display:flex; align-items:center; gap:0.6rem;">
              <span class="file-status-badge ${n.days_inactive >= 90 ? 'badge-failed' : 'badge-processing'}" style="font-size:0.72rem;">
                ${n.days_inactive >= 90 ? '🔴 3+ MONTHS DORMANT' : '⚠️ INACTIVITY ALERT'}
              </span>
              <strong style="font-size:1.05rem; color:#fff;">${n.title}</strong>
              ${!n.is_read ? '<span style="font-size:0.7rem; background:rgba(99,102,241,0.25); color:var(--accent-cyan); padding:1px 6px; border-radius:4px; font-weight:700;">NEW</span>' : ''}
            </div>
            <div style="font-size:0.82rem; color:var(--text-dim); margin-top:0.25rem;">
              Candidate Document ID: <strong>${n.doc_id}</strong> • Inactive for <strong>${n.days_inactive} days</strong> • Alert generated ${formatDate(n.created_at)}
            </div>
          </div>
          <div style="text-align:right;">
            ${n.email_sent ? `
              <span class="file-status-badge badge-ready" style="font-size:0.76rem; padding:3px 8px;">
                ✓ Emailed to ${n.email_sent_to}
              </span>
              <div style="font-size:0.7rem; color:var(--text-dim); margin-top:2px;">
                ${formatDateTime(n.email_sent_at)}
              </div>
            ` : `
              <button class="btn btn-primary btn-sm" onclick="openEscalationEmailModal('${n.doc_id}', ${n.days_inactive})">
                📧 Email to damayanthi.u@riscrm.com
              </button>
            `}
          </div>
        </div>

        <p style="font-size:0.86rem; color:var(--text-muted); margin-bottom:1rem; line-height:1.5;">
          ${n.message}
        </p>

        <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid var(--border-subtle); padding-top:0.75rem; font-size:0.8rem;">
          <div style="color:var(--text-dim); display:flex; gap:1rem;">
            <span>📎 Attachment ready: <strong>Original Resume in DMS</strong></span>
            ${n.email_attachment_filename ? `<span>Attached: <strong>${n.email_attachment_filename}</strong></span>` : ''}
          </div>
          <div style="display:flex; gap:0.5rem;">
            <button class="btn btn-secondary btn-sm" onclick="viewOriginalResume('${n.doc_id}')">Original Resume</button>
            <button class="btn btn-secondary btn-sm" onclick="openDevPlanModal('${n.doc_id}')">Dev Plan</button>
            <button class="btn btn-secondary btn-sm" onclick="launchImprovementForCandidate('${n.doc_id}')">Improve Resume</button>
            ${!n.is_read ? `<button class="btn btn-secondary btn-sm" onclick="markNotificationAsRead('${n.id}')">Mark Read</button>` : ''}
            <button class="btn btn-danger btn-sm" onclick="confirmDeleteResume('${n.doc_id}', 'Candidate ${n.doc_id}')">🗑️ Delete</button>
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
    showToast(`Dispatched escalation email to ${res.recipient} with resume "${res.attachment_filename}" attached!`, "success");
    
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
    } else {
      if (authEl) {
        authEl.textContent = "Credentials Needed";
        authEl.style.color = "#f59e0b";
      }
      if (passAlert) passAlert.style.display = "block";
    }
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = "Error";
      statusEl.style.color = "var(--danger)";
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

async function runIKMAuthTest() {
  const user = document.getElementById("ikm-test-user-input")?.value.trim();
  const pass = document.getElementById("ikm-test-pass-input")?.value.trim();
  const resultEl = document.getElementById("ikm-auth-test-result");
  if (!resultEl) return;

  resultEl.style.display = "block";
  resultEl.style.background = "rgba(255, 255, 255, 0.05)";
  resultEl.style.color = "var(--text-muted)";
  resultEl.textContent = "Testing authentication with RAG Builder...";

  try {
    const res = await API.testIKMAuth(user, pass);
    if (res.success) {
      resultEl.style.background = "rgba(16, 185, 129, 0.15)";
      resultEl.style.color = "#6ee7b7";
      resultEl.textContent = `✓ ${res.message} (Token issued)`;
      showToast("RAG Builder authentication succeeded!", "success");
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

