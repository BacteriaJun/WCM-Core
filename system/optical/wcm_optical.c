/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_optical.h"
#include <stddef.h>

static uint8_t crc8_update(uint8_t crc, uint8_t octet) {
    crc ^= octet;
    for (uint8_t i=0; i<8u; ++i) {
        crc = (uint8_t)((crc & 0x80u) ? ((uint8_t)(crc << 1u) ^ 0x07u)
                                        : (uint8_t)(crc << 1u));
    }
    return crc;
}
void wcm_frame_encode(uint8_t node_id, uint8_t status, uint8_t out[WCM_FRAME_BYTES]) {
    if (!out) return;
    out[0] = WCM_FRAME_PREAMBLE;
    out[1] = node_id;
    out[2] = (uint8_t)(status & 0x0fu);
    out[3] = crc8_update(crc8_update(0u, out[1]), out[2]);
}
