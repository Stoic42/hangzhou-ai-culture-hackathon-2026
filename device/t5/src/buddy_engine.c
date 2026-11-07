/**
 * @file buddy_engine.c
 * @brief Rule pack v1/v2 parser/validator and single-threaded game session.
 */
#include "buddy_engine.h"

#include <stdio.h>
#include <string.h>

#include "cJSON.h"

#define SCHEMA_VERSION_MIN 1
#define SCHEMA_VERSION_MAX 2
#define DURATION_V1_MIN_SEC 60
#define DURATION_V1_MAX_SEC 90
#define DURATION_V2_MIN_SEC 60
#define DURATION_V2_MAX_SEC 180
#define PRESSURE_MIN_BOUND 0
#define PRESSURE_MAX_BOUND 1000
#define COMBO_WINDOW_MS 400

static const char * const EVENT_NAMES[] = {
    "game.start", "touch.tap", "touch.long_press", "touch.swipe", "timer.elapsed",
    "touch.swipe_left", "touch.swipe_right", "touch.swipe_up", "touch.swipe_down",
    "touch.rapid_tap", "imu.shake"
};

/* v1 allows indices [0 .. BUDDY_EVENT_TIMER]; v2 adds the rest. */
#define BUDDY_EVENT_V1_COUNT (BUDDY_EVENT_TIMER + 1)

static bool is_v1_event(buddy_event_t ev)
{
    return ev < BUDDY_EVENT_V1_COUNT;
}

static bool parse_event(const char *name, buddy_event_t *out)
{
    for (int i = 0; i < BUDDY_EVENT_COUNT; i++) {
        if (strcmp(name, EVENT_NAMES[i]) == 0) {
            *out = (buddy_event_t)i;
            return true;
        }
    }
    return false;
}

static bool parse_cmp(const char *name, buddy_cmp_t *out)
{
    static const char * const names[] = {"eq", "neq", "gt", "gte", "lt", "lte"};
    for (int i = 0; i < 6; i++) {
        if (strcmp(name, names[i]) == 0) {
            *out = (buddy_cmp_t)i;
            return true;
        }
    }
    return false;
}

static bool parse_enum(const char *const *table, int count, const char *name, int *out)
{
    for (int i = 0; i < count; i++) {
        if (strcmp(name, table[i]) == 0) {
            *out = i;
            return true;
        }
    }
    return false;
}

static bool parse_hex64(const char *text, uint8_t out[32])
{
    if (!text || strlen(text) != 64) {
        return false;
    }
    for (int i = 0; i < 32; i++) {
        unsigned int byte = 0;
        if (sscanf(text + i * 2, "%2x", &byte) != 1) {
            return false;
        }
        out[i] = (uint8_t)byte;
    }
    return true;
}

static bool parse_color(const char *text, uint32_t *out)
{
    unsigned int r = 0, g = 0, b = 0;
    if (!text || strlen(text) != 7 || text[0] != '#') {
        return false;
    }
    if (sscanf(text + 1, "%2x%2x%2x", &r, &g, &b) != 3) {
        return false;
    }
    *out = ((uint32_t)r << 16) | ((uint32_t)g << 8) | b;
    return true;
}

static bool cjson_is_int(const cJSON *item)
{
    return cJSON_IsNumber(item) && (double)(int)item->valuedouble == item->valuedouble;
}

static void fail(char *err, const char *msg)
{
    if (err) {
        snprintf(err, BUDDY_ERR_LEN, "%s", msg);
    }
}

int8_t buddy_find_node(const buddy_t *buddy, const char *node_id)
{
    if (!node_id) {
        return -1;
    }
    for (int i = 0; i < buddy->node_count; i++) {
        if (strcmp(buddy->nodes[i].id, node_id) == 0) {
            return (int8_t)i;
        }
    }
    return -1;
}

int8_t buddy_find_var(const buddy_t *buddy, const char *name)
{
    if (!name) {
        return -1;
    }
    for (int i = 0; i < buddy->var_count; i++) {
        if (strcmp(buddy->vars[i].name, name) == 0) {
            return (int8_t)i;
        }
    }
    return -1;
}

static bool parse_condition(const cJSON *cond, buddy_t *buddy, buddy_condition_t *out,
                            char *err, const char *where)
{
    const cJSON *left, *op, *right;

    if (!cJSON_IsObject(cond)) {
        fail(err, "condition must be object");
        return false;
    }
    left = cJSON_GetObjectItem(cond, "left");
    op = cJSON_GetObjectItem(cond, "op");
    right = cJSON_GetObjectItem(cond, "right");

    memset(out, 0, sizeof(*out));
    out->var = -1;

    if (cJSON_IsObject(left)) {
        /* require exactly one key: var / remaining_sec / pressure */
        int key_count = cJSON_GetArraySize(left);
        if (key_count != 1) {
            fail(err, "condition.left must be exactly one of {var}, {remaining_sec:true}, {pressure:true}");
            return false;
        }
        const cJSON *var = cJSON_GetObjectItem(left, "var");
        const cJSON *remaining = cJSON_GetObjectItem(left, "remaining_sec");
        const cJSON *pressure = cJSON_GetObjectItem(left, "pressure");
        if (cJSON_IsString(var)) {
            out->var = buddy_find_var(buddy, var->valuestring);
            if (out->var < 0) {
                fail(err, "condition uses undeclared variable");
                return false;
            }
        } else if (cJSON_IsBool(remaining) && cJSON_IsTrue(remaining)) {
            out->is_remaining = true;
        } else if (cJSON_IsBool(pressure) && cJSON_IsTrue(pressure)) {
            if (buddy->schema_version < 2) {
                fail(err, "pressure condition requires schema_version 2");
                return false;
            }
            out->is_pressure = true;
        } else {
            fail(err, "condition.left must be exactly one of {var}, {remaining_sec:true}, {pressure:true}");
            return false;
        }
    } else {
        fail(err, "condition.left missing");
        return false;
    }

    if (!cJSON_IsString(op) || !parse_cmp(op->valuestring, &out->op)) {
        fail(err, "condition.op not in whitelist");
        return false;
    }
    if (!cjson_is_int(right)) {
        fail(err, "condition.right must be an integer constant");
        return false;
    }
    out->right = (int)right->valuedouble;
    (void)where;
    return true;
}

static bool parse_actions(const cJSON *actions, buddy_t *buddy, buddy_action_t *out,
                          uint8_t *out_count, char *err, const char *where)
{
    static const char *const expr_names[] = {"neutral", "pleading", "happy", "smug", "anxious", "sleepy", "angry"};
    static const char *const motion_names[] = {"still", "breathe", "shake", "bounce", "nod"};
    int count = 0;

    if (!cJSON_IsArray(actions)) {
        fail(err, "actions must be an array");
        return false;
    }
    memset(out, 0, sizeof(buddy_action_t) * BUDDY_MAX_ACTIONS);
    *out_count = 0;

    const cJSON *action = NULL;
    cJSON_ArrayForEach(action, actions)
    {
        if (count >= BUDDY_MAX_ACTIONS) {
            fail(err, "too many actions in one list");
            return false;
        }
        buddy_action_t *dst = &out[count++];
        const cJSON *jop = cJSON_GetObjectItem(action, "op");
        if (!cJSON_IsString(jop)) {
            fail(err, "action.op missing");
            return false;
        }
        if (strcmp(jop->valuestring, "avatar.expression") == 0) {
            const cJSON *value = cJSON_GetObjectItem(action, "value");
            dst->op = BUDDY_OP_EXPRESSION;
            if (!cJSON_IsString(value) || !parse_enum(expr_names, 7, value->valuestring, (int *)&dst->expr)) {
                fail(err, "unknown avatar.expression value");
                return false;
            }
        } else if (strcmp(jop->valuestring, "avatar.motion") == 0) {
            const cJSON *value = cJSON_GetObjectItem(action, "value");
            dst->op = BUDDY_OP_MOTION;
            if (!cJSON_IsString(value) || !parse_enum(motion_names, 5, value->valuestring, (int *)&dst->motion)) {
                fail(err, "unknown avatar.motion value");
                return false;
            }
        } else if (strcmp(jop->valuestring, "audio.play") == 0) {
            const cJSON *rid = cJSON_GetObjectItem(action, "resource_id");
            dst->op = BUDDY_OP_AUDIO_PLAY;
            if (!cJSON_IsString(rid) || rid->valuestring[0] == '\0') {
                fail(err, "audio.play missing resource_id");
                return false;
            }
            dst->resource_id = rid->valuestring;
        } else if (strcmp(jop->valuestring, "timer.start") == 0) {
            const cJSON *seconds = cJSON_GetObjectItem(action, "seconds");
            dst->op = BUDDY_OP_TIMER_START;
            if (!cjson_is_int(seconds) || (int)seconds->valuedouble <= 0) {
                fail(err, "timer.start seconds must be a positive integer");
                return false;
            }
            dst->int_value = (int)seconds->valuedouble;
        } else if (strcmp(jop->valuestring, "var.set") == 0 || strcmp(jop->valuestring, "var.increment") == 0) {
            const cJSON *name = cJSON_GetObjectItem(action, "name");
            const cJSON *value = cJSON_GetObjectItem(action, "value");
            dst->op = strcmp(jop->valuestring, "var.set") == 0 ? BUDDY_OP_VAR_SET : BUDDY_OP_VAR_INCREMENT;
            if (!cJSON_IsString(name) || (dst->var = buddy_find_var(buddy, name->valuestring)) < 0) {
                fail(err, "action references undeclared variable");
                return false;
            }
            if (!cjson_is_int(value)) {
                fail(err, "action value must be an integer");
                return false;
            }
            dst->int_value = (int)value->valuedouble;
        } else if (strcmp(jop->valuestring, "game.end") == 0) {
            const cJSON *outcome = cJSON_GetObjectItem(action, "outcome");
            dst->op = BUDDY_OP_GAME_END;
            if (!cJSON_IsString(outcome)) {
                fail(err, "game.end outcome missing");
                return false;
            }
            if (strcmp(outcome->valuestring, "escaped") == 0) {
                dst->outcome = BUDDY_OUTCOME_ESCAPED;
            } else if (strcmp(outcome->valuestring, "carried_away") == 0) {
                dst->outcome = BUDDY_OUTCOME_CARRIED_AWAY;
            } else {
                fail(err, "game.end outcome must be escaped or carried_away");
                return false;
            }
        } else if (strcmp(jop->valuestring, "pressure.adjust") == 0) {
            const cJSON *value = cJSON_GetObjectItem(action, "value");
            if (buddy->schema_version < 2) {
                fail(err, "pressure.adjust requires schema_version 2");
                return false;
            }
            dst->op = BUDDY_OP_PRESSURE_ADJUST;
            if (!cjson_is_int(value)) {
                fail(err, "pressure.adjust value must be an integer");
                return false;
            }
            int v = (int)value->valuedouble;
            if (v < -PRESSURE_MAX_BOUND || v > PRESSURE_MAX_BOUND) {
                fail(err, "pressure.adjust value magnitude must be <= 1000");
                return false;
            }
            dst->int_value = v;
        } else {
            fail(err, "action op not in whitelist");
            return false;
        }
    }
    *out_count = (uint8_t)count;
    (void)where;
    return true;
}

bool buddy_parse(const char *json, uint32_t json_len, buddy_t *out, char *err)
{
    static const char *const face_names[] = {"round", "square", "bean"};
    static const char *const eyes_names[] = {"sleepy", "wide", "side", "dot"};
    static const char *const mouth_names[] = {"small", "grin", "flat", "open"};
    static const char *const mstyle_names[] = {"drowsy", "jittery", "still", "bouncy"};
    cJSON *root = NULL;
    bool ok = false;

    memset(out, 0, sizeof(*out));
    out->initial_node = -1;
    if (err) {
        err[0] = '\0';
    }

    root = cJSON_ParseWithLength(json, json_len);
    if (!root) {
        fail(err, "json parse failed");
        return false;
    }

    const cJSON *schema = cJSON_GetObjectItem(root, "schema_version");
    if (!cjson_is_int(schema) || (int)schema->valuedouble < SCHEMA_VERSION_MIN ||
        (int)schema->valuedouble > SCHEMA_VERSION_MAX) {
        fail(err, "schema_version must be 1 or 2");
        goto end;
    }
    out->schema_version = (uint8_t)(int)schema->valuedouble;

    const cJSON *buddy_id = cJSON_GetObjectItem(root, "buddy_id");
    if (!cJSON_IsString(buddy_id) || buddy_id->valuestring[0] == '\0') {
        fail(err, "buddy_id must be a non-empty string");
        goto end;
    }
    out->buddy_id = buddy_id->valuestring;

    const cJSON *content_hash = cJSON_GetObjectItem(root, "content_hash");
    uint8_t hash_bytes[32];
    if (!cJSON_IsString(content_hash) || !parse_hex64(content_hash->valuestring, hash_bytes)) {
        fail(err, "content_hash must be 64 lowercase hex chars");
        goto end;
    }

    const cJSON *content = cJSON_GetObjectItem(root, "content");
    if (!cJSON_IsObject(content)) {
        fail(err, "content must be an object");
        goto end;
    }
    const char *content_fields[] = {"name", "personality", "gameplay_summary"};
    const char **content_slots[] = {&out->name, &out->personality, &out->gameplay_summary};
    for (int i = 0; i < 3; i++) {
        const cJSON *field = cJSON_GetObjectItem(content, content_fields[i]);
        if (!cJSON_IsString(field) || field->valuestring[0] == '\0') {
            fail(err, "content field must be a non-empty string");
            goto end;
        }
        *content_slots[i] = field->valuestring;
    }
    const cJSON *tags = cJSON_GetObjectItem(content, "theme_tags");
    if (!cJSON_IsArray(tags)) {
        fail(err, "content.theme_tags must be an array");
        goto end;
    }
    {
        const cJSON *tag = NULL;
        cJSON_ArrayForEach(tag, tags)
        {
            if (!cJSON_IsString(tag) || tag->valuestring[0] == '\0' ||
                out->tag_count >= BUDDY_MAX_TAGS) {
                fail(err, "theme_tags must be non-empty strings");
                goto end;
            }
            out->tags[out->tag_count++] = tag->valuestring;
        }
        if (out->tag_count == 0) {
            fail(err, "theme_tags must not be empty");
            goto end;
        }
    }

    const cJSON *avatar = cJSON_GetObjectItem(root, "avatar");
    if (!cJSON_IsObject(avatar)) {
        fail(err, "avatar must be an object");
        goto end;
    }
    {
        const cJSON *face = cJSON_GetObjectItem(avatar, "face");
        const cJSON *eyes = cJSON_GetObjectItem(avatar, "eyes");
        const cJSON *mouth = cJSON_GetObjectItem(avatar, "mouth");
        const cJSON *mstyle = cJSON_GetObjectItem(avatar, "motion_style");
        if (!cJSON_IsString(face) || !parse_enum(face_names, 3, face->valuestring, (int *)&out->face) ||
            !cJSON_IsString(eyes) || !parse_enum(eyes_names, 4, eyes->valuestring, (int *)&out->eyes) ||
            !cJSON_IsString(mouth) || !parse_enum(mouth_names, 4, mouth->valuestring, (int *)&out->mouth) ||
            !cJSON_IsString(mstyle) || !parse_enum(mstyle_names, 4, mstyle->valuestring, (int *)&out->motion_style)) {
            fail(err, "avatar enum value not in whitelist");
            goto end;
        }
        const cJSON *palette = cJSON_GetObjectItem(avatar, "palette");
        if (!cJSON_IsArray(palette)) {
            fail(err, "avatar.palette must be an array");
            goto end;
        }
        const cJSON *color = NULL;
        cJSON_ArrayForEach(color, palette)
        {
            if (!cJSON_IsString(color) || out->palette_count >= BUDDY_MAX_PALETTE ||
                !parse_color(color->valuestring, &out->palette[out->palette_count])) {
                fail(err, "palette must be 2-4 #RRGGBB colors");
                goto end;
            }
            out->palette_count++;
        }
        if (out->palette_count < 2) {
            fail(err, "palette must contain at least 2 colors");
            goto end;
        }
    }

    const cJSON *game = cJSON_GetObjectItem(root, "game");
    if (!cJSON_IsObject(game)) {
        fail(err, "game must be an object");
        goto end;
    }
    const cJSON *duration = cJSON_GetObjectItem(game, "duration_sec");
    if (out->schema_version == 1) {
        if (!cjson_is_int(duration) || (int)duration->valuedouble < DURATION_V1_MIN_SEC ||
            (int)duration->valuedouble > DURATION_V1_MAX_SEC) {
            fail(err, "duration_sec must be 60-90");
            goto end;
        }
        out->duration_sec = (int)duration->valuedouble;
    } else {
        if (duration != NULL) {
            if (!cjson_is_int(duration) || (int)duration->valuedouble < DURATION_V2_MIN_SEC ||
                (int)duration->valuedouble > DURATION_V2_MAX_SEC) {
                fail(err, "duration_sec must be 60-180 when present");
                goto end;
            }
            out->duration_sec = (int)duration->valuedouble;
        } else {
            out->duration_sec = 0;
        }
    }

    const cJSON *variables = cJSON_GetObjectItem(game, "variables");
    if (!cJSON_IsArray(variables)) {
        fail(err, "game.variables must be an array");
        goto end;
    }
    {
        const cJSON *var = NULL;
        cJSON_ArrayForEach(var, variables)
        {
            const cJSON *name = cJSON_GetObjectItem(var, "name");
            const cJSON *type = cJSON_GetObjectItem(var, "type");
            const cJSON *initial = cJSON_GetObjectItem(var, "initial");
            if (!cJSON_IsString(name) || name->valuestring[0] == '\0' ||
                buddy_find_var(out, name->valuestring) >= 0 ||
                out->var_count >= BUDDY_MAX_VARS) {
                fail(err, "variable name invalid or duplicated");
                goto end;
            }
            if (!cJSON_IsString(type) || strcmp(type->valuestring, "int") != 0) {
                fail(err, "variable type must be int");
                goto end;
            }
            if (!cjson_is_int(initial)) {
                fail(err, "variable initial must be an integer");
                goto end;
            }
            out->vars[out->var_count].name = name->valuestring;
            out->vars[out->var_count].initial = (int)initial->valuedouble;
            out->var_count++;
        }
    }

    /* v2 pressure and quips (v1 must not contain them) */
    {
        const cJSON *pressure = cJSON_GetObjectItem(game, "pressure");
        const cJSON *quips = cJSON_GetObjectItem(game, "quips");
        if (out->schema_version == 1) {
            if (pressure != NULL) {
                fail(err, "schema_version 1 must not contain game.pressure");
                goto end;
            }
            if (quips != NULL) {
                fail(err, "schema_version 1 must not contain game.quips");
                goto end;
            }
        } else {
            if (!cJSON_IsObject(pressure)) {
                fail(err, "game.pressure must be an object");
                goto end;
            }
            const cJSON *p_initial = cJSON_GetObjectItem(pressure, "initial");
            const cJSON *p_rise = cJSON_GetObjectItem(pressure, "rise_per_sec");
            const cJSON *p_min = cJSON_GetObjectItem(pressure, "min");
            const cJSON *p_max = cJSON_GetObjectItem(pressure, "max");
            if (!cjson_is_int(p_initial) || !cjson_is_int(p_rise) ||
                !cjson_is_int(p_min) || !cjson_is_int(p_max)) {
                fail(err, "pressure fields must be integers");
                goto end;
            }
            out->pressure.initial = (int)p_initial->valuedouble;
            out->pressure.rise_per_sec = (int)p_rise->valuedouble;
            out->pressure.min = (int)p_min->valuedouble;
            out->pressure.max = (int)p_max->valuedouble;
            if (out->pressure.min < PRESSURE_MIN_BOUND || out->pressure.max > PRESSURE_MAX_BOUND ||
                !(out->pressure.min < out->pressure.initial && out->pressure.initial < out->pressure.max) ||
                out->pressure.rise_per_sec < 1 || out->pressure.rise_per_sec > PRESSURE_MAX_BOUND) {
                fail(err, "pressure must satisfy 0<=min<initial<max<=1000 and 1<=rise_per_sec<=1000");
                goto end;
            }

            if (!cJSON_IsObject(quips)) {
                fail(err, "game.quips must be an object");
                goto end;
            }
            const char *quip_keys[] = {"escaped", "carried_away"};
            uint8_t *quip_counts[] = {&out->quips.escaped_count, &out->quips.carried_away_count};
            const char **quip_slots[] = {out->quips.escaped, out->quips.carried_away};
            for (int q = 0; q < 2; q++) {
                const cJSON *arr = cJSON_GetObjectItem(quips, quip_keys[q]);
                if (!cJSON_IsArray(arr)) {
                    fail(err, "game.quips must contain escaped and carried_away arrays");
                    goto end;
                }
                uint8_t count = 0;
                const cJSON *item = NULL;
                cJSON_ArrayForEach(item, arr)
                {
                    if (!cJSON_IsString(item) || item->valuestring[0] == '\0') {
                        fail(err, "quips must be non-empty strings");
                        goto end;
                    }
                    if (count >= BUDDY_MAX_QUIPS) {
                        fail(err, "quips list must contain at most 4 strings");
                        goto end;
                    }
                    size_t len = strlen(item->valuestring);
                    /* UTF-8 codepoint count: simple skip continuation bytes */
                    size_t cp = 0;
                    for (size_t i = 0; i < len; i++) {
                        if ((item->valuestring[i] & 0xC0) != 0x80) {
                            cp++;
                        }
                    }
                    if (cp < 1 || cp > 40) {
                        fail(err, "quip must be 1-40 UTF-8 characters");
                        goto end;
                    }
                    quip_slots[q][count++] = item->valuestring;
                }
                *quip_counts[q] = count;
                if (count < 1) {
                    fail(err, "quips list must contain at least one string");
                    goto end;
                }
            }
        }
    }

    const cJSON *nodes = cJSON_GetObjectItem(game, "nodes");
    if (!cJSON_IsArray(nodes)) {
        fail(err, "game.nodes must be a non-empty array");
        goto end;
    }
    {
        const cJSON *node = NULL;
        cJSON_ArrayForEach(node, nodes)
        {
            if (out->node_count >= BUDDY_MAX_NODES) {
                fail(err, "too many nodes");
                goto end;
            }
            buddy_node_t *dst = &out->nodes[out->node_count];
            const cJSON *id = cJSON_GetObjectItem(node, "id");
            const cJSON *title = cJSON_GetObjectItem(node, "title");
            const cJSON *instruction = cJSON_GetObjectItem(node, "instruction");
            if (!cJSON_IsString(id) || id->valuestring[0] == '\0' ||
                buddy_find_node(out, id->valuestring) >= 0) {
                fail(err, "node id invalid or duplicated");
                goto end;
            }
            if (!cJSON_IsString(title) || title->valuestring[0] == '\0' ||
                !cJSON_IsString(instruction) || instruction->valuestring[0] == '\0') {
                fail(err, "node requires non-empty title and instruction");
                goto end;
            }
            dst->id = id->valuestring;
            dst->title = title->valuestring;
            dst->instruction = instruction->valuestring;
            const cJSON *on_enter = cJSON_GetObjectItem(node, "on_enter");
            if (on_enter != NULL &&
                !parse_actions(on_enter, out, dst->on_enter, &dst->on_enter_count, err, dst->id)) {
                goto end;
            }
            const cJSON *transitions = cJSON_GetObjectItem(node, "transitions");
            if (transitions != NULL && !cJSON_IsArray(transitions)) {
                fail(err, "node transitions must be an array");
                goto end;
            }
            const cJSON *tr = NULL;
            if (transitions != NULL) cJSON_ArrayForEach(tr, transitions)
            {
                if (dst->transition_count >= BUDDY_MAX_TRANSITIONS) {
                    fail(err, "too many transitions on one node");
                    goto end;
                }
                buddy_transition_t *tdst = &dst->transitions[dst->transition_count];
                const cJSON *event = cJSON_GetObjectItem(tr, "event");
                const cJSON *to = cJSON_GetObjectItem(tr, "to");
                const cJSON *condition = cJSON_GetObjectItem(tr, "condition");
                if (!cJSON_IsString(event) || !parse_event(event->valuestring, &tdst->event)) {
                    fail(err, "transition event not in whitelist");
                    goto end;
                }
                if (out->schema_version == 1 && !is_v1_event(tdst->event)) {
                    fail(err, "transition event not allowed in schema_version 1");
                    goto end;
                }
                if (!cJSON_IsString(to) || to->valuestring[0] == '\0') {
                    fail(err, "transition missing target node");
                    goto end;
                }
                if (condition != NULL) {
                    tdst->has_condition = true;
                    if (!parse_condition(condition, out, &tdst->condition, err, dst->id)) {
                        goto end;
                    }
                }
                const cJSON *actions = cJSON_GetObjectItem(tr, "actions");
                if (actions != NULL &&
                    !parse_actions(actions, out, tdst->actions, &tdst->action_count, err, dst->id)) {
                    goto end;
                }
                dst->transition_count++;
            }
            out->node_count++;
        }
        if (out->node_count == 0) {
            fail(err, "game.nodes must not be empty");
            goto end;
        }
    }

    /* resolve transition targets now that all nodes are known */
    {
        const cJSON *node = NULL;
        int ni = 0;
        cJSON_ArrayForEach(node, nodes)
        {
            buddy_node_t *dst = &out->nodes[ni++];
            const cJSON *transitions = cJSON_GetObjectItem(node, "transitions");
            const cJSON *tr = NULL;
            int ti = 0;
            if (transitions != NULL) cJSON_ArrayForEach(tr, transitions)
            {
                const cJSON *to = cJSON_GetObjectItem(tr, "to");
                dst->transitions[ti].to = buddy_find_node(out, to->valuestring);
                if (dst->transitions[ti].to < 0) {
                    fail(err, "transition target node does not exist");
                    goto end;
                }
                ti++;
            }
        }
    }

    const cJSON *initial = cJSON_GetObjectItem(game, "initial_node");
    if (!cJSON_IsString(initial) || (out->initial_node = buddy_find_node(out, initial->valuestring)) < 0) {
        fail(err, "initial_node not present in node table");
        goto end;
    }

    /* dual endings: collect outcome nodes (on_enter game.end or transition target of one) */
    {
        bool escaped_seen = false, carried_seen = false;
        for (int i = 0; i < out->node_count && !(escaped_seen && carried_seen); i++) {
            buddy_node_t *node = &out->nodes[i];
            for (int j = 0; j < node->on_enter_count; j++) {
                if (node->on_enter[j].op == BUDDY_OP_GAME_END) {
                    escaped_seen |= node->on_enter[j].outcome == BUDDY_OUTCOME_ESCAPED;
                    carried_seen |= node->on_enter[j].outcome == BUDDY_OUTCOME_CARRIED_AWAY;
                }
            }
            for (int j = 0; j < node->transition_count; j++) {
                buddy_transition_t *tr = &node->transitions[j];
                for (int k = 0; k < tr->action_count; k++) {
                    if (tr->actions[k].op == BUDDY_OP_GAME_END) {
                        escaped_seen |= tr->actions[k].outcome == BUDDY_OUTCOME_ESCAPED;
                        carried_seen |= tr->actions[k].outcome == BUDDY_OUTCOME_CARRIED_AWAY;
                    }
                }
            }
        }
        if (!escaped_seen) {
            fail(err, "missing escaped ending");
            goto end;
        }
        if (!carried_seen) {
            fail(err, "missing carried_away ending");
            goto end;
        }
    }

    /* graph reachability from initial_node (edges ignore conditions) */
    {
        bool visited[BUDDY_MAX_NODES] = {false};
        int8_t stack[BUDDY_MAX_NODES];
        int sp = 0;
        stack[sp++] = out->initial_node;
        while (sp > 0) {
            int8_t cur = stack[--sp];
            if (visited[cur]) {
                continue;
            }
            visited[cur] = true;
            for (int j = 0; j < out->nodes[cur].transition_count; j++) {
                int8_t to = out->nodes[cur].transitions[j].to;
                if (!visited[to]) {
                    stack[sp++] = to;
                }
            }
        }
        bool escaped_reachable = false;
        for (int i = 0; i < out->node_count; i++) {
            if (!visited[i]) {
                continue;
            }
            buddy_node_t *node = &out->nodes[i];
            for (int j = 0; j < node->on_enter_count; j++) {
                escaped_reachable |= node->on_enter[j].op == BUDDY_OP_GAME_END &&
                                     node->on_enter[j].outcome == BUDDY_OUTCOME_ESCAPED;
            }
            for (int j = 0; j < node->transition_count; j++) {
                buddy_transition_t *tr = &node->transitions[j];
                for (int k = 0; k < tr->action_count; k++) {
                    if (tr->actions[k].op == BUDDY_OP_GAME_END &&
                        tr->actions[k].outcome == BUDDY_OUTCOME_ESCAPED) {
                        escaped_reachable = true;
                    }
                }
            }
        }
        if (!escaped_reachable) {
            fail(err, "no escaped ending reachable from initial_node");
            goto end;
        }
        /* carried_away is always reachable: the global timeout (v1) or pressure (v2) forces it */
    }

    /* resources */
    {
        const cJSON *resources = cJSON_GetObjectItem(root, "resources");
        if (!cJSON_IsArray(resources)) {
            fail(err, "resources must be an array");
            goto end;
        }
        const cJSON *res = NULL;
        cJSON_ArrayForEach(res, resources)
        {
            const cJSON *rid = cJSON_GetObjectItem(res, "resource_id");
            const cJSON *kind = cJSON_GetObjectItem(res, "kind");
            const cJSON *url = cJSON_GetObjectItem(res, "url");
            const cJSON *sha = cJSON_GetObjectItem(res, "sha256");
            const cJSON *size = cJSON_GetObjectItem(res, "size");
            if (!cJSON_IsString(rid) || rid->valuestring[0] == '\0' ||
                out->resource_count >= BUDDY_MAX_RESOURCES) {
                fail(err, "resource_id invalid or duplicated");
                goto end;
            }
            for (int i = 0; i < out->resource_count; i++) {
                if (strcmp(out->resources[i].resource_id, rid->valuestring) == 0) {
                    fail(err, "resource_id duplicated");
                    goto end;
                }
            }
            if (!cJSON_IsString(kind) || strcmp(kind->valuestring, "audio") != 0) {
                fail(err, "resource kind must be audio");
                goto end;
            }
            if (!cJSON_IsString(url) ||
                (strncmp(url->valuestring, "builtin://", 10) != 0 &&
                 strncmp(url->valuestring, "https://", 8) != 0)) {
                fail(err, "resource url must be builtin:// or https://");
                goto end;
            }
            if (!cJSON_IsString(sha) || !parse_hex64(sha->valuestring, out->resources[out->resource_count].sha256)) {
                fail(err, "resource sha256 must be 64 lowercase hex chars");
                goto end;
            }
            if (!cjson_is_int(size) || (int)size->valuedouble < 0) {
                fail(err, "resource size must be a non-negative integer");
                goto end;
            }
            out->resources[out->resource_count].resource_id = rid->valuestring;
            out->resources[out->resource_count].url = url->valuestring;
            out->resources[out->resource_count].size = (uint32_t)size->valuedouble;
            out->resource_count++;
        }
    }

    /* detach the tree so it outlives this call; caller keeps `out` static */
    ok = true;
end:
    if (!ok) {
        cJSON_Delete(root);
    } else {
        /* stash the tree pointer: freed never (static presets live forever) */
    }
    return ok;
}

void buddy_session_start(buddy_session_t *session, const buddy_t *buddy)
{
    memset(session, 0, sizeof(*session));
    session->buddy = buddy;
    session->current_node = buddy->initial_node;
    for (int i = 0; i < buddy->var_count; i++) {
        session->var_values[i] = buddy->vars[i].initial;
    }
    session->remaining_sec = buddy->duration_sec;
    session->outcome = BUDDY_OUTCOME_NONE;
    session->expression = BUDDY_EXPR_NEUTRAL;
    session->motion = BUDDY_MOTION_STILL;
    if (buddy->schema_version >= 2) {
        session->pressure = buddy->pressure.initial;
    }
}

static bool condition_holds(const buddy_session_t *session, const buddy_condition_t *cond)
{
    int left;
    if (cond->is_remaining) {
        left = session->remaining_sec;
    } else if (cond->is_pressure) {
        left = session->pressure;
    } else {
        left = session->var_values[cond->var];
    }
    switch (cond->op) {
    case BUDDY_CMP_EQ:
        return left == cond->right;
    case BUDDY_CMP_NEQ:
        return left != cond->right;
    case BUDDY_CMP_GT:
        return left > cond->right;
    case BUDDY_CMP_GTE:
        return left >= cond->right;
    case BUDDY_CMP_LT:
        return left < cond->right;
    case BUDDY_CMP_LTE:
        return left <= cond->right;
    }
    return false;
}

static void run_actions(buddy_session_t *session, const buddy_action_t *actions,
                        uint8_t count, const buddy_session_ops_t *ops)
{
    for (int i = 0; i < count; i++) {
        const buddy_action_t *action = &actions[i];
        switch (action->op) {
        case BUDDY_OP_EXPRESSION:
            session->expression = action->expr;
            break;
        case BUDDY_OP_MOTION:
            session->motion = action->motion;
            break;
        case BUDDY_OP_AUDIO_PLAY:
            if (ops && ops->play_resource) {
                ops->play_resource(action->resource_id);
            }
            break;
        case BUDDY_OP_TIMER_START:
            /* v1 presets do not schedule per-node timers; global countdown covers timing */
            break;
        case BUDDY_OP_VAR_SET:
            session->var_values[action->var] = action->int_value;
            break;
        case BUDDY_OP_VAR_INCREMENT:
            session->var_values[action->var] += action->int_value;
            break;
        case BUDDY_OP_GAME_END:
            session->outcome = action->outcome;
            break;
        case BUDDY_OP_PRESSURE_ADJUST:
            session->pressure += action->int_value;
            if (action->int_value > 0) {
                session->mistakes++;
            } else if (action->int_value < 0) {
                session->relieves++;
            }
            break;
        default:
            break;
        }
    }
}

static void enter_node(buddy_session_t *session, int8_t node_index, const buddy_session_ops_t *ops)
{
    session->current_node = node_index;
    const buddy_node_t *node = &session->buddy->nodes[node_index];
    run_actions(session, node->on_enter, node->on_enter_count, ops);
}

static void enter_outcome_node(buddy_session_t *session, buddy_outcome_t outcome,
                               const buddy_session_ops_t *ops)
{
    /* find a node that hosts this outcome and enter it; fallback to raw outcome */
    for (int i = 0; i < session->buddy->node_count; i++) {
        const buddy_node_t *node = &session->buddy->nodes[i];
        for (int j = 0; j < node->on_enter_count; j++) {
            if (node->on_enter[j].op == BUDDY_OP_GAME_END &&
                node->on_enter[j].outcome == outcome) {
                enter_node(session, (int8_t)i, ops);
                session->outcome = outcome;
                return;
            }
        }
        for (int j = 0; j < node->transition_count; j++) {
            const buddy_transition_t *tr = &node->transitions[j];
            for (int k = 0; k < tr->action_count; k++) {
                if (tr->actions[k].op == BUDDY_OP_GAME_END &&
                    tr->actions[k].outcome == outcome) {
                    enter_node(session, tr->to, ops);
                    session->outcome = outcome;
                    return;
                }
            }
        }
    }
    /* no dedicated outcome node: keep current node with forced outcome */
    session->outcome = outcome;
}

static void check_auto_ending(buddy_session_t *session, const buddy_session_ops_t *ops)
{
    if (session->outcome != BUDDY_OUTCOME_NONE) {
        return;
    }
    const buddy_t *buddy = session->buddy;
    if (buddy->schema_version >= 2) {
        if (session->pressure >= buddy->pressure.max) {
            enter_outcome_node(session, BUDDY_OUTCOME_CARRIED_AWAY, ops);
            return;
        }
        if (session->pressure <= buddy->pressure.min) {
            enter_outcome_node(session, BUDDY_OUTCOME_ESCAPED, ops);
            return;
        }
    }
    if (buddy->duration_sec > 0 && session->remaining_sec <= 0) {
        enter_outcome_node(session, BUDDY_OUTCOME_CARRIED_AWAY, ops);
    }
}

static bool try_match_event(buddy_session_t *session, buddy_event_t event,
                            const buddy_session_ops_t *ops)
{
    const buddy_node_t *node = &session->buddy->nodes[session->current_node];
    for (int i = 0; i < node->transition_count; i++) {
        const buddy_transition_t *tr = &node->transitions[i];
        if (tr->event != event) {
            continue;
        }
        if (tr->has_condition && !condition_holds(session, &tr->condition)) {
            continue;
        }
        if (ops && ops->on_transition) {
            ops->on_transition(session->buddy, node->id, session->buddy->nodes[tr->to].id, event);
        }
        run_actions(session, tr->actions, tr->action_count, ops);
        enter_node(session, tr->to, ops);
        return true;
    }
    return false;
}

static bool is_directional_swipe(buddy_event_t event)
{
    return event == BUDDY_EVENT_SWIPE_LEFT || event == BUDDY_EVENT_SWIPE_RIGHT ||
           event == BUDDY_EVENT_SWIPE_UP || event == BUDDY_EVENT_SWIPE_DOWN;
}

bool buddy_session_handle_ex(buddy_session_t *session, buddy_event_t event,
                             const buddy_session_ops_t *ops, uint32_t now_ms)
{
    if (session->outcome != BUDDY_OUTCOME_NONE) {
        return false;
    }

    if (event == BUDDY_EVENT_GAME_START) {
        /* explicit start: run the initial node's on_enter (audio, expression) */
        enter_node(session, session->buddy->initial_node, ops);
        check_auto_ending(session, ops);
        return true;
    }

    if (event == BUDDY_EVENT_TIMER) {
        session->elapsed_sec++;
        if (session->buddy->schema_version >= 2) {
            session->pressure += session->buddy->pressure.rise_per_sec;
        }
        if (session->buddy->duration_sec > 0 && session->remaining_sec > 0) {
            session->remaining_sec--;
        }
        check_auto_ending(session, ops);
        return true;
    }

    /* combo tracking for taps */
    if (event == BUDDY_EVENT_TAP && now_ms > 0) {
        if (session->last_tap_ms == 0 || (now_ms - session->last_tap_ms) > COMBO_WINDOW_MS) {
            session->combo_count = 1;
        } else {
            session->combo_count++;
        }
        session->last_tap_ms = now_ms;
        if (session->combo_count > session->combo_peak) {
            session->combo_peak = session->combo_count;
        }
    }

    bool handled = try_match_event(session, event, ops);
    if (handled) {
        check_auto_ending(session, ops);
    }

    /* rapid_tap follows a successful combo tap */
    if (event == BUDDY_EVENT_TAP && now_ms > 0 && session->combo_count >= 2 &&
        session->outcome == BUDDY_OUTCOME_NONE) {
        if (try_match_event(session, BUDDY_EVENT_RAPID_TAP, ops)) {
            check_auto_ending(session, ops);
            handled = true;
        }
    }

    /* directional swipe falls back to generic swipe if no direction transition matched */
    if (!handled && is_directional_swipe(event) && session->outcome == BUDDY_OUTCOME_NONE) {
        if (try_match_event(session, BUDDY_EVENT_SWIPE, ops)) {
            check_auto_ending(session, ops);
            handled = true;
        }
    }

    return handled;
}

bool buddy_session_handle(buddy_session_t *session, buddy_event_t event,
                          const buddy_session_ops_t *ops)
{
    return buddy_session_handle_ex(session, event, ops, 0);
}
