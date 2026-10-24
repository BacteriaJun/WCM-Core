/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_cell_r4.h"
#include "wcm_optical.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>

#define CHECK(x) do {if(!(x)) {fprintf(stderr,"FAIL %s:%d %s\n",__FILE__,__LINE__,#x);return 1;}}while(0)
typedef struct {
  uint64_t t;
  uint64_t sample_t;
  uint32_t energy;
  uint32_t seq;
  bool pwr, safe_fail, tx_fail, aero_fail, clock_fail, energy_fail;
  bool frozen_energy;
  bool command_authorized;
  bool irq_on_enter;
  bool advance_guard_time;
  void *target;
  unsigned enters, exits, safe_count, tx_calls, aero_calls;
  uint8_t bit, shape;
  bool cannot_settle;
  wcm_r4_port_t p;
} mock_t;
static bool clk(void *u,uint64_t *out){mock_t*m=u;if(m->clock_fail)return false;*out=m->t;return true;}
static bool emeter(void *u,wcm_r4_energy_sample_t *out){mock_t*m=u;if(m->energy_fail)return false;
  if(!m->frozen_energy && (m->seq==0u || m->t>m->sample_t)){++m->seq;m->sample_t=m->t;}
  *out=(wcm_r4_energy_sample_t){m->sample_t,m->seq,m->energy};return true;}
static bool pgood(void *u){return ((mock_t*)u)->pwr;}
static bool reflect(void *u,uint8_t bit){mock_t*m=u;++m->tx_calls;m->bit=bit;
  if(m->tx_fail)return false;
  if(m->energy>=WCM_R4_SYMBOL_NJ)m->energy-=WCM_R4_SYMBOL_NJ;
  return true;}
static bool aero(void *u,uint8_t shape){mock_t*m=u;++m->aero_calls;m->shape=shape;
  if(m->aero_fail)return false;
  if(m->energy>=WCM_R4_AERO_NJ)m->energy-=WCM_R4_AERO_NJ;
  return true;}
static bool safe(void *u){mock_t*m=u;++m->safe_count;return !m->safe_fail;}
static bool quiescent(void *u){return !((mock_t*)u)->cannot_settle;}
static bool authorize(void *u,const wcm_r4_capture_t *sample){
  (void)sample;return ((mock_t*)u)->command_authorized;
}
static void enter(void *u){
  mock_t *m=u;++m->enters;
  if(m->advance_guard_time) {m->t+=5000u;m->advance_guard_time=false;}
  if(m->irq_on_enter && m->target) {
    wcm_r4_irq_post((wcm_r4_cell_t*)m->target,WCM_R4_IRQ_FAULT);
    m->irq_on_enter=false;
  }
}
static void leave(void *u){++((mock_t*)u)->exits;}
static const wcm_r4_port_t *port(mock_t *m){
  m->p=(wcm_r4_port_t){clk,emeter,pgood,reflect,aero,safe,authorize,enter,leave,m,quiescent};
  return &m->p;
}
static int fixture(wcm_r4_cell_t *c,mock_t *m,uint16_t command,uint32_t energy) {
  memset(m,0,sizeof(*m));m->t=10000u;m->pwr=true;m->energy=energy;m->command_authorized=true;
  CHECK(wcm_r4_init(c,port(m))==WCM_R4_OK);
  m->t=10001u;
  CHECK(wcm_r4_capture(c,WCM_R4_SENSOR,(wcm_r4_capture_t){m->t,50000u,400u,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_capture(c,WCM_R4_LOCAL_POLICY,(wcm_r4_capture_t){m->t,50000u,command,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(c)==WCM_R4_OK);
  CHECK(c->mode==(uint8_t)WCM_R4_IDLE);
  return 0;
}
static int frame(wcm_r4_cell_t *c,mock_t *m,uint32_t period) {
  uint8_t data[4];wcm_frame_encode(42u,7u,data);
  CHECK(wcm_r4_tx_start(c,data,period)==WCM_R4_OK);
  for(unsigned i=0;i<WCM_R4_FRAME_BITS;++i) {
    if(i!=0u)m->t+=(uint64_t)period;
    CHECK(wcm_r4_tx_step(c)==WCM_R4_OK);
    CHECK(m->bit==((data[i/8u]>>(7u-(i%8u)))&1u));
  }
  CHECK(wcm_r4_tx_step(c)==WCM_R4_PENDING); /* last symbol aperture */
  m->t+=(uint64_t)period;
  CHECK(wcm_r4_tx_step(c)==WCM_R4_OK);
  CHECK(c->mode==(uint8_t)WCM_R4_IDLE && m->tx_calls==32u);
  CHECK(m->enters==m->exits);
  return 0;
}
static int t_init_no_witness(void) {
  wcm_r4_cell_t c;mock_t m={0};m.pwr=true;m.command_authorized=true;m.t=10u;m.energy=10000u;
  CHECK(wcm_r4_init(&c,port(&m))==WCM_R4_OK);
  uint8_t f[4]={0u};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_REBIND_REQUIRED);
  CHECK(c.mode==WCM_R4_REBIND);return 0;
}
static int t_full_frame(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  CHECK(frame(&c,&m,1000u)==0);return 0;}
static int t_full_duration_ttl(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  c.witness[WCM_R4_SENSOR].ttl_us=1000u;
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,1000u)==WCM_R4_EXPIRED);
  return 0;}
static int t_insufficient_frame_energy(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,1000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_NO_ENERGY);
  CHECK(c.mode==WCM_R4_DORMANT);return 0;}
static int t_energy_sequence_no_double_credit(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,1200u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,10u)==WCM_R4_OK);
  /* Keep the same energy sample: re-reading cannot reset our software debits. */
  m.frozen_energy=true;
  uint32_t before=c.energy_credit_nj;
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==before-WCM_R4_SYMBOL_NJ);
  m.t+=10u;
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==before-2u*WCM_R4_SYMBOL_NJ);
  return 0;}
static int t_energy_stale_reject(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  m.frozen_energy=true;m.seq=1u;m.sample_t=m.t-6000u;
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_STALE);
  CHECK(c.mode==WCM_R4_REBIND);return 0;}
static int t_energy_brownout(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  m.pwr=false;
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_NO_ENERGY);
  CHECK(c.mode==WCM_R4_REBIND);return 0;}
static int t_rx_during_tx(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){m.t,20000u,500u,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_PENDING);
  CHECK(wcm_r4_poll(&c)==WCM_R4_STALE); /* cutover makes in-flight old capture invalid */
  CHECK(c.mode==WCM_R4_REBIND && c.epoch==2u);return 0;}
static int t_queue_fifo(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  for(unsigned i=0;i<WCM_R4_QUEUE;++i)
    CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){m.t,50000u,(uint16_t)(300u+i),220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(&c)==WCM_R4_OK);
  CHECK(c.witness[WCM_R4_SENSOR].value==301u);return 0;}
static int t_queue_overflow(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  for(unsigned i=0;i<WCM_R4_QUEUE;++i)
    CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){m.t,50000u,300u,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){m.t,50000u,300u,220u,0u})==WCM_R4_OVERFLOW);
  CHECK(wcm_r4_poll(&c)==WCM_R4_OVERFLOW && c.mode==WCM_R4_REBIND);
  return 0;}
static int t_irq_fault(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  wcm_r4_irq_post(&c,WCM_R4_IRQ_FAULT|WCM_R4_IRQ_BROWNOUT);
  CHECK(wcm_r4_poll(&c)==WCM_R4_REBIND_REQUIRED);
  CHECK(c.mode==WCM_R4_REBIND && c.epoch==2u);return 0;}
static int t_irq_blocks_start(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  wcm_r4_irq_post(&c,WCM_R4_IRQ_FAULT);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_PENDING);
  CHECK(m.tx_calls==0u);return 0;}
static int t_acquired_time_cutover(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  m.t=10010u;CHECK(wcm_r4_world_break(&c)==WCM_R4_OK); /* cutover at last sampled time until poll */
  CHECK(wcm_r4_poll(&c)==WCM_R4_OK);
  CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){10000u,10000u,300u,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(&c)==WCM_R4_STALE);
  CHECK(!c.witness[WCM_R4_SENSOR].valid);return 0;}
static int t_bad_quality_revokes(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){m.t,10000u,400u,10u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(&c)==WCM_R4_REJECT);
  CHECK(!c.witness[WCM_R4_SENSOR].valid);return 0;}
static int t_backwards_clock(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  m.t=5u;CHECK(wcm_r4_poll(&c)==WCM_R4_HALTED_ERR);
  CHECK(c.mode==WCM_R4_HALTED);return 0;}
static int t_clock_failure(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  m.clock_fail=true;CHECK(wcm_r4_watchdog(&c)==WCM_R4_HALTED_ERR);
  CHECK(c.mode==WCM_R4_HALTED);return 0;}
static int t_reflector_failure(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  m.tx_fail=true;CHECK(wcm_r4_tx_step(&c)==WCM_R4_IO);
  CHECK(c.mode==WCM_R4_REBIND);return 0;}
static int t_symbol_early(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,1000u)==WCM_R4_OK);
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_OK);CHECK(wcm_r4_tx_step(&c)==WCM_R4_PENDING);
  CHECK(m.tx_calls==1u);return 0;}
static int t_symbol_late(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,1000u)==WCM_R4_OK);
  m.t+=1100u;CHECK(wcm_r4_tx_step(&c)==WCM_R4_TIME);
  CHECK(c.mode==WCM_R4_REBIND);return 0;}
static int t_aero_confirmation(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,10000u)==0);
  uint32_t token=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&token)==WCM_R4_OK);
  CHECK(token==1u && c.shape==WCM_R4_AERO_UNKNOWN);
  m.t+=300u;CHECK(wcm_r4_aero_complete(&c,token,m.t,true)==WCM_R4_OK);
  CHECK(c.shape==1u && c.mode==WCM_R4_IDLE);return 0;}
static int t_aero_replay_token(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,10000u)==0);
  uint32_t token=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&token)==WCM_R4_OK);
  m.t+=300u;CHECK(wcm_r4_aero_complete(&c,token+1u,m.t,true)==WCM_R4_STALE);
  CHECK(c.mode==WCM_R4_AERO_PENDING && c.shape==WCM_R4_AERO_UNKNOWN);
  CHECK(wcm_r4_aero_complete(&c,token,m.t,true)==WCM_R4_OK);return 0;}
static int t_aero_prestart_feedback(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,10000u)==0);
  uint32_t token=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&token)==WCM_R4_OK);
  CHECK(wcm_r4_aero_complete(&c,token,m.t-1u,true)==WCM_R4_STALE);
  CHECK(c.shape==WCM_R4_AERO_UNKNOWN);return 0;}
static int t_aero_timeout(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,10000u)==0);
  uint32_t token=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&token)==WCM_R4_OK);
  m.t+=1001u;CHECK(wcm_r4_watchdog(&c)==WCM_R4_TIME);
  CHECK(c.mode==WCM_R4_REBIND && c.shape==WCM_R4_AERO_UNKNOWN);return 0;}
static int t_aero_fail(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,10000u)==0);
  uint32_t token=0u;m.aero_fail=true;
  CHECK(wcm_r4_aero_start(&c,1u,1000u,&token)==WCM_R4_IO);
  CHECK(c.mode==WCM_R4_REBIND);return 0;}
static int t_no_simultaneous(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  uint32_t token=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&token)==WCM_R4_BUSY);
  return 0;}
static int t_safefail_init(void){wcm_r4_cell_t c;mock_t m={0};m.t=10u;m.pwr=true;m.energy=10000u;m.safe_fail=true;m.command_authorized=true;
  CHECK(wcm_r4_init(&c,port(&m))==WCM_R4_HALTED_ERR);
  CHECK(c.mode==WCM_R4_HALTED);return 0;}
static int t_world_epoch_overflow(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  c.epoch=UINT32_MAX;
  CHECK(wcm_r4_world_break(&c)==WCM_R4_HALTED_ERR);
  CHECK(c.mode==WCM_R4_HALTED);return 0;}
static int t_counter_exhaust(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  c.witness[WCM_R4_SENSOR].generation=UINT16_MAX;
  CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){m.t,1000u,300u,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(&c)==WCM_R4_STALE);
  CHECK(c.mode==WCM_R4_REBIND && c.epoch==2u);return 0;}
static int t_aero_powerlow(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,1000u)==0);
  uint32_t tok=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&tok)==WCM_R4_NO_ENERGY);
  CHECK(c.mode==WCM_R4_DORMANT);return 0;}
static int t_watchdog_no_fault(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,10000u)==0);
  uint32_t tok=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&tok)==WCM_R4_OK);
  m.t+=500u;CHECK(wcm_r4_watchdog(&c)==WCM_R4_OK);return 0;}
static int t_energy_missed_read(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  m.energy_fail=true;uint8_t f[4]={0};
  CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_NO_ENERGY);
  return 0;}
static int t_late_command_sample(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  CHECK(wcm_r4_capture(&c,WCM_R4_LOCAL_POLICY,(wcm_r4_capture_t){10000u,1000u,WCM_R4_ACTION_AERO,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(&c)==WCM_R4_STALE);
  CHECK(c.witness[WCM_R4_LOCAL_POLICY].value==WCM_R4_ACTION_TX);return 0;}
static int t_break_rebind_new_sample(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  CHECK(wcm_r4_world_break(&c)==WCM_R4_OK);
  m.t+=100u;
  CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){m.t,50000u,400u,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_capture(&c,WCM_R4_LOCAL_POLICY,(wcm_r4_capture_t){m.t,50000u,WCM_R4_ACTION_TX,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(&c)==WCM_R4_OK);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  return 0;}
static int t_guard_clock_advanced(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  c.witness[WCM_R4_SENSOR].ttl_us=7000u;
  c.witness[WCM_R4_LOCAL_POLICY].ttl_us=7000u;
  m.advance_guard_time=true;
  uint8_t f[4]={0};
  CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_EXPIRED);
  CHECK(m.tx_calls==0u && c.mode==WCM_R4_IDLE && m.enters==m.exits);
  return 0;
}
static int t_feedback_irq_inside_guard(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,10000u)==0);
  uint32_t tok=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&tok)==WCM_R4_OK);
  m.target=&c;m.irq_on_enter=true;
  m.t+=200u;
  CHECK(wcm_r4_aero_complete(&c,tok,m.t,true)==WCM_R4_PENDING);
  CHECK(c.shape==WCM_R4_AERO_UNKNOWN && c.mode==WCM_R4_AERO_PENDING);
  CHECK(wcm_r4_poll(&c)==WCM_R4_REBIND_REQUIRED);
  CHECK(c.mode==WCM_R4_REBIND);
  return 0;
}
static int t_new_energy_seq_rollback(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  m.frozen_energy=true;m.seq=0u;
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_STALE);
  CHECK(c.mode==WCM_R4_REBIND);return 0;
}
static int t_forged_fresh_energy_seq(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  m.frozen_energy=true;
  ++m.seq; /* sequence claims new sample without new acquisition time */
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_STALE);
  CHECK(c.mode==WCM_R4_REBIND);return 0;
}
static int t_world_break_reads_actual_clock(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  m.t+=1000u;
  CHECK(wcm_r4_world_break(&c)==WCM_R4_OK);
  CHECK(c.cutover_us==m.t);
  CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){m.t-1u,1000u,400u,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(&c)==WCM_R4_STALE);
  return 0;
}
static int t_command_auth_reject(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  m.command_authorized=false;m.t+=1u;
  CHECK(wcm_r4_capture(&c,WCM_R4_LOCAL_POLICY,(wcm_r4_capture_t){m.t,50000u,WCM_R4_ACTION_TX,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(&c)==WCM_R4_REJECT);
  CHECK(!c.witness[WCM_R4_LOCAL_POLICY].valid);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_REBIND_REQUIRED);
  return 0;
}
static int t_fresh_meter_no_topup_during_symbols(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,1200u)==0);
  uint8_t f[4]={0}; CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  uint32_t before=c.energy_credit_nj;
  m.energy=99000u; m.t+=1u; /* meter would report huge new credit */
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==before-WCM_R4_SYMBOL_NJ);
  m.t+=99u;
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==before-2u*WCM_R4_SYMBOL_NJ);
  return 0;
}
static int t_meter_never_topup_while_aero_pending(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,3000u)==0);
  uint32_t tok=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&tok)==WCM_R4_OK);
  uint32_t before=c.energy_credit_nj; m.energy=99000u;m.t+=100u;
  /* sample via direct executor-internal path is unavailable; use new R3 public energy refresh */
  CHECK(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==before);
  CHECK(wcm_r4_aero_complete(&c,tok,m.t,true)==WCM_R4_OK);
  CHECK(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==before); /* identical seq, no rebate */
  m.t+=1u;CHECK(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==99000u); /* physical sample after confirmation */
  return 0;
}
static int t_predispatch_meter_cannot_refund_after_completion(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,3000u)==0);
  uint32_t tok=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&tok)==WCM_R4_OK);
  /* This meter sample is newer than initial start but BEFORE feedback confirms completion. */
  m.energy=99000u;m.t+=200u;
  CHECK(wcm_r4_aero_complete(&c,tok,m.t,true)==WCM_R4_OK);
  uint32_t before=c.energy_credit_nj;
  m.frozen_energy=true;m.seq=2u;m.sample_t=m.t-50u;
  CHECK(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==before); /* NOT reimbursed by pre-completion sample */
  m.frozen_energy=false;m.t+=1u;
  CHECK(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==99000u);
  return 0;
}

/* R4: an interrupted actuator is not physically settled merely because
 * software issued safe(), and newer meter values cannot clear that debt. */
static int t_quarantine_break_inflight(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,8000u)==0);
  uint32_t tok=0u;CHECK(wcm_r4_aero_start(&c,1u,1000u,&tok)==WCM_R4_OK);
  m.t+=50u;
  m.cannot_settle=true;
  CHECK(wcm_r4_world_break(&c)==WCM_R4_OK);
  CHECK(c.energy_quarantined==1u && c.energy_credit_nj==0u);
  CHECK(c.mode==WCM_R4_REBIND);
  m.t+=1u;
  CHECK(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){m.t,50000u,400u,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_capture(&c,WCM_R4_LOCAL_POLICY,(wcm_r4_capture_t){m.t,50000u,WCM_R4_ACTION_AERO,220u,0u})==WCM_R4_OK);
  CHECK(wcm_r4_poll(&c)==WCM_R4_OK);
  CHECK(c.mode==WCM_R4_REBIND); /* evidence alone cannot settle mechanics */
  CHECK(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==0u);
  CHECK(wcm_r4_settled(&c)==WCM_R4_BUSY);
  CHECK(c.energy_quarantined==1u);
  CHECK(wcm_r4_aero_start(&c,0u,1000u,&tok)==WCM_R4_NO_ENERGY);
  CHECK(m.aero_calls==1u);
  m.cannot_settle=false;
  m.t+=1u;
  CHECK(wcm_r4_settled(&c)==WCM_R4_OK);
  CHECK(c.energy_quarantined==0u && c.mode==WCM_R4_DORMANT);
  CHECK(c.energy_credit_nj==0u);
  CHECK(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==0u); /* same-time ADC cannot refill */
  m.t+=1u;
  CHECK(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  CHECK(c.energy_credit_nj==m.energy);
  CHECK(wcm_r4_aero_start(&c,0u,1000u,&tok)==WCM_R4_OK);
  return 0;
}
static int t_quarantine_break_during_tx(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_OK);
  CHECK(wcm_r4_world_break(&c)==WCM_R4_OK);
  CHECK(c.energy_quarantined==1u && c.energy_credit_nj==0u);
  CHECK(wcm_r4_settled(&c)==WCM_R4_OK);
  CHECK(c.energy_quarantined==0u);
  return 0;
}
static int t_failed_actuation_requires_settle(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,10000u)==0);
  uint32_t token=0u;m.aero_fail=true;
  CHECK(wcm_r4_aero_start(&c,1u,1000u,&token)==WCM_R4_IO);
  CHECK(c.energy_quarantined==1u && c.mode==WCM_R4_REBIND);
  CHECK(c.energy_credit_nj==0u);
  return 0;
}
static int t_failed_reflect_requires_settle(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  m.tx_fail=true;
  CHECK(wcm_r4_tx_step(&c)==WCM_R4_IO);
  CHECK(c.energy_quarantined==1u && c.mode==WCM_R4_REBIND);
  return 0;
}
static int t_feedback_must_follow_dispatch(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_AERO,10000u)==0);
  uint32_t token=0u;
  CHECK(wcm_r4_aero_start(&c,1u,1000u,&token)==WCM_R4_OK);
  CHECK(wcm_r4_aero_complete(&c,token,m.t,true)==WCM_R4_STALE);
  CHECK(c.mode==WCM_R4_AERO_PENDING && c.shape==WCM_R4_AERO_UNKNOWN);
  return 0;
}
static int t_init_must_be_physically_quiescent(void){wcm_r4_cell_t c;mock_t m={0};
  m.t=1000u;m.pwr=true;m.energy=10000u;m.command_authorized=true;m.cannot_settle=true;
  CHECK(wcm_r4_init(&c,port(&m))==WCM_R4_HALTED_ERR);
  CHECK(c.mode==WCM_R4_HALTED);
  return 0;
}
static int t_settle_does_not_skip_new_evidence(void){wcm_r4_cell_t c;mock_t m;
  CHECK(fixture(&c,&m,WCM_R4_ACTION_TX,10000u)==0);
  uint8_t f[4]={0};CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_OK);
  CHECK(wcm_r4_world_break(&c)==WCM_R4_OK);
  m.t+=1u;CHECK(wcm_r4_settled(&c)==WCM_R4_OK);
  CHECK(c.mode==WCM_R4_REBIND);
  m.t+=1u;CHECK(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  CHECK(wcm_r4_tx_start(&c,f,100u)==WCM_R4_REBIND_REQUIRED);
  return 0;
}
int main(void){
  int (*cases[])(void)={t_init_no_witness,t_full_frame,t_full_duration_ttl,
    t_insufficient_frame_energy,t_energy_sequence_no_double_credit,
    t_energy_stale_reject,t_energy_brownout,t_rx_during_tx,t_queue_fifo,
    t_queue_overflow,t_irq_fault,t_irq_blocks_start,t_acquired_time_cutover,
    t_bad_quality_revokes,t_backwards_clock,t_clock_failure,t_reflector_failure,
    t_symbol_early,t_symbol_late,t_aero_confirmation,t_aero_replay_token,
    t_aero_prestart_feedback,t_aero_timeout,t_aero_fail,t_no_simultaneous,
    t_safefail_init,t_world_epoch_overflow,t_counter_exhaust,t_aero_powerlow,
    t_watchdog_no_fault,t_energy_missed_read,t_late_command_sample,
    t_break_rebind_new_sample,t_guard_clock_advanced,
    t_feedback_irq_inside_guard,t_new_energy_seq_rollback,
    t_forged_fresh_energy_seq,t_world_break_reads_actual_clock,
    t_command_auth_reject,t_fresh_meter_no_topup_during_symbols,
    t_meter_never_topup_while_aero_pending,t_predispatch_meter_cannot_refund_after_completion,
    t_quarantine_break_inflight,t_quarantine_break_during_tx,
    t_failed_actuation_requires_settle,t_failed_reflect_requires_settle,
    t_feedback_must_follow_dispatch,t_init_must_be_physically_quiescent,
    t_settle_does_not_skip_new_evidence};
  for(size_t i=0u;i<sizeof(cases)/sizeof(cases[0]);++i) if(cases[i]()) return 1;
  printf("ALL PASS (%zu) | sizeof(wcm_r4_cell_t)=%zu B\n",sizeof(cases)/sizeof(cases[0]),sizeof(wcm_r4_cell_t));
  return 0;
}
