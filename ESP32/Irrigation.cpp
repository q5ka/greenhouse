#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoOTA.h>

// ---------- USER CONFIG ----------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

const char* MQTT_BROKER   = "192.168.1.100";
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT_ID = "esp32_irrigation_node";

// Topics
String TOPIC_MOISTURE[8] = {
  "greenhouse/irrigation/zone1/moisture",
  "greenhouse/irrigation/zone2/moisture",
  "greenhouse/irrigation/zone3/moisture",
  "greenhouse/irrigation/zone4/moisture",
  "greenhouse/irrigation/zone5/moisture",
  "greenhouse/irrigation/zone6/moisture",
  "greenhouse/irrigation/zone7/moisture",
  "greenhouse/irrigation/zone8/moisture"
};

String TOPIC_VALVE_STATE[8] = {
  "greenhouse/irrigation/zone1/valve_state",
  "greenhouse/irrigation/zone2/valve_state",
  "greenhouse/irrigation/zone3/valve_state",
  "greenhouse/irrigation/zone4/valve_state",
  "greenhouse/irrigation/zone5/valve_state",
  "greenhouse/irrigation/zone6/valve_state",
  "greenhouse/irrigation/zone7/valve_state",
  "greenhouse/irrigation/zone8/valve_state"
};

String TOPIC_CMD[8] = {
  "greenhouse/irrigation/zone1/cmd",
  "greenhouse/irrigation/zone2/cmd",
  "greenhouse/irrigation/zone3/cmd",
  "greenhouse/irrigation/zone4/cmd",
  "greenhouse/irrigation/zone5/cmd",
  "greenhouse/irrigation/zone6/cmd",
  "greenhouse/irrigation/zone7/cmd",
  "greenhouse/irrigation/zone8/cmd"
};

// ---------- PINS ----------
int SOIL_PINS[8]  = {36, 39, 34, 35, 32, 33, 25, 26};
int VALVE_PINS[8] = {5, 18, 19, 21, 22, 23, 2, 15};

// ---------- GLOBALS ----------
WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long lastSensorPublish = 0;
const unsigned long SENSOR_INTERVAL_MS = 10000;

bool valveActive[8] = {false};
unsigned long valveEndTime[8] = {0};
bool anyValveRunning = false;

// ---------- WIFI + MQTT ----------
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
}

void connectMQTT() {
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  while (!mqttClient.connected()) {
    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      for (int i = 0; i < 8; i++) {
        mqttClient.subscribe(TOPIC_CMD[i].c_str());
      }
    } else {
      delay(2000);
    }
  }
}

// ---------- HELPERS ----------
void publishInt(const char* topic, int value) {
  char buf[16];
  snprintf(buf, sizeof(buf), "%d", value);
  mqttClient.publish(topic, buf, true);
}

void publishState(int zone, const char* state) {
  mqttClient.publish(TOPIC_VALVE_STATE[zone].c_str(), state, true);
}

void stopValve(int zone) {
  digitalWrite(VALVE_PINS[zone], LOW);
  valveActive[zone] = false;
  publishState(zone, "OFF");
  anyValveRunning = false;
}

void startValve(int zone, int durationSec) {
  if (anyValveRunning) return;
  digitalWrite(VALVE_PINS[zone], HIGH);
  valveActive[zone] = true;
  valveEndTime[zone] = millis() + (durationSec * 1000UL);
  anyValveRunning = true;
  publishState(zone, "ON");
}

// ---------- MQTT CALLBACK ----------
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String cmd;
  for (unsigned int i = 0; i < length; i++) cmd += (char)payload[i];
  cmd.trim();

  int zone = -1;
  for (int i = 0; i < 8; i++) {
    if (String(topic) == TOPIC_CMD[i]) {
      zone = i;
      break;
    }
  }
  if (zone < 0) return;

  if (cmd.startsWith("WATER_ONCE:")) {
    int duration = cmd.substring(12).toInt();
    startValve(zone, duration);
  } else if (cmd == "ON") {
    startValve(zone, 3600);
  } else if (cmd == "OFF") {
    stopValve(zone);
  } else if (cmd == "AUTO") {
    // no local logic
  }
}

// ---------- SENSORS ----------
void readAndPublishSensors() {
  for (int i = 0; i < 8; i++) {
    int raw = analogRead(SOIL_PINS[i]);
    publishInt(TOPIC_MOISTURE[i].c_str(), raw);
  }
}

// ---------- SETUP / LOOP ----------
void setup() {
  for (int i = 0; i < 8; i++) {
    pinMode(VALVE_PINS[i], OUTPUT);
    digitalWrite(VALVE_PINS[i], LOW);
    pinMode(SOIL_PINS[i], INPUT);
  }

  connectWiFi();

  ArduinoOTA.setHostname("esp32_irrigation");
  ArduinoOTA.begin();

  connectMQTT();
}

void loop() {
  ArduinoOTA.handle();

  if (!mqttClient.connected()) {
    connectMQTT();
  }
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastSensorPublish >= SENSOR_INTERVAL_MS) {
    lastSensorPublish = now;
    readAndPublishSensors();
  }

  for (int i = 0; i < 8; i++) {
    if (valveActive[i] && now >= valveEndTime[i]) {
      stopValve(i);
    }
  }
}
