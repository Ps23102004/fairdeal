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

function appendMessage(role, html) {
  const chatLog = document.querySelector("#chat-log");
  const message = document.createElement("article");

  message.className = `message message--${role === "user" ? "user" : "app"}`;
  message.innerHTML = `<div class="message__bubble">${html}</div>`;
  chatLog.append(message);
  message.scrollIntoView({ behavior: "smooth", block: "end" });
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
      body: JSON.stringify({ message: text }),
    });

    if (!response.ok) {
      const errorMessage = await errorMessageFor(response);
      responseHtml = `<p class="request-error">Sorry—${escapeHtml(errorMessage)}</p>`;
    } else {
      const body = await response.json();
      responseHtml = `${escapeHtml(body.reply_text)}${renderDataSourceNote(body.data_source)}${renderResults(body.results)}`;
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
