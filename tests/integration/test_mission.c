/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_mission64.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"mission C test failed at %d\n",__LINE__);return 1;}}while(0)
int main(void) {
  /* This is a golden vector independently produced by Python missionc.py. */
  const uint8_t sample[8]={0x11u,0x11u,0x81u,0x04u,0x30u,0x00u,0x00u,0xf7u};
  wcm_mission_t m={0};
  CHECK(wcm_mission_decode(sample,&m));
  CHECK(m.version==1u&&m.task==1u&&m.sensor==1u);
  CHECK(m.threshold==6u&&m.sample_period==1u&&m.report_period==1u&&m.max_reports==3u);
  CHECK(m.seed==0u&&m.flags==0u);
  CHECK(!wcm_mission_due(&m,50u,1u,10000u,0u,0u));
  CHECK(wcm_mission_due(&m,70u,1u,10000u,0u,0u));
  CHECK(!wcm_mission_due(&m,70u,2u,19999u,10000u,1u));
  CHECK(wcm_mission_due(&m,70u,2u,20000u,10000u,1u));
  CHECK(!wcm_mission_due(&m,70u,2u,30000u,20000u,3u));
  uint8_t bad[8];memcpy(bad,sample,8u);bad[3]^=1u;
  CHECK(!wcm_mission_decode(bad,&m));
  bad[3]^=1u;bad[0]=0x21u;bad[7]=wcm_mission_crc8(bad,7u);
  CHECK(!wcm_mission_decode(bad,&m));
  puts("Mission-64 C parser: PASS (CRC, versions, limits, scheduling)");return 0;
}
