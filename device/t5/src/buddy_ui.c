/**
 * @file buddy_ui.c
 * @brief Offline preset buddy device UI: home carousel, detail, generate
 * offline notice, and the rule-pack driven game page.
 */
#include "buddy_ui.h"

#include <stdio.h>
#include <string.h>

#include "board_com_api.h"
#include "lv_vendor.h"
#include "lvgl.h"
/* SDK-private indev struct: LVGL v9 exposes no public setter for
 * gesture_limit / gesture_min_velocity, so tune them in-place. */
#include "src/indev/lv_indev_private.h"
#include "tal_api.h"
#include "tal_hash.h"
#include "tdl_audio_manage.h"
#include "tkl_audio.h"
#include "tkl_output.h"

#include "buddy_engine.h"
#include "builtin_assets.h"
#include "ui_text.h"

LV_FONT_DECLARE(buddy_font);

/* 466x466 round panel: every coordinate below is checked against the circle
 * (center 233,233, r 233). Chord half-width at y is sqrt(233^2 - (y-233)^2). */
#define SCREEN_SIZE 466
#define SCREEN_RADIUS 233

#define PRESET_COUNT_MAX 4
#define COLOR_BG 0x0A0E17        /**< deep dark pixel-night background */
#define COLOR_TEXT 0xF2F4F7
#define COLOR_TEXT_DIM 0x98A2B3
#define COLOR_ACCENT 0xA3E635    /**< saturated lime */
#define COLOR_DANGER 0xFF3B30    /**< saturated red */
#define COLOR_PANEL 0x151B2C
#define AVATAR_SIZE 160          /**< pixel monster body, multiple of 8 */

typedef struct {
    buddy_t buddy;
    bool parsed;
    bool resources_ok;
    char err[BUDDY_ERR_LEN];
} preset_slot_t;

static preset_slot_t s_presets[PRESET_COUNT_MAX];
static uint8_t s_preset_count;
static uint8_t s_selected;          /**< home selection, kept across detail */
static TDL_AUDIO_HANDLE_T s_audio;

/* home widgets */
static lv_obj_t *s_card;
static lv_obj_t *s_current_screen;  /**< live screen; replaced atomically on nav */
static lv_obj_t *s_label_name;
static lv_obj_t *s_label_personality;
static lv_obj_t *s_label_tag;
static lv_obj_t *s_label_index;
static lv_obj_t *s_avatar_root;

/* game widgets */
static lv_obj_t *s_game_area;
static lv_obj_t *s_label_timer;
static lv_obj_t *s_label_title;
static lv_obj_t *s_label_instruction;
static lv_obj_t *s_end_panel;
static lv_obj_t *s_label_outcome;
static lv_timer_t *s_game_timer;
static lv_timer_t *s_motion_timer;
static buddy_session_t s_session;
static bool s_session_active;

/* avatar parts */
static lv_obj_t *s_avatar_face;
static lv_obj_t *s_avatar_eye_l;
static lv_obj_t *s_avatar_eye_r;
static lv_obj_t *s_avatar_mouth;
static lv_obj_t *s_avatar_step[4];   /**< bg-colored corner blocks: stair-step silhouette */
static lv_obj_t *s_avatar_tooth[2];  /**< white pixel teeth, grin only */
static buddy_motion_t s_avatar_motion = BUDDY_MOTION_STILL;
static buddy_motion_style_t s_avatar_mstyle = BUDDY_MSTYLE_STILL;
static int16_t s_avatar_base_x;
static int16_t s_avatar_base_y;
static uint32_t s_motion_tick;

static void show_home(void);
static void show_home_refresh(void);
static void show_game(uint8_t preset_index);
static void show_detail_screen(uint8_t preset_index);
static void back_to_home_cb(lv_event_t *event);
static void game_refresh_node(void);

/** Load a new screen and free the previous one after it is no longer displayed. */
static void nav_load(lv_obj_t *new_screen)
{
    lv_obj_t *old = s_current_screen;
    /* Screens without an avatar (detail/generate) leave the global avatar
     * pointers referencing objects owned by the screen about to be deleted.
     * Clear them first so the motion timer never touches freed objects; the
     * old screen is still alive here, so the screen lookup is safe. Screens
     * with an avatar (home/game) already reassigned the pointers to the new
     * screen before this helper runs, so the lookup keeps them untouched. */
    if (old != NULL && old != new_screen && s_avatar_face != NULL &&
        lv_obj_get_screen(s_avatar_face) == old) {
        s_avatar_root = NULL;
        s_avatar_face = NULL;
        s_avatar_eye_l = NULL;
        s_avatar_eye_r = NULL;
        s_avatar_mouth = NULL;
    }
    lv_screen_load(new_screen);
    s_current_screen = new_screen;
    if (old != NULL && old != new_screen) {
        lv_obj_del(old);
    }
}

/* ------------------------------------------------------------------ */
/* resources & audio                                                   */
/* ------------------------------------------------------------------ */

static bool sha256_hex_of(const uint8_t *data, size_t len, char hex_out[65])
{
    uint8_t digest[32];
    if (tal_sha256_ret(data, len, digest, 0) != OPRT_OK) {
        return false;
    }
    for (int i = 0; i < 32; i++) {
        snprintf(hex_out + i * 2, 3, "%02x", digest[i]);
    }
    hex_out[64] = '\0';
    return true;
}

/** Firmware builtin resource table digest, computed once at boot. */
static uint8_t s_feedback_digest[32];
static bool s_feedback_digest_ok;

static void builtin_resource_digest_init(void)
{
    s_feedback_digest_ok = false;
    if (BUDDY_FEEDBACK_PCM_SIZE != 3200) {
        PR_ERR("buddy: builtin pcm size mismatch");
        return;
    }
    char hex[65];
    if (!sha256_hex_of(BUDDY_FEEDBACK_PCM, BUDDY_FEEDBACK_PCM_SIZE, hex)) {
        PR_ERR("buddy: sha256 of builtin pcm failed");
        return;
    }
    if (strcmp(hex, BUDDY_FEEDBACK_SHA256) != 0) {
        PR_ERR("buddy: builtin pcm sha256 mismatch");
        return;
    }
    /* recover raw digest bytes for per-resource comparison */
    for (int i = 0; i < 32; i++) {
        unsigned int byte = 0;
        if (sscanf(BUDDY_FEEDBACK_SHA256 + i * 2, "%2x", &byte) != 1) {
            PR_ERR("buddy: firmware sha256 table unparsable");
            return;
        }
        s_feedback_digest[i] = (uint8_t)byte;
    }
    s_feedback_digest_ok = true;
}

/**
 * Check every resource declared by a manifest against the firmware builtin
 * table before a game may start. Offline feature: https:// resources count
 * as unavailable; any missing builtin entry or size/sha mismatch fails.
 */
static bool validate_preset_resources(const buddy_t *buddy)
{
    if (!s_feedback_digest_ok) {
        PR_ERR("buddy: firmware resource table invalid");
        return false;
    }
    for (int i = 0; i < buddy->resource_count; i++) {
        const buddy_resource_t *res = &buddy->resources[i];
        if (strncmp(res->url, "https://", 8) == 0) {
            PR_ERR("buddy: resource %s is remote, unavailable offline", res->resource_id);
            return false;
        }
        if (strncmp(res->url, "builtin://", 10) != 0) {
            PR_ERR("buddy: resource %s url scheme unsupported", res->resource_id);
            return false;
        }
        if (strcmp(res->resource_id, "feedback") != 0 ||
            strcmp(res->url, "builtin://feedback") != 0) {
            PR_ERR("buddy: resource %s missing from firmware table", res->resource_id);
            return false;
        }
        if (res->size != BUDDY_FEEDBACK_PCM_SIZE ||
            memcmp(res->sha256, s_feedback_digest, 32) != 0) {
            PR_ERR("buddy: resource %s size/sha256 mismatch with firmware table", res->resource_id);
            return false;
        }
    }
    return true;
}

static void play_feedback_pcm(void)
{
    TKL_AUDIO_FRAME_INFO_T frame = {.pbuf = (char *)BUDDY_FEEDBACK_PCM};
    frame.used_size = BUDDY_FEEDBACK_PCM_SIZE;
    tkl_ao_put_frame(0, 0, NULL, &frame);
}

/** Session audio sink: only resources already validated at startup may play. */
static bool play_resource(const char *resource_id)
{
    const buddy_t *buddy = s_session.buddy;
    for (int i = 0; i < buddy->resource_count; i++) {
        const buddy_resource_t *res = &buddy->resources[i];
        if (strcmp(res->resource_id, resource_id) != 0) {
            continue;
        }
        if (!s_feedback_digest_ok || res->size != BUDDY_FEEDBACK_PCM_SIZE ||
            memcmp(res->sha256, s_feedback_digest, 32) != 0) {
            PR_ERR("buddy: resource %s failed firmware table check", resource_id);
            return false;
        }
        play_feedback_pcm();
        return true;
    }
    PR_ERR("buddy: resource %s missing", resource_id);
    return false;
}

static void on_transition(const buddy_t *buddy, const char *from_id, const char *to_id,
                          buddy_event_t event)
{
    PR_NOTICE("buddy %s: %s -> %s (event %d)", buddy->buddy_id, from_id, to_id, (int)event);
}

static const buddy_session_ops_t SESSION_OPS = {
    .play_resource = play_resource,
    .on_transition = on_transition,
};

/* ------------------------------------------------------------------ */
/* avatar                                                              */
/* ------------------------------------------------------------------ */

static lv_color_t palette_color(const buddy_t *buddy, uint8_t index)
{
    uint32_t rgb = buddy->palette[index % buddy->palette_count];
    return lv_color_hex(rgb);
}

/** Rebuild face/eyes/mouth from avatar definition plus expression.
 * Pixel-monster style: every part is an axis-aligned block (radius 0), all
 * sizes are multiples of 2 so edges stay crisp and "chunky"; the round face
 * gets bg-colored corner blocks for a stair-step silhouette, and the grin
 * gets white pixel teeth. Expression overrides come from the engine. */
static void avatar_apply(const buddy_t *buddy, buddy_expression_t expr)
{
    buddy_eyes_t eyes = buddy->eyes;
    buddy_mouth_t mouth = buddy->mouth;
    lv_color_t accent = palette_color(buddy, 1);
    lv_color_t face_color = palette_color(buddy, 0);
    bool stepped = false;

    switch (expr) {
    case BUDDY_EXPR_HAPPY:
        mouth = BUDDY_MOUTH_GRIN;
        eyes = BUDDY_EYES_WIDE;
        break;
    case BUDDY_EXPR_SMUG:
        mouth = BUDDY_MOUTH_FLAT;
        eyes = BUDDY_EYES_SIDE;
        break;
    case BUDDY_EXPR_ANXIOUS:
        mouth = BUDDY_MOUTH_SMALL;
        eyes = BUDDY_EYES_WIDE;
        break;
    case BUDDY_EXPR_SLEEPY:
        mouth = BUDDY_MOUTH_SMALL;
        eyes = BUDDY_EYES_SLEEPY;
        break;
    case BUDDY_EXPR_ANGRY:
        mouth = BUDDY_MOUTH_FLAT;
        eyes = BUDDY_EYES_SLEEPY;
        face_color = lv_color_hex(0xB3261E);   /**< saturated angry flush */
        break;
    case BUDDY_EXPR_PLEADING:
        mouth = BUDDY_MOUTH_OPEN;
        eyes = BUDDY_EYES_WIDE;
        break;
    default:
        break;
    }

    /* face: all pixel-block, radius 0. ROUND = square with stair-step corners,
     * SQUARE = plain square, BEAN = wide flat rectangle: three clearly
     * different silhouettes on top of each preset's own palette. */
    lv_obj_set_size(s_avatar_face, AVATAR_SIZE, AVATAR_SIZE);
    lv_obj_set_style_radius(s_avatar_face, 0, LV_PART_MAIN);
    switch (buddy->face) {
    case BUDDY_FACE_ROUND:
        stepped = true;
        break;
    case BUDDY_FACE_SQUARE:
        break;
    case BUDDY_FACE_BEAN:
        lv_obj_set_height(s_avatar_face, AVATAR_SIZE - 32);
        break;
    default:
        break;
    }
    lv_obj_set_style_bg_color(s_avatar_face, face_color, LV_PART_MAIN);
    lv_obj_set_style_border_width(s_avatar_face, 6, LV_PART_MAIN);
    lv_obj_set_style_border_color(s_avatar_face, accent, LV_PART_MAIN);
    lv_obj_set_style_border_opa(s_avatar_face, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_center(s_avatar_face);

    /* stair-step corners: 24px bg-colored blocks carve the square silhouette */
    const int16_t step = 24;
    lv_obj_set_size(s_avatar_step[0], step, step);
    lv_obj_set_size(s_avatar_step[1], step, step);
    lv_obj_set_size(s_avatar_step[2], step, step);
    lv_obj_set_size(s_avatar_step[3], step, step);
    lv_obj_align(s_avatar_step[0], LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_align(s_avatar_step[1], LV_ALIGN_TOP_RIGHT, 0, 0);
    lv_obj_align(s_avatar_step[2], LV_ALIGN_BOTTOM_LEFT, 0, 0);
    lv_obj_align(s_avatar_step[3], LV_ALIGN_BOTTOM_RIGHT, 0, 0);
    for (int i = 0; i < 4; i++) {
        if (stepped) {
            lv_obj_remove_flag(s_avatar_step[i], LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_style_bg_color(s_avatar_step[i], lv_color_hex(COLOR_BG), LV_PART_MAIN);
        } else {
            lv_obj_add_flag(s_avatar_step[i], LV_OBJ_FLAG_HIDDEN);
        }
    }

    /* eyes: square blocks, radius 0 */
    int16_t eye_w = 20, eye_h = 20, eye_y = -28;
    switch (eyes) {
    case BUDDY_EYES_SLEEPY:
        eye_w = 24;
        eye_h = 6;
        break;
    case BUDDY_EYES_WIDE:
        eye_w = 20;
        eye_h = 24;
        break;
    case BUDDY_EYES_SIDE:
        eye_w = 12;
        eye_h = 12;
        break;
    case BUDDY_EYES_DOT:
        eye_w = 8;
        eye_h = 8;
        break;
    default:
        break;
    }
    int16_t eye_dx = (eyes == BUDDY_EYES_SIDE) ? 4 : 0;
    lv_obj_set_size(s_avatar_eye_l, eye_w, eye_h);
    lv_obj_set_size(s_avatar_eye_r, eye_w, eye_h);
    lv_obj_align(s_avatar_eye_l, LV_ALIGN_CENTER, -28 + eye_dx, eye_y);
    lv_obj_align(s_avatar_eye_r, LV_ALIGN_CENTER, 28 + eye_dx, eye_y);
    lv_obj_set_style_radius(s_avatar_eye_l, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(s_avatar_eye_r, 0, LV_PART_MAIN);
    lv_obj_set_style_bg_color(s_avatar_eye_l, accent, LV_PART_MAIN);
    lv_obj_set_style_bg_color(s_avatar_eye_r, accent, LV_PART_MAIN);

    /* mouth: square / bar / hollow square blocks */
    bool grin = false;
    switch (mouth) {
    case BUDDY_MOUTH_GRIN:
        lv_obj_set_size(s_avatar_mouth, 44, 16);
        lv_obj_set_style_radius(s_avatar_mouth, 0, LV_PART_MAIN);
        lv_obj_set_style_border_width(s_avatar_mouth, 0, LV_PART_MAIN);
        lv_obj_set_style_bg_color(s_avatar_mouth, accent, LV_PART_MAIN);
        grin = true;
        break;
    case BUDDY_MOUTH_FLAT:
        lv_obj_set_size(s_avatar_mouth, 28, 6);
        lv_obj_set_style_radius(s_avatar_mouth, 0, LV_PART_MAIN);
        lv_obj_set_style_border_width(s_avatar_mouth, 0, LV_PART_MAIN);
        lv_obj_set_style_bg_color(s_avatar_mouth, accent, LV_PART_MAIN);
        break;
    case BUDDY_MOUTH_OPEN:
        lv_obj_set_size(s_avatar_mouth, 24, 24);
        lv_obj_set_style_radius(s_avatar_mouth, 0, LV_PART_MAIN);
        lv_obj_set_style_bg_color(s_avatar_mouth, lv_color_hex(COLOR_BG), LV_PART_MAIN);
        lv_obj_set_style_border_color(s_avatar_mouth, accent, LV_PART_MAIN);
        lv_obj_set_style_border_width(s_avatar_mouth, 4, LV_PART_MAIN);
        break;
    case BUDDY_MOUTH_SMALL:
    default:
        lv_obj_set_size(s_avatar_mouth, 16, 8);
        lv_obj_set_style_radius(s_avatar_mouth, 0, LV_PART_MAIN);
        lv_obj_set_style_border_width(s_avatar_mouth, 0, LV_PART_MAIN);
        lv_obj_set_style_bg_color(s_avatar_mouth, accent, LV_PART_MAIN);
        break;
    }
    lv_obj_align(s_avatar_mouth, LV_ALIGN_CENTER, 0, 30);

    /* pixel teeth inside the grin */
    for (int i = 0; i < 2; i++) {
        if (grin) {
            lv_obj_remove_flag(s_avatar_tooth[i], LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_style_bg_color(s_avatar_tooth[i], lv_color_hex(0xFFFFFF), LV_PART_MAIN);
        } else {
            lv_obj_add_flag(s_avatar_tooth[i], LV_OBJ_FLAG_HIDDEN);
        }
    }
}

/** Create an avatar widget tree under `parent`; returns root container. */
static lv_obj_t *avatar_create(lv_obj_t *parent)
{
    lv_obj_t *root = lv_obj_create(parent);
    lv_obj_set_size(root, AVATAR_SIZE + 30, AVATAR_SIZE + 30);
    lv_obj_set_style_bg_opa(root, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(root, 0, LV_PART_MAIN);

    s_avatar_face = lv_obj_create(root);
    lv_obj_set_style_pad_all(s_avatar_face, 0, LV_PART_MAIN);

    /* step corners and teeth must render above the face bg but below the
     * eyes/mouth, so create them before those parts. */
    for (int i = 0; i < 4; i++) {
        s_avatar_step[i] = lv_obj_create(s_avatar_face);
        lv_obj_set_style_radius(s_avatar_step[i], 0, LV_PART_MAIN);
        lv_obj_set_style_border_width(s_avatar_step[i], 0, LV_PART_MAIN);
        lv_obj_add_flag(s_avatar_step[i], LV_OBJ_FLAG_HIDDEN);
    }

    s_avatar_eye_l = lv_obj_create(s_avatar_face);
    s_avatar_eye_r = lv_obj_create(s_avatar_face);
    s_avatar_mouth = lv_obj_create(s_avatar_face);
    lv_obj_set_style_border_width(s_avatar_eye_l, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(s_avatar_eye_r, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(s_avatar_mouth, 0, LV_PART_MAIN);

    /* pixel teeth ride inside the grin mouth (children of the mouth) */
    for (int i = 0; i < 2; i++) {
        s_avatar_tooth[i] = lv_obj_create(s_avatar_mouth);
        lv_obj_set_size(s_avatar_tooth[i], 10, 6);
        lv_obj_set_style_radius(s_avatar_tooth[i], 0, LV_PART_MAIN);
        lv_obj_set_style_border_width(s_avatar_tooth[i], 0, LV_PART_MAIN);
        lv_obj_align(s_avatar_tooth[i], LV_ALIGN_BOTTOM_MID, i == 0 ? -11 : 11, -1);
        lv_obj_add_flag(s_avatar_tooth[i], LV_OBJ_FLAG_HIDDEN);
    }

    lv_obj_set_scrollbar_mode(s_avatar_face, LV_SCROLLBAR_MODE_OFF);
    lv_obj_set_scrollbar_mode(root, LV_SCROLLBAR_MODE_OFF);
    return root;
}

static void motion_timer_cb(lv_timer_t *timer)
{
    (void)timer;
    if (!s_avatar_face) {
        return;
    }
    lv_obj_t *root = lv_obj_get_parent(s_avatar_face);
    s_motion_tick++;
    int16_t dx = 0, dy = 0;
    buddy_motion_t motion = s_avatar_motion;
    if (motion == BUDDY_MOTION_STILL) {
        /* idle style motion when no explicit node motion */
        switch (s_avatar_mstyle) {
        case BUDDY_MSTYLE_DROWSY:
            dy = (int16_t)((s_motion_tick % 16) < 8 ? 1 : -1);
            break;
        case BUDDY_MSTYLE_JITTERY:
            dx = (int16_t)((s_motion_tick * 7) % 5) - 2;
            break;
        case BUDDY_MSTYLE_BOUNCY:
            dy = (int16_t)((s_motion_tick % 8) < 4 ? -3 : 3);
            break;
        default:
            return;
        }
    } else {
        switch (motion) {
        case BUDDY_MOTION_BREATHE:
            dy = (int16_t)((s_motion_tick % 20) < 10 ? -2 : 2);
            break;
        case BUDDY_MOTION_SHAKE:
            dx = (int16_t)(((s_motion_tick % 4) < 2) ? -6 : 6);
            break;
        case BUDDY_MOTION_BOUNCE:
            dy = (int16_t)(((s_motion_tick % 6) < 3) ? -10 : 6);
            break;
        case BUDDY_MOTION_NOD:
            dy = (int16_t)(((s_motion_tick % 4) < 2) ? -5 : 5);
            break;
        default:
            return;
        }
    }
    lv_obj_align(root, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_set_pos(root, s_avatar_base_x + dx, s_avatar_base_y + dy);
}

static void avatar_set_motion(buddy_motion_t motion, buddy_motion_style_t style)
{
    s_avatar_motion = motion;
    s_avatar_mstyle = style;
    s_motion_tick = 0;
}

/* ------------------------------------------------------------------ */
/* touch input normalization                                           */
/* ------------------------------------------------------------------ */

/* LVGL v9 input facts this works around (see F:/t5open lv_indev.c):
 * - A drag >scroll_limit (10px) on a SCROLLABLE object starts an elastic
 *   scroll that swallows the press: no CLICKED, and no GESTURE either
 *   unless gesture_sum >gesture_limit (50px) with per-read velocity
 *   >=gesture_min_velocity (3px/30ms) and no pause. 10-50px or pausing
 *   swipes vanish entirely; <10px swipes release as CLICKED ("tap").
 * - LV_EVENT_CLICKED is sent on release even after LV_EVENT_LONG_PRESSED
 *   or a gesture, so a long press always looks like tap+long_press.
 * Strategy: card/game_area are made non-scrollable, every press is tracked
 * from PRESSED through PRESSING, and release displacement classifies the
 * press as swipe vs tap ourselves. Gesture thresholds are also lowered. */
#define BUDDY_TAP_SLOP_PX     14   /**< max press displacement still counted as a tap */
#define BUDDY_GESTURE_LIMIT_PX 12  /**< LVGL gesture fires past this accumulated movement */
#define BUDDY_GESTURE_MIN_VEL   1  /**< px per indev read (30ms) to keep accumulating */

typedef struct {
    bool active;        /**< press in progress */
    bool gesture_seen;  /**< LV_EVENT_GESTURE fired for this press */
    bool swipe_done;    /**< swipe action already dispatched for this press */
    bool long_seen;     /**< LV_EVENT_LONG_PRESSED fired for this press */
    lv_point_t start;   /**< point at PRESSED */
    lv_point_t latest;  /**< most recent point from PRESSING */
} buddy_touch_t;

static buddy_touch_t s_touch;

/** Reset per-press state; called on LV_EVENT_PRESSED. */
static void buddy_touch_begin(lv_event_t *event)
{
    lv_indev_t *indev = lv_indev_get_act();
    if (indev == NULL) {
        return;
    }
    lv_indev_get_point(indev, &s_touch.start);
    s_touch.latest = s_touch.start;
    s_touch.active = true;
    s_touch.gesture_seen = false;
    s_touch.swipe_done = false;
    s_touch.long_seen = false;
    (void)event;
}

/** Track the moving point; called on LV_EVENT_PRESSING. */
static void buddy_touch_move(lv_event_t *event)
{
    lv_indev_t *indev = lv_indev_get_act();
    if (indev == NULL || !s_touch.active) {
        return;
    }
    lv_indev_get_point(indev, &s_touch.latest);
    (void)event;
}

static int16_t buddy_touch_disp(void)
{
    int32_t dx = s_touch.latest.x - s_touch.start.x;
    int32_t dy = s_touch.latest.y - s_touch.start.y;
    if (dx < 0) dx = -dx;
    if (dy < 0) dy = -dy;
    return (int16_t)(dx > dy ? dx : dy);
}

/** Dominant direction of the tracked press, for swipe fallback. */
static lv_dir_t buddy_touch_dir(void)
{
    int32_t dx = s_touch.latest.x - s_touch.start.x;
    int32_t dy = s_touch.latest.y - s_touch.start.y;
    int32_t ax = dx < 0 ? -dx : dx;
    int32_t ay = dy < 0 ? -dy : dy;
    if (ax >= ay) {
        return dx >= 0 ? LV_DIR_RIGHT : LV_DIR_LEFT;
    }
    return dy >= 0 ? LV_DIR_BOTTOM : LV_DIR_TOP;
}

/** True when the current press must NOT be treated as a tap on release. */
static bool buddy_touch_is_swipe(void)
{
    return s_touch.gesture_seen || s_touch.swipe_done ||
           buddy_touch_disp() > BUDDY_TAP_SLOP_PX;
}

/** Lower LVGL's gesture thresholds so LV_EVENT_GESTURE fires reliably
 *  (default 50px + 3px/30ms velocity reset swallows most panel swipes). */
static void input_thresholds_init(void)
{
    lv_indev_t *indev = lv_indev_get_next(NULL);
    while (indev != NULL) {
        indev->gesture_limit = BUDDY_GESTURE_LIMIT_PX;
        indev->gesture_min_velocity = BUDDY_GESTURE_MIN_VEL;
        indev = lv_indev_get_next(indev);
    }
}

/* ------------------------------------------------------------------ */
/* home                                                                */
/* ------------------------------------------------------------------ */


static lv_obj_t *make_label(lv_obj_t *parent, const char *text, lv_color_t color)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_color(label, color, LV_PART_MAIN);
    lv_obj_set_style_text_font(label, &buddy_font, LV_PART_MAIN);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    lv_label_set_long_mode(label, LV_LABEL_LONG_WRAP);
    return label;
}

/** Chunky pixel-style button: sharp square corners, saturated accent fill. */
static lv_obj_t *make_pixel_button(lv_obj_t *parent, const char *text, int16_t w, int16_t h)
{
    lv_obj_t *btn = lv_button_create(parent);
    lv_obj_set_size(btn, w, h);
    lv_obj_set_style_radius(btn, 0, LV_PART_MAIN);
    lv_obj_set_style_bg_color(btn, lv_color_hex(COLOR_ACCENT), LV_PART_MAIN);
    lv_obj_set_style_border_width(btn, 0, LV_PART_MAIN);
    lv_obj_t *btn_label = make_label(btn, text, lv_color_hex(COLOR_BG));
    lv_obj_center(btn_label);
    return btn;
}

static void home_refresh_card(void)
{
    preset_slot_t *slot = &s_presets[s_selected];
    const buddy_t *buddy = &slot->buddy;

    lv_label_set_text(s_label_name, slot->parsed ? buddy->name : "---");
    lv_label_set_text(s_label_personality, slot->parsed ? buddy->personality : slot->err);

    if (slot->parsed && buddy->tag_count > 0) {
        char tag_buf[48];
        snprintf(tag_buf, sizeof(tag_buf), "#%s", buddy->tags[0]);
        for (int i = 1; i < buddy->tag_count; i++) {
            size_t used = strlen(tag_buf);
            snprintf(tag_buf + used, sizeof(tag_buf) - used, "  #%s", buddy->tags[i]);
        }
        lv_label_set_text(s_label_tag, tag_buf);
    } else {
        lv_label_set_text(s_label_tag, "");
    }

    char index_buf[12];
    snprintf(index_buf, sizeof(index_buf), UI_HOME_INDEX_FMT, s_selected + 1, s_preset_count);
    lv_label_set_text(s_label_index, index_buf);

    if (slot->parsed) {
        avatar_apply(buddy, BUDDY_EXPR_NEUTRAL);
        avatar_set_motion(BUDDY_MOTION_STILL, buddy->motion_style);
    }
}

static void home_switch_card(lv_dir_t dir)
{
    if (dir == LV_DIR_LEFT) {
        s_selected = (s_selected + 1) % s_preset_count;
    } else if (dir == LV_DIR_RIGHT) {
        s_selected = (s_selected + s_preset_count - 1) % s_preset_count;
    } else {
        return;
    }
    PR_NOTICE("buddy: home card -> %u/%u", (unsigned)s_selected + 1, (unsigned)s_preset_count);
    home_refresh_card();
}

static void home_event_cb(lv_event_t *event)
{
    lv_event_code_t code = lv_event_get_code(event);
    if (code == LV_EVENT_GESTURE) {
        /* LVGL recognized the swipe; the release CLICKED must not start a
         * game, so mark the press as handled. LVGL sends GESTURE to the
         * screen because the card carries GESTURE_BUBBLE by default. */
        lv_dir_t dir = lv_indev_get_gesture_dir(lv_indev_get_act());
        if (dir != LV_DIR_NONE) {
            s_touch.gesture_seen = true;
            s_touch.swipe_done = true;
            home_switch_card(dir);
        }
    }
}

static void card_click_cb(lv_event_t *event)
{
    (void)event;
    /* LVGL emits CLICKED on every release, including after a swipe or a
     * long press. Only a clean, still press may start the game. */
    if (buddy_touch_is_swipe()) {
        PR_NOTICE("buddy: card click ignored (swipe, disp=%d)", buddy_touch_disp());
        return;
    }
    if (s_touch.long_seen) {
        PR_NOTICE("buddy: card click ignored (after long press)");
        return;
    }
    preset_slot_t *slot = &s_presets[s_selected];
    if (!slot->parsed) {
        PR_ERR("buddy: preset invalid: %s", slot->err);
        return;
    }
    if (!slot->resources_ok) {
        PR_ERR("buddy: preset resources invalid");
        return;
    }
    PR_NOTICE("buddy: card clicked, starting %s", slot->buddy.buddy_id);
    show_game(s_selected);
}

static void card_release_cb(lv_event_t *event)
{
    /* Fallback when LVGL's own gesture detection failed (pauses reset its
     * accumulator): classify by displacement so the swipe still lands. */
    if (s_touch.active && !s_touch.swipe_done && buddy_touch_disp() > BUDDY_TAP_SLOP_PX) {
        s_touch.swipe_done = true;
        lv_dir_t dir = buddy_touch_dir();
        PR_NOTICE("buddy: swipe fallback dir=%d disp=%d", (int)dir, buddy_touch_disp());
        home_switch_card(dir);
    }
    s_touch.active = false;
    (void)event;
}

static void card_long_press_cb(lv_event_t *event)
{
    (void)event;
    s_touch.long_seen = true;
    show_detail_screen(s_selected);
}

static void generate_click_cb(lv_event_t *event)
{
    (void)event;
    lv_obj_t *screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(screen, lv_color_hex(COLOR_BG), LV_PART_MAIN);
    lv_obj_add_event_cb(screen, back_to_home_cb, LV_EVENT_GESTURE, NULL);
    lv_obj_clear_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *title = make_label(screen, UI_GEN_TITLE, lv_color_hex(COLOR_TEXT));
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 30);

    lv_obj_t *msg = make_label(screen, UI_GEN_UNAVAILABLE, lv_color_hex(COLOR_TEXT_DIM));
    lv_obj_align(msg, LV_ALIGN_CENTER, 0, -20);

    lv_obj_t *back = make_pixel_button(screen, UI_BTN_BACK, 120, 48);
    lv_obj_align(back, LV_ALIGN_BOTTOM_MID, 0, -24);
    lv_obj_add_event_cb(back, back_to_home_cb, LV_EVENT_CLICKED, NULL);

    nav_load(screen);
}

static void back_to_home_cb(lv_event_t *event);

static void show_home(void)
{
    lv_obj_t *s_home = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_home, lv_color_hex(COLOR_BG), LV_PART_MAIN);
    lv_obj_clear_flag(s_home, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *title = make_label(s_home, UI_APP_TITLE, lv_color_hex(COLOR_ACCENT));
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 16);

    char subtitle[40];
    snprintf(subtitle, sizeof(subtitle), "%s (%d)", UI_HOME_SUBTITLE, s_preset_count);
    lv_obj_t *subtitle_label = make_label(s_home, subtitle, lv_color_hex(COLOR_TEXT_DIM));
    lv_obj_align(subtitle_label, LV_ALIGN_TOP_MID, 0, 44);

    s_avatar_root = avatar_create(s_home);
    lv_obj_align(s_avatar_root, LV_ALIGN_TOP_MID, 0, 74);
    s_avatar_base_x = 0;
    s_avatar_base_y = 74;

    s_label_name = make_label(s_home, "", lv_color_hex(COLOR_TEXT));
    lv_obj_align(s_label_name, LV_ALIGN_TOP_MID, 0, 268);

    s_label_personality = make_label(s_home, "", lv_color_hex(COLOR_TEXT_DIM));
    lv_obj_set_width(s_label_personality, 280);
    lv_obj_align(s_label_personality, LV_ALIGN_TOP_MID, 0, 296);

    s_label_tag = make_label(s_home, "", lv_color_hex(COLOR_ACCENT));
    lv_obj_align(s_label_tag, LV_ALIGN_TOP_MID, 0, 322);

    s_label_index = make_label(s_home, "", lv_color_hex(COLOR_TEXT_DIM));
    lv_obj_align(s_label_index, LV_ALIGN_TOP_MID, 0, 346);

    lv_obj_t *hint = make_label(s_home, UI_HOME_HINT, lv_color_hex(COLOR_TEXT_DIM));
    lv_obj_set_width(hint, 300);
    lv_obj_align(hint, LV_ALIGN_TOP_MID, 0, 372);

    /* 180x46 at BOTTOM_MID -24 -> y 396..442; bottom corners need
     * half-chord >= 90 at y=442: sqrt(233^2-209^2) = 103. OK. */
    lv_obj_t *generate = make_pixel_button(s_home, UI_BTN_GENERATE, 180, 46);
    lv_obj_align(generate, LV_ALIGN_BOTTOM_MID, 0, -24);
    lv_obj_add_event_cb(generate, generate_click_cb, LV_EVENT_CLICKED, NULL);

    s_card = lv_obj_create(s_home);
    lv_obj_set_size(s_card, 300, 300);
    lv_obj_align(s_card, LV_ALIGN_TOP_MID, 0, 68);
    lv_obj_set_style_bg_opa(s_card, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(s_card, 0, LV_PART_MAIN);
    /* Non-scrollable: otherwise an elastic scroll (default on plain objs)
     * swallows every drag and CLICKED is lost or mis-classified. */
    lv_obj_remove_flag(s_card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(s_card, card_click_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_add_event_cb(s_card, card_long_press_cb, LV_EVENT_LONG_PRESSED, NULL);
    lv_obj_add_event_cb(s_card, buddy_touch_begin, LV_EVENT_PRESSED, NULL);
    lv_obj_add_event_cb(s_card, buddy_touch_move, LV_EVENT_PRESSING, NULL);
    lv_obj_add_event_cb(s_card, card_release_cb, LV_EVENT_RELEASED, NULL);
    lv_obj_add_event_cb(s_home, home_event_cb, LV_EVENT_GESTURE, NULL);

    home_refresh_card();
    nav_load(s_home);
    PR_NOTICE("buddy: home ready, %d presets", s_preset_count);
}

static void back_to_home_cb(lv_event_t *event)
{
    lv_event_code_t code = lv_event_get_code(event);
    if (code == LV_EVENT_GESTURE) {
        lv_dir_t dir = lv_indev_get_gesture_dir(lv_indev_get_act());
        if (dir != LV_DIR_RIGHT) {
            return;
        }
    }
    show_home_refresh();
}

static void show_home_refresh(void)
{
    show_home();
}

/* ------------------------------------------------------------------ */
/* detail                                                              */
/* ------------------------------------------------------------------ */

static void show_detail_screen(uint8_t preset_index)
{
    preset_slot_t *slot = &s_presets[preset_index];
    const buddy_t *buddy = &slot->buddy;

    lv_obj_t *s_detail = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_detail, lv_color_hex(COLOR_BG), LV_PART_MAIN);
    lv_obj_clear_flag(s_detail, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *title = make_label(s_detail, UI_DETAIL_TITLE, lv_color_hex(COLOR_ACCENT));
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 18);

    char buf[160];
    lv_obj_t *body = lv_label_create(s_detail);
    lv_obj_set_style_text_font(body, &buddy_font, LV_PART_MAIN);
    lv_obj_set_style_text_color(body, lv_color_hex(COLOR_TEXT), LV_PART_MAIN);
    /* long text: centered, width 320 -> x 73..399; the narrowest chord the
     * text block can meet (y ~350) has half-width sqrt(233^2-117^2)=201,
     * so 320 < 402 always stays inside the circle. */
    lv_obj_set_width(body, 320);
    lv_obj_set_style_text_align(body, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    lv_label_set_long_mode(body, LV_LABEL_LONG_WRAP);
    if (slot->parsed) {
        snprintf(buf, sizeof(buf),
                 "%s：%s\n\n%s：%s\n\n%s：%s\n\n%s：", UI_DETAIL_NAME, buddy->name,
                 UI_DETAIL_PERSONALITY, buddy->personality, UI_DETAIL_GAMEPLAY, buddy->gameplay_summary,
                 UI_DETAIL_TAGS);
        lv_label_set_text(body, buf);
        for (int i = 0; i < buddy->tag_count; i++) {
            lv_label_ins_text(body, LV_LABEL_POS_LAST, i == 0 ? "" : "  ");
            lv_label_ins_text(body, LV_LABEL_POS_LAST, buddy->tags[i]);
        }
        lv_label_ins_text(body, LV_LABEL_POS_LAST, "\n\n");
        lv_label_ins_text(body, LV_LABEL_POS_LAST, UI_LOCAL_READY);
    } else {
        lv_label_set_text(body, slot->err);
    }
    lv_obj_align(body, LV_ALIGN_TOP_MID, 0, 64);

    lv_obj_t *back = make_pixel_button(s_detail, UI_BTN_BACK, 120, 48);
    lv_obj_align(back, LV_ALIGN_BOTTOM_MID, 0, -24);
    lv_obj_add_event_cb(back, back_to_home_cb, LV_EVENT_CLICKED, NULL);

    nav_load(s_detail);
}

/* ------------------------------------------------------------------ */
/* game                                                                */
/* ------------------------------------------------------------------ */

static void game_end_ui(void)
{
    bool escaped = s_session.outcome == BUDDY_OUTCOME_ESCAPED;
    lv_label_set_text(s_label_outcome, escaped ? UI_OUTCOME_ESCAPED : UI_OUTCOME_CARRIED);
    lv_obj_set_style_text_color(s_label_outcome,
                                lv_color_hex(escaped ? COLOR_ACCENT : COLOR_DANGER), LV_PART_MAIN);
    lv_obj_clear_flag(s_end_panel, LV_OBJ_FLAG_HIDDEN);
    PR_NOTICE("buddy %s: game ended (%s)", s_session.buddy->buddy_id,
              escaped ? "escaped" : "carried_away");
}

static void game_refresh_node(void)
{
    const buddy_t *buddy = s_session.buddy;
    const buddy_node_t *node = &buddy->nodes[s_session.current_node];

    lv_label_set_text(s_label_title, node->title);
    lv_label_set_text(s_label_instruction, node->instruction);

    char timer_buf[20];
    snprintf(timer_buf, sizeof(timer_buf), UI_GAME_REMAINING_FMT, s_session.remaining_sec);
    lv_label_set_text(s_label_timer, timer_buf);

    avatar_apply(buddy, s_session.expression);
    avatar_set_motion(s_session.motion, buddy->motion_style);
}

static void game_tick_cb(lv_timer_t *timer)
{
    (void)timer;
    if (!s_session_active || s_session.outcome != BUDDY_OUTCOME_NONE) {
        return;
    }
    /* timer events take priority over queued touch events this cycle */
    if (buddy_session_handle(&s_session, BUDDY_EVENT_TIMER, &SESSION_OPS)) {
        if (s_session.outcome != BUDDY_OUTCOME_NONE) {
            s_session_active = false;
            game_refresh_node();
            game_end_ui();
        } else {
            game_refresh_node();
        }
    }
}

static const char *game_event_name(buddy_event_t event)
{
    switch (event) {
    case BUDDY_EVENT_TAP: return "tap";
    case BUDDY_EVENT_LONG_PRESS: return "long_press";
    case BUDDY_EVENT_SWIPE: return "swipe";
    default: return "?";
    }
}

/** Compact one-line state dump: node, vars, remaining time. */
static void game_log_state(const char *what)
{
    const buddy_t *buddy = s_session.buddy;
    if (buddy == NULL) {
        return;
    }
    char vars[48] = "-";
    size_t used = 0;
    vars[0] = '\0';
    for (int i = 0; i < buddy->var_count; i++) {
        used += snprintf(vars + used, sizeof(vars) - used, "%s%s=%d", i ? " " : "",
                         buddy->vars[i].name, s_session.var_values[i]);
    }
    PR_NOTICE("buddy %s: %s node=%s vars=%s rem=%ds", buddy->buddy_id, what,
              buddy->nodes[s_session.current_node].id, vars[0] ? vars : "-",
              s_session.remaining_sec);
}

static void game_dispatch(buddy_event_t event)
{
    if (!s_session_active || s_session.outcome != BUDDY_OUTCOME_NONE) {
        return;
    }
    game_log_state(game_event_name(event));
    if (buddy_session_handle(&s_session, event, &SESSION_OPS)) {
        if (s_session.outcome != BUDDY_OUTCOME_NONE) {
            s_session_active = false;
            game_refresh_node();
            game_end_ui();
        } else {
            game_refresh_node();
            game_log_state("after");
        }
    }
}

static void game_area_event_cb(lv_event_t *event)
{
    lv_event_code_t code = lv_event_get_code(event);
    if (code == LV_EVENT_CLICKED) {
        /* LVGL sends CLICKED on every release, even after a gesture or a
         * long press. Only a clean still press is a tap. */
        if (buddy_touch_is_swipe()) {
            PR_NOTICE("buddy: tap suppressed after swipe (disp=%d)", buddy_touch_disp());
            return;
        }
        if (s_touch.long_seen) {
            PR_NOTICE("buddy: tap suppressed after long press");
            return;
        }
        game_dispatch(BUDDY_EVENT_TAP);
    } else if (code == LV_EVENT_LONG_PRESSED) {
        s_touch.long_seen = true;
        game_dispatch(BUDDY_EVENT_LONG_PRESS);
    } else if (code == LV_EVENT_GESTURE) {
        lv_dir_t dir = lv_indev_get_gesture_dir(lv_indev_get_act());
        if (dir != LV_DIR_NONE && !s_touch.swipe_done) {
            s_touch.gesture_seen = true;
            s_touch.swipe_done = true;
            game_dispatch(BUDDY_EVENT_SWIPE);
        }
    }
}

static void game_area_release_cb(lv_event_t *event)
{
    /* Fallback for swipes LVGL's own gesture detection missed (its
     * accumulator resets on any sub-velocity sample): classify by
     * displacement so the swipe still reaches the engine. */
    if (s_touch.active && !s_touch.swipe_done &&
        buddy_touch_disp() > BUDDY_TAP_SLOP_PX) {
        s_touch.swipe_done = true;
        PR_NOTICE("buddy: swipe fallback disp=%d", buddy_touch_disp());
        game_dispatch(BUDDY_EVENT_SWIPE);
    }
    s_touch.active = false;
    (void)event;
}

static void game_back_cb(lv_event_t *event)
{
    (void)event;
    PR_NOTICE("buddy %s: game aborted by user", s_session.buddy ? s_session.buddy->buddy_id : "-");
    s_session_active = false;
    s_session.outcome = BUDDY_OUTCOME_NONE;
    lv_timer_pause(s_game_timer);
    show_home_refresh();
}

static void game_restart_cb(lv_event_t *event)
{
    (void)event;
    lv_obj_add_flag(s_end_panel, LV_OBJ_FLAG_HIDDEN);
    buddy_session_start(&s_session, &s_presets[s_selected].buddy);
    s_session_active = true;
    lv_timer_reset(s_game_timer);
    lv_timer_resume(s_game_timer);
    /* game.start runs initial-node on_enter (audio, expression) */
    game_dispatch(BUDDY_EVENT_GAME_START);
    game_refresh_node();
    PR_NOTICE("buddy %s: game restarted", s_session.buddy->buddy_id);
}

static void show_game(uint8_t preset_index)
{
    s_selected = preset_index;
    const buddy_t *buddy = &s_presets[preset_index].buddy;

    lv_obj_t *s_game = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_game, lv_color_hex(COLOR_BG), LV_PART_MAIN);
    lv_obj_clear_flag(s_game, LV_OBJ_FLAG_SCROLLABLE);

    /* Round-screen header: top corners are outside the circle (chord at
     * y=10 is only 135 wide), so back and timer stack centered instead of
     * hugging the clipped corners. */
    lv_obj_t *back = make_pixel_button(s_game, UI_GAME_BACK, 76, 36);
    lv_obj_align(back, LV_ALIGN_TOP_MID, 0, 12);
    lv_obj_add_event_cb(back, game_back_cb, LV_EVENT_CLICKED, NULL);

    s_label_timer = make_label(s_game, "", lv_color_hex(COLOR_TEXT_DIM));
    lv_obj_align(s_label_timer, LV_ALIGN_TOP_MID, 0, 52);

    lv_obj_t *avatar_root = avatar_create(s_game);
    lv_obj_align(avatar_root, LV_ALIGN_TOP_MID, 0, 84);
    s_avatar_base_x = 0;
    s_avatar_base_y = 84;
    (void)avatar_root;

    s_label_title = make_label(s_game, "", lv_color_hex(COLOR_TEXT));
    lv_obj_set_style_text_font(s_label_title, &buddy_font, LV_PART_MAIN);
    lv_obj_align(s_label_title, LV_ALIGN_TOP_MID, 0, 278);

    s_label_instruction = make_label(s_game, "", lv_color_hex(COLOR_TEXT_DIM));
    lv_obj_set_width(s_label_instruction, 300);
    lv_obj_align(s_label_instruction, LV_ALIGN_TOP_MID, 0, 306);

    /* game area covers everything below the header; gestures drive events */
    s_game_area = lv_obj_create(s_game);
    lv_obj_set_size(s_game_area, lv_pct(100), lv_pct(100));
    lv_obj_align(s_game_area, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_bg_opa(s_game_area, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(s_game_area, 0, LV_PART_MAIN);
    /* Non-scrollable: an elastic scroll here would swallow drags without
     * ever producing CLICKED or GESTURE (the input black hole). */
    lv_obj_remove_flag(s_game_area, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(s_game_area, game_area_event_cb,
                        LV_EVENT_CLICKED | LV_EVENT_LONG_PRESSED | LV_EVENT_GESTURE, NULL);
    lv_obj_add_event_cb(s_game_area, buddy_touch_begin, LV_EVENT_PRESSED, NULL);
    lv_obj_add_event_cb(s_game_area, buddy_touch_move, LV_EVENT_PRESSING, NULL);
    lv_obj_add_event_cb(s_game_area, game_area_release_cb, LV_EVENT_RELEASED, NULL);
    lv_obj_move_foreground(back); /* back button stays clickable above area */

    /* ending overlay: 280x150 centered -> corners at (93,158)/(373,308),
     * worst radius sqrt(140^2+75^2) = 159 << 233. Square-corner pixel panel. */
    s_end_panel = lv_obj_create(s_game);
    lv_obj_set_size(s_end_panel, 280, 150);
    lv_obj_center(s_end_panel);
    lv_obj_set_style_bg_color(s_end_panel, lv_color_hex(COLOR_PANEL), LV_PART_MAIN);
    lv_obj_set_style_radius(s_end_panel, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(s_end_panel, 4, LV_PART_MAIN);
    lv_obj_set_style_border_color(s_end_panel, lv_color_hex(COLOR_ACCENT), LV_PART_MAIN);
    lv_obj_add_flag(s_end_panel, LV_OBJ_FLAG_HIDDEN);
    s_label_outcome = make_label(s_end_panel, "", lv_color_hex(COLOR_TEXT));
    lv_obj_align(s_label_outcome, LV_ALIGN_TOP_MID, 0, 24);
    lv_obj_t *restart = make_pixel_button(s_end_panel, UI_BTN_RESTART, 140, 44);
    lv_obj_align(restart, LV_ALIGN_BOTTOM_MID, 0, -18);
    lv_obj_add_event_cb(restart, game_restart_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_move_foreground(s_end_panel);

    /* fresh session */
    buddy_session_start(&s_session, buddy);
    s_session_active = true;
    lv_timer_reset(s_game_timer);
    lv_timer_resume(s_game_timer);
    game_dispatch(BUDDY_EVENT_GAME_START);
    game_refresh_node();

    nav_load(s_game);
    PR_NOTICE("buddy %s: game started, %ds", buddy->buddy_id, buddy->duration_sec);
}

/* ------------------------------------------------------------------ */
/* boot                                                                */
/* ------------------------------------------------------------------ */

static void audio_init(void)
{
    s_audio = NULL;
    if (tdl_audio_find(AUDIO_CODEC_NAME, &s_audio) == OPRT_OK) {
        tdl_audio_open(s_audio, NULL);
        tdl_audio_volume_set(s_audio, 80);
        PR_NOTICE("buddy: audio codec ready");
    } else {
        PR_ERR("buddy: audio codec not found, feedback sound disabled");
    }
}

void buddy_app_init(void)
{
    builtin_resource_digest_init();
    input_thresholds_init();

    s_preset_count = 0;
    for (uint32_t i = 0; i < BUDDY_BUILTIN_PRESET_COUNT && s_preset_count < PRESET_COUNT_MAX; i++) {
        preset_slot_t *slot = &s_presets[s_preset_count];
        slot->parsed = buddy_parse(BUDDY_BUILTIN_PRESETS[i].json, BUDDY_BUILTIN_PRESETS[i].json_len,
                                   &slot->buddy, slot->err);
        slot->resources_ok = slot->parsed && validate_preset_resources(&slot->buddy);
        if (slot->parsed) {
            PR_NOTICE("buddy: preset %s validated", slot->buddy.buddy_id);
            s_preset_count++;
        } else {
            PR_ERR("buddy: preset %u rejected: %s", (unsigned)i, slot->err);
        }
    }

    /* avatar motion ticker */
    s_motion_timer = lv_timer_create(motion_timer_cb, 90, NULL);

    /* countdown timer, paused until a game starts */
    s_game_timer = lv_timer_create(game_tick_cb, 1000, NULL);
    lv_timer_pause(s_game_timer);

    show_home();
}

/* hook for main.c: expose audio init before UI */
void buddy_audio_init(void)
{
    audio_init();
}
