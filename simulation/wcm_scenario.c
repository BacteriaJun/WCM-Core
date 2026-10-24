/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
/* WCM-Core conceptual, deterministic HOST ENVIRONMENT simulator.
 * A host-selected scenario changes SENSOR or POWER inputs, never supplies a
 * remote station command/ACK. This binary uses the actual Cell R4 C17 core.
 * Not a qualified node firmware, physical sensor or optical channel.
 */
#include "wcm_cell_r4.h"
#include "wcm_optical.h"
#include "wcm_power_model.h"
#include "wcm_mission64.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stdint.h>

typedef struct {
  uint64_t us, energy_timestamp;
  uint32_t seq, joules, symbols, completed, interrupted, safe_calls, epoch_breaks;
  uint16_t sensor;
  uint8_t reflect;
  bool brownout;
} env_t;
static bool clk(void *p,uint64_t *out){*out=((env_t*)p)->us;return true;}
static bool pg(void *p){return !((env_t*)p)->brownout;}
static bool meter(void *p,wcm_r4_energy_sample_t *r){
  env_t *e=p;
  if(e->seq==0 || e->us>e->energy_timestamp){e->seq++;e->energy_timestamp=e->us;}
  *r=(wcm_r4_energy_sample_t){e->energy_timestamp,e->seq,e->joules};return true;
}
static bool reflect(void *p,uint8_t v){
  env_t *e=p;if(e->brownout || e->joules<WCM_R4_SYMBOL_NJ)return false;
  e->joules-=WCM_R4_SYMBOL_NJ;e->reflect=v;e->symbols++;return true;
}
static bool aero(void *p,uint8_t shape){(void)p;(void)shape;return false;}
static bool safe(void *p){env_t *e=p;e->reflect=0;e->safe_calls++;return true;}
static bool local(void *p,const wcm_r4_capture_t *c){
  (void)p;return c->quality>=WCM_R4_QMIN && c->value==WCM_R4_ACTION_TX;
}
static void guard(void *p){(void)p;}
static bool settled(void *p){(void)p;return true;}
static wcm_r4_port_t port(env_t *e){return (wcm_r4_port_t){clk,meter,pg,reflect,aero,safe,local,guard,guard,e,settled};}
static bool load(const char *path,wcm_mission_t *m){
  uint8_t image[8];FILE *f=fopen(path,"rb");if(!f)return false;
  size_t n=fread(image,1,8,f);int extra=fgetc(f);int closed=fclose(f);
  return n==8 && extra==EOF && closed==0 && wcm_mission_decode(image,m);
}
static bool observe(env_t *e,wcm_r4_cell_t *c){
  wcm_r4_capture_t s={e->us,50000u,e->sensor,220u,0u};
  wcm_r4_capture_t l={e->us,50000u,WCM_R4_ACTION_TX,220u,0u};
  return wcm_r4_capture(c,WCM_R4_SENSOR,s)==WCM_R4_OK &&
         wcm_r4_capture(c,WCM_R4_LOCAL_POLICY,l)==WCM_R4_OK &&
         wcm_r4_poll(c)==WCM_R4_OK;
}
/* Returns: 1 committed report, 0 intended in-flight physical interruption,
 * -1 unexpected software or energy error. */
static int tx(env_t *e,wcm_r4_cell_t *c,const wcm_mission_t *m,unsigned report,bool inject_abort){
  uint8_t frame[WCM_FRAME_BYTES];
  wcm_frame_encode((uint8_t)m->seed,(uint8_t)(report&15),frame);
  if(!observe(e,c) || wcm_r4_tx_start(c,frame,100u)!=WCM_R4_OK)return -1;
  if(e->joules<WCM_R4_FRAME_INIT_NJ)return -1;
  e->joules-=WCM_R4_FRAME_INIT_NJ;
  for(unsigned k=0;k<WCM_R4_FRAME_BITS;k++){
    if(k)e->us+=100;
    if(inject_abort && k==4u){
      if(wcm_r4_world_break(c)!=WCM_R4_OK)return -1;
      e->epoch_breaks++;e->interrupted++;
      return c->mode==WCM_R4_REBIND && e->reflect==0u ? 0 : -1;
    }
    if(wcm_r4_tx_step(c)!=WCM_R4_OK)return -1;
  }
  e->us+=100;
  if(wcm_r4_tx_step(c)!=WCM_R4_OK || c->mode!=WCM_R4_IDLE)return -1;
  e->completed++;return 1;
}
static void trace(const char *event,unsigned tick,const env_t *e,unsigned boot){
  printf("{\"type\":\"event\",\"event\":\"%s\",\"tick\":%u,\"boot\":%u,\"us\":%llu,\"completed\":%u,\"symbols\":%u}\n",
         event,tick,boot,(unsigned long long)e->us,e->completed,e->symbols);
}
int main(int argc,char **argv){
  if(argc!=4){fprintf(stderr,"host simulator: mission.bin nominal|brownout|sensor-silent|energy-starve|fault-inflight ticks\n");return 2;}
  wcm_mission_t m;if(!load(argv[1],&m)){fputs("invalid provisioned mission\n",stderr);return 2;}
  const char *scenario=argv[2];
  bool nominal=strcmp(scenario,"nominal")==0;
  bool brownout=strcmp(scenario,"brownout")==0;
  bool silent=strcmp(scenario,"sensor-silent")==0;
  bool starving=strcmp(scenario,"energy-starve")==0;
  bool interrupted=strcmp(scenario,"fault-inflight")==0;
  if(!nominal&&!brownout&&!silent&&!starving&&!interrupted){fputs("unknown host scenario\n",stderr);return 2;}
  char *end=0;unsigned long ticks=strtoul(argv[3],&end,10);
  if(!end || *end!='\0' || ticks<1 || ticks>100000){fputs("ticks outside 1..100000\n",stderr);return 2;}
  env_t e={0};e.us=10000;e.sensor=silent?0:700;e.joules=starving?0:2500;
  wcm_r4_port_t io=port(&e);wcm_r4_cell_t c;
  if(wcm_r4_init(&c,&io)!=WCM_R4_OK)return 3;
  const uint64_t boot_at_initial=e.us;
  uint64_t boot_at=boot_at_initial,last=0;
  uint32_t samples=0;unsigned since_boot=0,boots=1;
  bool event_fired=false,terminal=false;
  trace("boot",0,&e,boots);
  for(unsigned t=0;t<ticks && !terminal;t++){
    e.us+=(uint64_t)m.sample_period*1000u;samples++;
    if(!starving && e.joules<2500){
      uint32_t add=2500-e.joules;
      e.joules+=add>1500?1500:add;
    }
    if(silent || !wcm_mission_due(&m,e.sensor,samples,e.us-boot_at,last,(uint8_t)since_boot))continue;
    if(starving)continue;/* physical gate rejects unavailable energy */
    int result=tx(&e,&c,&m,since_boot,interrupted && !event_fired);
    if(result<0){fputs("unexpected control transaction failure\n",stderr);return 3;}
    if(result==0){trace("world_break_quarantine",t,&e,boots);event_fired=true;terminal=true;break;}
    since_boot++;last=e.us-boot_at;trace("report_committed",t,&e,boots);
    if(brownout && !event_fired){
      event_fired=true;e.brownout=true;
      wcm_r4_irq_post(&c,WCM_R4_IRQ_BROWNOUT);
      wcm_r4_status_t s=wcm_r4_poll(&c);
      if(s!=WCM_R4_REBIND_REQUIRED && s!=WCM_R4_NO_ENERGY && s!=WCM_R4_HALTED_ERR && c.mode!=WCM_R4_REBIND){
        fputs("brownout did not revoke previous authority\n",stderr);return 3;
      }
      trace("brownout",t,&e,boots);
      e.brownout=false;e.joules=2500;e.us+=1000;
      /* Power-on reinitialisation reloads the immutable Mission-64 image.
       * Report count is volatile: retransmission is an allowed AT-LEAST-ONCE
       * semantic. Non-idempotent physical actions are NOT supported by v1. */
      if(wcm_r4_init(&c,&io)!=WCM_R4_OK)return 3;
      boots++;since_boot=0;samples=0;last=0;boot_at=e.us;
      trace("cold_boot",t,&e,boots);
    }
    if(since_boot==m.max_reports){trace("passive",t,&e,boots);terminal=true;}
  }
  printf("{\"type\":\"summary\",\"scenario\":\"%s\",\"boots\":%u,\"completed\":%u,\"symbols\":%u,\"interrupted\":%u,\"epoch_breaks\":%u,\"passive\":%s,\"downlink\":false,\"ack\":false,\"hardware_qualified\":false}\n",
         scenario,boots,e.completed,e.symbols,e.interrupted,e.epoch_breaks,
         terminal&&!interrupted?"true":"false");
  return 0;
}
