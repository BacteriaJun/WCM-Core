/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_mission64.h"
#include <stddef.h>
uint8_t wcm_mission_crc8(const uint8_t *b, unsigned n) {
  uint8_t c=0;
  if(!b) return 0;
  for(unsigned i=0;i<n;i++) {
    c^=b[i];
    for(unsigned j=0;j<8;j++) c=(uint8_t)((c&0x80u)?((unsigned)c<<1u)^0x07u:((unsigned)c<<1u));
  }
  return c;
}
static uint16_t read_bits(uint64_t *payload, unsigned width) {
  uint16_t value=(uint16_t)(*payload & ((1ull<<width)-1ull));
  *payload >>= width;
  return value;
}
bool wcm_mission_decode(const uint8_t data[WCM_MISSION_BYTES],wcm_mission_t *out) {
  if(!data||!out||wcm_mission_crc8(data,7u)!=data[7]) return false;
  uint64_t b=0;
  for(unsigned i=0;i<7u;i++) b=(b<<8)|data[i];
  wcm_mission_t m={0};
  m.flags=(uint8_t)read_bits(&b,8);
  m.seed=read_bits(&b,12);
  m.max_reports=(uint8_t)read_bits(&b,6);
  m.report_period=(uint8_t)read_bits(&b,6);
  m.sample_period=(uint8_t)read_bits(&b,6);
  m.threshold=(uint8_t)read_bits(&b,6);
  m.sensor=(uint8_t)read_bits(&b,4);
  m.task=(uint8_t)read_bits(&b,4);
  m.version=(uint8_t)read_bits(&b,4);
  if(m.version!=WCM_MISSION_VERSION ||
     (m.task!=WCM_TASK_THRESHOLD_REPORT && m.task!=WCM_TASK_PERIODIC_REPORT) ||
     m.sensor!=WCM_MISSION_SENSOR_SCALAR ||
     (m.task==WCM_TASK_PERIODIC_REPORT && m.threshold!=0u) ||
     (m.task==WCM_TASK_THRESHOLD_REPORT && m.threshold==0u) ||
     m.sample_period==0u || m.report_period==0u ||m.max_reports==0u||m.flags!=0u) return false;
  *out=m;
  return true;
}
bool wcm_mission_due(const wcm_mission_t *m, uint16_t sensor_value,
                     uint32_t samples_taken,uint64_t elapsed_us,
                     uint64_t last_report_us,uint8_t reports_done) {
  if(!m || reports_done>=m->max_reports || samples_taken==0u) return false;
  if(m->task==WCM_TASK_THRESHOLD_REPORT && sensor_value<10u*(uint16_t)m->threshold) return false;
  /* All timing is relative to local startup; no station-origin command or ACK.
   * Use a preprovisioned offset (seed) only for FIRST report. Both later
   * spacing and the initial stagger are bounded, deterministic schedules.
   */
  if(reports_done==0u) return elapsed_us >= (uint64_t)(m->seed%16u)*1000u;
  if(elapsed_us<last_report_us) return false;
  return elapsed_us-last_report_us >= (uint64_t)m->report_period*10000u;
}
