// Social Ultimate dashboard — vanilla JS, no build step
const API = "";  // same origin
let token = localStorage.getItem("su_token") || "";
let currentUser = null;
let accounts = [];

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function toast(msg, kind = "success") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast ${kind}`;
  setTimeout(() => t.classList.add("hidden"), 3500);
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(API + path, { ...opts, headers });
  if (r.status === 401) { logout(); throw new Error("Unauthorized"); }
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try { const j = await r.json(); detail = j.detail || detail; } catch {}
    throw new Error(detail);
  }
  return r.status === 204 ? null : r.json();
}

function showView(name) {
  $$(".view").forEach(v => v.classList.add("hidden"));
  $(`#view-${name}`).classList.remove("hidden");
  $("#btn-logout").classList.toggle("hidden", name === "auth");
  $("#btn-login, #btn-register").forEach ? null : null;
  $("#btn-login").classList.toggle("hidden", name !== "auth");
  $("#btn-register").classList.toggle("hidden", name !== "auth");
}

function logout() {
  token = "";
  localStorage.removeItem("su_token");
  currentUser = null;
  showView("auth");
}

// ---- Auth ----
async function login(email, password) {
  const body = new URLSearchParams({ username: email, password });
  const r = await fetch(API + "/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.detail || `Login failed (${r.status})`);
  }
  const j = await r.json();
  token = j.access_token;
  localStorage.setItem("su_token", token);
  await loadDashboard();
}

async function register(email, password) {
  await api("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  await login(email, password);
}

// ---- Dashboard data ----
async function loadDashboard() {
  showView("dashboard");
  currentUser = await api("/api/auth/me");
  accounts = await api("/api/instagram/accounts");

  // Show experimental panel only if server has it enabled
  try {
    const h = await fetch("/health").then(r => r.json());
    if (h.experimental_enabled) {
      $("#experimental-panel").classList.remove("hidden");
    }
  } catch {}

  const list = $("#accounts-list");
  if (accounts.length === 0) {
    list.innerHTML = '<p class="muted">No accounts connected yet.</p>';
  } else {
    list.innerHTML = accounts.map(a => `
      <div class="list-item">
        <div>
          <strong>@${a.ig_username || a.ig_user_id}</strong>
          <div class="meta">${a.account_type} · expires ${new Date(a.token_expires_at).toLocaleDateString()}</div>
        </div>
        <button class="btn btn-secondary btn-small" onclick="loadInsights(${a.id})">Insights</button>
      </div>
    `).join("");
  }

  const sel = $("#schedule-account");
  sel.innerHTML = '<option value="">Select account...</option>' +
    accounts.map(a => `<option value="${a.id}">@${a.ig_username || a.ig_user_id}</option>`).join("");

  // metrics for first account, if any
  if (accounts.length > 0) {
    await loadInsights(accounts[0].id);
  } else {
    $("#m-followers").textContent = "—";
    $("#m-follows").textContent = "—";
    $("#m-posts").textContent = "—";
    $("#m-views").textContent = "—";
  }

  const posts = await api("/api/posts");
  const pl = $("#posts-list");
  if (posts.length === 0) {
    pl.innerHTML = '<p class="muted">No scheduled posts.</p>';
  } else {
    pl.innerHTML = posts.map(p => `
      <div class="list-item">
        <div>
          <span class="badge badge-${p.status}">${p.status}</span>
          <span style="margin-left:0.5rem">${new Date(p.scheduled_for).toLocaleString()}</span>
          <div class="meta">${p.ig_media_id || ''}</div>
        </div>
      </div>
    `).join("");
  }
}

async function loadInsights(accountId) {
  try {
    const me = await api(`/api/instagram/accounts/${accountId}/me`);
    $("#m-followers").textContent = (me.followers_count ?? "—").toLocaleString();
    $("#m-follows").textContent = (me.follows_count ?? "—").toLocaleString();
    $("#m-posts").textContent = (me.media_count ?? "—").toLocaleString();
  } catch (e) {
    console.warn("Insights fetch failed:", e);
  }
  try {
    const ins = await api(`/api/instagram/accounts/${accountId}/insights?period=day`);
    const views = ins.data?.find(d => d.name === "profile_views");
    $("#m-views").textContent = views?.values?.slice(-1)[0]?.value?.toLocaleString() || "—";
  } catch {}
}

// ---- Event wiring ----
document.addEventListener("DOMContentLoaded", async () => {
  $$(".tab").forEach(t => t.addEventListener("click", () => {
    $$(".tab").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    $("#form-login").classList.toggle("hidden", t.dataset.tab !== "login");
    $("#form-register").classList.toggle("hidden", t.dataset.tab !== "register");
  }));

  $("#form-login").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await login(e.target.email.value, e.target.password.value);
    } catch (err) { $("#auth-error").textContent = err.message; $("#auth-error").classList.remove("hidden"); }
  });

  $("#form-register").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await register(e.target.email.value, e.target.password.value);
    } catch (err) { $("#auth-error").textContent = err.message; $("#auth-error").classList.remove("hidden"); }
  });

  $("#btn-logout").addEventListener("click", logout);
  $("#btn-login").addEventListener("click", () => showView("auth"));
  $("#btn-register").addEventListener("click", () => showView("auth"));

  $("#btn-connect-ig").addEventListener("click", async () => {
    try {
      const { url } = await api("/api/instagram/oauth/start");
      window.location.href = url;
    } catch (e) { toast(e.message, "error"); }
  });

  $("#form-schedule").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      account_id: parseInt($("#schedule-account").value, 10),
      caption: $("#schedule-caption").value,
      media_url: $("#schedule-image").value,
      media_type: "IMAGE",
      scheduled_for: new Date($("#schedule-when").value).toISOString(),
    };
    try {
      await api("/api/posts", { method: "POST", body: JSON.stringify(payload) });
      toast("Post scheduled");
      e.target.reset();
      await loadDashboard();
    } catch (err) { toast(err.message, "error"); }
  });

  // ---- Experimental: account creation ----
  $("#form-create-accounts").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!$("#ca-consent").checked) {
      toast("You must acknowledge the ToS warning first", "error");
      return;
    }
    const payload = {
      platform: $("#ca-platform").value,
      mailbox_backend: $("#ca-mailbox").value,
      count: parseInt($("#ca-count").value, 10) || 1,
      proxy: $("#ca-proxy").value || null,
      verification_timeout: parseInt($("#ca-timeout").value, 10) || 180,
      consent_acknowledged: true,
    };
    try {
      const r = await api("/api/experimental/accounts/create",
        { method: "POST", body: JSON.stringify(payload) });
      toast(`Queued ${payload.count} ${payload.platform} account(s) via ${payload.mailbox_backend}`);
      $("#btn-refresh-inbox").click();
    } catch (err) { toast(err.message, "error"); }
  });

  $("#btn-refresh-accounts").addEventListener("click", loadExperimentalAccounts);
  $("#btn-refresh-inbox").addEventListener("click", loadInbox);
  $("#inbox-backend-filter").addEventListener("change", loadInbox);
  $("#inbox-codes-only").addEventListener("change", loadInbox);

  async function loadExperimentalAccounts() {
    const target = $("#accounts-list-exp");
    try {
      const rows = await api("/api/experimental/accounts?limit=50");
      if (!rows.length) {
        target.innerHTML = '<p class="muted">No accounts yet.</p>';
        return;
      }
      target.innerHTML = rows.map(r => `
        <div class="list-item">
          <div>
            <span class="badge badge-${r.success ? 'posted' : (r.error ? 'failed' : 'pending')}">
              ${r.success ? 'success' : (r.username === '(pending)' ? 'pending' : 'failed')}
            </span>
            <strong>${r.platform}</strong> ·
            ${r.username || '(none)'} <span class="meta">${r.email || ''}</span>
            <div class="meta">
              ${r.mailbox_backend ? 'mailbox: ' + r.mailbox_backend + ' · ' : ''}
              ${new Date(r.created_at).toLocaleString()}
              ${r.error ? ' — ' + r.error.slice(0, 120) : ''}
            </div>
          </div>
        </div>
      `).join("");
    } catch (e) {
      target.innerHTML = '<p class="muted">Could not load: ' + e.message + '</p>';
    }
  }

  async function loadInbox() {
    const target = $("#inbox-list");
    target.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const params = new URLSearchParams();
      if ($("#inbox-codes-only").checked) params.set("codes_only", "true");
      const backend = $("#inbox-backend-filter").value;
      if (backend) params.set("backend", backend);
      const rows = await api("/api/experimental/inbox?" + params.toString());
      if (!rows.length) {
        target.innerHTML = '<p class="muted">No inbox messages match your filter.</p>';
        return;
      }
      target.innerHTML = rows.map(m => {
        const codes = (m.extracted_codes || []).map(c =>
          `<span class="code-pill">${c}</span>`).join('');
        const isTick = m.event !== 'message_received';
        return `
          <div class="list-item inbox-item ${isTick ? 'event-tick' : ''}">
            <div>
              <strong>${m.event === 'message_received' ? '✉' : '⏳'} ${m.subject || '(no subject)'}</strong>
              <span class="meta">${m.backend} · ${m.email_address}</span>
              <div class="meta">${m.sender} · ${new Date(m.captured_at).toLocaleString()}</div>
              ${codes ? '<div style="margin-top:0.4rem">' + codes + '</div>' : ''}
              ${m.body_excerpt ? '<div class="body">' + escapeHtml(m.body_excerpt) + '</div>' : ''}
            </div>
          </div>
        `;
      }).join("");
      loadExperimentalAccounts();
    } catch (e) {
      target.innerHTML = '<p class="muted">Could not load: ' + e.message + '</p>';
    }
  }

  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  // Initial load
  if (token) {
    try { await loadDashboard(); return; } catch { logout(); }
  }
  showView("auth");
});