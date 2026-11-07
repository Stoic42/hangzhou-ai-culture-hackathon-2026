/**
 * @file test_buddy_engine.c
 * @brief Host-side engine tests for BuddyManifest v1/v2.
 *
 * This is a minimal standalone test runner (no external test framework).
 * Build:
 *   gcc device/t5/tests/test_buddy_engine.c device/t5/src/buddy_engine.c \
 *       /f/t5open/src/libcjson/cJSON/cJSON.c -Idevice/t5/src \
 *       -I/f/t5open/src/libcjson/cJSON -o test_buddy_engine && ./test_buddy_engine
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "buddy_engine.h"

#define TEST_ASSERT(cond) do { \
    if (!(cond)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
        return 1; \
    } \
} while (0)

#define TEST_ASSERT_EQ(a, b) do { \
    if ((a) != (b)) { \
        fprintf(stderr, "FAIL %s:%d: %d != %d\n", __FILE__, __LINE__, (int)(a), (int)(b)); \
        return 1; \
    } \
} while (0)

static int test_v1_parse_last_one(void)
{
    buddy_t buddy;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":1,\"buddy_id\":\"bdy_test\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"duration_sec\":75,\"initial_node\":\"start\",\"variables\":[{\"name\":\"v\",\"type\":\"int\",\"initial\":0}],\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.tap\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[{\"op\":\"game.end\",\"outcome\":\"carried_away\"}]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    TEST_ASSERT_EQ(buddy.schema_version, 1);
    TEST_ASSERT_EQ(buddy.duration_sec, 75);
    TEST_ASSERT_EQ(buddy.node_count, 2);
    return 0;
}

static int test_v2_parse_minimal(void)
{
    buddy_t buddy;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":50,\"rise_per_sec\":3,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"你赢了\"],\"carried_away\":[\"你输了\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.tap\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[{\"op\":\"game.end\",\"outcome\":\"carried_away\"}]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    TEST_ASSERT_EQ(buddy.schema_version, 2);
    TEST_ASSERT_EQ(buddy.pressure.initial, 50);
    TEST_ASSERT_EQ(buddy.pressure.rise_per_sec, 3);
    TEST_ASSERT_EQ(buddy.pressure.min, 0);
    TEST_ASSERT_EQ(buddy.pressure.max, 100);
    TEST_ASSERT_EQ(buddy.quips.escaped_count, 1);
    TEST_ASSERT_EQ(buddy.quips.carried_away_count, 1);
    TEST_ASSERT_EQ(buddy.duration_sec, 0);
    return 0;
}

static int test_v2_pressure_erodes_to_carried_away(void)
{
    buddy_t buddy;
    buddy_session_t session;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":50,\"rise_per_sec\":10,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"e\"],\"carried_away\":[\"c\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[{\"op\":\"game.end\",\"outcome\":\"carried_away\"}]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    buddy_session_start(&session, &buddy);
    TEST_ASSERT_EQ(session.pressure, 50);
    for (int i = 0; i < 5; i++) {
        buddy_session_handle(&session, BUDDY_EVENT_TIMER, NULL);
    }
    TEST_ASSERT_EQ(session.pressure, 100);
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_CARRIED_AWAY);
    return 0;
}

static int test_v2_pressure_relief_to_escaped(void)
{
    buddy_t buddy;
    buddy_session_t session;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":30,\"rise_per_sec\":1,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"e\"],\"carried_away\":[\"c\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.tap\",\"to\":\"start\",\"actions\":[{\"op\":\"pressure.adjust\",\"value\":-15}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    buddy_session_start(&session, &buddy);
    TEST_ASSERT_EQ(session.pressure, 30);
    buddy_session_handle(&session, BUDDY_EVENT_TAP, NULL);
    TEST_ASSERT_EQ(session.pressure, 15);
    TEST_ASSERT_EQ(session.relieves, 1);
    buddy_session_handle(&session, BUDDY_EVENT_TAP, NULL);
    TEST_ASSERT_EQ(session.pressure, 0);
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_ESCAPED);
    return 0;
}

static int test_v2_pressure_condition(void)
{
    buddy_t buddy;
    buddy_session_t session;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":30,\"rise_per_sec\":1,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"e\"],\"carried_away\":[\"c\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.tap\",\"to\":\"end\",\"condition\":{\"left\":{\"pressure\":true},\"op\":\"lte\",\"right\":30},\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    buddy_session_start(&session, &buddy);
    TEST_ASSERT(buddy_session_handle(&session, BUDDY_EVENT_TAP, NULL));
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_ESCAPED);
    return 0;
}

static int test_v2_directional_swipe_fallback(void)
{
    buddy_t buddy;
    buddy_session_t session;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":50,\"rise_per_sec\":1,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"e\"],\"carried_away\":[\"c\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.swipe\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    buddy_session_start(&session, &buddy);
    TEST_ASSERT(buddy_session_handle(&session, BUDDY_EVENT_SWIPE_LEFT, NULL));
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_ESCAPED);
    return 0;
}

static int test_v2_directional_swipe_priority(void)
{
    buddy_t buddy;
    buddy_session_t session;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":50,\"rise_per_sec\":1,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"e\"],\"carried_away\":[\"c\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.swipe_left\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]},{\"event\":\"touch.swipe\",\"to\":\"start\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"carried_away\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    buddy_session_start(&session, &buddy);
    TEST_ASSERT(buddy_session_handle(&session, BUDDY_EVENT_SWIPE_LEFT, NULL));
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_ESCAPED);
    return 0;
}

static int test_v2_rapid_tap_window_and_reset(void)
{
    buddy_t buddy;
    buddy_session_t session;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":50,\"rise_per_sec\":1,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"e\"],\"carried_away\":[\"c\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.rapid_tap\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    buddy_session_start(&session, &buddy);
    /* old API (now_ms=0) disables combo timing, so no rapid_tap */
    buddy_session_handle(&session, BUDDY_EVENT_TAP, NULL);
    buddy_session_handle(&session, BUDDY_EVENT_TAP, NULL);
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_NONE);

    /* rapid_tap fires when two taps are within 400ms */
    buddy_session_start(&session, &buddy);
    buddy_session_handle_ex(&session, BUDDY_EVENT_TAP, NULL, 100);
    buddy_session_handle_ex(&session, BUDDY_EVENT_TAP, NULL, 200);
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_ESCAPED);
    TEST_ASSERT_EQ(session.combo_peak, 2);

    /* gap > 400ms resets combo */
    buddy_session_start(&session, &buddy);
    buddy_session_handle_ex(&session, BUDDY_EVENT_TAP, NULL, 100);
    buddy_session_handle_ex(&session, BUDDY_EVENT_TAP, NULL, 600);
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_NONE);
    TEST_ASSERT_EQ(session.combo_peak, 1);
    return 0;
}

static int test_v2_shake_event(void)
{
    buddy_t buddy;
    buddy_session_t session;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":50,\"rise_per_sec\":1,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"e\"],\"carried_away\":[\"c\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"imu.shake\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    buddy_session_start(&session, &buddy);
    TEST_ASSERT(buddy_session_handle(&session, BUDDY_EVENT_SHAKE, NULL));
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_ESCAPED);
    return 0;
}

static int test_v2_quips_rejected_missing_side(void)
{
    buddy_t buddy;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":50,\"rise_per_sec\":1,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"e\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.tap\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[]}]},\"resources\":[]}";
    TEST_ASSERT(!buddy_parse(json, strlen(json), &buddy, err));
    return 0;
}

static int test_v2_quips_rejected_too_long(void)
{
    buddy_t buddy;
    char err[BUDDY_ERR_LEN];
    char json[2048];
    snprintf(json, sizeof(json),
             "{\"schema_version\":2,\"buddy_id\":\"bdy_v2\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":50,\"rise_per_sec\":1,\"min\":0,\"max\":100},\"quips\":{\"escaped\":[\"%s\"],\"carried_away\":[\"c\"]},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.tap\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[]}]},\"resources\":[]}",
             "啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊");
    TEST_ASSERT(!buddy_parse(json, strlen(json), &buddy, err));
    return 0;
}

static int test_v1_rejects_v2_event(void)
{
    buddy_t buddy;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":1,\"buddy_id\":\"bdy_v1\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"duration_sec\":75,\"initial_node\":\"start\",\"variables\":[],\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.swipe_left\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[{\"op\":\"game.end\",\"outcome\":\"carried_away\"}]}]},\"resources\":[]}";
    TEST_ASSERT(!buddy_parse(json, strlen(json), &buddy, err));
    return 0;
}

static int test_v1_rejects_pressure(void)
{
    buddy_t buddy;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":1,\"buddy_id\":\"bdy_v1\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"duration_sec\":75,\"initial_node\":\"start\",\"variables\":[],\"pressure\":{\"initial\":50,\"rise_per_sec\":1,\"min\":0,\"max\":100},\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[{\"event\":\"touch.tap\",\"to\":\"end\",\"actions\":[{\"op\":\"game.end\",\"outcome\":\"escaped\"}]}]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[{\"op\":\"game.end\",\"outcome\":\"carried_away\"}]}]},\"resources\":[]}";
    TEST_ASSERT(!buddy_parse(json, strlen(json), &buddy, err));
    return 0;
}

static int test_v1_timeout_still_works(void)
{
    buddy_t buddy;
    buddy_session_t session;
    char err[BUDDY_ERR_LEN];
    const char *json = "{\"schema_version\":1,\"buddy_id\":\"bdy_v1\",\"content_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"content\":{\"name\":\"n\",\"personality\":\"p\",\"gameplay_summary\":\"g\",\"theme_tags\":[\"t\"]},\"avatar\":{\"face\":\"round\",\"eyes\":\"sleepy\",\"mouth\":\"small\",\"palette\":[\"#112233\",\"#445566\"],\"motion_style\":\"drowsy\"},\"game\":{\"duration_sec\":2,\"initial_node\":\"start\",\"variables\":[],\"nodes\":[{\"id\":\"start\",\"title\":\"s\",\"instruction\":\"i\",\"transitions\":[]},{\"id\":\"end\",\"title\":\"e\",\"instruction\":\"i\",\"on_enter\":[{\"op\":\"game.end\",\"outcome\":\"carried_away\"}]}]},\"resources\":[]}";
    TEST_ASSERT(buddy_parse(json, strlen(json), &buddy, err));
    buddy_session_start(&session, &buddy);
    TEST_ASSERT_EQ(session.remaining_sec, 2);
    buddy_session_handle(&session, BUDDY_EVENT_TIMER, NULL);
    TEST_ASSERT_EQ(session.remaining_sec, 1);
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_NONE);
    buddy_session_handle(&session, BUDDY_EVENT_TIMER, NULL);
    TEST_ASSERT_EQ(session.outcome, BUDDY_OUTCOME_CARRIED_AWAY);
    return 0;
}

typedef int (*test_fn_t)(void);

int main(void)
{
    test_fn_t tests[] = {
        test_v1_parse_last_one,
        test_v2_parse_minimal,
        test_v2_pressure_erodes_to_carried_away,
        test_v2_pressure_relief_to_escaped,
        test_v2_pressure_condition,
        test_v2_directional_swipe_fallback,
        test_v2_directional_swipe_priority,
        test_v2_rapid_tap_window_and_reset,
        test_v2_shake_event,
        test_v2_quips_rejected_missing_side,
        test_v2_quips_rejected_too_long,
        test_v1_rejects_v2_event,
        test_v1_rejects_pressure,
        test_v1_timeout_still_works,
    };
    int total = sizeof(tests) / sizeof(tests[0]);
    int passed = 0;
    for (int i = 0; i < total; i++) {
        if (tests[i]() == 0) {
            passed++;
        } else {
            fprintf(stderr, "  test %d failed\n", i);
        }
    }
    printf("%d/%d tests passed\n", passed, total);
    return passed == total ? 0 : 1;
}
