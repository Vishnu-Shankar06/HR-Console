const API = {
  activeUserId: "admin-001",

  setActiveUser(userId) {
    this.activeUserId = userId;
  },

  getHeaders(isJson = true) {
    const headers = {
      "X-User-Id": this.activeUserId
    };
    if (isJson) {
      headers["Content-Type"] = "application/json";
    }
    return headers;
  },

  async request(endpoint, options = {}) {
    const isFormData = options.body instanceof FormData;
    const headers = {
      ...this.getHeaders(!isFormData),
      ...(options.headers || {})
    };

    try {
      const response = await fetch(endpoint, {
        ...options,
        headers
      });

      if (!response.ok) {
        let errDetail = "Request failed";
        try {
          const errData = await response.json();
          errDetail = errData.detail || JSON.stringify(errData);
        } catch {
          errDetail = `HTTP ${response.status} error`;
        }
        throw new Error(errDetail);
      }

      return await response.json();
    } catch (err) {
      console.error(`API Error [${endpoint}]:`, err);
      throw err;
    }
  },

  // Health
  getHealth() {
    return this.request("/api/health");
  },

  // Dashboard
  getDashboardSummary() {
    return this.request("/api/dashboard/summary");
  },

  // Resumes
  getResumes(query = "", status = "") {
    let url = "/api/resumes?";
    if (query) url += `query=${encodeURIComponent(query)}&`;
    if (status) url += `status_filter=${encodeURIComponent(status)}&`;
    return this.request(url);
  },

  getResumeDetail(docId) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}`);
  },

  getResumePII(docId) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/pii`);
  },

  getResumePreview(docId) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/preview`);
  },

  getVersionPreview(versionId) {
    return this.request(`/api/versions/${encodeURIComponent(versionId)}/preview`);
  },

  uploadResumes(formData) {
    return fetch("/api/resumes", {
      method: "POST",
      headers: {
        "X-User-Id": this.activeUserId
      },
      body: formData
    }).then(res => {
      if (!res.ok) throw new Error("Upload failed");
      return res.json();
    });
  },

  // Jobs
  getJobs() {
    return this.request("/api/jobs");
  },

  createJob(title, jobText) {
    return this.request("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ title, job_text: jobText })
    });
  },

  // Candidate Matching
  matchCandidates(requestedCount, jobId = null, jobText = null, docIds = null) {
    return this.request("/api/matches", {
      method: "POST",
      body: JSON.stringify({
        requested_count: parseInt(requestedCount, 10),
        job_id: jobId || undefined,
        job_description_text: jobText || undefined,
        doc_ids: (Array.isArray(docIds) && docIds.length > 0) ? docIds : undefined
      })
    });
  },

  getMatchRun(runId) {
    return this.request(`/api/matches/${encodeURIComponent(runId)}`);
  },

  // Resume Improvement
  analyzeImprovement(docId, jobId = null, jobText = null, personalDetails = null) {
    const payload = {
      job_id: jobId || undefined,
      job_text: jobText || undefined
    };
    if (personalDetails) {
      if (personalDetails.name) payload.candidate_name = personalDetails.name;
      if (personalDetails.role) payload.candidate_role = personalDetails.role;
      if (personalDetails.phone) payload.candidate_phone = personalDetails.phone;
      if (personalDetails.email) payload.candidate_email = personalDetails.email;
      if (personalDetails.location) payload.candidate_location = personalDetails.location;
      if (personalDetails.links) payload.candidate_links = personalDetails.links;
    }
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/improvements`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  saveRevisedVersion(docId, changeSummary, revisedContent, approved = true, personalDetails = null, approvedChanges = null) {
    const payload = {
      change_summary: changeSummary,
      revised_content: revisedContent,
      approved
    };
    if (personalDetails) {
      if (personalDetails.name) payload.candidate_name = personalDetails.name;
      if (personalDetails.role) payload.candidate_role = personalDetails.role;
      if (personalDetails.phone) payload.candidate_phone = personalDetails.phone;
      if (personalDetails.email) payload.candidate_email = personalDetails.email;
      if (personalDetails.location) payload.candidate_location = personalDetails.location;
      if (personalDetails.links) payload.candidate_links = personalDetails.links;
    }
    if (approvedChanges) {
      payload.approved_changes = approvedChanges;
    }
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/versions`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  recalculateScore(docId, acceptedChanges, jobId = null, jobText = null) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/recalculate-score`, {
      method: "POST",
      body: JSON.stringify({
        job_id: jobId || undefined,
        job_text: jobText || undefined,
        accepted_changes: acceptedChanges
      })
    });
  },

  getVersionHistory(docId) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/versions`);
  },

  // Follow-ups & Candidate Development
  getFollowups(inactivityDays = null) {
    let url = "/api/follow-ups";
    if (inactivityDays) url += `?inactivity_days=${inactivityDays}`;
    return this.request(url);
  },

  getResumeActions(docId) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/actions`);
  },

  addResumeRemark(docId, notes, status = null) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/remarks`, {
      method: "POST",
      body: JSON.stringify({
        notes: notes,
        status: status || undefined
      })
    });
  },

  recordAction(docId, actionType, status = null, notes = null, nextActionAt = null) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/actions`, {
      method: "POST",
      body: JSON.stringify({
        action_type: actionType,
        status: status || undefined,
        notes: notes || undefined,
        next_action_at: nextActionAt || undefined
      })
    });
  },

  // Resume Deletion
  deleteResume(docId) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}`, {
      method: "DELETE"
    });
  },

  bulkDeleteResumes(docIds) {
    return this.request("/api/resumes/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ doc_ids: docIds })
    });
  },

  // Job Deletion
  deleteJob(jobId) {
    return this.request(`/api/jobs/${encodeURIComponent(jobId)}`, {
      method: "DELETE"
    });
  },

  // Audit
  getAuditEvents() {
    return this.request("/api/audit/events");
  },

  // Record Resume Opened / Viewed
  recordResumeOpened(docId) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/open`, {
      method: "POST"
    });
  },

  // Notifications
  getNotifications(unreadOnly = false) {
    return this.request(`/api/notifications?unread_only=${unreadOnly}`);
  },

  markNotificationRead(notificationId) {
    return this.request(`/api/notifications/${encodeURIComponent(notificationId)}/read`, {
      method: "POST"
    });
  },

  // AI Escalation Email
  sendEscalationEmail(docId, recipient = "damayanthi.u@riscrm.com", reason = null) {
    let url = `/api/resumes/${encodeURIComponent(docId)}/send-escalation-email?recipient=${encodeURIComponent(recipient)}`;
    if (reason) url += `&reason=${encodeURIComponent(reason)}`;
    return this.request(url, {
      method: "POST"
    });
  },

  generateWordResume(docId, revisedContent, changeSummary = "AI Enhanced Word Resume", targetRole = "Senior Professional", personalDetails = null, approvedChanges = null) {
    const payload = {
      revised_content: revisedContent,
      change_summary: changeSummary,
      target_role: targetRole
    };
    if (personalDetails) {
      if (personalDetails.name) payload.candidate_name = personalDetails.name;
      if (personalDetails.role) payload.candidate_role = personalDetails.role;
      if (personalDetails.phone) payload.candidate_phone = personalDetails.phone;
      if (personalDetails.email) payload.candidate_email = personalDetails.email;
      if (personalDetails.location) payload.candidate_location = personalDetails.location;
      if (personalDetails.links) payload.candidate_links = personalDetails.links;
    }
    if (approvedChanges) {
      payload.approved_changes = approvedChanges;
    }
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/generate-word`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  openInWord(docId) {
    return this.request(`/api/resumes/${encodeURIComponent(docId)}/open-in-word`, {
      method: "POST"
    });
  },

  // IKM / RAG Builder Operations
  getIKMStatus() {
    return this.request("/api/ikm/status");
  },

  testIKMAuth(username = null, password = null, baseUrl = null) {
    const payload = {};
    if (username) payload.username = username;
    if (password) payload.password = password;
    if (baseUrl) payload.base_url = baseUrl;
    return this.request("/api/ikm/test-auth", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  retrieveIKM(query, topK = 10, filters = null) {
    return this.request("/api/ikm/retrieve", {
      method: "POST",
      body: JSON.stringify({
        query,
        top_k: topK,
        filters: filters || undefined
      })
    });
  },

  chatIKM(query, conversation = []) {
    return this.request("/api/ikm/chat", {
      method: "POST",
      body: JSON.stringify({
        query,
        conversation
      })
    });
  },

  getResumeIKMTemplate(docId) {
    return this.request(`/api/ikm/resumes/${encodeURIComponent(docId)}/template`);
  },

  updateResumeIKMKeyFields(docId, fields, reason = "Recruiter manual update") {
    return this.request(`/api/ikm/resumes/${encodeURIComponent(docId)}/key-fields`, {
      method: "PATCH",
      body: JSON.stringify({
        fields,
        reason
      })
    });
  }
};
