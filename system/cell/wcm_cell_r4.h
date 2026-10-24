/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
#ifndef WCM_CELL_R4_H
#define WCM_CELL_R4_H
/* WCM-Cell R4 reference controller.
 * Executor owns all APIs except wcm_capture() and wcm_irq_post().
 * One producer per capture lane; callbacks remain nonblocking.
 */
#include <stdint.h>
#include <stdbool.h>
#include <stdatomic.h>

#if ATOMIC_INT_LOCK_FREE != 2
#error "Target requires a qualified lock-free unsigned-int atomic or separate IRQ-mask mailbox port"
#endif
#define WCM_R4_LANES 2u
#define WCM_R4_QUEUE 2u
#define WCM_R4_SENSOR 0u
#define WCM_R4_LOCAL_POLICY 1u /* internally derived from preprovisioned mission; never radio RX */
#define WCM_R4_ACTION_TX 1u
#define WCM_R4_ACTION_AERO 2u
#define WCM_R4_AERO_UNKNOWN 2u
#define WCM_R4_QMIN 160u
#define WCM_R4_SENSOR_MAX 800u
#define WCM_R4_TTL_MAX_US 1000000u
#define WCM_R4_ENERGY_MAX_NJ 100000u
/* Reference energy budgets; calibrate for the selected hardware target. */
#define WCM_R4_HARD_RESERVE_NJ 150u
#define WCM_R4_FRAME_INIT_NJ 40u
#define WCM_R4_SYMBOL_NJ 30u
#define WCM_R4_FRAME_BITS 32u
#define WCM_R4_FRAME_NJ (WCM_R4_FRAME_INIT_NJ + WCM_R4_SYMBOL_NJ * WCM_R4_FRAME_BITS)
#define WCM_R4_AERO_NJ 2000u
#define WCM_R4_EFFECT_US 200u
#define WCM_R4_SYMBOL_JITTER_US 100u
#define WCM_R4_MAX_AERO_WAIT_US 100000u
#define WCM_R4_ENERGY_SAMPLE_MAX_AGE_US 5000u
#define WCM_R4_IRQ_FAULT (1u << 0)
#define WCM_R4_IRQ_BROWNOUT (1u << 1)
#define WCM_R4_IRQ_OVERFLOW (1u << 2)
#define WCM_R4_IRQ_ALL (WCM_R4_IRQ_FAULT | WCM_R4_IRQ_BROWNOUT | WCM_R4_IRQ_OVERFLOW)

typedef enum {
  WCM_R4_OK=0, WCM_R4_REJECT=-1, WCM_R4_REBIND_REQUIRED=-2,
  WCM_R4_EXPIRED=-3, WCM_R4_NO_ENERGY=-4, WCM_R4_BUSY=-5,
  WCM_R4_TIME=-6, WCM_R4_IO=-7, WCM_R4_HALTED_ERR=-8,
  WCM_R4_PENDING=-9, WCM_R4_STALE=-10, WCM_R4_OVERFLOW=-11
} wcm_r4_status_t;
typedef enum {
  WCM_R4_REBIND=0, WCM_R4_IDLE=1, WCM_R4_TX=2,
  WCM_R4_AERO_PENDING=3, WCM_R4_DORMANT=4, WCM_R4_HALTED=5
} wcm_r4_mode_t;

typedef struct {
  uint64_t acquired_us;
  uint32_t ttl_us;
  uint16_t value;
  uint8_t quality;
  uint8_t _padding;
} wcm_r4_capture_t;

typedef struct {
  wcm_r4_capture_t ring[WCM_R4_QUEUE];
  _Atomic unsigned int head;
  _Atomic unsigned int tail;
} wcm_r4_lane_t;

typedef struct {
  uint64_t acquired_us;
  uint32_t epoch;
  uint32_t ttl_us;
  uint16_t generation;
  uint16_t value;
  uint8_t quality;
  uint8_t valid;
} wcm_r4_witness_t;

typedef struct {
  uint64_t acquired_us;
  uint32_t sequence; /* new conservative measurement must increase without wrap */
  uint32_t available_nj; /* lower-bound energy AFTER physical expenditures */
} wcm_r4_energy_sample_t;

typedef struct {
  bool (*clock_us)(void *user, uint64_t *now_us);
  bool (*energy_read)(void *user, wcm_r4_energy_sample_t *sample);
  bool (*power_good)(void *user);
  bool (*reflect_latch)(void *user, uint8_t bit);
  bool (*aero_start)(void *user, uint8_t shape);
  bool (*safe)(void *user); /* requests safe output; physical state is confirmed separately */
  bool (*authorize_local_policy)(void *user, const wcm_r4_capture_t *sample); /* authority derived from the provisioned local mission */
  void (*guard_enter)(void *user); /* prohibits lane/IRQ publication during guard */
  void (*guard_exit)(void *user);
  void *user;
  bool (*physical_quiescent)(void *user); /* target-qualified: no outstanding commanded motion */
} wcm_r4_port_t;

typedef struct {
  wcm_r4_lane_t ingress[WCM_R4_LANES];
  wcm_r4_witness_t witness[WCM_R4_LANES];
  const wcm_r4_port_t *port; /* immutable port table, may reside in ROM */
  _Atomic unsigned int irq_flags;
  uint64_t now_us;
  uint64_t cutover_us;
  uint64_t last_energy_acquired_us;
  uint64_t energy_reconcile_after_us; /* conservative physical completion watermark */
  uint64_t next_symbol_us;
  uint64_t aero_started_us;
  uint64_t aero_deadline_us;
  uint32_t epoch;
  uint32_t energy_credit_nj; /* never increases while a transaction is outstanding */
  uint32_t last_energy_seq;
  uint32_t energy_reconcile_count;
  uint32_t aero_token;
  uint16_t tx_generation[WCM_R4_LANES];
  uint16_t tx_remain_nj;
  uint16_t deny_count;
  uint16_t break_count;
  uint16_t dispatch_count;
  uint32_t tx_epoch;
  uint32_t tx_period_us;
  uint8_t frame[4];
  uint8_t tx_index;
  uint8_t mode;
  uint8_t shape;
  uint8_t shape_requested;
  uint8_t reflect_level;
  uint8_t energy_quarantined; /* pending actuation interrupted: require physical settlement */
} wcm_r4_cell_t;

/* Initializes and requests safe output. First observations must be after cutover. */
wcm_r4_status_t wcm_r4_init(wcm_r4_cell_t *c, const wcm_r4_port_t *port);
/* Single-producer-per-lane SPSC, safe against executor consumption; never blocks. */
wcm_r4_status_t wcm_r4_capture(wcm_r4_cell_t *c, uint8_t lane, wcm_r4_capture_t sample);
void wcm_r4_irq_post(wcm_r4_cell_t *c, unsigned int flags);
/* Drain input + faults. Call before deciding to commit, and after wakeup. */
wcm_r4_status_t wcm_r4_poll(wcm_r4_cell_t *c);
wcm_r4_status_t wcm_r4_world_break(wcm_r4_cell_t *c);
/* Following interrupted physical work, re-credit only after qualified quiescence. */
wcm_r4_status_t wcm_r4_settled(wcm_r4_cell_t *c);
/* Executor only: update energy lower bound, never recredit in-flight actions. */
wcm_r4_status_t wcm_r4_energy_refresh(wcm_r4_cell_t *c);
wcm_r4_status_t wcm_r4_tx_start(wcm_r4_cell_t *c, const uint8_t frame[4], uint32_t period_us);
wcm_r4_status_t wcm_r4_tx_step(wcm_r4_cell_t *c);
wcm_r4_status_t wcm_r4_aero_start(wcm_r4_cell_t *c, uint8_t shape, uint32_t wait_us, uint32_t *out_token);
/* Feedback must be acquired after dispatch and before deadline, and match token. */
wcm_r4_status_t wcm_r4_aero_complete(wcm_r4_cell_t *c, uint32_t token, uint64_t feedback_acquired_us, bool confirmed);
wcm_r4_status_t wcm_r4_watchdog(wcm_r4_cell_t *c);
#endif
