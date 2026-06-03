const UI = {

  elements: {},

  init() {
    this.elements = {
      background: document.getElementById("background"),
      imageOverlay: document.getElementById("image-overlay"),
      narration: document.getElementById("narration"),
      dialogue: document.getElementById("dialogue"),
      options: document.getElementById("options"),
      input: document.getElementById("player-input"),
      sendBtn: document.getElementById("send-btn"),
      sanityBar: document.getElementById("sanity-bar"),
      sanityVal: document.getElementById("sanity-val"),
      healthBar: document.getElementById("health-bar"),
      healthVal: document.getElementById("health-val"),
      loadingOverlay: document.getElementById("loading-overlay"),
      imageLoadingDot: document.getElementById("image-loading-dot"),
    };

    this.elements.sendBtn.addEventListener("click", () => this.handleInput());
    this.elements.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.handleInput();
      }
    });
  },

  handleInput() {
    const val = this.elements.input.value.trim();
    if (!val || Game.state.isProcessing) return;
    this.elements.input.value = "";
    this.clearOptions();
    Game.playerAction(val);
  },

  setLoading(on) {
    this.elements.loadingOverlay.style.opacity = on ? "1" : "0";
    this.elements.loadingOverlay.style.pointerEvents = on ? "all" : "none";
    this.elements.input.disabled = on;
    this.elements.sendBtn.disabled = on;
  },

  setImageLoading(on) {
    this.elements.imageLoadingDot.style.display = on ? "block" : "none";
  },

  setBackground(url) {
    const bg = this.elements.background;
    // 淡入新背景
    const next = document.createElement("div");
    next.className = "bg-layer";
    next.style.backgroundImage = `url(${url})`;
    next.style.opacity = "0";
    bg.appendChild(next);
    requestAnimationFrame(() => {
      next.style.transition = "opacity 1.5s ease";
      next.style.opacity = "1";
    });
    // 移除旧背景层
    setTimeout(() => {
      const old = bg.querySelector(".bg-layer:not(:last-child)");
      if (old) old.remove();
    }, 2000);
  },

  renderNarration(text) {
    this.elements.narration.innerHTML = "";
    this.typewrite(this.elements.narration, text, 18);
  },

  renderDialogue(lines) {
    const el = this.elements.dialogue;
    el.innerHTML = "";
    if (!lines.length) return;

    let delay = 0;
    lines.forEach((line, i) => {
      const row = document.createElement("div");
      row.className = "dialogue-line";
      row.style.opacity = "0";
      row.style.transform = "translateY(6px)";

      const speaker = document.createElement("span");
      speaker.className = "speaker";
      speaker.textContent = line.speaker + "：";

      const content = document.createElement("span");
      content.className = "speech";
      content.textContent = line.text;

      row.appendChild(speaker);
      row.appendChild(content);
      el.appendChild(row);

      setTimeout(() => {
        row.style.transition = "opacity 0.4s ease, transform 0.4s ease";
        row.style.opacity = "1";
        row.style.transform = "translateY(0)";
      }, delay);
      delay += 400 + line.text.length * 10;
    });
  },

  renderOptions(options) {
    const el = this.elements.options;
    el.innerHTML = "";
    options.forEach((opt, i) => {
      const btn = document.createElement("button");
      btn.className = "option-btn";
      btn.textContent = opt;
      btn.style.animationDelay = `${i * 0.12}s`;
      btn.addEventListener("click", () => {
        this.clearOptions();
        Game.playerAction(opt);
      });
      el.appendChild(btn);
    });
  },

  clearOptions() {
    this.elements.options.innerHTML = "";
  },

  updateStats(sanity, health) {
    this.elements.sanityVal.textContent = sanity;
    this.elements.sanityBar.style.width = sanity + "%";
    this.elements.sanityBar.style.backgroundColor =
      sanity > 50 ? "#7ec8a0" : sanity > 25 ? "#e0a040" : "#c04040";

    this.elements.healthVal.textContent = health;
    this.elements.healthBar.style.width = health + "%";
  },

  renderGameOver(reason) {
    this.clearOptions();
    const el = document.getElementById("game-over");
    el.querySelector(".game-over-reason").textContent = reason;
    el.style.display = "flex";
  },

  renderError(msg) {
    const el = this.elements.narration;
    el.innerHTML = `<span style="color:#ff6b6b;">错误：${msg}<br>请检查 API Key 是否正确填写。</span>`;
  },

  typewrite(el, text, speed = 20) {
    let i = 0;
    el.textContent = "";
    const timer = setInterval(() => {
      el.textContent += text[i];
      i++;
      if (i >= text.length) clearInterval(timer);
    }, speed);
  }

};
