/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#ifndef WCM_POWER_MODEL_H
#define WCM_POWER_MODEL_H
/* Reference capacitor-energy arithmetic.
 * Input voltage and capacitance must be worst-case lower bounds; brownout
 * comparators and ESR-induced voltage sag are independent hardware checks.
 */
#include <stdint.h>
#include <stdbool.h>
typedef struct {
  uint32_t capacitance_nf_min;  /* lower-bound capacitance after tolerance, aging and temperature */
  uint16_t voltage_mv_lower;    /* conservative acquired capacitor voltage */
  uint16_t cutoff_mv_upper;    /* high-side cutoff voltage accounting for ADC and regulator margin */
  uint16_t efficiency_permille; /* <=1000; discharge conversion lower bound */
} wcm_power_input_t;
bool wcm_power_available_nj(wcm_power_input_t in, uint32_t *out_nj);
#endif
