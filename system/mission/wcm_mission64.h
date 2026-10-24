/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#ifndef WCM_MISSION64_H
#define WCM_MISSION64_H
/* Fixed-layout factory-provisioned mission; no radio/optical receive path.
 * Mission-64 v1: big-endian bits [version:4 task:4 sensor:4 threshold:6
 *   sample_period:6 report_period:6 max_reports:6 seed:12 flags:8 crc8:8].
 * CRC-8/ATM poly=0x07 init=0 xorout=0, first seven bytes only.
 * CRC detects incidental corruption; task provenance is a provisioning requirement.
 */
#include <stdint.h>
#include <stdbool.h>
#define WCM_MISSION_BYTES 8u
#define WCM_MISSION_VERSION 1u
#define WCM_TASK_THRESHOLD_REPORT 1u
#define WCM_TASK_PERIODIC_REPORT 2u
#define WCM_MISSION_SENSOR_SCALAR 1u

typedef struct {
  uint8_t version;
  uint8_t task;
  uint8_t sensor;
  uint8_t threshold;
  uint8_t sample_period;
  uint8_t report_period;
  uint8_t max_reports;
  uint16_t seed;
  uint8_t flags;
} wcm_mission_t;
uint8_t wcm_mission_crc8(const uint8_t *bytes, unsigned count);
bool wcm_mission_decode(const uint8_t data[WCM_MISSION_BYTES], wcm_mission_t *mission);
bool wcm_mission_due(const wcm_mission_t *mission, uint16_t sensor_value,
                     uint32_t samples_taken, uint64_t elapsed_us,
                     uint64_t last_report_us, uint8_t reports_done);
#endif
