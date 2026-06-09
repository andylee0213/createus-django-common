/**
 * filename: createus_common/messaging/static/createus_common/js/thread_chat.js
 *
 * Generic polling chat widget — data-attribute driven, project-agnostic.
 *
 * ── Required on [data-chat-messages] ──────────────────────────────────────
 *   data-list-url        API endpoint (GET supports ?last_id=, POST creates)
 *   data-current-role    Numeric sender role of the viewing user
 *
 * ── Optional styling on [data-chat-messages] ──────────────────────────────
 *   data-row-class       Message row wrapper       (default: "d-flex mb-3")
 *   data-avatar-class    Avatar/initial circle     (default: "rounded-circle me-2 d-flex align-items-center justify-content-center")
 *   data-block-class     Text block container      (default: "")
 *   data-name-class      Sender name element       (default: "fw-semibold small")
 *   data-bubble-class    Message bubble            (default: "p-2 rounded")
 *   data-time-class      Timestamp element         (default: "text-muted small mt-1")
 *   data-empty-id        ID of element hidden once messages arrive
 *
 * ── Form / input ──────────────────────────────────────────────────────────
 *   [data-chat-form]     The <form> element
 *   [data-chat-input]    The text <textarea> or <input>
 *
 * ── Message shape from API ────────────────────────────────────────────────
 *   {
 *     id: number,
 *     sender_name: string | null,
 *     sender_role: number,
 *     content: string,
 *     is_internal: boolean,
 *     created_at: string (ISO 8601 or HH:MM),
 *
 *     // Attachment support — both forms accepted (backward compatible):
 *     attachment?: { url: string, name: string }           // legacy single
 *     attachments?: Array<{ url: string, name: string }>   // preferred multi
 *   }
 */

(function () {
  "use strict";

  var POLL_INTERVAL_MS = 5000;

  function initThreadChat(messagesEl) {
    var listUrl = messagesEl.dataset.listUrl;
    if (!listUrl) return;

    var currentRole = parseInt(messagesEl.dataset.currentRole, 10);
    var emptyId = messagesEl.dataset.emptyId || "";

    var rowClass = messagesEl.dataset.rowClass || "d-flex mb-3";
    var avatarClass =
      messagesEl.dataset.avatarClass ||
      "rounded-circle me-2 d-flex align-items-center justify-content-center";
    var blockClass = messagesEl.dataset.blockClass || "";
    var nameClass = messagesEl.dataset.nameClass || "fw-semibold small";
    var bubbleClass = messagesEl.dataset.bubbleClass || "p-2 rounded";
    var timeClass = messagesEl.dataset.timeClass || "text-muted small mt-1";

    var formEl = document.querySelector("[data-chat-form]");
    var inputEl = document.querySelector("[data-chat-input]");
    var emptyEl = emptyId ? document.getElementById(emptyId) : null;

    var lastId = null;
    var seenIds = {};

    // ── Escaping ────────────────────────────────────────────────────────────

    function escapeHTML(str) {
      return String(str == null ? "" : str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function escapeAttr(str) {
      return String(str == null ? "" : str).replace(/"/g, "&quot;");
    }

    // ── Helpers ─────────────────────────────────────────────────────────────

    function formatTime(value) {
      if (!value) return "";
      // Already formatted (HH:MM) — pass through
      if (/^\d{2}:\d{2}$/.test(String(value).trim())) return value;
      try {
        var d = new Date(value);
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      } catch (_) {
        return String(value);
      }
    }

    function isSelf(msg) {
      return Number(msg.sender_role) === currentRole;
    }

    function avatarInitial(msg) {
      var name = msg.sender_name || "?";
      return name.charAt(0).toUpperCase();
    }

    // ── Attachment rendering ─────────────────────────────────────────────────

    function normalizeAttachments(msg) {
      // Prefer the plural form; fall back to legacy singular
      if (Array.isArray(msg.attachments) && msg.attachments.length) {
        return msg.attachments;
      }
      if (msg.attachment && typeof msg.attachment === "object") {
        return [msg.attachment];
      }
      return [];
    }

    function buildAttachmentHTML(att) {
      if (!att) return "";
      var url = att.url || att.file_url || "";
      var name = escapeHTML(att.name || att.filename || "attachment");
      if (!url) {
        return '<div class="ct-attachment">' + name + "</div>";
      }
      return (
        '<div class="ct-attachment">' +
        '<a href="' + escapeAttr(url) + '" target="_blank" rel="noopener noreferrer">' +
        name +
        "</a>" +
        "</div>"
      );
    }

    function buildAttachmentsHTML(msg) {
      var atts = normalizeAttachments(msg);
      if (!atts.length) return "";
      return atts.map(buildAttachmentHTML).join("");
    }

    // ── Message row builder ──────────────────────────────────────────────────

    function buildMessageRow(msg) {
      var self = isSelf(msg);
      var alignClass = self ? "justify-content-end" : "justify-content-start";
      var bubbleColorClass = self ? "bg-primary text-white" : "bg-light";
      var internalBadge = msg.is_internal
        ? '<span class="badge bg-warning text-dark ms-1">internal</span>'
        : "";

      var avatarHTML = self
        ? ""
        : '<div class="' +
          avatarClass +
          '" style="width:32px;height:32px;min-width:32px;font-size:.85rem;">' +
          escapeHTML(avatarInitial(msg)) +
          "</div>";

      var attachmentsHTML = buildAttachmentsHTML(msg);

      var row = document.createElement("div");
      row.className = rowClass + " " + alignClass;
      row.dataset.messageId = msg.id;

      row.innerHTML =
        (self ? "" : avatarHTML) +
        '<div class="' + blockClass + (self ? " text-end" : "") + '">' +
          '<div class="' + nameClass + '">' +
            escapeHTML(msg.sender_name || "") + internalBadge +
          "</div>" +
          '<div class="' + bubbleClass + " " + bubbleColorClass + '">' +
            escapeHTML(msg.content || "") +
            (attachmentsHTML ? '<div class="mt-1">' + attachmentsHTML + "</div>" : "") +
          "</div>" +
          '<div class="' + timeClass + '">' + escapeHTML(formatTime(msg.created_at)) + "</div>" +
        "</div>" +
        (self ? avatarHTML : "");

      return row;
    }

    // ── Append / dedup ───────────────────────────────────────────────────────

    function appendMessages(messages) {
      var normalized = Array.isArray(messages)
        ? messages
        : messages && Array.isArray(messages.results)
        ? messages.results
        : messages && Array.isArray(messages.messages)
        ? messages.messages
        : [];

      var added = false;
      for (var i = 0; i < normalized.length; i++) {
        var msg = normalized[i];
        var id = msg.id;
        if (seenIds[id]) continue;
        seenIds[id] = true;
        if (lastId === null || id > lastId) lastId = id;
        messagesEl.appendChild(buildMessageRow(msg));
        added = true;
      }

      if (added) {
        if (emptyEl) emptyEl.style.display = "none";
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }

    // ── Polling ──────────────────────────────────────────────────────────────

    function fetchMessages() {
      var url = lastId !== null ? listUrl + "?last_id=" + lastId : listUrl;
      fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) {
          if (!r.ok) throw new Error("fetch failed");
          return r.json();
        })
        .then(function (data) {
          appendMessages(data);
        })
        .catch(function () {});
    }

    // ── CSRF ─────────────────────────────────────────────────────────────────

    function getCsrfToken() {
      var el = document.querySelector("[name=csrfmiddlewaretoken]");
      if (el) return el.value;
      var cookie = (document.cookie || "")
        .split("; ")
        .filter(function (c) { return c.indexOf("csrftoken=") === 0; })[0];
      return cookie ? cookie.split("=")[1] : "";
    }

    // ── Submit ───────────────────────────────────────────────────────────────

    function hasAttachment() {
      var fileInput = formEl ? formEl.querySelector("input[type=file]") : null;
      return !!(fileInput && fileInput.files && fileInput.files.length > 0);
    }

    function clearAttachmentPreview() {
      var fileInput = formEl ? formEl.querySelector("input[type=file]") : null;
      if (fileInput) {
        try {
          fileInput.value = "";
          fileInput.dispatchEvent(new Event("change"));
        } catch (_) {}
      }
      var preview = formEl ? formEl.querySelector("[data-attachment-preview]") : null;
      if (preview) preview.innerHTML = "";
    }

    function submitMessage(e) {
      e.preventDefault();
      if (!inputEl) return;

      var content = inputEl.value.trim();
      if (!content && !hasAttachment()) return;

      var formData = new FormData(formEl);

      fetch(listUrl, {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": getCsrfToken(),
        },
        body: formData,
      })
        .then(function (r) {
          if (!r.ok) throw new Error("submit failed");
          return r.json();
        })
        .then(function (msg) {
          // Server may return the message directly or wrapped
          var single = msg && (msg.id !== undefined) ? msg : msg && msg.message ? msg.message : null;
          if (single) {
            appendMessages([single]);
          }
          inputEl.value = "";
          clearAttachmentPreview();
        })
        .catch(function () {});
    }

    // ── Bootstrap ────────────────────────────────────────────────────────────

    fetchMessages();
    setInterval(fetchMessages, POLL_INTERVAL_MS);

    if (formEl) {
      formEl.addEventListener("submit", submitMessage);
    }
  }

  function init() {
    var containers = document.querySelectorAll("[data-chat-messages]");
    for (var i = 0; i < containers.length; i++) {
      initThreadChat(containers[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
