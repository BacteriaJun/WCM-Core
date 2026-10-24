/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#ifndef WCM_OPTICAL_H
#define WCM_OPTICAL_H
/* Endpoint-only optical transmitter: two reflected states, no RX/ACK API. */
#include <stdint.h>
#define WCM_FRAME_BYTES 4u
#define WCM_FRAME_PREAMBLE 0xD3u
void wcm_frame_encode(uint8_t node_id,uint8_t status_nibble,uint8_t out[WCM_FRAME_BYTES]);
#endif
