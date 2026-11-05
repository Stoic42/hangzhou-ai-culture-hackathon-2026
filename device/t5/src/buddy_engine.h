/**
 * @file buddy_engine.h
 * @brief Rule pack v1 (BuddyManifest) parser, validator and game session.
 *
 * Mirrors shared/tools/validate_buddies.py: closed whitelists for events,
 * actions and enums; duration 60-90s; both outcomes; graph reachability.
 * A session is a plain single-threaded state machine; no dynamic code.
 */
#ifndef BUDDY_ENGINE_H
#define BUDDY_ENGINE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BUDDY_MAX_NODES 16
#define BUDDY_MAX_TRANSITIONS 8
#define BUDDY_MAX_ACTIONS 6
#define BUDDY_MAX_VARS 4
#define BUDDY_MAX_RESOURCES 4
#define BUDDY_MAX_TAGS 4
#define BUDDY_MAX_PALETTE 4
#define BUDDY_ERR_LEN 96

typedef enum {
    BUDDY_EVENT_GAME_START = 0,
    BUDDY_EVENT_TAP,
    BUDDY_EVENT_LONG_PRESS,
    BUDDY_EVENT_SWIPE,
    BUDDY_EVENT_TIMER,
    BUDDY_EVENT_COUNT
} buddy_event_t;

typedef enum {
    BUDDY_OP_EXPRESSION = 0,
    BUDDY_OP_MOTION,
    BUDDY_OP_AUDIO_PLAY,
    BUDDY_OP_TIMER_START,
    BUDDY_OP_VAR_SET,
    BUDDY_OP_VAR_INCREMENT,
    BUDDY_OP_GAME_END,
    BUDDY_OP_COUNT
} buddy_op_t;

typedef enum {
    BUDDY_CMP_EQ = 0,
    BUDDY_CMP_NEQ,
    BUDDY_CMP_GT,
    BUDDY_CMP_GTE,
    BUDDY_CMP_LT,
    BUDDY_CMP_LTE
} buddy_cmp_t;

typedef enum {
    BUDDY_OUTCOME_NONE = 0,
    BUDDY_OUTCOME_ESCAPED,
    BUDDY_OUTCOME_CARRIED_AWAY
} buddy_outcome_t;

/* closed enums (indices match shared whitelist order) */
typedef enum { BUDDY_FACE_ROUND = 0, BUDDY_FACE_SQUARE, BUDDY_FACE_BEAN } buddy_face_t;
typedef enum { BUDDY_EYES_SLEEPY = 0, BUDDY_EYES_WIDE, BUDDY_EYES_SIDE, BUDDY_EYES_DOT } buddy_eyes_t;
typedef enum { BUDDY_MOUTH_SMALL = 0, BUDDY_MOUTH_GRIN, BUDDY_MOUTH_FLAT, BUDDY_MOUTH_OPEN } buddy_mouth_t;
typedef enum { BUDDY_MSTYLE_DROWSY = 0, BUDDY_MSTYLE_JITTERY, BUDDY_MSTYLE_STILL, BUDDY_MSTYLE_BOUNCY } buddy_motion_style_t;
typedef enum { BUDDY_EXPR_NEUTRAL = 0, BUDDY_EXPR_PLEADING, BUDDY_EXPR_HAPPY, BUDDY_EXPR_SMUG,
               BUDDY_EXPR_ANXIOUS, BUDDY_EXPR_SLEEPY, BUDDY_EXPR_ANGRY } buddy_expression_t;
typedef enum { BUDDY_MOTION_STILL = 0, BUDDY_MOTION_BREATHE, BUDDY_MOTION_SHAKE,
               BUDDY_MOTION_BOUNCE, BUDDY_MOTION_NOD } buddy_motion_t;

typedef struct {
    bool is_remaining;      /**< left is remaining_sec instead of a variable */
    int8_t var;             /**< variable index, -1 when is_remaining */
    buddy_cmp_t op;
    int right;              /**< integer constant */
} buddy_condition_t;

typedef struct {
    buddy_op_t op;
    buddy_expression_t expr;    /**< BUDDY_OP_EXPRESSION */
    buddy_motion_t motion;      /**< BUDDY_OP_MOTION */
    int8_t var;                 /**< BUDDY_OP_VAR_SET / BUDDY_OP_VAR_INCREMENT */
    int int_value;              /**< BUDDY_OP_VAR_SET / BUDDY_OP_VAR_INCREMENT value, or timer seconds */
    buddy_outcome_t outcome;    /**< BUDDY_OP_GAME_END */
    const char *resource_id;    /**< BUDDY_OP_AUDIO_PLAY (points into cJSON tree) */
} buddy_action_t;

typedef struct {
    buddy_event_t event;
    bool has_condition;
    buddy_condition_t condition;
    int8_t to;              /**< target node index */
    buddy_action_t actions[BUDDY_MAX_ACTIONS];
    uint8_t action_count;
} buddy_transition_t;

typedef struct {
    const char *id;
    const char *title;
    const char *instruction;
    buddy_action_t on_enter[BUDDY_MAX_ACTIONS];
    uint8_t on_enter_count;
    buddy_transition_t transitions[BUDDY_MAX_TRANSITIONS];
    uint8_t transition_count;
} buddy_node_t;

typedef struct {
    const char *resource_id;
    const char *url;
    uint8_t sha256[32];
    uint32_t size;
} buddy_resource_t;

typedef struct {
    /* identity & content */
    const char *buddy_id;
    const char *name;
    const char *personality;
    const char *gameplay_summary;
    const char *tags[BUDDY_MAX_TAGS];
    uint8_t tag_count;
    /* avatar */
    buddy_face_t face;
    buddy_eyes_t eyes;
    buddy_mouth_t mouth;
    buddy_motion_style_t motion_style;
    uint32_t palette[BUDDY_MAX_PALETTE];   /**< 0xRRGGBB */
    uint8_t palette_count;
    /* game */
    int duration_sec;
    int8_t initial_node;
    struct {
        const char *name;
        int initial;
    } vars[BUDDY_MAX_VARS];
    uint8_t var_count;
    buddy_node_t nodes[BUDDY_MAX_NODES];
    uint8_t node_count;
    buddy_resource_t resources[BUDDY_MAX_RESOURCES];
    uint8_t resource_count;
} buddy_t;

/** Parse and validate a rule pack. On success returns true and fills `out`;
 * the cJSON tree is retained internally for the lifetime of `out`.
 * On failure returns false and writes a short reason into `err`. */
bool buddy_parse(const char *json, uint32_t json_len, buddy_t *out, char *err);

/** Look up a node index by id, -1 when absent. */
int8_t buddy_find_node(const buddy_t *buddy, const char *node_id);

/** Look up a variable index by name, -1 when absent. */
int8_t buddy_find_var(const buddy_t *buddy, const char *name);

/** Per-session runtime state; reconstructed on every new game. */
typedef struct {
    const buddy_t *buddy;
    int8_t current_node;
    int var_values[BUDDY_MAX_VARS];
    int remaining_sec;
    buddy_outcome_t outcome;        /**< BUDDY_OUTCOME_NONE while playing */
    buddy_expression_t expression;
    buddy_motion_t motion;
} buddy_session_t;

typedef struct {
    /** Audio sink: play a builtin resource by id. Returns false when the
     * resource is missing or its size/sha256 does not match the manifest. */
    bool (*play_resource)(const char *resource_id);
    /** Optional log hook for state transitions (no user data). */
    void (*on_transition)(const buddy_t *buddy, const char *from_id, const char *to_id, buddy_event_t event);
} buddy_session_ops_t;

/** Create a fresh session at the initial node. */
void buddy_session_start(buddy_session_t *session, const buddy_t *buddy);

/** Feed an event (tap/long_press/swipe/timer tick). Timer events are handled
 * before touch events by the caller. When the global countdown reaches 0 the
 * session is forced into the carried_away ending regardless of rules.
 * Returns true when the node changed or the session ended. */
bool buddy_session_handle(buddy_session_t *session, buddy_event_t event,
                          const buddy_session_ops_t *ops);

#ifdef __cplusplus
}
#endif

#endif /* BUDDY_ENGINE_H */
