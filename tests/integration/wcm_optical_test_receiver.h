/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#ifndef WCM_TEST_RECEIVER_H
#define WCM_TEST_RECEIVER_H
/* Historical test oracle for framing ONLY; NEVER bundled into endpoint. */
#include "wcm_optical.h"
#include <stdint.h>
typedef enum { WCM_FRAME_OK=0, WCM_FRAME_ERASURE=-1, WCM_FRAME_PREAMBLE_FAIL=-2,
               WCM_FRAME_CRC_FAIL=-3, WCM_FRAME_ARG=-4 } wcm_frame_result_t;
typedef struct {uint8_t node_id;uint8_t status_nibble;} wcm_frame_payload_t;
wcm_frame_result_t wcm_frame_decode(const uint8_t bits[WCM_FRAME_BYTES],
                                  uint32_t validity_mask,wcm_frame_payload_t *out);
#endif
