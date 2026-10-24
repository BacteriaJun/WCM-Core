/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
/* SPSC host concurrency stress using two producer threads. */
#include "wcm_cell_r4.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#define ITER 20000u
typedef struct {wcm_r4_cell_t *c; uint8_t lane; _Atomic unsigned successes,overflow; _Atomic bool done;} producer_t;
static bool clock_read(void *u,uint64_t *t){(void)u;*t=10001u;return true;}
static bool energy(void *u,wcm_r4_energy_sample_t *s){(void)u;*s=(wcm_r4_energy_sample_t){10001u,1u,10000u};return true;}
static bool yes_power(void *u){(void)u;return true;}
static bool reflect(void *u,uint8_t b){(void)u;(void)b;return true;}
static bool aero(void *u,uint8_t s){(void)u;(void)s;return true;}
static bool safe(void *u){(void)u;return true;}
static bool quiescent(void*u){(void)u;return true;}
static bool authorize(void *u, const wcm_r4_capture_t *s){(void)u;(void)s;return true;}
static void enter(void *u){(void)u;}
static void exit_guard(void *u){(void)u;}
static void *produce(void *p){
  producer_t *x=p;
  for(unsigned i=0u;i<ITER;++i){
    wcm_r4_capture_t s={10001u,50000u,x->lane==WCM_R4_SENSOR?400u:WCM_R4_ACTION_TX,220u,0u};
    wcm_r4_status_t r=wcm_r4_capture(x->c,x->lane,s);
    if(r==WCM_R4_OK) atomic_fetch_add(&x->successes,1u);
    else if(r==WCM_R4_OVERFLOW) atomic_fetch_add(&x->overflow,1u);
    else abort();
  }
  atomic_store(&x->done,true);
  return NULL;
}
int main(void){
  wcm_r4_cell_t c;
  wcm_r4_port_t p={clock_read,energy,yes_power,reflect,aero,safe,authorize,enter,exit_guard,NULL,quiescent};
  if(wcm_r4_init(&c,&p)!=WCM_R4_OK) return 1;
  producer_t a={.c=&c,.lane=WCM_R4_SENSOR}, b={.c=&c,.lane=WCM_R4_LOCAL_POLICY};
  atomic_init(&a.successes,0u);atomic_init(&a.overflow,0u);atomic_init(&a.done,false);
  atomic_init(&b.successes,0u);atomic_init(&b.overflow,0u);atomic_init(&b.done,false);
  pthread_t x,y;
  if(pthread_create(&x,NULL,produce,&a) || pthread_create(&y,NULL,produce,&b)) return 2;
  while(!atomic_load(&a.done) || !atomic_load(&b.done)) (void)wcm_r4_poll(&c);
  pthread_join(x,NULL);pthread_join(y,NULL);
  for(unsigned n=0;n<8u;++n) (void)wcm_r4_poll(&c);
  unsigned int h0=atomic_load(&c.ingress[0].head),t0=atomic_load(&c.ingress[0].tail);
  unsigned int h1=atomic_load(&c.ingress[1].head),t1=atomic_load(&c.ingress[1].tail);
  unsigned int ok0=atomic_load(&a.successes),of0=atomic_load(&a.overflow);
  unsigned int ok1=atomic_load(&b.successes),of1=atomic_load(&b.overflow);
  printf("SPSC 2 producers: lane0 ok=%u overflow=%u, lane1 ok=%u overflow=%u; residual=%u/%u\n",
         ok0,of0,ok1,of1,h0-t0,h1-t1);
  if(ok0+of0!=ITER || ok1+of1!=ITER || h0!=t0 || h1!=t1) return 3;
  return 0;
}
