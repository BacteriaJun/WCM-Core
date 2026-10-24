/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#include "wcm_cell_r4.h"
#include <stddef.h>
#include <limits.h>

/* Freestanding zeroing; toolchain must not introduce implicit libc calls. */
static void wcm_zero(void *dst,size_t count) {
  unsigned char *p=dst;
  for(size_t i=0u;i<count;++i) p[i]=0u;
}
static wcm_r4_status_t reject(wcm_r4_cell_t *c, wcm_r4_status_t why) {
  if (c->deny_count < UINT16_MAX) ++c->deny_count;
  return why;
}
static wcm_r4_status_t halt(wcm_r4_cell_t *c) {
  c->mode=(uint8_t)WCM_R4_HALTED;
  c->tx_remain_nj=0u;
  for(unsigned i=0u;i<WCM_R4_LANES;++i) c->witness[i].valid=0u;
  (void)c->port->safe(c->port->user);
  c->energy_reconcile_after_us=c->now_us;
  return WCM_R4_HALTED_ERR;
}
static bool enough(const wcm_r4_cell_t *c, uint32_t need) {
  return !c->energy_quarantined && c->energy_credit_nj>=WCM_R4_HARD_RESERVE_NJ &&
         need <= c->energy_credit_nj-WCM_R4_HARD_RESERVE_NJ;
}
static bool pending(const wcm_r4_cell_t *c) {
  if (atomic_load_explicit(&c->irq_flags,memory_order_acquire)) return true;
  for(unsigned i=0u;i<WCM_R4_LANES;++i) {
    if(atomic_load_explicit(&c->ingress[i].head,memory_order_acquire)!=
       atomic_load_explicit(&c->ingress[i].tail,memory_order_acquire)) return true;
  }
  return false;
}
static wcm_r4_status_t sync_time(wcm_r4_cell_t *c) {
  uint64_t t=0u;
  if (!c->port->clock_us(c->port->user,&t) || t<c->now_us) return WCM_R4_TIME;
  c->now_us=t;
  return WCM_R4_OK;
}
static wcm_r4_status_t sample_energy(wcm_r4_cell_t *c) {
  wcm_r4_energy_sample_t s={0u,0u,0u};
  if (!c->port->power_good(c->port->user) || !c->port->energy_read(c->port->user,&s))
    return WCM_R4_NO_ENERGY;
  if (s.acquired_us>c->now_us || c->now_us-s.acquired_us>WCM_R4_ENERGY_SAMPLE_MAX_AGE_US ||
      s.sequence==0u || s.sequence<c->last_energy_seq) return WCM_R4_STALE;
  if (s.sequence>c->last_energy_seq) {
    /* A new sequence MUST identify a genuinely newer acquisition. */
    if(c->last_energy_seq!=0u && s.acquired_us<=c->last_energy_acquired_us)
      return WCM_R4_STALE;
    c->last_energy_acquired_us=s.acquired_us;
    c->last_energy_seq=s.sequence;
    const uint32_t measured=s.available_nj>WCM_R4_ENERGY_MAX_NJ ?
                        WCM_R4_ENERGY_MAX_NJ:s.available_nj;
    /* A new ADC sequence is not automatically new spendable credit:
     * 1. During TX/aero pending, physical expenditures may not have
     *    settled in the measurement. Only lower existing credit.
     * 2. In idle/rebind/dormant, replenish only if acquisition is strictly
     *    AFTER the most recent physical action/completion watermark.
     * This is safe only with a qualified lower-bound physical meter.
     */
    const bool outstanding=c->mode==(uint8_t)WCM_R4_TX ||
                           c->mode==(uint8_t)WCM_R4_AERO_PENDING;
    if(!outstanding && !c->energy_quarantined && s.acquired_us>c->energy_reconcile_after_us) {
      c->energy_credit_nj=measured;
      if(c->energy_reconcile_count<UINT32_MAX) ++c->energy_reconcile_count;
    } else if(measured<c->energy_credit_nj) {
      c->energy_credit_nj=measured;
    }
  }
  /* Identical measurement is NEVER recredited after a debit. */
  return WCM_R4_OK;
}
static wcm_r4_status_t gate_evidence(const wcm_r4_cell_t *c, uint16_t cmd, uint64_t horizon) {
  for(unsigned i=0u;i<WCM_R4_LANES;++i) {
    const wcm_r4_witness_t *w=&c->witness[i];
    if (!w->valid || w->epoch!=c->epoch) return WCM_R4_REBIND_REQUIRED;
    if (w->acquired_us<=c->cutover_us || w->acquired_us>c->now_us ||
        horizon<c->now_us || horizon<w->acquired_us ||
        horizon-w->acquired_us>(uint64_t)w->ttl_us) return WCM_R4_EXPIRED;
  }
  if (c->witness[WCM_R4_SENSOR].value>WCM_R4_SENSOR_MAX ||
      c->witness[WCM_R4_LOCAL_POLICY].value!=cmd) return WCM_R4_REJECT;
  return WCM_R4_OK;
}
static wcm_r4_status_t guarded(wcm_r4_cell_t *c,uint16_t cmd,uint64_t horizon,uint32_t energy_need) {
  wcm_r4_status_t r;
  if (pending(c)) return WCM_R4_PENDING;
  r=sample_energy(c);
  if(r!=WCM_R4_OK) return r;
  if(!enough(c,energy_need)) return WCM_R4_NO_ENERGY;
  return gate_evidence(c,cmd,horizon);
}
static wcm_r4_status_t cut(wcm_r4_cell_t *c) {
  if (c->epoch==UINT32_MAX) return halt(c);
  if(c->mode==(uint8_t)WCM_R4_TX || c->mode==(uint8_t)WCM_R4_AERO_PENDING) {
    c->energy_quarantined=1u;
    c->energy_credit_nj=0u; /* do not re-credit until physical output settled */
  }
  ++c->epoch;
  if (c->break_count<UINT16_MAX) ++c->break_count;
  c->cutover_us=c->now_us;
  c->mode=(uint8_t)WCM_R4_REBIND;
  c->tx_remain_nj=0u;
  c->tx_index=0u;
  c->shape=WCM_R4_AERO_UNKNOWN;
  c->shape_requested=WCM_R4_AERO_UNKNOWN;
  c->reflect_level=0u;
  wcm_zero(c->witness,sizeof(c->witness));
  if(!c->port->safe(c->port->user)) return halt(c);
  c->energy_reconcile_after_us=c->now_us;
  return WCM_R4_OK;
}
wcm_r4_status_t wcm_r4_settled(wcm_r4_cell_t *c) {
  if(!c) return WCM_R4_REJECT;
  if(c->mode==(uint8_t)WCM_R4_HALTED) return WCM_R4_HALTED_ERR;
  if(c->mode==(uint8_t)WCM_R4_TX || c->mode==(uint8_t)WCM_R4_AERO_PENDING)
    return WCM_R4_BUSY;
  c->port->guard_enter(c->port->user);
  wcm_r4_status_t rc=sync_time(c);
  if(rc==WCM_R4_OK && pending(c)) rc=WCM_R4_PENDING;
  if(rc==WCM_R4_OK && !c->port->physical_quiescent(c->port->user)) rc=WCM_R4_BUSY;
  if(rc==WCM_R4_OK && c->energy_quarantined) {
    c->energy_quarantined=0u;
    c->energy_reconcile_after_us=c->now_us;
    c->energy_credit_nj=0u; /* demand strictly later physical energy reading */
    if(c->mode==(uint8_t)WCM_R4_REBIND && c->witness[0].valid &&
       c->witness[1].valid) c->mode=(uint8_t)WCM_R4_IDLE;
  }
  c->port->guard_exit(c->port->user);
  if(rc==WCM_R4_TIME) return halt(c);
  return rc;
}
wcm_r4_status_t wcm_r4_energy_refresh(wcm_r4_cell_t *c) {
  if(!c) return WCM_R4_REJECT;
  if(c->mode==(uint8_t)WCM_R4_HALTED) return WCM_R4_HALTED_ERR;
  if(sync_time(c)!=WCM_R4_OK) return halt(c);
  /* Never sample across a pending physical-state discontinuity. */
  if(pending(c)) return WCM_R4_PENDING;
  return sample_energy(c);
}
wcm_r4_status_t wcm_r4_world_break(wcm_r4_cell_t *c) {
  if(!c) return WCM_R4_REJECT;
  if(c->mode==(uint8_t)WCM_R4_HALTED) return WCM_R4_HALTED_ERR;
  if(sync_time(c)!=WCM_R4_OK) return halt(c); /* cutover uses actual break time */
  return cut(c);
}
wcm_r4_status_t wcm_r4_init(wcm_r4_cell_t *c,const wcm_r4_port_t *p) {
  if(!c || !p || !p->clock_us || !p->energy_read || !p->power_good || !p->reflect_latch ||
     !p->aero_start || !p->safe || !p->authorize_local_policy || !p->guard_enter ||
     !p->guard_exit || !p->physical_quiescent) return WCM_R4_REJECT;
  wcm_zero(c,sizeof(*c));
  c->port=p;
  for(unsigned i=0u;i<WCM_R4_LANES;++i) {
    atomic_init(&c->ingress[i].head,0u);
    atomic_init(&c->ingress[i].tail,0u);
  }
  atomic_init(&c->irq_flags,0u);
  c->epoch=1u;c->mode=(uint8_t)WCM_R4_REBIND;c->shape=WCM_R4_AERO_UNKNOWN;
  c->shape_requested=WCM_R4_AERO_UNKNOWN;
  if(sync_time(c)!=WCM_R4_OK) return halt(c);
  c->cutover_us=c->now_us;
  if(!p->safe(p->user) || !p->physical_quiescent(p->user)) return halt(c);
  c->energy_reconcile_after_us=c->now_us;
  return WCM_R4_OK;
}
wcm_r4_status_t wcm_r4_capture(wcm_r4_cell_t *c,uint8_t lane,wcm_r4_capture_t s) {
  if(!c || lane>=WCM_R4_LANES) return WCM_R4_REJECT;
  wcm_r4_lane_t *q=&c->ingress[lane];
  unsigned int head=atomic_load_explicit(&q->head,memory_order_relaxed);
  unsigned int tail=atomic_load_explicit(&q->tail,memory_order_acquire);
  if(head-tail>=WCM_R4_QUEUE) {
    (void)atomic_fetch_or_explicit(&c->irq_flags,WCM_R4_IRQ_OVERFLOW,memory_order_release);
    return WCM_R4_OVERFLOW;
  }
  q->ring[head%WCM_R4_QUEUE]=s;
  atomic_store_explicit(&q->head,head+1u,memory_order_release);
  return WCM_R4_OK;
}
void wcm_r4_irq_post(wcm_r4_cell_t *c,unsigned int flags) {
  if(c) (void)atomic_fetch_or_explicit(&c->irq_flags,flags&WCM_R4_IRQ_ALL,memory_order_release);
}
static wcm_r4_status_t admit(wcm_r4_cell_t *c,uint8_t lane,const wcm_r4_capture_t *s) {
  if (s->ttl_us==0u || s->ttl_us>WCM_R4_TTL_MAX_US ||
      s->acquired_us<=c->cutover_us || s->acquired_us>c->now_us) return WCM_R4_STALE;
  wcm_r4_witness_t *w=&c->witness[lane];
  if(w->valid && s->acquired_us<w->acquired_us) return WCM_R4_STALE;
  if(w->generation==UINT16_MAX) { (void)cut(c);return WCM_R4_STALE; }
  ++w->generation;
  w->acquired_us=s->acquired_us;
  w->epoch=c->epoch;
  w->valid=0u;
  if(s->quality<WCM_R4_QMIN ||
     (lane==WCM_R4_LOCAL_POLICY && !c->port->authorize_local_policy(c->port->user,s)) ||
     (lane==WCM_R4_SENSOR && s->value>WCM_R4_SENSOR_MAX) ||
     (lane==WCM_R4_LOCAL_POLICY && s->value!=WCM_R4_ACTION_TX && s->value!=WCM_R4_ACTION_AERO))
       return WCM_R4_REJECT;
  w->value=s->value;w->ttl_us=s->ttl_us;w->quality=s->quality;w->valid=1u;
  if(!c->energy_quarantined &&
     (c->mode==(uint8_t)WCM_R4_REBIND || c->mode==(uint8_t)WCM_R4_DORMANT))
    c->mode=(uint8_t)WCM_R4_IDLE;
  return WCM_R4_OK;
}
wcm_r4_status_t wcm_r4_poll(wcm_r4_cell_t *c) {
  if(!c) return WCM_R4_REJECT;
  if(c->mode==(uint8_t)WCM_R4_HALTED) return WCM_R4_HALTED_ERR;
  if(sync_time(c)!=WCM_R4_OK) return halt(c);
  unsigned int flags=atomic_exchange_explicit(&c->irq_flags,0u,memory_order_acq_rel);
  if(flags) {
    wcm_r4_status_t r=cut(c);
    if(r!=WCM_R4_OK) return r;
    if(flags & WCM_R4_IRQ_OVERFLOW) return WCM_R4_OVERFLOW;
    return WCM_R4_REBIND_REQUIRED;
  }
  wcm_r4_status_t rc=WCM_R4_OK;
  /* Consume bounded FIFO: no producer writes a slot until tail releases it. */
  for(uint8_t lane=0u;lane<WCM_R4_LANES;++lane) {
    wcm_r4_lane_t *q=&c->ingress[lane];
    unsigned int tail=atomic_load_explicit(&q->tail,memory_order_relaxed);
    unsigned int head=atomic_load_explicit(&q->head,memory_order_acquire);
    while(tail!=head) {
      wcm_r4_capture_t s=q->ring[tail%WCM_R4_QUEUE];
      if(c->mode==(uint8_t)WCM_R4_TX || c->mode==(uint8_t)WCM_R4_AERO_PENDING) {
        wcm_r4_status_t br=cut(c);
        if(br!=WCM_R4_OK) return br;
      }
      wcm_r4_status_t r=admit(c,lane,&s);
      if(r!=WCM_R4_OK) rc=r;
      ++tail;
      atomic_store_explicit(&q->tail,tail,memory_order_release);
      /* Head was snapshotted on entering this lane: bounded per poll. */
    }
  }
  return rc;
}
static wcm_r4_status_t invalid_commit(wcm_r4_cell_t *c,wcm_r4_status_t r) {
  if(r==WCM_R4_PENDING) return r; /* caller must drain capture before reattempt */
  if(r==WCM_R4_TIME) return halt(c);
  if(r==WCM_R4_IO || r==WCM_R4_STALE) { (void)cut(c); return r; }
  return reject(c,r);
}
wcm_r4_status_t wcm_r4_tx_start(wcm_r4_cell_t *c,const uint8_t frame[4],uint32_t period_us) {
  if(!c || !frame || period_us==0u) return WCM_R4_REJECT;
  if(c->mode==(uint8_t)WCM_R4_HALTED) return WCM_R4_HALTED_ERR;
  if(c->mode==(uint8_t)WCM_R4_TX || c->mode==(uint8_t)WCM_R4_AERO_PENDING) return WCM_R4_BUSY;
  wcm_r4_status_t rc=sync_time(c);
  if(rc!=WCM_R4_OK) return halt(c);
  if(pending(c)) return WCM_R4_PENDING;
  const uint64_t duration=(uint64_t)WCM_R4_FRAME_BITS*(uint64_t)period_us+
                          WCM_R4_EFFECT_US+WCM_R4_SYMBOL_JITTER_US;
  if(UINT64_MAX-c->now_us<duration) { (void)cut(c); return WCM_R4_TIME; }
  const uint64_t horizon=c->now_us+duration;
  rc=gate_evidence(c,WCM_R4_ACTION_TX,horizon);
  if(rc!=WCM_R4_OK) return reject(c,rc);
  c->port->guard_enter(c->port->user);
  rc=sync_time(c);
  if(rc==WCM_R4_OK && UINT64_MAX-c->now_us<duration) rc=WCM_R4_TIME;
  if(rc==WCM_R4_OK) rc=guarded(c,WCM_R4_ACTION_TX,c->now_us+duration,WCM_R4_FRAME_NJ);
  if(rc==WCM_R4_OK) {
    for(unsigned k=0u;k<4u;++k) c->frame[k]=frame[k];
    c->tx_epoch=c->epoch;
    for(unsigned i=0u;i<WCM_R4_LANES;++i) c->tx_generation[i]=c->witness[i].generation;
    c->energy_credit_nj-=WCM_R4_FRAME_INIT_NJ;
    c->energy_reconcile_after_us=c->now_us;
    c->tx_remain_nj=(uint16_t)(WCM_R4_SYMBOL_NJ*WCM_R4_FRAME_BITS);
    c->tx_index=0u;c->tx_period_us=period_us;c->next_symbol_us=c->now_us;
    c->mode=(uint8_t)WCM_R4_TX;
  }
  c->port->guard_exit(c->port->user);
  if(rc==WCM_R4_NO_ENERGY) c->mode=(uint8_t)WCM_R4_DORMANT;
  return rc==WCM_R4_OK?rc:invalid_commit(c,rc);
}
wcm_r4_status_t wcm_r4_tx_step(wcm_r4_cell_t *c) {
  if(!c) return WCM_R4_REJECT;
  if(c->mode==(uint8_t)WCM_R4_HALTED) return WCM_R4_HALTED_ERR;
  if(c->mode!=(uint8_t)WCM_R4_TX) return WCM_R4_REJECT;
  c->port->guard_enter(c->port->user);
  wcm_r4_status_t rc=sync_time(c);
  const bool clock_ok=(rc==WCM_R4_OK);
  if(rc==WCM_R4_OK && c->now_us<c->next_symbol_us) rc=WCM_R4_PENDING;
  if(rc==WCM_R4_OK && c->now_us-c->next_symbol_us>WCM_R4_SYMBOL_JITTER_US) rc=WCM_R4_TIME;
  if(rc==WCM_R4_OK && pending(c)) rc=WCM_R4_PENDING;
  if(rc==WCM_R4_OK && c->tx_index==WCM_R4_FRAME_BITS) {
    /* The complete last symbol aperture has elapsed. */
    if(!c->port->safe(c->port->user)) rc=WCM_R4_IO;
    else {
      c->energy_reconcile_after_us=c->now_us;
      c->reflect_level=0u;c->tx_remain_nj=0u;c->mode=(uint8_t)WCM_R4_IDLE;
    }
  } else if(rc==WCM_R4_OK) {
    if(c->now_us>UINT64_MAX-WCM_R4_EFFECT_US) rc=WCM_R4_TIME;
    else rc=guarded(c,WCM_R4_ACTION_TX,c->now_us+WCM_R4_EFFECT_US,c->tx_remain_nj);
    if(rc==WCM_R4_OK && (c->epoch!=c->tx_epoch ||
        c->witness[0].generation!=c->tx_generation[0] ||
        c->witness[1].generation!=c->tx_generation[1])) rc=WCM_R4_STALE;
    if(rc==WCM_R4_OK) {
      uint8_t bit=(uint8_t)((c->frame[c->tx_index/8u]>>(7u-(c->tx_index%8u)))&1u);
      if(!c->port->reflect_latch(c->port->user,bit)) {
        c->energy_quarantined=1u; c->energy_credit_nj=0u;
        rc=WCM_R4_IO;
      }
      else {
        c->energy_credit_nj-=WCM_R4_SYMBOL_NJ;
        c->energy_reconcile_after_us=c->now_us;
        c->tx_remain_nj=(uint16_t)(c->tx_remain_nj-WCM_R4_SYMBOL_NJ);
        c->reflect_level=bit;
        ++c->tx_index;
        if(c->dispatch_count<UINT16_MAX) ++c->dispatch_count;
        c->next_symbol_us+=(uint64_t)c->tx_period_us;
      }
    }
  }
  c->port->guard_exit(c->port->user);
  if(rc!=WCM_R4_OK) {
    if(rc==WCM_R4_PENDING) return rc;
    if(!clock_ok) return halt(c);
    (void)cut(c);return rc;
  }
  return WCM_R4_OK;
}
wcm_r4_status_t wcm_r4_aero_start(wcm_r4_cell_t *c,uint8_t shape,uint32_t wait_us,uint32_t *out_token) {
  if(!c || !out_token || shape>1u || wait_us==0u || wait_us>WCM_R4_MAX_AERO_WAIT_US) return WCM_R4_REJECT;
  if(c->mode==(uint8_t)WCM_R4_HALTED) return WCM_R4_HALTED_ERR;
  if(c->mode==(uint8_t)WCM_R4_TX || c->mode==(uint8_t)WCM_R4_AERO_PENDING) return WCM_R4_BUSY;
  wcm_r4_status_t rc=sync_time(c);
  if(rc!=WCM_R4_OK) return halt(c);
  if(pending(c)) return WCM_R4_PENDING;
  if(UINT64_MAX-c->now_us<(uint64_t)wait_us+WCM_R4_EFFECT_US) { (void)cut(c);return WCM_R4_TIME; }
  rc=gate_evidence(c,WCM_R4_ACTION_AERO,c->now_us+(uint64_t)wait_us+WCM_R4_EFFECT_US);
  if(rc!=WCM_R4_OK) return reject(c,rc);
  c->port->guard_enter(c->port->user);
  rc=sync_time(c);
  if(rc==WCM_R4_OK) {
    if(UINT64_MAX-c->now_us<(uint64_t)wait_us+WCM_R4_EFFECT_US) rc=WCM_R4_TIME;
    else rc=guarded(c,WCM_R4_ACTION_AERO,c->now_us+(uint64_t)wait_us+WCM_R4_EFFECT_US,WCM_R4_AERO_NJ);
  }
  if(rc==WCM_R4_OK && c->aero_token==UINT32_MAX) rc=WCM_R4_STALE;
  if(rc==WCM_R4_OK && !c->port->aero_start(c->port->user,shape)) {
    c->energy_quarantined=1u; c->energy_credit_nj=0u;
    rc=WCM_R4_IO;
  }
  if(rc==WCM_R4_OK) {
    c->energy_credit_nj-=WCM_R4_AERO_NJ;
    c->energy_reconcile_after_us=c->now_us;
    c->shape_requested=shape;c->shape=WCM_R4_AERO_UNKNOWN;
    c->aero_started_us=c->now_us;c->aero_deadline_us=c->now_us+(uint64_t)wait_us;
    ++c->aero_token; *out_token=c->aero_token;
    c->mode=(uint8_t)WCM_R4_AERO_PENDING;
  }
  c->port->guard_exit(c->port->user);
  if(rc==WCM_R4_NO_ENERGY) c->mode=(uint8_t)WCM_R4_DORMANT;
  return rc==WCM_R4_OK?rc:invalid_commit(c,rc);
}
wcm_r4_status_t wcm_r4_aero_complete(wcm_r4_cell_t *c,uint32_t token,uint64_t feedback_at,bool confirmed) {
  if(!c) return WCM_R4_REJECT;
  if(c->mode==(uint8_t)WCM_R4_HALTED) return WCM_R4_HALTED_ERR;
  if(c->mode!=(uint8_t)WCM_R4_AERO_PENDING) return WCM_R4_REJECT;
  c->port->guard_enter(c->port->user);
  wcm_r4_status_t rc=sync_time(c);
  if(rc==WCM_R4_OK && pending(c)) rc=WCM_R4_PENDING;
  if(rc==WCM_R4_OK && (token!=c->aero_token ||
      feedback_at<=c->aero_started_us || feedback_at>c->now_us ||
      feedback_at>c->aero_deadline_us)) rc=WCM_R4_STALE;
  if(rc==WCM_R4_OK && c->now_us>c->aero_deadline_us) rc=WCM_R4_TIME;
  if(rc==WCM_R4_OK && !confirmed) rc=WCM_R4_IO;
  if(rc==WCM_R4_OK) {
    /* Trusted feedback source must be qualified by the hardware integration. */
    c->shape=c->shape_requested;c->mode=(uint8_t)WCM_R4_IDLE;
    if(feedback_at>c->energy_reconcile_after_us) c->energy_reconcile_after_us=feedback_at;
  }
  c->port->guard_exit(c->port->user);
  if(rc==WCM_R4_TIME && (c->now_us>c->aero_deadline_us)) { (void)cut(c);return rc; }
  if(rc==WCM_R4_TIME) return halt(c);
  if(rc==WCM_R4_IO) { (void)cut(c);return rc; }
  return rc;
}
wcm_r4_status_t wcm_r4_watchdog(wcm_r4_cell_t *c) {
  if(!c) return WCM_R4_REJECT;
  if(c->mode==(uint8_t)WCM_R4_HALTED) return WCM_R4_HALTED_ERR;
  if(sync_time(c)!=WCM_R4_OK) return halt(c);
  if(c->mode==(uint8_t)WCM_R4_AERO_PENDING && c->now_us>c->aero_deadline_us) {
    (void)cut(c);return WCM_R4_TIME;
  }
  if(c->mode==(uint8_t)WCM_R4_TX && c->now_us>c->next_symbol_us &&
     c->now_us-c->next_symbol_us>WCM_R4_SYMBOL_JITTER_US) {
    (void)cut(c);return WCM_R4_TIME;
  }
  return WCM_R4_OK;
}
