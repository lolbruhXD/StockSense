const app = document.querySelector("#app");
const toast = document.querySelector("#toast");
const state = {
  user: null,
  csrf: "",
  filters: null,
  authMode: "login",
  renderId: 0,
  devResetCode: "",
};
const pageSize = 100;
const invitation = new URLSearchParams(location.hash.split("?")[1] || "");
if (invitation.has("invite")) state.authMode = "signup";

const icons = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  box: '<path d="m3 7 9-4 9 4v10l-9 4-9-4z"/><path d="m3 7 9 4 9-4M12 11v10"/>',
  arrowDown: '<path d="M12 3v13m-5-5 5 5 5-5M4 20h16"/>',
  arrowUp: '<path d="M12 21V8m-5 5 5-5 5 5M4 4h16"/>',
  transfer: '<path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/>',
  adjust: '<path d="M4 7h16M7 4v6M4 17h16m-5-3v6"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7M3 3v5h5M12 7v5l3 2"/>',
  warehouse: '<path d="M3 21V8l9-5 9 5v13M3 10h18M7 21v-7h10v7M10 14v7"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  close: '<path d="M5 5 19 19M19 5 5 19"/>',
  alert: '<path d="M12 3 2 21h20L12 3zM12 9v5m0 3h.01"/>',
  check: '<path d="m4 12 5 5L20 6"/>',
};
const icon = (name, size = 18) =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;
const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
const formatQuantity = (value) =>
  Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });
const countLabel = (count, singular, plural = singular + "s") =>
  `${count} ${count === 1 ? singular : plural}`;
const titleCase = (value) =>
  String(value || "").replace(/(^|_)\w/g, (part) =>
    part.replace("_", " ").toUpperCase(),
  );
const formatDate = (value) =>
  value
    ? new Date(
        value.includes("T") ? value : value.replace(" ", "T") + "Z",
      ).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "—";
const queryString = (values) =>
  "?" +
  new URLSearchParams(
    Object.entries(values).filter(([, value]) => value !== "" && value != null),
  );

async function api(path, options = {}) {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(state.csrf ? { "X-CSRF-Token": state.csrf } : {}),
    },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && state.user) {
      state.user = null;
      renderAuth();
    }
    throw new Error(data.error || "The request could not be completed");
  }
  return data;
}

function showNotice(message, error = false) {
  toast.textContent = message;
  toast.className = error ? "show error" : "show";
  clearTimeout(showNotice.timer);
  showNotice.timer = setTimeout(() => (toast.className = ""), 4400);
}

function navLink(route, label, glyph, current) {
  return `<a class="nav-link ${current === route ? "active" : ""}" href="#${route}">${icon(glyph)}<span>${label}</span></a>`;
}

function shell(content, section, title, action = "") {
  const first = state.user.name.trim().split(" ")[0];
  const existing = app.querySelector(".shell");
  if (existing) {
    existing.querySelector("#main").innerHTML = content;
    existing.querySelector(".breadcrumbs strong").textContent = title;
    existing.querySelector(".top-actions").innerHTML =
      `${action}<a class="top-profile" href="#/profile" aria-label="My profile">${icon("user", 19)}</a>`;
    existing.querySelector(".avatar").textContent = first[0]?.toUpperCase() || "U";
    existing.querySelector(".sidebar-user strong").textContent = state.user.name;
    for (const link of existing.querySelectorAll(".nav-link")) {
      link.classList.toggle("active", link.getAttribute("href") === `#${section}`);
    }
    existing.classList.remove("menu-open");
    return;
  }
  app.innerHTML = `<div class="shell">
    <aside class="sidebar">
      <a class="brand" href="#/dashboard"><span class="brand-mark"><span></span><span></span><span></span></span><span>Stock<span>Sense</span><small>INVENTORY CONTROL</small></span></a>
      <div class="nav-group-label">WORKSPACE</div>
      <nav aria-label="Primary navigation">
        ${navLink("/dashboard", "Dashboard", "grid", section)}
        ${navLink("/stock", "Stock overview", "box", section)}
        ${navLink("/products", "Products", "box", section)}
        <div class="nav-group-label inside">OPERATIONS</div>
        ${navLink("/operations/all", "All operations", "grid", section)}
        ${navLink("/operations/receipt", "Receipts", "arrowDown", section)}
        ${navLink("/operations/delivery", "Deliveries", "arrowUp", section)}
        ${navLink("/operations/transfer", "Transfers", "transfer", section)}
        ${navLink("/operations/adjustment", "Adjustments", "adjust", section)}
        ${navLink("/history", "Move history", "history", section)}
        <div class="nav-group-label inside">CONFIGURE</div>
        ${navLink("/warehouses", "Warehouses", "warehouse", section)}
      </nav>
      <div class="sidebar-bottom"><div class="avatar">${escapeHtml(first[0]?.toUpperCase() || "U")}</div><div class="sidebar-user"><strong>${escapeHtml(state.user.name)}</strong><span>${escapeHtml(state.user.email)}</span></div><a href="#/profile" aria-label="Profile">${icon("chevron", 16)}</a></div>
    </aside>
    <div class="main-wrap"><header class="topbar"><button class="mobile-menu" type="button" data-action="menu" aria-label="Toggle menu">☰</button><div class="breadcrumbs"><span>Workspace</span>${icon("chevron", 14)}<strong>${escapeHtml(title)}</strong></div><div class="top-actions">${action}<a class="top-profile" href="#/profile" aria-label="My profile">${icon("user", 19)}</a></div></header>
    <main id="main" class="content">${content}</main></div></div><dialog id="dialog" class="modal"></dialog>`;
}

function pageHead(title, description, button = "") {
  return `<div class="page-head"><div><h1>${title}</h1><p>${description}</p></div>${button}</div>`;
}
function button(label, action, kind = "primary") {
  return `<button type="button" class="btn ${kind}" data-action="${action}">${label}</button>`;
}
function badge(status) {
  return `<span class="badge ${escapeHtml(status)}"><span></span>${escapeHtml(titleCase(status))}</span>`;
}
function empty(title, copy, action = "") {
  return `<div class="empty"><div class="empty-symbol">${icon("box", 30)}</div><h3>${title}</h3><p>${copy}</p>${action}</div>`;
}
function warehouseOptions(selected = "", all = false) {
  return `${all ? '<option value="">All warehouses</option>' : '<option value="">Select warehouse</option>'}${(referenceData()?.warehouses || []).map((w) => `<option value="${w.id}" ${String(selected) === String(w.id) ? "selected" : ""}>${escapeHtml(w.name)}</option>`).join("")}`;
}
function locationOptions(selected = "", placeholder = "Select location") {
  return `<option value="">${placeholder}</option>${(referenceData()?.locations || []).map((l) => `<option value="${l.id}" ${String(selected) === String(l.id) ? "selected" : ""}>${escapeHtml(l.warehouse)} / ${escapeHtml(l.name)}</option>`).join("")}`;
}
function categoryOptions(selected = "", all = false) {
  return `${all ? '<option value="">All categories</option>' : '<option value="">No category</option>'}${(referenceData()?.categories || []).map((c) => `<option value="${c.id}" ${String(selected) === String(c.id) ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("")}`;
}
function renderAuth() {
  state.renderId++;
  const mode = state.authMode;
  const signup = mode === "signup";
  const invited = signup && invitation.has("invite");
  const reset = mode === "reset" || mode === "reset-confirm";
  app.innerHTML = `<div class="auth-layout"><div class="auth-story"><div class="auth-brand"><span class="brand-mark"><span></span><span></span><span></span>Stock<span>Sense</span></div><div class="auth-copy"><span class="story-rule"></span><h1>Every item<br>has a story.</h1><p>Keep its movement clear, from arrival to delivery. One reliable view of your stock, across every location.</p></div><div class="auth-foot">RECEIVE <span>→</span> MOVE <span>→</span> DELIVER <span>→</span> ACCOUNT FOR IT</div></div>
    <div class="auth-panel"><div class="auth-card"><div class="eyebrow">WELCOME TO STOCKSENSE</div><h2>${invited ? "Join your team" : signup ? "Create your workspace" : reset ? "Reset your password" : "Welcome back"}</h2><p class="auth-sub">${invited ? "Create an account to join your company's workspace." : signup ? "Set up your account to start tracking stock." : reset ? "We will help you get back into your workspace." : "Sign in to see what is moving today."}</p>
      <form id="auth-form">${signup ? `<label>Your name<input name="name" required autocomplete="name" placeholder="Alex Morgan"></label>${invited ? "" : '<label>Company name<input name="company" required autocomplete="organization" placeholder="Acme Supply"></label>'}` : ""}<label>Email address<input name="email" type="email" required autocomplete="email" value="${escapeHtml(invited ? invitation.get("email") : "")}" placeholder="you@company.com"></label>${mode === "reset-confirm" ? `<label>Six digit code<input name="code" inputmode="numeric" pattern="[0-9]{6}" required placeholder="000000"></label>${state.devResetCode ? `<p class="dev-code">Local development code: <strong>${escapeHtml(state.devResetCode)}</strong></p>` : ""}` : ""}${mode === "login" || signup || mode === "reset-confirm" ? `<label>${mode === "reset-confirm" ? "New password" : "Password"}<input name="password" type="password" required minlength="10" autocomplete="${signup ? "new-password" : "current-password"}" placeholder="At least 10 characters"></label>` : ""}<button class="btn primary auth-submit" type="submit">${invited ? "Join workspace" : signup ? "Create account" : mode === "reset" ? "Send reset code" : mode === "reset-confirm" ? "Update password" : "Sign in"} ${icon("chevron", 17)}</button></form>
      <div class="auth-switch">${mode === "login" ? `<button data-auth="reset">Forgot password?</button><span>New here? <button data-auth="signup">Create an account</button></span>` : `<button data-auth="login">Back to sign in</button>${mode === "reset" ? '<button data-auth="reset-confirm">I have a code</button>' : ""}`}</div></div><div class="auth-panel-foot">Built for the people who keep things moving.</div></div></div>`;
}

function referenceData() {
  return state.filters;
}

let filterRequest;
let referenceVersion = 0;
let filterRequestVersion = -1;
function loadFilters() {
  if (referenceData()) return Promise.resolve(referenceData());
  if (!filterRequest || filterRequestVersion !== referenceVersion) {
    const version = referenceVersion;
    filterRequestVersion = version;
    filterRequest = api("/bootstrap?products=0")
      .then((filters) => {
        if (version === referenceVersion) state.filters = filters;
        return filters;
      })
      .finally(() => {
        if (filterRequestVersion === version) filterRequest = null;
      });
  }
  return filterRequest;
}
function clearFilters() {
  referenceVersion++;
  state.filters = null;
}

function renderDashboard(data) {
  const metrics = [
    ["Products in stock", data.products_in_stock, "box", "/stock"],
    ["Low / out of stock", data.low_stock, "alert", "/stock"],
    [
      "Pending receipts",
      data.pending_receipts,
      "arrowDown",
      "/operations/receipt",
    ],
    [
      "Pending deliveries",
      data.pending_deliveries,
      "arrowUp",
      "/operations/delivery",
    ],
    [
      "Transfers scheduled",
      data.scheduled_transfers,
      "transfer",
      "/operations/transfer",
    ],
  ];
  const content = `${pageHead("Inventory at a glance", `Good to see you, ${escapeHtml(state.user.name.split(" ")[0])}. Here is what needs your attention today.`, `<a class="btn primary" href="#/new/receipt">${icon("plus", 17)} New receipt</a>`)}
    <div class="dashboard-banner"><div><div class="banner-kicker">YOUR OPERATIONS, IN ONE PLACE</div><h2>Know what’s moving.<br><em>Know what’s next.</em></h2><p>Receive goods, fulfil orders, and keep every location in sync.</p></div><div class="banner-graphic" aria-hidden="true"><span class="graphic-box box-one"></span><span class="graphic-path"></span><span class="graphic-box box-two"></span><span class="graphic-dot"></span></div></div>
    <div class="metric-grid">${metrics.map(([label, value, glyph, href]) => `<a class="metric" href="#${href}"><div class="metric-top">${icon(glyph, 19)}${icon("chevron", 15)}</div><strong>${formatQuantity(value)}</strong><span>${label}</span></a>`).join("")}</div>
    <div class="dashboard-columns"><section class="panel"><div class="section-head"><div><h2>Operations in motion</h2><p>Current work across your warehouses</p></div><a href="#/operations/all">View all ${icon("chevron", 14)}</a></div><div class="flow-cards"><a href="#/operations/receipt" class="flow-card inbound"><div class="flow-icon">${icon("arrowDown", 22)}</div><div><small>INBOUND</small><h3>Receipts</h3><p>${data.pending_receipts} waiting to be received</p></div>${icon("chevron", 18)}</a><a href="#/operations/delivery" class="flow-card outbound"><div class="flow-icon">${icon("arrowUp", 22)}</div><div><small>OUTBOUND</small><h3>Deliveries</h3><p>${data.pending_deliveries} ready or in progress</p></div>${icon("chevron", 18)}</a></div><div class="section-head compact"><h3>Recent operations</h3><a href="#/history">Move history ${icon("chevron", 14)}</a></div>${data.recent_operations.length ? `<div class="compact-list">${data.recent_operations.map((o) => `<a href="#/operation/${o.id}"><span class="mini-type ${o.type}">${icon(o.type === "receipt" ? "arrowDown" : o.type === "delivery" ? "arrowUp" : o.type === "transfer" ? "transfer" : "adjust", 16)}</span><span><strong>${escapeHtml(o.reference)}</strong><small>${escapeHtml(titleCase(o.type))} · ${escapeHtml(o.partner || "Internal")}</small></span>${badge(o.status)}</a>`).join("")}</div>` : empty("No operations yet", "Create a receipt to start your inventory history.", `<a class="btn secondary" href="#/new/receipt">Create receipt</a>`)}</section>
    <section class="panel attention"><div class="section-head"><div><h2>Needs attention</h2><p>Products at or below their reorder point</p></div>${icon("alert", 19)}</div>${data.low_stock_products.length ? `<div class="alert-list">${data.low_stock_products.map((p) => `<a href="#/stock"><div><strong>${escapeHtml(p.name)}</strong><small>${escapeHtml(p.sku)} · ${escapeHtml(p.category || "Uncategorized")}</small></div><span>${formatQuantity(p.on_hand)} ${escapeHtml(p.uom)}</span></a>`).join("")}</div>` : `<div class="calm-state">${icon("check", 28)}<strong>All stock levels look healthy</strong><p>Low stock alerts will appear here when products reach their reorder point.</p></div>`}<a class="text-link" href="#/products">Manage reorder points ${icon("chevron", 14)}</a></section></div>`;
  shell(content, "/dashboard", "Dashboard");
}

function renderProducts(rows) {
  const content = `${pageHead("Products", "Create your catalog and set reorder points for timely alerts.", `<div class="head-actions">${button("Add category", "category", "secondary")}${button(`${icon("plus", 17)} Add product`, "product")}</div>`)}
    <div class="toolbar"><label class="search-field">${icon("search", 18)}<input id="product-search" placeholder="Search name or SKU" aria-label="Search products"></label><select id="product-category" aria-label="Filter by category">${categoryOptions("", true)}</select><span class="toolbar-count" id="product-count">Showing ${countLabel(rows.length, "product")}</span></div>
    <div class="table-wrap"><table><thead><tr><th>Product</th><th>SKU</th><th>Category</th><th>Unit</th><th>On hand</th><th>Reorder at</th><th>Status</th><th></th></tr></thead><tbody id="product-rows">${productRows(rows)}</tbody></table></div><button class="btn secondary load-more" type="button" data-action="products-more" ${rows.length < pageSize ? "hidden" : ""}>Load more products</button>`;
  shell(content, "/products", "Products");
}
function productRows(rows) {
  return rows.length
    ? rows
        .map(
          (p) =>
            `<tr data-id="${p.id}" data-name="${escapeHtml(p.name)}"><td><strong>${escapeHtml(p.name)}</strong></td><td class="code">${escapeHtml(p.sku)}</td><td>${escapeHtml(p.category || "—")}</td><td>${escapeHtml(p.uom)}</td><td><strong>${formatQuantity(p.on_hand)}</strong></td><td>${formatQuantity(p.reorder_point)}</td><td>${p.low_stock ? '<span class="status-low">Low stock</span>' : '<span class="status-good">In stock</span>'}</td><td><button class="table-action" data-action="edit-product" data-id="${p.id}">Edit</button></td></tr>`,
        )
        .join("")
    : `<tr><td colspan="8">${empty("Your catalog starts here", "Add your first product to begin tracking stock.", button("Add product", "product", "secondary"))}</td></tr>`;
}

function renderStock(rows) {
  const content = `${pageHead("Stock overview", "See on-hand quantities at each location and reconcile physical counts.", `<a class="btn primary" href="#/new/adjustment">${icon("plus", 17)} Stock adjustment</a>`)}
    <div class="toolbar"><label class="search-field">${icon("search", 18)}<input id="stock-search" placeholder="Search name or SKU" aria-label="Search stock"></label><select id="stock-warehouse" aria-label="Filter by warehouse">${warehouseOptions("", true)}</select><select id="stock-category" aria-label="Filter by category">${categoryOptions("", true)}</select><span class="toolbar-count" id="stock-count">Showing ${countLabel(rows.length, "location")}</span></div>
    <div class="table-wrap"><table><thead><tr><th>Product</th><th>SKU</th><th>Warehouse</th><th>Location</th><th>Unit cost</th><th>On hand</th><th>Unit</th></tr></thead><tbody id="stock-rows">${stockRows(rows)}</tbody></table></div><button class="btn secondary load-more" type="button" data-action="stock-more" ${rows.length < pageSize ? "hidden" : ""}>Load more stock</button><p class="table-note">Stock totals change only when an operation is validated. Use an adjustment to record a physical count.</p>`;
  shell(content, "/stock", "Stock overview");
}
function stockRows(rows) {
  return rows.length
    ? rows
        .map(
          (r) =>
            `<tr><td><strong>${escapeHtml(r.product)}</strong></td><td class="code">${escapeHtml(r.sku)}</td><td>${escapeHtml(r.warehouse)}</td><td>${escapeHtml(r.location)}</td><td>${formatQuantity(r.unit_cost)}</td><td><strong>${formatQuantity(r.quantity)}</strong></td><td>${escapeHtml(r.uom)}</td></tr>`,
        )
        .join("")
    : `<tr><td colspan="7">${empty("No recorded stock yet", "Opening stock and validated receipts will appear here.", '<a class="btn secondary" href="#/products">View products</a>')}</td></tr>`;
}

function operationTitle(kind) {
  return (
    {
      all: "All operations",
      receipt: "Receipts",
      delivery: "Deliveries",
      transfer: "Internal transfers",
      adjustment: "Stock adjustments",
    }[kind] || "Operations"
  );
}
function operationDescription(kind) {
  return (
    {
      all: "Search and filter every stock document in one place.",
      receipt: "Record goods arriving from suppliers.",
      delivery: "Pick, pack, and ship outgoing stock.",
      transfer: "Move products between locations without changing total stock.",
      adjustment: "Match recorded stock to a physical count.",
    }[kind] || ""
  );
}
function movementEndpoint(o, side) {
  const location = side === "from" ? o.from_location : o.to_location;
  const warehouse = side === "from" ? o.from_warehouse : o.to_warehouse;
  if (location) return `${warehouse} / ${location}`;
  if (o.type === "adjustment") return side === "to" ? "Physical count" : "—";
  return o.partner || (side === "from" ? "Supplier" : "Customer");
}
function renderOperations(kind, rows) {
  const newKind = kind === "all" ? "receipt" : kind;
  const content = `${pageHead(operationTitle(kind), operationDescription(kind), `<a class="btn primary" href="#/new/${newKind}">${icon("plus", 17)} New ${newKind}</a>`)}
    <div class="toolbar"><label class="search-field">${icon("search", 18)}<input id="operation-search" placeholder="Search reference or contact" aria-label="Search operations"></label>${kind === "all" ? `<select id="operation-type" aria-label="Filter by document type"><option value="">All types</option>${["receipt", "delivery", "transfer", "adjustment"].map((t) => `<option value="${t}">${titleCase(t)}</option>`).join("")}</select>` : ""}<select id="operation-status" aria-label="Filter by status"><option value="">All statuses</option>${["draft", "waiting", "ready", "done", "canceled"].map((s) => `<option value="${s}">${titleCase(s)}</option>`).join("")}</select><select id="operation-warehouse" aria-label="Filter by warehouse">${warehouseOptions("", true)}</select><select id="operation-category" aria-label="Filter by category">${categoryOptions("", true)}</select><span class="toolbar-count" id="operation-count">Showing ${countLabel(rows.length, "record")}</span></div>
    <div class="table-wrap"><table><thead><tr><th>Reference</th><th>Type</th><th>From</th><th>To</th><th>Contact</th><th>Scheduled</th><th>Items</th><th>Status</th><th></th></tr></thead><tbody id="operation-rows">${operationRows(rows, kind)}</tbody></table></div><button class="btn secondary load-more" type="button" data-action="operations-more" ${rows.length < pageSize ? "hidden" : ""}>Load more operations</button>`;
  shell(content, `/operations/${kind}`, operationTitle(kind));
}
function operationRows(rows, kind) {
  return rows.length
    ? rows
        .map(
          (o) =>
            `<tr data-id="${o.id}"><td><a class="row-link code" href="#/operation/${o.id}">${escapeHtml(o.reference)}</a></td><td>${escapeHtml(titleCase(o.type))}</td><td>${escapeHtml(movementEndpoint(o, "from"))}</td><td>${escapeHtml(movementEndpoint(o, "to"))}</td><td>${escapeHtml(o.partner || "—")}</td><td>${escapeHtml(o.scheduled_date || "—")}</td><td>${o.line_count}</td><td>${badge(o.status)}</td><td><a class="table-action" href="#/operation/${o.id}">Open ${icon("chevron", 14)}</a></td></tr>`,
        )
        .join("")
    : `<tr><td colspan="9">${empty(`No ${operationTitle(kind).toLowerCase()} yet`, `Create a ${kind === "all" ? "receipt" : kind} to get started.`, `<a class="btn secondary" href="#/new/${kind === "all" ? "receipt" : kind}">New ${kind === "all" ? "receipt" : kind}</a>`)}</td></tr>`;
}

function lineRow(line = {}) {
  const selected = line.product_id
    ? `<option value="${line.product_id}" selected>${escapeHtml(line.sku)} · ${escapeHtml(line.product)}</option>`
    : "";
  return `<div class="line-row"><label>Product<input class="product-find" type="search" placeholder="Find by SKU or name" aria-label="Find product"><select name="product_id" required><option value="">Select product</option>${selected}</select></label><label>Quantity<input name="quantity" type="number" min="0" step="0.001" required value="${escapeHtml(line.quantity ?? "")}" placeholder="0.000"></label><button type="button" class="remove-line" data-action="remove-line" aria-label="Remove product">${icon("close", 18)}</button></div>`;
}
function operationForm(kind, operation = null) {
  const editing = Boolean(operation);
  const description =
    kind === "adjustment"
      ? "Enter the physical quantity counted at the selected location."
      : "Save a draft, then move it through the required steps before validating stock.";
  const content = `${pageHead(editing ? `Edit ${escapeHtml(operation.reference)}` : `New ${kind}`, description, `<a class="btn secondary" href="#${editing ? "/operation/" + operation.id : "/operations/" + kind}">Back to ${editing ? "operation" : operationTitle(kind).toLowerCase()}</a>`)}
    <form id="operation-form" data-kind="${kind}" data-id="${operation?.id || ""}" class="editor"><div class="editor-main"><section class="form-panel"><div class="panel-title"><span class="step-number">01</span><div><h2>Movement details</h2><p>Where this stock is going and who is responsible.</p></div></div><div class="form-grid">
      ${kind === "receipt" || kind === "delivery" ? `<label class="field">${kind === "receipt" ? "Supplier" : "Customer"}<input name="partner" value="${escapeHtml(operation?.partner || "")}" placeholder="${kind === "receipt" ? "Supplier name" : "Customer name"}"></label>` : ""}
      ${kind === "receipt" || kind === "transfer" ? `<label class="field">Destination location<select name="to_location_id" required>${locationOptions(operation?.to_location_id)}</select></label>` : ""}
      ${kind === "delivery" || kind === "transfer" || kind === "adjustment" ? `<label class="field">${kind === "adjustment" ? "Counted location" : "Source location"}<select name="from_location_id" required>${locationOptions(operation?.from_location_id)}</select></label>` : ""}
      <label class="field">Scheduled date<input name="scheduled_date" type="date" value="${escapeHtml(operation?.scheduled_date || "")}"></label>
      <label class="field full">Notes<textarea name="note" rows="3" placeholder="Add context for your team">${escapeHtml(operation?.note || "")}</textarea></label>
    </div></section><section class="form-panel"><div class="panel-title"><span class="step-number">02</span><div><h2>Products</h2><p>${kind === "adjustment" ? "Enter the new physical count for each product." : "Add the products and quantities in this movement."}</p></div></div><div id="line-rows" class="line-rows">${(operation?.lines?.length ? operation.lines : [{}]).map(lineRow).join("")}</div><button class="add-line" data-action="add-line" type="button">${icon("plus", 16)} Add another product</button></section></div>
    <aside class="editor-side"><div class="summary-card"><h3>Before you save</h3><p>${kind === "receipt" ? "Received stock will be added to the destination when you validate." : kind === "delivery" ? "Pick and pack before marking ready. Validation removes stock from the source." : kind === "transfer" ? "Validation removes stock from the source and adds it to the destination in one step." : "Validation replaces the recorded quantity with your physical count."}</p><div class="summary-rule"></div><span>All completed changes appear in Move history.</span></div><button type="submit" class="btn primary save-btn">${editing ? "Save changes" : "Save draft"} ${icon("chevron", 17)}</button></aside></form>`;
  shell(
    content,
    `/operations/${kind}`,
    editing ? operation.reference : `New ${kind}`,
  );
}

function renderOperationDetail(o) {
  const steps =
    o.type === "delivery"
      ? ["Draft", "Waiting", "Picked", "Packed", "Ready", "Done"]
      : ["Draft", "Waiting", "Ready", "Done"];
  const position =
    o.status === "done"
      ? steps.length
      : o.status === "ready"
        ? steps.indexOf("Ready") + 1
        : o.status === "waiting"
          ? o.packed
            ? 4
            : o.picked
              ? 3
              : 2
          : 1;
  const actions = [];
  if (o.status === "draft")
    actions.push(button("Submit", `op-action:submit:${o.id}`, "secondary"));
  if (
    o.type === "delivery" &&
    ["waiting", "ready"].includes(o.status) &&
    !o.picked
  )
    actions.push(button("Mark picked", `op-action:pick:${o.id}`, "secondary"));
  if (
    o.type === "delivery" &&
    ["waiting", "ready"].includes(o.status) &&
    o.picked &&
    !o.packed
  )
    actions.push(button("Mark packed", `op-action:pack:${o.id}`, "secondary"));
  if (
    ["draft", "waiting"].includes(o.status) &&
    (o.type !== "delivery" || o.packed)
  )
    actions.push(button("Mark ready", `op-action:ready:${o.id}`, "secondary"));
  if (o.status === "ready")
    actions.push(
      button(`${icon("check", 16)} Validate ${o.type}`, `op-validate:${o.id}`),
    );
  if (["draft", "waiting"].includes(o.status))
    actions.push(`<a class="btn ghost" href="#/edit/${o.id}">Edit draft</a>`);
  if (["draft", "waiting", "ready"].includes(o.status))
    actions.push(button("Cancel", `op-action:cancel:${o.id}`, "ghost danger"));
  const content = `<div class="detail-back"><a href="#/operations/${o.type}">← Back to ${operationTitle(o.type).toLowerCase()}</a></div>${pageHead(o.reference, `${titleCase(o.type)} · Created ${formatDate(o.created_at)}`, badge(o.status))}<div class="detail-actions">${actions.join("")}${button("Print", "print", "ghost")}</div>
    ${o.status === "canceled" ? '<div class="notice-bar">This operation was canceled. It did not change stock.</div>' : `<div class="stepper">${steps.map((step, i) => `<div class="step ${i < position ? "complete" : ""}"><span>${i < position ? icon("check", 13) : i + 1}</span><small>${step}</small></div>`).join("")}</div>`}
    <div class="detail-grid"><section class="panel"><div class="section-head"><h2>Products</h2><span>${o.lines.length} items</span></div><div class="table-wrap inset"><table><thead><tr><th>Product</th><th>SKU</th><th>${o.type === "adjustment" ? "Counted quantity" : "Quantity"}</th><th>Unit</th></tr></thead><tbody>${o.lines.map((line) => `<tr><td><strong>${escapeHtml(line.product)}</strong></td><td class="code">${escapeHtml(line.sku)}</td><td><strong>${formatQuantity(line.quantity)}</strong></td><td>${escapeHtml(line.uom)}</td></tr>`).join("")}</tbody></table></div></section><aside class="panel detail-meta"><h2>Movement details</h2><dl><div><dt>From</dt><dd>${escapeHtml(movementEndpoint(o, "from"))}</dd></div><div><dt>To</dt><dd>${escapeHtml(movementEndpoint(o, "to"))}</dd></div><div><dt>Contact</dt><dd>${escapeHtml(o.partner || "—")}</dd></div><div><dt>Scheduled</dt><dd>${escapeHtml(o.scheduled_date || "—")}</dd></div><div><dt>Responsible</dt><dd>${escapeHtml(o.responsible || "—")}</dd></div><div><dt>Notes</dt><dd>${escapeHtml(o.note || "—")}</dd></div></dl></aside></div>`;
  shell(content, `/operations/${o.type}`, o.reference);
}

function renderHistory(rows) {
  const content = `${pageHead("Move history", "A permanent record of validated stock changes across every location.")}
    <div class="toolbar"><label class="search-field">${icon("search", 18)}<input id="history-search" placeholder="Search reference or SKU" aria-label="Search history"></label><select id="history-warehouse" aria-label="Filter by warehouse">${warehouseOptions("", true)}</select><label class="search-field">${icon("search", 18)}<input id="history-product-search" type="search" placeholder="Find product" aria-label="Find product filter"></label><select id="history-product" aria-label="Filter by product"><option value="">All products</option></select><span class="toolbar-count" id="history-count">Showing ${countLabel(rows.length, "movement")}</span></div>
    <div class="table-wrap"><table><thead><tr><th>Date</th><th>Reference</th><th>Product</th><th>Warehouse</th><th>Location</th><th>Change</th><th>Balance</th></tr></thead><tbody id="history-rows">${historyRows(rows)}</tbody></table></div><button class="btn secondary load-more" type="button" data-action="history-more" ${rows.length < pageSize ? "hidden" : ""}>Load more movements</button><p class="table-note">Transfers appear twice: stock leaves one location and enters another. Their total change is zero.</p>`;
  shell(content, "/history", "Move history");
}
function historyRows(rows) {
  return rows.length
    ? rows.map(historyRow).join("")
    : `<tr><td colspan="7">${empty("No movements yet", "Validated operations will appear here, with their exact stock effect.")}</td></tr>`;
}
function historyRow(m) {
  return `<tr data-id="${m.id}"><td>${formatDate(m.created_at)}</td><td><a class="row-link code" href="#/operation/${m.operation_id}">${escapeHtml(m.reference)}</a></td><td><strong>${escapeHtml(m.product)}</strong><small class="sub-cell">${escapeHtml(m.sku)}</small></td><td>${escapeHtml(m.warehouse)}</td><td>${escapeHtml(m.location)}</td><td class="${m.delta >= 0 ? "positive" : "negative"}"><strong>${m.delta > 0 ? "+" : ""}${formatQuantity(m.delta)} ${escapeHtml(m.uom)}</strong></td><td>${formatQuantity(m.balance)} ${escapeHtml(m.uom)}</td></tr>`;
}

function renderWarehouses() {
  const data = referenceData();
  const list = data.warehouses;
  const locationsByWarehouse = new Map();
  for (const location of data.locations) {
    if (!locationsByWarehouse.has(location.warehouse_id))
      locationsByWarehouse.set(location.warehouse_id, []);
    locationsByWarehouse.get(location.warehouse_id).push(location);
  }
  const content = `${pageHead("Warehouses & locations", "Organize stock by warehouse, room, rack, or any place your team counts.", button(`${icon("plus", 17)} Add warehouse`, "warehouse"))}
    ${
      list.length
        ? `<div class="warehouse-grid">${list
            .map((w) => {
              const locations = locationsByWarehouse.get(w.id) || [];
              return `<section class="warehouse-card"><div class="warehouse-title"><div class="warehouse-icon">${icon("warehouse", 23)}</div><div><h2>${escapeHtml(w.name)}</h2><span>${escapeHtml(w.code)}</span></div><button class="table-action warehouse-edit" data-action="edit-warehouse" data-id="${w.id}">Edit</button></div><p>${escapeHtml(w.address || "No address added")}</p><div class="warehouse-locations"><div class="warehouse-subhead">LOCATIONS <span>${locations.length}</span></div>${locations
                  .map(
                    (l) =>
                      `<div><span>${escapeHtml(l.name)}</span><span class="location-meta"><code>${escapeHtml(l.code)}</code><button class="table-action" data-action="edit-location" data-id="${l.id}">Edit</button></span></div>`,
                  )
                  .join(
                    "",
                  )}</div><button class="add-location" data-action="location" data-id="${w.id}">${icon("plus", 15)} Add location</button></section>`;
            })
            .join("")}</div>`
        : empty(
            "Start with a warehouse",
            "Each warehouse gets a Main stock location automatically. Add more locations as you need them.",
            button("Add warehouse", "warehouse", "secondary"),
          )
    }`;
  shell(content, "/warehouses", "Warehouses");
}

function renderProfile() {
  const content = `${pageHead("My profile", "Keep your account details up to date.")}<div class="profile-panel"><div class="profile-avatar">${escapeHtml(state.user.name[0].toUpperCase())}</div><form id="profile-form"><label class="field">Full name<input name="name" required value="${escapeHtml(state.user.name)}"></label><label class="field">Company<input value="${escapeHtml(state.user.company)}" disabled></label><label class="field">Email address<input value="${escapeHtml(state.user.email)}" disabled></label><p>Your email is used for sign-in and password recovery.</p><div class="profile-actions"><button class="btn primary" type="submit">Save profile</button><button class="btn secondary" type="button" data-action="logout">Sign out</button></div></form><form id="invite-form"><h2>Invite a teammate</h2><p>Create a link for someone to join ${escapeHtml(state.user.company)}. The link expires in seven days and only works with their email address.</p><label class="field">Teammate's email<input name="email" type="email" required placeholder="teammate@company.com"></label><button class="btn secondary" type="submit">Create invitation</button><div id="invite-result" hidden><label class="field">Invitation link<input id="invite-link" readonly aria-label="Invitation link"></label><button class="btn secondary" type="button" data-action="copy-invite">Copy link</button></div></form></div>`;
  shell(content, "/profile", "My profile");
}

async function render() {
  if (!state.user) return renderAuth();
  const route = location.hash.slice(1) || "/dashboard";
  const id = ++state.renderId;
  clearTimeout(changed.timer);
  productFilterController?.abort();
  stockFilterController?.abort();
  operationFilterController?.abort();
  historyFilterController?.abort();
  const current = () => id === state.renderId;
  try {
    if (route === "/dashboard") {
      const data = await api("/dashboard");
      if (current()) renderDashboard(data);
      return;
    }
    if (route === "/products") {
      const [products] = await Promise.all([api("/products"), loadFilters()]);
      if (current()) renderProducts(products);
      return;
    }
    if (route === "/stock") {
      const [rows] = await Promise.all([api("/stock"), loadFilters()]);
      if (current()) renderStock(rows);
      return;
    }
    if (route === "/history") {
      const [rows] = await Promise.all([api("/history"), loadFilters()]);
      if (current()) renderHistory(rows);
      return;
    }
    if (route === "/warehouses") {
      await loadFilters();
      if (current()) renderWarehouses();
      return;
    }
    if (route === "/profile") return renderProfile();
    const parts = route.split("/").filter(Boolean);
    if (
      parts[0] === "operations" &&
      ["all", "receipt", "delivery", "transfer", "adjustment"].includes(
        parts[1],
      )
    ) {
      const kind = parts[1];
      const [rows] = await Promise.all([
        api("/operations" + queryString({ type: kind === "all" ? "" : kind })),
        loadFilters(),
      ]);
      if (current()) renderOperations(kind, rows);
      return;
    }
    if (
      parts[0] === "new" &&
      ["receipt", "delivery", "transfer", "adjustment"].includes(parts[1])
    ) {
      await loadFilters();
      if (current()) operationForm(parts[1]);
      return;
    }
    if (parts[0] === "operation" && /^\d+$/.test(parts[1])) {
      const operation = await api(`/operations/${parts[1]}`);
      if (current()) renderOperationDetail(operation);
      return;
    }
    if (parts[0] === "edit" && /^\d+$/.test(parts[1])) {
      const [operation] = await Promise.all([
        api(`/operations/${parts[1]}`),
        loadFilters(),
      ]);
      if (current()) operationForm(operation.type, operation);
      return;
    }
    location.hash = "/dashboard";
  } catch (error) {
    if (current()) showNotice(error.message, true);
  }
}

function openModal(title, body, formId) {
  const dialog = document.querySelector("#dialog");
  dialog.innerHTML = `<div class="modal-head"><h2>${title}</h2><button class="icon-button" type="button" data-action="close-modal" aria-label="Close">${icon("close", 19)}</button></div><form id="${formId}" class="modal-form">${body}<div class="modal-foot"><button type="button" class="btn secondary" data-action="close-modal">Cancel</button><button type="submit" class="btn primary">Save</button></div></form>`;
  dialog.showModal();
}
async function productModal(id = null) {
  const p = id ? await api(`/products/${id}`) : null;
  openModal(
    p ? "Edit product" : "Add product",
    `<input type="hidden" name="id" value="${p?.id || ""}"><div class="modal-fields"><label class="field">Product name<input name="name" required value="${escapeHtml(p?.name || "")}" placeholder="e.g. Steel rods"></label><label class="field">SKU / code<input name="sku" required value="${escapeHtml(p?.sku || "")}" placeholder="e.g. STEEL-001"></label><label class="field">Category<select name="category_id">${categoryOptions(p?.category_id)}</select></label><label class="field">Unit of measure<input name="uom" required value="${escapeHtml(p?.uom || "")}" placeholder="e.g. pcs, kg, boxes"></label><label class="field">Unit cost<input name="unit_cost" type="number" min="0" step="0.01" value="${p?.unit_cost ?? 0}"></label><label class="field">Reorder point<input name="reorder_point" type="number" min="0" step="0.001" value="${p?.reorder_point ?? 0}"></label>${p ? `<label class="check-field"><input type="checkbox" name="active" ${p.active ? "checked" : ""}> Active product</label>` : `<div class="modal-divider">OPTIONAL OPENING STOCK</div><label class="field">Initial quantity<input name="initial_stock" type="number" min="0" step="0.001" value="0"></label><label class="field">Initial location<select name="initial_location_id">${locationOptions()}</select></label>`}</div>`,
    "product-form",
  );
}
function simpleModal(kind, warehouseId = null) {
  if (kind === "category")
    return openModal(
      "New category",
      '<label class="field">Category name<input name="name" required placeholder="e.g. Raw materials"></label>',
      "category-form",
    );
  if (kind === "warehouse")
    return openModal(
      "Add warehouse",
      '<label class="field">Warehouse name<input name="name" required placeholder="e.g. Main warehouse"></label><label class="field">Short code<input name="code" required placeholder="e.g. WH1"></label><label class="field">Address<input name="address" placeholder="Optional address"></label><p class="form-hint">A Main stock location will be created automatically.</p>',
      "warehouse-form",
    );
  if (kind === "location")
    return openModal(
      "Add location",
      `<input type="hidden" name="warehouse_id" value="${warehouseId}"><label class="field">Location name<input name="name" required placeholder="e.g. Rack A"></label><label class="field">Short code<input name="code" required placeholder="e.g. RACK-A"></label>`,
      "location-form",
    );
  if (kind === "edit-warehouse") {
    const w = referenceData().warehouses.find(
      (item) => item.id === Number(warehouseId),
    );
    return openModal(
      "Edit warehouse",
      `<input type="hidden" name="id" value="${w.id}"><label class="field">Warehouse name<input name="name" required value="${escapeHtml(w.name)}"></label><label class="field">Short code<input name="code" required value="${escapeHtml(w.code)}"></label><label class="field">Address<input name="address" value="${escapeHtml(w.address)}"></label>`,
      "warehouse-form",
    );
  }
  if (kind === "edit-location") {
    const l = referenceData().locations.find(
      (item) => item.id === Number(warehouseId),
    );
    return openModal(
      "Edit location",
      `<input type="hidden" name="id" value="${l.id}"><label class="field">Location name<input name="name" required value="${escapeHtml(l.name)}"></label><label class="field">Short code<input name="code" required value="${escapeHtml(l.code)}"></label>`,
      "location-form",
    );
  }
}

async function submitForm(event) {
  const form = event.target;
  const formId = form.getAttribute("id");
  if (
    ![
      "auth-form",
      "product-form",
      "category-form",
      "warehouse-form",
      "location-form",
      "operation-form",
      "profile-form",
      "invite-form",
    ].includes(formId)
  )
    return;
  event.preventDefault();
  const values = Object.fromEntries(new FormData(form));
  const submit = form.querySelector("[type=submit]");
  if (submit) submit.disabled = true;
  try {
    if (formId === "auth-form") {
      const mode = state.authMode;
      let path =
        mode === "signup"
          ? "/signup"
          : mode === "login"
            ? "/login"
            : mode === "reset"
              ? "/password-reset/request"
              : "/password-reset/confirm";
      const result = await api(path, {
        method: "POST",
        body: JSON.stringify(mode === "signup" && invitation.has("invite") ? { ...values, invite_token: invitation.get("invite") } : values),
      });
      if (mode === "reset") {
        state.authMode = "reset-confirm";
        state.devResetCode = result.development_code || "";
        renderAuth();
        showNotice(result.message);
        return;
      }
      if (mode === "reset-confirm") {
        state.authMode = "login";
        renderAuth();
        showNotice(result.message);
        return;
      }
      state.user = result.user;
      state.csrf = result.csrf;
      clearFilters();
      if (location.hash === "#/dashboard") await render();
      else location.hash = "/dashboard";
      return;
    }
    if (formId === "invite-form") {
      const result = await api("/invitations", {
        method: "POST",
        body: JSON.stringify(values),
      });
      const link = `${location.origin}${location.pathname}#/signup?invite=${encodeURIComponent(result.token)}&email=${encodeURIComponent(values.email)}`;
      document.querySelector("#invite-link").value = link;
      document.querySelector("#invite-result").hidden = false;
      showNotice("Invitation link is ready to share");
      return;
    }
    if (formId === "product-form") {
      values.active = Boolean(form.querySelector("[name=active]")?.checked);
      if (!values.id) delete values.active;
      await api(values.id ? `/products/${values.id}` : "/products", {
        method: values.id ? "PUT" : "POST",
        body: JSON.stringify(values),
      });
      showNotice(values.id ? "Product updated" : "Product created");
    } else if (
      ["category-form", "warehouse-form", "location-form"].includes(formId)
    ) {
      const kind = formId.split("-")[0];
      const path =
        "/" +
        {
          category: "categories",
          warehouse: "warehouses",
          location: "locations",
        }[kind];
      await api(values.id ? `${path}/${values.id}` : path, {
        method: values.id ? "PUT" : "POST",
        body: JSON.stringify(values),
      });
      showNotice(`${titleCase(kind)} ${values.id ? "updated" : "created"}`);
    } else if (formId === "operation-form") {
      values.type = form.dataset.kind;
      values.lines = Array.from(form.querySelectorAll(".line-row")).map(
        (row) => ({
          product_id: row.querySelector("[name=product_id]").value,
          quantity: row.querySelector("[name=quantity]").value,
        }),
      );
      const id = form.dataset.id;
      const result = await api(id ? `/operations/${id}` : "/operations", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(values),
      });
      clearFilters();
      showNotice(id ? "Operation updated" : "Draft saved");
      location.hash = "/operation/" + (id || result.id);
      return;
    } else if (formId === "profile-form") {
      const result = await api("/profile", {
        method: "PATCH",
        body: JSON.stringify(values),
      });
      state.user.name = result.name;
      showNotice("Profile updated");
    }
    document.querySelector("#dialog")?.close();
    if (formId !== "profile-form") clearFilters();
    await render();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    if (submit) submit.disabled = false;
  }
}

async function clickAction(event) {
  const target = event.target.closest("[data-action], [data-auth]");
  if (!target) return;
  const action = target.dataset.action;
  if (target.dataset.auth) {
    state.authMode = target.dataset.auth;
    renderAuth();
    return;
  }
  if (action === "menu")
    return document.querySelector(".shell")?.classList.toggle("menu-open");
  if (action === "copy-invite") {
    await navigator.clipboard.writeText(document.querySelector("#invite-link").value);
    showNotice("Invitation link copied");
    return;
  }
  if (action === "close-modal")
    return document.querySelector("#dialog")?.close();
  if (action === "product") return productModal().catch((error) => showNotice(error.message, true));
  if (action === "edit-product") return productModal(target.dataset.id).catch((error) => showNotice(error.message, true));
  if (
    [
      "category",
      "warehouse",
      "location",
      "edit-warehouse",
      "edit-location",
    ].includes(action)
  )
    return simpleModal(action, target.dataset.id);
  if (action === "add-line")
    return document
      .querySelector("#line-rows")
      ?.insertAdjacentHTML("beforeend", lineRow());
  if (action === "remove-line") {
    if (document.querySelectorAll(".line-row").length > 1)
      target.closest(".line-row").remove();
    return;
  }
  if (action === "print") return window.print();
  if (action === "products-more") {
    target.disabled = true;
    try {
      const count = document.querySelectorAll("#product-rows tr").length;
      const last = document.querySelector("#product-rows tr:last-child")?.dataset;
      const query = productQuery(last?.name, last?.id);
      const rows = await api("/products" + query);
      if (!target.isConnected || query !== productQuery(last?.name, last?.id)) return;
      if (rows.length)
        document.querySelector("#product-rows").insertAdjacentHTML("beforeend", productRows(rows));
      document.querySelector("#product-count").textContent = `Showing ${countLabel(count + rows.length, "product")}`;
      target.hidden = rows.length < pageSize;
    } catch (error) {
      showNotice(error.message, true);
    } finally {
      target.disabled = false;
    }
    return;
  }
  if (action === "stock-more") {
    target.disabled = true;
    try {
      const count = document.querySelectorAll("#stock-rows tr").length;
      const query = stockQuery(count);
      const rows = await api("/stock" + query);
      if (!target.isConnected || query !== stockQuery(count)) return;
      if (rows.length)
        document
          .querySelector("#stock-rows")
          .insertAdjacentHTML("beforeend", stockRows(rows));
      document.querySelector("#stock-count").textContent =
        `Showing ${countLabel(count + rows.length, "location")}`;
      target.hidden = rows.length < pageSize;
    } catch (error) {
      showNotice(error.message, true);
    } finally {
      target.disabled = false;
    }
    return;
  }
  if (action === "operations-more") {
    target.disabled = true;
    try {
      const count = document.querySelectorAll("#operation-rows tr").length;
      const before = document.querySelector("#operation-rows tr:last-child")?.dataset.id;
      const query = operationQuery(before);
      const rows = await api("/operations" + query);
      if (!target.isConnected || query !== operationQuery(before)) return;
      if (rows.length)
        document
          .querySelector("#operation-rows")
          .insertAdjacentHTML("beforeend", operationRows(rows, "all"));
      document.querySelector("#operation-count").textContent =
        `Showing ${countLabel(count + rows.length, "record")}`;
      target.hidden = rows.length < pageSize;
    } catch (error) {
      showNotice(error.message, true);
    } finally {
      target.disabled = false;
    }
    return;
  }
  if (action === "history-more") {
    target.disabled = true;
    try {
      const count = document.querySelectorAll("#history-rows tr").length;
      const before = document.querySelector("#history-rows tr:last-child")?.dataset.id;
      const query = historyQuery(before);
      const rows = await api("/history" + query);
      if (!target.isConnected || query !== historyQuery(before)) return;
      document
        .querySelector("#history-rows")
        .insertAdjacentHTML("beforeend", rows.map(historyRow).join(""));
      document.querySelector("#history-count").textContent =
        `Showing ${countLabel(count + rows.length, "movement")}`;
      target.hidden = rows.length < pageSize;
    } catch (error) {
      showNotice(error.message, true);
    } finally {
      target.disabled = false;
    }
    return;
  }
  try {
    if (action === "logout") {
      await api("/logout", { method: "POST", body: "{}" });
      state.user = null;
      state.csrf = "";
      clearFilters();
      renderAuth();
      return;
    }
    if (action?.startsWith("op-action:")) {
      const [, operation, id] = action.split(":");
      if (
        operation === "cancel" &&
        !window.confirm("Cancel this operation? It will not change stock.")
      )
        return;
      await api(`/operations/${id}/action`, {
        method: "POST",
        body: JSON.stringify({ action: operation }),
      });
      showNotice(
        `Operation ${{ ready: "marked ready", submit: "submitted", pick: "picked", pack: "packed", cancel: "canceled" }[operation] || "updated"}`,
      );
      return await render();
    }
    if (action?.startsWith("op-validate:")) {
      const id = action.split(":")[1];
      await api(`/operations/${id}/validate`, { method: "POST", body: "{}" });
      showNotice("Stock updated and movement logged");
      clearFilters();
      return await render();
    }
  } catch (error) {
    showNotice(error.message, true);
  }
}

function productQuery(afterName = "", afterId = 0) {
  return queryString({
    search: document.querySelector("#product-search")?.value,
    category_id: document.querySelector("#product-category")?.value,
    after_name: afterName,
    after_id: afterId,
  });
}
let productFilterController;
async function filterProducts() {
  productFilterController?.abort();
  const controller = new AbortController();
  productFilterController = controller;
  let rows;
  try {
    rows = await api("/products" + productQuery(), { signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") return;
    throw error;
  }
  if (controller.signal.aborted) return;
  const tbody = document.querySelector("#product-rows");
  if (tbody) tbody.innerHTML = productRows(rows);
  const count = document.querySelector("#product-count");
  if (count) count.textContent = `Showing ${countLabel(rows.length, "product")}`;
  const more = document.querySelector('[data-action="products-more"]');
  if (more) more.hidden = rows.length < pageSize;
}

function stockQuery(offset) {
  return queryString({
    search: document.querySelector("#stock-search")?.value,
    warehouse_id: document.querySelector("#stock-warehouse")?.value,
    category_id: document.querySelector("#stock-category")?.value,
    offset,
  });
}
let stockFilterController;
async function filterStock() {
  stockFilterController?.abort();
  const controller = new AbortController();
  stockFilterController = controller;
  let rows;
  try {
    rows = await api("/stock" + stockQuery(0), {
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === "AbortError") return;
    throw error;
  }
  if (controller.signal.aborted) return;
  const tbody = document.querySelector("#stock-rows");
  if (tbody) tbody.innerHTML = stockRows(rows);
  const count = document.querySelector("#stock-count");
  if (count) count.textContent = `Showing ${countLabel(rows.length, "location")}`;
  const more = document.querySelector('[data-action="stock-more"]');
  if (more) more.hidden = rows.length < pageSize;
}

function operationQuery(beforeId = 0) {
  const route = location.hash.slice(1).split("/");
  const kind = route[2];
  return queryString({
    type:
      kind === "all" ? document.querySelector("#operation-type")?.value : kind,
    status: document.querySelector("#operation-status")?.value,
    warehouse_id: document.querySelector("#operation-warehouse")?.value,
    category_id: document.querySelector("#operation-category")?.value,
    search: document.querySelector("#operation-search")?.value,
    before_id: beforeId,
  });
}
let operationFilterController;
async function filterOperations() {
  const kind = location.hash.slice(1).split("/")[2];
  const query = operationQuery(0);
  operationFilterController?.abort();
  const controller = new AbortController();
  operationFilterController = controller;
  let rows;
  try {
    rows = await api("/operations" + query, { signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") return;
    throw error;
  }
  if (controller.signal.aborted) return;
  const tbody = document.querySelector("#operation-rows");
  if (tbody) tbody.innerHTML = operationRows(rows, kind);
  const count = document.querySelector("#operation-count");
  if (count) count.textContent = `Showing ${countLabel(rows.length, "record")}`;
  const more = document.querySelector('[data-action="operations-more"]');
  if (more) more.hidden = rows.length < pageSize;
}
let historyFilterController;
async function filterHistory() {
  historyFilterController?.abort();
  const controller = new AbortController();
  historyFilterController = controller;
  let rows;
  try {
    rows = await api("/history" + historyQuery(0), {
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === "AbortError") return;
    throw error;
  }
  if (controller.signal.aborted) return;
  const tbody = document.querySelector("#history-rows");
  if (tbody) tbody.innerHTML = historyRows(rows);
  const count = document.querySelector("#history-count");
  if (count) count.textContent = `Showing ${countLabel(rows.length, "movement")}`;
  const more = document.querySelector('[data-action="history-more"]');
  if (more) more.hidden = rows.length < pageSize;
}
function historyQuery(beforeId = 0) {
  return queryString({
    before_id: beforeId,
    search: document.querySelector("#history-search")?.value,
    warehouse_id: document.querySelector("#history-warehouse")?.value,
    product_id: document.querySelector("#history-product")?.value,
  });
}
let productChoiceTimer;
let productChoiceController;
function queueProductChoices(input, delay = 150) {
  clearTimeout(productChoiceTimer);
  productChoiceController?.abort();
  productChoiceTimer = setTimeout(async () => {
    const controller = new AbortController();
    productChoiceController = controller;
    const search = input.value;
    const select = input.id === "history-product-search"
      ? document.querySelector("#history-product")
      : input.closest(".line-row")?.querySelector("[name=product_id]");
    if (!select) return;
    const selected = select.value;
    const selectedLabel = select.selectedOptions[0]?.textContent;
    try {
      const products = await api("/product-choices" + queryString({ search }), {
        signal: controller.signal,
      });
      if (controller.signal.aborted || !input.isConnected || input.value !== search) return;
      const label = input.id === "history-product-search" ? "All products" : "Select product";
      const keep = selected && !products.some((product) => String(product.id) === selected)
        ? `<option value="${selected}">${escapeHtml(selectedLabel)}</option>`
        : "";
      select.innerHTML = `<option value="">${label}</option>${keep}${products.map((product) => `<option value="${product.id}">${escapeHtml(product.sku)} · ${escapeHtml(product.name)}</option>`).join("")}`;
      select.value = selected;
    } catch (error) {
      if (error.name !== "AbortError") showNotice(error.message, true);
    }
  }, delay);
}
function changed(event) {
  if (event.target.matches(".product-find, #history-product-search")) {
    if (event.type !== "input") return;
    if (event.target.id === "history-product-search") {
      const selected = document.querySelector("#history-product");
      if (selected?.value) {
        selected.value = "";
        filterHistory().catch((error) => showNotice(error.message, true));
      }
    } else {
      const selected = event.target.closest(".line-row")?.querySelector("[name=product_id]");
      if (selected) selected.value = "";
    }
    queueProductChoices(event.target);
    return;
  }
  if (event.target.closest(".toolbar")) {
    if (event.type === "input" && event.target.tagName !== "INPUT") return;
    if (event.type === "change" && event.target.tagName === "INPUT") return;
    if (
      event.target.id.startsWith("product-") ||
      event.target.id.startsWith("stock-") ||
      event.target.id.startsWith("operation-") ||
      event.target.id.startsWith("history-")
    ) {
      clearTimeout(changed.timer);
      const task = event.target.id.startsWith("product-")
        ? filterProducts
        : event.target.id.startsWith("stock-")
        ? filterStock
        : event.target.id.startsWith("operation-")
          ? filterOperations
          : filterHistory;
      changed.timer = setTimeout(() => {
        task().catch((error) => showNotice(error.message, true));
      }, event.type === "input" ? 180 : 0);
    }
  }
}

document.addEventListener("submit", submitForm);
document.addEventListener("click", clickAction);
document.addEventListener("input", changed);
document.addEventListener("change", changed);
document.addEventListener("focusin", (event) => {
  if (event.target.matches(".product-find, #history-product-search"))
    queueProductChoices(event.target, 0);
});
window.addEventListener("hashchange", render);

(async () => {
  try {
    const session = await api("/session");
    state.user = session.user;
    state.csrf = session.csrf || "";
    await render();
  } catch (error) {
    showNotice(error.message, true);
    renderAuth();
  }
})();
