/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_power_model.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
int main(void) {
  uint32_t v=0u;
  wcm_power_input_t p={100u,3000u,2000u,1000u};
  assert(wcm_power_available_nj(p,&v) && v==250u);
  p.capacitance_nf_min=470u;
  assert(wcm_power_available_nj(p,&v) && v==1175u);
  p.capacitance_nf_min=1000u;p.efficiency_permille=800u;
  assert(wcm_power_available_nj(p,&v) && v==2000u);
  p.voltage_mv_lower=2000u;
  assert(wcm_power_available_nj(p,&v) && v==0u);
  p.voltage_mv_lower=1999u;
  assert(wcm_power_available_nj(p,&v) && v==0u);
  p.voltage_mv_lower=3000u;p.capacitance_nf_min=1000001u;
  assert(!wcm_power_available_nj(p,&v));
  p.capacitance_nf_min=1000u;p.efficiency_permille=1001u;
  assert(!wcm_power_available_nj(p,&v));
  p.efficiency_permille=1000u;
  assert(!wcm_power_available_nj(p,NULL));
  puts("ALL PASS (8) energy arithmetic tests");
  return 0;
}
