/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_power_model.h"
#include <stdint.h>
#include <limits.h>
bool wcm_power_available_nj(wcm_power_input_t in,uint32_t *out) {
  if(!out || in.capacitance_nf_min==0u ||
     in.capacitance_nf_min>1000000u ||
     in.voltage_mv_lower>10000u || in.cutoff_mv_upper>10000u ||
     in.efficiency_permille>1000u) return false;
  if(in.voltage_mv_lower<=in.cutoff_mv_upper || in.efficiency_permille==0u) {
    *out=0u;
    return true;
  }
  uint64_t high=(uint64_t)in.voltage_mv_lower*(uint64_t)in.voltage_mv_lower;
  uint64_t low=(uint64_t)in.cutoff_mv_upper*(uint64_t)in.cutoff_mv_upper;
  /* nJ = C[nF] * (Vhi[mV]^2 - Vlo[mV]^2) / (2,000,000).
   * Multiply in safe order to avoid overflow at the specified input bounds.
   */
  uint64_t raw=((uint64_t)in.capacitance_nf_min*(high-low))/2000000u;
  uint64_t derated=(raw*(uint64_t)in.efficiency_permille)/1000u;
  *out=derated>UINT32_MAX?UINT32_MAX:(uint32_t)derated;
  return true;
}
