let tempChart, moistureChart;
let vent1Chart, vent2Chart;
let moistureCharts = [];
let currentConfig = null;

// ---------------- HEALTH ----------------

async function updateHealth() {
  const res = await fetch("/api/health");
  const h = await res.json();

  const icon = ok => ok ? "🟢" : "🔴";

  document.getElementById("health").innerHTML = `
    <h2>System Health</h2>

    <div class="grid-row">
      <div>MQTT Connection</div>
      <div class="icon-cell">${icon(h.overall.mqtt_ok)}</div>
    </div>

    <div class="grid-row">
      <div>Sensor Freshness</div>
      <div class="icon-cell">${icon(h.overall.sensors_fresh)}</div>
    </div>

    <div class="grid-row">
      <div>Vent System</div>
      <div class="icon-cell">${icon(h.overall.vents_ok)}</div>
    </div>

    <div class="grid-row">
      <div>Irrigation System</div>
      <div class="icon-cell">${icon(h.overall.irrigation_ok)}</div>
    </div>

    <div class="grid-row">
      <div>Database Queue</div>
      <div class="icon-cell">${icon(h.overall.db_ok)}</div>
    </div>

    <details>
      <summary>Details</summary>
      <pre>${JSON.stringify(h, null, 2)}</pre>
    </details>
  `;
}

// ---------------- STATE UPDATE ----------------

async function updateState() {
  const res = await fetch("/api/state");
  const s = await res.json();
  currentConfig = s.config;

  const icons = s.icons;

  // Climate
  document.getElementById("climate").innerHTML = `
    <h2>Climate</h2>
    <div class="grid-row"><div>Zone 1 Temp: ${s.t_z1 ?? "-"} °F</div><div class="icon-cell">${icons.temp.zone1}</div></div>
    <div class="grid-row"><div>Zone 1 Humidity: ${s.h_z1 ?? "-"} %</div><div class="icon-cell">${icons.humidity.zone1}</div></div>
    <div class="grid-row"><div>Zone 2 Temp: ${s.t_z2 ?? "-"} °F</div><div class="icon-cell">${icons.temp.zone2}</div></div>
    <div class="grid-row"><div>Zone 2 Humidity: ${s.h_z2 ?? "-"} %</div><div class="icon-cell">${icons.humidity.zone2}</div></div>
    <div class="grid-row"><div>Outside Temp: ${s.t_out ?? "-"} °F</div><div class="icon-cell">${icons.temp.outside}</div></div>
    <div class="grid-row"><div>Outside Humidity: ${s.h_out ?? "-"} %</div><div class="icon-cell">${icons.humidity.outside}</div></div>
    <div class="grid-row"><div>Presence: ${s.presence}</div><div class="icon-cell">${icons.presence}</div></div>
  `;

  // Irrigation
  let irr = "<h2>Irrigation</h2>";
  for (let i = 0; i < 8; i++) {
    irr += `
      <div class="grid-row">
        <div>Zone ${i+1} Moisture: ${s.moisture[i] ?? "-"}</div>
        <div class="icon-cell">${icons.moisture[i]}</div>
      </div>
      <div>Valve: ${s.valve_state[i]}</div>
    `;
  }
  document.getElementById("irrigation").innerHTML = irr;

  // Lighting
  document.getElementById("lighting").innerHTML = `
    <h2>Lighting</h2>
    State: ${s.lights_state}<br>
  `;

  // Irrigation controls
  let ctrl = "";
  for (let i = 0; i < 8; i++) {
    const auto = currentConfig.irrigation.auto[i];
    const btnClass = auto ? "btn auto-on" : "btn auto-off";

    ctrl += `
      <div class="control-row">
        Zone ${i+1}:
        <button class="btn" onclick="irrigationWaterOnce(${i+1})">Water Once</button>
        <button class="btn" onclick="irrigationCmd(${i+1}, 'ON')">ON</button>
        <button class="btn" onclick="irrigationCmd(${i+1}, 'OFF')">OFF</button>
        <button id="irrigationAuto${i+1}" class="${btnClass}" onclick="toggleIrrigationAuto(${i+1})">AUTO</button>
      </div>
    `;
  }
  document.getElementById("irrigationControls").innerHTML = ctrl;

  updateVentAutoButtons();
  updateCameraControls();
  updateNotificationControls();
}

// ---------------- CAMERA ----------------

function updateCameraControls() {
  const cam = currentConfig.camera || { enabled: false, mode: "live" };

  document.getElementById("cameraControls").innerHTML = `
    <div class="grid-row">
      <div>Camera Enabled</div>
      <div><button class="btn ${cam.enabled ? "auto-on" : "auto-off"}" onclick="toggleCamera()">${cam.enabled ? "ON" : "OFF"}</button></div>
    </div>

    <div class="grid-row">
      <div>Mode</div>
      <div>
        <select id="cameraMode" onchange="setCameraMode()">
          <option value="live" ${cam.mode === "live" ? "selected" : ""}>Live</option>
          <option value="motion" ${cam.mode === "motion" ? "selected" : ""}>Motion</option>
          <option value="timelapse" ${cam.mode === "timelapse" ? "selected" : ""}>Time-lapse</option>
        </select>
      </div>
    </div>
  `;
}

async function toggleCamera() {
  currentConfig.camera.enabled = !currentConfig.camera.enabled;
  await saveConfig();
}

async function setCameraMode() {
  currentConfig.camera.mode = document.getElementById("cameraMode").value;
  await saveConfig();
}

// ---------------- NOTIFICATIONS ----------------

function updateNotificationControls() {
  const n = currentConfig.notifications || {
    email: { enabled: false, to: "" },
    sms: { enabled: false, to: "" }
  };

  document.getElementById("notificationControls").innerHTML = `
    <div class="grid-row">
      <div>Email Alerts</div>
      <div><button class="btn ${n.email.enabled ? "auto-on" : "auto-off"}" onclick="toggleEmailAlerts()">${n.email.enabled ? "ON" : "OFF"}</button></div>
    </div>

    <div class="grid-row">
      <div>Email To</div>
      <div><input id="emailTo" value="${n.email.to}" onchange="setEmailTo()"></div>
    </div>

    <div class="grid-row">
      <div>SMS Alerts</div>
      <div><button class="btn ${n.sms.enabled ? "auto-on" : "auto-off"}" onclick="toggleSmsAlerts()">${n.sms.enabled ? "ON" : "OFF"}</button></div>
    </div>

    <div class="grid-row">
      <div>SMS To</div>
      <div><input id="smsTo" value="${n.sms.to}" onchange="setSmsTo()"></div>
    </div>
  `;
}

async function toggleEmailAlerts() {
  currentConfig.notifications.email.enabled = !currentConfig.notifications.email.enabled;
  await saveConfig();
}

async function setEmailTo() {
  currentConfig.notifications.email.to = document.getElementById("emailTo").value;
  await saveConfig();
}

async function toggleSmsAlerts() {
  currentConfig.notifications.sms.enabled = !currentConfig.notifications.sms.enabled;
  await saveConfig();
}

async function setSmsTo() {
  currentConfig.notifications.sms.to = document.getElementById("smsTo").value;
  await saveConfig();
}

// ---------------- INIT ----------------

setInterval(updateState, 1000);
setInterval(updateHealth, 5000);
setInterval(updateCharts, 30000);

window.addEventListener("load", () => {
  updateState();
  updateHealth();
  updateCharts();
  loadConfig();
});
