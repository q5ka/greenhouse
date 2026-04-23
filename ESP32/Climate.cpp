#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoOTA.h>

// ---------- USER CONFIG ----------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

const char* MQTT_BROKER   = "192.168.1.100";
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT_ID = "esp32_climate_node";

// Topics
const char* TOPIC_T_Z1    = "greenhouse/climate/zone1/temperature";
const char* TOPIC_H_Z1    = "greenhouse/climate/zone1/humidity";
const char* TOPIC_T_Z2    = "greenhouse/climate/zone2/temperature";
const char* TOPIC_H_Z2    = "greenhouse/climate/zone2/humidity";
const char* TOPIC_T_OUT   = "greenhouse/climate/outside/temperature";
const char* TOPIC_H_OUT   = "greenhouse/climate/outside/humidity";
const char* TOPIC_LIGHT   = "greenhouse/climate/light";
const char* TOPIC_PIR     = "greenhouse/climate/presence";
const char* TOPIC_V1_STATE= "greenhouse/climate/vents/zone1/state";
const char* TOPIC_V2_STATE= "greenhouse/climate/vents/zone2/state";

const char* TOPIC_V1_CMD  = "greenhouse/climate/vents/zone1/cmd";
const char* TOPIC_V2_CMD  = "greenhouse/climate/vents/zone2/cmd";

// ---------- PINS ----------
#define DHTTYPE DHT22
const int PIN_DHT_Z1   = 4;
const int PIN_DHT_Z2   = 16;
const int PIN_DHT_OUT  = 17;
const int PIN_LDR      = 34;
const int PIN_PIR      = 26;
const int PIN_V1_A     = 25;
const int PIN_V1_B     = 33;
const int PIN_V2_A     = 32;
const int PIN_V2_B     = 14;

// ---------- GLOBALS ----------
WiFiClient espClient;
PubSubClient mqttClient(espClient);

DHT dht_z1(PIN_DHT_Z1, DHTTYPE);
DHT dht_z2(PIN_DHT_Z2, DHTTYPE);
DHT dht_out(PIN_DHT_OUT, DHTTYPE);

unsigned long lastSensorPublish = 0;
const unsigned long SENSOR_INTERVAL_MS = 10000;

enum VentState { VENT_UNKNOWN, VENT_OPENING, VENT_CLOSING, VENT_STOPPED };
VentState vent1State = VENT_UNKNOWN;
VentState vent2State = VENT_UNKNOWN;

// ---------- RELAY CONTROL ----------
void stopVent1() {
  digitalWrite(PIN_V1_A, LOW);
  digitalWrite(PIN_V1_B, LOW);
  vent1State = VENT_STOPPED;
  mqttClient.publish(TOPIC_V1_STATE, "STOPPED", true);
}

void openVent1() {
  digitalWrite(PIN_V1_B, LOW);
  digitalWrite(PIN_V1_A, HIGH);
  vent1State = VENT_OPENING;
  mqttClient.publish(TOPIC_V1_STATE, "OPENING", true);
}

void closeVent1() {
  digitalWrite(PIN_V1_A, LOW);
  digitalWrite(PIN_V1_B, HIGH);
  vent1State = VENT_CLOSING;
  mqttClient.publish(TOPIC_V1_STATE, "CLOSING", true);
}

void stopVent2() {
  digitalWrite(PIN_V2_A, LOW);
  digitalWrite(PIN_V2_B, LOW);
  vent2State = VENT_STOPPED;
  mqttClient.publish(TOPIC_V2_STATE, "STOPPED", true);
}

void openVent2() {
  digitalWrite(PIN_V2_B, LOW);
  digitalWrite(PIN_V2_A, HIGH);
  vent2State = VENT_OPENING;
  mqttClient.publish(TOPIC_V2_STATE, "OPENING", true);
}

void closeVent2() {
  digitalWrite(PIN_V2_A, LOW);
  digitalWrite(PIN_V2_B, HIGH);
  vent2State = VENT_CLOSING;
  mqttClient.publish(TOPIC_V2_STATE, "CLOSING", true);
}

// ---------- MQTT CALLBACK ----------
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String cmd;
  for (unsigned int i = 0; i < length; i++) cmd += (char)payload[i];
  cmd.trim();
  cmd.toUpperCase();

  if (String(topic) == TOPIC_V1_CMD) {
    if (cmd == "OPEN") openVent1();
    else if (cmd == "CLOSE") closeVent1();
    else if (cmd == "STOP") stopVent1();
  } else if (String(topic) == TOPIC_V2_CMD) {
    if (cmd == "OPEN") openVent2();
    else if (cmd == "CLOSE") closeVent2();
    else if (cmd == "STOP") stopVent2();
  }
}

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
      mqttClient.subscribe(TOPIC_V1_CMD);
      mqttClient.subscribe(TOPIC_V2_CMD);
    } else {
      delay(2000);
    }
  }
}

// ---------- PUBLISH HELPERS ----------
void publishFloat(const char* topic, float value) {
  char buf[16];
  dtostrf(value, 0, 2, buf);
  mqttClient.publish(topic, buf, true);
}

void publishInt(const char* topic, int value) {
  char buf[16];
  snprintf(buf, sizeof(buf), "%d", value);
  mqttClient.publish(topic, buf, true);
}

void readAndPublishSensors() {
  float t_z1 = dht_z1.readTemperature(true); // true = Fahrenheit
  float h_z1 = dht_z1.readHumidity();
  float t_z2 = dht_z2.readTemperature(true);
  float h_z2 = dht_z2.readHumidity();
  float t_out = dht_out.readTemperature(true);
  float h_out = dht_out.readHumidity();

  if (!isnan(t_z1)) publishFloat(TOPIC_T_Z1, t_z1);
  if (!isnan(h_z1)) publishFloat(TOPIC_H_Z1, h_z1);
  if (!isnan(t_z2)) publishFloat(TOPIC_T_Z2, t_z2);
  if (!isnan(h_z2)) publishFloat(TOPIC_H_Z2, h_z2);
  if (!isnan(t_out)) publishFloat(TOPIC_T_OUT, t_out);
  if (!isnan(h_out)) publishFloat(TOPIC_H_OUT, h_out);

  int ldrRaw = analogRead(PIN_LDR);
  publishInt(TOPIC_LIGHT, ldrRaw);

  int pirState = digitalRead(PIN_PIR);
  publishInt(TOPIC_PIR, pirState);
}

// ---------- SETUP / LOOP ----------
void setup() {
  pinMode(PIN_V1_A, OUTPUT);
  pinMode(PIN_V1_B, OUTPUT);
  pinMode(PIN_V2_A, OUTPUT);
  pinMode(PIN_V2_B, OUTPUT);
  stopVent1();
  stopVent2();

  pinMode(PIN_PIR, INPUT);
  dht_z1.begin();
  dht_z2.begin();
  dht_out.begin();

  connectWiFi();

  ArduinoOTA.setHostname("esp32_climate");
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
}
