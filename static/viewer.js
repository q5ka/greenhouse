/* ============================================================
   GLOBAL STATE
   ============================================================ */
let viewerState = {
  gh: null,
  activeTab: "timelapse",
  timelapseDates: [],
  timelapseFrames: [],
  currentFrameIndex: 0,
  slideshowInterval: null,
  zoom: 1,
  rotation: 0,
  panX: 0,
  panY: 0,
  isPanning: false,
  lastPanX: 0,
  lastPanY: 0
};

/* ============================================================
   OPEN / CLOSE MODAL
   ============================================================ */
function openMediaViewer(gh, tab = "timelapse") {
  viewerState.gh = gh;
  viewerState.activeTab = tab;

  document.getElementById("media-viewer-overlay").style.display = "flex";

  setActiveTab(tab);
}

function closeMediaViewer() {
  document.getElementById("media-viewer-overlay").style.display = "none";
  stopSlideshow();
}

/* Close on ESC */
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeMediaViewer();
});

/* Close on click outside */
document.addEventListener("click", (e) => {
  const overlay = document.getElementById("media-viewer-overlay");
  const modal = document.getElementById("media-viewer-modal");
  if (e.target === overlay) closeMediaViewer();
});

/* ============================================================
   TAB SWITCHING
   ============================================================ */
function setActiveTab(tab) {
  viewerState.activeTab = tab;

  document.querySelectorAll(".media-tab").forEach(t => t.classList.remove("active"));
  document.getElementById(`tab-${tab}`).classList.add("active");

  if (tab === "timelapse") loadTimelapseDates();
  if (tab === "motion") loadMotionClips();
}

/* ============================================================
   TIME-LAPSE
   ============================================================ */
async function loadTimelapseDates() {
  const today = new Date().toISOString().slice(0, 10);
  await loadTimelapseForDate(today);
}

async function loadTimelapseForDate(date) {
  const gh = viewerState.gh;
  const res = await fetch(`/api/camera/timelapse/list?gh=${gh}&date=${date}`);
  const data = await res.json();

  viewerState.timelapseFrames = data.files || [];
  viewerState.currentFrameIndex = 0;

  renderTimelapseGrid(date);
}

function renderTimelapseGrid(date) {
  const container = document.getElementById("media-viewer-content");
  container.innerHTML = `
    <div style="margin-bottom:12px;">
      <input type="date" id="tl-date" style="background:#0f172a;color:#e2e8f0;border:1px solid #1e293b;padding:6px;border-radius:6px;">
    </div>
    <div id="timelapse-grid"></div>
    <div style="margin-top:12px;display:flex;gap:12px;">
      <button class="lightbox-btn" onclick="prevTimelapseDay()">Prev Day</button>
      <button class="lightbox-btn" onclick="startSlideshow()">Play Slideshow</button>
      <button class="lightbox-btn" onclick="nextTimelapseDay()">Next Day</button>
    </div>
  `;

  document.getElementById("tl-date").value = date;
  document.getElementById("tl-date").addEventListener("change", (e) => {
    loadTimelapseForDate(e.target.value);
  });

  const grid = document.getElementById("timelapse-grid");

  viewerState.timelapseFrames.forEach((path, idx) => {
    const img = document.createElement("img");
    img.className = "timelapse-thumb";
    img.src = `/api/camera/timelapse/frame?gh=${viewerState.gh}&path=${path}`;
    img.onclick = () => openLightbox(idx);
    grid.appendChild(img);
  });
}

function prevTimelapseDay() {
  const d = new Date(document.getElementById("tl-date").value);
  d.setDate(d.getDate() - 1);
  loadTimelapseForDate(d.toISOString().slice(0, 10));
}

function nextTimelapseDay() {
  const d = new Date(document.getElementById("tl-date").value);
  d.setDate(d.getDate() + 1);
  loadTimelapseForDate(d.toISOString().slice(0, 10));
}

/* ============================================================
   SLIDESHOW
   ============================================================ */
function startSlideshow() {
  stopSlideshow();
  viewerState.slideshowInterval = setInterval(() => {
    nextFrame(true);
  }, 200);
}

function stopSlideshow() {
  if (viewerState.slideshowInterval) {
    clearInterval(viewerState.slideshowInterval);
    viewerState.slideshowInterval = null;
  }
}

/* ============================================================
   LIGHTBOX
   ============================================================ */
function openLightbox(index) {
  viewerState.currentFrameIndex = index;
  viewerState.zoom = 1;
  viewerState.rotation = 0;
  viewerState.panX = 0;
  viewerState.panY = 0;

  const overlay = document.getElementById("lightbox-overlay");
  overlay.style.display = "flex";

  renderLightboxImage();
}

function closeLightbox() {
  document.getElementById("lightbox-overlay").style.display = "none";
  stopSlideshow();
}

function renderLightboxImage(direction = null) {
  const img = document.getElementById("lightbox-img");
  const path = viewerState.timelapseFrames[viewerState.currentFrameIndex];

  img.src = `/api/camera/timelapse/frame?gh=${viewerState.gh}&path=${path}`;

  img.style.transform = `
    translate(${viewerState.panX}px, ${viewerState.panY}px)
    scale(${viewerState.zoom})
    rotate(${viewerState.rotation}deg)
  `;

  if (direction === "left") img.classList.add("slide-left");
  if (direction === "right") img.classList.add("slide-right");

  setTimeout(() => {
    img.classList.remove("slide-left", "slide-right");
  }, 300);
}

function nextFrame(slideshow = false) {
  viewerState.currentFrameIndex =
    (viewerState.currentFrameIndex + 1) % viewerState.timelapseFrames.length;
  renderLightboxImage("left");
}

function prevFrame() {
  viewerState.currentFrameIndex =
    (viewerState.currentFrameIndex - 1 + viewerState.timelapseFrames.length) %
    viewerState.timelapseFrames.length;
  renderLightboxImage("right");
}

/* Keyboard navigation */
document.addEventListener("keydown", (e) => {
  const overlay = document.getElementById("lightbox-overlay");
  if (overlay.style.display !== "flex") return;

  if (e.key === "ArrowRight") nextFrame();
  if (e.key === "ArrowLeft") prevFrame();
  if (e.key === "+") zoomIn();
  if (e.key === "-") zoomOut();
  if (e.key === "r") rotateRight();
  if (e.key === " ") {
    if (viewerState.slideshowInterval) stopSlideshow();
    else startSlideshow();
  }
});

/* Zoom */
function zoomIn() {
  viewerState.zoom = Math.min(viewerState.zoom + 0.2, 5);
  renderLightboxImage();
}

function zoomOut() {
  viewerState.zoom = Math.max(viewerState.zoom - 0.2, 0.2);
  renderLightboxImage();
}

/* Rotate */
function rotateLeft() {
  viewerState.rotation -= 90;
  renderLightboxImage();
}

function rotateRight() {
  viewerState.rotation += 90;
  renderLightboxImage();
}

/* Download */
function downloadFrame() {
  const path = viewerState.timelapseFrames[viewerState.currentFrameIndex];
  const a = document.createElement("a");
  a.href = `/api/camera/timelapse/frame?gh=${viewerState.gh}&path=${path}`;
  a.download = path.split("/").pop();
  a.click();
}

/* ============================================================
   MOTION CLIPS
   ============================================================ */
async function loadMotionClips() {
  const gh = viewerState.gh;
  const res = await fetch(`/api/camera/motion/list?gh=${gh}`);
  const data = await res.json();

  const container = document.getElementById("media-viewer-content");
  container.innerHTML = `
    <div id="motion-list"></div>
    <div id="motion-video-container"></div>
  `;

  const list = document.getElementById("motion-list");

  data.files.forEach((path) => {
    const item = document.createElement("div");
    item.className = "motion-item";
    item.innerHTML = `<span>${path}</span>`;
    item.onclick = () => playMotionClip(path);
    list.appendChild(item);
  });
}

function playMotionClip(path) {
  const container = document.getElementById("motion-video-container");
  container.innerHTML = `
    <video id="motion-video" controls autoplay>
      <source src="/api/camera/motion/video?gh=${viewerState.gh}&path=${path}" type="video/mp4">
    </video>
    <div style="margin-top:8px;display:flex;gap:12px;">
      <button class="lightbox-btn" onclick="rotateVideo()">Rotate</button>
      <button class="lightbox-btn" onclick="downloadMotion('${path}')">Download</button>
    </div>
  `;
}

function rotateVideo() {
  const video = document.getElementById("motion-video");
  const current = video.style.transform || "rotate(0deg)";
  const angle = parseInt(current.replace("rotate(", "").replace("deg)", "")) + 90;
  video.style.transform = `rotate(${angle}deg)`;
}

function downloadMotion(path) {
  const a = document.createElement("a");
  a.href = `/api/camera/motion/video?gh=${viewerState.gh}&path=${path}`;
  a.download = path.split("/").pop();
  a.click();
}
