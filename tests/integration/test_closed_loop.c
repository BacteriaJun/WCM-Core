/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_optical_test_receiver.h"
/* Virtual power and optical fixture; does not model a real photovoltaic or MEMS device. */
#include "wcm_cell_r4.h"
#include "wcm_optical.h"
#include "wcm_power_model.h"
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#define REQUIRE(x) do{if(!(x)){fprintf(stderr,"closed loop failed at %d: %s\n",__LINE__,#x);return 1;}}while(0)
typedef struct {
  uint64_t now;
  uint32_t seq;
  uint64_t sampled_us;
  uint32_t physical_energy_nj;
  uint8_t received[4];
  uint8_t bit_index;
  uint32_t present_mask;
  unsigned safe_count;
  bool brownout;
} fixture_t;
static bool clock_read(void*u,uint64_t*out){fixture_t*f=u;*out=f->now;return true;}
static bool power_good(void*u){return !((fixture_t*)u)->brownout;}
static bool read_energy(void*u,wcm_r4_energy_sample_t*out){
  fixture_t*f=u;
  if(f->seq==0u || f->now>f->sampled_us) {++f->seq;f->sampled_us=f->now;}
  *out=(wcm_r4_energy_sample_t){f->sampled_us,f->seq,f->physical_energy_nj};return true;
}
static bool reflect(void*u,uint8_t bit){
  fixture_t*f=u;
  if(f->brownout || f->physical_energy_nj<WCM_R4_SYMBOL_NJ)return false;
  f->physical_energy_nj-=WCM_R4_SYMBOL_NJ;
  if(f->bit_index<32u){
    if(bit) f->received[f->bit_index/8u]|=(uint8_t)(0x80u>>(f->bit_index%8u));
    ++f->bit_index;
    f->present_mask=(f->present_mask<<1)|1u; /* synthetic receiver: all symbols visible */
  }
  return true;
}
static bool aero(void*u,uint8_t shape){(void)u;(void)shape;return true;}
static bool safe(void*u){++((fixture_t*)u)->safe_count;return true;}
static bool quiescent(void*u){(void)u;return true;}
static bool command(void*u,const wcm_r4_capture_t*cap){(void)u;(void)cap;return true;}
static void guard_enter(void*u){(void)u;}
static void guard_exit(void*u){(void)u;}
int main(void){
  fixture_t f={0}; f.now=10000u;
  wcm_power_input_t input={1000u,3000u,2000u,1000u};
  REQUIRE(wcm_power_available_nj(input,&f.physical_energy_nj));
  REQUIRE(f.physical_energy_nj==2500u);
  wcm_r4_port_t p={clock_read,read_energy,power_good,reflect,aero,safe,command,guard_enter,guard_exit,&f,quiescent};
  wcm_r4_cell_t c;
  REQUIRE(wcm_r4_init(&c,&p)==WCM_R4_OK);
  ++f.now;
  REQUIRE(wcm_r4_capture(&c,WCM_R4_SENSOR,(wcm_r4_capture_t){f.now,60000u,400u,220u,0u})==WCM_R4_OK);
  REQUIRE(wcm_r4_capture(&c,WCM_R4_LOCAL_POLICY,(wcm_r4_capture_t){f.now,60000u,WCM_R4_ACTION_TX,220u,0u})==WCM_R4_OK);
  REQUIRE(wcm_r4_poll(&c)==WCM_R4_OK);
  uint8_t packet[4];wcm_frame_encode(17u,6u,packet);
  REQUIRE(wcm_r4_tx_start(&c,packet,100u)==WCM_R4_OK);
  /* Emulate the actual startup energy expenditure that the WCM reserves. */
  f.physical_energy_nj-=WCM_R4_FRAME_INIT_NJ;
  for(unsigned i=0u;i<32u;++i) {
    if(i) f.now+=100u;
    REQUIRE(wcm_r4_tx_step(&c)==WCM_R4_OK);
  }
  f.now+=100u;
  REQUIRE(wcm_r4_tx_step(&c)==WCM_R4_OK);
  REQUIRE(c.mode==WCM_R4_IDLE && f.bit_index==32u);
  wcm_frame_payload_t decoded={0};
  REQUIRE(wcm_frame_decode(f.received,f.present_mask,&decoded)==WCM_FRAME_OK);
  REQUIRE(decoded.node_id==17u && decoded.status_nibble==6u);
  uint32_t old_credit=c.energy_credit_nj;
  REQUIRE(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  REQUIRE(c.energy_credit_nj==old_credit); /* same-time reading no rebate */
  ++f.now;
  REQUIRE(wcm_r4_energy_refresh(&c)==WCM_R4_OK);
  REQUIRE(c.energy_credit_nj==f.physical_energy_nj);
  printf("CLOSED LOOP PASS: bits=%u, received_id=%u, physical_nJ=%u, software_credit_nJ=%u, safe_calls=%u\n",
    f.bit_index,decoded.node_id,f.physical_energy_nj,c.energy_credit_nj,f.safe_count);
  /* Separate event: an analog brownout latch must work independently of software. */
  f.brownout=true;
  REQUIRE(wcm_r4_energy_refresh(&c)==WCM_R4_NO_ENERGY);
  wcm_r4_irq_post(&c,WCM_R4_IRQ_BROWNOUT);
  REQUIRE(wcm_r4_poll(&c)==WCM_R4_REBIND_REQUIRED);
  REQUIRE(c.mode==WCM_R4_REBIND);
  puts("BROWNOUT SOFTWARE PATH PASS (analog hardware path NOT qualified)");
  /* A second simulated node loses power halfway through a frame.
   * The receiver must classify missing symbols as erasures, not as zeros.
   */
  fixture_t g={0};g.now=20000u;g.physical_energy_nj=2500u;
  wcm_r4_port_t p2={clock_read,read_energy,power_good,reflect,aero,safe,command,guard_enter,guard_exit,&g,quiescent};
  wcm_r4_cell_t c2;
  REQUIRE(wcm_r4_init(&c2,&p2)==WCM_R4_OK);
  ++g.now;
  REQUIRE(wcm_r4_capture(&c2,WCM_R4_SENSOR,(wcm_r4_capture_t){g.now,60000u,400u,220u,0u})==WCM_R4_OK);
  REQUIRE(wcm_r4_capture(&c2,WCM_R4_LOCAL_POLICY,(wcm_r4_capture_t){g.now,60000u,WCM_R4_ACTION_TX,220u,0u})==WCM_R4_OK);
  REQUIRE(wcm_r4_poll(&c2)==WCM_R4_OK);
  REQUIRE(wcm_r4_tx_start(&c2,packet,100u)==WCM_R4_OK);
  g.physical_energy_nj-=WCM_R4_FRAME_INIT_NJ;
  for(unsigned i=0u;i<8u;++i){
    if(i) g.now+=100u;
    REQUIRE(wcm_r4_tx_step(&c2)==WCM_R4_OK);
  }
  REQUIRE(g.bit_index==8u);
  g.now+=100u;g.brownout=true;
  REQUIRE(wcm_r4_tx_step(&c2)==WCM_R4_NO_ENERGY);
  REQUIRE(c2.mode==WCM_R4_REBIND);
  REQUIRE(wcm_frame_decode(g.received,g.present_mask,&decoded)==WCM_FRAME_ERASURE);
  puts("MIDFRAME POWER LOSS PASS: only 8 valid symbols; full frame erased");
  return 0;
}
