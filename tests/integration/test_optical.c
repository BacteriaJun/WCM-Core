/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_optical_test_receiver.h"
#include "wcm_optical.h"
#include <stdio.h>
#define CHECK(x) do {if(!(x)){fprintf(stderr,"FAIL %s:%d: %s\n",__FILE__,__LINE__,#x);return 1;}}while(0)
int main(void) {
    uint8_t frame[WCM_FRAME_BYTES]; wcm_frame_payload_t decoded={0};
    wcm_frame_encode(0xABu,0x0Du,frame);
    CHECK(wcm_frame_decode(frame,UINT32_MAX,&decoded)==WCM_FRAME_OK);
    CHECK(decoded.node_id==0xABu && decoded.status_nibble==0x0Du);
    puts("PASS encode_decode");
    CHECK(wcm_frame_decode(frame, UINT32_MAX ^ 0x00000008u,&decoded)==WCM_FRAME_ERASURE);
    puts("PASS erasure_never_zero");
    frame[1] ^= 0x02u;
    CHECK(wcm_frame_decode(frame,UINT32_MAX,&decoded)==WCM_FRAME_CRC_FAIL);
    puts("PASS corrupt_payload");
    frame[0] = 0;
    CHECK(wcm_frame_decode(frame,UINT32_MAX,&decoded)==WCM_FRAME_PREAMBLE_FAIL);
    puts("PASS bad_preamble");
    puts("ALL PASS (4) optical frame tests");
    return 0;
}
