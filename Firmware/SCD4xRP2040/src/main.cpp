#include <Arduino.h>
#include <SensirionI2cScd4x.h>
#include <Wire.h>
#include <Adafruit_NeoPixel.h>
#include "Adafruit_TinyUSB.h"

// macro definitions
// make sure that we use the proper definition of NO_ERROR
#ifdef NO_ERROR
#undef NO_ERROR
#endif
#define NO_ERROR 0

// Pin definitions
#define PIN_SDA 26
#define PIN_SCL 27
#define PIN_NEOPIXEL 16

// Timing constants
#define MEASUREMENT_INTERVAL_MS 5000

// CO2 validation range (ppm)
#define CO2_MIN_VALID 400
#define CO2_MAX_VALID 5000

// LED colors
#define COLOR_GREEN strip.Color(0, 255, 0)   // Normal operation
#define COLOR_YELLOW strip.Color(255, 255, 0) // Warning
#define COLOR_RED strip.Color(255, 0, 0)     // Error

SensirionI2cScd4x sensor;
bool sensor_initialized = false;

static char errorMessage[64];
static int16_t scderror;

Adafruit_NeoPixel strip = Adafruit_NeoPixel(1, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);

uint8_t const desc_hid_report[] = {
  0x06, 0x00, 0xFF,  // Usage Page (Vendor Defined 0xFF00)
  0x09, 0x01,        // Usage (0x01)
  0xA1, 0x01,        // Collection (Application)
  0x09, 0x02,        //   Usage (0x02)
  0x15, 0x00,        //   Logical Minimum (0)
  0x26, 0xFF, 0x00,  //   Logical Maximum (255)
  0x75, 0x08,        //   Report Size (8)
  0x95, 0x40,        //   Report Count (64)
  0x81, 0x02,        //   Input (Data,Var,Abs)
  0xC0               // End Collection
};

typedef struct __attribute__((packed)) {
  uint16_t co2_ppm;
  int16_t  temperature_x100;
  uint16_t humidity_x100;
} hid_sensor_report_t;

hid_sensor_report_t report;

// USB HID object
Adafruit_USBD_HID usb_hid;

void setLED(uint32_t color) {
    strip.setPixelColor(0, color);
    strip.show();
}

void set_report_callback(uint8_t report_id, hid_report_type_t report_type, uint8_t const* in_data, uint16_t bufsize) {
  // Echo back received data
  uint8_t out_data[64];
  for(uint8_t i = 0; i < bufsize && i < 64; i++) {
    out_data[i] = in_data[i];
  }
  usb_hid.sendReport(0, out_data, sizeof(out_data));
}

void setup() {
    // Initialize NeoPixel LED
    strip.begin();
    strip.setBrightness(5);
    setLED(COLOR_YELLOW);

    // Initialize I2C (must be done before USB)
    Wire1.setSDA(PIN_SDA);
    Wire1.setSCL(PIN_SCL);
    Wire1.begin();

    // Initialize USB HID
    #if defined(ARDUINO_ARCH_MBED) && defined(ARDUINO_ARCH_RP2040)
    TinyUSB_Device_Init(0);
    #endif
    
    if (!TinyUSBDevice.isInitialized()) {
      TinyUSBDevice.begin(0);
    }

    usb_hid.setPollInterval(2);
    usb_hid.setReportDescriptor(desc_hid_report, sizeof(desc_hid_report));
    usb_hid.setStringDescriptor("SCD4x CO2 Sensor");
    usb_hid.setReportCallback(0, 0);
    usb_hid.begin();

    // Force re-enumeration if already mounted (reset scenario)
    if (TinyUSBDevice.mounted()) {
      TinyUSBDevice.detach();
      delay(250);
      TinyUSBDevice.attach();
    }

    // Wait for USB enumeration (with timeout)
    uint32_t usb_timeout = millis() + 5000;
    while(!TinyUSBDevice.mounted() && millis() < usb_timeout) {
        delay(10);
    }

    // Initialize SCD4x sensor
    sensor.begin(Wire1, SCD41_I2C_ADDR_62);
    delay(100);
    
    // Configure sensor - robust initialization sequence
    uint64_t serialNumber = 0;
    
    // Try to wake up sensor (may already be awake)
    sensor.wakeUp();
    delay(20);
    
    // Stop any ongoing measurements (critical for reset scenario)
    for (int i = 0; i < 3; i++) {
        sensor.stopPeriodicMeasurement();
        delay(500);  // Wait for sensor to stop
    }
    
    // Reinitialize sensor
    scderror = sensor.reinit();
    if (scderror != NO_ERROR) {
        setLED(COLOR_RED);
        sensor_initialized = false;
        return;
    }
    delay(20);
    
    // Verify sensor communication
    scderror = sensor.getSerialNumber(serialNumber);
    if (scderror != NO_ERROR) {
        setLED(COLOR_RED);
        sensor_initialized = false;
        return;
    }
    
    // Start periodic measurements
    scderror = sensor.startPeriodicMeasurement();
    if (scderror != NO_ERROR) {
        setLED(COLOR_RED);
        sensor_initialized = false;
        return;
    }

    sensor_initialized = true;
    setLED(COLOR_GREEN);
}

uint32_t last_measure_ms = 0;

void loop() {
  #ifdef TINYUSB_NEED_POLLING_TASK
  TinyUSBDevice.task();
  #endif

  // Check initialization status
  if (!sensor_initialized) {
    setLED(COLOR_RED);
    delay(1000);
    return;
  }

  // Check measurement interval
  if (millis() - last_measure_ms < MEASUREMENT_INTERVAL_MS) {
    return;
  }
  last_measure_ms = millis();

  // Check if data is ready
  bool dataReady = false;
  if (sensor.getDataReadyStatus(dataReady) != NO_ERROR || !dataReady) {
    return;
  }

  // Read measurement data
  uint16_t co2;
  float temp, hum;
  if (sensor.readMeasurement(co2, temp, hum) != NO_ERROR) {
    setLED(COLOR_RED);
    return;
  }

  // Validate CO2 reading
  if (co2 < CO2_MIN_VALID || co2 > CO2_MAX_VALID) {
    setLED(COLOR_YELLOW);
    return;
  }

  // Prepare and send HID report (64 bytes)
  uint8_t sensor_report[64] = {0};
  
  // CO2 (2 bytes, little-endian)
  sensor_report[0] = (co2 & 0xFF);
  sensor_report[1] = ((co2 >> 8) & 0xFF);
  
  // Temperature (2 bytes, little-endian, signed)
  int16_t temp_raw = (int16_t)(temp * 100);
  sensor_report[2] = (temp_raw & 0xFF);
  sensor_report[3] = ((temp_raw >> 8) & 0xFF);
  
  // Humidity (2 bytes, little-endian)
  uint16_t hum_raw = (uint16_t)(hum * 100);
  sensor_report[4] = (hum_raw & 0xFF);
  sensor_report[5] = ((hum_raw >> 8) & 0xFF);

  if (usb_hid.ready()) {
    usb_hid.sendReport(0, sensor_report, 64);
    setLED(COLOR_GREEN);
  }
}