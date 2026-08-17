function safeListingUrl(url) {
  try {
    const parsed = new URL(url, window.location.href);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#";
  } catch (error) {
    return "#";
  }
}

function renderVerdictCard(result) {
  const rating = ["fair", "borderline", "unfair", "unknown"].includes(result.rating)
    ? result.rating
    : "unknown";
  const price = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(result.price);
  const distance = Number.isFinite(result.distance_miles)
    ? `${result.distance_miles} mile${result.distance_miles === 1 ? "" : "s"} away`
    : "Distance unavailable";

  // Listing fields (title/explanation/url) come from the active search
  // provider — today that's a fixed seed set, but the provider interface is
  // designed to be swapped for a real external listings API, so a listing's
  // title is untrusted input from here on and gets escaped like any other.
  return `
    <article class="verdict-card">
      <div class="verdict-card__header">
        <div>
          <a class="verdict-card__title" href="${escapeHtml(safeListingUrl(result.url))}" target="_blank" rel="noreferrer">${escapeHtml(result.title)}</a>
          <p class="verdict-card__price">${price}/month</p>
        </div>
        <span class="rating-badge rating-badge--${rating}">${rating}</span>
      </div>
      <div class="verdict-card__body">
        <p class="verdict-card__distance">${distance}</p>
        <p class="verdict-card__explanation">${escapeHtml(result.explanation)}</p>
      </div>
    </article>
  `;
}

function renderDataSourceNote(dataSource) {
  // Surfaces the API's data_source field in-band — a demo viewer previously
  // had no signal that listings are seed data, not live rentals, without
  // reading the README.
  if (typeof dataSource !== "string" || !dataSource.includes("demo")) {
    return "";
  }
  return `<p class="data-source-note">Listings shown are demo data (source: ${escapeHtml(dataSource)}), not live rentals.</p>`;
}

function renderResults(results) {
  if (!results.length) {
    return '<p class="no-results">No results found. Try adding a neighborhood, price, or bedroom count.</p>';
  }

  return results.map(renderVerdictCard).join("");
}

function renderWebReferences(webReferences) {
  if (!Array.isArray(webReferences) || !webReferences.length) {
    return "";
  }
  const items = webReferences
    .map(
      (ref) =>
        `<li><a href="${escapeHtml(safeListingUrl(ref.url))}" target="_blank" rel="noreferrer">${escapeHtml(ref.title)}</a></li>`
    )
    .join("");
  return `
    <div class="web-references">
      <p class="web-references__label">Explore more listings (unverified web search results):</p>
      <ul class="web-references__list">${items}</ul>
    </div>
  `;
}

function appendMessage(role, html, logEl = document.querySelector("#chat-log")) {
  const message = document.createElement("article");

  message.className = `message message--${role === "user" ? "user" : "app"}`;
  message.innerHTML = `<div class="message__bubble">${html}</div>`;
  logEl.append(message);
  message.scrollIntoView({ behavior: "smooth", block: "end" });
}

function renderClauseCard(result) {
  const rating = ["fair", "borderline", "unfair", "unknown"].includes(result.rating)
    ? result.rating
    : "unknown";
  return `
    <article class="clause-card">
      <div class="clause-card__header">
        <p class="clause-card__title">${escapeHtml(result.title)}</p>
        <span class="rating-badge rating-badge--${rating}">${rating}</span>
      </div>
      <p class="clause-card__explanation">${escapeHtml(result.explanation)}</p>
    </article>
  `;
}

function renderClauseResults(results) {
  if (!results.length) {
    return '<p class="no-results">No flagged clauses found in that text.</p>';
  }
  return results.map(renderClauseCard).join("");
}

function renderCollegeResult(result) {
  const rating = ["fair", "borderline", "unfair", "unknown"].includes(result.rating)
    ? result.rating
    : "unknown";
  const completion = Number.isFinite(result.completion_rate_4yr)
    ? `<p class="college-result__completion">4-year completion rate: ${Math.round(result.completion_rate_4yr * 100)}%</p>`
    : "";
  return `
    <article class="clause-card">
      <div class="clause-card__header">
        <p class="clause-card__title">${escapeHtml(result.title)}</p>
        <span class="rating-badge rating-badge--${rating}">${rating}</span>
      </div>
      <p class="clause-card__explanation">${escapeHtml(result.explanation)}</p>
      ${completion}
    </article>
  `;
}

function renderCollegeResults(results) {
  if (!results.length) {
    return '<p class="no-results">Couldn\'t find that school. Try the full official name.</p>';
  }
  return results.map(renderCollegeResult).join("");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

async function errorMessageFor(response) {
  try {
    const body = await response.json();
    if (typeof body.error === "string" && body.error.trim()) {
      return body.error;
    }
  } catch (error) {
    console.error("FairDeal returned an unreadable error response.", error);
  }

  return "FairDeal couldn't check that rent right now. Please try again.";
}

const chatForm = document.querySelector("#chat-form");
const chatInput = document.querySelector("#chat-input");
const chatLog = document.querySelector("#chat-log");
const sendButton = chatForm.querySelector('button[type="submit"]');
const modelSelect = document.querySelector("#model-select");

// Populate the model selector from whatever's actually pulled in Ollama —
// an empty list (Ollama down, or nothing pulled) just leaves the "Default"
// option, same graceful degrade as the rest of the app.
fetch("/api/models")
  .then((res) => (res.ok ? res.json() : { models: [] }))
  .then((body) => {
    for (const name of body.models || []) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      modelSelect.append(option);
    }
  })
  .catch((error) => console.error("FairDeal couldn't load the model list.", error));

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const text = chatInput.value.trim();
  if (!text) {
    return;
  }

  chatInput.value = "";
  appendMessage("user", escapeHtml(text));

  chatInput.disabled = true;
  sendButton.disabled = true;
  appendMessage("app", '<span class="typing-status" role="status">Thinking…</span>');
  const typingMessage = chatLog.lastElementChild;
  let responseHtml;

  try {
    const response = await fetch("/api/rentcheck", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, model: modelSelect.value || null }),
    });

    if (!response.ok) {
      const errorMessage = await errorMessageFor(response);
      responseHtml = `<p class="request-error">Sorry—${escapeHtml(errorMessage)}</p>`;
    } else {
      const body = await response.json();
      responseHtml = `${escapeHtml(body.reply_text)}${renderDataSourceNote(body.data_source)}${renderResults(body.results)}${renderWebReferences(body.web_references)}`;
    }
  } catch (error) {
    console.error("FairDeal rent check failed.", error);
    responseHtml = '<p class="request-error">FairDeal couldn\'t complete the rent check. Please try again.</p>';
  } finally {
    typingMessage?.remove();
    chatInput.disabled = false;
    sendButton.disabled = false;
    chatInput.focus();
  }

  appendMessage("app", responseHtml);
});

// -- tab switching -----------------------------------------------------

document.querySelectorAll(".module-tab").forEach((tab) => {
  tab.addEventListener("click", (event) => {
    event.preventDefault();
    const target = tab.dataset.target;
    if (!target || tab.classList.contains("is-active")) {
      return;
    }
    document.querySelectorAll(".module-tab").forEach((t) => t.classList.toggle("is-active", t === tab));
    document.querySelectorAll(".module-panel").forEach((panel) => {
      panel.classList.toggle("is-active", panel.dataset.target === target);
    });
  });
});

// -- lease review / contract review (paste-a-document forms) -----------

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      // reader.result is "data:application/pdf;base64,<data>" — strip the prefix.
      const commaIndex = reader.result.indexOf(",");
      resolve(reader.result.slice(commaIndex + 1));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function wireDocumentReviewForm(formId, logId, fileInputId, fileNameId, endpoint, placeholderText) {
  const form = document.querySelector(`#${formId}`);
  const log = document.querySelector(`#${logId}`);
  const textarea = form.querySelector("textarea");
  const fileInput = document.querySelector(`#${fileInputId}`);
  const fileNameLabel = document.querySelector(`#${fileNameId}`);
  const button = form.querySelector('button[type="submit"]');

  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (file) {
      fileNameLabel.textContent = `Selected: ${file.name}`;
      fileNameLabel.hidden = false;
      textarea.value = "";
      textarea.disabled = true;
    } else {
      fileNameLabel.hidden = true;
      textarea.disabled = false;
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileInput.files[0];
    const text = textarea.value.trim();
    if (!file && !text) {
      return;
    }

    const userSummary = file
      ? `<em>Uploaded ${escapeHtml(file.name)}</em>`
      : `<em>${placeholderText}</em> (${text.length.toLocaleString()} characters pasted)`;
    appendMessage("user", userSummary, log);
    textarea.disabled = true;
    fileInput.disabled = true;
    button.disabled = true;
    appendMessage("app", '<span class="typing-status" role="status">Scanning…</span>', log);
    const typingMessage = log.lastElementChild;
    let responseHtml;

    try {
      const requestBody = file ? { pdf_base64: await readFileAsBase64(file) } : { document_text: text };
      const response = await fetch(`/api/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorMessage = await errorMessageFor(response);
        responseHtml = `<p class="request-error">Sorry—${escapeHtml(errorMessage)}</p>`;
      } else {
        const body = await response.json();
        responseHtml = `${escapeHtml(body.reply_text)}${renderDataSourceNote(body.data_source)}${renderClauseResults(body.results)}`;
      }
    } catch (error) {
      console.error(`FairDeal ${endpoint} failed.`, error);
      responseHtml = '<p class="request-error">FairDeal couldn\'t scan that document. Please try again.</p>';
    } finally {
      typingMessage?.remove();
      textarea.disabled = false;
      fileInput.disabled = false;
      button.disabled = false;
    }

    appendMessage("app", responseHtml, log);
  });
}

wireDocumentReviewForm("lease-review-form", "lease-review-log", "lease-file", "lease-file-name", "leasereview", "Pasted lease");
wireDocumentReviewForm("contract-review-form", "contract-review-log", "contract-file", "contract-file-name", "contractreview", "Pasted contract");

// -- college ROI (school + major form) ----------------------------------

const collegeForm = document.querySelector("#college-roi-form");
const collegeLog = document.querySelector("#college-roi-log");
const schoolInput = document.querySelector("#school-name");
const majorInput = document.querySelector("#intended-major");
const collegeButton = collegeForm.querySelector('button[type="submit"]');

collegeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const school = schoolInput.value.trim();
  if (!school) {
    return;
  }
  const major = majorInput.value.trim();

  appendMessage("user", escapeHtml(major ? `${school} — ${major}` : school), collegeLog);
  schoolInput.disabled = true;
  majorInput.disabled = true;
  collegeButton.disabled = true;
  appendMessage("app", '<span class="typing-status" role="status">Looking up outcomes…</span>', collegeLog);
  const typingMessage = collegeLog.lastElementChild;
  let responseHtml;

  try {
    const response = await fetch("/api/collegeroi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ school, major: major || null }),
    });

    if (!response.ok) {
      const errorMessage = await errorMessageFor(response);
      responseHtml = `<p class="request-error">Sorry—${escapeHtml(errorMessage)}</p>`;
    } else {
      const body = await response.json();
      responseHtml = `${escapeHtml(body.reply_text)}${renderDataSourceNote(body.data_source)}${renderCollegeResults(body.results)}`;
    }
  } catch (error) {
    console.error("FairDeal collegeroi failed.", error);
    responseHtml = '<p class="request-error">FairDeal couldn\'t look up that school. Please try again.</p>';
  } finally {
    typingMessage?.remove();
    schoolInput.disabled = false;
    majorInput.disabled = false;
    collegeButton.disabled = false;
  }

  appendMessage("app", responseHtml, collegeLog);
});
