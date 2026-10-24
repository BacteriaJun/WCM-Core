/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
/* Native host reference endpoint using an offline 8-byte Mission-64 image.
 * Sensor, power and reflected-symbol callbacks model the endpoint environment.
 * argv[1] selects the stored task image for a bounded boot run.
 */
#include "wcm_cell_r4.h"
#include "wcm_optical.h"
#include "wcm_power_model.h"
#include "wcm_mission64.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#define REQUIRE(cond, label) do {if(!(cond)) {fprintf(stderr,"WCM virtual error: %s (line %d)\n",label,__LINE__);return 2;}}while(0)

typedef struct {
  uint64_t now_us,energy_at_us;
  uint32_t energy_sequence,energy_actual_nj;
  uint32_t symbols_emitted,frame_started,frame_completed,blocks_count;
  uint16_t sensor_value;
  uint8_t reflect_state;
  uint8_t current_local_action;
  bool power_bad,mission_valid;
} fixture_t;
static bool clock_read(void *u,uint64_t *out) {*out=((fixture_t*)u)->now_us;return true;}
static bool power_good(void *u){return !((fixture_t*)u)->power_bad;}
static bool energy_read(void *u,wcm_r4_energy_sample_t *out) {
  fixture_t *s=u;
  if(s->energy_sequence==0u || s->now_us>s->energy_at_us) {
    ++s->energy_sequence;s->energy_at_us=s->now_us;
  }
  *out=(wcm_r4_energy_sample_t){s->energy_at_us,s->energy_sequence,s->energy_actual_nj};
  return true;
}
static bool reflect_latch(void *u,uint8_t bit) {
  fixture_t *s=u;
  if(s->power_bad || s->energy_actual_nj<WCM_R4_SYMBOL_NJ)return false;
  s->energy_actual_nj-=WCM_R4_SYMBOL_NJ;
  s->reflect_state=bit;
  ++s->symbols_emitted; /* physical modulation, NOT ground-station decoding */
  return true;
}
static bool aero_start(void *u,uint8_t shape){(void)u;(void)shape;return false;}
static bool safe_output(void *u){((fixture_t*)u)->reflect_state=0u;return true;}
static bool local_policy_authorization(void *u,const wcm_r4_capture_t *sample) {
  fixture_t *s=u;
  return s->mission_valid && sample->quality>=WCM_R4_QMIN &&
         sample->value==s->current_local_action;
}
static bool quiescent(void *u){(void)u;return true;}
static void guard(void *u){(void)u;}
static wcm_r4_port_t make_port(fixture_t *s) {
  return (wcm_r4_port_t){clock_read,energy_read,power_good,reflect_latch,aero_start,
       safe_output,local_policy_authorization,guard,guard,s,quiescent};
}
static bool read_factory_image(const char *path,wcm_mission_t *out) {
  FILE *f=fopen(path,"rb");
  if(!f)return false;
  uint8_t bytes[WCM_MISSION_BYTES];
  size_t got=fread(bytes,1u,sizeof(bytes),f);
  int extra=fgetc(f);
  bool ok=(fclose(f)==0 && got==sizeof(bytes) && extra==EOF &&
           wcm_mission_decode(bytes,out));
  return ok;
}
static wcm_r4_status_t observe_locally(fixture_t *f,wcm_r4_cell_t *c) {
  const wcm_r4_capture_t sensor={f->now_us,50000u,f->sensor_value,220u,0u};
  const wcm_r4_capture_t permission={f->now_us,50000u,WCM_R4_ACTION_TX,220u,0u};
  if(wcm_r4_capture(c,WCM_R4_SENSOR,sensor)!=WCM_R4_OK ||
     wcm_r4_capture(c,WCM_R4_LOCAL_POLICY,permission)!=WCM_R4_OK)
    return WCM_R4_IO;
  return wcm_r4_poll(c);
}
static bool send_report(fixture_t *f,wcm_r4_cell_t *c,const wcm_mission_t *m,uint8_t report_no){
  uint8_t frame[WCM_FRAME_BYTES];
  const uint8_t node=(uint8_t)(m->seed&0xffu);
  wcm_frame_encode(node,(uint8_t)(report_no&0x0fu),frame);
  if(observe_locally(f,c)!=WCM_R4_OK)return false;
  if(wcm_r4_tx_start(c,frame,100u)!=WCM_R4_OK)return false;
  ++f->frame_started;
  if(f->energy_actual_nj<WCM_R4_FRAME_INIT_NJ)return false;
  f->energy_actual_nj-=WCM_R4_FRAME_INIT_NJ;
  for(unsigned i=0;i<WCM_R4_FRAME_BITS;i++){
    if(i)f->now_us+=100u;
    if(wcm_r4_tx_step(c)!=WCM_R4_OK)return false;
  }
  f->now_us+=100u;
  if(wcm_r4_tx_step(c)!=WCM_R4_OK || c->mode!=WCM_R4_IDLE)return false;
  ++f->frame_completed;
  return true;
}
int main(int argc,char **argv) {
  if(argc!=2){fprintf(stderr,"factory mission image path required; no runtime command interface\n");return 2;}
  wcm_mission_t m;
  REQUIRE(read_factory_image(argv[1],&m),"factory mission missing/invalid");
  fixture_t f={0};f.now_us=10000u;f.sensor_value=70u;
  f.current_local_action=WCM_R4_ACTION_TX;f.mission_valid=true;
  wcm_power_input_t pwr={1000u,3000u,2000u,1000u};
  REQUIRE(wcm_power_available_nj(pwr,&f.energy_actual_nj),"power model failed");
  wcm_r4_cell_t cell;
  wcm_r4_port_t port=make_port(&f);
  REQUIRE(wcm_r4_init(&cell,&port)==WCM_R4_OK,"control init");
  const uint64_t started=f.now_us;
  uint64_t last_report=0u;
  uint8_t reports=0u;
  uint32_t samples=0u;
  const uint64_t sample_step=(uint64_t)m.sample_period*1000u;
  const uint64_t horizon=(uint64_t)m.seed%16u*1000u+
       (uint64_t)m.max_reports*(uint64_t)m.report_period*10000u+50000u;
  while(f.now_us-started<horizon && reports<m.max_reports){
    f.now_us+=sample_step;
    ++samples;
    /* Deterministic virtual illumination recharge. This is NOT measured power. */
    if(f.energy_actual_nj<2500u){
      uint32_t add=2500u-f.energy_actual_nj;
      if(add>1500u)add=1500u;
      f.energy_actual_nj+=add;
    }
    uint64_t elapsed=f.now_us-started;
    if(!wcm_mission_due(&m,f.sensor_value,samples,elapsed,last_report,reports))continue;
    REQUIRE(send_report(&f,&cell,&m,reports),"local mission optical transaction");
    last_report=f.now_us-started;
    ++reports;
  }
  REQUIRE(f.frame_completed==reports,"report count mismatched");
  REQUIRE(f.symbols_emitted==32u*(uint32_t)reports,"optical symbol count mismatched");
  /* Mission ended; endpoint permits passive termination, no return/ACK. */
  REQUIRE(wcm_r4_world_break(&cell)==WCM_R4_OK,"mission termination revocation");
  REQUIRE(cell.mode==WCM_R4_REBIND,"old mission authorization revoked");
  printf("{\"system\":\"WCM-Core\",\"device\":\"virtual-node\",\"boot\":\"ok\","
         "\"mission_version\":%u,\"mission_task\":%u,\"reports_sent\":%u,"
         "\"optical_symbols_emitted\":%u,\"downlink_commands_received\":0,"
         "\"acknowledgements_expected\":false,\"receiver_algorithm_present\":false,"
         "\"mission_complete\":true,\"hardware_qualified\":false}\n",
         (unsigned)m.version,(unsigned)m.task,(unsigned)reports,f.symbols_emitted);
  return 0;
}
