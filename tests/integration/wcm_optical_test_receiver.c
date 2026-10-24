/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_optical_test_receiver.h"
#include "wcm_optical.h"
/* Test-only decoder: not part of the WCM endpoint image. */
static uint8_t crc8_update(uint8_t crc, uint8_t octet) {
    crc ^= octet;
    for (uint8_t i=0; i<8u; ++i) {
        crc = (uint8_t)((crc & 0x80u) ? ((uint8_t)(crc << 1u) ^ 0x07u)
                                        : (uint8_t)(crc << 1u));
    }
    return crc;
}
wcm_frame_result_t wcm_frame_decode(const uint8_t bits[WCM_FRAME_BYTES],
                                  uint32_t validity_mask,
                                  wcm_frame_payload_t *out) {
    if (!bits || !out) return WCM_FRAME_ARG;
    if (validity_mask != UINT32_MAX) return WCM_FRAME_ERASURE;
    if (bits[0] != WCM_FRAME_PREAMBLE || (bits[2] & 0xf0u) != 0u)
        return WCM_FRAME_PREAMBLE_FAIL;
    if (bits[3] != crc8_update(crc8_update(0u, bits[1]), bits[2]))
        return WCM_FRAME_CRC_FAIL;
    out->node_id = bits[1];
    out->status_nibble = bits[2];
    return WCM_FRAME_OK;
}
