(function () {
  const state = {
    products: [],
    selectedId: "",
    z: 20,
  };

  const computer = document.querySelector(".computer");
  const libraryWindow = document.querySelector('[data-window="library"]');
  const desktopIcons = document.querySelector("[data-desktop-icons]");
  const appGrid = document.querySelector("[data-app-grid]");
  const dock = document.querySelector("[data-dock]");
  const selectedName = document.querySelector("[data-selected-name]");
  const clock = document.querySelector("[data-clock]");
  const windowTitle = document.querySelector("[data-window-title]");
  const windowStatus = document.querySelector("[data-window-status]");
  const currentTitle = document.querySelector("[data-current-title]");
  const currentDesc = document.querySelector("[data-current-desc]");
  const currentAvatar = document.querySelector("[data-current-avatar]");
  const previewTitle = document.querySelector("[data-preview-title]");
  const previewDesc = document.querySelector("[data-preview-desc]");
  const metaLayout = document.querySelector("[data-meta-layout]");
  const metaStatus = document.querySelector("[data-meta-status]");
  const suggestions = document.querySelector("[data-suggestions]");
  const openLink = document.querySelector("[data-open-link]");

  function text(value, fallback) {
    const normalized = String(value || "").trim();
    return normalized || fallback || "";
  }

  function initials(product) {
    const raw = text(product.avatar, "") || text(product.title, "A").slice(0, 1);
    return raw.slice(0, 2).toUpperCase();
  }

  function layoutLabel(layout) {
    switch (layout) {
      case "chat_only":
        return "Chat app";
      case "chat_left_canvas_right":
        return "Workspace app";
      case "canvas_full":
        return "Full-screen app";
      case "chat_center":
        return "Focused app";
      default:
        return "AI app";
    }
  }

  function statusLabel(status) {
    switch (status) {
      case "ready":
        return "Ready";
      case "generating":
        return "Preparing";
      case "empty":
        return "Not started";
      case "error":
        return "Needs attention";
      default:
        return text(status, "Unknown");
    }
  }

  function productUrl(product) {
    const kind = encodeURIComponent(text(product.kind || product.id, "general"));
    return `/?assistant=${kind}`;
  }

  function normalizeProducts(payload) {
    const list = Array.isArray(payload && payload.products) ? payload.products : [];
    return list
      .filter((item) => item && item.id)
      .map((item) => ({
        ...item,
        id: text(item.id, ""),
        title: text(item.title || item.name, "AI App"),
        desc: text(item.desc || item.description, ""),
        product_layout: text(item.product_layout || item.productLayout || item.layout, "chat_center"),
        ui_status: text(item.ui_status || item.status, "empty"),
        preview_url: text(item.preview_url || item.previewUrl, ""),
        tools: Array.isArray(item.tools) ? item.tools : [],
        suggestions: Array.isArray(item.suggestions) ? item.suggestions : [],
      }));
  }

  function currentProduct() {
    return state.products.find((item) => item.id === state.selectedId) || state.products[0] || null;
  }

  function buildIcon(product, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.dataset.productId = product.id;
    button.setAttribute("aria-current", product.id === state.selectedId ? "true" : "false");

    const icon = document.createElement("span");
    icon.className = "app-icon-art";
    icon.textContent = initials(product);

    const label = document.createElement("span");
    label.className = "app-icon-label";
    label.textContent = text(product.title, "AI App");

    button.append(icon, label);
    button.addEventListener("click", () => selectProduct(product.id, {openLibrary: className === "dock-icon"}));
    button.addEventListener("dblclick", () => openSelectedApp());
    return button;
  }

  function renderAppGrid() {
    appGrid.replaceChildren(...state.products.map((product) => {
      const button = buildIcon(product, "library-app");
      const description = document.createElement("span");
      description.className = "library-app-desc";
      description.textContent = text(product.desc, layoutLabel(product.product_layout));
      button.append(description);
      return button;
    }));
  }

  function renderDesktopIcons() {
    const apps = state.products.slice(0, 9).map((product) => buildIcon(product, "desktop-icon"));
    const newApp = document.createElement("button");
    newApp.type = "button";
    newApp.className = "desktop-icon is-disabled";
    newApp.disabled = true;
    const art = document.createElement("span");
    art.className = "app-icon-art";
    art.textContent = "+";
    const label = document.createElement("span");
    label.className = "app-icon-label";
    label.textContent = "New App";
    newApp.append(art, label);
    desktopIcons.replaceChildren(...apps, newApp);
  }

  function renderDock() {
    const library = document.createElement("button");
    library.type = "button";
    library.className = "dock-icon system";
    library.title = "AI Computer";
    library.textContent = "N";
    library.addEventListener("click", openLibrary);

    const productButtons = state.products.slice(0, 8).map((product) => buildIcon(product, "dock-icon"));
    dock.replaceChildren(library, ...productButtons);
  }

  function renderSuggestions(product) {
    const rows = product.suggestions.slice(0, 3).map((item) => {
      const value = Array.isArray(item) ? item[1] || item[0] : item;
      const prompt = Array.isArray(item) ? item[0] : item;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion";
      button.textContent = text(value, "Start");
      button.title = text(prompt, "");
      button.disabled = true;
      return button;
    });

    if (!rows.length) {
      const note = document.createElement("p");
      note.className = "quiet-note";
      note.textContent = "Open this app and describe what you want to do.";
      suggestions.replaceChildren(note);
      return;
    }

    suggestions.replaceChildren(...rows);
  }

  function renderCurrent() {
    const product = currentProduct();
    if (!product) {
      computer.dataset.state = "empty";
      selectedName.textContent = "No apps";
      windowStatus.textContent = "Empty";
      currentTitle.textContent = "No apps found";
      currentDesc.textContent = "The AI computer could not find any apps.";
      openLink.setAttribute("aria-disabled", "true");
      return;
    }

    computer.dataset.state = "ready";
    state.selectedId = product.id;
    selectedName.textContent = text(product.title, "AI App");
    windowTitle.textContent = "AI Computer";
    windowStatus.textContent = statusLabel(product.ui_status);
    currentTitle.textContent = "Applications";
    currentDesc.textContent = "Choose an app on the desktop, in this window, or from the Dock.";
    currentAvatar.textContent = initials(product);
    previewTitle.textContent = text(product.title, "AI App");
    previewDesc.textContent = text(product.desc, "Open this app and keep working.");
    metaLayout.textContent = layoutLabel(product.product_layout);
    metaStatus.textContent = statusLabel(product.ui_status);
    openLink.href = productUrl(product);
    openLink.removeAttribute("aria-disabled");
    renderSuggestions(product);
    renderDesktopIcons();
    renderAppGrid();
    renderDock();
  }

  function selectProduct(productId, options = {}) {
    state.selectedId = productId;
    if (options.openLibrary) openLibrary();
    renderCurrent();
  }

  function openLibrary() {
    libraryWindow.classList.add("is-open");
    libraryWindow.style.zIndex = String(++state.z);
  }

  function closeLibrary() {
    libraryWindow.classList.remove("is-open");
  }

  function openSelectedApp() {
    const product = currentProduct();
    if (!product) return;
    window.location.href = productUrl(product);
  }

  function tickClock() {
    const now = new Date();
    clock.textContent = now.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  }

  function installWindowEvents() {
    document.querySelectorAll("[data-open-library]").forEach((node) => {
      node.addEventListener("click", openLibrary);
    });
    document.querySelectorAll("[data-open-app]").forEach((node) => {
      node.addEventListener("click", openSelectedApp);
    });
    document.querySelectorAll("[data-close-window]").forEach((node) => {
      node.addEventListener("click", closeLibrary);
    });
    libraryWindow.addEventListener("mousedown", () => {
      libraryWindow.style.zIndex = String(++state.z);
    });
  }

  async function loadProducts() {
    try {
      const response = await fetch("/api/products", {
        credentials: "same-origin",
        headers: {Accept: "application/json"},
      });
      if (!response.ok) throw new Error(`Request failed: ${response.status}`);
      const payload = await response.json();
      state.products = normalizeProducts(payload);
      state.selectedId = state.products[0] ? state.products[0].id : "";
      renderCurrent();
    } catch (error) {
      computer.dataset.state = "error";
      windowStatus.textContent = "Error";
      currentTitle.textContent = "Could not load apps";
      currentDesc.textContent = text(error && error.message, "Please refresh and try again.");
    }
  }

  installWindowEvents();
  tickClock();
  setInterval(tickClock, 15000);
  loadProducts();
})();
